from __future__ import annotations

from cluster_hmi.config import AppConfig
from cluster_hmi.services.dummy import DemoSimulationService
from cluster_hmi.services.neuwat_battery import NeuwatBatteryPollingService
from cluster_hmi.services.serial_reader import BatterySerialService, GenericSerialSectionService
from cluster_hmi.services.slider_can import SliderCanService
from cluster_hmi.store import ClusterStore


def build_services(config: AppConfig, store: ClusterStore) -> list:
    if config.battery_protocol == "neuwat":
        battery_service = NeuwatBatteryPollingService(
            config=config,
            endpoint=config.battery_serial,
            store=store,
        )
    else:
        battery_service = BatterySerialService(endpoint=config.battery_serial, store=store)

    services = [battery_service]

    if config.can_bus.enabled:
        services.append(
            SliderCanService(
                config=config,
                endpoint=config.can_bus,
                store=store,
            )
        )
    else:
        services.extend(
            [
                GenericSerialSectionService(
                    section_name="drive",
                    title="drive",
                    endpoint=config.drive_serial,
                    store=store,
                    key_map={
                        "speed": "speed_kph",
                        "speed_kph": "speed_kph",
                        "throttle": "throttle_pct",
                        "throttle_pct": "throttle_pct",
                        "regen": "regen_pct",
                        "regen_pct": "regen_pct",
                        "range": "range_km",
                        "range_km": "range_km",
                    },
                ),
                GenericSerialSectionService(
                    section_name="inverter",
                    title="inverter",
                    endpoint=config.inverter_serial,
                    store=store,
                    key_map={
                        "rpm": "rpm",
                        "inverter_temp": "inverter_temp_c",
                        "inverter_temp_c": "inverter_temp_c",
                        "motor_temp": "motor_temp_c",
                        "motor_temp_c": "motor_temp_c",
                        "dc_bus_voltage": "dc_bus_voltage_v",
                        "dc_bus_voltage_v": "dc_bus_voltage_v",
                        "phase_current": "phase_current_a",
                        "phase_current_a": "phase_current_a",
                        "torque": "torque_nm",
                        "torque_nm": "torque_nm",
                    },
                ),
            ]
        )

    if config.demo_mode:
        services.append(DemoSimulationService(store=store))

    return services
