"""Schneider VSD application tags (persisted state)."""

from pydoover.tags import Tag, Tags


class SchneiderVsdTags(Tags):

    app_display_name = Tag("string", default="Schneider VSD")

    # Operating mode ("user_control" or "terminal_control")
    operating_mode = Tag("string", default="user_control")

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

    # Cross-app alerting (e.g. pump shutdown on VSD fault)
    alert_triggered = Tag("boolean", default=False)
    alert_message_short = Tag("string", default=None)
    alert_message_long = Tag("string", default=None)
