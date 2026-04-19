# -*- coding: utf-8 -*-
"""
Style manager module.
Applies graduated symbology to INGV seismic layers:
  - Events: circle size proportional to magnitude, color = depth class
  - Stations: uniform triangle marker with network label
  - Heatmap: kernel density estimation renderer (Fase 2)
"""

from qgis.core import (
    QgsGraduatedSymbolRenderer,
    QgsRendererRange,
    QgsSymbol,
    QgsMarkerSymbol,
    QgsSingleSymbolRenderer,
    QgsSimpleMarkerSymbolLayer,
    QgsHeatmapRenderer,
    QgsColorRampShader,
    QgsStyle,
    QgsProperty,
    QgsVectorLayer,
)
from qgis.PyQt.QtGui import QColor


# ---------------------------------------------------------------------------
# Color palette (depth classes)
# ---------------------------------------------------------------------------

# Depth ranges in km → (label, hex color)
DEPTH_CLASSES = [
    (0,   10,  "Superficiale (0-10 km)",    "#E53935"),   # red
    (10,  35,  "Intermedio (10-35 km)",      "#FB8C00"),   # orange
    (35,  70,  "Medio (35-70 km)",           "#FDD835"),   # yellow
    (70,  150, "Profondo (70-150 km)",       "#43A047"),   # green
    (150, 700, "Molto profondo (>150 km)",   "#1E88E5"),   # blue
]

# Magnitude → symbol size mapping (px)
MAG_SIZE_MAP = [
    (0.0, 2.0, 4),
    (2.0, 3.0, 6),
    (3.0, 4.0, 9),
    (4.0, 5.0, 13),
    (5.0, 6.0, 18),
    (6.0, 7.0, 24),
    (7.0, 10.0, 32),
]


# ---------------------------------------------------------------------------
# Event layer style
# ---------------------------------------------------------------------------

def apply_event_style(layer: QgsVectorLayer) -> None:
    """Apply graduated symbology to the events layer.

    Symbols are circles whose SIZE is driven by magnitude (graduated renderer
    on the 'magnitude' field) and whose COLOR is a fixed orange with
    semi-transparency, so depth can be inspected in the attribute table.

    For a full depth-colored style, use apply_event_depth_style() instead.

    Args:
        layer: The seismic events QgsVectorLayer to style.
    """
    ranges = []

    for (mag_min, mag_max, size_px) in MAG_SIZE_MAP:
        symbol = QgsMarkerSymbol.createSimple({
            "name": "circle",
            "color": "255,120,0,180",       # orange, semi-transparent
            "outline_color": "180,60,0,220",
            "outline_width": "0.4",
            "size": str(size_px),
            "size_unit": "Point",
        })

        label = f"M {mag_min:.1f} – {mag_max:.1f}"
        rng = QgsRendererRange(mag_min, mag_max, symbol, label)
        ranges.append(rng)

    renderer = QgsGraduatedSymbolRenderer("magnitude", ranges)
    renderer.setMode(QgsGraduatedSymbolRenderer.Custom)
    layer.setRenderer(renderer)
    layer.triggerRepaint()


def apply_event_depth_style(layer: QgsVectorLayer) -> None:
    """Apply depth-colored graduated symbology to the events layer.

    Symbols are circles of fixed size colored by depth class.
    Useful to distinguish shallow vs deep events visually.

    Args:
        layer: The seismic events QgsVectorLayer to style.
    """
    ranges = []

    for (d_min, d_max, label, hex_color) in DEPTH_CLASSES:
        symbol = QgsMarkerSymbol.createSimple({
            "name": "circle",
            "color": hex_color,
            "color_alpha": "180",
            "outline_color": "50,50,50,200",
            "outline_width": "0.3",
            "size": "7",
            "size_unit": "Point",
        })
        rng = QgsRendererRange(d_min, d_max, symbol, label)
        ranges.append(rng)

    renderer = QgsGraduatedSymbolRenderer("depth_km", ranges)
    renderer.setMode(QgsGraduatedSymbolRenderer.Custom)
    layer.setRenderer(renderer)
    layer.triggerRepaint()


# ---------------------------------------------------------------------------
# Station layer style
# ---------------------------------------------------------------------------

def apply_station_style(layer: QgsVectorLayer) -> None:
    """Apply a uniform triangle marker style to the stations layer.

    Args:
        layer: The seismic stations QgsVectorLayer to style.
    """
    symbol = QgsMarkerSymbol.createSimple({
        "name": "triangle",
        "color": "30,120,220,210",
        "outline_color": "10,60,140,255",
        "outline_width": "0.5",
        "size": "6",
        "size_unit": "Point",
    })

    renderer = QgsSingleSymbolRenderer(symbol)
    layer.setRenderer(renderer)

    # Enable labels showing station code
    layer.setCustomProperty("labeling", "pal")
    layer.setCustomProperty("labeling/enabled", True)
    layer.setCustomProperty("labeling/fieldName", "station")
    layer.setCustomProperty("labeling/fontSize", "7")
    layer.setCustomProperty("labeling/placement", "2")   # around point

    layer.triggerRepaint()


# ---------------------------------------------------------------------------
# Heatmap style  (Fase 2)
# ---------------------------------------------------------------------------

def apply_heatmap_style(layer: QgsVectorLayer, radius_mm: float = 8.0,
                         weight_field: str = None) -> None:
    """Apply a kernel density heatmap renderer to an events layer.

    Uses QgsHeatmapRenderer — built into QGIS core, no extra dependencies.
    The color ramp goes transparent → yellow → orange → red (volcano palette).

    Args:
        layer: The seismic events QgsVectorLayer to style.
        radius_mm: KDE kernel radius in map units (millimetres at screen scale).
            Larger values = smoother, broader hotspots.
        weight_field: Optional attribute name to weight events by (e.g. 'magnitude').
            When None, every event contributes equally.
    """
    renderer = QgsHeatmapRenderer()
    renderer.setRadius(radius_mm)
    renderer.setRadiusUnit(
        # QgsUnitTypes.RenderMillimeters = 1  (safe numeric fallback)
        getattr(__import__("qgis.core", fromlist=["QgsUnitTypes"]).QgsUnitTypes,
                "RenderMillimeters", 1)
    )

    # Color ramp: fully transparent → yellow → orange → deep red.
    # Always built manually so the first stop is guaranteed alpha=0,
    # regardless of what QGIS default styles return.
    from qgis.core import QgsGradientColorRamp, QgsGradientStop
    color_ramp = QgsGradientColorRamp(
        QColor(255, 255, 0, 0),          # stop 0.0 — fully transparent
        QColor(189, 0, 38, 255),         # stop 1.0 — deep red, fully opaque
    )
    color_ramp.setStops([
        QgsGradientStop(0.35, QColor(255, 237, 160, 180)),  # pale yellow
        QgsGradientStop(0.60, QColor(253, 141,  60, 210)),  # orange
        QgsGradientStop(0.82, QColor(240,  59,  32, 235)),  # red-orange
    ])
    renderer.setColorRamp(color_ramp)

    if weight_field:
        renderer.setWeightExpression(weight_field)

    renderer.setMaximumValue(0)   # 0 = auto-scale to dataset maximum

    layer.setRenderer(renderer)
    layer.triggerRepaint()
