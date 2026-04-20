# -*- coding: utf-8 -*-
"""
INGV FDSNWS API client.
Handles all communication with webservices.ingv.it using QThread
to avoid blocking the QGIS main UI thread.
"""

import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime

from qgis.PyQt.QtCore import QThread, pyqtSignal


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_EVENT_URL = "https://webservices.ingv.it/fdsnws/event/1/query"
BASE_STATION_URL = "https://webservices.ingv.it/fdsnws/station/1/query"
REQUEST_TIMEOUT = 30  # seconds


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class SeismicEvent:
    """Represents a single seismic event from INGV."""

    __slots__ = (
        "event_id", "time", "latitude", "longitude",
        "depth_km", "mag_type", "magnitude", "location", "event_type"
    )

    def __init__(self, event_id, time, latitude, longitude,
                 depth_km, mag_type, magnitude, location, event_type):
        self.event_id = event_id
        self.time = time
        self.latitude = float(latitude)
        self.longitude = float(longitude)
        self.depth_km = float(depth_km)
        self.mag_type = mag_type
        self.magnitude = float(magnitude)
        self.location = location
        self.event_type = event_type

    def __repr__(self):
        return (
            f"<SeismicEvent id={self.event_id} "
            f"M{self.magnitude} {self.location}>"
        )


class SeismicStation:
    """Represents a seismic station from INGV."""

    __slots__ = (
        "network", "station", "latitude", "longitude",
        "elevation", "site_name", "start_time", "end_time"
    )

    def __init__(self, network, station, latitude, longitude,
                 elevation, site_name, start_time, end_time):
        self.network = network
        self.station = station
        self.latitude = float(latitude)
        self.longitude = float(longitude)
        self.elevation = float(elevation) if elevation else 0.0
        self.site_name = site_name
        self.start_time = start_time
        self.end_time = end_time


# ---------------------------------------------------------------------------
# Query builder
# ---------------------------------------------------------------------------

def build_event_url(start_time, end_time,
                    min_magnitude=None, max_magnitude=None,
                    min_depth=None, max_depth=None,
                    min_lat=None, max_lat=None,
                    min_lon=None, max_lon=None,
                    lat=None, lon=None, max_radius_km=None,
                    limit=10000):
    """Build the FDSNWS event query URL from filter parameters.

    Args:
        start_time (datetime): Query start time.
        end_time (datetime): Query end time.
        min_magnitude (float, optional): Minimum magnitude filter.
        max_magnitude (float, optional): Maximum magnitude filter.
        min_depth (float, optional): Minimum depth in km.
        max_depth (float, optional): Maximum depth in km.
        min_lat / max_lat / min_lon / max_lon: Bounding box coordinates.
        lat / lon / max_radius_km: Circular area filter (alternative to bbox).
        limit (int): Max number of events to return (default 10000).

    Returns:
        str: Complete query URL.
    """
    params = {
        "starttime": start_time.strftime("%Y-%m-%dT%H:%M:%S"),
        "endtime": end_time.strftime("%Y-%m-%dT%H:%M:%S"),
        "format": "text",
        "limit": limit,
        "orderby": "time-asc",
    }

    if min_magnitude is not None:
        params["minmagnitude"] = min_magnitude
    if max_magnitude is not None:
        params["maxmagnitude"] = max_magnitude
    if min_depth is not None:
        params["mindepth"] = min_depth
    if max_depth is not None:
        params["maxdepth"] = max_depth

    # Circular area takes priority over bounding box
    if lat is not None and lon is not None and max_radius_km is not None:
        params["lat"] = lat
        params["lon"] = lon
        params["maxradiuskm"] = max_radius_km
    elif all(v is not None for v in [min_lat, max_lat, min_lon, max_lon]):
        params["minlat"] = min_lat
        params["maxlat"] = max_lat
        params["minlon"] = min_lon
        params["maxlon"] = max_lon

    return BASE_EVENT_URL + "?" + urllib.parse.urlencode(params)


