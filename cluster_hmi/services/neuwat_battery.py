from __future__ import annotations

from dataclasses import dataclass
import time

from cluster_hmi.config import AppConfig, SerialEndpoint
from cluster_hmi.models import BatteryPackMetrics, FaultFlags
from cluster_hmi.neuwat_protocol import (
    BatteryTelemetry,
    SerialBackendError,
    format_status_flags,
    open_port,
    send_cmd_0500_and_read,
)
from cluster_hmi.services.base import ServiceThread
from cluster_hmi.store import ClusterStore


DEFAULT_NEUWAT_BATTERY_SERIALS = (17, 22, 6, 26)
PACK_CAPACITY_AH = 24.0
COULOMBIC_EFFICIENCY = 1.0
PACK_CELL_COUNT = 23
CELL_OVERVOLTAGE_PROTECT_V = 3.650
CELL_OVERVOLTAGE_RECOVERY_V = 3.300
CELL_UNDERVOLTAGE_PRIMARY_V = 2.900
CELL_UNDERVOLTAGE_PRIMARY_RECOVERY_V = 3.000
CELL_UNDERVOLTAGE_SECONDARY_V = 2.200
CELL_UNDERVOLTAGE_SECONDARY_RECOVERY_V = 3.000
CELL_PROHIBITED_CHARGE_V = 1.200

CHARGE_CURRENT_LIMIT_LEVEL_1_A = 25.0
CHARGE_CURRENT_LIMIT_LEVEL_2_A = 35.0
CURRENT_SHORT_CIRCUIT_A = 100.0
DISCHARGE_CURRENT_LIMIT_LEVEL_1_A = 50.0
DISCHARGE_CURRENT_LIMIT_LEVEL_2_A = 70.0

CHARGE_TEMP_HIGH_PROTECT_C = 62.0
CHARGE_TEMP_HIGH_RECOVERY_C = 58.0
CHARGE_TEMP_LOW_PROTECT_C = 0.0
CHARGE_TEMP_LOW_RECOVERY_C = 4.0
DISCHARGE_TEMP_HIGH_PROTECT_C = 74.0
DISCHARGE_TEMP_HIGH_RECOVERY_C = 70.0
DISCHARGE_TEMP_LOW_PROTECT_C = -20.0
DISCHARGE_TEMP_LOW_RECOVERY_C = -14.0

PACK_FULL_VOLTAGE = PACK_CELL_COUNT * CELL_OVERVOLTAGE_PROTECT_V
PACK_EMPTY_PRIMARY_VOLTAGE = PACK_CELL_COUNT * CELL_UNDERVOLTAGE_PRIMARY_V
IDLE_CURRENT_THRESHOLD_A = 0.05
IDLE_VOLTAGE_CORRECTION_DELAY_SECONDS = 30.0
IDLE_VOLTAGE_BLEND_EDGE = 0.18
IDLE_VOLTAGE_BLEND_MID = 0.04

VOLTAGE_SOC_POINTS = [
    (CELL_UNDERVOLTAGE_SECONDARY_V, 0.0),
    (CELL_UNDERVOLTAGE_PRIMARY_V, 2.0),
    (CELL_UNDERVOLTAGE_PRIMARY_RECOVERY_V, 6.0),
    (3.10, 14.0),
    (3.20, 28.0),
    (3.24, 42.0),
    (3.27, 55.0),
    (3.29, 65.0),
    (3.31, 75.0),
    (3.33, 84.0),
    (CELL_OVERVOLTAGE_RECOVERY_V, 92.0),
    (3.40, 97.0),
    (3.50, 99.0),
    (CELL_OVERVOLTAGE_PROTECT_V, 100.0),
]


@dataclass
class PackSocState:
    soc_percent: float
    last_sample_time: float
    idle_since: float | None
    last_voltage_soc_percent: float
    last_update_mode: str


