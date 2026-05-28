from __future__ import annotations

import tkinter as tk

from cluster_hmi.config import AppConfig
from cluster_hmi.models import BatteryPackMetrics, ClusterSnapshot
from cluster_hmi.store import ClusterStore
from cluster_hmi.ui.theme import BG, OUTLINE_SOFT, PANEL, TEXT, TEXT_MUTED, TEXT_SOFT, font_family
from cluster_hmi.ui.widgets import BatteryPackPanel, FaultIconBar, MetricCard, MetricTile


def _fmt(value: float, digits: int = 0) -> str:
    return f"{value:.{digits}f}"


def _online_battery_packs(snapshot: ClusterSnapshot) -> list[BatteryPackMetrics]:
    return [pack for pack in snapshot.battery_packs if pack.online]


def _battery_average_soc(snapshot: ClusterSnapshot) -> float:
    packs = _online_battery_packs(snapshot)
    if not packs:
        return 0.0
    return sum(pack.soc_pct for pack in packs) / len(packs)


def _overview_battery_rows(snapshot: ClusterSnapshot) -> list[tuple[str, str]]:
    if snapshot.battery_packs:
        rows: list[tuple[str, str]] = []
        for pack in snapshot.battery_packs[:4]:
            label = f"P{pack.serial_number} {'ON' if pack.online else 'OFF'}"
            value = f"{_fmt(pack.soc_pct, 0)}%" if pack.online else "--"
            rows.append((label, value))
        return rows

    return [
        ("STACK V", f"{_fmt(snapshot.battery.pack_voltage_v, 1)}V"),
        ("STACK P", f"{_fmt(snapshot.battery.pack_power_kw, 1)}KW"),
        ("RANGE", f"{_fmt(snapshot.drive.range_km, 0)}KM"),
        ("TEMP", f"{_fmt(snapshot.battery.pack_temp_c, 1)}C"),
    ]


class ClusterDashboardApp(tk.Tk):
    def __init__(self, config: AppConfig, store: ClusterStore) -> None:
        super().__init__()
        self._config = config
        self._store = store
        self._current_page = "overview"
        self._pages: dict[str, tk.Frame] = {}
        self._nav_buttons: dict[str, tk.Button] = {}
        self._display_font = font_family(self, "display")
        self._text_font = font_family(self, "text")

        self.configure(bg=BG)
        self.title("Car Cluster HMI")
        self.geometry(f"{config.width}x{config.height}")
        self.minsize(1024, 600)

        if config.fullscreen:
            self.attributes("-fullscreen", True)

        self.bind("<Escape>", lambda _: self.destroy())
        self.bind("<F11>", self._toggle_fullscreen)
        self.bind("1", lambda _: self.show_page("overview"))
        self.bind("2", lambda _: self.show_page("drive"))
        self.bind("3", lambda _: self.show_page("battery"))
        self.bind("4", lambda _: self.show_page("inverter"))
        self.bind("5", lambda _: self.show_page("odometer"))
        self.bind("6", lambda _: self.show_page("faults"))

        self._build_shell()
        self.show_page("overview")
        self._tick()

    def _build_shell(self) -> None:
        nav_shell = tk.Frame(self, bg=BG)
        nav_shell.pack(fill="x", padx=18, pady=(14, 8))

        nav = tk.Frame(nav_shell, bg=BG)
        nav.pack(side="left")

        for page_name, label in [
            ("overview", "Overview"),
            ("drive", "Drive"),
            ("battery", "Battery"),
            ("inverter", "Inverter"),
            ("odometer", "Odometer"),
            ("faults", "Faults"),
        ]:
            button = tk.Button(
                nav,
                text=label.upper(),
                command=lambda current=page_name: self.show_page(current),
                bg=BG,
                fg=TEXT_MUTED,
                activebackground=PANEL,
                activeforeground=TEXT,
                relief="flat",
                bd=0,
                padx=28,
                pady=16,
                font=(self._display_font, 20, "bold"),
            )
            button.pack(side="left", padx=(0, 12))
            self._nav_buttons[page_name] = button

        self._mode = tk.Label(
            nav_shell,
            text="CLUSTER PREVIEW",
            bg=PANEL,
            fg=TEXT_SOFT,
            font=(self._text_font, 16, "bold"),
            padx=18,
            pady=12,
        )
        self._mode.pack(side="right")

        divider = tk.Frame(self, bg=OUTLINE_SOFT, height=1)
        divider.pack(fill="x", padx=20, pady=(0, 6))

        self._status = tk.Label(
            self,
            text="NO LIVE DATA - DISPLAYING ZERO VALUES",
            bg=BG,
            fg=TEXT_MUTED,
            font=(self._text_font, 15, "bold"),
            anchor="w",
        )
        self._status.pack(side="bottom", fill="x", padx=20, pady=(6, 14))

        container = tk.Frame(self, bg=BG)
        container.pack(fill="both", expand=True, padx=20, pady=(0, 6))

        self._pages["overview"] = OverviewPage(container)
        self._pages["drive"] = DrivePage(container)
        self._pages["battery"] = BatteryPage(container)
        self._pages["inverter"] = InverterPage(container)
        self._pages["odometer"] = OdometerPage(container)
        self._pages["faults"] = FaultsPage(container)

        for page in self._pages.values():
            page.place(relx=0, rely=0, relwidth=1, relheight=1)

    def _tick(self) -> None:
        snapshot = self._store.get_snapshot()
        page = self._pages[self._current_page]
        updater = getattr(page, "update_snapshot", None)
        if callable(updater):
            updater(snapshot)
        status_text = snapshot.status_text
        if self._config.demo_mode:
            status_text = f"DEMO MODE - {status_text}"
        self._status.configure(text=status_text)
        self._mode.configure(text="DEMO MODE" if self._config.demo_mode else "LIVE CLUSTER")
        self.after(self._config.refresh_ms, self._tick)

    def show_page(self, page_name: str) -> None:
        self._current_page = page_name
        for current_name, page in self._pages.items():
            if current_name == page_name:
                page.lift()
                self._nav_buttons[current_name].configure(bg=PANEL, fg=TEXT)
            else:
                self._nav_buttons[current_name].configure(bg=BG, fg=TEXT_MUTED)

    def _toggle_fullscreen(self, _event) -> None:
        current = bool(self.attributes("-fullscreen"))
        self.attributes("-fullscreen", not current)


