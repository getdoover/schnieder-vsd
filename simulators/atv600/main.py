#!/usr/bin/env python3
"""ATV600 Modbus TCP Simulator.

Simulates a Schneider Altivar ATV600 VSD for development and testing.
Responds to the same register map that the real app reads/writes.

Usage:
    python main.py                        # defaults: port 5020, slave 1
    python main.py --port 502 --slave-id 2

    SIM_PORT=5020 SIM_SLAVE_ID=1 python main.py

Fault injection:
    Write 1 to holding register 30000 with any Modbus client to inject
    a fault. Write 0 to clear it. Or use --fault-after N to auto-fault
    after N seconds of running.
"""

import argparse
import asyncio
import logging
import os
import struct
import time

from pymodbus.datastore import (
    ModbusDeviceContext,
    ModbusSequentialDataBlock,
    ModbusServerContext,
)
from pymodbus.server import StartAsyncTcpServer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [SIM] %(message)s")
log = logging.getLogger("atv600_sim")

# ---------------------------------------------------------------------------
# Register addresses (must match vsd/atv600.py)
# ---------------------------------------------------------------------------

# Status block (read by app via FC3, 3200-3274)
REG_FREQUENCY = 3202
REG_CURRENT = 3204
REG_VOLTAGE = 3207
REG_POWER = 3208
REG_TEMPERATURE = 3210
REG_STATUS = 3240          # HMIS
REG_MOTOR_TIME_HI = 3244   # uint32 high word
REG_MOTOR_TIME_LO = 3245   # uint32 low word

# I/O block (read by app via FC3, 5200-5249)
REG_DIGITAL_IN = 5202
REG_ANALOG_IN_1 = 5232

# Config block (read by app via FC3, 8400-8524)
REG_CHCF = 8401
REG_RCB = 8412
REG_RF1 = 8413
REG_RF1B = 8415
REG_CCS = 8421
REG_CD1 = 8423
REG_CD2 = 8424

# Control registers (written by app)
REG_CONTROL = 8501
REG_SPEED_SET = 8502

# Setup registers (written by app)
REG_RSF = 7124
REG_BMP = 13529

# Simulation control (not on real hardware)
REG_FAULT_INJECT = 30000   # Write 1 = inject fault, 0 = clear

# HMIS states
HMIS_READY = 2
HMIS_FREEWHEEL = 3
HMIS_RUNNING = 4
HMIS_ACCELERATING = 5
HMIS_DECELERATING = 6
HMIS_FAULT = 23

# Datastore covers 0..30001
DATASTORE_SIZE = 30002