@dataclass
class PackPollResult:
    serial_number: int
    telemetry: BatteryTelemetry | None
    soc_state: PackSocState | None
    assessment: "PackProtectionAssessment | None"
    sample_time: float
    error: str | None = None


@dataclass(frozen=True)
class PackProtectionAssessment:
    charge_state: str
    discharge_state: str
    current_state: str
    alerts: tuple[str, ...]


@dataclass
class PackCacheEntry:
    serial_number: int
    telemetry: BatteryTelemetry | None = None
    soc_state: PackSocState | None = None
    assessment: PackProtectionAssessment | None = None
    last_success_time: float | None = None
    last_attempt_time: float = 0.0
    last_attempt_ok: bool = False
    last_error: str | None = None


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def soc_from_pack_voltage(pack_voltage: float) -> float:
    per_cell_voltage = pack_voltage / PACK_CELL_COUNT
    points = VOLTAGE_SOC_POINTS

    if per_cell_voltage <= points[0][0]:
        return points[0][1]
    if per_cell_voltage >= points[-1][0]:
        return points[-1][1]

    for (left_voltage, left_soc), (right_voltage, right_soc) in zip(points, points[1:]):
        if left_voltage <= per_cell_voltage <= right_voltage:
            span = right_voltage - left_voltage
            if span <= 0:
                return right_soc
            ratio = (per_cell_voltage - left_voltage) / span
            return left_soc + ratio * (right_soc - left_soc)

    return points[-1][1]


def voltage_trim_blend(per_cell_voltage: float) -> float:
    """Trust voltage more near the OCV curve edges and less on the flat plateau."""

    if per_cell_voltage <= 3.05 or per_cell_voltage >= 3.37:
        return IDLE_VOLTAGE_BLEND_EDGE
    if per_cell_voltage <= 3.15 or per_cell_voltage >= 3.33:
        return 0.10
    return IDLE_VOLTAGE_BLEND_MID


def apply_soc_bounds_from_limits(telemetry: BatteryTelemetry, soc_percent: float) -> float:
    min_cell = min(telemetry.cell_volts)
    max_cell = max(telemetry.cell_volts)

    if min_cell <= CELL_UNDERVOLTAGE_SECONDARY_V:
        soc_percent = min(soc_percent, 0.5)
    elif min_cell <= CELL_UNDERVOLTAGE_PRIMARY_V:
        soc_percent = min(soc_percent, 5.0)
    elif min_cell <= CELL_UNDERVOLTAGE_PRIMARY_RECOVERY_V:
        soc_percent = min(soc_percent, 10.0)

    if max_cell >= CELL_OVERVOLTAGE_PROTECT_V:
        soc_percent = max(soc_percent, 99.5)

    return clamp(soc_percent, 0.0, 100.0)


