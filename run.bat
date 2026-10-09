@echo off
REM Ejecuta el bot y lo reinicia solo si se cae. Dejalo abierto en el PC/VPS.
:loop
python -m bot.main
echo [%date% %time%] El bot se detuvo, reiniciando en 10s... >> bot-restarts.log
timeout /t 10 /nobreak >nul
goto loop
