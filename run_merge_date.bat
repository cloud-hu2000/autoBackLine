@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "POWERSHELL=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"

if "%~1"=="" (
  if not exist "%POWERSHELL%" (
    echo PowerShell not found: "%POWERSHELL%"
    exit /b 1
  )
  for /f %%i in ('"%POWERSHELL%" -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set "TARGET_DATE=%%i"
) else (
  set "TARGET_DATE=%~1"
)

python merge_only.py --date "%TARGET_DATE%"
pause
