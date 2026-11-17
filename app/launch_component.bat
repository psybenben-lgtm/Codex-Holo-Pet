@echo off
setlocal
cd /d "%~dp0.."

set "MODE=%~1"
if "%MODE%"=="" set "MODE=workbench"

set "PY_EXE="
set "ANY_PY="

call :find_python
if /I "%MODE%"=="stop" goto :do_stop
if defined PY_EXE goto :run_py
if defined ANY_PY goto :run_diag

echo ========================================================================
echo [ERROR] Python 3.9 - 3.13 with tkinter was NOT found on this PC.
echo Install standard Python 3.11 ^(includes tkinter^) via PowerShell:
echo   winget install -e --id Python.Python.3.11 --scope user --accept-package-agreements --accept-source-agreements
echo Then double-click launcher 0 again.
echo ========================================================================
pause
exit /b 1

:run_py
"%PY_EXE%" "app\launcher.py" "%MODE%"
exit /b %ERRORLEVEL%

:run_diag
"%ANY_PY%" "app\launcher.py" --diagnose-python
exit /b %ERRORLEVEL%

:do_stop
if defined PY_EXE goto :stop_with_py
powershell -NoProfile -Command "$p = @(Get-NetTCPConnection -LocalPort 29765,29766 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess); Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and ($_.CommandLine -match 'coffee_server|coffee_pet|strike_desktop|badminton_overlay|transparent_badminton' -or ($p -contains $_.ProcessId)) } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
echo [DONE] Stopped local Codex Holo Pet processes.
pause
goto :eof

:stop_with_py
"%PY_EXE%" "app\launcher.py" stop
exit /b %ERRORLEVEL%

:find_python
for %%P in (
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python39\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "C:\Python311\python.exe"
    "C:\Python312\python.exe"
    "C:\Python310\python.exe"
    "C:\Python39\python.exe"
    "%USERPROFILE%\anaconda3\python.exe"
    "%USERPROFILE%\miniconda3\python.exe"
) do call :probe_py %%P
for /f "delims=" %%I in ('where python 2^>nul') do call :probe_py "%%~I"
for /f "delims=" %%I in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do call :probe_py "%%~I"
goto :eof

:probe_py
if defined PY_EXE goto :eof
set "CAND=%~1"
if not exist "%CAND%" goto :eof
"%CAND%" -c "import sys; raise SystemExit(2 if 'WindowsApps' in sys.executable else 0)" >nul 2>&1
if errorlevel 1 goto :eof
if not defined ANY_PY set "ANY_PY=%CAND%"
"%CAND%" -c "import sys,tkinter; raise SystemExit(0 if (3,9) <= sys.version_info[:2] <= (3,14) else 2)" >nul 2>&1
if errorlevel 1 goto :eof
set "PY_EXE=%CAND%"
goto :eof
