@echo off
chcp 65001 > nul
title Alive Food Database - Data Engine

echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║         ALIVE FOOD DATABASE - DATA ENGINE                    ║
echo ╠══════════════════════════════════════════════════════════════╣
echo ║                                                              ║
echo ║  [1] PDF/Studie verarbeiten                                  ║
echo ║  [2] KI Query starten (Gesundheitsziel → Zutaten)           ║
echo ║  [3] Food nachschlagen                                       ║
echo ║  [4] Beenden                                                 ║
echo ║                                                              ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

:menu
set /p choice="Waehle eine Option (1-4): "

if "%choice%"=="1" goto upload
if "%choice%"=="2" goto query
if "%choice%"=="3" goto food
if "%choice%"=="4" goto end

echo Ungueltige Auswahl. Bitte 1-4 eingeben.
goto menu

:upload
echo.
echo ══════════════════════════════════════════════════════════════
echo PDF/STUDIE VERARBEITEN
echo ══════════════════════════════════════════════════════════════
echo.
echo Ziehe eine PDF oder TXT Datei in dieses Fenster und druecke Enter:
echo (Oder gib den Dateipfad ein)
echo.
set /p filepath="Dateipfad: "
echo.
echo Verarbeite: %filepath%
echo.
python data_engine_v2.py %filepath% --model gpt-4o-mini
echo.
echo ══════════════════════════════════════════════════════════════
pause
goto menu

:query
echo.
echo ══════════════════════════════════════════════════════════════
echo KI QUERY - Gesundheitsziel eingeben
echo ══════════════════════════════════════════════════════════════
echo.
echo Beispiele: "Gut Health", "Heart Health", "Brain Health"
echo.
set /p goal="Gesundheitsziel: "
echo.
python query_demo.py "%goal%"
echo.
pause
goto menu

:food
echo.
echo ══════════════════════════════════════════════════════════════
echo FOOD NACHSCHLAGEN
echo ══════════════════════════════════════════════════════════════
echo.
echo Beispiele: "Flaxseed", "Berries", "Walnuts"
echo.
set /p foodname="Food Name: "
echo.
python -c "exec(open('query_demo.py').read().replace('if __name__', '#if __name__')); db = load_database(); info = query_food_info(db, '%foodname%'); print(info) if info else print('Nicht gefunden')"
echo.
pause
goto menu

:end
echo.
echo Auf Wiedersehen!
exit
