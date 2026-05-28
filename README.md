# Raspberry Pi Car Cluster HMI

This is the finalized Raspberry Pi 4 car-cluster application. It is built around two live vehicle data sources only:

- Neuwat RS-485 battery packs
- Slider controller CAN bus

## What is included

- Full-screen friendly Tkinter dashboard with the layout you described:
  - Drive centered and most prominent
  - Battery on the left
  - Inverter / motor on the right
  - Odometer / diagnostics at the bottom
  - Separate faults page for fault details
  - Per-pack Neuwat battery diagnostics on the overview and battery pages so each pack can be seen separately
- Background data services for Neuwat RS-485 polling and Slider CAN decoding
- Dummy mode for visual testing right away
- Raspberry Pi `systemd` service starter files for boot launch

## Run it now

### 1. Create a virtual environment if you want one

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Run the live preview with animated data

```powershell
python main.py --demo
```

### 3. Run the zero-data mode

```powershell
python main.py
```

When there is no live data, every metric intentionally falls back to `0`.

## Keyboard shortcuts

- `1` Overview
- `2` Drive
- `3` Battery
- `4` Inverter
- `5` Odometer
- `6` Faults
- `F11` Toggle fullscreen
- `Esc` Exit

## Live data inputs

The HMI supports two battery input modes:

- `stream` mode: newline-delimited JSON or key/value packets on a serial port
- `neuwat` mode: direct RS-485 polling of Neuwat packs using CMD `0x0500` at `4800 8E1`

Drive and inverter data can now come directly from the Slider controller CAN protocol:

- `0x10F8109A`: direction, speed mode, controller RPM, fault code, low-power flag
- `0x10F8108D`: DC bus voltage and controller-reported motor current

The app derives these HMI fields from CAN:

- `Drive speed`: converted from controller RPM using `CLUSTER_CAN_SPEED_SCALE_KPH_PER_RPM`
- `Drive range`: estimated from live battery SoC using `CLUSTER_ESTIMATED_FULL_RANGE_KM`
- `Inverter RPM`: direct from controller RPM
- `Inverter DC bus voltage`: direct from CAN
- `Inverter current`: mapped from the controller current frame into the current slot on the inverter page

Fields that are not published by the confirmed controller CAN frames stay at zero until a documented frame exists for them. That currently includes throttle, regen, inverter temperature, motor temperature, and torque.

### Battery input examples

JSON:

```json
{"soc": 74.5, "pack_voltage": 356.2, "pack_current": 44.1, "pack_power": 15.7, "pack_temp": 31.4}
```

Key/value:

```text
soc=74.5,pack_voltage=356.2,pack_current=44.1,pack_power=15.7,pack_temp=31.4
```

## Raspberry Pi environment variables

### Neuwat battery mode

Use this when the Raspberry Pi is connected directly to the Neuwat RS-485 bus:

```bash
export CLUSTER_BATTERY_PORT=/dev/ttyUSB0
export CLUSTER_BATTERY_PROTOCOL=neuwat
export CLUSTER_BATTERY_BAUD=4800
export CLUSTER_BATTERY_SERIALS=17,22,6,26
export CLUSTER_BATTERY_TIMEOUT_S=0.2
export CLUSTER_BATTERY_POLL_TIMEOUT_S=2.0
export CLUSTER_BATTERY_RETRIES=3
export CLUSTER_BATTERY_POLL_INTERVAL_S=1.0

export CLUSTER_CAN_ENABLED=1
export CLUSTER_CAN_INTERFACE=socketcan
export CLUSTER_CAN_CHANNEL=can0
export CLUSTER_CAN_BITRATE=250000
export CLUSTER_CAN_TIMEOUT_S=0.2
export CLUSTER_CAN_LISTEN_ONLY=1
export CLUSTER_CAN_SPEED_SCALE_KPH_PER_RPM=0.01257
export CLUSTER_ESTIMATED_FULL_RANGE_KM=280
```

`CLUSTER_BATTERY_SERIALS` defaults to `17,22,6,26` in `neuwat` mode to match the definitive poller, but you should override that if your pack serials differ.

