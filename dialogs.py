# -*- coding: utf-8 -*-
"""
Dialogs module.
Main query dialog for the INGV Seismic Explorer plugin.
Allows users to configure filters and trigger data download.
"""

from datetime import datetime, timedelta

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QGroupBox,
    QDateTimeEdit, QDoubleSpinBox, QSpinBox,
    QComboBox, QCheckBox, QProgressBar,
    QTabWidget, QWidget, QMessageBox,
    QSizePolicy, QFrame, QScrollArea,
)
from qgis.PyQt.QtCore import Qt, QDateTime, QDate, QTime, pyqtSignal
from qgis.PyQt.QtGui import QColor, QCursor, QFont

from qgis.core import QgsProject, QgsRectangle, QgsCoordinateTransform, QgsCoordinateReferenceSystem
from qgis.gui import QgsMapTool, QgsRubberBand


# ---------------------------------------------------------------------------
# Custom map tool: draw a rectangle on the canvas
# ---------------------------------------------------------------------------

class DrawRectangleTool(QgsMapTool):
    """Interactive map tool that lets the user draw a bounding box.

    The user clicks and drags on the map canvas. On mouse release the
    tool emits ``rectangleDrawn(QgsRectangle)`` with the drawn extent
    in the canvas CRS, then deactivates itself and restores the
    previous map tool.

    Signals:
        rectangleDrawn (QgsRectangle): Emitted when the user releases
            the mouse after drawing a valid rectangle.
        drawingCancelled (): Emitted when the user presses Escape.
    """

    rectangleDrawn   = pyqtSignal(object)   # QgsRectangle
    drawingCancelled = pyqtSignal()

    def __init__(self, canvas, previous_tool=None):
        super().__init__(canvas)
        self._canvas        = canvas
        self._previous_tool = previous_tool
        self._rubber_band   = None
        self._start_point   = None
        self._drawing       = False
        self.setCursor(QCursor(Qt.CrossCursor))

    # ------------------------------------------------------------------
    # Mouse events
    # ------------------------------------------------------------------

    def canvasPressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._start_point = self.toMapCoordinates(event.pos())
            self._drawing = True
            self._init_rubber_band()

    def canvasMoveEvent(self, event):
        if self._drawing and self._start_point:
            end = self.toMapCoordinates(event.pos())
            self._update_rubber_band(end)

    def canvasReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._drawing:
            end = self.toMapCoordinates(event.pos())
            self._drawing = False
            self._clear_rubber_band()

            rect = QgsRectangle(self._start_point, end)
            rect.normalize()

            if not rect.isEmpty():
                self.rectangleDrawn.emit(rect)

            self._restore_previous_tool()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._drawing = False
            self._clear_rubber_band()
            self.drawingCancelled.emit()
            self._restore_previous_tool()

    # ------------------------------------------------------------------
    # Rubber band helpers
    # ------------------------------------------------------------------

    def _init_rubber_band(self):
        from qgis.core import QgsWkbTypes
        self._clear_rubber_band()
        self._rubber_band = QgsRubberBand(self._canvas, QgsWkbTypes.PolygonGeometry)
        self._rubber_band.setColor(QColor(220, 50, 50, 160))
        self._rubber_band.setFillColor(QColor(220, 50, 50, 40))
        self._rubber_band.setWidth(2)

    def _update_rubber_band(self, end_point):
        if self._rubber_band is None or self._start_point is None:
            return
        from qgis.core import QgsPointXY
        rect = QgsRectangle(self._start_point, end_point)
        self._rubber_band.setToGeometry(
            __import__("qgis.core", fromlist=["QgsGeometry"]).QgsGeometry.fromRect(rect),
            None,
        )

    def _clear_rubber_band(self):
        if self._rubber_band:
            self._canvas.scene().removeItem(self._rubber_band)
            self._rubber_band = None

    def _restore_previous_tool(self):
        if self._previous_tool:
            self._canvas.setMapTool(self._previous_tool)
        else:
            self._canvas.unsetMapTool(self)

from .api_client import (
    build_event_url,
    build_station_url,
    EventFetchWorker,
    StationFetchWorker,
)
from .layer_builder import (
    build_events_layer, build_stations_layer, add_layer_to_project,
    enable_temporal_properties, build_events_layer_temporal,
)
from .style_manager import apply_heatmap_style
from .analysis import AnalysisDialog


# ---------------------------------------------------------------------------
# Main dialog
# ---------------------------------------------------------------------------

