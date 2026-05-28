from __future__ import annotations

from dataclasses import dataclass
import math
import tkinter as tk
import tkinter.font as tkfont
from typing import Literal

from cluster_hmi.models import BatteryPackMetrics
from cluster_hmi.ui.theme import (
    ACCENT,
    BG,
    OK,
    OUTLINE,
    OUTLINE_SOFT,
    PANEL,
    PANEL_ALT,
    PANEL_SHADOW,
    TEXT,
    TEXT_MUTED,
    TEXT_SOFT,
    WARNING,
    WARNING_SOFT,
    font_family,
)

FontWeight = Literal["normal", "bold"]


def _font_spec(family: str, size: int, weight: FontWeight) -> tuple[str, int, FontWeight]:
    return (family, size, weight)


@dataclass(frozen=True)
class CardLayout:
    title_size: int
    label_size: int
    value_size: int
    unit_size: int
    body_label_size: int
    body_value_size: int
    title_y: float
    divider_y: float
    label_y: float
    primary_value_y: float
    unit_y: float
    secondary_top: float
    secondary_bottom: float
    secondary_padding_x: float
    secondary_gap_x: float


def _rounded_rect_points(x1: float, y1: float, x2: float, y2: float, radius: float) -> list[float]:
    radius = max(8.0, radius)
    return [
        x1 + radius,
        y1,
        x2 - radius,
        y1,
        x2,
        y1,
        x2,
        y1 + radius,
        x2,
        y2 - radius,
        x2,
        y2,
        x2 - radius,
        y2,
        x1 + radius,
        y2,
        x1,
        y2,
        x1,
        y2 - radius,
        x1,
        y1 + radius,
        x1,
        y1,
    ]


def _draw_rounded_panel(
    canvas: tk.Canvas,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    radius: float,
    *,
    fill: str,
    outline: str,
    width: int,
) -> None:
    points = _rounded_rect_points(x1, y1, x2, y2, radius)
    canvas.create_polygon(points, smooth=True, fill=fill, outline=outline, width=width)