def build_station_url(network="IV", level="station"):
    """Build the FDSNWS station query URL.

    Args:
        network (str): Network code (default IV = Rete Sismica Nazionale).
        level (str): Detail level: network | station | channel | response.

    Returns:
        str: Complete query URL.
    """
    params = {
        "network": network,
        "level": level,
        "format": "text",
    }
    return BASE_STATION_URL + "?" + urllib.parse.urlencode(params)


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def parse_events(text):
    """Parse FDSNWS text response into SeismicEvent list.

    Expected columns (pipe-separated):
    EventID | Time | Latitude | Longitude | Depth/Km | Author | Catalog |
    Contributor | ContributorID | MagType | Magnitude | MagAuthor |
    EventLocationName | EventType

    Args:
        text (str): Raw API response text.

    Returns:
        list[SeismicEvent]: Parsed events.
    """
    events = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 13:
            continue
        try:
            events.append(SeismicEvent(
                event_id=parts[0],
                time=parts[1],
                latitude=parts[2],
                longitude=parts[3],
                depth_km=parts[4],
                mag_type=parts[9],
                magnitude=parts[10] if parts[10] else "0",
                location=parts[12],
                event_type=parts[13] if len(parts) > 13 else "earthquake",
            ))
        except (ValueError, IndexError):
            continue
    return events


def parse_stations(text):
    """Parse FDSNWS station text response into SeismicStation list.

    Expected columns (pipe-separated):
    Network | Station | Latitude | Longitude | Elevation | SiteName |
    StartTime | EndTime

    Args:
        text (str): Raw API response text.

    Returns:
        list[SeismicStation]: Parsed stations.
    """
    stations = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 6:
            continue
        try:
            stations.append(SeismicStation(
                network=parts[0],
                station=parts[1],
                latitude=parts[2],
                longitude=parts[3],
                elevation=parts[4],
                site_name=parts[5],
                start_time=parts[6] if len(parts) > 6 else "",
                end_time=parts[7] if len(parts) > 7 else "",
            ))
        except (ValueError, IndexError):
            continue
    return stations


# ---------------------------------------------------------------------------
# QThread workers
# ---------------------------------------------------------------------------

class EventFetchWorker(QThread):
    """Background worker that fetches seismic events from INGV API.

    Signals:
        finished (list): Emitted with parsed SeismicEvent list on success.
        error (str): Emitted with error message on failure.
        progress (str): Status message updates during fetch.
    """

    finished = pyqtSignal(list)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, url, parent=None):
        super().__init__(parent)
        self.url = url

    def run(self):
        """Execute the HTTP request and parse the response."""
        try:
            if not self.url.startswith("https://"):
                self.error.emit("URL non valido: sono permessi solo endpoint HTTPS")
                return
            self.progress.emit("Connessione a webservices.ingv.it...")
            req = urllib.request.Request(
                self.url,
                headers={"User-Agent": "QGIS-INGV-SeismicExplorer/0.1"}
            )
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:  # noqa: S310
                self.progress.emit("Download dati in corso...")
                raw = resp.read().decode("utf-8")

            self.progress.emit("Parsing eventi sismici...")
            events = parse_events(raw)
            self.finished.emit(events)

        except urllib.error.HTTPError as exc:
            if exc.code == 204:
                # No content = no events found (valid response)
                self.finished.emit([])
            else:
                self.error.emit(
                    f"Errore HTTP {exc.code}: {exc.reason}\n"
                    f"URL: {self.url}"
                )
        except urllib.error.URLError as exc:
            self.error.emit(
                f"Errore di rete: {exc.reason}\n"
                "Verificare la connessione internet."
            )
        except Exception as exc:
            self.error.emit(f"Errore imprevisto: {exc}")


class StationFetchWorker(QThread):
    """Background worker that fetches seismic stations from INGV API.

    Signals:
        finished (list): Emitted with parsed SeismicStation list on success.
        error (str): Emitted with error message on failure.
        progress (str): Status message updates during fetch.
    """

    finished = pyqtSignal(list)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, url, parent=None):
        super().__init__(parent)
        self.url = url

    def run(self):
        """Execute the HTTP request and parse the response."""
        try:
            if not self.url.startswith("https://"):
                self.error.emit("URL non valido: sono permessi solo endpoint HTTPS")
                return
            self.progress.emit("Download stazioni sismiche INGV...")
            req = urllib.request.Request(
                self.url,
                headers={"User-Agent": "QGIS-INGV-SeismicExplorer/0.1"}
            )
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:  # noqa: S310
                raw = resp.read().decode("utf-8")

            self.progress.emit("Parsing stazioni...")
            stations = parse_stations(raw)
            self.finished.emit(stations)

        except urllib.error.HTTPError as exc:
            self.error.emit(f"Errore HTTP {exc.code}: {exc.reason}")
        except urllib.error.URLError as exc:
            self.error.emit(f"Errore di rete: {exc.reason}")
        except Exception as exc:
            self.error.emit(f"Errore imprevisto: {exc}")
