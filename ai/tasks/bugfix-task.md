# Bugfix Task Template

## Purpose

Vorlage für Fehlerbehebungen im IBTool-Projekt. Ziel: minimale, gezielte Änderungen zur Behebung des gemeldeten Problems.

## Scope

- Nur den gemeldeten Fehler beheben
- Keine Refactorings nebenbei
- Keine Code-Verbesserungen außerhalb des Fehlerbereichs
- Keine neuen Features einbauen

## Vorgehensweise

### 1. Analyse

- [ ] Fehlerbeschreibung vollständig verstehen
- [ ] Betroffenen Code lokalisieren und lesen
- [ ] Reproduktionsszenario identifizieren
- [ ] Root Cause bestimmen (nicht nur Symptom)

### 2. Auswirkungsanalyse

- [ ] Welche anderen Module nutzen den betroffenen Code?
- [ ] Kann der Fix Seiteneffekte haben?
- [ ] Gibt es bestehende Tests für den betroffenen Bereich?

### 3. Implementierung

- [ ] Minimale Änderung zur Fehlerbehebung
- [ ] Bestehende Code-Konventionen einhalten
- [ ] Docstrings aktualisieren falls nötig
- [ ] Logger-Meldungen für neue Fehlerpfade

### 4. Validierung

- [ ] Bestehende Tests laufen weiter (keine Regression)
- [ ] Neuer Test für den behobenen Fehler
- [ ] Bei Geometrie-Fixes: Validitäts- und Multipart-Checks
- [ ] Debug-Modus getestet (falls Processing-bezogen)

### 5. Dokumentation

- [ ] CHANGELOG.md aktualisieren
- [ ] Commit-Message beschreibt den Fix klar

## Allowed Changes

- Bugfix im betroffenen Modul
- Neuer Test für den Fix
- CHANGELOG-Eintrag
- Docstring-Anpassung im geänderten Code

## Forbidden Changes

- Umbenennung von Variablen/Funktionen außerhalb des Fix-Bereichs
- Hinzufügen von Imports die nicht für den Fix nötig sind
- Refactoring benachbarter Funktionen
- Änderung der öffentlichen API
- Hinzufügen neuer Dependencies

## Checklist

```
[ ] Root Cause identifiziert
[ ] Fix ist minimal und gezielt
[ ] Keine Regression in bestehenden Tests
[ ] Neuer Test deckt den Bug ab
[ ] CHANGELOG aktualisiert
[ ] Code-Review-ready
```
