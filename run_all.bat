@echo off
title FLO Launcher — Factory Logistics Optimizer
echo Starting FLO Core Engine (Session 1) and Factory Simulator (Session 2)...
echo.
start "FLO Core Engine (Port 8000)" cmd /k "run_core.bat"
timeout /t 2 /nobreak >nul
start "Factory Simulator (Port 8001)" cmd /k "run_factory.bat"
timeout /t 2 /nobreak >nul
echo Opening Factory Simulator GUI in browser...
start http://127.0.0.1:8001
echo FLO System is now RUNNING!
