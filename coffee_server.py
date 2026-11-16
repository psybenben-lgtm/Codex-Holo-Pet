"""Serve the hologram, coffee stages, strike digging, bath/scrubbing, and V2.0 Transparent Desktop Badminton Drama."""
import argparse
import datetime as dt
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import math
import importlib.util
import os
from pathlib import Path
import plistlib
import queue
import socket
import ssl
import subprocess
import sys
import threading
import time
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'app'))

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from badminton_engine import BadmintonDirectorEngine, detect_lan_ips
from badminton_live import LiveBadminton, PROTOCOL
from coffee_work import has_codex_cli, work_states
from local_runtime import FORBIDDEN_PORTS, get_http_port, get_https_port, get_udp_port
import network_helper
import pc_voice
from strike_engine import StrikeEngine


def live_action_allowed(client_ip: str, action: str) -> bool:
    """校验实时联动接口权限：宿主机生命周期限本机，球局/手势/摄像头遥控放行局域网手机端。"""
    try:
        addr = ipaddress.ip_address(str(client_ip).strip())
        addr = getattr(addr, 'ipv4_mapped', None) or addr
    except ValueError:
        return False
    host_only = {'desktop', 'close', 'launch_overlay'}
    if action in host_only:
        return addr.is_loopback
    lan_ctrl = {
        'start', 'swing', 'barrage', 'quit', 'hand_mode', 'poke',
        'camera_power', 'camera_retry', 'camera_switch', 'camera_preview', 'bar',
    }
    if action in lan_ctrl:
        return addr.is_loopback or addr.is_private or addr.is_link_local
    return True


sys.dont_write_bytecode = True


def _detect_local_ip():
    ips = detect_lan_ips()
    return ips[0] if ips else '127.0.0.1'


HTTP = get_http_port()
HTTPS = get_https_port()
UDP_PORT = get_udp_port()