def assess_pack_protection(telemetry: BatteryTelemetry) -> PackProtectionAssessment:
    min_cell = min(telemetry.cell_volts)
    max_cell = max(telemetry.cell_volts)
    min_temp = min(telemetry.temperatures_c)
    max_temp = max(telemetry.temperatures_c)
    current_amps = telemetry.current_amps
    charge_current_amps = max(-current_amps, 0.0)
    discharge_current_amps = max(current_amps, 0.0)
    alerts: list[str] = []

    charge_state = "ok"
    if (
        min_cell <= CELL_PROHIBITED_CHARGE_V
        or max_cell >= CELL_OVERVOLTAGE_PROTECT_V
        or min_temp <= CHARGE_TEMP_LOW_PROTECT_C
        or max_temp >= CHARGE_TEMP_HIGH_PROTECT_C
    ):
        charge_state = "blocked"
    elif (
        max_cell >= CELL_OVERVOLTAGE_RECOVERY_V
        or min_temp <= CHARGE_TEMP_LOW_RECOVERY_C
        or max_temp >= CHARGE_TEMP_HIGH_RECOVERY_C
    ):
        charge_state = "recovery-zone"

    discharge_state = "ok"
    if (
        min_cell <= CELL_UNDERVOLTAGE_SECONDARY_V
        or min_temp <= DISCHARGE_TEMP_LOW_PROTECT_C
        or max_temp >= DISCHARGE_TEMP_HIGH_PROTECT_C
    ):
        discharge_state = "blocked"
    elif (
        min_cell <= CELL_UNDERVOLTAGE_PRIMARY_V
        or min_temp <= DISCHARGE_TEMP_LOW_RECOVERY_C
        or max_temp >= DISCHARGE_TEMP_HIGH_RECOVERY_C
    ):
        discharge_state = "recovery-zone"

    current_state = "idle"
    if charge_current_amps > 0:
        current_state = "charging"
        if charge_current_amps >= CURRENT_SHORT_CIRCUIT_A:
            alerts.append("charging current exceeds short-circuit threshold")
        elif charge_current_amps >= CHARGE_CURRENT_LIMIT_LEVEL_2_A:
            alerts.append("charging current exceeds over-charge level 2")
        elif charge_current_amps >= CHARGE_CURRENT_LIMIT_LEVEL_1_A:
            alerts.append("charging current exceeds over-charge level 1")
    elif discharge_current_amps > 0:
        current_state = "discharging"
        if discharge_current_amps >= CURRENT_SHORT_CIRCUIT_A:
            alerts.append("discharge current exceeds short-circuit threshold")
        elif discharge_current_amps >= DISCHARGE_CURRENT_LIMIT_LEVEL_2_A:
            alerts.append("discharge current exceeds overload level 2")
        elif discharge_current_amps >= DISCHARGE_CURRENT_LIMIT_LEVEL_1_A:
            alerts.append("discharge current exceeds overload level 1")

    if max_cell >= CELL_OVERVOLTAGE_PROTECT_V:
        alerts.append("cell overvoltage protection threshold reached")
    elif max_cell >= CELL_OVERVOLTAGE_RECOVERY_V:
        alerts.append("cell voltage in charge recovery zone")

    if min_cell <= CELL_UNDERVOLTAGE_SECONDARY_V:
        alerts.append("cell below secondary overdischarge threshold")
    elif min_cell <= CELL_UNDERVOLTAGE_PRIMARY_V:
        alerts.append("cell below primary overdischarge threshold")
    elif min_cell <= CELL_UNDERVOLTAGE_PRIMARY_RECOVERY_V:
        alerts.append("cell voltage in discharge recovery zone")

    if min_temp <= CHARGE_TEMP_LOW_PROTECT_C:
        alerts.append("temperature below charge protection threshold")
    elif min_temp <= CHARGE_TEMP_LOW_RECOVERY_C:
        alerts.append("temperature in charge low-temp recovery zone")

    if max_temp >= CHARGE_TEMP_HIGH_PROTECT_C:
        alerts.append("temperature above charge protection threshold")
    elif max_temp >= CHARGE_TEMP_HIGH_RECOVERY_C:
        alerts.append("temperature in charge high-temp recovery zone")

    if min_temp <= DISCHARGE_TEMP_LOW_PROTECT_C:
        alerts.append("temperature below discharge protection threshold")
    elif min_temp <= DISCHARGE_TEMP_LOW_RECOVERY_C:
        alerts.append("temperature in discharge low-temp recovery zone")

    if max_temp >= DISCHARGE_TEMP_HIGH_PROTECT_C:
        alerts.append("temperature above discharge protection threshold")
    elif max_temp >= DISCHARGE_TEMP_HIGH_RECOVERY_C:
        alerts.append("temperature in discharge high-temp recovery zone")

    return PackProtectionAssessment(
        charge_state=charge_state,
        discharge_state=discharge_state,
        current_state=current_state,
        alerts=tuple(alerts),
    )


