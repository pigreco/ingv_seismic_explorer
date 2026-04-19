# -*- coding: utf-8 -*-
"""
Main plugin module.
Registers the INGV Seismic Explorer in the QGIS Web menu and toolbar.
"""

import os

from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import QCoreApplication


class INGVSeismicExplorer:
    """Main class for the INGV Seismic Explorer QGIS plugin.

    Adds a toolbar button and a Web menu entry that open the
    SeismicExplorerDialog for querying INGV seismic data.
    """

    def __init__(self, iface):
        """Initialize the plugin.

        Args:
            iface: A QGIS QgisInterface instance providing access to the
                QGIS GUI and core functionality.
        """
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.menu = self.tr("&INGV Seismic Explorer")
        self.toolbar = None
        self._dialog = None

    # ------------------------------------------------------------------
    # Translation helper
    # ------------------------------------------------------------------

    def tr(self, message):
        """Translate a string using Qt translation API.

        Args:
            message (str): String to translate.

        Returns:
            str: Translated string.
        """
        return QCoreApplication.translate("INGVSeismicExplorer", message)

    # ------------------------------------------------------------------
    # Action factory
    # ------------------------------------------------------------------

    def _add_action(
        self,
        icon_path,
        text,
        callback,
        enabled=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None,
    ):
        """Create a QAction and register it in the Web menu and toolbar.

        Args:
            icon_path (str): Absolute path to the action icon.
            text (str): Label shown in menu and tooltip.
            callback: Slot connected to the action's triggered signal.
            enabled (bool): Whether the action is enabled at startup.
            add_to_menu (bool): Add to QGIS Web menu.
            add_to_toolbar (bool): Add to plugin toolbar.
            status_tip (str, optional): Status bar tip.
            whats_this (str, optional): 'What's This?' help text.
            parent: Parent QWidget (defaults to QGIS main window).

        Returns:
            QAction: The created action.
        """
        icon = QIcon(icon_path)
        action = QAction(icon, text, parent or self.iface.mainWindow())
        action.triggered.connect(callback)
        action.setEnabled(enabled)

        if status_tip:
            action.setStatusTip(status_tip)
        if whats_this:
            action.setWhatsThis(whats_this)

        if add_to_toolbar and self.toolbar:
            self.toolbar.addAction(action)
        if add_to_menu:
            self.iface.addPluginToWebMenu(self.menu, action)

        self.actions.append(action)
        return action

    # ------------------------------------------------------------------
    # QGIS lifecycle
    # ------------------------------------------------------------------

    def initGui(self):
        """Create menu entries and toolbar icons when plugin is loaded."""
        self.toolbar = self.iface.addToolBar("INGV Seismic Explorer")
        self.toolbar.setObjectName("INGVSeismicExplorerToolbar")

        icon_path = os.path.join(self.plugin_dir, "icon.png")
        if not os.path.exists(icon_path):
            # Fallback: use a built-in QGIS icon if custom one is missing
            icon_path = ":/images/themes/default/mActionZoomIn.svg"

        self._add_action(
            icon_path=icon_path,
            text=self.tr("INGV Seismic Explorer"),
            callback=self.run,
            status_tip=self.tr(
                "Apri il pannello per scaricare terremoti e stazioni INGV"
            ),
            whats_this=self.tr(
                "Scarica eventi sismici e stazioni dalla Rete Sismica Nazionale "
                "tramite i Web Services INGV FDSNWS."
            ),
            parent=self.iface.mainWindow(),
        )

    def unload(self):
        """Remove menu entries and toolbar icons when plugin is unloaded."""
        for action in self.actions:
            self.iface.removePluginWebMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)

        if self.toolbar:
            del self.toolbar
            self.toolbar = None

        self.actions.clear()

        # Close open dialog if any
        if self._dialog:
            self._dialog.close()
            self._dialog = None

    # ------------------------------------------------------------------
    # Main action
    # ------------------------------------------------------------------

    def run(self):
        """Open the INGV Seismic Explorer dialog.

        The dialog is created once and reused on subsequent calls
        (non-modal, singleton pattern).
        """
        from .dialogs import SeismicExplorerDialog

        if self._dialog is None:
            self._dialog = SeismicExplorerDialog(
                iface=self.iface,
                parent=self.iface.mainWindow(),
            )
            # Reset reference when dialog is closed
            self._dialog.finished.connect(self._on_dialog_closed)

        self._dialog.show()
        self._dialog.raise_()
        self._dialog.activateWindow()

    def _on_dialog_closed(self):
        """Clear dialog reference when the user closes it."""
        self._dialog = None