class _FallbackHoloServerModule:
    """独立全息 HTTP/UDP 服务基类：100% 保证脱离外部目录独立零报错运行。"""
    LOCAL_IP = _detect_local_ip()
    ASSETS_DIR = str(ROOT / 'coffee')
    MOBILE_HTML_PATH = str(ROOT / 'coffee' / 'index.html')
    SPRITES_JS_PATH = str(ROOT / 'coffee' / 'pixel.js')
    CURRENT_HOLO_MODE = 'fuzz'

    class QuietThreadingHTTPServer(ThreadingHTTPServer):
        daemon_threads = True
        allow_reuse_address = True

        def handle_error(self, request, client_address):
            exc = sys.exc_info()[1]
            if isinstance(exc, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, ssl.SSLError, socket.timeout)):
                return
            super().handle_error(request, client_address)

    ThreadingHTTPServer = QuietThreadingHTTPServer

    class HoloV4Handler(SimpleHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def do_GET(self):
            url = urlsplit(self.path)
            path = url.path.rstrip('/')
            if path in ('', '/holo'):
                content = (ROOT / 'coffee' / 'badminton_holo.html').read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
            self.send_error(404)

        def do_POST(self):
            self.send_error(404)

    @staticmethod
    def get_local_ip():
        return _detect_local_ip()

    @staticmethod
    def start_udp_discovery_responder():
        def _respond():
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(('0.0.0.0', UDP_PORT))
                while True:
                    data, addr = sock.recvfrom(1024)
                    if b'HOLO' in data or b'COFFEE' in data:
                        reply = json.dumps({'ip': _FallbackHoloServerModule.LOCAL_IP, 'port': HTTP}).encode('utf-8')
                        sock.sendto(reply, addr)
            except Exception:
                pass
        threading.Thread(target=_respond, daemon=True).start()


legacy = _FallbackHoloServerModule
CAPACITY = 0.8
strike_stage = StrikeEngine()
badminton_stage = BadmintonDirectorEngine()
live_badminton = LiveBadminton()
badminton_stage.http_port = HTTP
badminton_stage.https_port = HTTPS
FLIGHT_MS = 165
SOURCE_MS = 85
CERT_DIR = ROOT / 'coffee' / '.lan-certificate'


class UnifiedCoordinator:
    """三合一模式切换、空白电脑 Codex 状态模拟与零权限隐私配置中枢。"""

    def __init__(self):
        self.lock = threading.Lock()
        self.mode = 'coffee'
        self.work_override = 'auto'
        self.raw_work = 'waiting'
        self.keyboard_capture = True
        self.camera_deps_ready = bool(
            importlib.util.find_spec('cv2') and importlib.util.find_spec('mediapipe')
        )
        self.badminton_control = 'camera' if self.camera_deps_ready else 'mouse'
        self.holo_faces = 4
        self.coffee_desktop_at = -100.0
        self.mode_seq = 0
        self.chat_seq = 0
        self.chat_text = ''

    def effective_work(self):
        with self.lock:
            if self.work_override in ('working', 'idle'):
                return self.work_override
            return self.raw_work

    def snapshot(self):
        now = time.monotonic()
        with self.lock:
            bm_snap = live_badminton.snapshot()
            coffee_online = (now - self.coffee_desktop_at) < 4.5
            bm_online = bool(bm_snap.get('desktop_online')) and not bm_snap.get('closed')
            return {
                'mode': self.mode,
                'mode_seq': self.mode_seq,
                'desktop_online': bm_online if self.mode == 'badminton' else coffee_online,
                'coffee_desktop_online': coffee_online,
                'badminton_desktop_online': bm_online,
                'codex_cli_detected': has_codex_cli(),
                'work_override': self.work_override,
                'raw_work': self.raw_work,
                'effective_work': self.work_override if self.work_override in ('working', 'idle') else self.raw_work,
                'keyboard_capture': self.keyboard_capture,
                'camera_deps_ready': self.camera_deps_ready,
                'badminton_control': self.badminton_control,
                'holo_faces': self.holo_faces,
                'chat_seq': self.chat_seq,
                'chat_text': self.chat_text,
            }

    def set_work_override(self, override):
        if override not in ('auto', 'working', 'idle'):
            raise ValueError('invalid work override')
        with self.lock:
            self.work_override = override
            eff = self.work_override if self.work_override in ('working', 'idle') else self.raw_work
        with stage.lock:
            if stage.work != eff:
                stage.work = eff
                stage.publish()
        with strike_stage.lock:
            strike_stage.office_mode = (eff == 'working')
            strike_stage.working = (eff == 'working')
        return self.snapshot()

    def set_privacy(self, body):
        with self.lock:
            if 'keyboard_capture' in body:
                self.keyboard_capture = bool(body['keyboard_capture'])
            if 'badminton_control' in body and str(body['badminton_control']) in ('camera', 'mouse'):
                req = str(body['badminton_control'])
                self.badminton_control = 'mouse' if (req == 'camera' and not self.camera_deps_ready) else req
            if 'holo_faces' in body:
                self.holo_faces = 1 if int(body['holo_faces']) == 1 else 4
            ctrl = self.badminton_control
            bm_online = bool(live_badminton.snapshot().get('desktop_online'))
        if bm_online and 'badminton_control' in body:
            try:
                live_badminton.action('camera_power', {'enabled': ctrl == 'camera'})
            except Exception:
                pass
        return self.snapshot()

    def push_chat(self, text):
        with self.lock:
            self.chat_seq += 1
            self.chat_text = str(text or '')[:48]
        return self.snapshot()

    def _spawn_pet(self, target_mode):
        py_exe = Path(sys.executable)
        py_gui = py_exe.with_name('pythonw.exe')
        exe = str(py_gui if py_gui.is_file() else py_exe)
        env = os.environ.copy()
        env['PYTHONUTF8'] = '1'
        env['CODEX_HOLO_PORT'] = str(HTTP)
        env['CODEX_HOLO_HTTPS_PORT'] = str(HTTPS)
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0) | getattr(subprocess, 'DETACHED_PROCESS', 0)
        if target_mode == 'badminton':
            cmd = [exe, str(ROOT / 'app' / 'badminton_overlay.py')]
            if self.badminton_control != 'camera' or not self.camera_deps_ready:
                cmd.append('--no-camera')
        else:
            cmd = [exe, str(ROOT / 'coffee_pet.py')]
            if target_mode == 'strike':
                cmd.append('--strike')
        subprocess.Popen(cmd, cwd=str(ROOT), env=env, creationflags=flags)

    def switch_mode(self, target_mode, *, spawn=True):
        if target_mode not in ('coffee', 'strike', 'badminton'):
            raise ValueError('invalid mode')
        with self.lock:
            prev_mode = self.mode
            self.mode = target_mode
            self.mode_seq += 1
        with stage.lock:
            stage.android_coffee = (target_mode == 'coffee')
            stage.publish()
        if not spawn:
            return self.snapshot()
        now = time.monotonic()
        if target_mode == 'badminton':
            if not live_badminton.snapshot().get('desktop_online'):
                self._spawn_pet('badminton')
        else:
            if prev_mode == 'badminton' or live_badminton.snapshot().get('desktop_online'):
                try:
                    live_badminton.action('close', {})
                except Exception:
                    pass
            with self.lock:
                coffee_alive = (now - self.coffee_desktop_at) < 4.0
            if not coffee_alive:
                self._spawn_pet(target_mode)
        return self.snapshot()


pet_hub = UnifiedCoordinator()


def milliseconds():
    return time.time_ns() // 1_000_000


def read_work_state(thread_id):
    for work in work_states(ROOT, thread_id):
        with pet_hub.lock:
            pet_hub.raw_work = work
            eff = pet_hub.work_override if pet_hub.work_override in ('working', 'idle') else work
        with stage.lock:
            if stage.work != eff:
                stage.work = eff
                stage.publish()


