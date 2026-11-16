@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."

set "MODE=%~1"
if "%MODE%"=="" set "MODE=workbench"

set "HOLO_HTTP_PORT=29765"
set "HOLO_HTTPS_PORT=29766"
set "HOLO_UDP_PORT=29767"
set "CODEX_HOLO_PORT=29765"
set "CODEX_HOLO_HTTPS_PORT=29766"
set "CODEX_HOLO_UDP_PORT=29767"
set "BASE_URL=http://127.0.0.1:%HOLO_HTTP_PORT%"
set "READY_ROUTE=/api/pet/mode"
if /I "%MODE%"=="badminton" set "READY_ROUTE=/api/badminton/live/status"

if /I "%MODE%"=="stop" goto :do_stop

echo ========================================================================
echo   Codex 全息桌宠 V2.0 本地启动助手  (安全端口: %HOLO_HTTP_PORT% / %HOLO_HTTPS_PORT%)
echo ========================================================================
echo.

set "PY_EXE="
if /I "%MODE%"=="install" (
    call :find_python rally_install
    if not defined PY_EXE (
        echo [错误] 未检测到可用的 Python 3 解释器！
        echo 请先安装 64 位 Python 3.9 至 3.13，并加入 PATH。
        pause
        exit /b 1
    )
    goto :do_install
)

if /I "%MODE%"=="badminton" (
    call :find_python rally
) else (
    call :find_python pil
)
if not defined PY_EXE (
    echo [错误] 未找到已安装 Pillow^(PIL^) 的 Python 环境！
    echo 请先双击运行根目录下的 "4-环境依赖一键安装.bat" 完成依赖安装。
    pause
    exit /b 1
)

echo [1/3] 已定位 Python 环境: "%PY_EXE%"
echo [2/3] 正在检查本地权威同步服务 (%BASE_URL%)...

curl.exe -fs --noproxy "*" --max-time 2 "%BASE_URL%%READY_ROUTE%" >nul 2>&1
if not errorlevel 1 (
    echo       服务已在线，跳过重复启动。
    goto :server_ready
)

if /I "%MODE%"=="badminton" (
    curl.exe -fs --noproxy "*" --max-time 1 "%BASE_URL%/api/badminton/status" >nul 2>&1
    if not errorlevel 1 (
        echo 本机仍在运行旧版全息服务。请先双击 5-停止后台全息服务与桌宠，再重新启动。
        pause
        exit /b 1
    )
)
if not exist "coffee\.lan-certificate" mkdir "coffee\.lan-certificate"
echo       正在后台启动本地全息与羽毛球权威服务 (端口 %HOLO_HTTP_PORT%)...
start /min "HoloServer-%HOLO_HTTP_PORT%" cmd /S /C ""%PY_EXE%" -u "%CD%\coffee_server.py" --port %HOLO_HTTP_PORT% --https-port %HOLO_HTTPS_PORT% > coffee\.lan-certificate\server-startup.log 2>&1"

set "READY=0"
for /L %%I in (1,1,15) do (
    curl.exe -fs --noproxy "*" --max-time 1 "%BASE_URL%%READY_ROUTE%" >nul 2>&1
    if not errorlevel 1 (
        set "READY=1"
        goto :server_ready
    )
    ping -n 2 127.0.0.1 >nul
)

if "%READY%"=="0" (
    echo.
    echo [错误] 本地服务在 15 秒内未能就绪！以下是启动日志：
    echo ------------------------------------------------------------------------
    if exist "coffee\.lan-certificate\server-startup.log" type "coffee\.lan-certificate\server-startup.log"
    echo ------------------------------------------------------------------------
    pause
    exit /b 1
)

:server_ready
rem 先刷新局域网离线向导缓存再分发模式
echo       本地服务已就绪！正在刷新离线向导缓存...
"%PY_EXE%" network_helper.py --no-open >nul 2>&1

if /I "%MODE%"=="workbench" goto :launch_workbench
if /I "%MODE%"=="badminton" goto :launch_badminton
if /I "%MODE%"=="strike" goto :launch_strike
if /I "%MODE%"=="coffee" goto :launch_coffee
if /I "%MODE%"=="guide" goto :launch_guide
goto :eof

