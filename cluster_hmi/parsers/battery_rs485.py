from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from cluster_hmi.models import BatteryMetrics, FaultFlags
from cluster_hmi.parsers.common import parse_json_or_kv


@dataclass
class ParsedBatteryPacket:
    metrics: BatteryMetrics
    faults: FaultFlags = field(default_factory=FaultFlags)
    messages: list[str] = field(default_factory=list)


def _coerce_float(value: object) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return float(value)
    raise TypeError(f"cannot convert {type(value).__name__} to float")


class BatteryRs485Parser:
    """
    Temporary battery parser.

    The exact RS485 packet map from the earlier chat is not available in this thread, so this trial
    version accepts JSON or key/value frames now and exposes a `decode_register_snapshot` hook for
    the real register map once that protocol is pasted in.
    """

    KEY_MAP = {
        "soc": "soc_pct",
        "soc_pct": "soc_pct",
        "pack_voltage": "pack_voltage_v",
        "pack_voltage_v": "pack_voltage_v",
        "voltage": "pack_voltage_v",
        "pack_current": "pack_current_a",
        "pack_current_a": "pack_current_a",
        "current": "pack_current_a",
        "pack_power": "pack_power_kw",
        "pack_power_kw": "pack_power_kw",
        "power": "pack_power_kw",
        "pack_temp": "pack_temp_c",
        "pack_temp_c": "pack_temp_c",
        "temperature": "pack_temp_c",
        "temp": "pack_temp_c",
    }

    def parse(self, payload: bytes) -> ParsedBatteryPacket | None:
        data = parse_json_or_kv(payload)
        if not data:
            return None

        metrics = BatteryMetrics()
        for source_key, target_key in self.KEY_MAP.items():
            if source_key in data:
                setattr(metrics, target_key, _coerce_float(data[source_key]))

        faults = FaultFlags(
            temperature=bool(data.get("temp_fault", False)) or metrics.pack_temp_c >= 55.0,
            battery=bool(data.get("battery_fault", False)),
            communication=bool(data.get("comm_fault", False)),
        )

        messages: list[str] = []
        if faults.temperature:
            messages.append("TEMP: Battery temperature is above the warning threshold.")
        if faults.battery:
            messages.append("BATT: Battery management system reported a battery fault.")
        if faults.communication:
            messages.append("COMM: Battery communication fault reported by the data source.")

        return ParsedBatteryPacket(metrics=metrics, faults=faults, messages=messages)

    def decode_register_snapshot(self, registers: Mapping[int, int]) -> ParsedBatteryPacket:
        """
        Placeholder for the real RS485 register mapping.

        Update these register addresses when the exact BMS protocol from the other chat is provided.
        """
        metrics = BatteryMetrics(
            soc_pct=registers.get(0x0100, 0) / 10.0,
            pack_voltage_v=registers.get(0x0101, 0) / 10.0,
            pack_current_a=registers.get(0x0102, 0) / 10.0,
            pack_power_kw=registers.get(0x0103, 0) / 100.0,
            pack_temp_c=registers.get(0x0104, 0) / 10.0,
        )
        faults = FaultFlags(
            temperature=metrics.pack_temp_c >= 55.0,
            battery=bool(registers.get(0x01F0, 0)),
            communication=bool(registers.get(0x01F1, 0)),
        )
        messages = []
        if faults.temperature:
            messages.append("TEMP: Battery temperature is above the warning threshold.")
        if faults.battery:
            messages.append("BATT: Battery management system reported a battery fault.")
        if faults.communication:
            messages.append("COMM: Battery communication fault reported by the data source.")
        return ParsedBatteryPacket(metrics=metrics, faults=faults, messages=messages)