class MetricCard(tk.Canvas):
    def __init__(
        self,
        master: tk.Misc,
        title: str,
        primary_label: str,
        primary_unit: str,
        secondary_columns: int = 2,
        compact: bool = False,
        primary_emphasis: float = 1.0,
    ) -> None:
        super().__init__(master, bg=BG, bd=0, highlightthickness=0)
        self._title = title
        self._primary_label = primary_label
        self._primary_unit = primary_unit
        self._secondary_columns = max(1, secondary_columns)
        self._compact = compact
        self._primary_emphasis = max(1.0, primary_emphasis)
        self._primary_value = "0"
        self._secondary_rows: list[tuple[str, str]] = []
        self._display_font = font_family(self, "display")
        self._text_font = font_family(self, "text")
        self.bind("<Configure>", lambda _: self._redraw())

    def set_content(self, primary_value: str, secondary_rows: list[tuple[str, str]]) -> None:
        self._primary_value = primary_value
        self._secondary_rows = secondary_rows
        self._redraw()

    def _redraw(self) -> None:
        self.delete("all")
        width = max(100, self.winfo_width())
        height = max(80, self.winfo_height())
        radius = min(width, height) * 0.14
        secondary_count = len(self._secondary_rows)
        secondary_columns = min(self._secondary_columns, max(1, secondary_count)) if secondary_count else 1
        secondary_rows = max(1, math.ceil(secondary_count / secondary_columns)) if secondary_count else 0

        _draw_rounded_panel(
            self,
            8,
            10,
            width - 2,
            height - 2,
            radius,
            fill=PANEL_SHADOW,
            outline=PANEL_SHADOW,
            width=1,
        )
        _draw_rounded_panel(
            self,
            4,
            4,
            width - 6,
            height - 6,
            radius,
            fill=PANEL,
            outline=OUTLINE,
            width=3,
        )
        _draw_rounded_panel(
            self,
            10,
            10,
            width - 12,
            height - 12,
            radius * 0.82,
            fill=PANEL_ALT,
            outline=OUTLINE_SOFT,
            width=1,
        )

        layout = self._layout_metrics(width=width, height=height, secondary_rows=secondary_rows)
        title_size = layout.title_size
        label_size = layout.label_size
        value_size = layout.value_size
        unit_size = layout.unit_size
        body_label_size = layout.body_label_size
        body_value_size = layout.body_value_size
        primary_value_y = layout.primary_value_y

        self.create_text(
            width / 2,
            layout.title_y,
            text=self._title,
            fill=TEXT,
            font=_font_spec(self._display_font, title_size, "bold"),
            anchor="center",
        )
        self.create_line(
            width * 0.18,
            layout.divider_y,
            width * 0.82,
            layout.divider_y,
            fill=OUTLINE_SOFT,
            width=1,
        )
        if self._primary_label.strip():
            self.create_text(
                width / 2,
                layout.label_y,
                text=self._primary_label.upper(),
                fill=TEXT_MUTED,
                font=_font_spec(self._text_font, label_size, "bold"),
                anchor="center",
            )
        self.create_text(
            width / 2 + max(1, int(value_size * 0.05)),
            primary_value_y + max(1, int(value_size * 0.05)),
            text=self._primary_value,
            fill=PANEL_SHADOW,
            font=_font_spec(self._display_font, value_size, "bold"),
            anchor="center",
        )
        self.create_text(
            width / 2,
            primary_value_y,
            text=self._primary_value,
            fill=TEXT,
            font=_font_spec(self._display_font, value_size, "bold"),
            anchor="center",
        )
        self.create_text(
            width / 2,
            layout.unit_y,
            text=self._primary_unit,
            fill=ACCENT,
            font=_font_spec(self._text_font, unit_size, "bold"),
            anchor="center",
        )

        if not secondary_count:
            return

        secondary_top = layout.secondary_top
        secondary_bottom = layout.secondary_bottom
        available_height = max(28, secondary_bottom - secondary_top)
        cell_height = available_height / secondary_rows
        horizontal_padding = layout.secondary_padding_x
        column_gap = layout.secondary_gap_x
        available_width = width - horizontal_padding * 2 - column_gap * (secondary_columns - 1)
        cell_width = available_width / secondary_columns

        for index, (label, value) in enumerate(self._secondary_rows):
            column_index = index % secondary_columns
            row_index = index // secondary_columns
            x1 = horizontal_padding + column_index * (cell_width + column_gap)
            x2 = x1 + cell_width
            center_x = (x1 + x2) / 2
            y1 = secondary_top + row_index * cell_height
            label_y = y1 + cell_height * 0.22
            value_y = y1 + cell_height * 0.68
            if label.strip():
                self.create_text(
                    center_x,
                    label_y,
                    text=label.upper(),
                    fill=TEXT_SOFT,
                    font=_font_spec(self._text_font, body_label_size, "bold"),
                    anchor="center",
                )
                self.create_text(
                    center_x,
                    value_y,
                    text=value,
                    fill=TEXT,
                    font=_font_spec(self._display_font, body_value_size, "bold"),
                    anchor="center",
                )
            else:
                self.create_text(
                    center_x,
                    y1 + cell_height * 0.50,
                    text=value,
                    fill=TEXT,
                    font=_font_spec(self._display_font, max(body_value_size, body_label_size + 2), "bold"),
                    anchor="center",
                )

    def _layout_metrics(self, *, width: int, height: int, secondary_rows: int) -> CardLayout:
        compact = self._compact
        emphasis = self._primary_emphasis
        has_primary_label = bool(self._primary_label.strip())
        hero_mode = emphasis >= 3.0 and not compact
        title_y = height * (0.13 if compact else 0.12)
        divider_y = height * (0.20 if compact else 0.19)
        label_y = height * (0.27 if compact else 0.25)
        primary_value_y = height * (0.45 if compact else 0.44)
        unit_y = height * (0.60 if compact else 0.59)
        secondary_top = height * (0.71 if compact else 0.70)
        secondary_bottom = height - (14 if compact else 16)
        secondary_padding_x = width * (0.05 if compact else 0.07)
        secondary_gap_x = width * (0.02 if compact else 0.03)

        if secondary_rows >= 3:
            primary_value_y = height * (0.35 if compact else 0.37)
            unit_y = height * (0.48 if compact else 0.50)
            secondary_top = height * (0.52 if compact else 0.54)
        elif secondary_rows == 2:
            primary_value_y = height * (0.38 if compact else 0.40)
            unit_y = height * (0.52 if compact else 0.55)
            secondary_top = height * (0.57 if compact else 0.60)

        if not has_primary_label:
            primary_value_y = height * (0.37 if compact else 0.39)
            unit_y = height * (0.52 if compact else 0.55)
            secondary_top = height * (0.63 if compact else 0.65)

        if hero_mode:
            title_y = height * 0.10
            divider_y = height * 0.17
            primary_value_y = height * 0.42
            unit_y = height * 0.57
            secondary_top = height * 0.76
            secondary_bottom = height - 12

        if emphasis > 1.0:
            shift = height * min(0.055, (emphasis - 1.0) * 0.04)
            primary_value_y -= shift
            unit_y += shift * 0.20
            secondary_top += shift * 0.55

        if hero_mode:
            primary_value_y = min(primary_value_y, height * 0.35)
            unit_y = min(unit_y, height * 0.60)
            secondary_top = min(max(secondary_top, height * 0.70), height * 0.73)

        title_size = self._fit_font(
            text=self._title,
            family=self._display_font,
            weight="bold",
            min_size=15 if compact else 18,
            max_size=max(20, int(height * (0.15 if compact else 0.16))),
            max_width=width * 0.80,
            max_height=height * 0.10,
        )
        label_size = self._fit_font(
            text=self._primary_label.upper(),
            family=self._text_font,
            weight="bold",
            min_size=11,
            max_size=max(14, int(height * (0.08 if compact else 0.09))),
            max_width=width * 0.62,
            max_height=height * 0.06,
        )
        unit_size = self._fit_font(
            text=self._primary_unit,
            family=self._text_font,
            weight="bold",
            min_size=10,
            max_size=max(14, int(height * 0.07)),
            max_width=width * 0.38,
            max_height=height * 0.05,
        )

        value_max_width = width * (0.54 if compact else 0.60)
        if len(self._primary_value) >= 5:
            value_max_width = width * (0.64 if compact else 0.70)
        value_max_height = height * (0.18 if compact else 0.22)
        if secondary_rows >= 2:
            value_max_height = height * (0.16 if compact else 0.19)
        if not has_primary_label:
            value_max_height = height * (0.21 if compact else 0.24)
        if hero_mode:
            value_max_width = width * 0.34
            value_max_height = height * 0.34
        value_max_width *= min(1.16, 1.0 + (emphasis - 1.0) * 0.10)
        value_max_height *= min(1.55, 1.0 + (emphasis - 1.0) * 0.40)
        base_min_size = 24 if compact else 28
        base_max_size = max(28, int(height * (0.28 if compact else 0.32)))
        if hero_mode:
            base_min_size = 34
            base_max_size = max(base_max_size, int(height * 0.40))
        value_size = self._fit_font(
            text=self._primary_value,
            family=self._display_font,
            weight="bold",
            min_size=int(base_min_size * emphasis),
            max_size=int(base_max_size * emphasis),
            max_width=value_max_width,
            max_height=value_max_height,
        )

        cell_width = (
            width - secondary_padding_x * 2 - secondary_gap_x * (max(1, self._secondary_columns) - 1)
        ) / max(1, self._secondary_columns)
        body_label_size = self._fit_font(
            text=max((label.upper() for label, _ in self._secondary_rows), key=len, default="LABEL"),
            family=self._text_font,
            weight="bold",
            min_size=10 if compact else 11,
            max_size=max(12, int(height * (0.05 if compact else 0.06))),
            max_width=cell_width * 0.88,
            max_height=max(14, (secondary_bottom - secondary_top) / max(1, secondary_rows) * 0.24),
        )
        body_value_size = self._fit_font(
            text=max((value for _, value in self._secondary_rows), key=len, default="0"),
            family=self._display_font,
            weight="bold",
            min_size=12 if compact else 14,
            max_size=max(16, int(height * (0.075 if compact else 0.10))),
            max_width=cell_width * 0.90,
            max_height=max(16, (secondary_bottom - secondary_top) / max(1, secondary_rows) * 0.38),
        )

        return CardLayout(
            title_size=title_size,
            label_size=label_size,
            value_size=value_size,
            unit_size=unit_size,
            body_label_size=body_label_size,
            body_value_size=body_value_size,
            title_y=title_y,
            divider_y=divider_y,
            label_y=label_y,
            primary_value_y=primary_value_y,
            unit_y=unit_y,
            secondary_top=secondary_top,
            secondary_bottom=secondary_bottom,
            secondary_padding_x=secondary_padding_x,
            secondary_gap_x=secondary_gap_x,
        )

    def _fit_font(
        self,
        *,
        text: str,
        family: str,
        weight: FontWeight,
        min_size: int,
        max_size: int,
        max_width: float,
        max_height: float,
    ) -> int:
        if not text:
            return min_size

        best = min_size
        for size in range(max_size, min_size - 1, -1):
            font = tkfont.Font(family=family, size=size, weight=weight)
            if font.measure(text) <= max_width and font.metrics("linespace") <= max_height:
                return size
            best = min(best, size)
        return max(8, best)


