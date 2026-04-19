# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A QGIS 3.20+ plugin (Python) that queries and visualizes earthquake and seismic station data from the [INGV FDSNWS web services](https://webservices.ingv.it/fdsnws/) directly within QGIS.

## Installation & Development

No build step — pure Python plugin. To install, copy the `ingv_seismic_explorer/` folder to:
- Linux: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
- Windows: `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\`

After editing `.py` files, restart QGIS or use the **Plugin Reloader** plugin to hot-reload.

There are no tests, no linter config, and no CI pipeline currently.

## Architecture

Seven Python modules with clean separation of concerns:

| Module | Role |
|--------|------|
| `__init__.py` + `main.py` | QGIS plugin lifecycle (`classFactory` → `initGui` → `run` → `unload`); singleton dialog management |
| `api_client.py` | FDSN URL builders, pipe-delimited text parsers, `QThread` workers for non-blocking HTTP |
| `layer_builder.py` | Creates in-memory `QgsVectorLayer` (EPSG:4326), sets temporal properties |
| `style_manager.py` | Graduated (magnitude), depth-colored, heatmap, and station renderers |
| `dialogs.py` | Main tabbed `QDialog` + custom `QgsMapTool` for interactive rectangle drawing |
| `analysis.py` | Gutenberg-Richter b-value, time series, depth histograms; matplotlib charts |

### Data flow

```
User sets filters → build_event_url() → EventFetchWorker (QThread)
    → urllib.request.urlopen() → parse_events() → SeismicEvent list
    → build_events_layer() → apply_*_style() → add_layer_to_project()
```

### Key design decisions

- **HTTP via `urllib`** (not `QgsNetworkAccessManager`) to keep threading simple inside `QThread` workers.
- **Singleton dialog** — `_dialog` is cached in `main.py`; never recreated after first `run()` call.
- **All geometries in EPSG:4326** — map extent is converted to WGS84 before querying.
- **Temporal Controller integration** uses `try/except` to handle API differences across QGIS versions ≥3.14.
- **Matplotlib backend** explicitly set to `Qt5Agg`; gracefully degraded if matplotlib is absent.

## External endpoints

| Service | Base URL |
|---------|----------|
| Events | `https://webservices.ingv.it/fdsnws/event/1/query` |
| Stations | `https://webservices.ingv.it/fdsnws/station/1/query` |

No API key required. Event queries are capped at 10,000 results. HTTP 204 is treated as a valid empty result.

## Dependencies

- **Required**: QGIS ≥ 3.20 (provides PyQt5, `qgis.core`, `qgis.gui`), Python 3.x stdlib only.
- **Optional**: matplotlib (bundled with QGIS 3.x) — used only in `analysis.py`; plugin works without it.
- No `requirements.txt` or package manager.
