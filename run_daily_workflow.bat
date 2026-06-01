@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "POWERSHELL=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"

if not exist "%POWERSHELL%" (
  echo PowerShell not found: "%POWERSHELL%"
  exit /b 1
)

"%POWERSHELL%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0daily_workflow.ps1" %*

if errorlevel 1 (
  echo.
  echo Workflow failed. Check the latest logs\daily_workflow_*.log file.
  pause
  exit /b 1
)

echo.
echo Workflow completed. Check logs\daily_workflow_*.log for details.
pause
