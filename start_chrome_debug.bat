@echo off
chcp 65001 >nul
setlocal

set "ROOT=%~dp0"
set "CHROME=C:\Program Files\Google\Chrome\Application\chrome.exe"
set "PROFILE=%ROOT%browser\data"
set "PORT=9222"

if not exist "%CHROME%" (
  echo Chrome not found: "%CHROME%"
  exit /b 1
)

if not exist "%PROFILE%" mkdir "%PROFILE%"

%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe -NoProfile -Command "try { $r = Invoke-RestMethod -Uri 'http://127.0.0.1:%PORT%/json/version' -TimeoutSec 2; if ($r.webSocketDebuggerUrl) { exit 0 } } catch { exit 1 }" >nul 2>nul
if not errorlevel 1 (
  echo Chrome debug mode already running on port %PORT%.
  echo Reusing existing browser.
  exit /b 0
)

echo Starting Chrome debug mode on port %PORT%...
start "" "%CHROME%" --remote-debugging-port=%PORT% --user-data-dir="%PROFILE%" --new-window about:blank

echo Chrome debug mode requested.
echo Profile: %PROFILE%
echo Port: %PORT%

exit /b 0
