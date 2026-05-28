"""Helpers for Neuwat RS-485 battery packets."""

from __future__ import annotations

from dataclasses import dataclass
import os
import select
import sys
import time
from typing import Iterable, Protocol

try:
    import serial  # type: ignore[import-not-found]
except ImportError:
    serial = None


BAUDRATE = 4800
BYTESIZE = serial.EIGHTBITS if serial is not None else 8
PARITY = serial.PARITY_EVEN if serial is not None else "E"
STOPBITS = serial.STOPBITS_ONE if serial is not None else 1

START_OF_FRAME = 0xFF
REQUEST_MARKER = 0x00
RESPONSE_MARKER = 0x55
TYPE_BYTE = 0x01

CMD_BATTERY_MICRO = 0x0500
REQUEST_LENGTH = 15
RESPONSE_LENGTH = 81
PAYLOAD_LENGTH = 66
CELL_COUNT = 23
TEMP_COUNT = 4

CRC_INIT = 0xFFFF
CRC_POLY = 0x1021


class ProtocolError(RuntimeError):
    """Raised when a decoded packet does not match the expected shape."""


class SerialBackendError(RuntimeError):
    """Raised when no usable serial backend is available."""


class SerialPortLike(Protocol):
    @property
    def in_waiting(self) -> int: ...

    def read(self, size: int = 1, /) -> bytes: ...

    def write(self, data: bytes | bytearray | memoryview, /) -> int | None: ...

    def flush(self) -> None: ...

    def reset_input_buffer(self) -> None: ...


@dataclass(frozen=True)
class BatteryTelemetry:
    """Decoded telemetry from CMD 0x0500.

    Datasheet scaling from the updated poller:
    - cell values are centivolts
    - current is milliamps
    - temperature is centi-degrees Celsius
    """

    serial_number: int
    cell_centivolts: tuple[int, ...]
    current_milliamps: int
    temperature_centi_c: tuple[int, ...]
    status_flags: bytes
    frame: bytes

    @property
    def cell_volts(self) -> tuple[float, ...]:
        return tuple(value / 100.0 for value in self.cell_centivolts)

    @property
    def pack_voltage(self) -> float:
        return sum(self.cell_centivolts) / 100.0

    @property
    def current_amps(self) -> float:
        return self.current_milliamps / 1000.0

    @property
    def temperatures_c(self) -> tuple[float, ...]:
        return tuple(value / 100.0 for value in self.temperature_centi_c)

    @property
    def serial_decimal_10(self) -> str:
        return f"{self.serial_number:010d}"

    @property
    def serial_hex_8(self) -> str:
        return f"0x{self.serial_number:08X}"


def crc16_ccitt(data: bytes, *, initial: int = CRC_INIT, polynomial: int = CRC_POLY) -> int:
    crc = initial
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ polynomial) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc & 0xFFFF


def build_cmd_0500_request(serial_number: int) -> bytes:
    if not 0 <= serial_number <= 0xFFFFFFFF:
        raise ValueError("serial_number must fit in 4 bytes")

    frame_wo_crc = bytes(
        [
            START_OF_FRAME,
            REQUEST_MARKER,
            0x00,
            REQUEST_LENGTH,
            TYPE_BYTE,
        ]
    ) + serial_number.to_bytes(4, "big") + bytes(
        [
            0x05,
            0x00,
            0x00,
            0x00,
        ]
    )
    crc = crc16_ccitt(frame_wo_crc)
    frame = frame_wo_crc + crc.to_bytes(2, "big")
    if crc16_ccitt(frame) != 0:
        raise AssertionError("built request does not satisfy CRC residue check")
    return frame


def decode_cmd_0500_response(frame: bytes) -> BatteryTelemetry:
    if len(frame) != RESPONSE_LENGTH:
        raise ProtocolError(f"expected {RESPONSE_LENGTH} bytes, got {len(frame)}")
    if crc16_ccitt(frame) != 0:
        raise ProtocolError("CRC check failed")
    if frame[0] != START_OF_FRAME:
        raise ProtocolError("bad start-of-frame marker")
    if frame[1] != RESPONSE_MARKER:
        raise ProtocolError(f"expected response marker 0x55, got 0x{frame[1]:02X}")
    if frame[2] != 0x00 or frame[3] != RESPONSE_LENGTH or frame[4] != TYPE_BYTE:
        raise ProtocolError("unexpected fixed header bytes")
    if frame[9] != 0x05 or frame[10] != 0x00:
        raise ProtocolError("unexpected command in response")
    if frame[11] != 0x00 or frame[12] != PAYLOAD_LENGTH:
        raise ProtocolError("unexpected payload length in response")

    serial_number = int.from_bytes(frame[5:9], "big", signed=False)
    cells = tuple(
        int.from_bytes(frame[13 + index * 2 : 15 + index * 2], "big", signed=True)
        for index in range(CELL_COUNT)
    )
    current = int.from_bytes(frame[59:63], "big", signed=True)
    temperatures = tuple(
        int.from_bytes(frame[63 + index * 2 : 65 + index * 2], "big", signed=True)
        for index in range(TEMP_COUNT)
    )
    status_flags = bytes(frame[71:79])

    return BatteryTelemetry(
        serial_number=serial_number,
        cell_centivolts=cells,
        current_milliamps=current,
        temperature_centi_c=temperatures,
        status_flags=status_flags,
        frame=frame,
    )


