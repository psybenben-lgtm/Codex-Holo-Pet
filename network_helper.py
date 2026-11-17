# -*- coding: utf-8 -*-
"""
局域网网络自适应与手机连接向导 (network_helper.py V2.1 本地环境适配版)
1. 智能排除 VPN / Clash / WSL 虚拟网卡，自动识别真实 Wi-Fi 局域网 IP。
2. 使用统一安全端口 (默认 29765/29766，绝不使用 8765/18765)。
3. 生成内嵌标准可扫二维码与实时服务状态检测的《手机连接向导.html》，同时供服务端 /guide 路由复用。
"""
import base64
from io import BytesIO
import os
from pathlib import Path
import sys
from urllib.parse import quote
import webbrowser

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / '.rally-runtime'
if RUNTIME.is_dir() and str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'app'))

from badminton_engine import detect_lan_ips
from local_runtime import get_http_port, get_https_port, get_no_proxy_opener

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


def make_qr_png_bytes(text):
    """生成高对比度标准 QR 二维码 PNG 字节流（带标准静区，手机秒扫）。"""
    import qrcode
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=9, border=4)
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color='#000000', back_color='#ffffff').convert('RGB')
    buf = BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def _qr_img_src(text, inline_base64=True):
    if inline_base64:
        try:
            b64 = base64.b64encode(make_qr_png_bytes(text)).decode('ascii')
            return f'data:image/png;base64,{b64}'
        except Exception:
            pass
    return f'/api/qrcode?text={quote(text, safe="")}'


