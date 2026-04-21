"""Schneider VSD application tags (persisted state)."""

from pydoover.tags import Tag, Tags


class SchneiderVsdTags(Tags):

    app_display_name = Tag("string", default="Schneider VSD")

    # Connection
    comms_active = Tag("boolean", default=False)

    # Drive state
    vsd_state = Tag("string", default="disconnected")
    vsd_running = Tag("boolean", default=False)
    vsd_faulted = Tag("boolean", default=False)
    vsd_fault_code = Tag("number", default=None)
    vsd_fault_description = Tag("string", default=None)

    # Operating values
    vsd_frequency = Tag("number", default=None)
    vsd_current = Tag("number", default=None)
    vsd_voltage = Tag("number", default=None)
    vsd_power = Tag("number", default=None)
    vsd_temperature = Tag("number", default=None)
    motor_run_hours = Tag("number", default=None)

    # Digital inputs
    di_1 = Tag("boolean", default=None)
    di_2 = Tag("boolean", default=None)
    di_3 = Tag("boolean", default=None)

    # Dynamic UI state (bound into UI element hidden/display_name resolvers).
    # Default True means element starts hidden until main_loop decides otherwise.
    hide_start_button = Tag("boolean", default=True)
    hide_stop_button = Tag("boolean", default=True)
    hide_reset_fault_button = Tag("boolean", default=True)
    hide_frequency_setpoint = Tag("boolean", default=True)
    hide_no_comms_warning = Tag("boolean", default=True)
    hide_motor_fault_warning = Tag("boolean", default=True)
    motor_fault_label = Tag("string", default="Motor Fault")
