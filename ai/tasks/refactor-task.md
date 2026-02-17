# Refactor Task Template

## Purpose

Vorlage für strukturelle Verbesserungen im IBTool-Projekt. Ziel: bessere Codestruktur ohne Änderung der fachlichen Logik.

## Scope

- Struktur und Lesbarkeit verbessern
- Keine Logikänderungen
- Bestehende Tests nicht brechen
- API-Kompatibilität wahren

## Vorgehensweise

### 1. Bestandsaufnahme

- [ ] Aktuellen Code vollständig lesen und verstehen
- [ ] Abhängigkeiten identifizieren (wer nutzt den Code?)
- [ ] Bestehende Tests identifizieren und ausführen
- [ ] Zielstruktur definieren

### 2. Planung

- [ ] Refactoring-Schritte in kleine, testbare Einheiten aufteilen
- [ ] Reihenfolge festlegen (innen nach außen)
- [ ] Rückwärtskompatibilität sicherstellen
- [ ] Zu löschenden Code identifizieren

### 3. Implementierung

- [ ] Ein Schritt pro Commit
- [ ] Nach jedem Schritt: Tests ausführen
- [ ] Imports aktualisieren
- [ ] Docstrings an neue Struktur anpassen

### 4. Validierung

- [ ] Alle bestehenden Tests grün
- [ ] Neue Tests für extrahierte Komponenten
- [ ] Funktionalität manuell verifiziert
- [ ] Keine verwaisten Imports oder toten Code

## Allowed Changes

- Extraktion von Funktionen/Klassen
- Umbenennung gemäß Naming Conventions
- Verschieben von Code in passende Module
- Entfernen von totem Code
- Hinzufügen von Docstrings zu geändertem Code
- Erstellung neuer Module für extrahierte Logik

## Forbidden Changes

- Änderung der fachlichen Logik
- Änderung von Algorithmus-Parametern
- Hinzufügen neuer Features
- Änderung des externen Verhaltens
- Entfernen oder Ändern bestehender Tests (außer Anpassung an neue Struktur)

## Checklist

```
[ ] Alle bestehenden Tests grün vor Start
[ ] Zielstruktur dokumentiert
[ ] Schrittweise umgesetzt (nicht alles auf einmal)
[ ] Tests nach jedem Schritt grün
[ ] Keine Logikänderung
[ ] API-Kompatibilität gewahrt
[ ] CHANGELOG aktualisiert
```

## Typische Refactoring-Muster im Projekt

### Monolithische Funktion aufteilen

```
Vorher: eine_grosse_funktion(a, b, c, d, e)  # 500+ Zeilen
Nachher:
  - KlasseA.schritt_1(a, b)
  - KlasseB.schritt_2(c)
  - Orchestrator.ausfuehren(a, b, c, d, e)  # delegiert
```

### Parameter zu Klassenkonstanten

```
Vorher: funktion(x, threshold=50, buffer=5)
Nachher:
  class Processor:
      THRESHOLD = 50
      BUFFER = 5
      def verarbeite(self, x): ...
```
