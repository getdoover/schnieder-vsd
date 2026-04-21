"""Schneider VSD control application."""

import logging

from pydoover import ui
from pydoover.docker import Application

from .app_config import SchneiderVsdConfig
from .app_tags import SchneiderVsdTags
from .app_ui import SchneiderVsdUI
from .vsd import get_vsd_class
from .vsd.base import VsdStatus

log = logging.getLogger(__name__)


class SchneiderVsdApplication(Application):
    config: SchneiderVsdConfig
    tags: SchneiderVsdTags

    config_cls = SchneiderVsdConfig
    tags_cls = SchneiderVsdTags
    ui_cls = SchneiderVsdUI

    loop_target_period = 5

    async def setup(self):
        vsd_class = get_vsd_class(self.config.vsd_type.value)
        self.vsd = vsd_class(
            host=self.config.modbus_host.value,
            port=int(self.config.modbus_port.value),
            slave_id=int(self.config.modbus_unit_id.value),
            amps_divisor=int(self.config.amps_divisor.value),
            max_frequency=self.config.max_frequency.value,
            min_frequency=self.config.min_frequency.value,
        )
        self._setup_done = False
        self._warned_overcurrent = False
        self._warned_overtemperature = False

    def _selected_mode(self) -> str:
        return self.ui_manager.get_value("mode_selector")

    @property
    def _is_terminal_mode(self) -> bool:
        """True when a terminal mode is configured AND currently selected."""
        return (
            bool(self.config.terminal_mode_label.value)
            and self._selected_mode() == "terminal_control"
        )

    @property
    def _remote_control_allowed(self) -> bool:
        """True when the user can issue start/stop/speed commands."""
        # Terminal mode configured → must be in user_control
        if self.config.terminal_mode_label.value:
            return self._selected_mode() == "user_control"
        # No terminal mode configured → always allowed
        return True

    async def main_loop(self):
        # Attempt VSD setup (register configuration) if not done
        if not self._setup_done:
            if await self.vsd.run_setup():
                self._setup_done = True
                log.info("VSD setup complete — starting normal operation")
            else:
                await self._set_disconnected()
                return

        # Poll status
        status = await self.vsd.read_status()
        if not status.contactable:
            await self._set_disconnected()
            self._setup_done = False
            return

        # Push all values to tags
        await self._update_tags(status)

        # Enforce operating mode on the VSD hardware each cycle
        await self._enforce_operating_mode()

        # Periodic VSD management (auto fault recovery when not in terminal mode)
        if not self._is_terminal_mode:
            await self.vsd.manage_operating_state()

        # Warning checks (always active regardless of mode)
        await self._check_warnings(status)

    # ------------------------------------------------------------------
    # Operating mode
    # ------------------------------------------------------------------

    async def _enforce_operating_mode(self):
        """Continuously enforce the selected mode on the VSD hardware.

        In terminal mode the drive is switched to physical terminal control
        (e.g. float switch). In user control mode the drive is put into
        remote-ready-local so it accepts Modbus commands.
        """
        if not self.config.terminal_mode_label.value:
            return  # No mode switching configured

        if not self.vsd.is_contactable:
            return

        if self._is_terminal_mode:
            await self.vsd.set_operating_mode("terminal")
        else:
            await self.vsd.set_operating_mode("local")

    # ------------------------------------------------------------------
    # Tag updates
    # ------------------------------------------------------------------

    async def _update_tags(self, status: VsdStatus):
        await self.tags.comms_active.set(True)
        await self.tags.vsd_state.set(status.hmis_name)
        await self.tags.vsd_running.set(status.is_running)
        await self.tags.vsd_faulted.set(status.is_faulted)
        await self.tags.vsd_fault_code.set(
            status.fault_code if status.is_faulted else None,
        )
        await self.tags.vsd_fault_description.set(
            status.fault_description if status.is_faulted else None,
        )
        await self.tags.vsd_frequency.set(status.frequency_hz)
        await self.tags.vsd_current.set(status.current_amps)
        await self.tags.vsd_voltage.set(status.voltage_v)
        await self.tags.vsd_power.set(status.power_kw)
        await self.tags.vsd_temperature.set(status.temperature_c)
        await self.tags.motor_run_hours.set(round(status.motor_run_hours, 1))
        await self.tags.di_1.set(status.di_1)
        await self.tags.di_2.set(status.di_2)
        await self.tags.di_3.set(status.di_3)

        # Dynamic display name
        if status.is_running:
            name = f"{self.app_display_name} - {status.frequency_hz:.1f}Hz"
        elif status.is_faulted:
            name = f"{self.app_display_name} - FAULT"
        else:
            name = self.app_display_name
        await self.tags.app_display_name.set(name)

    async def _set_disconnected(self):
        await self.tags.comms_active.set(False)
        await self.tags.vsd_state.set("disconnected")
        await self.tags.app_display_name.set(
            f"{self.app_display_name} - OFFLINE",
        )

    # ------------------------------------------------------------------
    # Warnings
    # ------------------------------------------------------------------

    async def _check_warnings(self, status: VsdStatus):
        max_amps = self.config.max_amps.value
        oc_threshold = max_amps * (self.config.overcurrent_threshold.value / 100.0)
        ot_threshold = self.config.overtemperature_threshold.value

        if status.current_amps > oc_threshold:
            if not self._warned_overcurrent:
                self._warned_overcurrent = True
                log.warning(
                    "Overcurrent: %.1f A > %.1f A threshold",
                    status.current_amps, oc_threshold,
                )
                await self.create_message("notifications", {
                    "title": "VSD overcurrent",
                    "message": (
                        f"VSD overcurrent: {status.current_amps:.1f}A "
                        f"> {oc_threshold:.1f}A"
                    ),
                    "body": (
                        f"Motor current {status.current_amps:.1f}A exceeds "
                        f"threshold {oc_threshold:.1f}A"
                    ),
                    "severity": "warning",
                })
        else:
            self._warned_overcurrent = False

        if status.temperature_c > ot_threshold:
            if not self._warned_overtemperature:
                self._warned_overtemperature = True
                log.warning(
                    "Overtemperature: %d C > %d C threshold",
                    status.temperature_c, ot_threshold,
                )
                await self.create_message("notifications", {
                    "title": "VSD overtemperature",
                    "message": (
                        f"VSD overtemperature: {status.temperature_c}°C "
                        f"> {ot_threshold}°C"
                    ),
                    "body": (
                        f"Drive temperature {status.temperature_c}°C exceeds "
                        f"threshold {ot_threshold}°C"
                    ),
                    "severity": "warning",
                })
        else:
            self._warned_overtemperature = False

    # ------------------------------------------------------------------
    # UI handlers
    # ------------------------------------------------------------------

    @ui.handler("mode_selector")
    async def on_mode_change(self, ctx, value):
        if value is None:
            return
        label = self.config.terminal_mode_label.value or "Terminal Control"
        if value == "terminal_control":
            log.info("Switching to terminal mode (%s)", label)
        else:
            log.info("Switching to user control")

    @ui.handler("start_button")
    async def on_start(self, ctx, value):
        await ctx.set_value(None)
        if not self._remote_control_allowed:
            log.warning("Start rejected — switch to User Control mode first")
            return
        if not self.vsd.is_contactable:
            log.warning("Start rejected — VSD not contactable")
            return
        log.info("Start command received")
        await self.vsd.start_motor()

    @ui.handler("stop_button")
    async def on_stop(self, ctx, value):
        await ctx.set_value(None)
        if not self._remote_control_allowed:
            log.warning("Stop rejected — switch to User Control mode first")
            return
        if not self.vsd.is_contactable:
            log.warning("Stop rejected — VSD not contactable")
            return
        log.info("Stop command received")
        await self.vsd.stop_motor()

    @ui.handler("reset_fault_button")
    async def on_reset_fault(self, ctx, value):
        await ctx.set_value(None)
        if not self.vsd.is_contactable:
            log.warning("Fault reset rejected — VSD not contactable")
            return
        log.info("Fault reset command received")
        await self.vsd.clear_fault()

    @ui.handler("frequency_setpoint")
    async def on_frequency_change(self, ctx, value):
        if value is None:
            return
        if not self._remote_control_allowed:
            log.warning("Frequency change rejected — switch to User Control mode first")
            return
        if not self.vsd.is_contactable:
            log.warning("Frequency change rejected — VSD not contactable")
            return
        log.info("Frequency setpoint: %.1f Hz", float(value))
        await self.vsd.set_target_freq(float(value))
