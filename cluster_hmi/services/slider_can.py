from __future__ import annotations

import time
from typing import TYPE_CHECKING

from cluster_hmi.config import AppConfig, CanBusEndpoint
from cluster_hmi.models import FaultFlags
from cluster_hmi.services.base import ServiceThread
from cluster_hmi.slider_can import SliderControllerState, update_controller_state
from cluster_hmi.store import ClusterStore

if TYPE_CHECKING:
    import can

try:
    import can
except ImportError:  # pragma: no cover - optional dependency on target hardware.
    can = None


def safe_shutdown(bus: object | None) -> None:
    if bus is None:
        return
    try:
        shutdown = getattr(bus, "shutdown", None)
        if shutdown is not None:
            shutdown()
    except Exception:
        pass


def open_can_bus(endpoint: CanBusEndpoint, bitrate: int):
    if can is None:
        raise RuntimeError("python-can is not installed")

    kwargs: dict[str, object] = {
        "interface": endpoint.interface,
        "channel": endpoint.channel,
    }

    if endpoint.interface != "socketcan":
        kwargs["bitrate"] = bitrate

    if endpoint.interface == "slcan":
        kwargs["ttyBaudrate"] = endpoint.serial_baudrate

    if endpoint.listen_only:
        kwargs["listen_only"] = True

    return can.Bus(**kwargs)


def scan_bitrate(endpoint: CanBusEndpoint) -> int:
    if endpoint.interface == "socketcan":
        return endpoint.bitrate

    if not endpoint.scan_bitrates:
        raise RuntimeError("no CAN scan bitrates configured")

    last_error: Exception | None = None
    for bitrate in endpoint.scan_bitrates:
        bus = None
        try:
            bus = open_can_bus(endpoint, bitrate)
            msg = bus.recv(timeout=endpoint.scan_seconds)
            if msg is not None:
                return bitrate
        except Exception as exc:  # pragma: no cover - hardware dependent
            last_error = exc
        finally:
            safe_shutdown(bus)

    if last_error is not None:
        raise RuntimeError(f"unable to detect CAN bitrate: {last_error}") from last_error
    raise RuntimeError("no CAN traffic detected while scanning bitrates")


class SliderCanService(ServiceThread):
    def __init__(self, config: AppConfig, endpoint: CanBusEndpoint, store: ClusterStore) -> None:
        super().__init__(name="slider-can")
        self._config = config
        self._endpoint = endpoint
        self._store = store
        self._state = SliderControllerState()

    def run(self) -> None:
        if not self._endpoint.enabled or not self._endpoint.channel:
            return

        while not self.stopped():
            bus = None
            try:
                bitrate = scan_bitrate(self._endpoint) if self._endpoint.scan else self._endpoint.bitrate
                bus = open_can_bus(self._endpoint, bitrate)
                self._read_loop(bus)
            except Exception as exc:  # pragma: no cover - requires live CAN hardware.
                self._store.set_status(f"CAN ERROR: {exc}")
                self._store.update_faults(
                    source="can",
                    flags=FaultFlags(communication=True),
                    messages=[f"CAN link error: {exc}"],
                    timeout_s=max(self._config.stale_after_s, 3.0),
                )
                time.sleep(1.0)
            finally:
                safe_shutdown(bus)

    def _read_loop(self, bus: "can.BusABC") -> None:
        while not self.stopped():
            msg = bus.recv(timeout=self._endpoint.timeout_s)
            if msg is None:
                continue

            self._state = update_controller_state(
                self._state,
                msg.arbitration_id,
                bytes(msg.data),
                is_extended_id=msg.is_extended_id,
                current_signed=self._config.can_current_signed,
            )

            state_1 = self._state.status_1
            state_2 = self._state.status_2
            if state_1 is None and state_2 is None:
                continue

            battery_soc = self._store.get_snapshot().battery.soc_pct
            estimated_range_km = max(
                0.0,
                (battery_soc / 100.0) * self._config.estimated_full_range_km,
            )

            speed_rpm = state_1.speed_rpm if state_1 is not None else 0.0
            speed_kph = speed_rpm * self._config.can_speed_scale_kph_per_rpm

            self._store.update_drive(
                speed_kph=speed_kph,
                throttle_pct=0.0,
                regen_pct=0.0,
                range_km=estimated_range_km,
            )
            self._store.update_inverter(
                rpm=speed_rpm,
                dc_bus_voltage_v=state_2.dc_voltage_v if state_2 is not None else 0.0,
                phase_current_a=state_2.motor_current_a if state_2 is not None else 0.0,
                torque_nm=0.0,
            )

            self._publish_faults(speed_kph)

    def _publish_faults(self, speed_kph: float) -> None:
        status_1 = self._state.status_1
        status_2 = self._state.status_2

        messages: list[str] = []
        flags = FaultFlags()

        if status_1 is not None:
            messages.append(
                "CONTROLLER: "
                f"direction {status_1.direction}  "
                f"mode {'low' if status_1.low_speed_mode else 'high'}  "
                f"rpm {status_1.speed_rpm:.0f}  "
                f"speed {speed_kph:.1f} km/h"
            )
            if status_1.fault_code:
                messages.append(f"CONTROLLER FAULT: {status_1.fault_text}")

            if status_1.fault_code in {0x04, 0x0B}:
                flags = FaultFlags(
                    temperature=True,
                    battery=flags.battery,
                    inverter=flags.inverter,
                    motor=flags.motor,
                    communication=flags.communication,
                )
            if status_1.fault_code in {0x09, 0x0A} or status_1.low_power:
                flags = FaultFlags(
                    temperature=flags.temperature,
                    battery=True,
                    inverter=flags.inverter,
                    motor=flags.motor,
                    communication=flags.communication,
                )
            if status_1.fault_code in {0x03, 0x04, 0x0D}:
                flags = FaultFlags(
                    temperature=flags.temperature,
                    battery=flags.battery,
                    inverter=True,
                    motor=flags.motor,
                    communication=flags.communication,
                )
            if status_1.fault_code == 0x0B:
                flags = FaultFlags(
                    temperature=flags.temperature,
                    battery=flags.battery,
                    inverter=flags.inverter,
                    motor=True,
                    communication=flags.communication,
                )
            if status_1.low_power:
                messages.append("CONTROLLER: low-power flag asserted")

        if status_2 is not None:
            messages.append(
                "DC BUS: "
                f"{status_2.dc_voltage_v:.1f} V  "
                f"motor current {status_2.motor_current_a:.1f} A"
            )

        self._store.update_faults(
            source="can",
            flags=flags,
            messages=messages,
            timeout_s=max(self._config.stale_after_s, 3.0),
        )

