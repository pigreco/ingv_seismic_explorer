# -*- coding: utf-8 -*-
"""
Layer builder module.
Creates QgsVectorLayer instances from INGV API data (events and stations).
"""

from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsFields,
    QgsField,
    QgsProject,
    QgsCoordinateReferenceSystem,
    QgsVectorLayerTemporalProperties,
)
from qgis.PyQt.QtCore import QVariant, QDateTime, Qt

from .style_manager import apply_event_style, apply_station_style


# ---------------------------------------------------------------------------
# Events layer
# ---------------------------------------------------------------------------

def build_events_layer(events, layer_name="INGV Terremoti"):
    """Create a point vector layer from a list of SeismicEvent objects.

    The layer uses EPSG:4326 (WGS84) CRS, matching the coordinates
    returned by the INGV FDSNWS API.

    Attribute table columns:
        event_id    (String)  - INGV unique event identifier
        time        (String)  - ISO origin time (UTC)
        magnitude   (Double)  - Magnitude value
        mag_type    (String)  - Magnitude type (ML, Mw, Mb, ...)
        depth_km    (Double)  - Hypocentral depth in km
        location    (String)  - Human-readable location name
        event_type  (String)  - Event type (earthquake, quarry blast, ...)
        latitude    (Double)  - Epicentral latitude (WGS84)
        longitude   (Double)  - Epicentral longitude (WGS84)
        ingv_url    (String)  - Direct link to INGV event page

    Args:
        events (list[SeismicEvent]): Parsed events from api_client.
        layer_name (str): Name displayed in the QGIS Layers panel.

    Returns:
        QgsVectorLayer: The populated, styled vector layer (not yet added
            to the project — caller is responsible for QgsProject.addMapLayer).
    """
    layer = QgsVectorLayer("Point?crs=EPSG:4326", layer_name, "memory")
    provider = layer.dataProvider()

    # Define attribute fields
    fields = QgsFields()
    fields.append(QgsField("event_id",   QVariant.String))
    fields.append(QgsField("time",       QVariant.String))
    fields.append(QgsField("magnitude",  QVariant.Double))
    fields.append(QgsField("mag_type",   QVariant.String))
    fields.append(QgsField("depth_km",   QVariant.Double))
    fields.append(QgsField("location",   QVariant.String))
    fields.append(QgsField("event_type", QVariant.String))
    fields.append(QgsField("latitude",   QVariant.Double))
    fields.append(QgsField("longitude",  QVariant.Double))
    fields.append(QgsField("ingv_url",   QVariant.String))
    provider.addAttributes(fields)
    layer.updateFields()

    # Populate features
    features = []
    for ev in events:
        feat = QgsFeature()
        feat.setGeometry(
            QgsGeometry.fromPointXY(QgsPointXY(ev.longitude, ev.latitude))
        )
        feat.setAttributes([
            ev.event_id,
            ev.time,
            ev.magnitude,
            ev.mag_type,
            ev.depth_km,
            ev.location,
            ev.event_type,
            ev.latitude,
            ev.longitude,
            f"https://terremoti.ingv.it/event/{ev.event_id}",
        ])
        features.append(feat)

    provider.addFeatures(features)
    layer.updateExtents()

    # Apply graduated symbology
    apply_event_style(layer)

    return layer


# ---------------------------------------------------------------------------
# Stations layer
# ---------------------------------------------------------------------------

def build_stations_layer(stations, layer_name="INGV Stazioni Sismiche (IV)"):
    """Create a point vector layer from a list of SeismicStation objects.

    Args:
        stations (list[SeismicStation]): Parsed stations from api_client.
        layer_name (str): Name displayed in the QGIS Layers panel.

    Returns:
        QgsVectorLayer: The populated, styled vector layer.
    """
    layer = QgsVectorLayer("Point?crs=EPSG:4326", layer_name, "memory")
    provider = layer.dataProvider()

    fields = QgsFields()
    fields.append(QgsField("network",    QVariant.String))
    fields.append(QgsField("station",    QVariant.String))
    fields.append(QgsField("site_name",  QVariant.String))
    fields.append(QgsField("elevation",  QVariant.Double))
    fields.append(QgsField("latitude",   QVariant.Double))
    fields.append(QgsField("longitude",  QVariant.Double))
    fields.append(QgsField("start_time", QVariant.String))
    fields.append(QgsField("end_time",   QVariant.String))
    provider.addAttributes(fields)
    layer.updateFields()

    features = []
    for st in stations:
        feat = QgsFeature()
        feat.setGeometry(
            QgsGeometry.fromPointXY(QgsPointXY(st.longitude, st.latitude))
        )
        feat.setAttributes([
            st.network,
            st.station,
            st.site_name,
            st.elevation,
            st.latitude,
            st.longitude,
            st.start_time,
            st.end_time,
        ])
        features.append(feat)

    provider.addFeatures(features)
    layer.updateExtents()

    apply_station_style(layer)

    return layer


# ---------------------------------------------------------------------------
# Helper: add layer to project
# ---------------------------------------------------------------------------

def add_layer_to_project(layer):
    """Add a vector layer to the current QGIS project.

    Args:
        layer (QgsVectorLayer): Layer to add.

    Returns:
        QgsVectorLayer: The same layer (now registered in QgsProject).
    """
    QgsProject.instance().addMapLayer(layer)
    return layer


# ---------------------------------------------------------------------------
# Temporal properties  (Fase 2)
# ---------------------------------------------------------------------------

def enable_temporal_properties(layer: QgsVectorLayer,
                                 time_field: str = "time") -> None:
    """Enable QGIS Temporal Controller integration on an events layer.

    After calling this, the layer will respond to the QGIS temporal
    controller (View → Panels → Temporal Controller), animating events
    through time based on their origin timestamp.

    Requires QGIS >= 3.14.

    The 'time' field in the events layer stores ISO-8601 strings (UTC).
    QGIS temporal properties accept string datetime fields directly.

    Args:
        layer: The seismic events QgsVectorLayer.
        time_field: Name of the datetime attribute (default 'time').
    """
    try:
        props = layer.temporalProperties()
        if props is None:
            return

        props.setIsActive(True)

        # Mode 0 = FeatureDateTimeInstantFromField
        # Each feature appears at a single instant (its origin time)
        props.setMode(
            QgsVectorLayerTemporalProperties.ModeFeatureDateTimeInstantFromField
        )
        props.setStartField(time_field)

        # Duration: keep each event visible for 1 hour on the timeline
        from qgis.PyQt.QtCore import QgsInterval
        props.setFixedDuration(QgsInterval(3600))    # 3600 seconds = 1 hour

        layer.temporalPropertiesChanged.emit()

    except Exception:
        # Temporal API changed between QGIS versions; fail silently
        pass


def build_events_layer_temporal(events, layer_name="INGV Terremoti (temporale)"):
    """Create an events layer with temporal properties pre-enabled.

    Convenience wrapper around build_events_layer + enable_temporal_properties.

    Args:
        events (list[SeismicEvent]): Parsed events from api_client.
        layer_name (str): Layer name for the QGIS panel.

    Returns:
        QgsVectorLayer: Events layer ready for temporal animation.
    """
    from .layer_builder import build_events_layer
    layer = build_events_layer(events, layer_name=layer_name)
    enable_temporal_properties(layer, time_field="time")
    return layer