class FaultIconBar(tk.Canvas):
    def __init__(self, master: tk.Misc, items: list[tuple[str, str]] | None = None) -> None:
        super().__init__(master, bg=BG, bd=0, highlightthickness=0, height=90)
        self._states = {
            "temperature": False,
            "battery": False,
            "inverter": False,
            "motor": False,
        }
        self._items = items or [
            ("temperature", "TEMP"),
            ("battery", "BATT"),
            ("inverter", "INV"),
            ("motor", "MTR"),
        ]
        self._display_font = font_family(self, "display")
        self._text_font = font_family(self, "text")
        self.bind("<Configure>", lambda _: self._redraw())

    def set_states(self, states: dict[str, bool]) -> None:
        self._states.update(states)
        self._redraw()

    def _redraw(self) -> None:
        self.delete("all")
        count = max(1, len(self._items))
        width = max(68 * count + 12 * (count - 1), self.winfo_width())
        height = max(74, self.winfo_height())
        item_width = min(96, width / count - 12)
        gap = min(22, width * 0.03)
        total_width = item_width * count + gap * (count - 1)
        start_x = (width - total_width) / 2

        for index, (key, label) in enumerate(self._items):
            active = self._states.get(key, False)
            x1 = start_x + index * (item_width + gap)
            y1 = 10
            x2 = x1 + item_width
            y2 = height - 10
            center_x = (x1 + x2) / 2
            center_y = (y1 + y2) / 2 - 6
            outline = WARNING if active else OK
            fill = WARNING_SOFT if active else PANEL_ALT

            _draw_rounded_panel(
                self,
                x1 + 3,
                y1 + 6,
                x2 + 3,
                y2 + 6,
                16,
                fill=PANEL_SHADOW,
                outline=PANEL_SHADOW,
                width=1,
            )
            _draw_rounded_panel(
                self,
                x1,
                y1,
                x2,
                y2,
                16,
                fill=fill,
                outline=outline,
                width=2,
            )
            if key == "temperature":
                self._draw_thermometer(center_x, center_y, outline)
            elif key == "battery":
                self._draw_battery(center_x, center_y, outline)
            elif key == "inverter":
                self._draw_inverter(center_x, center_y, outline)
            else:
                self._draw_motor(center_x, center_y, outline)
            self.create_text(
                center_x,
                y2 - 15,
                text=label,
                fill=TEXT_SOFT if active else TEXT_MUTED,
                font=_font_spec(self._text_font, max(11, int(height * 0.15)), "bold"),
            )

    def _draw_thermometer(self, center_x: float, center_y: float, color: str) -> None:
        self.create_line(center_x, center_y - 15, center_x, center_y + 4, fill=color, width=3)
        self.create_oval(center_x - 7, center_y + 3, center_x + 7, center_y + 17, outline=color, width=2)
        self.create_line(center_x + 9, center_y - 11, center_x + 13, center_y - 11, fill=color, width=2)
        self.create_line(center_x + 9, center_y - 3, center_x + 13, center_y - 3, fill=color, width=2)

    def _draw_battery(self, center_x: float, center_y: float, color: str) -> None:
        self.create_rectangle(center_x - 15, center_y - 12, center_x + 15, center_y + 12, outline=color, width=2)
        self.create_rectangle(center_x + 16, center_y - 5, center_x + 20, center_y + 5, outline=color, width=2)
        bolt = [
            center_x - 4,
            center_y - 8,
            center_x + 2,
            center_y - 8,
            center_x - 2,
            center_y - 1,
            center_x + 6,
            center_y - 1,
            center_x - 2,
            center_y + 11,
            center_x + 1,
            center_y + 3,
            center_x - 6,
            center_y + 3,
        ]
        self.create_polygon(bolt, fill=color, outline=color)

    def _draw_inverter(self, center_x: float, center_y: float, color: str) -> None:
        self.create_rectangle(center_x - 14, center_y - 10, center_x + 14, center_y + 10, outline=color, width=2)
        self.create_line(
            [
                center_x - 10,
                center_y + 3,
                center_x - 3,
                center_y - 4,
                center_x + 2,
                center_y + 2,
                center_x + 9,
                center_y - 5,
            ],
            fill=color,
            width=2,
            smooth=True,
        )
        self.create_line(center_x - 10, center_y - 12, center_x - 10, center_y - 15, fill=color, width=2)
        self.create_line(center_x + 10, center_y - 12, center_x + 10, center_y - 15, fill=color, width=2)

    def _draw_motor(self, center_x: float, center_y: float, color: str) -> None:
        self.create_oval(center_x - 12, center_y - 12, center_x + 12, center_y + 12, outline=color, width=2)
        self.create_oval(center_x - 3, center_y - 3, center_x + 3, center_y + 3, outline=color, width=2)
        self.create_line(center_x, center_y - 9, center_x, center_y - 4, fill=color, width=2)
        self.create_line(center_x - 8, center_y + 5, center_x - 3, center_y + 2, fill=color, width=2)
        self.create_line(center_x + 8, center_y + 5, center_x + 3, center_y + 2, fill=color, width=2)
        self.create_line(center_x + 12, center_y, center_x + 18, center_y, fill=color, width=2)