class SeismicExplorerDialog(QDialog):
    """Main query dialog for INGV Seismic Explorer.

    Provides tabbed UI for:
      - Tab 1: Seismic events query (date, magnitude, depth, area filters)
      - Tab 2: Seismic stations import
    """

    def __init__(self, iface, parent=None):
        """Initialize dialog.

        Args:
            iface: QGIS interface instance.
            parent: Parent QWidget.
        """
        super().__init__(parent)
        self.iface = iface
        self._worker = None
        self._last_events = []
        self._drawn_extent = None   # QgsRectangle captured by DrawRectangleTool

        self.setWindowTitle("INGV Seismic Explorer")
        self.setMinimumWidth(480)
        self.setMinimumHeight(700)
        self.resize(500, 720)
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self):
        """Build the full dialog UI."""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(12, 12, 12, 12)

        # Header
        header = QLabel("🔴 INGV Seismic Explorer")
        header_font = QFont()
        header_font.setPointSize(13)
        header_font.setBold(True)
        header.setFont(header_font)
        main_layout.addWidget(header)

        subtitle = QLabel(
            "Dati sismici ufficiali — INGV FDSNWS Web Services  |  "
            "<a href='https://webservices.ingv.it'>webservices.ingv.it</a>"
        )
        subtitle.setOpenExternalLinks(True)
        subtitle.setStyleSheet("color: gray; font-size: 10pt;")
        main_layout.addWidget(subtitle)

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(separator)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_events_tab(), "🌍  Terremoti")
        self.tabs.addTab(self._build_stations_tab(), "📡  Stazioni")
        self.tabs.addTab(self._build_advanced_tab(), "🔬  Analisi")
        self.tabs.addTab(self._build_guide_tab(), "📖  Guida")
        main_layout.addWidget(self.tabs)

        # Status bar
        self.status_label = QLabel("Pronto.")
        self.status_label.setStyleSheet("color: #555; font-size: 9pt;")
        main_layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)   # indeterminate
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(14)
        main_layout.addWidget(self.progress_bar)

        # Bottom buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.btn_close = QPushButton("Chiudi")
        self.btn_close.clicked.connect(self.close)
        btn_row.addWidget(self.btn_close)

        self.btn_download = QPushButton("⬇  Scarica Terremoti")
        self.btn_download.setDefault(True)
        self.btn_download.setStyleSheet(
            "QPushButton { background-color: #c0392b; color: white; "
            "font-weight: bold; padding: 6px 18px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #e74c3c; }"
            "QPushButton:disabled { background-color: #aaa; }"
        )
        self.btn_download.clicked.connect(self._on_download_events)
        btn_row.addWidget(self.btn_download)

        main_layout.addLayout(btn_row)

    def _build_events_tab(self):
        """Build the 'Terremoti' tab content."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)
        layout.setContentsMargins(8, 8, 8, 8)

        # --- Date range ---
        grp_date = QGroupBox("Intervallo temporale")
        date_grid = QGridLayout(grp_date)

        date_grid.addWidget(QLabel("Da:"), 0, 0)
        self.dt_start = QDateTimeEdit()
        self.dt_start.setCalendarPopup(True)
        self.dt_start.setDisplayFormat("dd/MM/yyyy HH:mm")
        default_start = QDateTime(QDate.currentDate().addDays(-30), QTime(0, 0))
        self.dt_start.setDateTime(default_start)
        date_grid.addWidget(self.dt_start, 0, 1)

        date_grid.addWidget(QLabel("A:"), 1, 0)
        self.dt_end = QDateTimeEdit()
        self.dt_end.setCalendarPopup(True)
        self.dt_end.setDisplayFormat("dd/MM/yyyy HH:mm")
        self.dt_end.setDateTime(QDateTime.currentDateTime())
        date_grid.addWidget(self.dt_end, 1, 1)

        # Quick presets
        preset_row = QHBoxLayout()
        for label, days in [("Oggi", 0), ("7 giorni", 7), ("30 giorni", 30), ("1 anno", 365)]:
            btn = QPushButton(label)
            btn.setFixedHeight(22)
            btn.clicked.connect(lambda checked, d=days: self._set_date_preset(d))
            preset_row.addWidget(btn)
        date_grid.addLayout(preset_row, 2, 0, 1, 2)
        layout.addWidget(grp_date)

        # --- Magnitude ---
        grp_mag = QGroupBox("Magnitudo")
        mag_grid = QGridLayout(grp_mag)

        mag_grid.addWidget(QLabel("Min:"), 0, 0)
        self.spin_mag_min = QDoubleSpinBox()
        self.spin_mag_min.setRange(-1.0, 9.9)
        self.spin_mag_min.setValue(2.0)
        self.spin_mag_min.setSingleStep(0.5)
        self.spin_mag_min.setDecimals(1)
        mag_grid.addWidget(self.spin_mag_min, 0, 1)

        mag_grid.addWidget(QLabel("Max:"), 0, 2)
        self.spin_mag_max = QDoubleSpinBox()
        self.spin_mag_max.setRange(-1.0, 10.0)
        self.spin_mag_max.setValue(10.0)
        self.spin_mag_max.setSingleStep(0.5)
        self.spin_mag_max.setDecimals(1)
        mag_grid.addWidget(self.spin_mag_max, 0, 3)
        layout.addWidget(grp_mag)

        # --- Depth ---
        grp_depth = QGroupBox("Profondità ipocentrale (km)")
        depth_grid = QGridLayout(grp_depth)

        depth_grid.addWidget(QLabel("Min:"), 0, 0)
        self.spin_depth_min = QSpinBox()
        self.spin_depth_min.setRange(0, 700)
        self.spin_depth_min.setValue(0)
        self.spin_depth_min.setSuffix(" km")
        depth_grid.addWidget(self.spin_depth_min, 0, 1)

        depth_grid.addWidget(QLabel("Max:"), 0, 2)
        self.spin_depth_max = QSpinBox()
        self.spin_depth_max.setRange(0, 700)
        self.spin_depth_max.setValue(700)
        self.spin_depth_max.setSuffix(" km")
        depth_grid.addWidget(self.spin_depth_max, 0, 3)
        layout.addWidget(grp_depth)

        # --- Area ---
        grp_area = QGroupBox("Area geografica")
        area_layout = QVBoxLayout(grp_area)

        self.combo_area = QComboBox()
        self.combo_area.addItems([
            "Tutta Italia (bbox predefinito)",
            "Usa extent mappa corrente",
            "Coordinate personalizzate",
            "Disegna a schermo",
            "Nessun filtro area (tutto il mondo)",
        ])
        self.combo_area.currentIndexChanged.connect(self._on_area_changed)
        area_layout.addWidget(self.combo_area)

        # Widget: disegna a schermo (index 3)
        self.draw_area_widget = QWidget()
        draw_vbox = QVBoxLayout(self.draw_area_widget)
        draw_vbox.setContentsMargins(0, 6, 0, 2)
        draw_vbox.setSpacing(4)

        self.btn_draw = QPushButton("✏  Clicca e trascina sulla mappa")
        self.btn_draw.setStyleSheet(
            "QPushButton { background-color: #8e44ad; color: white; "
            "font-weight: bold; padding: 5px 14px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #9b59b6; }"
        )
        self.btn_draw.clicked.connect(self._on_start_draw)
        draw_vbox.addWidget(self.btn_draw)

        self.lbl_drawn_extent = QLabel("Nessuna area disegnata.")
        self.lbl_drawn_extent.setStyleSheet("color: #666; font-size: 9pt; padding: 2px 0;")
        draw_vbox.addWidget(self.lbl_drawn_extent)

        self.draw_area_widget.setVisible(False)
        area_layout.addWidget(self.draw_area_widget)

        # Custom coordinates (shown only when mode = "Coordinate personalizzate")
        self.custom_area_widget = QWidget()
        custom_vbox = QVBoxLayout(self.custom_area_widget)
        custom_vbox.setContentsMargins(0, 6, 0, 2)
        custom_vbox.setSpacing(6)

        # Row 1: Latitudini
        lat_row = QHBoxLayout()
        lat_row.setSpacing(8)
        lbl_min_lat = QLabel("Lat min:")
        lbl_min_lat.setFixedWidth(55)
        self.spin_min_lat = QDoubleSpinBox()
        self.spin_min_lat.setRange(-90, 90)
        self.spin_min_lat.setValue(35.0)
        self.spin_min_lat.setDecimals(3)
        self.spin_min_lat.setFixedWidth(90)
        lbl_max_lat = QLabel("Lat max:")
        lbl_max_lat.setFixedWidth(55)
        self.spin_max_lat = QDoubleSpinBox()
        self.spin_max_lat.setRange(-90, 90)
        self.spin_max_lat.setValue(47.5)
        self.spin_max_lat.setDecimals(3)
        self.spin_max_lat.setFixedWidth(90)
        lat_row.addWidget(lbl_min_lat)
        lat_row.addWidget(self.spin_min_lat)
        lat_row.addSpacing(10)
        lat_row.addWidget(lbl_max_lat)
        lat_row.addWidget(self.spin_max_lat)
        lat_row.addStretch()
        custom_vbox.addLayout(lat_row)

        # Row 2: Longitudini
        lon_row = QHBoxLayout()
        lon_row.setSpacing(8)
        lbl_min_lon = QLabel("Lon min:")
        lbl_min_lon.setFixedWidth(55)
        self.spin_min_lon = QDoubleSpinBox()
        self.spin_min_lon.setRange(-180, 180)
        self.spin_min_lon.setValue(6.0)
        self.spin_min_lon.setDecimals(3)
        self.spin_min_lon.setFixedWidth(90)
        lbl_max_lon = QLabel("Lon max:")
        lbl_max_lon.setFixedWidth(55)
        self.spin_max_lon = QDoubleSpinBox()
        self.spin_max_lon.setRange(-180, 180)
        self.spin_max_lon.setValue(19.0)
        self.spin_max_lon.setDecimals(3)
        self.spin_max_lon.setFixedWidth(90)
        lon_row.addWidget(lbl_min_lon)
        lon_row.addWidget(self.spin_min_lon)
        lon_row.addSpacing(10)
        lon_row.addWidget(lbl_max_lon)
        lon_row.addWidget(self.spin_max_lon)
        lon_row.addStretch()
        custom_vbox.addLayout(lon_row)

        self.custom_area_widget.setVisible(False)
        area_layout.addWidget(self.custom_area_widget)
        layout.addWidget(grp_area)

        # --- Options ---
        grp_opts = QGroupBox("Opzioni layer")
        opts_layout = QVBoxLayout(grp_opts)

        self.chk_depth_style = QCheckBox("Colora per profondità (invece che magnitudo)")
        opts_layout.addWidget(self.chk_depth_style)

        limit_row = QHBoxLayout()
        limit_row.addWidget(QLabel("Limite eventi:"))
        self.spin_limit = QSpinBox()
        self.spin_limit.setRange(1, 10000)
        self.spin_limit.setValue(5000)
        limit_row.addWidget(self.spin_limit)
        limit_row.addStretch()
        opts_layout.addLayout(limit_row)
        layout.addWidget(grp_opts)

        layout.addStretch()
        return tab

    def _build_stations_tab(self):
        """Build the 'Stazioni' tab content."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)

        info = QLabel(
            "Importa le stazioni della <b>Rete Sismica Nazionale (rete IV)</b> "
            "come layer punto in QGIS.\n\n"
            "Ogni stazione include: codice, nome sito, quota, coordinate "
            "e date operative."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        grp = QGroupBox("Rete sismica")
        grp_layout = QGridLayout(grp)
        grp_layout.addWidget(QLabel("Rete FDSN:"), 0, 0)
        self.combo_network = QComboBox()
        self.combo_network.addItems(["IV  (Rete Sismica Nazionale)", "MN  (MedNet)", "IT  (INGV Nazionale)"])
        grp_layout.addWidget(self.combo_network, 0, 1)
        layout.addWidget(grp)

        self.btn_download_stations = QPushButton("📡  Scarica Stazioni Sismiche")
        self.btn_download_stations.setStyleSheet(
            "QPushButton { background-color: #2980b9; color: white; "
            "font-weight: bold; padding: 6px 18px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #3498db; }"
            "QPushButton:disabled { background-color: #aaa; }"
        )
        self.btn_download_stations.clicked.connect(self._on_download_stations)
        layout.addWidget(self.btn_download_stations)

        layout.addStretch()
        return tab

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _set_date_preset(self, days):
        """Set start date to N days ago, end to now."""
        now = QDateTime.currentDateTime()
        self.dt_end.setDateTime(now)
        if days == 0:
            start = QDateTime(QDate.currentDate(), QTime(0, 0))
        else:
            start = now.addDays(-days)
        self.dt_start.setDateTime(start)

    def _on_area_changed(self, index):
        """Show/hide coordinate/draw widgets based on area selection."""
        self.custom_area_widget.setVisible(index == 2)
        self.draw_area_widget.setVisible(index == 3)
        self.adjustSize()

    def _get_area_params(self):
        """Return area filter kwargs for build_event_url based on UI selection.

        Returns:
            dict: Keyword arguments to pass to build_event_url.
        """
        mode = self.combo_area.currentIndex()

        if mode == 0:
            # Tutta Italia
            return dict(min_lat=35.0, max_lat=47.5, min_lon=6.0, max_lon=19.5)

        elif mode == 1:
            # Extent mappa corrente
            canvas = self.iface.mapCanvas()
            ext = canvas.extent()
            try:
                src_crs = canvas.mapSettings().destinationCrs()
                wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
                if src_crs != wgs84:
                    transform = QgsCoordinateTransform(
                        src_crs, wgs84, QgsProject.instance()
                    )
                    ext = transform.transformBoundingBox(ext)
            except Exception:
                pass
            return dict(
                min_lat=round(ext.yMinimum(), 5),
                max_lat=round(ext.yMaximum(), 5),
                min_lon=round(ext.xMinimum(), 5),
                max_lon=round(ext.xMaximum(), 5),
            )

        elif mode == 2:
            # Coordinate personalizzate
            return dict(
                min_lat=self.spin_min_lat.value(),
                max_lat=self.spin_max_lat.value(),
                min_lon=self.spin_min_lon.value(),
                max_lon=self.spin_max_lon.value(),
            )

        elif mode == 3:
            # Disegna a schermo — usa l'extent catturato da DrawRectangleTool
            if self._drawn_extent is None:
                return None   # segnale di errore: area non disegnata
            ext = self._drawn_extent
            try:
                src_crs = self.iface.mapCanvas().mapSettings().destinationCrs()
                wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
                if src_crs != wgs84:
                    transform = QgsCoordinateTransform(
                        src_crs, wgs84, QgsProject.instance()
                    )
                    ext = transform.transformBoundingBox(ext)
            except Exception:
                pass
            return dict(
                min_lat=round(ext.yMinimum(), 5),
                max_lat=round(ext.yMaximum(), 5),
                min_lon=round(ext.xMinimum(), 5),
                max_lon=round(ext.xMaximum(), 5),
            )

        else:
            # Nessun filtro (index 4)
            return {}

    def _validate_event_params(self):
        """Validate form inputs before sending the API request.

        Returns:
            bool: True if valid, False otherwise (shows warning dialog).
        """
        if self.dt_start.dateTime() >= self.dt_end.dateTime():
            QMessageBox.warning(
                self, "Parametri non validi",
                "La data di inizio deve essere precedente alla data di fine."
            )
            return False
        if self.spin_mag_min.value() > self.spin_mag_max.value():
            QMessageBox.warning(
                self, "Parametri non validi",
                "La magnitudo minima non può essere maggiore di quella massima."
            )
            return False
        if self.spin_depth_min.value() > self.spin_depth_max.value():
            QMessageBox.warning(
                self, "Parametri non validi",
                "La profondità minima non può essere maggiore di quella massima."
            )
            return False
        if self.combo_area.currentIndex() == 3 and self._drawn_extent is None:
            QMessageBox.warning(
                self, "Area non disegnata",
                "Hai selezionato 'Disegna a schermo' ma non hai ancora disegnato "
                "nessuna area.\n\nClicca il pulsante viola e trascina un rettangolo "
                "sulla mappa, poi riprova."
            )
            return False
        return True

    def _on_start_draw(self):
        """Hide the dialog, activate DrawRectangleTool on the map canvas."""
        canvas = self.iface.mapCanvas()
        previous_tool = canvas.mapTool()

        tool = DrawRectangleTool(canvas, previous_tool=previous_tool)
        tool.rectangleDrawn.connect(self._on_rectangle_drawn)
        tool.drawingCancelled.connect(self._on_draw_cancelled)

        # Hide dialog so the canvas is fully accessible
        self.hide()
        canvas.setMapTool(tool)
        canvas.setFocus()

    def _on_rectangle_drawn(self, rect):
        """Receive the drawn rectangle, update UI, restore dialog."""
        self._drawn_extent = rect

        # Show feedback label with WGS84 coordinates if possible
        try:
            src_crs = self.iface.mapCanvas().mapSettings().destinationCrs()
            wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
            ext = rect
            if src_crs != wgs84:
                transform = QgsCoordinateTransform(src_crs, wgs84, QgsProject.instance())
                ext = transform.transformBoundingBox(rect)
            self.lbl_drawn_extent.setText(
                f"✅  {ext.yMinimum():.3f}°N – {ext.yMaximum():.3f}°N  |  "
                f"{ext.xMinimum():.3f}°E – {ext.xMaximum():.3f}°E"
            )
            self.lbl_drawn_extent.setStyleSheet("color: #27ae60; font-size: 9pt; padding: 2px 0;")
        except Exception:
            self.lbl_drawn_extent.setText("✅  Area disegnata.")
            self.lbl_drawn_extent.setStyleSheet("color: #27ae60; font-size: 9pt; padding: 2px 0;")

        self.btn_draw.setText("✏  Ridisegna area")
        self.show()
        self.raise_()
        self.activateWindow()

    def _on_draw_cancelled(self):
        """Restore dialog after user pressed Escape."""
        self.show()
        self.raise_()
        self.activateWindow()

    def _set_busy(self, busy):
        """Enable/disable UI controls during data fetch."""
        self.btn_download.setEnabled(not busy)
        self.btn_download_stations.setEnabled(not busy)
        self.btn_close.setEnabled(not busy)
        self.progress_bar.setVisible(busy)

    # ------------------------------------------------------------------
    # Download: events
    # ------------------------------------------------------------------

    def _on_download_events(self):
        """Build URL, start worker thread and connect signals."""
        if not self._validate_event_params():
            return

        start = self.dt_start.dateTime().toPyDateTime()
        end = self.dt_end.dateTime().toPyDateTime()
        area = self._get_area_params()

        # None means "draw on screen" was chosen but no area was drawn
        if area is None:
            return

        url = build_event_url(
            start_time=start,
            end_time=end,
            min_magnitude=self.spin_mag_min.value(),
            max_magnitude=self.spin_mag_max.value(),
            min_depth=self.spin_depth_min.value(),
            max_depth=self.spin_depth_max.value(),
            limit=self.spin_limit.value(),
            **area,
        )

        self._set_busy(True)
        self.status_label.setText(f"Query: {url[:80]}...")

        self._worker = EventFetchWorker(url, parent=self)
        self._worker.progress.connect(self._on_worker_progress)
        self._worker.finished.connect(self._on_events_ready)
        self._worker.error.connect(self._on_worker_error)
        self._worker.start()

    def _on_events_ready(self, events):
        """Handle successful event fetch: build and add layer."""
        self._set_busy(False)
        self._last_events = events   # keep for analysis

        if not events:
            self.status_label.setText("Nessun evento trovato per i filtri selezionati.")
            QMessageBox.information(
                self, "Nessun risultato",
                "La query non ha restituito eventi sismici.\n"
                "Prova ad allargare l'intervallo di date o abbassare la magnitudo minima."
            )
            return

        # Build layer name from time range
        start_str = self.dt_start.dateTime().toString("dd/MM/yy")
        end_str = self.dt_end.dateTime().toString("dd/MM/yy")
        layer_name = f"INGV Terremoti {start_str}–{end_str} (M≥{self.spin_mag_min.value():.1f})"

        layer = build_events_layer(events, layer_name=layer_name)

        # Apply depth style if requested
        if self.chk_depth_style.isChecked():
            from .style_manager import apply_event_depth_style
            apply_event_depth_style(layer)

        add_layer_to_project(layer)

        self.status_label.setText(
            f"✅ {len(events)} eventi caricati → layer: \"{layer_name}\""
        )
        self.iface.mapCanvas().refresh()

    # ------------------------------------------------------------------
    # Download: stations
    # ------------------------------------------------------------------

    def _on_download_stations(self):
        """Start the station fetch worker."""
        network_code = self.combo_network.currentText().split()[0]
        url = build_station_url(network=network_code)

        self._set_busy(True)
        self.status_label.setText("Download stazioni in corso...")

        self._worker = StationFetchWorker(url, parent=self)
        self._worker.progress.connect(self._on_worker_progress)
        self._worker.finished.connect(self._on_stations_ready)
        self._worker.error.connect(self._on_worker_error)
        self._worker.start()

    def _on_stations_ready(self, stations):
        """Handle successful station fetch: build and add layer."""
        self._set_busy(False)

        if not stations:
            self.status_label.setText("Nessuna stazione trovata.")
            return

        network_code = self.combo_network.currentText().split()[0]
        layer_name = f"INGV Stazioni Sismiche ({network_code})"
        layer = build_stations_layer(stations, layer_name=layer_name)
        add_layer_to_project(layer)

        self.status_label.setText(
            f"✅ {len(stations)} stazioni caricate → layer: \"{layer_name}\""
        )
        self.iface.mapCanvas().refresh()

    # ------------------------------------------------------------------
    # Shared worker signal handlers
    # ------------------------------------------------------------------

    def _on_worker_progress(self, message):
        """Update status label with worker progress message."""
        self.status_label.setText(message)

    def _on_worker_error(self, message):
        """Handle worker error: show dialog and re-enable UI."""
        self._set_busy(False)
        self.status_label.setText("❌ Errore durante il download.")
        QMessageBox.critical(self, "Errore INGV API", message)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        """Ensure background worker is stopped before closing."""
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(2000)
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Fase 2: Analisi tab
    # ------------------------------------------------------------------

    def _build_advanced_tab(self):
        """Build the 'Analisi' tab — Fase 2 features."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)

        # ---- Heatmap ----
        grp_heatmap = QGroupBox("🔥  Heatmap sismicità")
        h_layout = QVBoxLayout(grp_heatmap)

        h_layout.addWidget(QLabel(
            "Trasforma il layer eventi attivo in una heatmap kernel density.\n"
            "Il colore mostra la concentrazione degli epicentri nell'area."
        ))

        radius_row = QHBoxLayout()
        radius_row.addWidget(QLabel("Raggio kernel (mm):"))
        self.spin_heatmap_radius = QDoubleSpinBox()
        self.spin_heatmap_radius.setRange(1.0, 50.0)
        self.spin_heatmap_radius.setValue(8.0)
        self.spin_heatmap_radius.setSingleStep(1.0)
        radius_row.addWidget(self.spin_heatmap_radius)
        radius_row.addStretch()
        h_layout.addLayout(radius_row)

        weight_row = QHBoxLayout()
        weight_row.addWidget(QLabel("Peso per campo:"))
        self.combo_heatmap_weight = QComboBox()
        self.combo_heatmap_weight.addItems(["Nessuno (uniforme)", "magnitude", "depth_km"])
        weight_row.addWidget(self.combo_heatmap_weight)
        weight_row.addStretch()
        h_layout.addLayout(weight_row)

        btn_heatmap = QPushButton("🔥  Applica Heatmap al layer selezionato")
        btn_heatmap.clicked.connect(self._on_apply_heatmap)
        h_layout.addWidget(btn_heatmap)

        layout.addWidget(grp_heatmap)

        # ---- Temporal animation ----
        grp_temporal = QGroupBox("⏱  Animazione temporale (QGIS Temporal Controller)")
        t_layout = QVBoxLayout(grp_temporal)

        t_layout.addWidget(QLabel(
            "Abilita le proprietà temporali sul layer selezionato.\n"
            "Poi apri il Temporal Controller (Visualizza → Pannelli → Temporal Controller)\n"
            "e premi Play per animare la sequenza degli eventi nel tempo."
        ))

        dur_row = QHBoxLayout()
        dur_row.addWidget(QLabel("Durata visibilità evento:"))
        self.combo_event_duration = QComboBox()
        self.combo_event_duration.addItems([
            "1 ora", "6 ore", "12 ore", "1 giorno", "1 settimana"
        ])
        dur_row.addWidget(self.combo_event_duration)
        dur_row.addStretch()
        t_layout.addLayout(dur_row)

        btn_temporal = QPushButton("⏱  Abilita animazione temporale")
        btn_temporal.clicked.connect(self._on_enable_temporal)
        t_layout.addWidget(btn_temporal)

        layout.addWidget(grp_temporal)

        # ---- Grafici ----
        grp_charts = QGroupBox("📊  Analisi statistica (Gutenberg-Richter + serie temporale)")
        c_layout = QVBoxLayout(grp_charts)

        c_layout.addWidget(QLabel(
            "Apre la finestra di analisi con grafici interattivi sull'ultimo\n"
            "set di terremoti scaricato (tab Terremoti)."
        ))

        btn_charts = QPushButton("📊  Apri grafici di analisi")
        btn_charts.clicked.connect(self._on_open_analysis)
        c_layout.addWidget(btn_charts)

        layout.addWidget(grp_charts)

        layout.addStretch()
        return tab

    # ------------------------------------------------------------------
    # Fase 2 handlers
    # ------------------------------------------------------------------

    def _get_active_ingv_layer(self):
        """Return the currently selected layer if it is an INGV events layer.

        Returns:
            QgsVectorLayer | None
        """
        layer = self.iface.activeLayer()
        if layer is None:
            QMessageBox.warning(
                self, "Nessun layer selezionato",
                "Seleziona prima un layer INGV terremoti nel pannello Layer."
            )
            return None
        if not hasattr(layer, "dataProvider"):
            QMessageBox.warning(
                self, "Layer non valido",
                "Il layer selezionato non è un layer vettoriale."
            )
            return None
        return layer

    def _on_apply_heatmap(self):
        """Apply heatmap renderer to the currently active layer."""
        layer = self._get_active_ingv_layer()
        if layer is None:
            return

        radius = self.spin_heatmap_radius.value()
        weight_idx = self.combo_heatmap_weight.currentIndex()
        weight_field = None if weight_idx == 0 else self.combo_heatmap_weight.currentText()

        try:
            apply_heatmap_style(layer, radius_mm=radius, weight_field=weight_field)
            self.status_label.setText(
                f"✅ Heatmap applicata a \"{layer.name()}\" "
                f"(raggio {radius:.0f} mm"
                + (f", peso: {weight_field}" if weight_field else "") + ")"
            )
            self.iface.mapCanvas().refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Errore heatmap", str(exc))

    def _on_enable_temporal(self):
        """Enable temporal properties on the active layer."""
        layer = self._get_active_ingv_layer()
        if layer is None:
            return

        # Map combo index to seconds
        duration_map = {0: 3600, 1: 21600, 2: 43200, 3: 86400, 4: 604800}
        duration_secs = duration_map.get(self.combo_event_duration.currentIndex(), 3600)

        try:
            from qgis.core import QgsVectorLayerTemporalProperties
            props = layer.temporalProperties()
            if props is None:
                raise RuntimeError("Layer non supporta proprietà temporali.")

            props.setIsActive(True)
            props.setMode(
                QgsVectorLayerTemporalProperties.ModeFeatureDateTimeInstantFromField
            )
            props.setStartField("time")

            # Set fixed duration
            try:
                from qgis.core import QgsInterval
                props.setFixedDuration(QgsInterval(duration_secs))
            except Exception:
                pass

            layer.triggerRepaint()
            self.status_label.setText(
                f"✅ Animazione temporale abilitata su \"{layer.name()}\". "
                "Apri il Temporal Controller e premi Play."
            )
        except Exception as exc:
            QMessageBox.critical(
                self, "Errore temporal",
                f"Impossibile abilitare le proprietà temporali:\n{exc}\n\n"
                "Richiede QGIS ≥ 3.14 e un layer con campo 'time'."
            )

    def _events_from_active_layer(self):
        """Read SeismicEvent objects from the currently active QGIS layer.

        Used as fallback when _last_events is empty (e.g. after dialog reopen).
        Reconstructs events from the layer attribute table, so the analysis
        works on any INGV events layer already loaded in the project.

        Returns:
            list[SeismicEvent] | None  — None if layer is invalid or missing
                the expected INGV fields.
        """
        from .api_client import SeismicEvent

        layer = self.iface.activeLayer()
        if layer is None:
            return None

        # Check the layer has the expected INGV fields
        field_names = [f.name() for f in layer.fields()]
        required = {"event_id", "magnitude", "depth_km", "time", "location"}
        if not required.issubset(set(field_names)):
            return None

        events = []
        for feat in layer.getFeatures():
            try:
                events.append(SeismicEvent(
                    event_id=str(feat["event_id"]),
                    time=str(feat["time"]),
                    latitude=feat["latitude"],
                    longitude=feat["longitude"],
                    depth_km=feat["depth_km"],
                    mag_type=feat["mag_type"] if "mag_type" in field_names else "ML",
                    magnitude=feat["magnitude"],
                    location=str(feat["location"]),
                    event_type=feat["event_type"] if "event_type" in field_names else "earthquake",
                ))
            except Exception:
                continue
        return events if events else None

    def _on_open_analysis(self):
        """Open the analysis chart dialog.

        Uses _last_events if available (same session). If the dialog was
        closed and reopened, falls back to reading features from the
        currently active INGV layer in the project.
        """
        events = self._last_events or []

        if not events:
            # Fallback: try to read from the active layer
            events = self._events_from_active_layer() or []

        if not events:
            QMessageBox.information(
                self, "Nessun dato",
                "Nessun dato disponibile per l'analisi.\n\n"
                "Opzioni:\n"
                "• Scarica eventi dal tab Terremoti, oppure\n"
                "• Seleziona un layer INGV Terremoti nel pannello Layer e riprova."
            )
            return

        # Build a descriptive label
        layer = self.iface.activeLayer()
        label = layer.name() if layer else f"{len(events)} eventi"

        dlg = AnalysisDialog(
            events=events,
            layer_name=label,
            parent=self,
        )
        dlg.exec()

    # ------------------------------------------------------------------
    # Guida tab
    # ------------------------------------------------------------------

    def _build_guide_tab(self):
        """Build the '📖 Guida' help tab."""
        from qgis.PyQt.QtWidgets import QScrollArea, QTextBrowser

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setStyleSheet("font-size: 10pt; background: transparent;")
        browser.setHtml("""
<style>
  body  { font-family: sans-serif; font-size: 10pt; margin: 8px 12px; }
  h2    { font-size: 13pt; margin-top: 16px; margin-bottom: 4px; }
  h3    { font-size: 11pt; margin-top: 12px; margin-bottom: 2px; color: #c0392b; }
  p     { margin: 4px 0 8px 0; line-height: 1.5; }
  ul    { margin: 4px 0 8px 18px; padding: 0; }
  li    { margin-bottom: 3px; line-height: 1.45; }
  code  { font-family: monospace; background: #f0f0f0; padding: 1px 4px;
          border-radius: 3px; font-size: 9.5pt; }
  .tip  { background: #eaf4fb; border-left: 3px solid #2980b9;
          padding: 6px 10px; border-radius: 2px; margin: 6px 0; }
  .warn { background: #fef9e7; border-left: 3px solid #f39c12;
          padding: 6px 10px; border-radius: 2px; margin: 6px 0; }
  a     { color: #2980b9; }
  hr    { border: none; border-top: 1px solid #ddd; margin: 14px 0; }
</style>

<h2>🔴 INGV Seismic Explorer — Guida rapida</h2>
<p>Plugin QGIS per scaricare e analizzare eventi sismici e stazioni dalla
<b>Rete Sismica Nazionale</b> tramite i Web Services ufficiali INGV.
Nessuna registrazione richiesta — dati completamente aperti e gratuiti.</p>

<hr>

<h2>🌍 Tab Terremoti</h2>

<h3>Intervallo temporale</h3>
<p>Imposta il periodo di interesse con i selettori data/ora oppure usa i
pulsanti rapidi (<b>Oggi</b>, <b>7 giorni</b>, <b>30 giorni</b>, <b>1 anno</b>).
Gli orari sono in <b>UTC</b>, come restituiti dall'API INGV.</p>

<h3>Magnitudo</h3>
<p>Filtra gli eventi per magnitudo minima e massima. Per visualizzare solo
terremoti percepibili dalla popolazione imposta <b>Min ≥ 2.0</b>.</p>

<h3>Profondità ipocentrale</h3>
<p>Filtra per profondità in km. I terremoti italiani si concentrano tra
0 e 35 km (crosta superiore). Valori > 70 km indicano sismicità
di subduzione (es. arco calabro).</p>

<h3>Area geografica</h3>
<ul>
  <li><b>Tutta Italia</b> — bounding box predefinito 35–47.5°N / 6–19.5°E</li>
  <li><b>Extent mappa corrente</b> — usa il rettangolo visibile nella canvas
      (utile per zoom su aree specifiche). La CRS viene convertita
      automaticamente in WGS84.</li>
  <li><b>Coordinate personalizzate</b> — inserisci min/max lat e lon manualmente.</li>
  <li><b>Nessun filtro area</b> — recupera eventi mondiali (attenzione ai limiti
      di 10&nbsp;000 eventi per query).</li>
</ul>

<h3>Opzioni layer</h3>
<ul>
  <li><b>Colora per profondità</b> — se attivo, i cerchi vengono colorati per
      classe di profondità invece che con il colore arancio uniforme.</li>
  <li><b>Limite eventi</b> — max 10&nbsp;000 per singola query (limite API INGV).
      Per periodi lunghi riduci il limite o suddividi in query più brevi.</li>
</ul>

<div class="tip">
  <b>💡 Simbologia automatica:</b> il layer viene caricato con cerchi
  proporzionali alla magnitudo (4 px per M&lt;2 → 32 px per M≥7).
  Puoi modificare lo stile dal pannello Layer Properties di QGIS.
</div>

<hr>

<h2>📡 Tab Stazioni</h2>
<p>Scarica le stazioni della <b>Rete Sismica Nazionale (rete IV)</b> o
di altre reti INGV come layer punto. Ogni stazione include codice,
nome sito, quota, coordinate e date operative.</p>
<p>Le stazioni vengono visualizzate con un <b>triangolo blu</b> ed etichettate
con il codice stazione.</p>

<div class="tip">
  <b>💡</b> Sovrapponi il layer stazioni a quello terremoti per vedere
  quali stazioni hanno registrato gli eventi nell'area di interesse.
</div>

<hr>

<h2>🔬 Tab Analisi</h2>

<h3>🔥 Heatmap sismicità</h3>
<p>Trasforma il layer attivo in una <b>kernel density heatmap</b>.
Il colore va da trasparente (nessun evento) a rosso intenso (alta concentrazione).
</p>
<ul>
  <li><b>Raggio kernel</b> — valori bassi (4–6 mm) mostrano hotspot precisi,
      valori alti (15–30 mm) producono una visualizzazione più fluida.</li>
  <li><b>Peso per campo</b> — seleziona <code>magnitude</code> per dare
      maggiore peso agli eventi più forti.</li>
</ul>
<div class="warn">
  <b>⚠️</b> La heatmap sostituisce lo stile del layer selezionato.
  Per tornare allo stile originale: tasto destro sul layer →
  <i>Proprietà → Simbologia → Graduated</i> e riapplica.
</div>

<h3>⏱ Animazione temporale</h3>
<p>Abilita le <b>proprietà temporali</b> sul layer attivo per integrarlo
con il <b>Temporal Controller</b> di QGIS (≥ 3.14).</p>
<p>Passi:</p>
<ul>
  <li>Scegli la durata di visibilità di ogni evento (es. <b>1 giorno</b>).</li>
  <li>Clicca <i>Abilita animazione temporale</i>.</li>
  <li>Apri <b>Visualizza → Pannelli → Temporal Controller</b>.</li>
  <li>Imposta il passo temporale e premi <b>▶ Play</b> per animare.</li>
</ul>
<div class="tip">
  <b>💡</b> Scarica un mese di sismicità con M ≥ 1 e animala giorno per giorno
  per osservare visivamente l'evoluzione di uno sciame sismico.
</div>

<h3>📊 Grafici di analisi</h3>
<p>Apre la finestra con tre grafici interattivi:</p>
<ul>
  <li><b>Gutenberg-Richter</b> — distribuzione cumulativa log₁₀N vs M con
      stima automatica del <b>b-value</b> (tipicamente 0.8–1.2 per l'Italia)
      e della <b>magnitudo di completezza Mc</b>.</li>
  <li><b>Serie temporale</b> — conteggio eventi per giorno o settimana con
      media mobile a 7 giorni. Utile per identificare sciami.</li>
  <li><b>Distribuzione profondità</b> — istogramma orizzontale colorato
      per classe di profondità.</li>
</ul>
<div class="tip">
  <b>💡</b> I grafici funzionano anche dopo aver riaperto il plugin:
  basta selezionare il layer INGV nel pannello Layer prima di cliccare
  <i>Apri grafici di analisi</i>.
</div>

<hr>

<h2>⚙️ Requisiti e note tecniche</h2>
<ul>
  <li>QGIS ≥ 3.20 (animazione temporale richiede ≥ 3.14)</li>
  <li>Connessione internet per le query API</li>
  <li>Nessuna API key — i dati INGV FDSNWS sono aperti</li>
  <li>I dati sono in <b>EPSG:4326 (WGS84)</b></li>
  <li>Orari sempre in <b>UTC</b></li>
</ul>

<h2>🔗 Link utili</h2>
<ul>
  <li><a href="https://terremoti.ingv.it">terremoti.ingv.it</a> — portale ufficiale INGV</li>
  <li><a href="https://webservices.ingv.it/fdsnws/event/1/">FDSNWS Event API</a> — documentazione endpoint</li>
  <li><a href="https://webservices.ingv.it/fdsnws/station/1/">FDSNWS Station API</a> — documentazione stazioni</li>
  <li><a href="https://ingvterremoti.com">ingvterremoti.com</a> — blog scientifico INGV</li>
</ul>
""")

        scroll.setWidget(browser)
        return scroll
