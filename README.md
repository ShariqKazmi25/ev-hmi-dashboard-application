# Solar-Powered EV Dashboard

A Python/Tkinter instrument cluster for a 72 V swappable-battery EV senior design project at Lahore University of Management Sciences. It runs on a Raspberry Pi 4 and brings battery, drive, inverter, and fault information into a six-view dashboard.

## Desktop preview

Use Python 3.10 or newer with Tkinter. On Raspberry Pi OS, install `python3-tk` if Tkinter is missing. From the repository root, activate a virtual environment and run:

```bash
python -m pip install -r requirements.txt
python main.py --demo
```

Demo mode generates sample telemetry and needs no vehicle connection. Use `1` through `6` to switch between Overview, Drive, Battery, Inverter, Odometer, and Faults. `F11` toggles fullscreen and `Esc` exits.

## Vehicle interfaces

| Source | Interface | Data used by the dashboard |
| --- | --- | --- |
| Neuwat battery packs | RS-485, 4800 baud, 8E1 | Per-pack voltage, current, temperature, cell readings, status flags, and estimated state of charge |
| Slider motor controller | CAN, 250 kbit/s in the reference configuration | RPM, direction, speed mode, low-power flag, fault code, DC bus voltage, and motor current |

Background services poll the battery packs by serial number and decode two extended Slider CAN frames. The battery service checks frame integrity, retries missing responses, and tracks the freshness of each pack. The dashboard derives road speed from controller RPM and estimates remaining range from battery state of charge. The odometer view is populated by demo data in the current code.

## Raspberry Pi setup

1. Install the Python dependencies into the interpreter that will launch the app. Connect the RS-485 and CAN interfaces.
2. Copy [`deploy/cluster-hmi.env.example`](deploy/cluster-hmi.env.example) to `deploy/cluster-hmi.env`. Set the serial device, battery pack serial numbers, and CAN channel for your hardware. The sample targets SocketCAN on `can0`. A USB SLCAN adapter can be configured with `CLUSTER_CAN_INTERFACE=slcan` and its serial device as `CLUSTER_CAN_CHANNEL`.
3. For SocketCAN, configure the interface at the vehicle bus bitrate before launching the application. With the sample settings, run `sudo ip link set can0 up type can bitrate 250000`.
4. From a graphical session on the Pi, source the environment file and run `python3 main.py --fullscreen`.

For boot launch, use the sample [`systemd` unit](deploy/cluster-hmi.service) and [launcher](deploy/start-cluster.sh). Set the user, checkout path, and Python interpreter to match your Pi before enabling the service.

## Code map

- [`main.py`](main.py) loads configuration, starts background services, and launches the Tkinter app.
- [`cluster_hmi/services/`](cluster_hmi/services/) contains the battery polling, CAN, serial-stream, and demo services.
- [`cluster_hmi/neuwat_protocol.py`](cluster_hmi/neuwat_protocol.py) and [`cluster_hmi/slider_can.py`](cluster_hmi/slider_can.py) handle the vehicle protocols.
- [`cluster_hmi/store.py`](cluster_hmi/store.py) publishes thread-safe snapshots and applies stale-data handling.
- [`cluster_hmi/ui/`](cluster_hmi/ui/) contains the dashboard views and widgets.
