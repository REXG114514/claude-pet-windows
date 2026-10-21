@echo off
chcp 65001 >nul
py -3 "%~dp0install.py" --uninstall %*
pause