class ATV600Simulator:
    """Simulates ATV600 motor behaviour driven by control register writes."""

    def __init__(self, slave_id: int = 1, fault_after: float | None = None):
        self.slave_id = slave_id
        self.fault_after = fault_after

        # Motor simulation state
        self.hmis = HMIS_READY
        self.target_freq = 0.0       # from speed setpoint register
        self.actual_freq = 0.0       # ramps toward target
        self.temperature = 25.0      # ambient start
        self.motor_seconds = 0       # total motor run time
        self.running = False
        self.run_start_time: float | None = None
        self._prev_ctrl_bit7 = False # for rising-edge fault reset detection
        self._fault_injected = False

        # Build datastore
        values = [0] * DATASTORE_SIZE
        block = ModbusSequentialDataBlock(0, values)
        self.store = ModbusDeviceContext(hr=block, ir=block)
        self.context = ModbusServerContext(
            devices={slave_id: self.store}, single=False,
        )

        # Set initial register values
        self._write(REG_STATUS, HMIS_READY)
        self._write(REG_TEMPERATURE, 25)
        self._write(REG_VOLTAGE, 0)
        # Digital inputs: DI1 low, DI2 low, DI3 low
        self._write(REG_DIGITAL_IN, 0x00)

    # -- Register helpers --------------------------------------------------

    def _read(self, address: int) -> int:
        # datastore getValues returns a list; FC3 = function code 3
        vals = self.store.getValues(3, address, count=1)
        return vals[0]

    def _write(self, address: int, value: int):
        self.store.setValues(3, address, [value & 0xFFFF])

    def _write_uint32(self, address: int, value: int):
        high = (value >> 16) & 0xFFFF
        low = value & 0xFFFF
        self.store.setValues(3, address, [high, low])

    # -- Simulation tick (called every 100 ms) -----------------------------

    def tick(self, dt: float):
        ctrl = self._read(REG_CONTROL)
        run_bit = bool(ctrl & 0x01)
        reset_bit = bool(ctrl & 0x80)

        # Fault injection via register 30000
        fault_inject = self._read(REG_FAULT_INJECT)
        if fault_inject and not self._fault_injected:
            self._fault_injected = True
            self.hmis = HMIS_FAULT
            self.running = False
            self.actual_freq = 0.0
            log.info("FAULT INJECTED via register %d", REG_FAULT_INJECT)

        # Auto fault after N seconds of running
        if (
            self.fault_after
            and self.running
            and self.run_start_time
            and time.time() - self.run_start_time > self.fault_after
        ):
            self._fault_injected = True
            self.hmis = HMIS_FAULT
            self.running = False
            self.actual_freq = 0.0
            self.run_start_time = None
            log.info("AUTO-FAULT after %.0f s of running", self.fault_after)

        # Fault reset: rising edge on bit 7
        if reset_bit and not self._prev_ctrl_bit7 and self.hmis == HMIS_FAULT:
            self.hmis = HMIS_READY
            self._fault_injected = False
            self._write(REG_FAULT_INJECT, 0)
            log.info("FAULT CLEARED")
        self._prev_ctrl_bit7 = reset_bit

        # If faulted, skip motor simulation
        if self.hmis == HMIS_FAULT:
            self._update_registers()
            return

        # Read speed setpoint
        raw_setpoint = self._read(REG_SPEED_SET)
        self.target_freq = raw_setpoint / 10.0

        # Motor state machine
        if run_bit and not self.running:
            # Start command
            self.running = True
            self.run_start_time = time.time()
            self.hmis = HMIS_ACCELERATING
            log.info("MOTOR START (target %.1f Hz)", self.target_freq)

        elif not run_bit and self.running:
            # Stop command
            self.running = False
            self.hmis = HMIS_DECELERATING
            log.info("MOTOR STOP")

        # Frequency ramping
        ramp_rate = 10.0  # Hz per second
        if self.running:
            if self.actual_freq < self.target_freq:
                self.actual_freq = min(
                    self.target_freq, self.actual_freq + ramp_rate * dt,
                )
                self.hmis = HMIS_ACCELERATING if self.actual_freq < self.target_freq else HMIS_RUNNING
            elif self.actual_freq > self.target_freq:
                self.actual_freq = max(
                    self.target_freq, self.actual_freq - ramp_rate * dt,
                )
                self.hmis = HMIS_DECELERATING if self.actual_freq > self.target_freq else HMIS_RUNNING
            else:
                self.hmis = HMIS_RUNNING
        else:
            # Decelerating to stop
            if self.actual_freq > 0:
                self.actual_freq = max(0.0, self.actual_freq - ramp_rate * dt)
                self.hmis = HMIS_DECELERATING
            else:
                self.actual_freq = 0.0
                self.hmis = HMIS_READY

        # Motor run time
        if self.running:
            self.motor_seconds += dt

        # Temperature simulation
        if self.running:
            # Heats up slowly while running (toward ~60°C)
            self.temperature += (60.0 - self.temperature) * 0.001 * dt
        else:
            # Cools down toward ambient (25°C)
            self.temperature += (25.0 - self.temperature) * 0.005 * dt

        self._update_registers()

    def _update_registers(self):
        """Write simulated values back to the register datastore."""
        # Status
        self._write(REG_STATUS, self.hmis)
        self._write(REG_FREQUENCY, int(self.actual_freq * 10))

        # Current proportional to frequency (0.2 A per Hz baseline)
        current = self.actual_freq * 0.2 if self.running else 0.0
        self._write(REG_CURRENT, int(current * 10))  # amps_divisor = 10

        # Voltage: ~400V when running, 0 when stopped
        voltage = 400 if self.actual_freq > 0.5 else 0
        self._write(REG_VOLTAGE, voltage)

        # Power: approximate (V * I * pf / 1000, simplified)
        power_kw = (voltage * current * 0.85 / 1000) if self.running else 0.0
        self._write(REG_POWER, int(power_kw * 10))

        # Temperature
        self._write(REG_TEMPERATURE, int(self.temperature))

        # Motor run time (uint32 seconds)
        self._write_uint32(REG_MOTOR_TIME_HI, int(self.motor_seconds))


async def run_simulation(sim: ATV600Simulator):
    """Background task: tick the simulator every 100 ms."""
    log.info("Simulation loop started")
    last = time.monotonic()
    while True:
        await asyncio.sleep(0.1)
        now = time.monotonic()
        sim.tick(now - last)
        last = now


async def main(port: int, slave_id: int, fault_after: float | None):
    sim = ATV600Simulator(slave_id=slave_id, fault_after=fault_after)

    # Start simulation background task
    asyncio.create_task(run_simulation(sim))

    log.info(
        "ATV600 simulator listening on 0.0.0.0:%d (slave %d)", port, slave_id,
    )
    if fault_after:
        log.info("Will auto-fault after %.0f s of running", fault_after)
    log.info("Write 1 to register %d to inject a fault", REG_FAULT_INJECT)

    await StartAsyncTcpServer(
        context=sim.context,
        address=("0.0.0.0", port),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ATV600 Modbus TCP Simulator")
    parser.add_argument(
        "--port", type=int,
        default=int(os.environ.get("SIM_PORT", "5020")),
        help="TCP port (default 5020)",
    )
    parser.add_argument(
        "--slave-id", type=int,
        default=int(os.environ.get("SIM_SLAVE_ID", "1")),
        help="Modbus slave ID (default 1)",
    )
    parser.add_argument(
        "--fault-after", type=float,
        default=os.environ.get("SIM_FAULT_AFTER"),
        help="Auto-inject fault after N seconds of running",
    )
    args = parser.parse_args()
    asyncio.run(main(args.port, args.slave_id, args.fault_after))