:launch_workbench
set "PYTHONUTF8=1"
echo [3/3] 正在启动透明桌面 Codex 小人与三合一网页工作台...
call :is_script_running "coffee_pet\.py|badminton_overlay\.py"
if "%SCRIPT_RUNNING%"=="0" (
    start /min "HoloDesktop-Workbench" cmd /S /C ""%PY_EXE%" -u "%CD%\coffee_pet.py" > coffee\.lan-certificate\coffee-desktop-launch.log 2>&1"
) else (
    echo       当前透明桌宠已在运行中。
)
ping -n 2 127.0.0.1 >nul
start "" "%BASE_URL%/"
echo [完成] 已打开 Codex 全息桌宠三合一工作台: %BASE_URL%/
echo        提示：点击桌面小人可弹出对话气泡，并在工作台切换【倒咖啡 / 搓澡 / 羽毛球】！
ping -n 3 127.0.0.1 >nul
goto :eof

:launch_badminton
set "PYTHONUTF8=1"
set "PY_GUI=%PY_EXE:python.exe=pythonw.exe%"
if not exist "%PY_GUI%" set "PY_GUI=%PY_EXE%"
set "BM_EXTRA_ARGS="
"%PY_EXE%" -c "import pathlib,sys; sys.path.insert(0,str(pathlib.Path('.rally-runtime').resolve())); import cv2, mediapipe" >nul 2>&1
if errorlevel 1 (
    echo       [提示] 未检测到摄像头视觉库，自动切为「纯鼠标挥拍（免摄像头权限）」启动！
    set "BM_EXTRA_ARGS=--no-camera"
)
echo [3/3] 正在启动透明桌面羽毛球桌宠、悬浮控制条与网页控制台...
call :is_script_running "badminton_overlay\.py"
if "%SCRIPT_RUNNING%"=="0" (
    start "" /D "%CD%" "%PY_GUI%" "%CD%\app\badminton_overlay.py" %BM_EXTRA_ARGS%
) else (
    echo       当前交付包的透明桌面羽毛球桌宠已在运行中。
)
ping -n 2 127.0.0.1 >nul
start "" "%BASE_URL%/badminton/director"
echo [完成] 已打开桌宠控制台（支持摄像头与纯鼠标挥拍/手机扫码）: %BASE_URL%/badminton/director
ping -n 3 127.0.0.1 >nul
goto :eof

:launch_strike
echo [3/3] 正在启动电子打工仔挖土罢工桌宠并打开联调中枢...
call :is_script_running "strike_desktop\.py"
if "%SCRIPT_RUNNING%"=="0" (
    start /min "HoloDesktop-Strike" cmd /S /C ""%PY_EXE%" -u "%CD%\strike_desktop.py" > coffee\.lan-certificate\strike-desktop-launch.log 2>&1"
) else (
    echo       当前交付包的电子打工仔桌宠已在运行中。
)
ping -n 2 127.0.0.1 >nul
start "" "%BASE_URL%/strike/dash"
echo [完成] 已打开三端联调中枢: %BASE_URL%/strike/dash
ping -n 3 127.0.0.1 >nul
goto :eof

:launch_coffee
echo [3/3] 正在启动跨屏倒咖啡桌宠并打开全息与触控页...
call :is_script_running "coffee_pet\.py"
if "%SCRIPT_RUNNING%"=="0" (
    start /min "HoloDesktop-Coffee" cmd /S /C ""%PY_EXE%" -u "%CD%\coffee_pet.py" > coffee\.lan-certificate\coffee-desktop-launch.log 2>&1"
) else (
    echo       当前交付包的跨屏倒咖啡桌宠已在运行中。
)
ping -n 2 127.0.0.1 >nul
start "" "%BASE_URL%/coffee/holo"
start "" "%BASE_URL%/coffee/pour"
echo [完成] 已打开: %BASE_URL%/coffee/holo 与 %BASE_URL%/coffee/pour
ping -n 3 127.0.0.1 >nul
goto :eof

:launch_guide
echo [3/3] 正在打开局域网配置与手机连接向导...
"%PY_EXE%" network_helper.py
echo.
echo 提示：如需给手机使用，请确保手机与电脑连接同一个 Wi-Fi。
pause
goto :eof