For `socketcan` on Raspberry Pi 4, bring the interface up before starting the HMI:

```bash
sudo ip link set can0 up type can bitrate 250000
ip -details link show can0
```

If you are using a USB SLCAN dongle instead of native `socketcan`, configure:

```bash
export CLUSTER_CAN_ENABLED=1
export CLUSTER_CAN_INTERFACE=slcan
export CLUSTER_CAN_CHANNEL=/dev/ttyUSB1
export CLUSTER_CAN_SERIAL_BAUD=115200
export CLUSTER_CAN_SCAN=1
```

### Generic stream battery mode

Use this only if you want to feed the HMI battery values from another process:

```bash
export CLUSTER_BATTERY_PORT=/dev/ttyUSB0
export CLUSTER_BATTERY_PROTOCOL=stream
export CLUSTER_BATTERY_BAUD=115200
```

Then start:

```bash
python3 main.py --fullscreen
```

If CAN is disabled, the app can still fall back to the older serial stream path for drive and inverter inputs, but the final intended vehicle setup is Neuwat RS-485 plus Slider CAN only.

## Neuwat integration notes

The HMI now vendors the definitive Neuwat protocol and polling logic directly inside the project:

- `cluster_hmi/neuwat_protocol.py`
- `cluster_hmi/services/neuwat_battery.py`

That means you can copy this HMI project onto the Raspberry Pi as a self-contained app instead of having to carry a second helper project beside it.

The battery tab now shows a stack-level aggregate view across all responding Neuwat packs:

- `SoC`: minimum pack SoC, so the displayed value stays conservative for the full stack
- `Pack Voltage`: sum of all responding pack voltages
- `Current`: average of the responding pack currents, which is the best stack-current estimate for series packs
- `Power`: total stack voltage multiplied by average pack current
- `Temp`: highest reported temperature across responding packs
- long partial poll cycles no longer blank the battery tab mid-round; the HMI keeps recent-good Neuwat values alive until the current polling budget has genuinely expired

The Neuwat backend now also mirrors the updated definitive poller’s datasheet logic:

- cell voltage scaling uses the updated centivolt interpretation from the pack data
- SoC is seeded from the revised voltage curve and then coulomb-counted
- idle voltage correction uses stronger blending near the LiFePO4 curve edges and weaker blending on the flat plateau
- SoC is clamped by protection thresholds so a critically low cell, or a true overvoltage condition, can force the displayed SoC into a safe range
- charge/discharge/current/temperature protection assessments are generated per pack from the datasheet thresholds

The faults page shows per-pack detail lines, raw `status` bytes, and any datasheet-derived alerts from the protection assessment.

## Slider CAN integration notes

The final app vendors the confirmed Slider controller CAN protocol directly into the project:

- `cluster_hmi/slider_can.py`
- `cluster_hmi/services/slider_can.py`

On Raspberry Pi 4, the preferred deployment is `socketcan` on `can0`. The app also supports `slcan` adapters through `python-can` when the controller is connected through a USB serial CAN bridge.

The HMI uses the validated CAN fields conservatively:

- speed on the drive page is derived from controller RPM using a configurable scale
- range on the drive page is derived from battery SoC so the CAN and battery sources stay consistent
- controller fault codes and low-power state are merged into the same fault page used by the battery service

This keeps the final application aligned with the two real vehicle data sources instead of relying on placeholder drive/inverter streams.

## Raspberry Pi boot setup

Starter files are in `deploy/`:

- `deploy/start-cluster.sh`
- `deploy/cluster-hmi.service`
- `deploy/cluster-hmi.env.example`

Copy the project to the Pi, adjust the paths and username inside the service file, then:

```bash
sudo cp deploy/cluster-hmi.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable cluster-hmi.service
sudo systemctl start cluster-hmi.service
```

For hardware-specific settings, copy:

```bash
cp deploy/cluster-hmi.env.example deploy/cluster-hmi.env
```

Then edit `deploy/cluster-hmi.env` with the real RS-485 port, CAN interface settings, and battery serial numbers for your packs. The launcher script will source that file automatically on boot.
