"""Modbus client for Schneider Altivar VSD communication.

This module provides a high-level interface for communicating with
Schneider Altivar series Variable Speed Drives via Modbus TCP.

Register Map (Altivar ATV320/ATV340 series):
- Holding Registers (read/write):
  - 8501 (CMD): Control word
  - 8502 (LFRD): Frequency reference (0.1 Hz resolution)
  - 8601 (ACC): Acceleration time (0.1s resolution)
  - 8602 (DEC): Deceleration time (0.1s resolution)

- Input Registers (read-only):
  - 3201 (ETA): Status word
  - 3202 (RFRD): Output frequency (0.1 Hz)
  - 3203 (LCR): Motor current (0.1 A)
  - 3204 (UOP): Motor voltage (V)
  - 3205 (OPR): Motor power (0.1 kW)
  - 3210 (THD): Drive temperature (C)
  - 3211 (UDC): DC bus voltage (V)
  - 3221 (LFT): Last fault code
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

log = logging.getLogger(__name__)


# Schneider Altivar register addresses
class AltivarRegisters:
    """Modbus register addresses for Schneider Altivar VSDs."""

    # Control registers (holding registers - read/write)
    CMD = 8501          # Control word
    LFRD = 8502         # Frequency reference setpoint
    ACC = 8601          # Acceleration time
    DEC = 8602          # Deceleration time

    # Status registers (input registers - read only)
    ETA = 3201          # Status word
    RFRD = 3202         # Output frequency
    LCR = 3203          # Motor current
    UOP = 3204          # Motor voltage
    OPR = 3205          # Motor power
    THD = 3210          # Drive temperature
    UDC = 3211          # DC bus voltage
    LFT = 3221          # Last fault code


# Control word bits (CMD register)
class ControlBits:
    """Control word bit definitions."""
    RUN = 0             # Run command
    DIRECTION = 1       # Forward (0) / Reverse (1)
    FAULT_RESET = 7     # Fault reset command


# Status word bits (ETA register)
class StatusBits:
    """Status word bit definitions."""
    READY = 0           # Drive ready
    RUNNING = 1         # Motor running
    DIRECTION = 2       # Actual direction
    FAULT = 3           # Fault active
    WARNING = 7         # Warning active
    AT_REFERENCE = 10   # Speed at reference


# Fault codes
FAULT_CODES = {
    0: "No fault",
    2: "Overcurrent",
    3: "Overvoltage",
    4: "Undervoltage",
    5: "Overtemperature",
    6: "Motor overload",
    7: "External fault",
    8: "Ground fault",
    9: "Loss of motor phase",
    10: "Communication loss",
    17: "Internal communication",
    18: "Encoder fault",
    24: "Input phase loss",
    25: "DC bus overvoltage",
    30: "IGBT overtemperature",
    38: "Process underload",
    39: "Process overload",
    51: "EEPROM fault",
    64: "Motor short circuit",
    71: "Brake control fault",
}


@dataclass
class VsdStatus:
    """VSD status data structure."""
    connected: bool = False
    ready: bool = False
    running: bool = False
    faulted: bool = False
    warning: bool = False
    at_reference: bool = False
    direction_forward: bool = True
    output_frequency: float = 0.0
    motor_current: float = 0.0
    motor_voltage: float = 0.0
    motor_power: float = 0.0
    drive_temperature: float = 0.0
    dc_bus_voltage: float = 0.0
    fault_code: int = 0
    fault_description: str = "No fault"


class SchneiderVsdClient:
    """Async Modbus TCP client for Schneider Altivar VSDs."""

    def __init__(
        self,
        host: str,
        port: int = 502,
        unit_id: int = 1,
        timeout: float = 5.0
    ):
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.timeout = timeout
        self._client: Optional[AsyncModbusTcpClient] = None
        self._connected = False
        self._lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        """Check if client is connected."""
        return self._connected and self._client is not None

    async def connect(self) -> bool:
        """Establish connection to the VSD.

        Returns:
            True if connection successful, False otherwise.
        """
        async with self._lock:
            try:
                self._client = AsyncModbusTcpClient(
                    host=self.host,
                    port=self.port,
                    timeout=self.timeout
                )
                self._connected = await self._client.connect()

                if self._connected:
                    log.info(f"Connected to VSD at {self.host}:{self.port}")
                else:
                    log.warning(f"Failed to connect to VSD at {self.host}:{self.port}")

                return self._connected

            except Exception as e:
                log.error(f"Connection error: {e}")
                self._connected = False
                return False

    async def disconnect(self):
        """Close connection to the VSD."""
        async with self._lock:
            if self._client:
                self._client.close()
                self._client = None
            self._connected = False
            log.info("Disconnected from VSD")

    async def read_status(self) -> VsdStatus:
        """Read current VSD status.

        Returns:
            VsdStatus object with current values.
        """
        status = VsdStatus()

        if not self.is_connected:
            return status

        try:
            async with self._lock:
                # Read status registers (ETA to LFT)
                # Note: Altivar uses 1-based addressing, pymodbus uses 0-based
                result = await self._client.read_input_registers(
                    address=AltivarRegisters.ETA - 1,
                    count=21,  # ETA through LFT
                    slave=self.unit_id
                )

                if result.isError():
                    log.error(f"Failed to read status registers: {result}")
                    self._connected = False
                    return status

                # Parse status word (ETA)
                eta = result.registers[0]
                status.ready = bool(eta & (1 << StatusBits.READY))
                status.running = bool(eta & (1 << StatusBits.RUNNING))
                status.direction_forward = not bool(eta & (1 << StatusBits.DIRECTION))
                status.faulted = bool(eta & (1 << StatusBits.FAULT))
                status.warning = bool(eta & (1 << StatusBits.WARNING))
                status.at_reference = bool(eta & (1 << StatusBits.AT_REFERENCE))

                # Parse operating values
                status.output_frequency = result.registers[1] / 10.0  # RFRD
                status.motor_current = result.registers[2] / 10.0     # LCR
                status.motor_voltage = result.registers[3]            # UOP
                status.motor_power = result.registers[4] / 10.0       # OPR
                status.drive_temperature = result.registers[9]        # THD (offset 9 from ETA)
                status.dc_bus_voltage = result.registers[10]          # UDC

                # Read fault code
                status.fault_code = result.registers[20]  # LFT (offset 20 from ETA)
                status.fault_description = FAULT_CODES.get(
                    status.fault_code,
                    f"Unknown fault ({status.fault_code})"
                )

                status.connected = True

        except ModbusException as e:
            log.error(f"Modbus error reading status: {e}")
            self._connected = False
        except Exception as e:
            log.error(f"Error reading status: {e}")
            self._connected = False

        return status

    async def write_control_word(self, run: bool, reset: bool = False, reverse: bool = False) -> bool:
        """Write control word to VSD.

        Args:
            run: True to run, False to stop
            reset: True to reset fault
            reverse: True for reverse direction

        Returns:
            True if write successful.
        """
        if not self.is_connected:
            return False

        try:
            cmd = 0
            if run:
                cmd |= (1 << ControlBits.RUN)
            if reverse:
                cmd |= (1 << ControlBits.DIRECTION)
            if reset:
                cmd |= (1 << ControlBits.FAULT_RESET)

            async with self._lock:
                result = await self._client.write_register(
                    address=AltivarRegisters.CMD - 1,
                    value=cmd,
                    slave=self.unit_id
                )

                if result.isError():
                    log.error(f"Failed to write control word: {result}")
                    return False

            log.debug(f"Control word written: run={run}, reset={reset}, reverse={reverse}")
            return True

        except ModbusException as e:
            log.error(f"Modbus error writing control: {e}")
            return False
        except Exception as e:
            log.error(f"Error writing control: {e}")
            return False

    async def set_frequency(self, frequency_hz: float) -> bool:
        """Set frequency reference.

        Args:
            frequency_hz: Target frequency in Hz.

        Returns:
            True if write successful.
        """
        if not self.is_connected:
            return False

        try:
            # Convert to 0.1 Hz resolution
            freq_value = int(frequency_hz * 10)

            async with self._lock:
                result = await self._client.write_register(
                    address=AltivarRegisters.LFRD - 1,
                    value=freq_value,
                    slave=self.unit_id
                )

                if result.isError():
                    log.error(f"Failed to write frequency: {result}")
                    return False

            log.debug(f"Frequency setpoint written: {frequency_hz} Hz")
            return True

        except ModbusException as e:
            log.error(f"Modbus error writing frequency: {e}")
            return False
        except Exception as e:
            log.error(f"Error writing frequency: {e}")
            return False

    async def set_ramp_times(self, accel_seconds: float, decel_seconds: float) -> bool:
        """Set acceleration and deceleration times.

        Args:
            accel_seconds: Acceleration time in seconds.
            decel_seconds: Deceleration time in seconds.

        Returns:
            True if write successful.
        """
        if not self.is_connected:
            return False

        try:
            # Convert to 0.1s resolution
            accel_value = int(accel_seconds * 10)
            decel_value = int(decel_seconds * 10)

            async with self._lock:
                # Write acceleration time
                result = await self._client.write_register(
                    address=AltivarRegisters.ACC - 1,
                    value=accel_value,
                    slave=self.unit_id
                )
                if result.isError():
                    log.error(f"Failed to write acceleration time: {result}")
                    return False

                # Write deceleration time
                result = await self._client.write_register(
                    address=AltivarRegisters.DEC - 1,
                    value=decel_value,
                    slave=self.unit_id
                )
                if result.isError():
                    log.error(f"Failed to write deceleration time: {result}")
                    return False

            log.debug(f"Ramp times written: accel={accel_seconds}s, decel={decel_seconds}s")
            return True

        except ModbusException as e:
            log.error(f"Modbus error writing ramp times: {e}")
            return False
        except Exception as e:
            log.error(f"Error writing ramp times: {e}")
            return False

    async def start(self) -> bool:
        """Send start command to VSD."""
        return await self.write_control_word(run=True)

    async def stop(self) -> bool:
        """Send stop command to VSD."""
        return await self.write_control_word(run=False)

    async def reset_fault(self) -> bool:
        """Send fault reset command to VSD."""
        # Send reset pulse
        if await self.write_control_word(run=False, reset=True):
            await asyncio.sleep(0.5)  # Hold reset for 500ms
            return await self.write_control_word(run=False, reset=False)
        return False
