# -*- coding: utf-8 -*-
"""
Analysis module — Fase 2.
Provides seismological analysis tools:
  - Gutenberg-Richter frequency-magnitude distribution (b-value estimation)
  - Event time series (daily / weekly counts)
  - Depth distribution histogram
  - Interactive matplotlib chart dialog embedded in Qt
"""

import math
from collections import defaultdict, Counter
from datetime import datetime, timedelta

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget,
    QWidget, QPushButton, QLabel, QComboBox,
    QSizePolicy, QFrame, QMessageBox,
)
from qgis.PyQt.QtCore import Qt
from qgis.core import QgsVectorLayer

# matplotlib import — bundled with QGIS since 3.x
try:
    import matplotlib
    matplotlib.use("Qt5Agg")
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
    from matplotlib.figure import Figure
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False


# ---------------------------------------------------------------------------
# Pure analysis functions (no Qt dependency)
# ---------------------------------------------------------------------------

def compute_gutenberg_richter(events, mag_step=0.1):
    """Compute Gutenberg-Richter cumulative frequency distribution.

    The GR law states:  log10(N) = a - b * M
    where N = number of earthquakes with M >= threshold.

    Args:
        events (list[SeismicEvent]): List of seismic events.
        mag_step (float): Magnitude bin width for histogram.

    Returns:
        dict with keys:
            magnitudes  (list[float]) - magnitude thresholds
            log_n       (list[float]) - log10 of cumulative count
            n_cumul     (list[int])   - raw cumulative counts
            b_value     (float | None) - estimated GR b-value
            a_value     (float | None) - estimated GR a-value
            mag_complete (float | None) - magnitude of completeness estimate
    """
    if not events:
        return {}

    mags = [ev.magnitude for ev in events if ev.magnitude is not None]
    if not mags:
        return {}

    m_min = math.floor(min(mags) / mag_step) * mag_step
    m_max = math.ceil(max(mags) / mag_step) * mag_step

    # Build thresholds from m_min to m_max
    thresholds = []
    m = m_min
    while m <= m_max + 1e-9:
        thresholds.append(round(m, 2))
        m += mag_step

    # Cumulative counts N(M >= threshold)
    n_cumul = [sum(1 for mag in mags if mag >= t) for t in thresholds]
    log_n = [math.log10(n) if n > 0 else None for n in n_cumul]

    # Estimate b-value via least squares on the linear part
    # Use only thresholds where N >= 5 for stability
    valid_pts = [
        (t, ln) for t, ln in zip(thresholds, log_n)
        if ln is not None and n_cumul[thresholds.index(t)] >= 5
    ]

    b_value = None
    a_value = None
    mag_complete = None

    if len(valid_pts) >= 4:
        xs = [p[0] for p in valid_pts]
        ys = [p[1] for p in valid_pts]
        n = len(xs)
        sum_x = sum(xs)
        sum_y = sum(ys)
        sum_xy = sum(x * y for x, y in zip(xs, ys))
        sum_xx = sum(x * x for x in xs)
        denom = n * sum_xx - sum_x ** 2
        if denom != 0:
            b_value = -(n * sum_xy - sum_x * sum_y) / denom
            a_value = (sum_y + b_value * sum_x) / n
            # Magnitude of completeness: midpoint of valid range
            mag_complete = round(xs[0], 1)

    return {
        "magnitudes":    thresholds,
        "log_n":         log_n,
        "n_cumul":       n_cumul,
        "b_value":       b_value,
        "a_value":       a_value,
        "mag_complete":  mag_complete,
        "valid_fit_pts": valid_pts,
    }


def compute_time_series(events, bin_days=1):
    """Count events per time bin (daily or weekly).

    Args:
        events (list[SeismicEvent]): Seismic events with 'time' attribute.
        bin_days (int): Bin size in days (1 = daily, 7 = weekly).

    Returns:
        dict with keys:
            dates  (list[datetime]) - bin start dates
            counts (list[int])      - event count per bin
    """
    if not events:
        return {"dates": [], "counts": []}

    parsed = []
    for ev in events:
        try:
            dt = datetime.fromisoformat(ev.time[:19])
            parsed.append(dt)
        except (ValueError, TypeError):
            continue

    if not parsed:
        return {"dates": [], "counts": []}

    parsed.sort()
    start = parsed[0].replace(hour=0, minute=0, second=0, microsecond=0)
    end = parsed[-1].replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=bin_days)

    bins = []
    current = start
    while current <= end:
        bins.append(current)
        current += timedelta(days=bin_days)

    counts = [0] * (len(bins) - 1)
    for dt in parsed:
        for i in range(len(bins) - 1):
            if bins[i] <= dt < bins[i + 1]:
                counts[i] += 1
                break

    return {"dates": bins[:-1], "counts": counts}