class CoffeeStage:
    def __init__(self):
        self.lock = threading.Lock()
        self.clients = set()
        self.work = 'waiting'
        self.android_coffee = False
        self.shutdown = False
        self.round = 0
        self.reset()

    def reset(self):
        self.round = max(milliseconds(), self.round + 1)
        self.owner = ''
        self.seq = 0
        self.sample_at = 0
        self.sent = self.base = self.flow = 0
        self.last_land = 0
        self.parcels = []

    def snapshot(self):
        now = milliseconds()
        while self.parcels and self.parcels[0][0] < now - 1600:
            self.base = self.parcels.pop(0)[1]
        return dict(now=now, round=self.round, owner=self.owner, sent=self.sent,
                    base=self.base, parcels=self.parcels.copy(), flow=self.flow,
                    sampleAt=self.sample_at, lastLand=self.last_land, work=self.work,
                    shutdown=self.shutdown)

    def publish(self):
        snapshot = self.snapshot()
        for client in list(self.clients):
            try:
                client.get_nowait()
            except queue.Empty:
                pass
            try:
                client.put_nowait(snapshot)
            except queue.Full:
                pass

    def pour(self, data):
        owner = str(data.get('owner', 'carafe-default'))
        seq = int(data.get('seq', 1))
        amount, flow = float(data.get('amount', 0)), float(data.get('flow', 0))
        if not (math.isfinite(amount) and math.isfinite(flow)):
            raise ValueError('invalid pour')
        now = milliseconds()
        req_round = data.get('round', self.round)
        if req_round != self.round or (seq <= self.seq and owner == self.owner):
            return
        if self.owner and self.owner != owner and now - self.sample_at < 1400:
            return
        if self.sent >= CAPACITY:
            return
        self.owner, self.seq, self.sample_at = owner, seq, now
        amount = min(CAPACITY, max(self.sent, amount))
        self.flow = max(0.0, min(1.0, flow))
        if amount > self.sent:
            self.last_land = max(now + SOURCE_MS + FLIGHT_MS, self.last_land + 1)
            self.parcels.append((self.last_land, amount, self.flow))
            self.sent = amount
        self.publish()


stage = CoffeeStage()


