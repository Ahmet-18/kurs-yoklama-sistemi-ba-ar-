@echo off
title Kurs Yoklama ve Mazeret Sistemi
chcp 65001 > nul
echo ======================================================
echo    KURS YOKLAMA VE MAZERET BILDIRIM SISTEMI
echo ======================================================
echo.
echo Gerekli Flask web paketi yukleniyor/kontrol ediliyor...
python -m pip install flask
if %ERRORLEVEL% NEQ 0 (
    py -m pip install flask
)
echo.
echo ======================================================
echo Sunucu Baslatiliyor...
echo ======================================================
echo.
python app.py
if %ERRORLEVEL% NEQ 0 (
    py app.py
)
pause