class FrameScanner:
    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, chunk: bytes) -> list[bytes]:
        self._buffer.extend(chunk)
        frames: list[bytes] = []

        while True:
            if not self._buffer:
                break

            start_index = self._buffer.find(bytes([START_OF_FRAME]))
            if start_index < 0:
                self._buffer.clear()
                break
            if start_index > 0:
                del self._buffer[:start_index]

            if len(self._buffer) < 4:
                break

            length = self._buffer[3]
            if length < REQUEST_LENGTH or length > 255:
                del self._buffer[0]
                continue

            if len(self._buffer) < length:
                break

            candidate = bytes(self._buffer[:length])
            if crc16_ccitt(candidate) == 0:
                frames.append(candidate)
                del self._buffer[:length]
                continue

            del self._buffer[0]

        return frames


class PosixSerialPort:
    """Small stdlib-only serial wrapper for Raspberry Pi/Linux."""

    def __init__(self, port: str, *, timeout: float) -> None:
        import fcntl
        import termios

        self._fcntl = fcntl
        self._termios = termios
        self._timeout = timeout
        self._fd: int | None = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        self._configure()

    def _require_fd(self) -> int:
        fd = self._fd
        if fd is None:
            raise RuntimeError("serial port is closed")
        return fd

    def _configure(self) -> None:
        fd = self._require_fd()
        termios = self._termios
        attrs = termios.tcgetattr(fd)

        attrs[0] = 0
        attrs[1] = 0
        attrs[2] &= ~termios.CSIZE
        attrs[2] |= termios.CS8 | termios.CREAD | termios.CLOCAL | termios.PARENB
        attrs[2] &= ~termios.PARODD
        attrs[2] &= ~termios.CSTOPB
        if hasattr(termios, "CRTSCTS"):
            attrs[2] &= ~termios.CRTSCTS
        attrs[3] = 0
        attrs[4] = termios.B4800
        attrs[5] = termios.B4800
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 0

        termios.tcsetattr(fd, termios.TCSANOW, attrs)
        termios.tcflush(fd, termios.TCIOFLUSH)

    @property
    def in_waiting(self) -> int:
        fd = self._require_fd()
        buf = bytearray(4)
        request = getattr(self._termios, "FIONREAD", 0x541B)
        self._fcntl.ioctl(fd, request, buf, True)
        return int.from_bytes(buf, byteorder=sys.byteorder)

    def read(self, size: int = 1, /) -> bytes:
        fd = self._require_fd()
        deadline = time.monotonic() + self._timeout
        chunks: list[bytes] = []
        remaining = max(size, 1)

        while remaining > 0:
            timeout_left = deadline - time.monotonic()
            if timeout_left <= 0:
                break

            ready, _, _ = select.select([fd], [], [], timeout_left)
            if not ready:
                break

            try:
                chunk = os.read(fd, remaining)
            except BlockingIOError:
                continue

            if not chunk:
                break

            chunks.append(chunk)
            remaining -= len(chunk)

            if self.in_waiting <= 0:
                break

        return b"".join(chunks)

    def write(self, data: bytes | bytearray | memoryview, /) -> int:
        fd = self._require_fd()
        payload = bytes(data)
        total_written = 0
        while total_written < len(payload):
            _, writable, _ = select.select([], [fd], [], self._timeout)
            if not writable:
                raise TimeoutError("timed out while writing to serial port")
            total_written += os.write(fd, payload[total_written:])
        return total_written

    def flush(self) -> None:
        self._termios.tcdrain(self._require_fd())

    def reset_input_buffer(self) -> None:
        self._termios.tcflush(self._require_fd(), self._termios.TCIFLUSH)

    def close(self) -> None:
        fd = self._fd
        if fd is not None:
            os.close(fd)
            self._fd = None

    def __enter__(self) -> "PosixSerialPort":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def open_port(port: str, *, timeout: float = 0.2):
    if serial is not None:
        return serial.Serial(
            port=port,
            baudrate=BAUDRATE,
            bytesize=BYTESIZE,
            parity=PARITY,
            stopbits=STOPBITS,
            timeout=timeout,
        )

    if os.name != "posix":
        raise SerialBackendError(
            "pyserial is not installed and no stdlib serial backend is available on this OS"
        )

    return PosixSerialPort(port, timeout=timeout)


def read_matching_response(
    ser: SerialPortLike,
    *,
    expected_serial: int | None,
    timeout: float,
) -> BatteryTelemetry:
    deadline = time.monotonic() + timeout
    scanner = FrameScanner()

    while time.monotonic() < deadline:
        chunk = ser.read(ser.in_waiting or 1)
        if not chunk:
            continue

        for frame in scanner.feed(chunk):
            try:
                telemetry = decode_cmd_0500_response(frame)
            except ProtocolError:
                continue

            if expected_serial is None or telemetry.serial_number == expected_serial:
                return telemetry

    serial_text = "any serial" if expected_serial is None else f"serial {expected_serial}"
    raise TimeoutError(f"timed out waiting for a valid response for {serial_text}")


def send_cmd_0500_and_read(
    ser: SerialPortLike,
    *,
    serial_number: int,
    timeout: float,
    clear_input: bool = True,
) -> BatteryTelemetry:
    if clear_input:
        ser.reset_input_buffer()

    request = build_cmd_0500_request(serial_number)
    ser.write(request)
    ser.flush()
    return read_matching_response(
        ser,
        expected_serial=None if serial_number == 0 else serial_number,
        timeout=timeout,
    )


def format_status_flags(status_flags: Iterable[int]) -> str:
    return " ".join(f"{value:02X}" for value in status_flags)