class CoffeeHandler(legacy.HoloV4Handler):
    def _add_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Origin, Accept')

    def do_OPTIONS(self):
        self.send_response(204)
        self._add_cors_headers()
        self.send_header('Content-Length', '0')
        self.end_headers()

    def send_bytes(self, content, content_type, filename=None):
        self.send_response(200)
        self._add_cors_headers()
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        if filename:
            self.send_header('Content-Disposition', f'inline; filename="{filename}"')
        self.end_headers()
        self.wfile.write(content)

    def send_json(self, data):
        self.send_bytes(json.dumps(data, ensure_ascii=False).encode('utf-8'), 'application/json; charset=utf-8')

    def do_GET(self):
        url = urlsplit(self.path)
        path = url.path.rstrip('/')
        query = parse_qs(url.query)

        if path in ('', '/workbench'):
            wb = ROOT / 'coffee' / 'workbench.html'
            target = wb if wb.is_file() else (ROOT / 'coffee' / 'index.html')
            self.send_bytes(target.read_bytes(), 'text/html; charset=utf-8')
            return
        if path == '/api/pet/mode':
            self.send_json(pet_hub.snapshot())
            return
        if path in ('/api/work_state', '/api/privacy'):
            self.send_json(pet_hub.snapshot())
            return
        # V2.0 羽毛球互动路由 & 本地向导与二维码接口
        if path in ('/badminton', '/badminton/director', '/badminton/ctrl'):
            self.send_bytes((ROOT / 'coffee' / 'badminton_director.html').read_bytes(), 'text/html; charset=utf-8')
            return
        if path == '/badminton/holo':
            self.send_bytes((ROOT / 'coffee' / 'badminton_holo.html').read_bytes(), 'text/html; charset=utf-8')
            return
        if path in ('/guide', '/connect', '/lan'):
            ips = detect_lan_ips()
            html = network_helper.build_guide_html(ips, http_port=HTTP, https_port=HTTPS, inline_qr=False)
            self.send_bytes(html.encode('utf-8'), 'text/html; charset=utf-8')
            return
        if path == '/api/qrcode':
            text = (query.get('text') or [''])[0]
            if not text:
                self.send_error(400)
                return
            try:
                png = network_helper.make_qr_png_bytes(text)
                self.send_bytes(png, 'image/png')
            except Exception:
                import html as _h
                safe = _h.escape(text)
                svg = (
                    '<svg xmlns="http://www.w3.org/2000/svg" width="220" height="220" viewBox="0 0 220 220">'
                    '<rect width="220" height="220" rx="14" fill="#0f172a" stroke="#38bdf8" stroke-width="2"/>'
                    '<text x="110" y="92" text-anchor="middle" fill="#facc15" font-size="13" font-family="sans-serif">缺少 qrcode 依赖</text>'
                    '<text x="110" y="118" text-anchor="middle" fill="#cbd5e1" font-size="11" font-family="sans-serif">手机浏览器直接输入网址：</text>'
                    f'<text x="110" y="142" text-anchor="middle" fill="#38bdf8" font-size="10" font-family="monospace">{safe[:30]}</text>'
                    '</svg>'
                ).encode('utf-8')
                self.send_bytes(svg, 'image/svg+xml; charset=utf-8')
            return
        if path == '/qr_download.png':
            host_header = self.headers.get('Host', '').strip()
            if host_header:
                target_url = f'http://{host_header}/download'
            else:
                ips = detect_lan_ips()
                ip = getattr(self.server, 'fixed_lan_ip', None) or badminton_stage.preferred_ip or ips[0]
                target_url = f'http://{ip}:{HTTP}/download'
            try:
                png = network_helper.make_qr_png_bytes(target_url)
                self.send_bytes(png, 'image/png')
            except Exception:
                self.send_error(500)
            return
        if path == '/api/badminton/live/status':
            self.send_json(live_badminton.snapshot())
            return
        if path == '/api/badminton/live/stream':
            self.stream_badminton(live_badminton)
            return
        if path == '/api/badminton/status':
            self.send_json(badminton_stage.snapshot())
            return
        if path == '/api/badminton/stream':
            self.stream_badminton()
            return

        if path == '/holo' and query.get('live') == ['1'] and 'classic' not in query:
            # 荣耀 APK 打开 /holo?live=1 时默认引导至全息羽毛球发球机或挖土全息
            self.send_response(302)
            self._add_cors_headers()
            self.send_header('Location', '/badminton/holo?faces=4')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        elif path == '/api/strike/stream':
            self.stream_strike()
        elif path == '/api/strike/status':
            self.send_json(strike_stage.snapshot())
        elif path == '/api/strike/clock':
            self.send_json({'now': strike_stage.clock()})
        elif path in ('/strike', '/strike/holo'):
            self.send_response(302)
            self._add_cors_headers()
            self.send_header('Location', '/coffee/holo?mode=strike&faces=4')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', '0')
            self.end_headers()
        elif path in ('/bath', '/strike/bath'):
            self.send_response(302)
            self._add_cors_headers()
            self.send_header('Location', '/coffee/bath')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', '0')
            self.end_headers()
        elif path == '/coffee/events':
            self.stream_coffee()
        elif path == '/coffee/clock':
            self.send_json({'now': milliseconds()})
        elif path == '/coffee/lan':
            ips = detect_lan_ips()
            badminton_stage.lan_ips = ips
            ip = getattr(self.server, 'fixed_lan_ip', None) or (
                badminton_stage.preferred_ip if badminton_stage.preferred_ip in ips else ips[0]
            )
            self.send_json({
                'ip': ip,
                'ips': ips,
                'lan_ips': ips,
                'http_port': HTTP,
                'https_port': HTTPS,
                'tls': bool(getattr(self.server, 'tls_ready', False)),
                'director_url': f'http://127.0.0.1:{HTTP}/badminton/director',
                'holo_url': f'http://{ip}:{HTTP}/badminton/holo',
                'ctrl_url': f'http://{ip}:{HTTP}/badminton/ctrl',
                'guide_url': f'http://127.0.0.1:{HTTP}/guide',
            })
        elif path == '/coffee/ios-profile.mobileconfig' and getattr(self.server, 'tls_ready', False):
            cert = (CERT_DIR / 'coffee-root.cer').read_bytes()
            from hashlib import sha256
            profile_id = 'local.coffee.' + sha256(cert).hexdigest()[:16]
            payload = dict(PayloadType='com.apple.security.root', PayloadVersion=1,
                           PayloadIdentifier=profile_id + '.ca', PayloadUUID=str(uuid4()),
                           PayloadDisplayName='Coffee LAN', PayloadCertificateFileName='coffee-root.cer',
                           PayloadContent=cert)
            profile = dict(PayloadType='Configuration', PayloadVersion=1, PayloadIdentifier=profile_id,
                           PayloadUUID=str(uuid4()), PayloadDisplayName='Coffee LAN',
                           PayloadDescription=f'HTTPS certificate for coffee at {self.server.lan_ip}',
                           PayloadContent=[payload])
            self.send_bytes(plistlib.dumps(profile), 'application/x-apple-aspen-config', 'coffee-lan.mobileconfig')
        elif path == '/coffee/certificate' and getattr(self.server, 'tls_ready', False):
            self.send_bytes((CERT_DIR / 'coffee-root.cer').read_bytes(), 'application/x-x509-ca-cert', 'coffee-root.cer')
        elif path in ('/coffee', '/coffee/pour', '/coffee/bath', '/coffee/holo', '/coffee/desk'):
            self.send_bytes((ROOT / 'coffee' / 'index.html').read_bytes(), 'text/html; charset=utf-8')
        elif path in ('/strike/dash', '/dash', '/strike/control', '/fuzz', '/controller'):
            self.send_bytes((ROOT / 'coffee' / 'strike_dashboard.html').read_bytes(), 'text/html; charset=utf-8')
        elif path in ('/download', '/download.html', '/app', '/coffee/download.html'):
            dl_path = ROOT / 'coffee' / 'download.html'
            if dl_path.is_file():
                self.send_bytes(dl_path.read_bytes(), 'text/html; charset=utf-8')
            else:
                self.send_error(404)
        elif path == '/favicon.ico':
            self.send_response(204)
            self._add_cors_headers()
            self.end_headers()
        elif path.startswith('/coffee/') or path.startswith('/sfx/') or path.startswith('/assets/') or path.startswith('/docs/'):
            mime_map = {
                '.js': 'text/javascript; charset=utf-8',
                '.css': 'text/css; charset=utf-8',
                '.html': 'text/html; charset=utf-8',
                '.wav': 'audio/wav',
                '.mp3': 'audio/mpeg',
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.webp': 'image/webp',
                '.svg': 'image/svg+xml',
                '.json': 'application/json; charset=utf-8',
            }
            rel_parts = [p for p in path.lstrip('/').split('/') if p and p not in ('.', '..')]
            candidates = []
            if rel_parts:
                candidates.append(ROOT.joinpath(*rel_parts))
                rel_name = rel_parts[-1]
                for folder in (ROOT / 'coffee', ROOT / 'assets' / 'audio', ROOT / 'assets', ROOT / 'sfx'):
                    candidates.append(folder / rel_name)
            for candidate in candidates:
                try:
                    resolved = candidate.resolve()
                    if not str(resolved).startswith(str(ROOT.resolve())):
                        continue
                    if resolved.is_file():
                        mime = mime_map.get(resolved.suffix.lower(), 'application/octet-stream')
                        self.send_bytes(resolved.read_bytes(), mime)
                        return
                except OSError:
                    continue
            self.send_error(404)
        else:
            self.send_error(404)

    def do_POST(self):
        path = urlsplit(self.path).path.rstrip('/')

        if path in ('/api/pet/mode', '/api/pet/heartbeat', '/api/pet/chat', '/api/work_state', '/api/privacy'):
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 <= size <= 4096:
                    raise ValueError('Invalid request size')
                body = json.loads(self.rfile.read(size)) if size else {}
                if not isinstance(body, dict):
                    raise ValueError('Expected a JSON object')
                if path == '/api/pet/mode':
                    res = pet_hub.switch_mode(
                        str(body.get('mode', 'coffee')),
                        spawn=bool(body.get('spawn', True)),
                    )
                elif path == '/api/pet/heartbeat':
                    with pet_hub.lock:
                        pet_hub.coffee_desktop_at = time.monotonic()
                        if 'mode' in body and str(body['mode']) in ('coffee', 'strike') and pet_hub.mode != 'badminton':
                            pet_hub.mode = str(body['mode'])
                    res = pet_hub.snapshot()
                elif path == '/api/pet/chat':
                    res = pet_hub.push_chat(body.get('text', ''))
                elif path == '/api/work_state':
                    res = pet_hub.set_work_override(str(body.get('override', 'auto')))
                else:
                    res = pet_hub.set_privacy(body)
                self.send_json(res)
            except (TypeError, ValueError, KeyError) as exc:
                self.send_json({'ok': False, 'error': str(exc)})
            return

        # 全系统停止接口（同时通知桌面端退出并优雅停止本地 HTTP/HTTPS 服务）
        if path == '/api/system/shutdown':
            with stage.lock:
                stage.shutdown = True
                stage.publish()
            badminton_stage.request_system_shutdown()
            live_badminton.action('close', {})
            self.send_json({'ok': True, 'shutdown': True})
            threading.Timer(0.35, shutdown_active_servers).start()
            return

        if path.startswith('/api/badminton/live/'):
            action=path.rsplit('/',1)[-1]
            if not live_action_allowed(self.client_address[0], action):
                self.send_error(403)
                return
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0 <= size <= 2048:
                    self.send_error(413)
                    return
                data=json.loads(self.rfile.read(size)) if size else {}
                if not isinstance(data,dict):
                    raise ValueError('expected object')
                if action == 'launch_overlay':
                    import subprocess
                    snap = live_badminton.snapshot()
                    launched = False
                    if not snap.get('desktop_online'):
                        py_exe = Path(sys.executable)
                        py_gui = py_exe.with_name('pythonw.exe')
                        cmd = [str(py_gui if py_gui.is_file() else py_exe), str(ROOT / 'app' / 'badminton_overlay.py')]
                        if data.get('camera_enabled') is False:
                            cmd.append('--no-camera')
                        if data.get('camera_index') is not None:
                            cmd.extend(['--camera', str(max(0, int(data['camera_index'])))])
                        env = os.environ.copy()
                        env['PYTHONUTF8'] = '1'
                        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0) | getattr(subprocess, 'DETACHED_PROCESS', 0)
                        subprocess.Popen(cmd, cwd=str(ROOT), env=env, creationflags=flags)
                        launched = True
                    else:
                        snap = live_badminton.action('bar', {'visible': True, 'expanded': True})
                        if data.get('camera_enabled') is True:
                            snap = live_badminton.action('camera_power', {'enabled': True})
                    snap['applied'] = True
                    snap['launched'] = launched
                    self.send_json(snap)
                    return
                self.send_json(live_badminton.action(action, data))
            except KeyError:
                self.send_error(404)
            except (ValueError, TypeError, OverflowError):
                self.send_error(400)
            return

        # V2.0 羽毛球互动 POST API
        if path.startswith('/api/badminton/'):
            try:
                size = int(self.headers.get('Content-Length', '0'))
                body = json.loads(self.rfile.read(size)) if size > 0 else {}
                action = path.removeprefix('/api/badminton/')
                if action == 'start_play':
                    res = badminton_stage.start_play_with_me()
                elif action == 'jump_scene':
                    res = badminton_stage.jump_to_scene(str(body.get('scene_id', 'S0')))
                elif action == 'prev_scene':
                    res = badminton_stage.prev_scene()
                elif action == 'next_scene':
                    res = badminton_stage.next_scene()
                elif action == 'replay_scene':
                    res = badminton_stage.replay_current_scene()
                elif action == 'set_paused':
                    res = badminton_stage.set_paused(bool(body.get('paused', False)))
                elif action == 'manual_serve':
                    res = badminton_stage.manual_serve(fast=bool(body.get('fast', False)))
                elif action == 'manual_swing':
                    res = badminton_stage.trigger_manual_swing(
                        power=float(body.get('power', 35.0)),
                        source=str(body.get('source', 'director_manual'))
                    )
                elif action == 'camera_frame':
                    res = badminton_stage.report_camera_frame(
                        hand_detected=bool(body.get('hand_detected', False)),
                        x=float(body.get('x', 0.5)),
                        y=float(body.get('y', 0.5)),
                        speed=float(body.get('speed', 0.0)),
                        source=str(body.get('source', 'webrtc'))
                    )
                elif action == 'update_params':
                    res = badminton_stage.update_params(body)
                elif action == 'refresh_lan':
                    res = badminton_stage.refresh_lan_ips()
                elif action == 'close_desktop':
                    res = badminton_stage.request_desktop_close()
                    live_badminton.action('close', {})
                elif action == 'heartbeat':
                    extra = {}
                    if 'mode' in body:
                        extra['mode'] = body.get('mode')
                    if body.get('reset_close'):
                        extra['reset_close'] = True
                    res = badminton_stage.heartbeat_device(
                        role=str(body.get('role', 'ctrl')),
                        rtt_ms=float(body.get('rtt_ms', 0.0)),
                        ack_event_id=int(body.get('ack_event_id', 0)),
                        extra=extra or None
                    )
                else:
                    self.send_error(404)
                    return
                self.send_json(res)
            except Exception as exc:
                self.send_json({'ok': False, 'error': str(exc)})
            return

        if path.startswith('/api/strike/'):
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 <= size <= 4096:
                    raise ValueError('Invalid request size')
                body = json.loads(self.rfile.read(size)) if size else {}
                if not isinstance(body, dict):
                    raise ValueError('Expected a JSON object')

                if path == '/api/strike/input':
                    hits = max(1, min(60, int(body.get('hits', 1))))
                    res = strike_stage.record_input(hits)
                elif path == '/api/strike/desktop':
                    hits = max(0, min(60, int(body.get('hits', 0))))
                    if not pet_hub.keyboard_capture:
                        hits = 0
                    working = bool(body.get('working', False)) or (pet_hub.effective_work() == 'working')
                    enabled = bool(body.get('enabled', True))
                    res = strike_stage.record_input(hits, working=working, enabled=enabled)
                elif path == '/api/strike/discover':
                    res = strike_stage.trigger_discovery_manually(body.get('kind'))
                elif path == '/api/strike/angry':
                    res = strike_stage.trigger_angry_manually(int(body.get('stage', 1)))
                elif path == '/api/strike/trigger':
                    res = strike_stage.trigger_strike_manually()
                elif path == '/api/strike/bath_push':
                    res = strike_stage.push_bathtub()
                elif path == '/api/strike/bath_knob':
                    res = strike_stage.update_bath_knob(
                        temp=body.get('temp'),
                        foam=body.get('foam'),
                        water_level=body.get('water_level'),
                    )
                elif path == '/api/strike/scrub_start':
                    res = strike_stage.start_scrubbing(immediate=bool(body.get('immediate', False)))
                elif path == '/api/strike/scrub_move':
                    res = strike_stage.scrub_move(
                        x=body.get('x', 0.5),
                        y=body.get('y', 0.55),
                        dx=body.get('dx', 0.0),
                        dy=body.get('dy', 0.0),
                        zone=body.get('zone', 'back'),
                        delta=body.get('delta', 3.5),
                    )
                elif path == '/api/strike/return_office':
                    res = strike_stage.return_to_office()
                elif path == '/api/strike/reset':
                    res = strike_stage.reset()
                else:
                    self.send_error(404)
                    return
                self.send_json(res)
            except (TypeError, ValueError, OverflowError) as exc:
                self.send_json({'ok': False, 'error': str(exc)})
            return

        if path in ('/api/pc_speak', '/api/pc_speech_stop'):
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 16000:
                    raise ValueError('Invalid speech request size')
                data = json.loads(self.rfile.read(size))
                if path.endswith('_stop'):
                    pc_voice.stop(data.get('id'))
                    self.send_json({'ok': True})
                else:
                    self.send_json(pc_voice.speak(data))
            except (ValueError, RuntimeError) as exc:
                self.send_json({'ok': False, 'error': str(exc)})
            return

        if path not in ('/coffee/pour', '/coffee/reset', '/coffee/mode'):
            if getattr(self.server, 'server_port', HTTP) == HTTP:
                super().do_POST()
            else:
                self.send_error(404)
            return

        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 <= size <= 2048:
                raise ValueError('invalid size')
            data = json.loads(self.rfile.read(size)) if size else {}
            with stage.lock:
                if path == '/coffee/mode':
                    stage.android_coffee = data.get('coffee') is True
                elif path == '/coffee/reset':
                    if not data.get('round') or data.get('round') == stage.round:
                        stage.reset()
                        stage.publish()
                else:
                    stage.pour(data)
                snapshot = stage.snapshot()
        except (TypeError, ValueError, KeyError) as exc:
            self.send_json({'ok': False, 'error': str(exc)})
            return
        self.send_json(snapshot)

    def stream_badminton(self, engine=None):
        engine=engine or badminton_stage
        self.send_response(200)
        self._add_cors_headers()
        self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache, no-transform')
        self.send_header('X-Accel-Buffering', 'no')
        self.end_headers()
        q = engine.subscribe()
        try:
            while True:
                try:
                    snapshot = q.get(timeout=1.5)
                except queue.Empty:
                    snapshot = engine.snapshot()
                evt = {"type": "badminton_tick", "data": snapshot}
                self.wfile.write(b'data: ' + json.dumps(evt, ensure_ascii=False).encode('utf-8') + b'\n\n')
                self.wfile.flush()
        except OSError:
            pass
        finally:
            engine.unsubscribe(q)

    def stream_strike(self):
        self.send_response(200)
        self._add_cors_headers()
        self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache, no-transform')
        self.send_header('X-Accel-Buffering', 'no')
        self.end_headers()
        q = strike_stage.subscribe()
        try:
            while True:
                try:
                    snapshot = q.get(timeout=2.0)
                except queue.Empty:
                    snapshot = strike_stage.snapshot()
                evt = {"type": "state_tick", "data": snapshot}
                self.wfile.write(b'data: ' + json.dumps(evt, ensure_ascii=False).encode('utf-8') + b'\n\n')
                self.wfile.flush()
        except OSError:
            pass
        finally:
            strike_stage.unsubscribe(q)

    def stream_coffee(self):
        self.send_response(200)
        self._add_cors_headers()
        self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache, no-transform')
        self.send_header('X-Accel-Buffering', 'no')
        self.end_headers()
        client = queue.Queue(maxsize=1)
        with stage.lock:
            stage.clients.add(client)
            client.put_nowait(stage.snapshot())
        try:
            while True:
                try:
                    state = client.get(timeout=4)
                except queue.Empty:
                    with stage.lock:
                        state = stage.snapshot()
                self.wfile.write(b'data: ' + json.dumps(state, separators=(',', ':')).encode('utf-8') + b'\n\n')
                self.wfile.flush()
        except OSError:
            pass
        finally:
            with stage.lock:
                stage.clients.discard(client)


