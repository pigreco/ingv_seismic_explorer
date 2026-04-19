# -*- coding: utf-8 -*-
"""
INGV Seismic Explorer
Import and visualize seismic events from INGV FDSNWS web services in QGIS.
"""


def classFactory(iface):
    """Load INGVSeismicExplorer class from main module.

    Args:
        iface: A QGIS interface instance (QgisInterface).

    Returns:
        INGVSeismicExplorer: The main plugin instance.
    """
    from .main import INGVSeismicExplorer
    return INGVSeismicExplorer(iface)
