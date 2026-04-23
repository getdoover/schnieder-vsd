"""Schneider VSD configuration schema."""

from pydoover import config


class SchneiderVsdConfig(config.Schema):

    # VSD model
    vsd_type = config.Enum(
        "VSD Type",
        choices=["atv600"],
        default="atv600",
        description="Schneider Altivar model",
    )

    # Modbus connection
    modbus_host = config.String(
        "Modbus Host",
        default="192.168.1.100",
        description="IP address or hostname of the VSD",
    )
    modbus_port = config.Integer(
        "Modbus Port",
        default=502,
    )
    modbus_unit_id = config.Integer(
        "Modbus Unit ID",
        default=0,
        minimum=0,
        maximum=247,
        description=(
            "Modbus slave/unit ID. ATV6xx embedded Ethernet typically uses "
            "the value set in ADDT on the drive HMI (often 248 by default, "
            "sometimes left at 1). Try 0 if writes fail with ILLEGAL FUNCTION "
            "— some drives accept 0 as a catch-all on Ethernet."
        ),
    )

    # Operating limits
    max_frequency = config.Number(
        "Max Frequency (Hz)",
        default=50.0,
        description="Maximum allowed frequency setpoint",
    )
    min_frequency = config.Number(
        "Min Frequency (Hz)",
        default=0.0,
        description="Minimum allowed frequency setpoint",
    )

    # Motor rating (used for overload warnings and UI colour ranges)
    max_power_kw = config.Number(
        "Motor Rated Power (kW)",
        default=7.5,
        description="Nominal motor power rating in kW. Used for "
                    "overload warnings and power colour-coding.",
    )

    # Current scaling (varies by ATV model/configuration) — hidden; only
    # used to populate status.current_amps for tags/logging.
    amps_divisor = config.Integer(
        "Amps Divisor",
        default=10,
        description="Divisor for motor current register value",
        hidden=True,
    )

    # Operating mode
    terminal_mode_label = config.String(
        "Terminal Mode Label",
        default="",
        description=(
            "If set, a mode selector appears in the UI allowing the operator "
            "to switch between terminal control (e.g. a float switch wired to "
            "the drive) and remote user control. The label you enter here is "
            "shown as the name of the terminal mode (e.g. 'Float Switch'). "
            "Leave blank if the drive is always controlled remotely."
        ),
    )

    # Digital input labels
    di_1_name = config.String("DI 1 Name", default="Digital Input 1")
    di_2_name = config.String("DI 2 Name", default="Digital Input 2")
    di_3_name = config.String("DI 3 Name", default="Digital Input 3")

    # Comms watchdog — the drive faults on Modbus silence beyond this timeout.
    # Factory default is 10 s which is too tight for a typical container
    # restart. Max accepted by the drive is 30 s.
    modbus_timeout_seconds = config.Number(
        "Modbus Timeout (seconds)",
        default=30.0,
        description=(
            "How long the drive waits with no Modbus requests before treating "
            "it as comms loss. Max 30 s per Schneider. Set high enough to "
            "cover a container restart."
        ),
        hidden=True,
    )
    stop_on_comms_loss = config.Boolean(
        "Stop Motor on Comms Loss",
        default=True,
        description=(
            "If true, drive freewheel-stops the motor when Modbus comms are "
            "lost beyond the timeout. If false, drive keeps running — use "
            "only when loss of remote monitoring alone shouldn't stop the "
            "pump."
        ),
        hidden=True,
    )

    # Alarm thresholds
    overpower_threshold = config.Number(
        "Overpower Threshold (%)",
        default=110.0,
        description="Percentage of rated power that triggers overload warning",
        hidden=True,
    )
    overtemperature_threshold = config.Number(
        "Overtemperature Threshold (C)",
        default=80.0,
        description="Drive temperature alarm threshold in degrees C",
        hidden=True,
    )

    position = config.ApplicationPosition()


def export():
    from pathlib import Path

    SchneiderVsdConfig.export(
        Path(__file__).parents[2] / "doover_config.json",
        "schneider_vsd",
    )
