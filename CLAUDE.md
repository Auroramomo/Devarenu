# Arbeitsregeln für Claude in diesem Repo

## Dateien ändern

Dateien **nur** mit dem Edit- oder Write-Werkzeug ändern. Nie per
`python - <<'EOF'`, `cat > datei <<'EOF'` oder einem anderen Heredoc im
Befehl, und keine Programme direkt im Befehl.

## Hilfsskripte und Zwischendateien

Alles Flüchtige gehört nach `~/Devarenu/.tmp/` — Hilfsskripte, Ausgaben,
Bilder, Messungen. Der Ordner steht in `.gitignore` und liegt im
Arbeitsverzeichnis.

**Nicht** nach `/tmp`: das liegt außerhalb des Arbeitsverzeichnisses und
löst bei jedem Zugriff eine Rückfrage aus.

Ein Hilfsskript wird also als Datei dorthin geschrieben und von dort
aufgerufen:

```
python3 .tmp/name.py
node .tmp/name.mjs
```
