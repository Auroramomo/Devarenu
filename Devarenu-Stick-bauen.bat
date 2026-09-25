@echo off
REM ===================================================================
REM  Devarenu: Update-Stick bauen
REM
REM  Doppelklick. Das Fenster sagt, was passiert.
REM
REM  Am Ende liegt auf dem Desktop ein Ordner "Devarenu-Stick".
REM  Dessen INHALT kommt auf einen USB-Stick -- die Dateien ganz oben,
REM  nicht der Ordner selbst.
REM
REM  Gebraucht wird: Git fuer Windows. Sonst nichts.
REM ===================================================================
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title Devarenu -- Update-Stick bauen
color 07

echo.
echo   ================================================
echo    Devarenu -- Update-Stick bauen
echo   ================================================
echo.

REM ---------------------------------------------------------- Git da?
where git >nul 2>&1
if errorlevel 1 (
  echo   Git fuer Windows ist nicht installiert.
  echo.
  echo   Es wird gebraucht, um das Projekt herunterzuladen.
  echo   Kostenlos, von der offiziellen Seite:
  echo.
  echo       https://git-scm.com/download/win
  echo.
  echo   Herunterladen, installieren, alle Vorgaben uebernehmen,
  echo   danach diese Datei noch einmal doppelt anklicken.
  echo.
  pause
  exit /b 1
)
echo   [ok]  Git ist da.

REM ------------------------------------------------------- Arbeitsort
set "ARBEIT=%TEMP%\devarenu-stick"
set "QUELLE=%ARBEIT%\repo"
set "ZIEL=%USERPROFILE%\Desktop\Devarenu-Stick"

if not exist "%ARBEIT%" mkdir "%ARBEIT%"

REM --------------------------------------------------------- Holen
if exist "%QUELLE%\.git" (
  echo   [..]  Hole Neuerungen ...
  git -C "%QUELLE%" fetch --all --tags --prune --quiet
  if errorlevel 1 goto netzfehler
) else (
  echo   [..]  Lade das Projekt herunter. Das dauert einen Moment ...
  git clone --quiet https://github.com/Auroramomo/Devarenu.git "%QUELLE%"
  if errorlevel 1 goto netzfehler
)
echo   [ok]  Projekt ist aktuell.

REM ------------------------------------------------- Betreuer einlesen
REM  Name und Adresse stehen an EINER Stelle im Projekt: betreuer.txt.
REM  "delims==" trennt am Gleichheitszeichen, "eol=#" laesst Kommentare
REM  aus. betreuer.txt hat LF-Zeilenenden, weil sie aus git kommt --
REM  je nach Einstellung kann git unter Windows daraus CRLF machen.
REM  for /f kommt mit beidem zurecht: es trennt an der Zeile und
REM  nimmt ein CR nicht in den Wert auf. Nachgestellt geprueft mit
REM  beiden Varianten.
set "BETREUER_NAME=dem Betreuer"
set "BETREUER_MAIL="
if exist "%QUELLE%\betreuer.txt" (
  for /f "usebackq eol=# tokens=1,* delims==" %%a in ("%QUELLE%\betreuer.txt") do (
    if /i "%%a"=="name" set "BETREUER_NAME=%%b"
    if /i "%%a"=="mail" set "BETREUER_MAIL=%%b"
  )
)

REM ------------------------------------------- neuester Tag nach NUMMER
REM  Nicht nach Datum: v0.2.9 wurde spaeter getaggt als v0.2.13 haette
REM  werden koennen, und dann waere der Stick eine Fassung zu alt.
REM  --sort=-v:refname sortiert nach Versionsnummer, absteigend.
set "TAG="
for /f "delims=" %%t in ('git -C "%QUELLE%" tag --list "v*" --sort^=-v:refname') do (
  if not defined TAG set "TAG=%%t"
)
if not defined TAG (
  echo.
  echo   Im Projekt ist keine Fassung markiert. Das sollte nicht sein.
  echo   Bitte bei !BETREUER_NAME! melden: !BETREUER_MAIL!
  echo.
  pause
  exit /b 1
)
echo   [ok]  Neueste Fassung: %TAG%