class OverviewPage(tk.Frame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, bg=BG)
        self.left_faults = FaultIconBar(
            self,
            items=[
                ("temperature", "TEMP"),
                ("battery", "BATT"),
            ],
        )
        self.left_faults.place(relx=0.065, rely=0.155, relwidth=0.11, relheight=0.115, anchor="center")

        self.right_faults = FaultIconBar(
            self,
            items=[
                ("inverter", "INV"),
                ("motor", "MTR"),
            ],
        )
        self.right_faults.place(relx=0.935, rely=0.155, relwidth=0.11, relheight=0.115, anchor="center")

        self.drive = MetricCard(
            self,
            title="DRIVE",
            primary_label="",
            primary_unit="KM/H",
            secondary_columns=3,
            primary_emphasis=3.05,
        )
        self.drive.place(relx=0.50, rely=0.295, relwidth=0.78, relheight=0.46, anchor="center")

        self.battery = MetricCard(
            self,
            title="BATTERY",
            primary_label="MIN SOC",
            primary_unit="%",
            secondary_columns=2,
            compact=False,
            primary_emphasis=2.55,
        )
        self.battery.place(relx=0.255, rely=0.675, relwidth=0.425, relheight=0.315, anchor="center")

        self.inverter = MetricCard(
            self,
            title="INV / MOTOR",
            primary_label="",
            primary_unit="RPM",
            secondary_columns=2,
            compact=False,
            primary_emphasis=1.95,
        )
        self.inverter.place(relx=0.745, rely=0.675, relwidth=0.405, relheight=0.305, anchor="center")

        self.odometer = MetricCard(
            self,
            title="ODOMETER",
            primary_label="",
            primary_unit="KM",
            secondary_columns=2,
            compact=True,
        )
        self.odometer.place(relx=0.50, rely=0.895, relwidth=0.305, relheight=0.155, anchor="center")

    def update_snapshot(self, snapshot: ClusterSnapshot) -> None:
        self.left_faults.set_states(
            {
                "temperature": snapshot.faults.temperature,
                "battery": snapshot.faults.battery,
            }
        )
        self.right_faults.set_states(
            {
                "inverter": snapshot.faults.inverter,
                "motor": snapshot.faults.motor,
            }
        )
        self.drive.set_content(
            primary_value=_fmt(snapshot.drive.speed_kph, 0),
            secondary_rows=[
                ("", f"THR {_fmt(snapshot.drive.throttle_pct, 0)}%"),
                ("", f"REG {_fmt(snapshot.drive.regen_pct, 0)}%"),
                ("", f"RNG {_fmt(snapshot.drive.range_km, 0)}KM"),
            ],
        )
        self.battery.set_content(
            primary_value=_fmt(snapshot.battery.soc_pct, 0),
            secondary_rows=_overview_battery_rows(snapshot),
        )
        self.inverter.set_content(
            primary_value=_fmt(snapshot.inverter.rpm, 0),
            secondary_rows=[
                ("", f"INV {_fmt(snapshot.inverter.inverter_temp_c, 1)}C"),
                ("", f"MTR {_fmt(snapshot.inverter.motor_temp_c, 1)}C"),
                ("", f"TQ {_fmt(snapshot.inverter.torque_nm, 0)}NM"),
                ("", f"BUS {_fmt(snapshot.inverter.dc_bus_voltage_v, 1)}V"),
            ],
        )
        self.odometer.set_content(
            primary_value=_fmt(snapshot.odometer.odometer_km, 1),
            secondary_rows=[
                ("", f"A {_fmt(snapshot.odometer.trip_a_km, 1)}KM"),
                ("", f"B {_fmt(snapshot.odometer.trip_b_km, 1)}KM"),
            ],
        )


