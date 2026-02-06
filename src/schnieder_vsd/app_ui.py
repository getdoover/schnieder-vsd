from pydoover import ui


class SchniederVsdUI:
    """UI components for Schneider VSD control and monitoring."""

    def __init__(self):
        # Connection status
        self.connection_status = ui.TextVariable(
            "connection_status",
            "Connection Status"
        )
        self.last_communication = ui.DateTimeVariable(
            "last_communication",
            "Last Communication"
        )

        # VSD Status submodule
        self.status = ui.Submodule("vsd_status", "VSD Status")
        self.drive_state = ui.TextVariable("drive_state", "Drive State")
        self.is_running = ui.BooleanVariable("is_running", "Running")
        self.is_ready = ui.BooleanVariable("is_ready", "Ready")
        self.is_faulted = ui.BooleanVariable("is_faulted", "Faulted")
        self.fault_code = ui.TextVariable("fault_code", "Fault Code")
        self.status.add_children(
            self.drive_state,
            self.is_running,
            self.is_ready,
            self.is_faulted,
            self.fault_code
        )

        # Operating values submodule
        self.operating = ui.Submodule("operating_values", "Operating Values")
        self.output_frequency = ui.NumericVariable(
            "output_frequency",
            "Output Frequency",
            precision=1,
            unit="Hz",
            ranges=[
                ui.Range("Low", 0, 10, ui.Colour.blue),
                ui.Range("Normal", 10, 50, ui.Colour.green),
                ui.Range("High", 50, 60, ui.Colour.red),
            ]
        )
        self.motor_current = ui.NumericVariable(
            "motor_current",
            "Motor Current",
            precision=1,
            unit="A",
            ranges=[
                ui.Range("Normal", 0, 100, ui.Colour.green),
                ui.Range("Warning", 100, 120, ui.Colour.yellow),
                ui.Range("Overload", 120, 200, ui.Colour.red),
            ]
        )
        self.motor_voltage = ui.NumericVariable(
            "motor_voltage",
            "Motor Voltage",
            precision=0,
            unit="V"
        )
        self.motor_power = ui.NumericVariable(
            "motor_power",
            "Motor Power",
            precision=1,
            unit="kW"
        )
        self.drive_temperature = ui.NumericVariable(
            "drive_temperature",
            "Drive Temperature",
            precision=0,
            unit="C",
            ranges=[
                ui.Range("Normal", 0, 60, ui.Colour.green),
                ui.Range("Warning", 60, 80, ui.Colour.yellow),
                ui.Range("Critical", 80, 120, ui.Colour.red),
            ]
        )
        self.dc_bus_voltage = ui.NumericVariable(
            "dc_bus_voltage",
            "DC Bus Voltage",
            precision=0,
            unit="V"
        )
        self.operating.add_children(
            self.output_frequency,
            self.motor_current,
            self.motor_voltage,
            self.motor_power,
            self.drive_temperature,
            self.dc_bus_voltage
        )

        # Control submodule
        self.control = ui.Submodule("vsd_control", "VSD Control")
        self.frequency_setpoint = ui.NumericParameter(
            "frequency_setpoint",
            "Frequency Setpoint (Hz)",
            precision=1
        )
        self.run_command = ui.StateCommand(
            "run_command",
            "Run Command",
            user_options=[
                ui.Option("stop", "Stop"),
                ui.Option("run", "Run"),
            ]
        )
        self.start_button = ui.Action(
            "start_button",
            "Start",
            colour=ui.Colour.green,
            position=1
        )
        self.stop_button = ui.Action(
            "stop_button",
            "Stop",
            colour=ui.Colour.red,
            requires_confirm=True,
            position=2
        )
        self.reset_fault = ui.Action(
            "reset_fault",
            "Reset Fault",
            colour=ui.Colour.yellow,
            requires_confirm=True,
            position=3
        )
        self.control.add_children(
            self.frequency_setpoint,
            self.run_command,
            self.start_button,
            self.stop_button,
            self.reset_fault
        )

        # Warnings
        self.overcurrent_warning = ui.WarningIndicator(
            "overcurrent_warning",
            "Overcurrent Warning",
            hidden=True
        )
        self.overtemperature_warning = ui.WarningIndicator(
            "overtemperature_warning",
            "Overtemperature Warning",
            hidden=True
        )
        self.communication_warning = ui.WarningIndicator(
            "communication_warning",
            "Communication Lost",
            hidden=True
        )

        # Alert stream for notifications
        self.alerts = ui.AlertStream()

    def fetch(self):
        """Return all UI components to be registered."""
        return (
            self.connection_status,
            self.last_communication,
            self.status,
            self.operating,
            self.control,
            self.overcurrent_warning,
            self.overtemperature_warning,
            self.communication_warning,
        )

    def update_connection(self, connected: bool, last_comm=None):
        """Update connection status indicators."""
        if connected:
            self.connection_status.update("Connected")
            self.communication_warning.hide()
        else:
            self.connection_status.update("Disconnected")
            self.communication_warning.show()
        if last_comm:
            self.last_communication.update(last_comm)

    def update_status(
        self,
        drive_state: str,
        running: bool,
        ready: bool,
        faulted: bool,
        fault_code: str = ""
    ):
        """Update VSD status indicators."""
        self.drive_state.update(drive_state)
        self.is_running.update(running)
        self.is_ready.update(ready)
        self.is_faulted.update(faulted)
        self.fault_code.update(fault_code if faulted else "None")

    def update_operating_values(
        self,
        frequency: float,
        current: float,
        voltage: float,
        power: float,
        temperature: float,
        dc_bus: float
    ):
        """Update operating value displays."""
        self.output_frequency.update(frequency)
        self.motor_current.update(current)
        self.motor_voltage.update(voltage)
        self.motor_power.update(power)
        self.drive_temperature.update(temperature)
        self.dc_bus_voltage.update(dc_bus)

    def update_warnings(
        self,
        overcurrent: bool,
        overtemperature: bool
    ):
        """Update warning indicators."""
        if overcurrent:
            self.overcurrent_warning.show()
        else:
            self.overcurrent_warning.hide()

        if overtemperature:
            self.overtemperature_warning.show()
        else:
            self.overtemperature_warning.hide()