def tls_context(ip, extra_ips=None):
    """为本机回环 (127.0.0.1) 与所有真实局域网 IP 签发多 SAN 本地证书。"""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    CERT_DIR.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc)
    chain, private = CERT_DIR / 'chain.pem', CERT_DIR / 'server-key.pem'
    root = CERT_DIR / 'coffee-root.cer'

    target_ips = []
    for candidate in ['127.0.0.1', ip, *(extra_ips or [])]:
        try:
            addr = ipaddress.ip_address(candidate)
            if addr not in target_ips:
                target_ips.append(addr)
        except ValueError:
            continue

    try:
        cert = x509.load_pem_x509_certificate(chain.read_bytes())
        san_ips = set(cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.IPAddress))
        reusable = (all(addr in san_ips for addr in target_ips)
                    and cert.not_valid_after_utc > now + dt.timedelta(days=1)
                    and private.is_file() and root.is_file())
    except (OSError, ValueError, x509.ExtensionNotFound):
        reusable = False
    if not reusable:
        root_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f'Coffee LAN {ip}')])
        leaf_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, ip)])

        def builder(subject, issuer, pubkey, days):
            return (x509.CertificateBuilder().subject_name(subject).issuer_name(issuer)
                    .public_key(pubkey).serial_number(x509.random_serial_number())
                    .not_valid_before(now - dt.timedelta(days=1))
                    .not_valid_after(now + dt.timedelta(days=days)))

        ca = (builder(ca_name, ca_name, root_key.public_key(), 366)
              .add_extension(x509.BasicConstraints(ca=True, path_length=0), True)
              .add_extension(x509.KeyUsage(True, False, False, False, False, True, True, False, False), True)
              .sign(root_key, hashes.SHA256()))
        leaf = (builder(leaf_name, ca_name, key.public_key(), 365)
                .add_extension(x509.BasicConstraints(ca=False, path_length=None), True)
                .add_extension(x509.SubjectAlternativeName([x509.IPAddress(addr) for addr in target_ips]), False)
                .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), False)
                .sign(root_key, hashes.SHA256()))
        root.write_bytes(ca.public_bytes(serialization.Encoding.DER))
        chain.write_bytes(leaf.public_bytes(serialization.Encoding.PEM) + ca.public_bytes(serialization.Encoding.PEM))
        private.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                              serialization.NoEncryption()))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(chain), str(private))
    return context