:do_install
echo 正在安装本机摄像头与语音识别组件...
set "PYTHONUTF8=1"
"%PY_EXE%" "%CD%\app\install_rally.py"
if errorlevel 1 (
    echo 安装未完成，请查看上面的说明。
    pause
    exit /b 1
)
echo 安装完成。双击 0-一键启动 即可开打。
pause
exit /b

:do_stop
echo 正在停止当前交付包目录下的后台全息服务与桌面桌宠进程...
set "MY_ROOT=%CD%"
powershell -NoProfile -Command "$root = [Regex]::Escape($env:MY_ROOT); $portPids = @(Get-NetTCPConnection -LocalPort 29765,29766 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess); Get-CimInstance Win32_Process | Where-Object { ($_.Name -like 'python*' -and $_.CommandLine -match 'coffee_server\.py|transparent_badminton_desktop\.py|rally_desktop\.py|badminton_overlay\.py|strike_desktop\.py|coffee_pet\.py|desktop_shovel_pet\.py' -and ($_.CommandLine -match $root -or ($portPids -contains $_.ProcessId) -or $_.CommandLine -match '--port\s+29765')) } | ForEach-Object { Write-Output ('终止进程 PID=' + $_.ProcessId + ' ' + $_.CommandLine); Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
echo [完成] 相关本地进程已清理。
pause
goto :eof

:find_python
set "PROBE_MODE=%~1"
for %%P in (
    "%LOCALAPPDATA%\Programs\Python\Python39\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
    "C:\Python39\python.exe"
    "C:\Python310\python.exe"
    "C:\Python311\python.exe"
    "C:\Python312\python.exe"
    "%USERPROFILE%\anaconda3\python.exe"
    "%USERPROFILE%\miniconda3\python.exe"
) do call :probe_py %%P "%PROBE_MODE%"
for /f "delims=" %%I in ('where python 2^>nul') do call :probe_py "%%~I" "%PROBE_MODE%"
for /f "delims=" %%I in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do call :probe_py "%%~I" "%PROBE_MODE%"
goto :eof

:probe_py
if defined PY_EXE goto :eof
set "CANDIDATE=%~1"
set "REQ_MODE=%~2"
if not exist "%CANDIDATE%" goto :eof
if /I "%REQ_MODE%"=="rally" (
    "%CANDIDATE%" -c "import pathlib,sys,tkinter; sys.path.insert(0,str(pathlib.Path('.rally-runtime').resolve())); import PIL; raise SystemExit(0 if sys.version_info[:2] >= (3,9) else 2)" >nul 2>&1
    if not errorlevel 1 set "PY_EXE=%CANDIDATE%"
    goto :eof
)
if /I "%REQ_MODE%"=="rally_install" (
    "%CANDIDATE%" -c "import sys,struct,tkinter; raise SystemExit(0 if (3,9) <= sys.version_info[:2] <= (3,13) and struct.calcsize('P')==8 else 2)" >nul 2>&1
    if not errorlevel 1 set "PY_EXE=%CANDIDATE%"
    goto :eof
)
if /I "%REQ_MODE%"=="pil" (
    "%CANDIDATE%" -c "import pathlib,sys; sys.path.insert(0,str(pathlib.Path('.rally-runtime').resolve())); import PIL; raise SystemExit(2 if 'WindowsApps' in sys.executable else 0)" >nul 2>&1
    if not errorlevel 1 set "PY_EXE=%CANDIDATE%"
) else (
    "%CANDIDATE%" -c "import sys; raise SystemExit(2 if 'WindowsApps' in sys.executable else 0)" >nul 2>&1
    if not errorlevel 1 set "PY_EXE=%CANDIDATE%"
)
goto :eof

:is_script_running
set "SCRIPT_RUNNING=0"
set "MY_ROOT=%CD%"
set "TARGET_PAT=%~1"
powershell -NoProfile -Command "$root = [Regex]::Escape($env:MY_ROOT); $pat = $env:TARGET_PAT; if (Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -match $pat -and $_.CommandLine -match $root }) { exit 10 } else { exit 0 }" >nul 2>&1
if "%errorlevel%"=="10" set "SCRIPT_RUNNING=1"
goto :eof
