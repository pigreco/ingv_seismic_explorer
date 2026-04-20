# INGV Seismic Explorer — QGIS Plugin

Import and visualize seismic events and stations from the official
**INGV FDSNWS Web Services** directly inside QGIS.

![version](https://img.shields.io/badge/version-0.3.2-blue)
![QGIS](https://img.shields.io/badge/QGIS-3.20%2B%20%7C%204.x-green)
![license](https://img.shields.io/badge/license-GPLv2%2B-lightgrey)

## Features

- **Query seismic events** by date range, magnitude, depth and geographic area
- **Use current map extent** or **draw a rectangle** on the map as search area
- **Multiple visualization styles** — graduated (magnitude), depth-colored, heatmap
- **Import seismic stations** from Rete Sismica Nazionale (400+ stations, network IV)
- **Export results** to GeoPackage, Shapefile or GeoJSON
- **Statistical analysis** — Gutenberg-Richter b-value, time series, depth histograms
- **No API key required** — data is completely open and free

## Requirements

- QGIS ≥ 3.20 or QGIS 4.x (Qt6 / PyQt6)
- Internet connection
- matplotlib (optional, bundled with QGIS) — required only for charts

## Installation

### From GitHub Release (recommended)

1. Download `ingv_seismic_explorer.zip` from the [latest release](https://github.com/pigreco/ingv_seismic_explorer/releases/latest)
2. QGIS → Plugins → Manage and Install Plugins → **Install from ZIP**
3. Select the downloaded ZIP and click **Install Plugin**
4. Enable **INGV Seismic Explorer**

### Manual install

1. Download or clone this repository
2. Copy the `ingv_seismic_explorer/` folder to your QGIS plugins directory:
   - **Linux/macOS**: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
   - **Windows**: `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\`
3. Enable **INGV Seismic Explorer** under Plugins → Manage and Install Plugins → Installed
4. Find it under menu **Web → INGV Seismic Explorer**

## Data Source

All data comes from the official INGV FDSNWS API:

| Service | URL |
|---------|-----|
| Events | `https://webservices.ingv.it/fdsnws/event/1/query` |
| Stations | `https://webservices.ingv.it/fdsnws/station/1/query` |

Standard: [FDSN Web Services](https://www.fdsn.org/webservices/)

## Changelog

### 0.3.2
- Security: use `# nosec B310` to suppress Bandit B310 on `urlopen` (`# noqa` is ignored by Bandit)

### 0.3.1
- Security: validate HTTPS scheme before `urllib.request.urlopen` (Bandit B310)

### 0.3.0
- Fix: campo `time` del layer eventi da `String` a `DateTime` (nativo QGIS)
- Fix: import `QgsInterval` da `qgis.core` — la durata visibilità nel Temporal Controller ora funziona correttamente

### 0.2.0
- QGIS 4 / Qt6 / PyQt6 compatibility: qualified enums, `QtAgg` matplotlib backend, dark-theme stylesheet fixes
- Added `qgisMaximumVersion=4.99`

### 0.1.0
- Initial release — core query, layer import and symbology

## License

GPLv2+ — see [LICENSE](LICENSE)
