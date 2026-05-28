from __future__ import annotations

import math
import time

from cluster_hmi.models import FaultFlags
from cluster_hmi.services.base import ServiceThread
from cluster_hmi.store import ClusterStore


class DemoSimulationService(ServiceThread):
    def __init__(self, store: ClusterStore) -> None:
        super().__init__(name="demo-simulation")
        self._store = store

    def run(self) -> None:
        start = time.monotonic()
        while not self.stopped():
            t = time.monotonic() - start
            speed = max(0.0, 72.0 + 28.0 * math.sin(t * 0.55))
            throttle = max(0.0, 45.0 + 40.0 * math.sin(t * 0.90))
            regen = max(0.0, 12.0 + 12.0 * math.sin(t * 1.20 + 1.1))
            soc = max(0.0, min(100.0, 72.0 - 0.02 * t))
            pack_current = 32.0 + 48.0 * math.sin(t * 0.68)
            pack_voltage = 356.0 + 6.0 * math.sin(t * 0.22)
            pack_power_kw = (pack_voltage * pack_current) / 1000.0
            battery_temp = 31.0 + 9.0 * math.sin(t * 0.16)
            inverter_temp = 38.0 + 12.0 * math.sin(t * 0.20 + 0.4)
            motor_temp = 42.0 + 15.0 * math.sin(t * 0.18 + 1.1)
            rpm = max(0.0, speed * 85.0)
            phase_current = abs(pack_current) * 1.6
            torque = 140.0 + 60.0 * math.sin(t * 0.50)
            trip = t / 45.0

            self._store.update_drive(
                speed_kph=speed,
                throttle_pct=throttle,
                regen_pct=regen,
                range_km=max(0.0, soc * 2.8),
            )
            self._store.update_battery(
                soc_pct=soc,
                pack_voltage_v=pack_voltage,
                pack_current_a=pack_current,
                pack_power_kw=pack_power_kw,
                pack_temp_c=battery_temp,
            )
            self._store.update_inverter(
                rpm=rpm,
                inverter_temp_c=inverter_temp,
                motor_temp_c=motor_temp,
                dc_bus_voltage_v=pack_voltage,
                phase_current_a=phase_current,
                torque_nm=torque,
            )
            self._store.update_odometer(
                odometer_km=18234.5 + trip,
                trip_a_km=124.6 + trip,
                trip_b_km=436.1 + trip * 0.5,
                efficiency_wh_per_km=132.0 + 18.0 * math.sin(t * 0.30),
                drive_time_h=trip / 2.0,
                low_voltage_v=13.7 + 0.2 * math.sin(t * 0.8),
            )

            faults = FaultFlags(
                temperature=battery_temp >= 39.0 or motor_temp >= 55.0,
                battery=soc <= 18.0,
                inverter=inverter_temp >= 48.0,
                motor=motor_temp >= 55.0,
                communication=False,
            )
            messages = []
            if faults.temperature:
                messages.append("TEMP: Elevated system temperature detected.")
            if faults.inverter:
                messages.append("INV: Inverter temperature is approaching its limit.")
            if faults.motor:
                messages.append("MTR: Motor temperature is above the warning threshold.")
            if faults.battery:
                messages.append("BATT: State of charge is low.")
            self._store.update_faults(flags=faults, messages=messages)

            time.sleep(0.1)
