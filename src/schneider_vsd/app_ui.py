"""Schneider VSD UI definition."""

from pydoover import ui

from .app_tags import SchneiderVsdTags


# Tag-backed resolvers for attributes that change at runtime. The UI schema
# is published once at setup, so we can't mutate element.hidden / display_name
# from main_loop — the mutations wouldn't propagate. Instead we bind those
# fields to tags and update the tags each cycle; the platform re-resolves on
# each render.
_HIDE_START = "$tag.app().hide_start_button:boolean:true"
_HIDE_STOP = "$tag.app().hide_stop_button:boolean:true"
_HIDE_RESET = "$tag.app().hide_reset_fault_button:boolean:true"
_HIDE_FREQ = "$tag.app().hide_frequency_setpoint:boolean:true"
_HIDE_NO_COMMS = "$tag.app().hide_no_comms_warning:boolean:true"
_HIDE_MOTOR_FAULT = "$tag.app().hide_motor_fault_warning:boolean:true"
_MOTOR_FAULT_LABEL = '$tag.app().motor_fault_label:string:"Motor Fault"'
_APP_DISPLAY_NAME = '$tag.app().app_display_name:string:"Schneider VSD"'


class SchneiderVsdUI(ui.UI, display_name=_APP_DISPLAY_NAME):

    # --- Warnings (top of page; visibility driven by tags) ---
    no_comms_warning = ui.WarningIndicator(
        "No communications with VSD",
        name="no_comms_warning",
        hidden=_HIDE_NO_COMMS,
        can_cancel=False,
    )
    motor_fault_warning = ui.WarningIndicator(
        _MOTOR_FAULT_LABEL,
        name="motor_fault_warning",
        hidden=_HIDE_MOTOR_FAULT,
        can_cancel=False,
    )

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
        units="Hz", precision=1, form=ui.Widget.radial, icon="gauge",
    )
    motor_power = ui.NumericVariable(
        "Motor Power", value=SchneiderVsdTags.vsd_power,
        units="kW", precision=1, icon="bolt",
    )
    drive_thermal_load = ui.NumericVariable(
        "Drive Thermal Load", value=SchneiderVsdTags.vsd_thermal_load,
        units="%", precision=0, icon="thermometer-half",
    )
    mains_voltage = ui.NumericVariable(
        "Mains Voltage", value=SchneiderVsdTags.vsd_mains_voltage,
        units="V", precision=0, icon="plug",
    )
    motor_run_hours = ui.NumericVariable(
        "Total Hours", value=SchneiderVsdTags.motor_run_hours,
        units="hrs", precision=1, icon="clock",
    )

    # --- Digital inputs (top-level; config-driven hide in setup()) ---
    di_1 = ui.BooleanVariable("Digital Input 1", value=SchneiderVsdTags.di_1, icon="toggle-on")
    di_2 = ui.BooleanVariable("Digital Input 2", value=SchneiderVsdTags.di_2, icon="toggle-on")
    di_3 = ui.BooleanVariable("Digital Input 3", value=SchneiderVsdTags.di_3, icon="toggle-on")

    # --- Control (top-level; runtime hide bound to tags) ---
    frequency_setpoint = ui.FloatInput(
        "Frequency Setpoint", units="Hz", precision=1,
        hidden=_HIDE_FREQ,
        help_str="Set the target output frequency for the motor.",
    )
    start_button = ui.Button(
        "Start", name="start_button", requires_confirm=True,
        hidden=_HIDE_START,
        help_str="Send a start command to the drive.",
    )
    stop_button = ui.Button(
        "Stop", name="stop_button", requires_confirm=True,
        hidden=_HIDE_STOP,
        help_str="Send a stop command to the drive.",
    )
    reset_fault_button = ui.Button(
        "Reset Fault", name="reset_fault_button", requires_confirm=True,
        hidden=_HIDE_RESET,
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

        # Colour ranges for drive thermal load (%). THD trips at ~118%.
        temp_thresh = self.config.overtemperature_threshold.value
        self.drive_thermal_load.ranges = [
            ui.Range(None, 0, temp_thresh * 0.75, ui.Colour.green),
            ui.Range(None, temp_thresh * 0.75, temp_thresh, ui.Colour.yellow),
            ui.Range(None, temp_thresh, temp_thresh * 1.5, ui.Colour.red),
        ]

        # Colour ranges for motor power
        max_kw = self.config.max_power_kw.value
        op_pct = self.config.overpower_threshold.value / 100.0
        self.motor_power.ranges = [
            ui.Range(None, 0, max_kw * op_pct, ui.Colour.green),
            ui.Range(None, max_kw * op_pct, max_kw * 1.5, ui.Colour.red),
        ]

        # Colour ranges for mains voltage — covers EU 400 V and AU/NZ 415 V
        # systems with ±~10 % tolerance. Anything outside 360–440 V is abnormal.
        self.mains_voltage.ranges = [
            ui.Range(None, 0, 360, ui.Colour.red),
            ui.Range(None, 360, 440, ui.Colour.green),
            ui.Range(None, 440, 600, ui.Colour.red),
        ]
