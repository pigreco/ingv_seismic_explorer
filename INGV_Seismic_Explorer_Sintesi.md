# INGV Seismic Explorer — Sintesi del progetto

> Plugin QGIS per il monitoraggio sismico tramite i Web Services ufficiali INGV  
> Versione 0.1.0 · Licenza GPLv2 · Python 3.x · QGIS ≥ 3.20

---

## Contesto

Il portale **terremoti.ingv.it** dell'Istituto Nazionale di Geofisica e Vulcanologia espone dati sismici aperti e gratuiti tramite le API **FDSNWS** (Federation of Digital Seismograph Networks Web Services), standard internazionale adottato dai principali centri sismologici mondiali.

Il plugin nasce per portare questi dati direttamente nell'ambiente GIS, eliminando il ciclo manuale download → import che rallenta l'analisi.

---

## Architettura

```
ingv_seismic_explorer/
├── __init__.py          # Entry point QGIS (classFactory)
├── metadata.txt         # Manifest: nome, versione, categoria Web
├── main.py              # Classe principale, menu Web + toolbar
├── dialogs.py           # Dialog Qt con tutta la UI (4 tab)
├── api_client.py        # Client FDSNWS + worker QThread
├── layer_builder.py     # Costruisce QgsVectorLayer da eventi/stazioni
├── style_manager.py     # Simbologia graduata, profondità, heatmap
├── analysis.py          # Analisi statistica + grafici matplotlib
├── README.md
└── LICENSE (GPLv2)
```

### Pattern architetturali adottati

- **Separazione responsabilità** — ogni modulo ha un ruolo unico e non dipende dalla UI
- **QThread worker** — le chiamate HTTP girano in background senza bloccare QGIS
- **Singleton dialog** — il dialog viene creato una volta e riaperto (non ricreato)
- **Fallback layer → eventi** — l'analisi rilegge i dati dal layer attivo se `_last_events` è vuoto

---

## API utilizzate

| Endpoint | Dati | Formato risposta |
|----------|------|-----------------|
| `webservices.ingv.it/fdsnws/event/1/query` | Eventi sismici | Text, QuakeML, KML |
| `webservices.ingv.it/fdsnws/station/1/query` | Stazioni sismiche | StationXML, Text |

**Nessuna API key richiesta.** Limite: 10.000 eventi per singola query.

Parametri principali: `starttime`, `endtime`, `minmagnitude`, `maxmagnitude`, `mindepth`, `maxdepth`, `minlat`, `maxlat`, `minlon`, `maxlon`, `format`, `limit`.

---

## Funzionalità — Fase 1 (core)

### Tab Terremoti
- Filtri per **intervallo temporale** con preset rapidi (Oggi / 7gg / 30gg / 1 anno)
- Filtri per **magnitudo** (min/max) e **profondità ipocentrale** (min/max km)
- **5 modalità area geografica**:
  - Tutta Italia (bbox predefinito)
  - Extent mappa corrente (con conversione CRS automatica in WGS84)
  - Coordinate personalizzate (lat/lon min-max)
  - **Disegna a schermo** — `DrawRectangleTool` custom con rubber band rosso in tempo reale
  - Nessun filtro (mondiale)
- Limite eventi configurabile (1–10.000)
- Opzione stile per **profondità** invece che magnitudo

### Tab Stazioni
- Import stazioni **Rete Sismica Nazionale** (rete IV, 400+ stazioni) e altre reti INGV
- Attributi: codice, nome sito, quota, coordinate, date operative
- Simbologia triangolo blu con etichetta codice stazione

### Simbologia automatica layer eventi
- **Cerchi graduati per magnitudo**: da 4 px (M < 2) a 32 px (M ≥ 7)
- **Colore per profondità** (opzionale):

