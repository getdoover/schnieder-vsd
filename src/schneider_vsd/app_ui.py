"""Schneider VSD UI definition."""

from pydoover import ui

from .app_tags import SchneiderVsdTags


class SchneiderVsdUI(ui.UI):

    # --- Operating mode ---
    mode_selector = ui.Select(
        "Operating Mode",
        name="mode_selector",
        options=[
            ui.Option("User Control"),
            ui.Option("Terminal Control"),
        ],
        default="user_control",
        help_str=(
            "Controls how the drive receives start/stop commands.\n\n"
            "User Control — start, stop, and set speed from this interface. "
            "The drive accepts commands over its network connection.\n\n"
            "Terminal Control — the drive is controlled by a physical signal "
            "wired to its terminal inputs (e.g. a float switch or relay). "
            "Remote controls are disabled while in this mode."
        ),
    )

    # --- Operating values (top-level) ---
    output_frequency = ui.NumericVariable(
        "Speed", value=SchneiderVsdTags.vsd_frequency,
        units="Hz", precision=1,
    )
    motor_current = ui.NumericVariable(
        "Current Draw", value=SchneiderVsdTags.vsd_current,
        units="A", precision=1,
    )
    drive_temperature = ui.NumericVariable(
        "Drive Temperature", value=SchneiderVsdTags.vsd_temperature,
        units="°C", precision=0,
    )
    motor_run_hours = ui.NumericVariable(
        "Total Hours", value=SchneiderVsdTags.motor_run_hours,
        units="hrs", precision=1,
    )

    # --- Digital inputs (top-level, hidden unless labelled in config) ---
    di_1 = ui.BooleanVariable("Digital Input 1", value=SchneiderVsdTags.di_1)
    di_2 = ui.BooleanVariable("Digital Input 2", value=SchneiderVsdTags.di_2)
    di_3 = ui.BooleanVariable("Digital Input 3", value=SchneiderVsdTags.di_3)

    # --- Control (top-level, visibility managed from application.py) ---
    frequency_setpoint = ui.FloatInput(
        "Frequency Setpoint", units="Hz", precision=1,
        help_str="Set the target output frequency for the motor.",
    )
    start_button = ui.Button(
        "Start", name="start_button", requires_confirm=True,
        help_str="Send a start command to the drive.",
    )
    stop_button = ui.Button(
        "Stop", name="stop_button", requires_confirm=True,
        help_str="Send a stop command to the drive.",
    )
    reset_fault_button = ui.Button(
        "Reset Fault", name="reset_fault_button", requires_confirm=True,
        help_str=(
            "Clear an active fault on the drive. "
            "The drive must be in a faulted state for this to take effect."
        ),
    )

    async def setup(self):
        """Configure dynamic UI properties from app config."""
        terminal_label = self.config.terminal_mode_label.value

        # Only show mode selector if a terminal mode label is configured
        if not terminal_label:
            self.mode_selector.hidden = True
        else:
            # Rename the "Terminal Control" option to the configured label
            self.mode_selector.options[1].display_name = terminal_label
            # Fresh installs with a physical terminal wired up should default
            # to terminal control so Modbus commands don't fight the wiring.
            self.mode_selector.default = "terminal_control"

        # Frequency input range
        self.frequency_setpoint.min_val = self.config.min_frequency.value
        self.frequency_setpoint.max_val = self.config.max_frequency.value

        # Digital input labels — hide any DI whose config value is blank or
        # still at the literal default "Digital Input N".
        for idx, (di, cfg_value) in enumerate([
            (self.di_1, self.config.di_1_name.value),
            (self.di_2, self.config.di_2_name.value),
            (self.di_3, self.config.di_3_name.value),
        ], start=1):
            default_label = f"Digital Input {idx}"
            if not cfg_value or cfg_value == default_label:
                di.hidden = True
            else:
                di.display_name = cfg_value

        # Colour ranges for frequency
        max_freq = self.config.max_frequency.value
        self.output_frequency.ranges = [
            ui.Range(None, 0, max_freq * 0.2, ui.Colour.blue),
            ui.Range(None, max_freq * 0.2, max_freq, ui.Colour.green),
        ]

        # Colour ranges for temperature
        temp_thresh = self.config.overtemperature_threshold.value
        self.drive_temperature.ranges = [
            ui.Range(None, 0, temp_thresh * 0.75, ui.Colour.green),
            ui.Range(None, temp_thresh * 0.75, temp_thresh, ui.Colour.yellow),
            ui.Range(None, temp_thresh, temp_thresh * 1.5, ui.Colour.red),
        ]

        # Colour ranges for current
        max_amps = self.config.max_amps.value
        oc_pct = self.config.overcurrent_threshold.value / 100.0
        self.motor_current.ranges = [
            ui.Range(None, 0, max_amps * oc_pct, ui.Colour.green),
            ui.Range(None, max_amps * oc_pct, max_amps * 1.5, ui.Colour.red),
        ]