ACTIVE_SERVERS = []


def shutdown_active_servers():
    """优雅关闭所有当前活跃的 HTTP/HTTPS 服务并退出服务进程。"""
    for srv in list(ACTIVE_SERVERS):
        try:
            srv.shutdown()
        except Exception:
            pass
    try:
        badminton_stage._stop.set()
        live_badminton.stop.set()
    except Exception:
        pass


def main():
    global HTTP, HTTPS
    parser = argparse.ArgumentParser()
    parser.add_argument('--ip')
    parser.add_argument('--port', type=int)
    parser.add_argument('--https-port', type=int)
    parser.add_argument('--thread', default=os.environ.get('CODEX_THREAD_ID'))
    parser.add_argument('--open', action='store_true')
    parser.add_argument('--legacy-automation', action='store_true')
    args = parser.parse_args()
    if args.port:
        if args.port in FORBIDDEN_PORTS:
            raise SystemExit(f'端口 {args.port} 已按要求禁用，请改用其它本地端口 (默认 {HTTP})')
        HTTP = args.port
        HTTPS = args.https_port or (HTTP + 1 if (HTTP + 1) not in FORBIDDEN_PORTS else HTTP + 2)
    elif args.https_port:
        if args.https_port in FORBIDDEN_PORTS:
            raise SystemExit(f'端口 {args.https_port} 已按要求禁用')
        HTTPS = args.https_port

    badminton_stage.http_port = HTTP
    badminton_stage.https_port = HTTPS

    all_ips = detect_lan_ips()
    legacy.LOCAL_IP = str(ipaddress.IPv4Address(args.ip or all_ips[0]))
    with legacy.ThreadingHTTPServer(('0.0.0.0', HTTP), CoffeeHandler) as http:
        http.lan_ip, http.tls_ready = legacy.LOCAL_IP, False
        http.fixed_lan_ip = args.ip
        https = None
        try:
            context = tls_context(legacy.LOCAL_IP, extra_ips=all_ips)
            https = legacy.ThreadingHTTPServer(('0.0.0.0', HTTPS), CoffeeHandler)
            https.socket = context.wrap_socket(https.socket, server_side=True, do_handshake_on_connect=False)
            https.lan_ip, https.tls_ready = legacy.LOCAL_IP, True
            https.fixed_lan_ip = args.ip
            http.tls_ready = True
            threading.Thread(target=https.serve_forever, daemon=True).start()
        except (OSError, ImportError, ValueError) as exc:
            print(f'HTTPS 可选回退 (HTTP {HTTP} 正常运行): {exc}', flush=True)
            if https:
                https.server_close()
                https = None
        ACTIVE_SERVERS.clear()
        ACTIVE_SERVERS.append(http)
        if https:
            ACTIVE_SERVERS.append(https)
        legacy.start_udp_discovery_responder()
        threading.Thread(target=read_work_state, args=(args.thread,), daemon=True).start()
        print('=' * 68, flush=True)
        print('  ✨ [Codex 全息桌宠三合一工作台] 本地互动中枢已就绪！', flush=True)
        print(f'  🖥️  三合一工作台(总览/切换/扫码): http://127.0.0.1:{HTTP}/', flush=True)
        print(f'  🧭 多设备连接与配置向导:         http://127.0.0.1:{HTTP}/guide', flush=True)
        print(f'  🎬 羽毛球导演与鼠标/摄像头控制台: http://127.0.0.1:{HTTP}/badminton/director', flush=True)
        print(f'  🔮 手机 A 全息发球机端:          http://{legacy.LOCAL_IP}:{HTTP}/badminton/holo', flush=True)
        print('=' * 68, flush=True)
        if args.open:
            import webbrowser
            threading.Thread(target=webbrowser.open, args=(f'http://127.0.0.1:{HTTP}/',), daemon=True).start()
        try:
            http.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            pc_voice.stop()
            if https:
                https.shutdown()
                https.server_close()


if __name__ == '__main__':
    main()
