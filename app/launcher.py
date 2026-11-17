# -*- coding: utf-8 -*-
"""
Codex 全息桌宠 V2.0 跨环境统一启动与自检器 (app/launcher.py)
仅依赖 Python 标准库：
- 彻底替代易受 cmd.exe UTF-8/CP936 字节偏移错位崩溃影响的复杂 .bat 逻辑；
- 正确处理含空格、中文、括号的路径；
- 自动检测标准版 tkinter、自动按需补装最小核心依赖 (Pillow + qrcode)；
- 绕过系统代理探活端口 29765，清理卡死/跨目录孤立桌宠互斥锁后拉起透明桌宠与浏览器工作台；
- 若出现异常则打印完整中文诊断与日志并等待按键，绝不静默闪退。
"""
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = ROOT / '.rally-runtime'
CERT_DIR = ROOT / 'coffee' / '.lan-certificate'

if RUNTIME_DIR.is_dir() and str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / 'app') not in sys.path:
    sys.path.insert(0, str(ROOT / 'app'))

HTTP_PORT = int(os.environ.get('CODEX_HOLO_PORT') or 29765)
HTTPS_PORT = int(os.environ.get('CODEX_HOLO_HTTPS_PORT') or 29766)
BASE_URL = f'http://127.0.0.1:{HTTP_PORT}'


def setup_console():
    if sys.platform == 'win32':
        try:
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:
            pass
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            try:
                stream.reconfigure(encoding='utf-8', errors='replace')
            except Exception:
                pass


def no_proxy_opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http_get_json(url, timeout=1.5):
    with no_proxy_opener().open(url, timeout=timeout) as resp:
        if resp.status != 200:
            raise RuntimeError(f'HTTP {resp.status}')
        return json.loads(resp.read().decode('utf-8'))


