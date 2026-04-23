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
            modbus_timeout_seconds=self.config.modbus_timeout_seconds.value,
            stop_on_comms_loss=self.config.stop_on_comms_loss.value,
        )
        self._setup_done = False
        self._warned_overpower = False
        self._warned_overtemperature = False
        # Edge-detection for event notifications. Initialised to None so the
        # first cycle captures state without firing — avoids a phantom
        # "started" on boot with a drive already running.
        self._prev_running: bool | None = None
        self._prev_faulted: bool | None = None

    def _selected_mode(self) -> str | None:
        # Not a @property: pydoover's rpc.register_handlers uses
        # inspect.getmembers, which evaluates @property getters before the
        # UI manager has registered interactions — that raises KeyError.
        try:
            return self.ui_manager.get_value("mode_selector")
        except KeyError:
            return None

    def _is_terminal_mode(self) -> bool:
        """True when a terminal mode is configured AND currently selected."""
        return (
            bool(self.config.terminal_mode_label.value)
            and self._selected_mode() == "terminal_control"
        )

    def _remote_control_allowed(self) -> bool:
        """True when the user can issue start/stop/speed commands."""
        if self.config.terminal_mode_label.value:
            return self._selected_mode() == "user_control"
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

        # Deferred config: if setup came up in read-only mode (drive was
        # running at boot), retry the full config as soon as drive is idle.
        if not self.vsd.config_applied and not status.is_running:
            log.info("Drive now idle — running deferred configuration")
            if await self.vsd.run_setup():
                log.info("Deferred configuration complete")

        # Push all values to tags
        await self._update_tags(status)

        # Enforce operating mode on the VSD hardware each cycle
        await self._enforce_operating_mode()

        # Periodic VSD management (auto fault recovery when not in terminal mode)
        if not self._is_terminal_mode():
            await self.vsd.manage_operating_state()

        # Warning checks (always active regardless of mode)
        await self._check_warnings(status)

        # Event notifications — fire on state transitions if configured
        await self._check_event_notifications(status)

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

        if self._is_terminal_mode():
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
        await self.tags.vsd_voltage.set(status.motor_voltage_v)
        await self.tags.vsd_mains_voltage.set(status.mains_voltage_v)
        # OPR is signed % of motor nominal; translate to kW via configured rating.
        power_kw = status.power_pct / 100.0 * self.config.max_power_kw.value
        await self.tags.vsd_power.set(round(power_kw, 2))
        await self.tags.vsd_power_pct.set(status.power_pct)
        await self.tags.vsd_thermal_load.set(status.thermal_load_pct)
        await self.tags.motor_run_hours.set(round(status.motor_run_hours, 1))
        await self.tags.di_1.set(status.di_1)
        await self.tags.di_2.set(status.di_2)
        await self.tags.di_3.set(status.di_3)
        ai_1, ai_2, ai_3, ai_4, ai_5 = status.ai_values
        await self.tags.ai_1.set(ai_1)
        await self.tags.ai_2.set(ai_2)
        await self.tags.ai_3.set(ai_3)
        await self.tags.ai_4.set(ai_4)
        await self.tags.ai_5.set(ai_5)

        await self.tags.app_display_name.set(
            f"{self.app_display_name} : {self._state_label(status)}"
        )
        await self._update_ui_visibility(status)

    async def _set_disconnected(self):
        await self.tags.comms_active.set(False)
        await self.tags.vsd_state.set("disconnected")
        await self.tags.app_display_name.set(
            f"{self.app_display_name} : {self._state_label(None)}"
        )
        await self._update_ui_visibility(None)

    @staticmethod
    def _state_label(status: VsdStatus | None) -> str:
        if status is None or not status.contactable:
            return "No Comms"
        return status.hmis_name.replace("_", " ").title()

    async def _update_ui_visibility(self, status: VsdStatus | None) -> None:
        """Drive conditional UI visibility via tag-backed resolvers.

        Element.hidden is bound to $tag.app().hide_<name> in app_ui.py — the
        schema is only published once at setup, so we can't mutate element
        attributes at runtime. Tag writes re-render each cycle.
        """
        contactable = status is not None and status.contactable
        in_terminals = self._is_terminal_mode()
        is_running = contactable and status.is_running
        is_faulted = contactable and status.is_faulted
        # Drive is running but the remote-mode latch isn't asserted — it
        # was started locally (HMI/terminal). Frequency setpoint writes
        # would be no-ops in this state; hide the input and surface a
        # warning instead.
        started_locally = (
            is_running and not status.remote_channel_active
        )

        await self.tags.hide_frequency_setpoint.set(
            in_terminals or not contactable or started_locally
        )
        await self.tags.hide_start_button.set(
            in_terminals or is_running or not contactable
        )
        await self.tags.hide_stop_button.set(
            in_terminals or not is_running or not contactable
        )
        await self.tags.hide_reset_fault_button.set(not is_faulted)

        await self.tags.hide_no_comms_warning.set(contactable)
        await self.tags.hide_motor_fault_warning.set(not is_faulted)
        await self.tags.hide_local_run_warning.set(not started_locally)
        if is_faulted:
            fault_desc = (status.fault_description or "").strip()
            label = f"Motor Fault: {fault_desc}" if fault_desc else "Motor Fault"
            await self.tags.motor_fault_label.set(label)

    # ------------------------------------------------------------------
    # Warnings
    # ------------------------------------------------------------------

    async def _check_warnings(self, status: VsdStatus):
        max_kw = self.config.max_power_kw.value
        op_threshold = max_kw * (self.config.overpower_threshold.value / 100.0)
        ot_threshold = self.config.overtemperature_threshold.value
        power_kw = status.power_pct / 100.0 * max_kw

        if power_kw > op_threshold:
            if not self._warned_overpower:
                self._warned_overpower = True
                log.warning(
                    "Motor overload: %.1f kW > %.1f kW threshold",
                    power_kw, op_threshold,
                )
                await self.create_message("notifications", {
                    "title": "VSD high motor load",
                    "message": (
                        f"VSD high motor load: {power_kw:.1f}kW "
                        f"> {op_threshold:.1f}kW"
                    ),
                    "body": (
                        f"Motor power {power_kw:.1f}kW exceeds "
                        f"threshold {op_threshold:.1f}kW"
                    ),
                    "severity": "warning",
                })
        else:
            self._warned_overpower = False

        if status.thermal_load_pct > ot_threshold:
            if not self._warned_overtemperature:
                self._warned_overtemperature = True
                log.warning(
                    "Drive thermal load: %d%% > %d%% threshold",
                    status.thermal_load_pct, ot_threshold,
                )
                await self.create_message("notifications", {
                    "title": "VSD high thermal load",
                    "message": (
                        f"VSD high thermal load: {status.thermal_load_pct}% "
                        f"> {ot_threshold}%"
                    ),
                    "body": (
                        f"Drive thermal load {status.thermal_load_pct}% "
                        f"exceeds threshold {ot_threshold}%"
                    ),
                    "severity": "warning",
                })
        else:
            self._warned_overtemperature = False

    async def _check_event_notifications(self, status: VsdStatus):
        """Post notifications on state transitions (started/stopped/fault).

        Skipped on the very first cycle — we record the state so later
        comparisons detect real edges, not the boot-time snapshot.
        """
        is_running = bool(status.is_running)
        is_faulted = bool(status.is_faulted)
        notif = self.config.notifications
        name = self.app_display_name

        if self._prev_running is not None:
            if is_running and not self._prev_running and notif.on_start.value:
                await self.create_message("notifications", {
                    "title": f"{name} started",
                    "message": f"{name} motor started",
                    "body": f"Motor started at {status.frequency_hz:.1f} Hz",
                    "severity": "info",
                })
            elif not is_running and self._prev_running and notif.on_stop.value:
                await self.create_message("notifications", {
                    "title": f"{name} stopped",
                    "message": f"{name} motor stopped",
                    "body": "Motor stopped",
                    "severity": "info",
                })

        if self._prev_faulted is not None:
            if is_faulted and not self._prev_faulted and notif.on_fault.value:
                fault_desc = (status.fault_description or "").strip() or "Unknown fault"
                await self.create_message("notifications", {
                    "title": f"{name} fault",
                    "message": f"{name} fault: {fault_desc}",
                    "body": f"Drive faulted: {fault_desc}",
                    "severity": "error",
                })

        self._prev_running = is_running
        self._prev_faulted = is_faulted

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
        if not self._remote_control_allowed():
            log.warning("Start rejected — switch to User Control mode first")
            return
        if not self.vsd.is_contactable:
            log.warning("Start rejected — VSD not contactable")
            return
        # Push the speed setpoint to the drive before asserting RUN — otherwise
        # the drive sits in HMIS=2 (ready) with RUN latched but no reference.
        setpoint = self.ui_manager.get_value("frequency_setpoint")
        try:
            setpoint = float(setpoint) if setpoint is not None else 0.0
        except (TypeError, ValueError):
            setpoint = 0.0
        if setpoint <= 0:
            setpoint = self.config.max_frequency.value
            log.info("Frequency setpoint unset; defaulting to %.1f Hz", setpoint)
        await self.vsd.set_target_freq(setpoint)
        log.info("Start command received")
        await self.vsd.start_motor()

    @ui.handler("stop_button")
    async def on_stop(self, ctx, value):
        await ctx.set_value(None)
        if not self._remote_control_allowed():
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
        if not self._remote_control_allowed():
            log.warning("Frequency change rejected — switch to User Control mode first")
            return
        if not self.vsd.is_contactable:
            log.warning("Frequency change rejected — VSD not contactable")
            return
        log.info("Frequency setpoint: %.1f Hz", float(value))
        await self.vsd.set_target_freq(float(value))