REM -------------------------------------- braucht sie grosse Teile?
REM  teile.json nennt Sprachmodell, Spracherkennung und Stimmen. Die
REM  liegen NICHT im Projekt -- zusammen sind es rund vierzehn
REM  Gigabyte. Ist die Datei da, reicht dieser Stick nicht.
git -C "%QUELLE%" cat-file -e "%TAG%:teile.json" 2>nul
if not errorlevel 1 (
  echo.
  echo   ================================================
  echo    Dieser Weg reicht fuer dieses Update nicht.
  echo   ================================================
  echo.
  echo   Dieses Update bringt neue grosse Teile mit
  echo   ^(Modelle oder Pakete^). Dafuer reicht diese
  echo   Batch-Datei nicht.
  echo.
  echo   Es braucht einen vollstaendigen Update-Stick,
  echo   gebaut mit:  stick_bauen.sh --voll
  echo.
  echo   Es wurde NICHTS gebaut.
  echo   Bitte bei !BETREUER_NAME! melden: !BETREUER_MAIL!
  echo.
  pause
  exit /b 1
)
echo   [ok]  Keine grossen Teile noetig.

REM ------------------------------------------------------- Bauen
if exist "%ZIEL%" rmdir /s /q "%ZIEL%"
mkdir "%ZIEL%"

echo   [..]  Packe das Projekt zusammen ...
git -C "%QUELLE%" bundle create "%ZIEL%\devarenu.bundle" --all --quiet
if errorlevel 1 (
  echo.
  echo   Das Zusammenpacken ist fehlgeschlagen.
  echo   Bitte bei !BETREUER_NAME! melden: !BETREUER_MAIL!
  echo.
  pause
  exit /b 1
)

> "%ZIEL%\upd-dev.txt" echo version=%TAG%

REM ----------------------------------------------------- LIESMICH
> "%ZIEL%\LIESMICH.txt" (
  echo Devarenu-Update %TAG%
  echo ==========================
  echo.
  echo SO GEHT ES:
  echo.
  echo  1. Einen USB-Stick anstecken.
  echo.
  echo  2. Die Dateien aus diesem Ordner auf den Stick kopieren --
  echo     GANZ OBEN auf den Stick, nicht in einen Unterordner.
  echo.
  echo     Richtig:   E:\upd-dev.txt
  echo     Falsch:    E:\Devarenu-Stick\upd-dev.txt
  echo.
  echo     ^(Der Rechner findet es zur Not auch einen Ordner tiefer,
  echo      aber oben ist richtig.^)
  echo.
  echo  3. Den Stick in den Gemeinderechner stecken. Sonst nichts.
  echo.
  echo     Der Rechner merkt es von allein. Eingespielt wird erst
  echo     nach dem Gottesdienst, wenn niemand mehr zuhoert.
  echo     Am Pult steht unter "Einrichtung", was passiert ist.
  echo.
  echo  4. Den Stick danach wieder abziehen.
  echo.
  echo.
  echo WENN ETWAS NICHT STIMMT:
  echo.
  echo  Am Pult unter "Einrichtung" steht, was der Rechner zuletzt
  echo  mit einem Stick gemacht hat. Steht dort nichts, hat er den
  echo  Stick nicht gelesen -- dann liegen die Dateien vermutlich
  echo  doch in einem Unterordner.
  echo.
  echo  Gebaut am %DATE% mit Devarenu-Stick-bauen.bat
)

echo   [ok]  Fertig.
echo.
echo   ================================================
echo.
echo    Auf dem Desktop liegt jetzt der Ordner
echo.
echo        Devarenu-Stick
echo.
echo    Die Dateien daraus ganz oben auf einen USB-Stick
echo    kopieren -- nicht den Ordner selbst.
echo.
echo    Fassung: %TAG%
echo.
echo   ================================================
echo.
explorer "%ZIEL%"
pause
exit /b 0

:netzfehler
echo.
echo   Das Projekt liess sich nicht herunterladen.
echo.
echo   Meistens liegt es an der Internetverbindung.
echo   Noch einmal versuchen; geht es wieder nicht,
echo   bitte bei !BETREUER_NAME! melden: !BETREUER_MAIL!
echo.
pause
exit /b 1
