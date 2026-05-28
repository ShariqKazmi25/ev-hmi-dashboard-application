from __future__ import annotations

import time

from cluster_hmi.config import SerialEndpoint
from cluster_hmi.parsers.battery_rs485 import BatteryRs485Parser
from cluster_hmi.parsers.common import parse_json_or_kv
from cluster_hmi.services.base import ServiceThread
from cluster_hmi.store import ClusterStore

try:
    import serial
except ImportError:  # pragma: no cover - optional dependency for live hardware only.
    serial = None


def _coerce_float(value: object) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return float(value)
    raise TypeError(f"cannot convert {type(value).__name__} to float")


class BatterySerialService(ServiceThread):
    def __init__(self, endpoint: SerialEndpoint, store: ClusterStore) -> None:
        super().__init__(name="battery-serial")
        self._endpoint = endpoint
        self._store = store
        self._parser = BatteryRs485Parser()

    def run(self) -> None:
        if not self._endpoint.enabled or not self._endpoint.port or serial is None:
            return

        while not self.stopped():
            try:
                with serial.Serial(
                    self._endpoint.port,
                    self._endpoint.baudrate,
                    timeout=self._endpoint.timeout_s,
                ) as handle:
                    self._read_loop(handle)
            except Exception as exc:  # pragma: no cover - requires hardware.
                self._store.set_status(f"BATTERY PORT ERROR: {exc}")
                time.sleep(1.0)

    def _read_loop(self, handle) -> None:
        buffer = b""
        while not self.stopped():
            chunk = handle.read(handle.in_waiting or 1)
            if not chunk:
                continue

            buffer += chunk
            while b"\n" in buffer:
                frame, buffer = buffer.split(b"\n", 1)
                parsed = self._parser.parse(frame)
                if not parsed:
                    continue
                self._store.update_battery(
                    soc_pct=parsed.metrics.soc_pct,
                    pack_voltage_v=parsed.metrics.pack_voltage_v,
                    pack_current_a=parsed.metrics.pack_current_a,
                    pack_power_kw=parsed.metrics.pack_power_kw,
                    pack_temp_c=parsed.metrics.pack_temp_c,
                )
                self._store.update_faults(
                    flags=parsed.faults,
                    messages=parsed.messages,
                    source="battery",
                )


class GenericSerialSectionService(ServiceThread):
    def __init__(
        self,
        section_name: str,
        title: str,
        endpoint: SerialEndpoint,
        store: ClusterStore,
        key_map: dict[str, str],
    ) -> None:
        super().__init__(name=f"{section_name}-serial")
        self._section_name = section_name
        self._title = title
        self._endpoint = endpoint
        self._store = store
        self._key_map = key_map

    def run(self) -> None:
        if not self._endpoint.enabled or not self._endpoint.port or serial is None:
            return

        while not self.stopped():
            try:
                with serial.Serial(
                    self._endpoint.port,
                    self._endpoint.baudrate,
                    timeout=self._endpoint.timeout_s,
                ) as handle:
                    self._read_loop(handle)
            except Exception as exc:  # pragma: no cover - requires hardware.
                self._store.set_status(f"{self._title.upper()} PORT ERROR: {exc}")
                time.sleep(1.0)

    def _read_loop(self, handle) -> None:
        buffer = b""
        while not self.stopped():
            chunk = handle.read(handle.in_waiting or 1)
            if not chunk:
                continue

            buffer += chunk
            while b"\n" in buffer:
                frame, buffer = buffer.split(b"\n", 1)
                data = parse_json_or_kv(frame)
                if not data:
                    continue

                translated = {}
                for source_key, target_key in self._key_map.items():
                    if source_key in data:
                        translated[target_key] = _coerce_float(data[source_key])

                if not translated:
                    continue

                if self._section_name == "drive":
                    self._store.update_drive(**translated)
                elif self._section_name == "inverter":
                    self._store.update_inverter(**translated)
