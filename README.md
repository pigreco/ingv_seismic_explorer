# INGV Seismic Explorer — QGIS Plugin

Import and visualize seismic events and stations from the official
**INGV FDSNWS Web Services** directly inside QGIS.

## Features

- **Query seismic events** by date range, magnitude, depth and geographic area
- **Use current map extent** as search area with one click
- **Automatic graduated symbology** — circle size = magnitude, color = depth class
- **Import seismic stations** from Rete Sismica Nazionale (400+ stations, network IV)
- **No API key required** — data is completely open and free

## Installation

1. Download or clone this repository
2. Copy the `ingv_seismic_explorer/` folder to your QGIS plugins directory:
   - **Linux/macOS**: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
   - **Windows**: `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\`
3. Open QGIS → Plugins → Manage and Install Plugins → Installed
4. Enable **INGV Seismic Explorer**
5. Find it under menu **Web → INGV Seismic Explorer**

## Data Source

All data comes from the official INGV FDSNWS API:
- Events: `https://webservices.ingv.it/fdsnws/event/1/query`
- Stations: `https://webservices.ingv.it/fdsnws/station/1/query`

Standard: [FDSN Web Services](https://www.fdsn.org/webservices/)

## Requirements

- QGIS ≥ 3.20
- Internet connection

## License

GPLv2+ — see [LICENSE](LICENSE)