def compute_depth_distribution(events, bin_km=5):
    """Compute depth histogram.

    Args:
        events (list[SeismicEvent]): Seismic events.
        bin_km (int): Bin size in km.

    Returns:
        dict with keys:
            depths (list[float]) - bin left edges
            counts (list[int])   - event count per bin
    """
    if not events:
        return {"depths": [], "counts": []}

    depths = [ev.depth_km for ev in events if ev.depth_km is not None]
    if not depths:
        return {"depths": [], "counts": []}

    max_depth = max(depths)
    n_bins = max(1, int(math.ceil(max_depth / bin_km)))
    bins = [i * bin_km for i in range(n_bins + 1)]
    counts = [0] * n_bins

    for d in depths:
        idx = min(int(d / bin_km), n_bins - 1)
        counts[idx] += 1

    return {"depths": bins[:-1], "counts": counts}


# ---------------------------------------------------------------------------
# Matplotlib chart helpers
# ---------------------------------------------------------------------------

def _make_figure(figsize=(7, 4)):
    """Create a Figure with transparent background and tight layout."""
    fig = Figure(figsize=figsize, dpi=96)
    fig.patch.set_facecolor("none")
    return fig


def plot_gutenberg_richter(ax, gr_data):
    """Plot the GR cumulative frequency-magnitude distribution.

    Args:
        ax: matplotlib Axes object.
        gr_data (dict): Output of compute_gutenberg_richter().
    """
    mags = gr_data.get("magnitudes", [])
    log_n = gr_data.get("log_n", [])

    # Raw data points
    valid_m = [m for m, ln in zip(mags, log_n) if ln is not None]
    valid_ln = [ln for ln in log_n if ln is not None]

    ax.plot(valid_m, valid_ln, "o", color="#E53935", markersize=5,
            label="Dati osservati", zorder=3)

    # GR fit line
    b = gr_data.get("b_value")
    a = gr_data.get("a_value")
    mc = gr_data.get("mag_complete")
    if b is not None and a is not None and valid_m:
        fit_m = [m for m in valid_m if m >= (mc or 0)]
        fit_y = [a - b * m for m in fit_m]
        ax.plot(fit_m, fit_y, "-", color="#1E88E5", linewidth=2,
                label=f"GR fit: b = {b:.2f}", zorder=2)
        if mc is not None:
            ax.axvline(mc, color="#FB8C00", linestyle="--", linewidth=1.2,
                       label=f"Mc ≈ {mc:.1f}", zorder=1)

    ax.set_xlabel("Magnitudo (M)", fontsize=10)
    ax.set_ylabel("log₁₀ N (eventi ≥ M)", fontsize=10)
    ax.set_title("Relazione Gutenberg-Richter", fontsize=11, fontweight="bold")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3, linestyle="--")
    ax.tick_params(labelsize=9)