class _DetailPage(tk.Frame):
    page_title = ""
    primary_title = ""
    primary_unit = ""
    primary_emphasis = 1.0

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, bg=BG)
        display_font = font_family(self, "display")
        self.title = tk.Label(
            self,
            text=self.page_title,
            bg=BG,
            fg=TEXT,
            font=(display_font, 40, "bold"),
        )
        self.title.pack(anchor="w", pady=(8, 10))

        self.primary = MetricCard(
            self,
            title=self.page_title,
            primary_label=self.primary_title,
            primary_unit=self.primary_unit,
            secondary_columns=3,
            primary_emphasis=self.primary_emphasis,
        )
        self.primary.pack(fill="x", pady=(0, 20), ipady=32)

        grid = tk.Frame(self, bg=BG)
        grid.pack(fill="both", expand=True)
        self.tiles: list[MetricTile] = []
        for _ in range(6):
            tile = MetricTile(grid, label="", unit="")
            self.tiles.append(tile)
        for index, tile in enumerate(self.tiles):
            row = index // 3
            column = index % 3
            tile.grid(row=row, column=column, sticky="nsew", padx=10, pady=10)
            grid.grid_columnconfigure(column, weight=1)
            grid.grid_rowconfigure(row, weight=1)


class DrivePage(_DetailPage):
    page_title = "DRIVE"
    primary_title = "Speed"
    primary_unit = "KM/H"
    primary_emphasis = 1.95

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        labels = [
            ("Throttle", "%"),
            ("Regen", "%"),
            ("Range", "km"),
            ("Battery SoC", "%"),
            ("Pack Power", "kW"),
            ("Motor RPM", "rpm"),
        ]
        for tile, (label, unit) in zip(self.tiles, labels):
            tile.set_label(label)
            tile.set_value(f"0 {unit}".strip())

    def update_snapshot(self, snapshot: ClusterSnapshot) -> None:
        self.primary.set_content(
            primary_value=_fmt(snapshot.drive.speed_kph, 0),
            secondary_rows=[
                ("Throttle", f"{_fmt(snapshot.drive.throttle_pct, 0)} %"),
                ("Regen", f"{_fmt(snapshot.drive.regen_pct, 0)} %"),
                ("Range", f"{_fmt(snapshot.drive.range_km, 0)} km"),
            ],
        )
        values = [
            f"{_fmt(snapshot.drive.throttle_pct, 0)} %",
            f"{_fmt(snapshot.drive.regen_pct, 0)} %",
            f"{_fmt(snapshot.drive.range_km, 0)} km",
            f"{_fmt(snapshot.battery.soc_pct, 0)} %",
            f"{_fmt(snapshot.battery.pack_power_kw, 1)} kW",
            f"{_fmt(snapshot.inverter.rpm, 0)} rpm",
        ]
        for tile, value in zip(self.tiles, values):
            tile.set_value(value)


