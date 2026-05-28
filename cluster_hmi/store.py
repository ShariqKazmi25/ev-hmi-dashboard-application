from __future__ import annotations

import copy
import time
from dataclasses import replace
from threading import RLock

from cluster_hmi.models import (
    BatteryPackMetrics,
    BatteryMetrics,
    ClusterSnapshot,
    DriveMetrics,
    FaultFlags,
    InverterMetrics,
    OdometerMetrics,
)

_FAULT_FLAG_FIELDS = tuple(FaultFlags.__dataclass_fields__.keys())


class ClusterStore:
    def __init__(
        self,
        stale_after_s: float = 2.5,
        section_stale_after_s: dict[str, float] | None = None,
    ) -> None:
        self._lock = RLock()
        self._stale_after_s = stale_after_s
        self._section_stale_after_s = dict(section_stale_after_s or {})
        self._snapshot = ClusterSnapshot()
        self._status_override = ""
        self._fault_sources: dict[str, dict[str, object]] = {}
        self._last_seen: dict[str, float] = {
            "drive": 0.0,
            "battery": 0.0,
            "inverter": 0.0,
            "odometer": 0.0,
            "faults": 0.0,
        }

    def update_drive(self, **values: float) -> None:
        self._update_section("drive", DriveMetrics, values)

    def update_battery(self, **values: float) -> None:
        self._update_section("battery", BatteryMetrics, values)

    def update_battery_packs(self, packs: list[BatteryPackMetrics]) -> None:
        with self._lock:
            self._snapshot = replace(self._snapshot, battery_packs=copy.deepcopy(packs))
            self._last_seen["battery"] = time.monotonic()
            self._status_override = ""

    def update_inverter(self, **values: float) -> None:
        self._update_section("inverter", InverterMetrics, values)

    def update_odometer(self, **values: float) -> None:
        self._update_section("odometer", OdometerMetrics, values)

    def update_faults(
        self,
        flags: FaultFlags | None = None,
        messages: list[str] | None = None,
        *,
        source: str = "general",
        timeout_s: float | None = None,
    ) -> None:
        with self._lock:
            current = self._fault_sources.get(
                source,
                {
                    "flags": FaultFlags(),
                    "messages": [],
                    "last_seen": 0.0,
                    "timeout_s": timeout_s,
                },
            )
            current["flags"] = flags if flags is not None else current["flags"]
            current["messages"] = list(messages) if messages is not None else list(current["messages"])
            current["last_seen"] = time.monotonic()
            current["timeout_s"] = timeout_s
            self._fault_sources[source] = current
            self._last_seen["faults"] = time.monotonic()
            self._status_override = ""

    def set_status(self, text: str) -> None:
        with self._lock:
            self._status_override = text

    def get_snapshot(self) -> ClusterSnapshot:
        with self._lock:
            snapshot = copy.deepcopy(self._snapshot)
            last_seen = dict(self._last_seen)
            status_override = self._status_override
            fault_sources = copy.deepcopy(self._fault_sources)

        now = time.monotonic()
        stale_sections = []

        if self._is_stale("drive", last_seen["drive"], now):
            snapshot.drive = DriveMetrics()
            stale_sections.append("drive")
        if self._is_stale("battery", last_seen["battery"], now):
            snapshot.battery = BatteryMetrics()
            snapshot.battery_packs = [self._offline_pack_snapshot(pack) for pack in snapshot.battery_packs]
            stale_sections.append("battery")
        if self._is_stale("inverter", last_seen["inverter"], now):
            snapshot.inverter = InverterMetrics()
            stale_sections.append("inverter")
        if self._is_stale("odometer", last_seen["odometer"], now):
            snapshot.odometer = OdometerMetrics()
            stale_sections.append("odometer")

        active_fault_sources = self._active_fault_sources(fault_sources, now)
        if active_fault_sources:
            snapshot.faults = self._merge_fault_flags(source["flags"] for source in active_fault_sources)
            snapshot.fault_messages = [
                message
                for source in active_fault_sources
                for message in source["messages"]
            ]
        else:
            snapshot.faults = FaultFlags()
            snapshot.fault_messages = []

        if status_override:
            snapshot.status_text = status_override
        elif len(stale_sections) == 4:
            snapshot.status_text = "NO LIVE DATA - DISPLAYING ZERO VALUES"
        elif stale_sections:
            snapshot.status_text = "PARTIAL LIVE DATA - STALE: " + ", ".join(section.upper() for section in stale_sections)
        else:
            snapshot.status_text = "LIVE DATA ACTIVE"

        return snapshot

    def _update_section(self, name: str, model_type: type, values: dict[str, float]) -> None:
        with self._lock:
            current = getattr(self._snapshot, name)
            filtered_values = {key: value for key, value in values.items() if hasattr(current, key)}
            updated = replace(current, **filtered_values)
            self._snapshot = replace(self._snapshot, **{name: updated})
            self._last_seen[name] = time.monotonic()
            self._status_override = ""

    def _is_stale(self, section: str, last_seen: float, now: float) -> bool:
        if not last_seen:
            return True
        timeout_s = self._section_stale_after_s.get(section, self._stale_after_s)
        return now - last_seen > timeout_s

    def _offline_pack_snapshot(self, pack: BatteryPackMetrics) -> BatteryPackMetrics:
        return replace(
            pack,
            online=False,
            freshness_text="offline",
            soc_pct=0.0,
            pack_voltage_v=0.0,
            pack_current_a=0.0,
            pack_power_kw=0.0,
            pack_temp_c=0.0,
            min_cell_v=0.0,
            max_cell_v=0.0,
            current_state="idle",
            charge_state="unknown",
            discharge_state="unknown",
            status_flags_text="",
            note="stale",
        )

    def _active_fault_sources(self, fault_sources: dict[str, dict[str, object]], now: float) -> list[dict[str, object]]:
        active_sources: list[dict[str, object]] = []
        default_timeout = self._section_stale_after_s.get("faults", self._stale_after_s)

        for source in fault_sources.values():
            last_seen = float(source.get("last_seen", 0.0))
            if not last_seen:
                continue
            timeout_s = source.get("timeout_s")
            timeout = float(timeout_s) if timeout_s is not None else default_timeout
            if now - last_seen <= timeout:
                active_sources.append(source)

        return active_sources

    def _merge_fault_flags(self, flags_iterable) -> FaultFlags:
        merged = {field_name: False for field_name in _FAULT_FLAG_FIELDS}
        for flags in flags_iterable:
            for field_name in _FAULT_FLAG_FIELDS:
                merged[field_name] = merged[field_name] or bool(getattr(flags, field_name))
        return FaultFlags(**merged)