def plot_time_series(ax, ts_data, bin_label="giorno"):
    """Plot the event count time series as a bar chart.

    Args:
        ax: matplotlib Axes object.
        ts_data (dict): Output of compute_time_series().
        bin_label (str): 'giorno' or 'settimana'.
    """
    dates = ts_data.get("dates", [])
    counts = ts_data.get("counts", [])

    if not dates:
        ax.text(0.5, 0.5, "Nessun dato disponibile",
                ha="center", va="center", transform=ax.transAxes, fontsize=11)
        return

    ax.bar(dates, counts, width=timedelta(days=0.8 if bin_label == "giorno" else 5),
           color="#FB8C00", alpha=0.85, edgecolor="#C76F00", linewidth=0.5)

    # Moving average (7-day) when daily
    if bin_label == "giorno" and len(counts) >= 7:
        window = 7
        ma = []
        for i in range(len(counts)):
            start_i = max(0, i - window // 2)
            end_i = min(len(counts), i + window // 2 + 1)
            ma.append(sum(counts[start_i:end_i]) / (end_i - start_i))
        ax.plot(dates, ma, color="#E53935", linewidth=1.8,
                label="Media mobile 7gg", zorder=3)
        ax.legend(fontsize=9)

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m/%y"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.set_xlabel("Data", fontsize=10)
    ax.set_ylabel(f"N eventi / {bin_label}", fontsize=10)
    ax.set_title("Serie temporale eventi sismici", fontsize=11, fontweight="bold")
    ax.grid(True, alpha=0.3, linestyle="--", axis="y")
    ax.tick_params(axis="x", rotation=30, labelsize=8)
    ax.tick_params(axis="y", labelsize=9)


def plot_depth_distribution(ax, depth_data):
    """Plot the depth histogram as horizontal bars.

    Args:
        ax: matplotlib Axes object.
        depth_data (dict): Output of compute_depth_distribution().
    """
    depths = depth_data.get("depths", [])
    counts = depth_data.get("counts", [])

    if not depths:
        ax.text(0.5, 0.5, "Nessun dato disponibile",
                ha="center", va="center", transform=ax.transAxes, fontsize=11)
        return

    # Color by depth class
    colors = []
    for d in depths:
        if d < 10:
            colors.append("#E53935")
        elif d < 35:
            colors.append("#FB8C00")
        elif d < 70:
            colors.append("#FDD835")
        elif d < 150:
            colors.append("#43A047")
        else:
            colors.append("#1E88E5")

    bin_height = depths[1] - depths[0] if len(depths) > 1 else 5
    ax.barh(depths, counts, height=bin_height * 0.85,
            color=colors, edgecolor="white", linewidth=0.3, align="edge")
    ax.invert_yaxis()
    ax.set_xlabel("N eventi", fontsize=10)
    ax.set_ylabel("Profondità (km)", fontsize=10)
    ax.set_title("Distribuzione profondità ipocentrale", fontsize=11, fontweight="bold")
    ax.grid(True, alpha=0.3, linestyle="--", axis="x")
    ax.tick_params(labelsize=9)


# ---------------------------------------------------------------------------
# Chart dialog
# ---------------------------------------------------------------------------

class AnalysisDialog(QDialog):
    """Floating dialog that displays seismological analysis charts.

    Requires matplotlib (bundled with QGIS >= 3.x).

    Args:
        events (list[SeismicEvent]): Events to analyse.
        layer_name (str): Title label shown at the top.
        parent: Parent Qt widget.
    """

    def __init__(self, events, layer_name="", parent=None):
        super().__init__(parent)
        self.events = events
        self.layer_name = layer_name
        self.setWindowTitle("INGV — Analisi Sismicità")
        self.setMinimumSize(720, 520)
        self.resize(800, 560)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(10, 10, 10, 10)

        # Header
        header = QLabel(
            f"<b>Analisi sismicità</b>  —  {len(self.events)} eventi"
            + (f"  |  {self.layer_name}" if self.layer_name else "")
        )
        header.setStyleSheet("font-size: 11pt; padding: 4px 0;")
        layout.addWidget(header)

        if not HAS_MATPLOTLIB:
            warn = QLabel(
                "⚠️  matplotlib non disponibile.\n"
                "Installalo con:  pip install matplotlib"
            )
            warn.setAlignment(Qt.AlignCenter)
            warn.setStyleSheet("color: #c0392b; font-size: 11pt; padding: 20px;")
            layout.addWidget(warn)
            layout.addWidget(self._make_close_btn())
            return

        # Tabs with three charts
        tabs = QTabWidget()
        tabs.addTab(self._make_gr_tab(),    "📊  Gutenberg-Richter")
        tabs.addTab(self._make_ts_tab(),    "📅  Serie temporale")
        tabs.addTab(self._make_dep_tab(),   "🔽  Profondità")
        layout.addWidget(tabs)

        # Stats summary bar
        stats = self._build_stats_bar()
        layout.addWidget(stats)

        layout.addWidget(self._make_close_btn())

    # ------------------------------------------------------------------
    # Tab builders
    # ------------------------------------------------------------------

    def _make_gr_tab(self):
        """Build the Gutenberg-Richter chart tab."""
        gr_data = compute_gutenberg_richter(self.events)
        fig = _make_figure(figsize=(7, 4))
        ax = fig.add_subplot(111)
        ax.set_facecolor("#fafafa")
        if gr_data:
            plot_gutenberg_richter(ax, gr_data)
        else:
            ax.text(0.5, 0.5, "Dati insufficienti",
                    ha="center", va="center", transform=ax.transAxes)
        fig.tight_layout(pad=1.2)
        return self._wrap_canvas(fig)

    def _make_ts_tab(self):
        """Build the time series chart tab with daily/weekly toggle."""
        widget = QWidget()
        vl = QVBoxLayout(widget)
        vl.setContentsMargins(0, 4, 0, 0)

        # Toggle
        hl = QHBoxLayout()
        hl.addWidget(QLabel("Raggruppamento:"))
        self.combo_bin = QComboBox()
        self.combo_bin.addItems(["Giornaliero (1 giorno)", "Settimanale (7 giorni)"])
        hl.addWidget(self.combo_bin)
        hl.addStretch()
        vl.addLayout(hl)

        # Canvas placeholder
        self._ts_fig = _make_figure(figsize=(7, 3.8))
        self._ts_ax = self._ts_fig.add_subplot(111)
        self._ts_ax.set_facecolor("#fafafa")
        self._ts_canvas = FigureCanvas(self._ts_fig)
        self._ts_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        vl.addWidget(NavigationToolbar(self._ts_canvas, widget))
        vl.addWidget(self._ts_canvas)

        self.combo_bin.currentIndexChanged.connect(self._refresh_ts)
        self._refresh_ts(0)
        return widget

    def _make_dep_tab(self):
        """Build the depth distribution chart tab."""
        dep_data = compute_depth_distribution(self.events, bin_km=5)
        fig = _make_figure(figsize=(7, 4))
        ax = fig.add_subplot(111)
        ax.set_facecolor("#fafafa")
        plot_depth_distribution(ax, dep_data)
        fig.tight_layout(pad=1.2)
        return self._wrap_canvas(fig)

    # ------------------------------------------------------------------
    # Refresh time series on bin change
    # ------------------------------------------------------------------

    def _refresh_ts(self, index):
        """Redraw the time series chart with new bin size."""
        bin_days = 1 if index == 0 else 7
        bin_label = "giorno" if index == 0 else "settimana"
        ts_data = compute_time_series(self.events, bin_days=bin_days)
        self._ts_ax.clear()
        self._ts_ax.set_facecolor("#fafafa")
        plot_time_series(self._ts_ax, ts_data, bin_label=bin_label)
        self._ts_fig.tight_layout(pad=1.2)
        self._ts_canvas.draw()

    # ------------------------------------------------------------------
    # Stats summary
    # ------------------------------------------------------------------

    def _build_stats_bar(self):
        """Build a compact stats summary row."""
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setStyleSheet(
            "background: #f0f4f8; border-radius: 4px; padding: 4px;"
        )
        hl = QHBoxLayout(frame)
        hl.setContentsMargins(8, 4, 8, 4)

        if self.events:
            mags = [ev.magnitude for ev in self.events if ev.magnitude is not None]
            depths = [ev.depth_km for ev in self.events if ev.depth_km is not None]
            gr = compute_gutenberg_richter(self.events)

            stats = [
                ("N eventi",     str(len(self.events))),
                ("M max",        f"{max(mags):.1f}" if mags else "—"),
                ("M media",      f"{sum(mags)/len(mags):.2f}" if mags else "—"),
                ("Depth media",  f"{sum(depths)/len(depths):.1f} km" if depths else "—"),
                ("b-value",      f"{gr['b_value']:.2f}" if gr.get("b_value") else "—"),
                ("Mc stimato",   f"{gr['mag_complete']:.1f}" if gr.get("mag_complete") else "—"),
            ]
        else:
            stats = []

        for label, value in stats:
            col = QVBoxLayout()
            lbl = QLabel(label)
            lbl.setStyleSheet("font-size: 8pt; color: #666;")
            val = QLabel(f"<b>{value}</b>")
            val.setStyleSheet("font-size: 10pt;")
            col.addWidget(lbl)
            col.addWidget(val)
            hl.addLayout(col)
            if stats.index((label, value)) < len(stats) - 1:
                sep = QFrame()
                sep.setFrameShape(QFrame.VLine)
                sep.setStyleSheet("color: #ccc;")
                hl.addWidget(sep)

        return frame

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _wrap_canvas(self, fig):
        """Wrap a matplotlib Figure in a QWidget with navigation toolbar."""
        widget = QWidget()
        vl = QVBoxLayout(widget)
        vl.setContentsMargins(0, 0, 0, 0)
        canvas = FigureCanvas(fig)
        canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        vl.addWidget(NavigationToolbar(canvas, widget))
        vl.addWidget(canvas)
        return widget

    def _make_close_btn(self):
        btn = QPushButton("Chiudi")
        btn.clicked.connect(self.close)
        btn.setMaximumWidth(100)
        hl = QHBoxLayout()
        hl.addStretch()
        hl.addWidget(btn)
        w = QWidget()
        w.setLayout(hl)
        return w
