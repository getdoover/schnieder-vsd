# Schneider VSD

<img src="https://companieslogo.com/img/orig/SU.PA-45fa0b74.svg" alt="Schneider Electric Logo" style="max-width: 100px;">

**Monitor and control Schneider Altivar Variable Speed Drives via Modbus TCP**

[![Version](https://img.shields.io/badge/version-0.1.0-blue.svg)](https://github.com/getdoover/schnieder-vsd)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/getdoover/schnieder-vsd/blob/main/LICENSE)

[Getting Started](#getting-started) | [Configuration](#configuration) | [Developer](https://github.com/getdoover/schnieder-vsd/blob/main/DEVELOPMENT.md) | [Need Help?](#need-help)

<br/>

## Overview

The Schneider VSD application provides comprehensive monitoring and control capabilities for Schneider Altivar series Variable Speed Drives (VSDs) through Modbus TCP communication. This device application enables remote visibility into drive operations and, when enabled, allows operators to control the VSD from the Doover platform.

VSDs are critical components in industrial environments, controlling motor speed to optimize energy consumption and process control. This application bridges Schneider Altivar drives to the Doover IoT platform, providing real-time telemetry, status monitoring, and remote control capabilities. The application supports the ATV320 and ATV340 series drives with their standard Modbus register map.

With configurable safety controls, operators can choose to enable or disable remote start/stop and speed control features. The application also provides warning alerts for overcurrent and overtemperature conditions, helping to prevent equipment damage and unplanned downtime.

### Features

- **Real-time Status Monitoring** - View drive state, running status, ready state, and fault conditions
- **Operating Values Display** - Monitor output frequency, motor current, voltage, power, temperature, and DC bus voltage
- **Remote Start/Stop Control** - Start and stop the motor remotely (when enabled in configuration)
- **Frequency Setpoint Control** - Adjust motor speed remotely (when enabled in configuration)
- **Fault Management** - View fault codes with descriptions and reset faults remotely
- **Warning Alerts** - Automatic alerts for overcurrent and overtemperature conditions
- **Telemetry Publishing** - Continuous telemetry data stream for historical analysis
- **State Machine Management** - Robust connection and operation state handling with automatic reconnection

<br/>

## Getting Started

### Prerequisites

1. **Schneider Altivar VSD** - A compatible Schneider Altivar VSD (ATV320 or ATV340 series) with Modbus TCP enabled
2. **Network Connectivity** - The Doover device must be able to reach the VSD on the configured IP address and port
3. **Modbus TCP Gateway** - Either a built-in Ethernet port on the VSD or an external Modbus TCP gateway
4. **VSD Configuration** - The VSD must be configured to accept Modbus commands (refer to VSD manual for COM protocol settings)

### Installation

1. Add the Schneider VSD app to your Doover device through the Doover platform
2. Configure the Modbus connection settings (IP address, port, unit ID)
3. Set operational limits and safety settings as required
4. Deploy the configuration to the device

### Quick Start

1. Ensure the VSD is powered on and connected to the network
2. Add the app to your Doover device and configure the **Modbus Host** with the VSD's IP address
3. Leave other settings at defaults for initial testing
4. Deploy and verify the connection status shows "Connected"
5. View real-time operating values in the UI
6. To enable control, set **Enable Remote Control** to `true` and redeploy

<br/>

## Configuration

| Setting | Description | Default |
|---------|-------------|---------|
| **Display Name** | Name shown in the UI for this VSD | Schneider VSD |
| **Modbus Host** | IP address or hostname of the Modbus TCP gateway | 192.168.1.100 |
| **Modbus Port** | Modbus TCP port (standard is 502) | 502 |
| **Modbus Unit ID** | Modbus slave/unit ID of the VSD | 1 |
| **Connection Timeout** | Timeout for Modbus connection in seconds | 5.0 |
| **Maximum Frequency (Hz)** | Maximum allowed frequency setpoint | 50.0 |
| **Minimum Frequency (Hz)** | Minimum allowed frequency setpoint | 0.0 |
| **Acceleration Time (s)** | Time to accelerate from 0 to max frequency | 10.0 |
| **Deceleration Time (s)** | Time to decelerate from max frequency to 0 | 10.0 |
| **Enable Remote Control** | Allow remote start/stop commands | false |
| **Enable Speed Control** | Allow remote frequency/speed changes | false |
| **Poll Interval (s)** | Interval between status polls | 1.0 |
| **Overcurrent Threshold (%)** | Current threshold for overcurrent warning (% of nominal) | 110.0 |
| **Overtemperature Threshold (C)** | Temperature threshold for overtemperature warning | 80.0 |

### Safety Settings

The application includes two important safety flags that are **disabled by default**:

- **Enable Remote Control** - Must be set to `true` to allow start/stop commands from the UI
- **Enable Speed Control** - Must be set to `true` to allow frequency setpoint changes from the UI

This ensures that remote control is an explicit, conscious decision by the operator.

### Example Configuration

```json
{
  "display_name": "Pump 1 VSD",
  "modbus_host": "192.168.10.50",
  "modbus_port": 502,
  "modbus_unit_id": 1,
  "connection_timeout": 5.0,
  "maximum_frequency_(hz)": 50.0,
  "minimum_frequency_(hz)": 10.0,
  "acceleration_time_(s)": 15.0,
  "deceleration_time_(s)": 20.0,
  "enable_remote_control": true,
  "enable_speed_control": true,
  "poll_interval_(s)": 1.0,
  "overcurrent_threshold_(%)": 105.0,
  "overtemperature_threshold_(c)": 75.0
}
```

<br/>

## UI Elements

This application provides a comprehensive user interface for monitoring and controlling the VSD.

### Variables (Display)

| Element | Description |
|---------|-------------|
| **Connection Status** | Current connection state (Connected/Disconnected) |
| **Last Communication** | Timestamp of last successful communication |
| **Drive State** | Current state of the drive (Idle, Running, Starting, Stopping, Faulted, etc.) |
| **Running** | Boolean indicator showing if motor is running |
| **Ready** | Boolean indicator showing if drive is ready to start |
| **Faulted** | Boolean indicator showing if drive has an active fault |
| **Fault Code** | Description of current fault (if any) |
| **Output Frequency** | Current motor frequency in Hz (color-coded: blue 0-10, green 10-50, red 50-60) |
| **Motor Current** | Current draw in Amps (color-coded: green 0-100, yellow 100-120, red 120+) |
| **Motor Voltage** | Motor voltage in Volts |
| **Motor Power** | Power consumption in kW |
| **Drive Temperature** | Internal drive temperature in Celsius (color-coded: green 0-60, yellow 60-80, red 80+) |
| **DC Bus Voltage** | DC bus voltage in Volts |

### Parameters (User Input)

| Element | Description |
|---------|-------------|
| **Frequency Setpoint (Hz)** | Target frequency for the motor (requires Enable Speed Control) |

### Actions (Buttons)

| Element | Description |
|---------|-------------|
| **Start** | Start the motor (green button, requires Enable Remote Control) |
| **Stop** | Stop the motor (red button with confirmation, requires Enable Remote Control) |
| **Reset Fault** | Reset an active fault (yellow button with confirmation, requires Enable Remote Control) |

### State Commands

| Element | Description |
|---------|-------------|
| **Run Command** | Toggle between Run and Stop states (requires Enable Remote Control) |

### Warning Indicators

| Element | Description |
|---------|-------------|
| **Overcurrent Warning** | Displayed when motor current exceeds configured threshold |
| **Overtemperature Warning** | Displayed when drive temperature exceeds configured threshold |
| **Communication Lost** | Displayed when connection to VSD is lost |

<br/>

## How It Works

1. **Initialization** - The application initializes the Modbus TCP client with configured host, port, and unit ID settings. It sets up the UI components and state machine.

2. **Connection** - The application attempts to connect to the VSD via Modbus TCP. On successful connection, it configures the acceleration and deceleration ramp times. If connection fails, it retries up to 3 times before waiting for the next loop cycle.

3. **Status Polling** - Every loop cycle (default 1 second), the application reads status registers from the VSD including the status word, operating values (frequency, current, voltage, power, temperature), and fault codes.

4. **State Management** - Based on the status read, the application manages state transitions (connecting, idle, running, starting, stopping, faulted, resetting). It detects fault conditions and transitions appropriately.

5. **UI Updates** - The UI is updated with current values, connection status, warnings, and state information. Color-coded ranges provide at-a-glance status indication.

6. **Telemetry Publishing** - Operating data is published to the `vsd_telemetry` channel as JSON for historical tracking and external integrations. Tags are also updated for external access.

7. **Control Handling** - When control buttons are pressed (if enabled), the application sends appropriate Modbus commands to the VSD and manages state transitions accordingly.

<br/>

## Tags

The application publishes the following tags for external access:

| Tag | Description |
|-----|-------------|
| **vsd_state** | Current state machine state |
| **vsd_running** | Boolean running status |
| **vsd_frequency** | Current output frequency in Hz |
| **vsd_current** | Current motor current in Amps |
| **vsd_faulted** | Boolean fault status |
| **vsd_fault_code** | Numeric fault code |

### Telemetry Channel

The application publishes JSON telemetry to the `vsd_telemetry` channel with the following structure:

```json
{
  "timestamp": "2024-01-15T10:30:00.000Z",
  "state": "running",
  "frequency_hz": 45.0,
  "current_a": 12.5,
  "voltage_v": 400,
  "power_kw": 5.5,
  "temperature_c": 45,
  "dc_bus_v": 580,
  "running": true,
  "faulted": false
}
```

<br/>

## Integrations

This application works with:

- **Schneider Altivar ATV320 Series** - Entry-level VSDs with Modbus TCP option
- **Schneider Altivar ATV340 Series** - Advanced VSDs with built-in Ethernet/Modbus TCP
- **Modbus TCP Gateways** - For VSDs with RS-485 Modbus RTU, use a gateway to convert to TCP
- **Doover Dashboards** - View VSD data on custom dashboards
- **Doover Alerts** - Receive notifications for faults and warnings
- **External Systems** - Subscribe to the `vsd_telemetry` channel for integration with other systems

<br/>

## Need Help?

- Email: support@doover.com
- [Doover Documentation](https://docs.doover.com)
- [App Developer Documentation](https://github.com/getdoover/schnieder-vsd/blob/main/DEVELOPMENT.md)

<br/>

## Version History

### v0.1.0 (Current)
- Initial release
- Modbus TCP communication with Schneider Altivar VSDs
- Real-time status monitoring (frequency, current, voltage, power, temperature)
- State machine for connection and operation management
- Remote start/stop/reset control with safety flags
- Frequency setpoint control with configurable limits
- Overcurrent and overtemperature warning alerts
- Telemetry publishing to channels
- Comprehensive UI with status display, operating values, and control buttons

<br/>

## License

This app is licensed under the [Apache License 2.0](https://github.com/getdoover/schnieder-vsd/blob/main/LICENSE).