def http_post_json(url, payload, timeout=2.0):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
    )
    with no_proxy_opener().open(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def pause_exit(code=1, interactive=True):
    if interactive and os.environ.get('CODEX_LAUNCHER_NOPAUSE') != '1':
        try:
            input('\n按回车键关闭窗口...')
        except EOFError:
            pass
    raise SystemExit(code)


def check_tkinter():
    try:
        import tkinter  # noqa: F401
        return True
    except Exception:
        return False


def ensure_core_deps():
    missing = [m for m in ('PIL', 'qrcode') if not importlib.util.find_spec(m)]
    if not missing:
        return True
    print(f'[1/3] 检测到首次运行尚未安装轻量核心依赖 ({", ".join(missing)})，正在自动安装 (约 5MB)...', flush=True)
    r = subprocess.run(
        [sys.executable, str(ROOT / 'app' / 'install_rally.py'), '--core'],
        cwd=str(ROOT),
    )
    if r.returncode != 0:
        return False
    importlib.invalidate_caches()
    return True


def _win_hidden_kwargs(new_group=False):
    """Windows 下隐藏后台子进程与控制台命令行，绝不混用 CREATE_NO_WINDOW 与 DETACHED_PROCESS。"""
    if sys.platform != 'win32':
        return {}
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    if new_group:
        flags |= getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
    si = subprocess.STARTUPINFO()
    si.dwFlags |= getattr(subprocess, 'STARTF_USESHOWWINDOW', 0)
    si.wShowWindow = getattr(subprocess, 'SW_HIDE', 0)
    return {'creationflags': flags, 'startupinfo': si}


def _gui_python_executable():
    py_exe = Path(sys.executable)
    py_gui = py_exe.with_name('pythonw.exe')
    return str(py_gui if py_gui.is_file() else py_exe)


def is_our_process_running(pattern):
    if sys.platform != 'win32':
        return False
    ps = (
        f"$root = [Regex]::Escape('{str(ROOT)}'); "
        f"$pat = '{pattern}'; "
        "$hit = Get-CimInstance Win32_Process | Where-Object { "
        "$_.Name -like 'python*' -and $_.CommandLine -match $pat -and $_.CommandLine -match $root "
        "}; if ($hit) { exit 10 } else { exit 0 }"
    )
    r = subprocess.run(['powershell', '-NoProfile', '-Command', ps], capture_output=True, **_win_hidden_kwargs())
    return r.returncode == 10


def cleanup_orphan_pets(mode):
    """清理不属于当前可用会话的残余桌宠实例，防止旧互斥锁阻挡新桌宠窗口弹出。"""
    if sys.platform != 'win32':
        return
    if mode == 'badminton':
        pat = r'badminton_overlay\.py'
    else:
        pat = r'coffee_pet\.py|strike_desktop\.py'
    ps = (
        f"$pat = '{pat}'; "
        "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -match $pat } "
        "| ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    subprocess.run(['powershell', '-NoProfile', '-Command', ps], capture_output=True, **_win_hidden_kwargs())


def stop_all():
    print('正在停止 Codex 全息桌宠与本地同步服务...', flush=True)
    try:
        http_post_json(f'{BASE_URL}/api/system/shutdown', {}, timeout=0.8)
        time.sleep(0.4)
    except Exception:
        pass
    if sys.platform == 'win32':
        ps = (
            f"$root = [Regex]::Escape('{str(ROOT)}'); "
            f"$portPids = @(Get-NetTCPConnection -LocalPort {HTTP_PORT},{HTTPS_PORT} -State Listen -ErrorAction SilentlyContinue "
            "| Select-Object -ExpandProperty OwningProcess); "
            "Get-CimInstance Win32_Process | Where-Object { "
            "$_.Name -like 'python*' -and ("
            "$_.CommandLine -match 'coffee_server\\.py|transparent_badminton_desktop\\.py|rally_desktop\\.py|badminton_overlay\\.py|strike_desktop\\.py|coffee_pet\\.py|desktop_shovel_pet\\.py' "
            "-and ($_.CommandLine -match $root -or ($portPids -contains $_.ProcessId) -or $_.CommandLine -match '--port\\s+" + str(HTTP_PORT) + "')"
            ") } | ForEach-Object { "
            "Write-Output ('终止进程 PID=' + $_.ProcessId); "
            "Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
        )
        r = subprocess.run(
            ['powershell', '-NoProfile', '-Command', ps],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            **_win_hidden_kwargs(),
        )
        if r.stdout.strip():
            print(r.stdout.strip(), flush=True)
    print('[完成] 相关本地进程已清理。', flush=True)


def spawn_detached(cmd, log_path):
    CERT_DIR.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env['PYTHONUTF8'] = '1'
    env['CODEX_HOLO_PORT'] = str(HTTP_PORT)
    env['CODEX_HOLO_HTTPS_PORT'] = str(HTTPS_PORT)
    with open(log_path, 'wb') as log_f:
        return subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            close_fds=True,
            **_win_hidden_kwargs(new_group=True),
        )


def check_firewall_hint():
    if sys.platform != 'win32':
        return
    hidden_kw = _win_hidden_kwargs()
    try:
        prof = subprocess.check_output(['netsh', 'advfirewall', 'show', 'currentprofile'], stderr=subprocess.STDOUT, timeout=1.0, **hidden_kw)
        txt = prof.decode('utf-8', errors='ignore') + prof.decode('gbk', errors='ignore')
        active = any(('状态' in line or 'State' in line) and ('启用' in line or 'ON' in line.upper()) for line in txt.splitlines())
        if not active:
            return
        rule_name = f'Codex-Holo-Pet-TCP-{HTTP_PORT}'
        chk = subprocess.run(['netsh', 'advfirewall', 'firewall', 'show', 'rule', f'name={rule_name}'], capture_output=True, timeout=1.0, **hidden_kw)
        if chk.returncode != 0:
            add = subprocess.run(
                ['netsh', 'advfirewall', 'firewall', 'add', 'rule', f'name={rule_name}', 'dir=in', 'action=allow', 'protocol=TCP', f'localport={HTTP_PORT}'],
                capture_output=True, timeout=1.0, **hidden_kw,
            )
            if add.returncode == 0:
                print(f'      已自动注册局域网防火墙放行规则 (端口 {HTTP_PORT})。', flush=True)
            else:
                print(f'      [提示] Windows 防火墙已开启；若手机扫码无法访问，可放行端口 {HTTP_PORT} 或让电脑连手机热点！', flush=True)
    except Exception:
        pass


def ensure_server():
    server_log = CERT_DIR / 'server-startup.log'
    try:
        info = http_get_json(f'{BASE_URL}/api/pet/mode', timeout=1.2)
        if isinstance(info, dict) and 'mode' in info:
            print('      本地三合一中枢已在运行中，复用现有服务。', flush=True)
            return info
    except Exception:
        pass

    # 若端口被旧版仅羽毛球服务或僵尸进程占用，先清理再启动新版中枢
    try:
        http_get_json(f'{BASE_URL}/api/badminton/status', timeout=0.8)
        print('      检测到旧版本地服务占用端口，正在自动切换为新版三合一中枢...', flush=True)
        stop_all()
        time.sleep(0.5)
    except Exception:
        pass

    print(f'      正在后台启动本地全息与桌宠同步服务 (端口 {HTTP_PORT})...', flush=True)
    proc = spawn_detached(
        [_gui_python_executable(), '-u', str(ROOT / 'coffee_server.py'), '--port', str(HTTP_PORT), '--https-port', str(HTTPS_PORT)],
        server_log,
    )
    deadline = time.monotonic() + 18.0
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            break
        try:
            info = http_get_json(f'{BASE_URL}/api/pet/mode', timeout=0.8)
            if isinstance(info, dict) and 'mode' in info:
                return info
        except Exception:
            time.sleep(0.15)

    print('\n[错误] 本地同步服务未能就绪！启动日志如下：', flush=True)
    print('-' * 72, flush=True)
    if server_log.is_file():
        print(server_log.read_text(encoding='utf-8', errors='replace')[-2000:], flush=True)
    print('-' * 72, flush=True)
    pause_exit(1)


def open_browser_url(url):
    try:
        if sys.platform == 'win32':
            os.startfile(url)
            return
    except Exception:
        pass
    try:
        webbrowser.open(url)
    except Exception:
        pass


def launch_desktop_pet(mode):
    gui_exe = _gui_python_executable()

    target_mode = 'coffee' if mode in ('workbench', 'coffee') else mode
    if target_mode == 'badminton':
        cmd = [gui_exe, str(ROOT / 'app' / 'badminton_overlay.py')]
        has_cam = bool(importlib.util.find_spec('cv2') and importlib.util.find_spec('mediapipe'))
        if not has_cam:
            print('      [提示] 未安装摄像头视觉扩展，自动切为「纯鼠标挥拍（免摄像头权限）」！', flush=True)
            cmd.append('--no-camera')
        log_path = CERT_DIR / 'badminton-desktop-launch.log'
        expect_key = 'badminton_desktop_online'
    elif target_mode == 'strike':
        cmd = [gui_exe, str(ROOT / 'strike_desktop.py')]
        log_path = CERT_DIR / 'strike-desktop-launch.log'
        expect_key = 'coffee_desktop_online'
    else:
        cmd = [gui_exe, str(ROOT / 'coffee_pet.py')]
        log_path = CERT_DIR / 'coffee-desktop-launch.log'
        expect_key = 'coffee_desktop_online'

    try:
        info = http_get_json(f'{BASE_URL}/api/pet/mode', timeout=1.2)
    except Exception:
        info = {}

    if not info.get(expect_key):
        cleanup_orphan_pets(target_mode)
        spawn_detached(cmd, log_path)
        deadline = time.monotonic() + 7.0
        online = False
        while time.monotonic() < deadline:
            try:
                cur = http_get_json(f'{BASE_URL}/api/pet/mode', timeout=0.8)
                if cur.get(expect_key):
                    online = True
                    break
            except Exception:
                pass
            time.sleep(0.25)
        if online:
            print('      透明桌面小人已上线！', flush=True)
        else:
            print('      [警告] 透明桌面小人未能在 7 秒内上线！日志：', flush=True)
            if log_path.is_file():
                print(log_path.read_text(encoding='utf-8', errors='replace')[-1500:], flush=True)
            pet_err = CERT_DIR / 'pet-errors.log'
            if pet_err.is_file():
                print(pet_err.read_text(encoding='utf-8', errors='replace')[-1000:], flush=True)
    else:
        print('      当前透明桌面小人已在运行中。', flush=True)


def run_diagnose_python():
    print('========================================================================', flush=True)
    print('[错误] 未找到带 tkinter 的标准桌面版 Python (3.9~3.13)！', flush=True)
    if not check_tkinter():
        print('[诊断] 当前 Python 缺少 tkinter 图形库（大概率是嵌入式 Embedded Python）！', flush=True)
        print('       嵌入式 Python 无法显示透明桌面桌宠，也无法加载依赖。', flush=True)
    print('请执行以下命令自动安装标准桌面版 Python 3.11（或交由 AI Agent 自动处理）：', flush=True)
    print('  winget install -e --id Python.Python.3.11 --scope user --accept-package-agreements --accept-source-agreements', flush=True)
    print('========================================================================', flush=True)
    pause_exit(1)


def main():
    setup_console()
    mode = (sys.argv[1] if len(sys.argv) > 1 else 'workbench').strip().lower()

    if mode == '--diagnose-python':
        run_diagnose_python()

    if mode == 'stop':
        stop_all()
        pause_exit(0)

    print('========================================================================', flush=True)
    print(f'  Codex 全息桌宠 V2.0 本地启动助手  (安全端口: {HTTP_PORT} / {HTTPS_PORT})', flush=True)
    print('========================================================================\n', flush=True)

    if not check_tkinter():
        run_diagnose_python()

    print(f'[1/3] 已定位标准 Python 环境: {sys.executable}', flush=True)

    if mode == 'install':
        print('正在安装本地依赖与可选摄像头/语音识别组件...', flush=True)
        r = subprocess.run([sys.executable, str(ROOT / 'app' / 'install_rally.py')], cwd=str(ROOT))
        if r.returncode != 0:
            print('\n[提示] 安装未全部成功，请检查上方输出。', flush=True)
            pause_exit(1)
        print('\n[完成] 依赖安装成功！现在双击「0-一键启动_Codex全息桌宠三合一工作台.bat」即可开玩。', flush=True)
        pause_exit(0)

    if not ensure_core_deps():
        print('\n[错误] 轻量核心依赖 (Pillow / qrcode) 自动安装失败！请检查网络后重试或运行 4-环境依赖一键安装.bat。', flush=True)
        pause_exit(1)

    print(f'[2/3] 正在检查并启动本地权威同步服务 ({BASE_URL})...', flush=True)
    ensure_server()
    check_firewall_hint()

    try:
        subprocess.run(
            [sys.executable, str(ROOT / 'network_helper.py'), '--no-open'],
            cwd=str(ROOT), capture_output=True, timeout=6, **_win_hidden_kwargs(),
        )
    except Exception:
        pass

    if mode == 'guide':
        print('[3/3] 正在打开局域网配置与手机扫码向导...', flush=True)
        try:
            subprocess.run([sys.executable, str(ROOT / 'network_helper.py')], cwd=str(ROOT), timeout=10)
        except Exception:
            open_browser_url(f'{BASE_URL}/guide')
        pause_exit(0)

    target_mode = 'coffee' if mode == 'workbench' else mode
    if target_mode in ('coffee', 'strike', 'badminton'):
        try:
            http_post_json(f'{BASE_URL}/api/pet/mode', {'mode': target_mode, 'spawn': False}, timeout=1.5)
        except Exception:
            pass

    print('[3/3] 正在启动透明桌面 Codex 小人与网页工作台...', flush=True)
    launch_desktop_pet(mode)

    if mode == 'workbench':
        urls = [f'{BASE_URL}/']
    elif mode == 'coffee':
        urls = [f'{BASE_URL}/coffee/holo', f'{BASE_URL}/coffee/pour']
    elif mode == 'strike':
        urls = [f'{BASE_URL}/strike/dash']
    elif mode == 'badminton':
        urls = [f'{BASE_URL}/badminton/director']
    else:
        urls = [f'{BASE_URL}/']

    if os.environ.get('CODEX_LAUNCHER_NO_BROWSER') != '1':
        for u in urls:
            open_browser_url(u)

    print(f'\n[完成] 已打开工作台/控制台: {", ".join(urls)}', flush=True)
    print('       提示：桌面小人支持点击弹出对话、右键快捷操作与左下角切换【倒咖啡 / 搓澡 / 羽毛球】！', flush=True)
    time.sleep(2.5)


if __name__ == '__main__':
    main()
