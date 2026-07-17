# Anleitung & Datenschutz

Diese Datei ist der Text, der auch im App-Fenster unter „Anleitung & Datenschutz"
angezeigt wird — als eigenständiges Dokument zum Nachlesen, Ausdrucken oder Weitergeben.

## So funktioniert der Ablauf

1. **Eingabe:** Datei auswählen/hineinziehen oder Text aus der Zwischenablage einfügen.
2. **Analysieren:** Die App durchsucht den Inhalt nach personenbezogenen Daten (PII) — es wird dabei noch *nichts* verändert oder gespeichert.
3. **Kategorien prüfen:** Alle gefundenen Kategorien (z. B. Namen, E-Mail-Adressen, Orte) werden mit Beispielen angezeigt. Jede Kategorie kann einzeln abgewählt werden, um sie im Ergebnis sichtbar zu lassen.
4. **Anonymisierung anwenden:** Erst jetzt wird der finale, anonymisierte Text erzeugt und als Datei gespeichert.

## Optionen im Detail

**Tiefencheck (LLM-Prüfung)**
Ein zusätzlicher, langsamerer Durchlauf durch ein lokales Sprachmodell, *nachdem* die automatische Erkennung bereits alle offensichtlichen Daten geschwärzt hat. Er findet Dinge, die eine reine Muster-/Namenserkennung strukturell nicht erkennen kann: Spitznamen ("Krümel"), Rollenbezeichnungen ("der Teamleiter"), Projekt- oder Decknamen. Er ist kein Ersatz für die automatische Erkennung, sondern eine zweite, gezielt andere Prüfung obendrauf.

**Ausgabe: Transkript / Zusammenfassung / Beides**
Legt fest, was am Ende erzeugt wird. Das Transkript ist der vollständige anonymisierte Text, die Zusammenfassung eine kurze KI-generierte Übersicht davon. Beide werden als **getrennte** Markdown-Dateien gespeichert.

**Kategorie abwählen**
Lässt eine erkannte Kategorie unangetastet im Ergebnistext stehen, statt sie zu schwärzen — z. B. wenn Ortsangaben für den Zweck des Dokuments unproblematisch sind.

**Schwärzen vs. Nummerieren vs. Pseudonymisieren (nur bei Namen)**
"Schwärzen" ersetzt jeden Namen durch den generischen Platzhalter `[PERSON]` — bei mehreren Personen im Dokument sind sie danach nicht mehr unterscheidbar. "Nummerieren" ersetzt stattdessen durch `[PERSON1]`, `[PERSON2]`, … — unterschiedliche Personen bleiben so auseinanderhaltbar, ohne dass ein echter oder erfundener Name sichtbar wird. "Pseudonymisieren" ersetzt jeden Namen durch einen erfundenen, aber **konsistenten** Fantasienamen. Bei Nummerieren wie Pseudonymisieren gilt: derselbe echte Name bekommt überall im Dokument (und, falls vorhanden, auch in einer zusätzlichen Tabellen-Kopie) dasselbe Label — nützlich, wenn die Daten danach noch lesbar/nutzbar bleiben sollen. Achtung: Die Zuordnung erfolgt über den exakt erkannten Textabschnitt — wird dieselbe Person mal mit vollem Namen, mal nur mit Nachnamen erwähnt, kann das zwei unterschiedliche Nummern/Pseudonyme ergeben.

**Anonymisierungs-Protokoll**
Die Tabelle am Ende jeder Ausgabedatei listet auf, welche Kategorien wie oft erkannt und ersetzt wurden — damit das Ergebnis nachvollziehbar bleibt, statt "unsichtbar" verändert zu werden.

**Suchen & Ersetzen**
Erscheint beim Ergebnis und korrigiert einzelne Begriffe nachträglich im Transkript und in der Zusammenfassung — z. B. ein Wort, das bei einer Audio-Transkription falsch verstanden wurde. "Ersetzen" ändert das erste Vorkommen, "Alle ersetzen" jedes Vorkommen; optional mit Berücksichtigung von Groß-/Kleinschreibung. Die Markdown-Downloads werden danach automatisch neu erzeugt; eine tabellarische Ausgabedatei (Excel/CSV/JSON/ODS) bleibt davon unberührt.

## Unterstützte Formate & Downloads

Text/Dokumente (`.txt`, `.md`, `.docx`, `.pdf`), Tabellen (`.xlsx`/`.xls`, `.csv`, `.json`, `.ods`), OpenDocument-Text (`.odt`, `.odp`), Audio (`.mp3`, `.wav`, `.m4a` u. a.) und Text aus der Zwischenablage.

Bei Tabellenformaten (Excel/CSV/JSON/ODS) entsteht zusätzlich zum Markdown-Transkript eine anonymisierte Kopie im **Originalformat** — also eine echte, weiter nutzbare Tabelle mit denselben Spalten wie das Original, nur mit anonymisierten Werten.

## Lokale KI-Komponenten & Installation

Die App nutzt zwei Arten lokaler KI-Modelle, beide laufen vollständig auf diesem Rechner:

**Ollama (Sprachmodell)**
Wird für den Tiefencheck und die Zusammenfassung gebraucht. Falls nicht installiert: [ollama.com/download](https://ollama.com/download), danach das gewählte Modell laden (z. B. `ollama pull gemma4:12b`). Welches Modell genutzt wird, lässt sich im Bereich „Systemstatus" per Dropdown umstellen — kuratierte Vorschläge nach RAM/VRAM-Bedarf sortiert (kleiner = weniger Ressourcen, größer = bessere Qualität), oder als Freitext jedes andere lokal gepullte Modell.

**faster-whisper (Spracherkennung)**
Wird nur für Audio-Dateien gebraucht und lädt das gewählte Modell beim ersten Gebrauch automatisch herunter — danach läuft es offline. Kein System-`ffmpeg` nötig, das ist bereits in `faster-whisper` enthalten. Die Modellgröße lässt sich ebenfalls im Bereich „Systemstatus" umstellen — von `tiny` (sehr sparsam, weniger genau) bis `large-v3` (beste Qualität, braucht deutlich mehr Arbeitsspeicher); Standard ist `small` als guter Kompromiss.

**spaCy-Sprachmodelle**
Werden für die Grunderkennung (Namen, Orte, …) gebraucht, einmalig zu installieren.

Der Bereich „Systemstatus" unten in der App zeigt an, was davon fehlt, und kann fehlende Modelle direkt nachladen. Nur eine bereits vorausgesetzte Ollama-Installation muss manuell eingerichtet werden.

## Datenschutz: was passiert mit den Daten?

- **Alles läuft lokal.** Es gibt keine Cloud-Anbindung und keinen externen API-Aufruf — weder für die Dokumentenanalyse noch für die KI-Auswertung.
- **Rohdaten verlassen nie diesen Rechner.** Hochgeladene Dateien werden nur temporär auf der Festplatte zwischengespeichert und nach der Analyse sofort gelöscht.
- **Das Sprachmodell (Ollama) sieht nur bereits anonymisierten Text.** Der Tiefencheck und die Zusammenfassung laufen ausschließlich über bereits geschwärzten Text — nie über das Originaldokument.
- **Ergebnisdateien liegen lokal.** Anonymisierte Dokumente werden in einem lokalen Ordner dieser App gespeichert und stehen nur auf diesem Rechner zur Verfügung.
- **Keine Analyse, kein Tracking.** Diese App sammelt keine Nutzungsdaten und sendet nichts an Dritte.

---

CC BY-NC — [Lernsachen.blog](https://lernsachen.blog)