class MetricTile(tk.Frame):
    def __init__(self, master: tk.Misc, label: str, unit: str = "") -> None:
        super().__init__(master, bg=PANEL, highlightbackground=OUTLINE_SOFT, highlightthickness=1)
        self._display_font = font_family(self, "display")
        self._text_font = font_family(self, "text")
        self._label_text = label.upper()
        self._value_text = f"0 {unit}".strip()
        self._label = tk.Label(
            self,
            text=self._label_text,
            bg=PANEL,
            fg=TEXT_SOFT,
            font=_font_spec(self._text_font, 12, "bold"),
        )
        self._value = tk.Label(
            self,
            text=self._value_text,
            bg=PANEL,
            fg=TEXT,
            font=_font_spec(self._display_font, 24, "bold"),
        )
        self._label.pack(anchor="w", padx=16, pady=(12, 2))
        self._value.pack(anchor="w", padx=16, pady=(2, 12))
        self.bind("<Configure>", lambda _: self._redraw())

    def set_value(self, value: str) -> None:
        self._value_text = value
        self._value.configure(text=value)
        self._redraw()

    def set_label(self, value: str) -> None:
        self._label_text = value.upper()
        self._label.configure(text=self._label_text)
        self._redraw()

    def _redraw(self) -> None:
        width = max(120, self.winfo_width())
        height = max(90, self.winfo_height())
        label_size = self._fit_font(
            text=self._label_text,
            family=self._text_font,
            weight="bold",
            min_size=11,
            max_size=max(15, int(height * 0.16)),
            max_width=width - 32,
            max_height=max(16, height * 0.16),
        )
        value_size = self._fit_font(
            text=self._value_text,
            family=self._display_font,
            weight="bold",
            min_size=18,
            max_size=max(24, int(height * 0.36)),
            max_width=width - 32,
            max_height=max(24, height * 0.36),
        )
        self._label.configure(font=_font_spec(self._text_font, label_size, "bold"))
        self._value.configure(font=_font_spec(self._display_font, value_size, "bold"))

    def _fit_font(
        self,
        *,
        text: str,
        family: str,
        weight: FontWeight,
        min_size: int,
        max_size: int,
        max_width: float,
        max_height: float,
    ) -> int:
        if not text:
            return min_size

        for size in range(max_size, min_size - 1, -1):
            font = tkfont.Font(family=family, size=size, weight=weight)
            if font.measure(text) <= max_width and font.metrics("linespace") <= max_height:
                return size
        return min_size


