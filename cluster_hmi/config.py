from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_csv_ints(name: str, default: tuple[int, ...] = ()) -> tuple[int, ...]:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default

    parsed: list[int] = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        parsed.append(int(item, 0))
    return tuple(parsed)


@dataclass(frozen=True)
class CanBusEndpoint:
    enabled: bool = False
    interface: str = "socketcan"
    channel: str = "can0"
    bitrate: int = 250000
    timeout_s: float = 0.2
    serial_baudrate: int = 115200
    scan: bool = False
    scan_bitrates: tuple[int, ...] = (125000, 250000, 500000, 1000000)
    scan_seconds: float = 3.0
    status_interval_s: float = 5.0
    listen_only: bool = True


@dataclass(frozen=True)
class SerialEndpoint:
    enabled: bool = False
    port: str = ""
    baudrate: int = 115200
    timeout_s: float = 0.1


@dataclass(frozen=True)
class AppConfig:
    fullscreen: bool = False
    width: int = 1280
    height: int = 720
    refresh_ms: int = 100
    stale_after_s: float = 2.5
    demo_mode: bool = False
    battery_protocol: str = "stream"
    battery_serial_numbers: tuple[int, ...] = ()
    battery_retries: int = 3
    battery_poll_interval_s: float = 1.0
    battery_poll_timeout_s: float = 2.0
    estimated_full_range_km: float = 280.0
    can_speed_scale_kph_per_rpm: float = 0.01257
    can_current_signed: bool = False
    can_bus: CanBusEndpoint = field(default_factory=CanBusEndpoint)
    battery_serial: SerialEndpoint = field(default_factory=SerialEndpoint)
    drive_serial: SerialEndpoint = field(default_factory=SerialEndpoint)
    inverter_serial: SerialEndpoint = field(default_factory=SerialEndpoint)

    def neuwat_serial_count(self) -> int:
        return max(len(self.battery_serial_numbers), 1)

    def neuwat_per_pack_budget_s(self) -> float:
        return max(self.battery_poll_timeout_s, 0.0) * max(self.battery_retries, 1)

    def neuwat_cycle_budget_s(self) -> float:
        return (
            self.neuwat_serial_count() * self.neuwat_per_pack_budget_s()
            + max(self.battery_poll_interval_s, 0.0)
        )

    def neuwat_section_stale_after_s(self) -> float:
        return max(self.stale_after_s, self.neuwat_per_pack_budget_s() + 1.0)

    def neuwat_recent_pack_window_s(self) -> float:
        return max(self.neuwat_section_stale_after_s(), self.neuwat_cycle_budget_s() + 1.0)

    @classmethod
    def from_env(cls) -> "AppConfig":
        battery_port = os.getenv("CLUSTER_BATTERY_PORT", "")
        drive_port = os.getenv("CLUSTER_DRIVE_PORT", "")
        inverter_port = os.getenv("CLUSTER_INVERTER_PORT", "")
        can_enabled = _env_flag("CLUSTER_CAN_ENABLED", default=False)
        battery_protocol = os.getenv("CLUSTER_BATTERY_PROTOCOL", "stream").strip().lower()

        return cls(
            fullscreen=_env_flag("CLUSTER_FULLSCREEN", default=False),
            width=int(os.getenv("CLUSTER_WIDTH", "1280")),
            height=int(os.getenv("CLUSTER_HEIGHT", "720")),
            refresh_ms=int(os.getenv("CLUSTER_REFRESH_MS", "100")),
            stale_after_s=float(os.getenv("CLUSTER_STALE_AFTER_S", "2.5")),
            demo_mode=_env_flag("CLUSTER_DEMO_MODE", default=False),
            battery_protocol=battery_protocol,
            battery_serial_numbers=_env_csv_ints(
                "CLUSTER_BATTERY_SERIALS",
                default=(17, 22, 6, 26) if battery_protocol == "neuwat" else (),
            ),
            battery_retries=int(os.getenv("CLUSTER_BATTERY_RETRIES", "3")),
            battery_poll_interval_s=float(os.getenv("CLUSTER_BATTERY_POLL_INTERVAL_S", "1.0")),
            battery_poll_timeout_s=float(os.getenv("CLUSTER_BATTERY_POLL_TIMEOUT_S", "2.0")),
            estimated_full_range_km=float(os.getenv("CLUSTER_ESTIMATED_FULL_RANGE_KM", "280.0")),
            can_speed_scale_kph_per_rpm=float(
                os.getenv("CLUSTER_CAN_SPEED_SCALE_KPH_PER_RPM", "0.01257")
            ),
            can_current_signed=_env_flag("CLUSTER_CAN_CURRENT_SIGNED", default=False),
            can_bus=CanBusEndpoint(
                enabled=can_enabled,
                interface=os.getenv("CLUSTER_CAN_INTERFACE", "socketcan").strip().lower(),
                channel=os.getenv("CLUSTER_CAN_CHANNEL", "can0").strip(),
                bitrate=int(os.getenv("CLUSTER_CAN_BITRATE", "250000")),
                timeout_s=float(os.getenv("CLUSTER_CAN_TIMEOUT_S", "0.2")),
                serial_baudrate=int(os.getenv("CLUSTER_CAN_SERIAL_BAUD", "115200")),
                scan=_env_flag("CLUSTER_CAN_SCAN", default=False),
                scan_bitrates=_env_csv_ints(
                    "CLUSTER_CAN_SCAN_BITRATES",
                    default=(125000, 250000, 500000, 1000000),
                ),
                scan_seconds=float(os.getenv("CLUSTER_CAN_SCAN_SECONDS", "3.0")),
                status_interval_s=float(os.getenv("CLUSTER_CAN_STATUS_INTERVAL_S", "5.0")),
                listen_only=_env_flag("CLUSTER_CAN_LISTEN_ONLY", default=True),
            ),
            battery_serial=SerialEndpoint(
                enabled=bool(battery_port),
                port=battery_port,
                baudrate=int(os.getenv("CLUSTER_BATTERY_BAUD", "4800" if battery_protocol == "neuwat" else "115200")),
                timeout_s=float(os.getenv("CLUSTER_BATTERY_TIMEOUT_S", "0.2" if battery_protocol == "neuwat" else "0.1")),
            ),
            drive_serial=SerialEndpoint(
                enabled=bool(drive_port),
                port=drive_port,
                baudrate=int(os.getenv("CLUSTER_DRIVE_BAUD", "115200")),
                timeout_s=float(os.getenv("CLUSTER_DRIVE_TIMEOUT_S", "0.1")),
            ),
            inverter_serial=SerialEndpoint(
                enabled=bool(inverter_port),
                port=inverter_port,
                baudrate=int(os.getenv("CLUSTER_INVERTER_BAUD", "115200")),
                timeout_s=float(os.getenv("CLUSTER_INVERTER_TIMEOUT_S", "0.1")),
            ),
        )