def build_guide_html(ips=None, http_port=None, https_port=None, inline_qr=True):
    """构建完整本地适配的《多设备连接中心与配置向导》HTML 内容。"""
    ips = ips or detect_lan_ips()
    port = int(http_port or get_http_port())
    sport = int(https_port or get_https_port())
    primary_ip = ips[0] if ips else '127.0.0.1'

    badminton_dir_url = f'http://127.0.0.1:{port}/badminton/director'
    badminton_holo_url = f'http://{primary_ip}:{port}/badminton/holo'
    badminton_ctrl_url = f'http://{primary_ip}:{port}/badminton/ctrl'
    strike_dash_url = f'http://127.0.0.1:{port}/strike/dash'
    strike_holo_url = f'http://{primary_ip}:{port}/coffee/holo?mode=strike&faces=4'
    bath_url = f'http://{primary_ip}:{port}/coffee/bath'
    pour_url = f'http://{primary_ip}:{port}/coffee/pour'
    download_url = f'http://{primary_ip}:{port}/download'

    qr_holo_src = _qr_img_src(badminton_holo_url, inline_base64=inline_qr)
    qr_ctrl_src = _qr_img_src(badminton_ctrl_url, inline_base64=inline_qr)
    qr_bath_src = _qr_img_src(bath_url, inline_base64=inline_qr)
    qr_dl_src = _qr_img_src(download_url, inline_base64=inline_qr)

    ip_options = '\n'.join(
        f'<option value="{ip}" {"selected" if i == 0 else ""}>{ip} {"(推荐主局域网 Wi-Fi)" if i == 0 else ""}</option>'
        for i, ip in enumerate(ips)
    )
    ip_badges = ' · '.join(f'<code>{ip}:{port}</code>' for ip in ips)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Codex 全息桌宠 V2.0 · 本地网络适配与多设备连接向导</title>
    <style>
        :root {{
            --bg: #090d16;
            --card-bg: rgba(22, 30, 49, 0.92);
            --border: #2a3859;
            --accent: #38bdf8;
            --accent-green: #4ade80;
            --accent-orange: #fb923c;
            --text: #f1f5f9;
            --muted: #94a3b8;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background: radial-gradient(circle at 50% 0%, #172554 0%, var(--bg) 75%);
            color: var(--text);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
            padding: 26px 16px 48px;
            display: flex;
            justify-content: center;
            min-height: 100vh;
        }}
        .container {{ max-width: 980px; width: 100%; }}
        .header {{ text-align: center; margin-bottom: 20px; }}
        .header h1 {{ font-size: 24px; font-weight: 800; color: #fff; margin-bottom: 8px; }}
        .header p {{ color: var(--muted); font-size: 13.5px; line-height: 1.6; }}
        .status-row {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            justify-content: center;
            align-items: center;
            margin-top: 12px;
        }}
        .badge-ip {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: #1e293b;
            border: 1px solid var(--accent);
            color: var(--accent);
            padding: 6px 14px;
            border-radius: 999px;
            font-size: 13px;
            font-weight: bold;
        }}
        .badge-srv {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: rgba(234, 179, 8, 0.14);
            border: 1px solid #facc15;
            color: #fde047;
            padding: 6px 14px;
            border-radius: 999px;
            font-size: 13px;
            font-weight: bold;
        }}
        .badge-srv.online {{
            background: rgba(22, 163, 74, 0.18);
            border-color: #4ade80;
            color: #4ade80;
        }}
        .badge-srv.offline {{
            background: rgba(220, 38, 38, 0.18);
            border-color: #f87171;
            color: #fca5a5;
        }}
        .ip-bar {{
            margin: 14px auto 18px;
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 12px 16px;
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            align-items: center;
            justify-content: space-between;
        }}
        .ip-bar select, .ip-bar input {{
            background: #0d1322;
            color: #f8fafc;
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 7px 10px;
            font-size: 13px;
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
            gap: 16px;
        }}
        @media (max-width: 520px) {{
            .grid {{ grid-template-columns: 1fr; }}
        }}
        .card {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 18px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            gap: 12px;
        }}
        .card-title {{ font-size: 16px; font-weight: 800; }}
        .card-desc {{ color: var(--muted); font-size: 12.5px; line-height: 1.55; margin-top: 4px; }}
        .qr-row {{
            display: flex;
            gap: 14px;
            align-items: center;
            margin-top: 8px;
        }}
        .qr-img {{
            width: 112px;
            height: 112px;
            border-radius: 10px;
            background: #fff;
            padding: 5px;
            flex-shrink: 0;
        }}
        .url-box {{
            background: #0d1322;
            border: 1px solid #1f2c47;
            border-radius: 8px;
            padding: 9px 12px;
            font-family: Consolas, monospace;
            font-size: 12px;
            color: var(--accent);
            word-break: break-all;
            user-select: all;
            margin-top: 8px;
            flex: 1;
        }}
        .btn {{
            display: inline-block;
            text-align: center;
            padding: 10px 16px;
            border-radius: 8px;
            text-decoration: none;
            font-size: 13.5px;
            font-weight: bold;
            color: #fff;
            cursor: pointer;
            border: none;
        }}
        .btn-gold {{ background: #d97706; }}
        .btn-cyan {{ background: #0284c7; }}
        .btn-green {{ background: #15803d; }}
        .btn-purple {{ background: #7e22ce; }}
        .btn-slate {{ background: #334155; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏸 Codex 全息桌宠 V2.0 · 本地局域网配置与连接向导</h1>
            <p>已完成本地环境适配（使用独立端口 {port}/{sport}，已自动过滤 Clash/VPN/WSL 虚拟网卡）。请确保手机与电脑连在同一个 Wi-Fi 下。</p>
            <div class="status-row">
                <div class="badge-ip">可用局域网 IP: {ip_badges}</div>
                <div class="badge-srv" id="srvStatusBadge">⏳ 正在检测本地同步服务 ({port})...</div>
                <button class="btn" id="btnGuideShutdown" style="display:none;background:#dc2626;padding:6px 14px;border-radius:999px;font-size:12.5px;" onclick="shutdownServer()">⏻ 停止桌面与服务</button>
            </div>
        </div>

        <div class="ip-bar">
            <div style="font-size:13px;font-weight:700;">📡 切换局域网 IP（自动更新二维码与手机链接）：</div>
            <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
                <select id="selIp">{ip_options}</select>
                <input type="text" id="customIp" placeholder="或手动输入 IP (如 192.168.1.5)">
                <button class="btn btn-cyan" style="padding:7px 12px;font-size:12.5px;" onclick="applyIp()">应用 IP</button>
                <button class="btn btn-slate" style="padding:7px 12px;font-size:12.5px;" onclick="refreshLan()">🔄 刷新网卡</button>
            </div>
        </div>
        <div id="netDiagBar" style="margin:-6px 0 14px;padding:10px 14px;border-radius:10px;background:#0f172a;border:1px solid #1e293b;font-size:12.5px;color:#cbd5e1;display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;">
            <span id="netDiagText">📡 请用手机连接同一 Wi-Fi（或电脑连接手机热点），扫描下方二维码；若扫码超时请确认 Windows 防火墙放行 {port} 端口。</span>
        </div>

        <div class="grid">
            <div class="card" style="border-top: 3px solid #f59e0b;">
                <div>
                    <div class="card-title" style="color: #fbbf24;">🎛️ 电脑端：网页主控制台 + 透明桌宠与摄像头</div>
                    <div class="card-desc">双击 0 号启动器会自动打开透明桌宠、桌面左下角悬浮控制条及电脑网页控制台，可一键开启/切换摄像头、查看镜像校准、开始开打或关闭桌宠。</div>
                    <div class="url-box" id="urlDir">{badminton_dir_url}</div>
                </div>
                <a href="{badminton_dir_url}" id="linkDir" target="_blank" class="btn btn-gold">🎛️ 打开电脑网页主控制台</a>
            </div>

            <div class="card" style="border-top: 3px solid var(--accent-orange);">
                <div>
                    <div class="card-title" style="color: var(--accent-orange);">🔮 手机 A：3D 全息微型羽毛球发球机</div>
                    <div class="card-desc">用全息投影手机扫左侧二维码或访问下方地址，放上四面金字塔。手机发球后，同一颗球从电脑边缘飞向 Codex；正常对打后会连发七球。</div>
                    <div class="qr-row">
                        <img class="qr-img" id="qrHolo" src="{qr_holo_src}" alt="手机 A 全息端二维码">
                        <div class="url-box" id="urlHolo">{badminton_holo_url}</div>
                    </div>
                </div>
                <a href="{badminton_holo_url}" id="linkHolo" target="_blank" class="btn btn-cyan">打开手机 A 全息发球机</a>
            </div>

            <div class="card" style="border-top: 3px solid var(--accent);">
                <div>
                    <div class="card-title" style="color: var(--accent);">📱 手机 B：辅助控制与远程导演端</div>
                    <div class="card-desc">手机遥控与辅助导演面板，支持远程触发开打、参数调节与音效控制（本地摄像头开关请使用电脑网页控制台或桌面悬浮条）。</div>
                    <div class="qr-row">
                        <img class="qr-img" id="qrCtrl" src="{qr_ctrl_src}" alt="手机 B 导演遥控端二维码">
                        <div class="url-box" id="urlCtrl">{badminton_ctrl_url}</div>
                    </div>
                </div>
                <a href="{badminton_ctrl_url}" id="linkCtrl" target="_blank" class="btn btn-purple">打开手机 B 导演遥控端</a>
            </div>

            <div class="card" style="border-top: 3px solid var(--accent-green);">
                <div>
                    <div class="card-title" style="color: var(--accent-green);">⛏️ 保留旧版玩法 &amp; 客户端下载中心</div>
                    <div class="card-desc">完整兼容第一版全息挖土甩泥、木桶泡澡搓澡、倾斜倒咖啡，以及安卓伴侣 App 下载页。</div>
                    <div class="qr-row">
                        <img class="qr-img" id="qrBath" src="{qr_bath_src}" alt="旧版泡澡搓澡二维码">
                        <div class="url-box" id="urlLegacy">全息挖土: {strike_holo_url}<br>手机搓澡: {bath_url}<br>手机倒咖啡: {pour_url}<br>客户端下载: {download_url}</div>
                    </div>
                </div>
                <div style="display:flex;gap:8px;flex-wrap:wrap;">
                    <a href="{strike_dash_url}" id="linkDash" target="_blank" class="btn btn-green" style="flex:1;">打开挖土与搓澡控制台</a>
                    <a href="http://127.0.0.1:{port}/download" target="_blank" class="btn btn-slate">📱 App 下载页</a>
                </div>
            </div>
        </div>
    </div>

    <script>
        const PORT = {port};
        const LOCAL_API = location.protocol.startsWith('http') ? location.origin : `http://127.0.0.1:${{PORT}}`;

        function checkServer() {{
            const badge = document.getElementById('srvStatusBadge');
            const stopBtn = document.getElementById('btnGuideShutdown');
            fetch(`${{LOCAL_API}}/api/badminton/status`, {{ cache: 'no-store' }})
                .then(r => {{
                    if (!r.ok) throw new Error('status');
                    badge.className = 'badge-srv online';
                    badge.textContent = `✅ 本地同步服务已就绪 (端口 ${{PORT}})`;
                    if (stopBtn) stopBtn.style.display = 'inline-block';
                }})
                .catch(() => {{
                    badge.className = 'badge-srv offline';
                    badge.textContent = `❌ 本地同步服务未启动，请先双击「0-一键启动」或「3-局域网配置向导」bat`;
                    if (stopBtn) stopBtn.style.display = 'none';
                }});
        }}

        function shutdownServer() {{
            if (!confirm('确认停止本地桌宠与后台同步服务？')) return;
            fetch(`${{LOCAL_API}}/api/system/shutdown`, {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: '{{}}'
            }}).then(() => {{
                const badge = document.getElementById('srvStatusBadge');
                const stopBtn = document.getElementById('btnGuideShutdown');
                if (badge) {{
                    badge.className = 'badge-srv offline';
                    badge.textContent = '⏻ 后台服务与桌宠已停止，可关闭此页面';
                }}
                if (stopBtn) stopBtn.style.display = 'none';
                try {{ window.close(); }} catch {{}}
            }}).catch(() => {{}});
        }}

        function setQrSrc(imgId, targetUrl) {{
            const img = document.getElementById(imgId);
            if (!img) return;
            img.src = `${{LOCAL_API}}/api/qrcode?text=${{encodeURIComponent(targetUrl)}}`;
        }}

        function updateUrls(ip, syncServer = true) {{
            const clean = (ip || '127.0.0.1').trim();
            const holo = `http://${{clean}}:${{PORT}}/badminton/holo`;
            const ctrl = `http://${{clean}}:${{PORT}}/badminton/ctrl`;
            const strikeHolo = `http://${{clean}}:${{PORT}}/coffee/holo?mode=strike&faces=4`;
            const bath = `http://${{clean}}:${{PORT}}/coffee/bath`;
            const pour = `http://${{clean}}:${{PORT}}/coffee/pour`;
            const dl = `http://${{clean}}:${{PORT}}/download`;

            document.getElementById('urlHolo').textContent = holo;
            document.getElementById('linkHolo').href = holo;
            document.getElementById('urlCtrl').textContent = ctrl;
            document.getElementById('linkCtrl').href = ctrl;
            document.getElementById('urlLegacy').innerHTML =
                `全息挖土: ${{strikeHolo}}<br>手机搓澡: ${{bath}}<br>手机倒咖啡: ${{pour}}<br>客户端下载: ${{dl}}`;

            setQrSrc('qrHolo', holo);
            setQrSrc('qrCtrl', ctrl);
            setQrSrc('qrBath', bath);
            if (syncServer) {{
                fetch(`${{LOCAL_API}}/coffee/lan`, {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ ip: clean }})
                }}).then(r => r.ok ? r.json() : null).then(updateDiag).catch(() => {{}});
            }}
        }}

        function updateDiag(lan) {{
            const el = document.getElementById('netDiagText');
            if (!el || !lan) return;
            if (lan.firewall_warning) {{
                el.innerHTML = `⚠️ <strong>${{lan.firewall_warning}}</strong> · 可选方案：电脑连手机热点后点「🔄 刷新网卡」`;
                el.style.color = '#fbbf24';
            }} else if (lan.ip && lan.ip !== '127.0.0.1') {{
                el.textContent = `✅ 本机已绑定 0.0.0.0:${{PORT}}，当前可访问局域网 IP：${{lan.ip}}（手机同一 Wi-Fi 下直接扫码即可）`;
                el.style.color = '#4ade80';
            }}
        }}

        function refreshLan() {{
            fetch(`${{LOCAL_API}}/coffee/lan`, {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ refresh: true }})
            }}).then(r => r.ok ? r.json() : null).then(lan => {{
                if (!lan || !lan.ips?.length) return;
                const sel = document.getElementById('selIp');
                sel.innerHTML = lan.ips.map((x, i) => `<option value="${{x}}"${{x === lan.ip ? ' selected' : ''}}>${{x}}${{i === 0 ? ' (推荐 Wi-Fi)' : ''}}</option>`).join('');
                updateUrls(lan.ip, false);
                updateDiag(lan);
            }}).catch(() => {{}});
        }}

        document.getElementById('selIp').addEventListener('change', e => updateUrls(e.target.value, true));
        function applyIp() {{
            const custom = document.getElementById('customIp').value.trim();
            const ip = custom || document.getElementById('selIp').value;
            updateUrls(ip, true);
        }}

        checkServer();
        refreshLan();
        setInterval(checkServer, 3000);
    </script>
</body>
</html>
"""


def generate_guide_html(ips, out_dir):
    http_port = get_http_port()
    https_port = get_https_port()
    html_content = build_guide_html(ips, http_port=http_port, https_port=https_port, inline_qr=True)
    out_path = os.path.join(out_dir, '手机连接向导.html')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    return out_path


def main():
    ips = detect_lan_ips()
    primary_ip = ips[0]
    http_port = get_http_port()
    out_dir = os.path.dirname(os.path.abspath(__file__))
    guide_path = generate_guide_html(ips, out_dir)
    print(f'Recommended LAN IP: {primary_ip} (All detected: {ips}, Port: {http_port})')
    print(f'Generated guide: {guide_path}')
    if '--no-open' not in sys.argv:
        target = guide_path
        try:
            with get_no_proxy_opener().open(f'http://127.0.0.1:{http_port}/api/badminton/status', timeout=0.6) as resp:
                if resp.status == 200:
                    target = f'http://127.0.0.1:{http_port}/guide'
        except Exception:
            pass
        try:
            webbrowser.open(target)
        except Exception:
            pass


if __name__ == '__main__':
    main()