def update_soc_state(
    telemetry: BatteryTelemetry,
    pack_states: dict[int, PackSocState],
    *,
    sample_time: float,
) -> PackSocState:
    voltage_soc_percent = soc_from_pack_voltage(telemetry.pack_voltage)
    current_amps = telemetry.current_amps
    per_cell_voltage = telemetry.pack_voltage / PACK_CELL_COUNT
    is_idle = abs(current_amps) <= IDLE_CURRENT_THRESHOLD_A
    existing_state = pack_states.get(telemetry.serial_number)

    if existing_state is None:
        state = PackSocState(
            soc_percent=apply_soc_bounds_from_limits(telemetry, voltage_soc_percent),
            last_sample_time=sample_time,
            idle_since=sample_time if is_idle else None,
            last_voltage_soc_percent=voltage_soc_percent,
            last_update_mode="voltage-init",
        )
        pack_states[telemetry.serial_number] = state
        return state

    dt_seconds = max(sample_time - existing_state.last_sample_time, 0.0)
    dt_hours = dt_seconds / 3600.0
    soc_percent = existing_state.soc_percent

    if dt_hours > 0:
        delta_soc_percent = (
            COULOMBIC_EFFICIENCY * current_amps * dt_hours / PACK_CAPACITY_AH
        ) * 100.0
        soc_percent = clamp(soc_percent - delta_soc_percent, 0.0, 100.0)

    idle_since = existing_state.idle_since
    update_mode = "coulomb"
    if is_idle:
        if idle_since is None:
            idle_since = sample_time
        if sample_time - idle_since >= IDLE_VOLTAGE_CORRECTION_DELAY_SECONDS:
            blend = voltage_trim_blend(per_cell_voltage)
            soc_percent = clamp(
                (1.0 - blend) * soc_percent
                + blend * voltage_soc_percent,
                0.0,
                100.0,
            )
            update_mode = f"coulomb+voltage-trim({blend:.2f})"
    else:
        idle_since = None

    soc_percent = apply_soc_bounds_from_limits(telemetry, soc_percent)

    state = PackSocState(
        soc_percent=soc_percent,
        last_sample_time=sample_time,
        idle_since=idle_since,
        last_voltage_soc_percent=voltage_soc_percent,
        last_update_mode=update_mode,
    )
    pack_states[telemetry.serial_number] = state
    return state