class BatteryPage(tk.Frame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, bg=BG)
        display_font = font_family(self, "display")
        text_font = font_family(self, "text")

        self.title = tk.Label(
            self,
            text="BATTERY",
            bg=BG,
            fg=TEXT,
            font=(display_font, 40, "bold"),
        )
        self.title.pack(anchor="w", pady=(8, 10))

        self.primary = MetricCard(
            self,
            title="BATTERY STACK",
            primary_label="MIN SOC",
            primary_unit="%",
            secondary_columns=3,
            primary_emphasis=2.15,
        )
        self.primary.pack(fill="x", pady=(0, 18), ipady=24)

        self.pack_hint = tk.Label(
            self,
            text="Per-pack battery telemetry will appear here when Neuwat pack data is available.",
            bg=BG,
            fg=TEXT_MUTED,
            anchor="w",
            font=(text_font, 14, "bold"),
        )
        self.pack_hint.pack(fill="x", pady=(0, 12))

        self.pack_grid = tk.Frame(self, bg=BG)
        self.pack_grid.pack(fill="both", expand=True)
        self.pack_panels: list[BatteryPackPanel] = []
        for index in range(4):
            panel = BatteryPackPanel(self.pack_grid)
            row = index // 2
            column = index % 2
            panel.grid(row=row, column=column, sticky="nsew", padx=10, pady=10)
            self.pack_grid.grid_columnconfigure(column, weight=1)
            self.pack_grid.grid_rowconfigure(row, weight=1)
            self.pack_panels.append(panel)

    def update_snapshot(self, snapshot: ClusterSnapshot) -> None:
        online_packs = _online_battery_packs(snapshot)
        average_soc = _battery_average_soc(snapshot)
        total_packs = len(snapshot.battery_packs)
        online_count = len(online_packs)

        self.primary.set_content(
            primary_value=_fmt(snapshot.battery.soc_pct, 0),
            secondary_rows=[
                ("Online", f"{online_count}/{total_packs}" if total_packs else "0/0"),
                ("Avg SoC", f"{_fmt(average_soc, 0)} %"),
                ("Stack V", f"{_fmt(snapshot.battery.pack_voltage_v, 1)} V"),
                ("Current", f"{_fmt(snapshot.battery.pack_current_a, 1)} A"),
                ("Power", f"{_fmt(snapshot.battery.pack_power_kw, 1)} kW"),
                ("Temp", f"{_fmt(snapshot.battery.pack_temp_c, 1)} C"),
            ],
        )

        has_pack_data = bool(snapshot.battery_packs)
        self.pack_hint.configure(
            text=(
                "Each pack is shown separately for diagnostics."
                if has_pack_data
                else "Per-pack battery telemetry will appear here when Neuwat pack data is available."
            ),
            fg=TEXT_SOFT if has_pack_data else TEXT_MUTED,
        )
        if not has_pack_data:
            for panel in self.pack_panels:
                panel.grid_remove()
            return

        for panel, pack in zip(self.pack_panels, snapshot.battery_packs[:4]):
            panel.set_pack(pack)
            panel.grid()

        for panel in self.pack_panels[len(snapshot.battery_packs[:4]) :]:
            panel.grid_remove()


