@echo off
setlocal
cd /d "%~dp0server"

rem Clear stale proxy env so outbound API calls do not use a dead local proxy.
set "HTTP_PROXY="
set "HTTPS_PROXY="
set "ALL_PROXY="
set "http_proxy="
set "https_proxy="
set "all_proxy="

set "PY=C:\Users\jyfht\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
if not exist "%PY%" (
  echo Cannot find the tutor Python runtime:
  echo   %PY%
  pause
  exit /b 1
)

rem If the server is already healthy, just open the page.
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8793/api/health' -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 } } catch {}; exit 1"
if not errorlevel 1 goto openpage

echo Starting tutor server...
powershell -NoProfile -Command "Start-Process -FilePath '%PY%' -ArgumentList 'tutor_server.py' -WorkingDirectory '%~dp0server' -WindowStyle Hidden -RedirectStandardOutput '%~dp0data\server-bat.log' -RedirectStandardError '%~dp0data\server-bat.err.log'"

echo Waiting for http://127.0.0.1:8793 ...
powershell -NoProfile -Command "$ok = $false; for ($i = 0; $i -lt 120; $i++) { try { $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8793/api/health' -TimeoutSec 1; if ($r.StatusCode -eq 200) { $ok = $true; break } } catch {}; Start-Sleep -Milliseconds 500 }; if ($ok) { exit 0 } else { exit 1 }"
if errorlevel 1 (
  echo.
  echo Tutor server did not start. Check the logs:
  echo   %~dp0data\server-bat.log
  echo   %~dp0data\server-bat.err.log
  pause
  exit /b 1
)

:openpage
start "" "http://127.0.0.1:8793/"
endlocal
