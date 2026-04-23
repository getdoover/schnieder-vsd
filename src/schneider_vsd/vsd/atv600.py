"""Schneider Altivar ATV600 VSD implementation.

Register map, command sequences, and status parsing ported from the
proven vsd_control driver that has been running reliably across
multiple ATV600 deployments.

Register addresses/scaling cross-checked against
`Edited - ATV600_Communication_parameters_EAV64332_V3.7.xlsx`.
"""

import asyncio
import logging
import time

from ..modbus_client import ModbusTcpConnection, reg_int16, reg_uint16, reg_uint32
from .base import VsdBase, VsdStatus

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Register addresses (0-based Modbus)
# ---------------------------------------------------------------------------

# Status block — batch read 3200..3274 (75 regs, FC3)
REG_FREQUENCY = 3202        # RFR — output frequency, 0.1 Hz
REG_CURRENT = 3204          # LCR — motor current, raw / amps_divisor = A
REG_MAINS_VOLTAGE = 3207    # ULN — mains voltage, 0.1 V
REG_MOTOR_VOLTAGE = 3208    # UOP — motor voltage, 1 V
REG_THERMAL_LOAD = 3209     # THD — drive thermal state, 1 % (100% = nominal)
REG_POWER_PCT = 3211        # OPR — motor power, 1 % (signed, % of nominal)
REG_STATUS = 3240           # HMIS — device state enumeration
REG_MOTOR_TIME = 3244       # RTH — motor run time, uint32 seconds

# I/O block — batch read 5200..5249 (50 regs, FC3)
REG_DIGITAL_IN = 5202       # IL1R — logic inputs (bit0=DI1, bit1=DI2, ...)
REG_AI1_PHYSICAL = 5242     # AI1C..AI5C — physical (scaled) values at 5242..5246

# Config block — batch read 8400..8524 (125 regs, FC3) [unused, retained for parity]
REG_CHCF = 8401             # I/O control mode
REG_RCB = 8412              # Reference frequency switching (can't change while running)
REG_RF1 = 8413              # Reference frequency 1 source
REG_RF1B = 8415             # Reference frequency 1B source
REG_CCS = 8421              # Command channel switching (can't change while running)
REG_CD1 = 8423              # Command word 1 source
REG_CD2 = 8424              # Command word 2 source

# Control registers
REG_CONTROL = 8501          # CMD control word
REG_SPEED_SET = 8502        # Speed setpoint, Hz * 10

# Setup-only registers
REG_RSF = 7124              # Fault reset assignment
REG_TTO = 6005              # Modbus timeout, 0.1 s units (max 300 = 30 s)
REG_ETHL = 7021             # Ethernet error response (0=Ignore, 1=Freewheel)
REG_BMP = 13529             # BMP — disable local-only mode lockout

# Diagnostic — single-register read outside the batched blocks
REG_LFT = 7121              # LFT — last error occurred (only read when faulted)

NUM_ANALOG_INPUTS = 5       # AI1..AI5


# ---------------------------------------------------------------------------
# HMIS status word values
# ---------------------------------------------------------------------------

HMIS_STATES = {
    0: "tuning",
    1: "dc_braking",
    2: "ready",
    3: "freewheel",
    4: "running",
    5: "accelerating",
    6: "decelerating",
    7: "current_limit",
    8: "fast_stop",
    11: "no_mains",
    13: "ctrl_stop",
    14: "dec_adapt",
    15: "output_cut",
    17: "undervoltage",
    18: "tc_mode",
    23: "fault",
    30: "sto",
    35: "idle",
}

HMIS_ERROR_STATES = {7, 11, 15, 17, 20, 23, 36}
HMIS_RUNNING_STATES = {4, 5, 6}

FAULT_CODES = {
    0: "No fault",
    2: "Overcurrent",
    3: "Overvoltage",
    4: "Undervoltage",
    5: "Overtemperature",
    6: "Motor overload",
    7: "External fault",
    8: "Ground fault",
    9: "Phase loss",
    10: "Communication loss",
    17: "Internal communication",
    18: "Encoder fault",
    24: "Input phase loss",
    25: "DC bus overvoltage",
    30: "IGBT overtemperature",
    38: "Underload",
    39: "Overload",
    51: "EEPROM fault",
    64: "Motor short circuit",
    71: "Brake fault",
    96: "Unknown fault",
}


