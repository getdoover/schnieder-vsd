"""Abstract base class for Schneider VSD models.

Defines the interface that each VSD model must implement.
Subclasses provide the register map, command sequences, and
status parsing specific to their Altivar model.
"""

import abc
import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass
class VsdStatus:
    """Snapshot of VSD state from a single poll cycle."""

    contactable: bool = False

    # HMIS state (Schneider high-level status word)
    hmis_state: int = 0
    hmis_name: str = "unknown"

    # Derived state flags
    is_ready: bool = False
    is_running: bool = False
    is_faulted: bool = False
    is_warning: bool = False

    # Operating values
    frequency_hz: float = 0.0
    current_amps: float = 0.0
    motor_voltage_v: float = 0.0   # UOP, motor output voltage (V)
    mains_voltage_v: float = 0.0   # ULN, mains input voltage (V)
    power_pct: float = 0.0         # OPR, motor power (% of nominal, signed)
    temperature_c: float = 0.0     # TJP0, IGBT junction temperature (°C)
    motor_run_hours: float = 0.0

    # Fault info
    fault_code: int = 0
    fault_description: str = ""

    # Digital inputs
    di_1: bool = False
    di_2: bool = False
    di_3: bool = False

    # Analog inputs (AI1C..AI5C physical scaled values)
    ai_values: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0, 0.0])

    # Raw registers for debugging
    raw_registers: dict[int, int] = field(default_factory=dict)


class VsdBase(abc.ABC):
    """Abstract base for Schneider Altivar VSD drivers."""

    def __init__(
        self,
        host: str,
        port: int = 502,
        slave_id: int = 1,
        timeout: float = 3.0,
        amps_divisor: int = 10,
        max_frequency: float = 50.0,
        min_frequency: float = 0.0,
    ):
        self.host = host
        self.port = port
        self.slave_id = slave_id
        self.timeout = timeout
        self.amps_divisor = amps_divisor
        self.max_frequency = max_frequency
        self.min_frequency = min_frequency

        self._contactable = False
        self._last_status: VsdStatus | None = None
        self._last_clear_fault_time: float = 0
        self._last_start_time: float = 0

    @property
    def is_contactable(self) -> bool:
        return self._contactable

    @property
    def last_status(self) -> VsdStatus | None:
        return self._last_status

    @abc.abstractmethod
    async def run_setup(self) -> bool:
        """Write initial configuration to prepare the drive for remote control."""
        ...

    @abc.abstractmethod
    async def read_status(self) -> VsdStatus:
        """Read all status registers and return a parsed snapshot."""
        ...

    @abc.abstractmethod
    async def start_motor(self) -> bool:
        """Execute the full start sequence (mode switch + start command)."""
        ...

    @abc.abstractmethod
    async def stop_motor(self) -> bool:
        """Execute the full stop sequence (stop command + revert mode)."""
        ...

    @abc.abstractmethod
    async def set_target_freq(self, frequency_hz: float) -> bool:
        """Set speed reference. Frequency is clamped to [min, max]."""
        ...

    @abc.abstractmethod
    async def clear_fault(self) -> bool:
        """Send fault reset command."""
        ...

    @abc.abstractmethod
    async def set_operating_mode(self, mode: str) -> bool:
        """Switch operating mode (model-specific: local/remote/terminal)."""
        ...

    @abc.abstractmethod
    async def manage_operating_state(self) -> None:
        """Periodic housekeeping: auto fault recovery, mode maintenance."""
        ...
