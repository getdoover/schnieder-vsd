from pathlib import Path

from pydoover import config


class SchniederVsdConfig(config.Schema):
    """Configuration schema for Schneider VSD control application.

    Supports Schneider Altivar series VSDs via Modbus TCP/RTU.
    """

    def __init__(self):
        # Display settings
        self.display_name = config.String(
            "Display Name",
            description="Name shown in the UI for this VSD",
            default="Schneider VSD"
        )

        # Modbus connection settings
        self.modbus_host = config.String(
            "Modbus Host",
            description="IP address or hostname of the Modbus TCP gateway",
            default="192.168.1.100"
        )
        self.modbus_port = config.Integer(
            "Modbus Port",
            description="Modbus TCP port (default 502)",
            default=502
        )
        self.modbus_unit_id = config.Integer(
            "Modbus Unit ID",
            description="Modbus slave/unit ID of the VSD",
            default=1
        )
        self.connection_timeout = config.Number(
            "Connection Timeout",
            description="Timeout for Modbus connection in seconds",
            default=5.0
        )

        # VSD operational limits
        self.max_frequency = config.Number(
            "Maximum Frequency (Hz)",
            description="Maximum allowed frequency setpoint",
            default=50.0
        )
        self.min_frequency = config.Number(
            "Minimum Frequency (Hz)",
            description="Minimum allowed frequency setpoint",
            default=0.0
        )
        self.acceleration_time = config.Number(
            "Acceleration Time (s)",
            description="Time to accelerate from 0 to max frequency",
            default=10.0
        )
        self.deceleration_time = config.Number(
            "Deceleration Time (s)",
            description="Time to decelerate from max frequency to 0",
            default=10.0
        )

        # Safety settings
        self.enable_remote_control = config.Boolean(
            "Enable Remote Control",
            description="Allow remote start/stop commands",
            default=False
        )
        self.enable_speed_control = config.Boolean(
            "Enable Speed Control",
            description="Allow remote frequency/speed changes",
            default=False
        )

        # Monitoring settings
        self.poll_interval = config.Number(
            "Poll Interval (s)",
            description="Interval between status polls",
            default=1.0
        )

        # Alarm thresholds
        self.overcurrent_threshold = config.Number(
            "Overcurrent Threshold (%)",
            description="Current threshold for overcurrent warning (% of nominal)",
            default=110.0
        )
        self.overtemperature_threshold = config.Number(
            "Overtemperature Threshold (C)",
            description="Temperature threshold for overtemperature warning",
            default=80.0
        )

    @property
    def frequency_range(self):
        """Returns the configured frequency range as a tuple."""
        return (self.min_frequency.value, self.max_frequency.value)


def export():
    """Export configuration schema to doover_config.json."""
    SchniederVsdConfig().export(
        Path(__file__).parents[2] / "doover_config.json",
        "schnieder_vsd"
    )


if __name__ == "__main__":
    export()
