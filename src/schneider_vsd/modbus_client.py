"""Thin async Modbus TCP client wrapper.

Provides a connection-per-operation model for reliable communication
with Schneider Altivar VSDs over Modbus TCP. Each operation opens a
fresh TCP connection and closes it when done, avoiding stale connection
issues common with industrial Modbus devices.
"""

import logging
import struct

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

log = logging.getLogger(__name__)


class ModbusTcpConnection:
    """Async context manager for a single Modbus TCP connection.

    Usage::

        async with ModbusTcpConnection(host, port, slave_id) as conn:
            regs = await conn.read_holding_registers(3200, 75)
            await conn.write_register(8501, 7)
    """

    def __init__(self, host: str, port: int, slave_id: int, timeout: float = 3.0):
        self.host = host
        self.port = port
        self.slave_id = slave_id
        self.timeout = timeout
        self._client: AsyncModbusTcpClient | None = None

    async def __aenter__(self):
        self._client = AsyncModbusTcpClient(
            self.host, port=self.port, timeout=self.timeout,
        )
        await self._client.connect()
        if not self._client.connected:
            raise ConnectionError(f"Failed to connect to {self.host}:{self.port}")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            self._client.close()
            self._client = None
        return False

    async def read_holding_registers(self, address: int, count: int) -> list[int] | None:
        """Read holding registers (FC3). Returns register values or None on error."""
        try:
            result = await self._client.read_holding_registers(
                address, count=count, device_id=self.slave_id,
            )
            if result.isError():
                log.warning("Error reading registers %d-%d: %s", address, address + count, result)
                return None
            return list(result.registers)
        except (ModbusException, Exception) as e:
            log.error("Exception reading registers %d-%d: %s", address, address + count, e)
            return None

    async def write_register(self, address: int, value: int) -> bool:
        """Write a single holding register (FC6). Returns True on success."""
        try:
            result = await self._client.write_register(
                address, value, device_id=self.slave_id,
            )
            if result.isError():
                log.warning("Error writing register %d=%d: %s", address, value, result)
                return False
            return True
        except (ModbusException, Exception) as e:
            log.error("Exception writing register %d=%d: %s", address, value, e)
            return False

    async def write_register_bits(
        self,
        address: int,
        bits_to_set: list[int] | None = None,
        bits_to_unset: list[int] | None = None,
    ) -> bool:
        """Read-modify-write individual bits in a holding register.

        Reads the current value, applies bit changes, writes back.
        Safe way to modify control register bits without disturbing others.
        """
        bits_to_set = bits_to_set or []
        bits_to_unset = bits_to_unset or []

        registers = await self.read_holding_registers(address, 1)
        if registers is None:
            return False

        value = registers[0]
        for bit in bits_to_set:
            value |= (1 << bit)
        for bit in bits_to_unset:
            value &= ~(1 << bit)

        return await self.write_register(address, value)


# --- Register value extraction helpers ---


def reg_uint16(registers: list[int], offset: int) -> int:
    """Extract uint16 value at offset in register list."""
    return registers[offset]


def reg_int16(registers: list[int], offset: int) -> int:
    """Extract signed int16 value at offset in register list."""
    raw = registers[offset]
    return struct.unpack(">h", struct.pack(">H", raw))[0]


def reg_uint32(registers: list[int], offset: int) -> int:
    """Extract uint32 from two consecutive registers (big-endian word order)."""
    high = registers[offset]
    low = registers[offset + 1]
    packed = struct.pack(">HH", high, low)
    return struct.unpack(">I", packed)[0]
