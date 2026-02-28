# UI-Modernisierungsvorschläge für IB-Tool

Dieses Dokument beschreibt konkrete Vorschläge, wie die aktuelle funktionale Oberfläche des Plugins moderner, klarer und effizienter werden kann.

## 1) Informationsarchitektur vereinfachen

- **Workflow in 4 Schritte gliedern** statt aller Felder auf einer Fläche:
  1. Eingabedaten
  2. Parameter
  3. Validierung
  4. Ausführung & Ergebnisse
- **Accordion- oder Stepper-Layout** nutzen, damit Nutzer:innen nur den aktuell relevanten Block sehen.
- **Primäre Aktion hervorheben**: „Check“ und „Start“ visuell klar priorisieren (Primary/Secondary-Button-Logik).

## 2) Modernes visuelles Designsystem einführen

- **Konsistente Abstände (8-pt-Grid)** für ruhigeres Layout.
- **Typografie-Hierarchie**:
  - Abschnittstitel (größer/fett)
  - Feldlabels (mittel)
  - Hilfetexte (klein/grau)
- **Statusfarben semantisch konsistent**:
  - Grün = gültig/ok
  - Gelb = Hinweis
  - Rot = Fehler
  - Blau = laufender Prozess
- **Dezentere Gruppierung** über Karten/Frames statt harter Boxen.

## 3) Formulareingaben benutzerfreundlicher machen

- **Pfadfelder mit Inline-Feedback** direkt beim Auswählen prüfen (Datei existiert, Layertyp passt, Feld vorhanden).
- **Kontextsensitive Hilfetexte** unter kritischen Eingaben (z. B. HU/RN-Anforderungen).
- **Sinnvolle Defaults** für häufig genutzte Parameter (z. B. bekannte CRS oder zuletzt genutzte Verzeichnisse).
- **Ungültige Felder direkt markieren** (rote Kontur + konkrete Fehlermeldung am Feld statt nur globaler Meldung).

## 4) Validierung und Fehlerkommunikation verbessern

- **Validierungsergebnis als Checkliste** anzeigen:
  - ✅ HU geladen
  - ❌ RN enthält Multipart-Geometrien
  - ⚠️ Part:HU-Verhältnis grenzwertig
- **Fehlertexte lösungsorientiert formulieren** („Bitte zuerst `multiparttosingleparts` auf Layer RN ausführen“).
- **„Fix-it“-Verlinkungen** zu Doku oder QGIS-Toolnamen in der Meldung ergänzen.

## 5) Ausführungserlebnis (Processing UX) modernisieren

- **Fortschritt in Phasen** visualisieren (z. B. 1/6 Daten laden, 2/6 Blockbildung, …).
- **Live-Log mit Filter** (Info/Warn/Error) und „Kopieren“-Button für Support.
- **Abbruch und Wiederaufnahme**: klare Zustände bei Cancel, inkl. Hinweis auf bereits erzeugte Zwischenergebnisse.
- **Ergebnisbereich nach Lauf** mit direkten Aktionen:
  - Ergebnis in QGIS laden
  - Arbeitsverzeichnis öffnen
  - Log exportieren

## 6) Interaktionsmuster für Power-User

- **Preset-Profile** (z. B. „Standard“, „Schnelltest“, „Hohe Genauigkeit“).
- **Parameter speichern/laden** als JSON/INI.
- **Zuletzt verwendete Eingaben** in einer History-Liste anzeigen.
- **Keyboard-freundliche Navigation** (Tab-Reihenfolge, Enter startet Primäraktion).

## 7) Barrierefreiheit und Robustheit

- **Kontrast erhöhen** (auch auf dunklen QGIS-Themes).
- **Icons nie ohne Textlabel** einsetzen.
- **Tooltips für Fachbegriffe** (BCR, MST, EdgeCatch).
- **Responsives Verhalten** bei kleineren Dialoggrößen (Scrollbereiche statt abgeschnittener Felder).

## 8) Konkrete Quick Wins (geringer Aufwand, hoher Nutzen)

1. Buttons „Check“ und „Start“ visuell differenzieren und konsistent platzieren.
2. Fehlermeldungen feldnah anzeigen statt nur in einer globalen Messagebox.
3. Fortschrittsanzeige von „nur Prozent“ auf „Phase + Prozent“ erweitern.
4. Validierungs-Checkliste im Dialog ergänzen.
5. Letzte Pfade/Parameter persistent speichern.

## 9) Vorschlag für Umsetzungs-Roadmap

- **Sprint 1 (UI-Klarheit)**: Layout strukturieren, Typografie/Spacing, Primäraktion.
- **Sprint 2 (Validierung UX)**: Feldnahe Fehler, Checkliste, bessere Fehlermeldungen.
- **Sprint 3 (Processing UX)**: Phasen-Fortschritt, Log-Panel, Ergebnisaktionen.
- **Sprint 4 (Power Features)**: Presets, Import/Export, Verlauf.

## 10) Messbare Erfolgsindikatoren

- Reduktion von Abbrüchen vor Start (nach „Check“) um X %.
- Kürzere Zeit bis erster erfolgreicher Lauf.
- Weniger Support-Anfragen zu Eingabe-/Pfadfehlern.
- Höhere Wiederverwendung gespeicherter Presets.