class NeuwatBatteryPollingService(ServiceThread):
    def __init__(self, config: AppConfig, endpoint: SerialEndpoint, store: ClusterStore) -> None:
        super().__init__(name="battery-neuwat-poll")
        self._config = config
        self._endpoint = endpoint
        self._store = store
        self._pack_states: dict[int, PackSocState] = {}
        self._pack_cache: dict[int, PackCacheEntry] = {
            serial_number: PackCacheEntry(serial_number=serial_number)
            for serial_number in config.battery_serial_numbers
        }

    def run(self) -> None:
        if not self._endpoint.enabled or not self._endpoint.port:
            return

        while not self.stopped():
            try:
                with open_port(self._endpoint.port, timeout=self._endpoint.timeout_s) as handle:
                    self._poll_loop(handle)
            except (OSError, SerialBackendError) as exc:  # pragma: no cover - hardware dependent
                self._store.set_status(f"NEUWAT BATTERY PORT ERROR: {exc}")
                time.sleep(1.0)
            except Exception as exc:  # pragma: no cover - hardware dependent
                self._store.set_status(f"NEUWAT BATTERY ERROR: {exc}")
                time.sleep(1.0)

    def _poll_loop(self, handle) -> None:
        serial_numbers = self._config.battery_serial_numbers
        if not serial_numbers:
            self._store.set_status("NEUWAT BATTERIES: NO SERIALS CONFIGURED")
            time.sleep(max(self._config.battery_poll_interval_s, 0.5))
            return

        while not self.stopped():
            cycle_started = time.monotonic()

            for serial_number in serial_numbers:
                if self.stopped():
                    break

                result = self._poll_pack(
                    handle,
                    serial_number=serial_number,
                    timeout=self._config.battery_poll_timeout_s,
                    retries=max(self._config.battery_retries, 1),
                )
                self._remember_result(result)
                self._publish_state()

            elapsed = time.monotonic() - cycle_started
            sleep_time = max(self._config.battery_poll_interval_s - elapsed, 0.0)
            if sleep_time:
                time.sleep(sleep_time)

    def _poll_pack(self, handle, *, serial_number: int, timeout: float, retries: int) -> PackPollResult:
        last_error = "no reply"
        for _ in range(retries):
            try:
                telemetry = send_cmd_0500_and_read(
                    handle,
                    serial_number=serial_number,
                    timeout=timeout,
                    clear_input=True,
                )
            except TimeoutError as exc:
                last_error = str(exc)
                continue

            sample_time = time.monotonic()
            soc_state = update_soc_state(
                telemetry,
                self._pack_states,
                sample_time=sample_time,
            )
            assessment = assess_pack_protection(telemetry)
            return PackPollResult(
                serial_number=serial_number,
                telemetry=telemetry,
                soc_state=soc_state,
                assessment=assessment,
                sample_time=sample_time,
            )

        return PackPollResult(
            serial_number=serial_number,
            telemetry=None,
            soc_state=None,
            assessment=None,
            sample_time=time.monotonic(),
            error=last_error,
        )

    def _remember_result(self, result: PackPollResult) -> None:
        entry = self._pack_cache.get(result.serial_number)
        if entry is None:
            entry = PackCacheEntry(serial_number=result.serial_number)
            self._pack_cache[result.serial_number] = entry

        entry.last_attempt_time = result.sample_time
        entry.last_attempt_ok = (
            result.telemetry is not None
            and result.soc_state is not None
            and result.assessment is not None
        )
        entry.last_error = result.error

        if entry.last_attempt_ok:
            entry.telemetry = result.telemetry
            entry.soc_state = result.soc_state
            entry.assessment = result.assessment
            entry.last_success_time = result.sample_time

    def _active_entries(self) -> list[PackCacheEntry]:
        cutoff = time.monotonic() - self._config.neuwat_recent_pack_window_s()
        active_entries: list[PackCacheEntry] = []

        for serial_number in self._config.battery_serial_numbers:
            entry = self._pack_cache.get(serial_number)
            if entry is None:
                continue
            if entry.last_success_time is None or entry.last_success_time < cutoff:
                continue
            if entry.telemetry is None or entry.soc_state is None or entry.assessment is None:
                continue
            active_entries.append(entry)

        return active_entries

    def _publish_state(self) -> None:
        active_entries = self._active_entries()
        messages: list[str] = []
        pack_metrics: list[BatteryPackMetrics] = []
        total_packs = len(self._config.battery_serial_numbers)

        if active_entries:
            total_voltage = sum(entry.telemetry.pack_voltage for entry in active_entries if entry.telemetry is not None)
            avg_current = (
                sum(entry.telemetry.current_amps for entry in active_entries if entry.telemetry is not None)
                / len(active_entries)
            )
            total_power = total_voltage * avg_current / 1000.0
            max_temp = max(
                max(entry.telemetry.temperatures_c)
                for entry in active_entries
                if entry.telemetry is not None
            )
            min_soc = min(
                entry.soc_state.soc_percent
                for entry in active_entries
                if entry.soc_state is not None
            )
            avg_soc = (
                sum(
                    entry.soc_state.soc_percent
                    for entry in active_entries
                    if entry.soc_state is not None
                )
                / len(active_entries)
            )

            self._store.update_battery(
                soc_pct=min_soc,
                pack_voltage_v=total_voltage,
                pack_current_a=avg_current,
                pack_power_kw=total_power,
                pack_temp_c=max_temp,
            )
            messages.append(
                f"STACK: packs {len(active_entries)}/{total_packs}  "
                f"SoC min {min_soc:.1f}% avg {avg_soc:.1f}%  "
                f"V {total_voltage:.2f}  "
                f"I {avg_current:.2f} A  "
                f"P {total_power:.2f} kW  "
                f"Tmax {max_temp:.1f} C"
            )
        else:
            self._store.update_battery(
                soc_pct=0.0,
                pack_voltage_v=0.0,
                pack_current_a=0.0,
                pack_power_kw=0.0,
                pack_temp_c=0.0,
            )

        raw_status_present = False
        temp_warning = False
        protection_alert_present = False
        active_by_serial = {entry.serial_number: entry for entry in active_entries}
        now = time.monotonic()

        for serial_number in self._config.battery_serial_numbers:
            entry = active_by_serial.get(serial_number)
            if entry is None:
                cached_entry = self._pack_cache.get(serial_number)
                note = "waiting for first reply"
                if cached_entry is not None and cached_entry.last_error:
                    note = cached_entry.last_error
                    messages.append(
                        f"PACK {serial_number}: no reply ({cached_entry.last_error})"
                    )
                else:
                    messages.append(f"PACK {serial_number}: waiting for first reply")
                pack_metrics.append(
                    BatteryPackMetrics(
                        serial_number=serial_number,
                        online=False,
                        freshness_text="offline",
                        note=note,
                    )
                )
                continue

            telemetry = entry.telemetry
            soc_state = entry.soc_state
            assessment = entry.assessment
            if telemetry is None or soc_state is None or assessment is None:
                continue

            max_temp = max(telemetry.temperatures_c)
            temp_warning = temp_warning or any("temperature" in alert for alert in assessment.alerts)
            status_text = format_status_flags(telemetry.status_flags)
            pack_has_raw_status = any(flag != 0 for flag in telemetry.status_flags)
            raw_status_present = raw_status_present or pack_has_raw_status
            protection_alert_present = protection_alert_present or bool(assessment.alerts)
            age_seconds = now - entry.last_success_time if entry.last_success_time is not None else 0.0
            freshness = "live" if entry.last_attempt_ok else f"cached {age_seconds:.1f}s"
            pack_metrics.append(
                BatteryPackMetrics(
                    serial_number=telemetry.serial_number,
                    online=True,
                    freshness_text=freshness,
                    soc_pct=soc_state.soc_percent,
                    pack_voltage_v=telemetry.pack_voltage,
                    pack_current_a=telemetry.current_amps,
                    pack_power_kw=telemetry.pack_voltage * telemetry.current_amps / 1000.0,
                    pack_temp_c=max_temp,
                    min_cell_v=min(telemetry.cell_volts),
                    max_cell_v=max(telemetry.cell_volts),
                    current_state=assessment.current_state,
                    charge_state=assessment.charge_state,
                    discharge_state=assessment.discharge_state,
                    status_flags_text=status_text if pack_has_raw_status else "CLEAR",
                    note=freshness if not entry.last_attempt_ok else ("; ".join(assessment.alerts[:2]) if assessment.alerts else ""),
                )
            )
            messages.append(
                f"PACK {telemetry.serial_number}: "
                f"SoC {soc_state.soc_percent:.1f}%  "
                f"V {telemetry.pack_voltage:.2f}  "
                f"I {telemetry.current_amps:.2f} A  "
                f"Tmax {max_temp:.1f} C  "
                f"{freshness}  "
                f"chg {assessment.charge_state}  "
                f"dchg {assessment.discharge_state}  "
                f"dir {assessment.current_state}  "
                f"status {status_text}"
            )
            if assessment.alerts:
                messages.append("  alerts: " + "; ".join(assessment.alerts))

        flags = FaultFlags(
            temperature=temp_warning,
            battery=raw_status_present or protection_alert_present,
            communication=len(active_entries) < total_packs,
        )
        self._store.update_battery_packs(pack_metrics)
        self._store.update_faults(
            flags=flags,
            messages=messages,
            source="battery",
            timeout_s=self._config.neuwat_section_stale_after_s(),
        )
        self._store.set_status(
            f"NEUWAT BATTERIES ONLINE: {len(active_entries)}/{total_packs}"
            if total_packs
            else "NEUWAT BATTERIES: NO SERIALS CONFIGURED"
        )