| Classe | Profondità | Colore |
|--------|-----------|--------|
| Superficiale | 0–10 km | Rosso |
| Intermedio | 10–35 km | Arancio |
| Medio | 35–70 km | Giallo |
| Profondo | 70–150 km | Verde |
| Molto profondo | > 150 km | Blu |

---

## Funzionalità — Fase 2 (avanzate)

### Heatmap sismicità
- Renderer `QgsHeatmapRenderer` nativo QGIS (zero dipendenze esterne)
- Ramp colore costruita manualmente: `alpha=0` (assenza eventi) → giallo pallido → arancio → rosso intenso
- Raggio kernel configurabile (1–50 mm)
- Peso opzionale per campo (`magnitude` o `depth_km`)

### Animazione temporale
- Integrazione con **QGIS Temporal Controller** (≥ 3.14)
- `QgsVectorLayerTemporalProperties` con campo `time` come istante di origine
- Durata visibilità evento configurabile: 1 ora / 6 ore / 12 ore / 1 giorno / 1 settimana
- Uso: Visualizza → Pannelli → Temporal Controller → Play

### Grafici di analisi statistica
Finestra `AnalysisDialog` con tre tab matplotlib:

**Gutenberg-Richter**
- Scatter plot log₁₀N vs M (distribuzione cumulativa)
- Stima automatica **b-value** via regressione lineare (punti con N ≥ 5)
- Stima **magnitudo di completezza Mc**
- Formula: `log₁₀(N) = a − b × M`

**Serie temporale**
- Istogramma giornaliero o settimanale (toggle combo box)
- Media mobile a 7 giorni sovrapposta
- Utile per identificare visivamente l'inizio e la fine di uno sciame

**Distribuzione profondità**
- Istogramma orizzontale colorato per classe di profondità
- Bin configurabili (default 5 km)

**Barra statistiche riassuntive**: N eventi · M max · M media · Depth media · b-value · Mc stimato

---

## DrawRectangleTool

Classe custom `QgsMapTool` per il disegno interattivo dell'area di query:

```
canvasPressEvent   → inizializza QgsRubberBand rosso semitrasparente
canvasMoveEvent    → aggiorna il rettangolo in tempo reale
canvasReleaseEvent → emette rectangleDrawn(QgsRectangle), ripristina tool precedente
keyPressEvent(Esc) → emette drawingCancelled, annulla senza errori
```

Al rilascio: il dialog torna in primo piano con le coordinate WGS84 visualizzate in verde.  
Il tool salva e ripristina il map tool precedente al completamento.

---

## Tab Guida

`QTextBrowser` con HTML stilizzato che documenta:
- Tutti i filtri del tab Terremoti con note pratiche
- Import stazioni e simbologia
- Heatmap: configurazione e come ripristinare lo stile originale
- Animazione temporale: passi dettagliati
- Grafici: interpretazione b-value e Mc
- Requisiti tecnici e link utili INGV

---

## Note tecniche

| Voce | Dettaglio |
|------|-----------|
| CRS dati | EPSG:4326 (WGS84) |
| Orari | UTC (come restituiti dall'API) |
| HTTP client | `urllib` in `QThread` (non blocca UI) |
| Rete QGIS | Non usa `QgsNetworkAccessManager` (scelta deliberata per semplicità del threading) |
| Matplotlib | Bundled con QGIS 3.x, fallback message se assente |
| Compatibilità OS | Windows, Linux, macOS |
| Campo temporale | `time` (stringa ISO-8601) |

---

## Sviluppi futuri ipotizzati (Fase 3)

- **Export report PDF** con mappa + grafici per area selezionata
- **Confronto sciami** — due periodi temporali sovrapposti sullo stesso grafico
- **Processing Provider** — query INGV come algoritmi nel Processing Toolbox di QGIS
- **Notifiche in-QGIS** — polling con `QTimer` per nuovi eventi sopra soglia configurabile
- **Pubblicazione** sul repository ufficiale plugins.qgis.org (richiede account OSGEO)
