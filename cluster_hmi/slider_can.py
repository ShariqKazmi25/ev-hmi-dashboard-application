from __future__ import annotations

from dataclasses import dataclass


COMMON_CAN_BITRATES = (125000, 250000, 500000, 1000000)
SLIDER_MSG_STATUS_1_ID = 0x10F8109A
SLIDER_MSG_STATUS_2_ID = 0x10F8108D

SLIDER_FAULTS = {
    0x00: "No fault",
    0x03: "Over current",
    0x04: "Controller temperature too high",
    0x09: "Battery pack under-voltage",
    0x0A: "Battery pack over-voltage",
    0x0B: "Motor temperature too high",
    0x0D: "Accelerator fault",
}

SLIDER_DIRECTION = {
    0b00: "invalid",
    0b01: "forward",
    0b10: "reverse",
    0b11: "reserved",
}


@dataclass(frozen=True)
class SliderStatus1:
    direction: str
    low_speed_mode: bool
    speed_rpm: float
    fault_code: int
    fault_text: str
    low_power: bool


@dataclass(frozen=True)
class SliderStatus2:
    dc_voltage_v: float
    motor_current_a: float


@dataclass(frozen=True)
class SliderControllerState:
    status_1: SliderStatus1 | None = None
    status_2: SliderStatus2 | None = None


def decode_u16_le(data: bytes, start_index: int, *, signed: bool = False) -> int | None:
    end_index = start_index + 2
    if len(data) < end_index:
        return None
    return int.from_bytes(data[start_index:end_index], byteorder="little", signed=signed)


def is_slider_frame(arbitration_id: int, is_extended_id: bool) -> bool:
    return is_extended_id and arbitration_id in {SLIDER_MSG_STATUS_1_ID, SLIDER_MSG_STATUS_2_ID}


def decode_status_1(arbitration_id: int, data: bytes, *, is_extended_id: bool) -> SliderStatus1 | None:
    if not is_slider_frame(arbitration_id, is_extended_id) or arbitration_id != SLIDER_MSG_STATUS_1_ID:
        return None

    mode = data[0] if len(data) >= 1 else 0
    speed_rpm_raw = decode_u16_le(data, 1)
    fault_code = data[3] if len(data) >= 4 else 0

    return SliderStatus1(
        direction=SLIDER_DIRECTION.get(mode & 0b11, "unknown"),
        low_speed_mode=bool(mode & 0b1000),
        speed_rpm=float(speed_rpm_raw or 0),
        fault_code=fault_code,
        fault_text=SLIDER_FAULTS.get(fault_code, f"Unknown fault 0x{fault_code:02X}"),
        low_power=len(data) >= 5 and data[4] == 0xAA,
    )


def decode_status_2(
    arbitration_id: int,
    data: bytes,
    *,
    is_extended_id: bool,
    current_signed: bool = False,
) -> SliderStatus2 | None:
    if not is_slider_frame(arbitration_id, is_extended_id) or arbitration_id != SLIDER_MSG_STATUS_2_ID:
        return None

    dc_voltage_raw = decode_u16_le(data, 0)
    motor_current_raw = decode_u16_le(data, 2, signed=current_signed)

    return SliderStatus2(
        dc_voltage_v=(float(dc_voltage_raw) / 10.0) if dc_voltage_raw is not None else 0.0,
        motor_current_a=(float(motor_current_raw) / 10.0) if motor_current_raw is not None else 0.0,
    )


def update_controller_state(
    state: SliderControllerState,
    arbitration_id: int,
    data: bytes,
    *,
    is_extended_id: bool,
    current_signed: bool = False,
) -> SliderControllerState:
    status_1 = decode_status_1(arbitration_id, data, is_extended_id=is_extended_id)
    if status_1 is not None:
        return SliderControllerState(status_1=status_1, status_2=state.status_2)

    status_2 = decode_status_2(
        arbitration_id,
        data,
        is_extended_id=is_extended_id,
        current_signed=current_signed,
    )
    if status_2 is not None:
        return SliderControllerState(status_1=state.status_1, status_2=status_2)

    return state