class BatteryPackPanel(tk.Frame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, bg=PANEL, highlightbackground=OUTLINE_SOFT, highlightthickness=1)
        self._display_font = font_family(self, "display")
        self._text_font = font_family(self, "text")
        self._pack = BatteryPackMetrics()

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        header = tk.Frame(self, bg=PANEL)
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 4))
        header.columnconfigure(0, weight=1)

        self._title = tk.Label(
            header,
            text="PACK",
            bg=PANEL,
            fg=TEXT,
            anchor="w",
            font=_font_spec(self._display_font, 16, "bold"),
        )
        self._title.grid(row=0, column=0, sticky="w")

        self._state = tk.Label(
            header,
            text="OFFLINE",
            bg=PANEL_ALT,
            fg=TEXT_MUTED,
            padx=10,
            pady=3,
            font=_font_spec(self._text_font, 10, "bold"),
        )
        self._state.grid(row=0, column=1, sticky="e")

        self._soc = tk.Label(
            self,
            text="--",
            bg=PANEL,
            fg=TEXT,
            font=_font_spec(self._display_font, 44, "bold"),
        )
        self._soc.grid(row=1, column=0, sticky="n", padx=16, pady=(0, 6))

        metrics = tk.Frame(self, bg=PANEL)
        metrics.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 8))
        for column in range(2):
            metrics.columnconfigure(column, weight=1)
        for row in range(3):
            metrics.rowconfigure(row, weight=1)

        self._metric_labels: list[tk.Label] = []
        for index in range(6):
            label = tk.Label(
                metrics,
                text="--",
                bg=PANEL,
                fg=TEXT_SOFT,
                anchor="w",
                justify="left",
                font=_font_spec(self._text_font, 13, "bold"),
            )
            label.grid(
                row=index // 2,
                column=index % 2,
                sticky="ew",
                padx=(0, 12) if index % 2 == 0 else (12, 0),
                pady=2,
            )
            self._metric_labels.append(label)

        self._mode_line = tk.Label(
            self,
            text="IDLE | CHG ? | DCHG ?",
            bg=PANEL,
            fg=ACCENT,
            anchor="w",
            justify="left",
            font=_font_spec(self._text_font, 11, "bold"),
        )
        self._mode_line.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 4))

        self._status_line = tk.Label(
            self,
            text="WAITING FOR PACK DATA",
            bg=PANEL,
            fg=TEXT_MUTED,
            anchor="w",
            justify="left",
            wraplength=320,
            font=_font_spec(self._text_font, 10, "bold"),
        )
        self._status_line.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 14))

        self.bind("<Configure>", lambda _: self._redraw())

    def set_pack(self, pack: BatteryPackMetrics) -> None:
        self._pack = pack
        self._apply_pack()
        self._redraw()

    def _apply_pack(self) -> None:
        pack = self._pack
        self._title.configure(text=f"PACK {pack.serial_number}" if pack.serial_number else "PACK")

        state_text, state_fg, state_bg = self._state_visuals(pack)
        self._state.configure(text=state_text, fg=state_fg, bg=state_bg)

        if pack.online:
            self._soc.configure(text=f"{pack.soc_pct:.0f}%")
            values = [
                f"V {pack.pack_voltage_v:.1f}V",
                f"I {pack.pack_current_a:.1f}A",
                f"P {pack.pack_power_kw:.1f}KW",
                f"T {pack.pack_temp_c:.1f}C",
                f"MIN {pack.min_cell_v:.3f}V",
                f"MAX {pack.max_cell_v:.3f}V",
            ]
            mode_text = (
                f"{self._short_direction(pack.current_state)} | "
                f"CHG {self._short_state(pack.charge_state)} | "
                f"DCHG {self._short_state(pack.discharge_state)}"
            )
            if pack.status_flags_text and pack.status_flags_text != "CLEAR":
                status_text = f"STAT {pack.status_flags_text}"
            elif pack.note:
                status_text = pack.note.upper()
            else:
                status_text = "STAT CLEAR"
        else:
            self._soc.configure(text="--")
            values = [
                "V --",
                "I --",
                "P --",
                "T --",
                "MIN --",
                "MAX --",
            ]
            mode_text = "OFFLINE | CHG -- | DCHG --"
            status_text = pack.note.upper() if pack.note else "WAITING FOR FIRST REPLY"

        for label, value in zip(self._metric_labels, values):
            label.configure(text=value)
        self._mode_line.configure(text=mode_text)
        self._status_line.configure(text=status_text)

    def _redraw(self) -> None:
        width = max(180, self.winfo_width())
        height = max(180, self.winfo_height())

        title_size = self._fit_font(
            text=self._title.cget("text"),
            family=self._display_font,
            weight="bold",
            min_size=13,
            max_size=max(18, int(height * 0.08)),
            max_width=width * 0.42,
            max_height=max(18, height * 0.08),
        )
        state_size = self._fit_font(
            text=self._state.cget("text"),
            family=self._text_font,
            weight="bold",
            min_size=9,
            max_size=max(12, int(height * 0.06)),
            max_width=width * 0.28,
            max_height=max(16, height * 0.06),
        )
        soc_size = self._fit_font(
            text=self._soc.cget("text"),
            family=self._display_font,
            weight="bold",
            min_size=26,
            max_size=max(34, int(height * 0.25)),
            max_width=width * 0.55,
            max_height=max(34, height * 0.20),
        )
        metric_size = self._fit_font(
            text=max((label.cget("text") for label in self._metric_labels), key=len, default="V 000.0V"),
            family=self._text_font,
            weight="bold",
            min_size=11,
            max_size=max(14, int(height * 0.07)),
            max_width=width * 0.36,
            max_height=max(16, height * 0.08),
        )
        footer_size = self._fit_font(
            text=self._mode_line.cget("text"),
            family=self._text_font,
            weight="bold",
            min_size=10,
            max_size=max(12, int(height * 0.055)),
            max_width=width - 32,
            max_height=max(14, height * 0.06),
        )
        status_size = self._fit_font(
            text=self._status_line.cget("text"),
            family=self._text_font,
            weight="bold",
            min_size=9,
            max_size=max(11, int(height * 0.05)),
            max_width=width - 32,
            max_height=max(14, height * 0.09),
        )

        self._title.configure(font=_font_spec(self._display_font, title_size, "bold"))
        self._state.configure(font=_font_spec(self._text_font, state_size, "bold"))
        self._soc.configure(font=_font_spec(self._display_font, soc_size, "bold"))
        for label in self._metric_labels:
            label.configure(font=_font_spec(self._text_font, metric_size, "bold"))
        self._mode_line.configure(font=_font_spec(self._text_font, footer_size, "bold"))
        self._status_line.configure(
            font=_font_spec(self._text_font, status_size, "bold"),
            wraplength=max(140, width - 32),
        )

    def _state_visuals(self, pack: BatteryPackMetrics) -> tuple[str, str, str]:
        if pack.online:
            if pack.freshness_text.startswith("cached"):
                return ("ONLINE", WARNING, WARNING_SOFT)
            return ("ONLINE", TEXT, OK)
        if pack.note.startswith("waiting"):
            return ("WAITING", TEXT_MUTED, PANEL_ALT)
        return ("OFFLINE", TEXT_MUTED, PANEL_ALT)

    def _short_state(self, value: str) -> str:
        mapping = {
            "ok": "OK",
            "blocked": "BLOCK",
            "recovery-zone": "RECOV",
            "unknown": "--",
        }
        return mapping.get(value, value.upper())

    def _short_direction(self, value: str) -> str:
        mapping = {
            "charging": "CHG",
            "discharging": "DCHG",
            "idle": "IDLE",
        }
        return mapping.get(value, value.upper())

    def _fit_font(
        self,
        *,
        text: str,
        family: str,
        weight: FontWeight,
        min_size: int,
        max_size: int,
        max_width: float,
        max_height: float,
    ) -> int:
        if not text:
            return min_size

        for size in range(max_size, min_size - 1, -1):
            font = tkfont.Font(family=family, size=size, weight=weight)
            if font.measure(text) <= max_width and font.metrics("linespace") <= max_height:
                return size
        return min_size
