import logging

from pydoover.state import StateMachine

log = logging.getLogger(__name__)


class SchniederVsdState:
    """State machine for Schneider VSD operational states.

    Manages the VSD lifecycle including:
    - Initialization and connection
    - Ready/running states
    - Fault handling and recovery
    """

    state: str

    states = [
        {"name": "disconnected"},
        {"name": "connecting", "timeout": 10, "on_timeout": "connection_timeout"},
        {"name": "ready"},
        {"name": "starting", "timeout": 30, "on_timeout": "start_timeout"},
        {"name": "running"},
        {"name": "stopping", "timeout": 30, "on_timeout": "stop_timeout"},
        {"name": "faulted"},
        {"name": "resetting", "timeout": 10, "on_timeout": "reset_timeout"},
    ]

    transitions = [
        # Connection transitions
        {"trigger": "connect", "source": "disconnected", "dest": "connecting"},
        {"trigger": "connected", "source": "connecting", "dest": "ready"},
        {"trigger": "connection_timeout", "source": "connecting", "dest": "disconnected"},
        {"trigger": "disconnect", "source": "*", "dest": "disconnected"},

        # Start/stop transitions
        {"trigger": "start", "source": "ready", "dest": "starting"},
        {"trigger": "started", "source": "starting", "dest": "running"},
        {"trigger": "start_timeout", "source": "starting", "dest": "faulted"},
        {"trigger": "stop", "source": ["running", "starting"], "dest": "stopping"},
        {"trigger": "stopped", "source": "stopping", "dest": "ready"},
        {"trigger": "stop_timeout", "source": "stopping", "dest": "faulted"},

        # Fault transitions
        {"trigger": "fault", "source": "*", "dest": "faulted"},
        {"trigger": "reset", "source": "faulted", "dest": "resetting"},
        {"trigger": "reset_complete", "source": "resetting", "dest": "ready"},
        {"trigger": "reset_timeout", "source": "resetting", "dest": "faulted"},
    ]

    def __init__(self, app=None):
        self.app = app
        self.fault_code = None
        self.fault_description = None

        self.state_machine = StateMachine(
            states=self.states,
            transitions=self.transitions,
            model=self,
            initial="disconnected",
            queued=True,
        )

    # State entry callbacks
    async def on_enter_disconnected(self):
        log.info("VSD state: Disconnected")

    async def on_enter_connecting(self):
        log.info("VSD state: Connecting...")

    async def on_enter_ready(self):
        log.info("VSD state: Ready")
        self.fault_code = None
        self.fault_description = None

    async def on_enter_starting(self):
        log.info("VSD state: Starting motor...")

    async def on_enter_running(self):
        log.info("VSD state: Running")

    async def on_enter_stopping(self):
        log.info("VSD state: Stopping motor...")

    async def on_enter_faulted(self):
        log.error(f"VSD state: Faulted - {self.fault_code}: {self.fault_description}")

    async def on_enter_resetting(self):
        log.info("VSD state: Resetting fault...")

    def set_fault(self, code: str, description: str):
        """Set fault information before triggering fault transition."""
        self.fault_code = code
        self.fault_description = description

    @property
    def is_connected(self) -> bool:
        """Check if connected to VSD."""
        return self.state not in ["disconnected", "connecting"]

    @property
    def is_running(self) -> bool:
        """Check if motor is running."""
        return self.state == "running"

    @property
    def is_ready(self) -> bool:
        """Check if VSD is ready for commands."""
        return self.state == "ready"

    @property
    def is_faulted(self) -> bool:
        """Check if VSD is in fault state."""
        return self.state == "faulted"

    @property
    def can_start(self) -> bool:
        """Check if start command is allowed."""
        return self.state == "ready"

    @property
    def can_stop(self) -> bool:
        """Check if stop command is allowed."""
        return self.state in ["running", "starting"]

    @property
    def can_reset(self) -> bool:
        """Check if reset command is allowed."""
        return self.state == "faulted"

    def get_state_display(self) -> str:
        """Get human-readable state description."""
        state_names = {
            "disconnected": "Disconnected",
            "connecting": "Connecting...",
            "ready": "Ready",
            "starting": "Starting...",
            "running": "Running",
            "stopping": "Stopping...",
            "faulted": "Faulted",
            "resetting": "Resetting...",
        }
        return state_names.get(self.state, self.state)

    # Trigger method type hints for IDE autocomplete
    async def connect(self): ...
    async def connected(self): ...
    async def connection_timeout(self): ...
    async def disconnect(self): ...
    async def start(self): ...
    async def started(self): ...
    async def start_timeout(self): ...
    async def stop(self): ...
    async def stopped(self): ...
    async def stop_timeout(self): ...
    async def fault(self): ...
    async def reset(self): ...
    async def reset_complete(self): ...
    async def reset_timeout(self): ...
