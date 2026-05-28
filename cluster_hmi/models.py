from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DriveMetrics:
    speed_kph: float = 0.0
    throttle_pct: float = 0.0
    regen_pct: float = 0.0
    range_km: float = 0.0


@dataclass
class BatteryMetrics:
    soc_pct: float = 0.0
    pack_voltage_v: float = 0.0
    pack_current_a: float = 0.0
    pack_power_kw: float = 0.0
    pack_temp_c: float = 0.0


@dataclass
class BatteryPackMetrics:
    serial_number: int = 0
    online: bool = False
    freshness_text: str = ""
    soc_pct: float = 0.0
    pack_voltage_v: float = 0.0
    pack_current_a: float = 0.0
    pack_power_kw: float = 0.0
    pack_temp_c: float = 0.0
    min_cell_v: float = 0.0
    max_cell_v: float = 0.0
    current_state: str = "idle"
    charge_state: str = "unknown"
    discharge_state: str = "unknown"
    status_flags_text: str = ""
    note: str = ""


@dataclass
class InverterMetrics:
    rpm: float = 0.0
    inverter_temp_c: float = 0.0
    motor_temp_c: float = 0.0
    dc_bus_voltage_v: float = 0.0
    phase_current_a: float = 0.0
    torque_nm: float = 0.0


@dataclass
class OdometerMetrics:
    odometer_km: float = 0.0
    trip_a_km: float = 0.0
    trip_b_km: float = 0.0
    efficiency_wh_per_km: float = 0.0
    drive_time_h: float = 0.0
    low_voltage_v: float = 0.0


@dataclass
class FaultFlags:
    temperature: bool = False
    battery: bool = False
    inverter: bool = False
    motor: bool = False
    communication: bool = False


@dataclass
class ClusterSnapshot:
    drive: DriveMetrics = field(default_factory=DriveMetrics)
    battery: BatteryMetrics = field(default_factory=BatteryMetrics)
    battery_packs: list[BatteryPackMetrics] = field(default_factory=list)
    inverter: InverterMetrics = field(default_factory=InverterMetrics)
    odometer: OdometerMetrics = field(default_factory=OdometerMetrics)
    faults: FaultFlags = field(default_factory=FaultFlags)
    fault_messages: list[str] = field(default_factory=list)
    status_text: str = "NO LIVE DATA - DISPLAYING ZERO VALUES"