class ATV600(VsdBase):
    """Schneider Altivar ATV600 series VSD driver."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._last_target_freq: float | None = None
        self._config_applied: bool = False
        # Tracks whether CMD bits 1+2 (remote-mode latch) are currently
        # asserted. While True, the drive ignores HMI/terminal commands —
        # we clear the latch once the drive is safely idle so the panel
        # can initiate the next start. Fire-once-per-stop via this flag to
        # avoid EEPROM wear on repeated R/WS writes.
        self._remote_latched: bool | None = None

    @property
    def config_applied(self) -> bool:
        """True once the R/WS config writes have successfully landed.

        False when setup was skipped (e.g. drive running at container
        boot). Callers should re-invoke run_setup once the drive goes
        idle to complete the deferred config.
        """
        return self._config_applied

    def _conn(self) -> ModbusTcpConnection:
        return ModbusTcpConnection(self.host, self.port, self.slave_id, self.timeout)

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    async def run_setup(self) -> bool:
        """Configure the ATV600 for remote Ethernet control.

        Writes configuration registers for:
        - BMP: disable local-only mode lockout
        - RSF: fault reset via Embedded Ethernet
        - CHCF: I/O control mode
        - RCB: reference freq switching via Embedded Ethernet
        - CCS: command channel switching via Embedded Ethernet
        - TTO: Modbus TCP timeout (keeps drive running across short comms
          gaps like container restarts)
        - ETHL: Ethernet error response (freewheel vs ignore)

        Then sets remote-ready-local as default operating mode.
        If the drive is faulted, attempts to clear the fault.

        If the drive is already running when setup runs (e.g. container
        restart mid-run), the R/WS config writes are skipped — they'd
        return SLAVE_DEVICE_FAILURE (ex 4) and we don't want the log spam.
        The drive keeps its previous EEPROM-persisted config, so we just
        mark contactable and exit. `config_applied` stays False so the
        caller can re-run setup once the drive next goes idle.
        """
        try:
            status = await self.read_status()
            if not status.contactable:
                return False

            if status.is_running:
                log.info(
                    "ATV600 already running at startup (%s:%d) — skipping "
                    "config writes. Config will be re-applied when drive "
                    "next goes idle.",
                    self.host, self.port,
                )
                self._contactable = True
                return True

            # Cap TTO at 30 s (drive limit); unit is 0.1 s.
            tto_ticks = max(1, min(300, int(self.modbus_timeout_seconds * 10)))
            ethl_value = 1 if self.stop_on_comms_loss else 0

            async with self._conn() as conn:
                # Base config — RCB/CCS/RF1*/CD* can't be changed while running
                ok = all([
                    await conn.write_register(REG_BMP, 2),
                    await conn.write_register(REG_RSF, 247),
                    await conn.write_register(REG_CHCF, 3),
                    await conn.write_register(REG_RCB, 241),
                    await conn.write_register(REG_CCS, 242),
                    await conn.write_register(REG_TTO, tto_ticks),
                    await conn.write_register(REG_ETHL, ethl_value),
                ])
                if not ok:
                    log.error("Failed to write base configuration registers")
                    return False

            await asyncio.sleep(0.5)
            if not await self._set_remote_ready_local():
                log.error("Failed to apply remote-ready-local during setup")
                return False
            await asyncio.sleep(0.5)

            # If faulted, try to clear
            status = await self.read_status()
            if status.contactable and status.is_faulted:
                log.info("Drive faulted during setup — clearing")
                await self._switch_to_remote()
                await asyncio.sleep(0.2)
                await self.clear_fault()
                await asyncio.sleep(0.5)
                if not await self._set_remote_ready_local():
                    log.error("Failed to restore remote-ready-local after fault clear")
                    return False

            self._contactable = True
            self._config_applied = True
            log.info(
                "ATV600 setup complete (%s:%d) — TTO=%.1fs, ETHL=%d",
                self.host, self.port, tto_ticks / 10.0, ethl_value,
            )
            return True

        except Exception as e:
            log.error("ATV600 setup failed: %s", e)
            self._contactable = False
            return False

    # ------------------------------------------------------------------
    # Status reading
    # ------------------------------------------------------------------

    async def read_status(self) -> VsdStatus:
        """Read status, I/O, and config registers.

        Three batch reads per the proven polling pattern:
          1. Status block  3200-3274  (75 regs)
          2. I/O block     5200-5249  (50 regs)
          3. Config block  8400-8524  (125 regs)

        When HMIS indicates fault, an additional single read of LFT (7121)
        is issued to resolve the fault code.

        All via FC3 (read holding registers).
        """
        status = VsdStatus()
        try:
            async with self._conn() as conn:
                status_regs = await conn.read_holding_registers(3200, 75)
                if status_regs is None:
                    self._contactable = False
                    return status

                io_regs = await conn.read_holding_registers(5200, 50)
                # Config block — retained from vsd_control for behavioural
                # parity. We parse CMD out of it (8501) to tell whether the
                # remote-mode latch is currently asserted (i.e. whether our
                # Ethernet channel is actively commanding the drive).
                config_regs = await conn.read_holding_registers(8400, 125)

                # Only pay for the LFT read when the drive is signalling a fault.
                fault_reg = None
                hmis_peek = reg_uint16(status_regs, REG_STATUS - 3200)
                if hmis_peek == 23:
                    fault_reg = await conn.read_holding_registers(REG_LFT, 1)

            self._contactable = True
            status.contactable = True

            # --- Parse status block (offsets relative to base 3200) ---
            hmis = reg_uint16(status_regs, REG_STATUS - 3200)
            status.hmis_state = hmis
            status.hmis_name = HMIS_STATES.get(hmis, f"unknown_{hmis}")
            status.is_running = hmis in HMIS_RUNNING_STATES
            status.is_faulted = hmis == 23
            status.is_warning = hmis in HMIS_ERROR_STATES and hmis != 23
            status.is_ready = hmis == 2

            status.frequency_hz = reg_uint16(status_regs, REG_FREQUENCY - 3200) / 10.0
            status.current_amps = reg_uint16(status_regs, REG_CURRENT - 3200) / self.amps_divisor
            status.mains_voltage_v = reg_uint16(status_regs, REG_MAINS_VOLTAGE - 3200) / 10.0
            status.motor_voltage_v = reg_uint16(status_regs, REG_MOTOR_VOLTAGE - 3200)
            status.thermal_load_pct = reg_uint16(status_regs, REG_THERMAL_LOAD - 3200)
            status.power_pct = reg_int16(status_regs, REG_POWER_PCT - 3200)
            status.motor_run_hours = round(
                reg_uint32(status_regs, REG_MOTOR_TIME - 3200) / 3600.0, 2
            )

            # --- Parse I/O block ---
            if io_regs is not None:
                di = reg_uint16(io_regs, REG_DIGITAL_IN - 5200)
                status.di_1 = bool(di & 0x01)
                status.di_2 = bool(di & 0x02)
                status.di_3 = bool(di & 0x04)
                # AI1C..AI5C — physical values (scaled per drive config)
                status.ai_values = [
                    reg_int16(io_regs, (REG_AI1_PHYSICAL - 5200) + i)
                    for i in range(NUM_ANALOG_INPUTS)
                ]

            # --- Parse control word ---
            if config_regs is not None:
                cw = reg_uint16(config_regs, REG_CONTROL - 8400)
                status.control_word = cw
                # Bits 1+2 are the remote-mode latch under CCS=242/CHCF=3.
                # When set, the drive is listening to our Ethernet CMD and
                # LFR. When clear, it's following its local command source
                # (terminals / HMI).
                status.remote_channel_active = bool(cw & 0b0110)

            # --- Fault code ---
            if fault_reg:
                code = fault_reg[0]
                status.fault_code = code
                status.fault_description = FAULT_CODES.get(code, f"Fault code {code}")

            self._last_status = status
            return status

        except Exception as e:
            log.error("Failed to read ATV600 status: %s", e)
            self._contactable = False
            return status

    # ------------------------------------------------------------------
    # Motor control
    # ------------------------------------------------------------------

    async def start_motor(self) -> bool:
        """Start the motor with the proven two-step control word sequence.

        1. Wait 2 s for other commands to settle
        2. Switch to remote control mode
        3. Write 6 (bits 1+2: remote mode, no run)
        4. Write 7 (bits 0+1+2: remote mode + run)
        """
        try:
            # Drain any pending commands before issuing the start sequence —
            # retained from vsd_control. Blocks the main loop briefly; fine
            # because the 5 s loop period gives ample headroom.
            await asyncio.sleep(2)
            await self._switch_to_remote()
            await asyncio.sleep(0.2)

            async with self._conn() as conn:
                if not await conn.write_register(REG_CONTROL, 6):
                    return False
                await asyncio.sleep(0.2)
                if not await conn.write_register(REG_CONTROL, 7):
                    return False

            self._last_start_time = time.time()
            log.info("ATV600 start command sent")
            return True

        except Exception as e:
            log.error("Failed to start ATV600: %s", e)
            return False

    async def stop_motor(self) -> bool:
        """Stop the motor via atomic takeover-and-stop.

        Writes CMD=6 (0b00000110): bits 1+2 set = remote-mode latch, bit 0
        clear = no run. This single atomic write takes control of the
        drive's command channel AND clears the run bit — works whether
        the drive was commanded by HMI, terminal wiring, or remote, so
        operators can shut down manually-started pumps from the app.

        Post-stop mode cleanup (`_set_remote_ready_local`) is handled by
        `manage_operating_state` once the drive reaches idle — we don't
        call it here because it writes R/WS registers that are rejected
        while the motor is still decelerating.
        """
        try:
            async with self._conn() as conn:
                if not await conn.write_register(REG_CONTROL, 6):
                    return False
            self._remote_latched = True
            log.info("ATV600 stop command sent")
            return True

        except Exception as e:
            log.error("Failed to stop ATV600: %s", e)
            return False

    async def set_target_freq(self, frequency_hz: float) -> bool:
        """Set speed reference frequency (clamped to configured range).

        LFR (8502) is R/W and accepts writes at any time. The drive only
        *uses* it as the active reference when the remote-mode latch is
        asserted (bits 1+2 of CMD) — during a remote run, or right after
        `_switch_to_remote` is called from `start_motor` or `stop_motor`.
        Writing LFR here without asserting the latch avoids an idle →
        remote → ready-local cycle every time the operator tweaks the
        setpoint, which would needlessly wear the R/WS source-assignment
        registers (RF1B, CD2, RF1, CD1).
        """
        frequency_hz = max(self.min_frequency, min(self.max_frequency, frequency_hz))
        register_value = int(frequency_hz * 10)

        try:
            async with self._conn() as conn:
                if not await conn.write_register(REG_SPEED_SET, register_value):
                    return False

            self._last_target_freq = frequency_hz
            log.info("ATV600 frequency set to %.1f Hz", frequency_hz)
            return True

        except Exception as e:
            log.error("Failed to set ATV600 frequency: %s", e)
            return False

    async def clear_fault(self) -> bool:
        """Clear fault via rising-edge trigger on bit 7 of control word.

        Bits 1+2 must stay asserted across the pulse — they're the remote-mode
        latch under this drive's I/O profile (CHCF=3). Dropping them puts the
        drive out of remote config and the fault reset is ignored.

        Sequence:
            6   (0b0000_0110) — prep: bits 1+2 set, bit 7 clear
            134 (0b1000_0110) — rising edge: bits 1+2 set, bit 7 set
            6   (0b0000_0110) — drop bit 7 so the next reset also sees a rising edge

        An earlier version wrote literal 0 then 128, clobbering bits 1+2 —
        the drive never actually cleared (fault kept re-arming on the next
        HMIS read). An even earlier RMW-bit version worked because it
        preserved 1+2 incidentally.
        """
        try:
            async with self._conn() as conn:
                if not await conn.write_register(REG_CONTROL, 6):
                    return False
                await asyncio.sleep(0.2)
                if not await conn.write_register(REG_CONTROL, 134):
                    return False
                await asyncio.sleep(0.2)
                if not await conn.write_register(REG_CONTROL, 6):
                    return False

            self._last_clear_fault_time = time.time()
            log.info("ATV600 fault reset sent")
            return True

        except Exception as e:
            log.error("Failed to clear ATV600 fault: %s", e)
            return False

    async def set_operating_mode(self, mode: str) -> bool:
        if mode == "remote":
            return await self._switch_to_remote()
        elif mode == "local":
            return await self._set_remote_ready_local()
        elif mode == "terminal":
            return await self._set_terminal_mode()
        else:
            log.error("Unknown operating mode: %s", mode)
            return False

    async def manage_operating_state(self) -> None:
        """Called each loop — handles auto fault recovery and mode maintenance."""
        if self._last_status is None or not self._contactable:
            return

        # Auto fault recovery with 10 s throttle
        if self._last_status.is_faulted:
            if time.time() - self._last_clear_fault_time > 10:
                log.info("Auto-clearing fault")
                await self._switch_to_remote()
                await asyncio.sleep(0.2)
                await self.clear_fault()
                await asyncio.sleep(0.5)
                await self._set_remote_ready_local()

        # Post-idle cleanup: release the CMD bits 1+2 remote-mode latch so
        # the panel HMI / terminal can initiate the next start. Fires once
        # per stop cycle via the _remote_latched flag — avoids repeat R/WS
        # writes to RF1/RF1B/CD1/CD2 and the associated EEPROM wear.
        elif not self._last_status.is_running:
            if (self._remote_latched is not False
                    and self._last_status.hmis_state in (2, 3)
                    and time.time() - self._last_start_time > 2):
                await self._set_remote_ready_local()

    # ------------------------------------------------------------------
    # Internal mode-switching commands
    # ------------------------------------------------------------------

    async def _switch_to_remote(self) -> bool:
        """Switch to remote (Embedded Ethernet) command control.

        Asserts bits 1+2 of CMD — the remote-mode latch under this drive's
        I/O profile (CCS=242, CHCF=3). Bits 1+2 tell the drive to listen to
        CMD2 (the Ethernet command register). CMD itself is R/W so this
        works whether the motor is running or stopped — which lets us take
        control of a drive that was manually started from the HMI or
        terminals.

        RF1B/CD2 source-assignment registers are R/WS (write-when-stopped)
        and get rejected with SLAVE_DEVICE_FAILURE while the motor runs.
        They're persisted in drive EEPROM by our idle setup routine, so
        skipping them mid-run leaves them at the correct values.
        """
        try:
            async with self._conn() as conn:
                if not (self._last_status and self._last_status.is_running):
                    await conn.write_register(REG_RF1B, 171)
                    await conn.write_register(REG_CD2, 40)
                ok = await conn.write_register_bits(
                    REG_CONTROL, bits_to_set=[1, 2],
                )
            if ok:
                self._remote_latched = True
            return ok
        except Exception as e:
            log.error("Failed to switch to remote: %s", e)
            return False

    async def _set_remote_ready_local(self) -> bool:
        """Remote-ready-local: drive is ready for remote but defaults to local HMI.

        RF1/RF1B/CD1/CD2 are R/WS. While the motor runs these writes return
        SLAVE_DEVICE_FAILURE. manage_operating_state re-applies this once
        the drive goes idle, so skipping during run is safe.
        """
        if self._last_status and self._last_status.is_running:
            return True

        try:
            async with self._conn() as conn:
                ok = all([
                    await conn.write_register(REG_RF1, 163),
                    await conn.write_register(REG_RF1B, 171),
                    await conn.write_register(REG_CD1, 3),
                    await conn.write_register(REG_CD2, 40),
                ])
                if not ok:
                    return False
                result = await conn.write_register_bits(
                    REG_CONTROL, bits_to_unset=[1, 2],
                )
            if result:
                self._remote_latched = False
            return result
        except Exception as e:
            log.error("Failed to set remote-ready-local: %s", e)
            return False

    async def _set_terminal_mode(self) -> bool:
        """Switch to terminal (hardwired) control.

        Freewheel state requires going through remote-ready-local first.
        """
        try:
            if self._last_status and self._last_status.hmis_state == 3:
                await self._set_remote_ready_local()
                await asyncio.sleep(0.5)

            async with self._conn() as conn:
                ok = all([
                    await conn.write_register(REG_RF1B, 163),
                    await conn.write_register(REG_CD2, 1),
                ])
                if not ok:
                    return False
                return await conn.write_register(REG_CONTROL, 6)
        except Exception as e:
            log.error("Failed to set terminal mode: %s", e)
            return False