class InverterPage(_DetailPage):
    page_title = "INVERTER / MOTOR"
    primary_title = "RPM"
    primary_unit = "RPM"
    primary_emphasis = 1.50

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        labels = [
            ("Inv Temp", "C"),
            ("Motor Temp", "C"),
            ("DC Bus", "V"),
            ("Current", "A"),
            ("Torque", "Nm"),
            ("Battery Power", "kW"),
        ]
        for tile, (label, unit) in zip(self.tiles, labels):
            tile.set_label(label)
            tile.set_value(f"0 {unit}".strip())

    def update_snapshot(self, snapshot: ClusterSnapshot) -> None:
        self.primary.set_content(
            primary_value=_fmt(snapshot.inverter.rpm, 0),
            secondary_rows=[
                ("Inv Temp", f"{_fmt(snapshot.inverter.inverter_temp_c, 1)} C"),
                ("Motor Tmp", f"{_fmt(snapshot.inverter.motor_temp_c, 1)} C"),
                ("DC Bus", f"{_fmt(snapshot.inverter.dc_bus_voltage_v, 1)} V"),
                ("Current", f"{_fmt(snapshot.inverter.phase_current_a, 1)} A"),
                ("Torque", f"{_fmt(snapshot.inverter.torque_nm, 0)} Nm"),
            ],
        )
        values = [
            f"{_fmt(snapshot.inverter.inverter_temp_c, 1)} C",
            f"{_fmt(snapshot.inverter.motor_temp_c, 1)} C",
            f"{_fmt(snapshot.inverter.dc_bus_voltage_v, 1)} V",
            f"{_fmt(snapshot.inverter.phase_current_a, 1)} A",
            f"{_fmt(snapshot.inverter.torque_nm, 0)} Nm",
            f"{_fmt(snapshot.battery.pack_power_kw, 1)} kW",
        ]
        for tile, value in zip(self.tiles, values):
            tile.set_value(value)


class OdometerPage(_DetailPage):
    page_title = "ODOMETER / DIAG"
    primary_title = "Odometer"
    primary_unit = "KM"

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        labels = [
            ("Trip A", "km"),
            ("Trip B", "km"),
            ("Efficiency", "Wh/km"),
            ("Drive Time", "h"),
            ("12V Rail", "V"),
            ("Pack Voltage", "V"),
        ]
        for tile, (label, unit) in zip(self.tiles, labels):
            tile.set_label(label)
            tile.set_value(f"0 {unit}".strip())

    def update_snapshot(self, snapshot: ClusterSnapshot) -> None:
        self.primary.set_content(
            primary_value=_fmt(snapshot.odometer.odometer_km, 1),
            secondary_rows=[
                ("Trip A", f"{_fmt(snapshot.odometer.trip_a_km, 1)} km"),
                ("Trip B", f"{_fmt(snapshot.odometer.trip_b_km, 1)} km"),
                ("Eff", f"{_fmt(snapshot.odometer.efficiency_wh_per_km, 0)} Wh/km"),
                ("12V", f"{_fmt(snapshot.odometer.low_voltage_v, 1)} V"),
                ("Drive", f"{_fmt(snapshot.odometer.drive_time_h, 1)} h"),
            ],
        )
        values = [
            f"{_fmt(snapshot.odometer.trip_a_km, 1)} km",
            f"{_fmt(snapshot.odometer.trip_b_km, 1)} km",
            f"{_fmt(snapshot.odometer.efficiency_wh_per_km, 0)} Wh/km",
            f"{_fmt(snapshot.odometer.drive_time_h, 1)} h",
            f"{_fmt(snapshot.odometer.low_voltage_v, 1)} V",
            f"{_fmt(snapshot.battery.pack_voltage_v, 1)} V",
        ]
        for tile, value in zip(self.tiles, values):
            tile.set_value(value)


class FaultsPage(tk.Frame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, bg=BG)
        display_font = font_family(self, "display")
        text_font = font_family(self, "text")
        title = tk.Label(
            self,
            text="FAULTS",
            bg=BG,
            fg=TEXT,
            font=(display_font, 28, "bold"),
        )
        title.pack(anchor="w", pady=(8, 10))

        self.icons = FaultIconBar(self)
        self.icons.pack(fill="x", pady=(0, 16))

        self.text = tk.Text(
            self,
            bg=PANEL,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            bd=0,
            font=(text_font, 14),
            wrap="word",
        )
        self.text.pack(fill="both", expand=True)

    def update_snapshot(self, snapshot: ClusterSnapshot) -> None:
        self.icons.set_states(
            {
                "temperature": snapshot.faults.temperature,
                "battery": snapshot.faults.battery,
                "inverter": snapshot.faults.inverter,
                "motor": snapshot.faults.motor,
            }
        )
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        if snapshot.fault_messages:
            self.text.insert("end", "\n".join(snapshot.fault_messages))
        else:
            self.text.insert("end", "No active faults.\n\nUse the other tabs for live values while this page stays focused on details.")
        self.text.configure(state="disabled")
