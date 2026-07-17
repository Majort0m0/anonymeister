# Anonymizer App

Die App soll auf Mac und auf Windows Geräten lauffähig sein.
Die App soll als Input verschiedene Dateitypen (Zwischenablage, txt, md, doc, pdf, mp3) akzeptieren.

Die Inhalte sollen transkripiert und anonymisiert werden. Als Ausgabe soll dann eine schön formaterte md Datei stehen.

Die Transkription soll mit lokalen KI Modellen aus Datenschutzgründen umgesetzt werden. Auf meinem System (Macbook Air M4 - 16GB RAM) stehen über Ollama zB gemma4:12b oder gemma4-64k:latest zur Verfügung. Für Audio Dateien ist whisper lokal installiert. Diese sollen über bzw mit dieser App verwendet werden.
Wenn die lokalen Modelle auf einem System, auf dem die App gestartet wird nichtt zur Verfügung stehen, sollen Anleitungen oder gleich automatische Installationsprozesse vorhanden sein, um die richtige Komponenten zu installieren. Wenn es andere lokalen LLMs gibt, welche für die oben genannten Aufgaben besser geeignet sind, auch abhängig vom jeweiligen Host System, dann mache bitte Vorschläge.

Wenn etwas unklar ist oder du noch verbesserungsvorschläge zur App Architektur hast, dann frag bitte nach.
