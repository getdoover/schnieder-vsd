"""Schneider VSD Control Application.

This application provides monitoring and control of Schneider Altivar
Variable Speed Drives via Modbus TCP.
"""

import logging
import json
from datetime import datetime

from pydoover.docker import Application
from pydoover import ui

from .app_config import SchniederVsdConfig
from .app_ui import SchniederVsdUI
from .app_state import SchniederVsdState
from .modbus_client import SchneiderVsdClient, VsdStatus

log = logging.getLogger(__name__)


class SchniederVsdApplication(Application):
    """Main application class for Schneider VSD control."""

    config: SchniederVsdConfig
    loop_target_period = 1  # Poll every 1 second

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.ui: SchniederVsdUI = None
        self.state: SchniederVsdState = None
        self.modbus: SchneiderVsdClient = None
        self.last_status: VsdStatus = VsdStatus()
        self.last_comm_time: datetime = None
        self.connection_retry_count = 0
        self.max_connection_retries = 3

    async def setup(self):
        """Initialize the application."""
        # Initialize UI
        self.ui = SchniederVsdUI()
        self.ui_manager.add_children(*self.ui.fetch())

        # Set display name from config
        if self.config.display_name.value:
            self.ui_manager.set_display_name(self.config.display_name.value)

        # Initialize state machine
        self.state = SchniederVsdState(self)

        # Initialize Modbus client
        self.modbus = SchneiderVsdClient(
            host=self.config.modbus_host.value,
            port=self.config.modbus_port.value,
            unit_id=self.config.modbus_unit_id.value,
            timeout=self.config.connection_timeout.value
        )

        # Start connection
        await self.state.connect()

        log.info(
            f"Schneider VSD application initialized - "
            f"Host: {self.config.modbus_host.value}:{self.config.modbus_port.value}"
        )

    async def main_loop(self):
        """Main application loop - polls VSD status and updates UI."""
        # Handle connection state
        if self.state.state == "connecting":
            connected = await self.modbus.connect()
            if connected:
                # Configure ramp times on initial connection
                await self.modbus.set_ramp_times(
                    self.config.acceleration_time.value,
                    self.config.deceleration_time.value
                )
                await self.state.connected()
                self.connection_retry_count = 0
            else:
                self.connection_retry_count += 1
                if self.connection_retry_count >= self.max_connection_retries:
                    log.warning("Max connection retries reached")
                    self.connection_retry_count = 0
                # Stay in connecting state, will retry on next loop

        elif self.state.state == "disconnected":
            # Attempt reconnection
            await self.state.connect()

        elif self.state.is_connected:
            # Read VSD status
            status = await self.modbus.read_status()

            if status.connected:
                self.last_status = status
                self.last_comm_time = datetime.now()
                await self._update_from_status(status)
            else:
                # Connection lost
                log.warning("Lost connection to VSD")
                await self.modbus.disconnect()
                await self.state.disconnect()

        # Update UI with current state
        self._update_ui()

        # Persist state to tags
        await self._persist_state()

    async def _update_from_status(self, status: VsdStatus):
        """Update internal state based on VSD status.

        Args:
            status: Current VSD status from Modbus read.
        """
        # Handle state transitions based on VSD status
        if status.faulted and not self.state.is_faulted:
            # VSD has faulted
            self.state.set_fault(
                str(status.fault_code),
                status.fault_description
            )
            await self.state.fault()
            await self.ui.alerts.send_alert(
                f"VSD Fault: {status.fault_description}"
            )

        elif self.state.state == "starting" and status.running:
            # Motor has started
            await self.state.started()

        elif self.state.state == "stopping" and not status.running and status.ready:
            # Motor has stopped
            await self.state.stopped()

        elif self.state.state == "resetting" and not status.faulted and status.ready:
            # Fault has been reset
            await self.state.reset_complete()

        # Check for warning conditions
        overcurrent = status.motor_current > self.config.overcurrent_threshold.value
        overtemp = status.drive_temperature > self.config.overtemperature_threshold.value

        if overcurrent and not self.ui.overcurrent_warning.is_visible:
            await self.ui.alerts.send_alert(
                f"Overcurrent warning: {status.motor_current:.1f}A"
            )
        if overtemp and not self.ui.overtemperature_warning.is_visible:
            await self.ui.alerts.send_alert(
                f"Overtemperature warning: {status.drive_temperature:.0f}C"
            )

        self.ui.update_warnings(overcurrent, overtemp)

    def _update_ui(self):
        """Update all UI elements with current status."""
        status = self.last_status

        # Connection status
        self.ui.update_connection(
            self.state.is_connected,
            self.last_comm_time
        )

        # VSD status
        self.ui.update_status(
            drive_state=self.state.get_state_display(),
            running=status.running,
            ready=status.ready,
            faulted=status.faulted or self.state.is_faulted,
            fault_code=status.fault_description if status.faulted else ""
        )

        # Operating values
        self.ui.update_operating_values(
            frequency=status.output_frequency,
            current=status.motor_current,
            voltage=status.motor_voltage,
            power=status.motor_power,
            temperature=status.drive_temperature,
            dc_bus=status.dc_bus_voltage
        )

    async def _persist_state(self):
        """Persist current state to tags for external access."""
        await self.set_tag("vsd_state", self.state.state)
        await self.set_tag("vsd_running", self.last_status.running)
        await self.set_tag("vsd_frequency", self.last_status.output_frequency)
        await self.set_tag("vsd_current", self.last_status.motor_current)
        await self.set_tag("vsd_faulted", self.last_status.faulted)
        await self.set_tag("vsd_fault_code", self.last_status.fault_code)

        # Publish telemetry data
        telemetry = {
            "timestamp": datetime.now().isoformat(),
            "state": self.state.state,
            "frequency_hz": self.last_status.output_frequency,
            "current_a": self.last_status.motor_current,
            "voltage_v": self.last_status.motor_voltage,
            "power_kw": self.last_status.motor_power,
            "temperature_c": self.last_status.drive_temperature,
            "dc_bus_v": self.last_status.dc_bus_voltage,
            "running": self.last_status.running,
            "faulted": self.last_status.faulted,
        }
        await self.publish_to_channel("vsd_telemetry", json.dumps(telemetry))

    # UI Callbacks

    @ui.callback("start_button")
    async def on_start(self, new_value):
        """Handle start button press."""
        log.info("Start button pressed")
        self.ui.start_button.coerce(None)

        if not self.config.enable_remote_control.value:
            log.warning("Remote control is disabled")
            await self.ui.alerts.send_alert("Remote control is disabled in configuration")
            return

        if not self.state.can_start:
            log.warning(f"Cannot start in state: {self.state.state}")
            return

        if await self.modbus.start():
            await self.state.start()
        else:
            log.error("Failed to send start command")

    @ui.callback("stop_button")
    async def on_stop(self, new_value):
        """Handle stop button press."""
        log.info("Stop button pressed")
        self.ui.stop_button.coerce(None)

        if not self.config.enable_remote_control.value:
            log.warning("Remote control is disabled")
            await self.ui.alerts.send_alert("Remote control is disabled in configuration")
            return

        if not self.state.can_stop:
            log.warning(f"Cannot stop in state: {self.state.state}")
            return

        if await self.modbus.stop():
            await self.state.stop()
        else:
            log.error("Failed to send stop command")

    @ui.callback("reset_fault")
    async def on_reset_fault(self, new_value):
        """Handle fault reset button press."""
        log.info("Reset fault button pressed")
        self.ui.reset_fault.coerce(None)

        if not self.config.enable_remote_control.value:
            log.warning("Remote control is disabled")
            await self.ui.alerts.send_alert("Remote control is disabled in configuration")
            return

        if not self.state.can_reset:
            log.warning(f"Cannot reset in state: {self.state.state}")
            return

        if await self.modbus.reset_fault():
            await self.state.reset()
        else:
            log.error("Failed to send reset command")

    @ui.callback("run_command")
    async def on_run_command(self, new_value):
        """Handle run command state change."""
        log.info(f"Run command changed to: {new_value}")

        if not self.config.enable_remote_control.value:
            log.warning("Remote control is disabled")
            await self.ui.alerts.send_alert("Remote control is disabled in configuration")
            return

        if new_value == "run" and self.state.can_start:
            if await self.modbus.start():
                await self.state.start()
        elif new_value == "stop" and self.state.can_stop:
            if await self.modbus.stop():
                await self.state.stop()

    @ui.callback("frequency_setpoint")
    async def on_frequency_change(self, new_value):
        """Handle frequency setpoint change."""
        log.info(f"Frequency setpoint changed to: {new_value}")

        if not self.config.enable_speed_control.value:
            log.warning("Speed control is disabled")
            await self.ui.alerts.send_alert("Speed control is disabled in configuration")
            return

        if new_value is None:
            return

        # Clamp to configured limits
        min_freq, max_freq = self.config.frequency_range
        frequency = max(min_freq, min(max_freq, float(new_value)))

        if await self.modbus.set_frequency(frequency):
            log.info(f"Frequency set to {frequency} Hz")
        else:
            log.error("Failed to set frequency")
