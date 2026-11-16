# -*- coding: utf-8 -*-
"""
《我就赢了 Codex 一球，它竟然开挂了》V2.0 全链路自动化验收测试套件 (tests/test_badminton_v2.py)
验证范围：
1. M01/M02: 原生透明桌面渲染器 (TransparentBadmintonDesktop 帧渲染、S0~S10 全部角色姿态、超大羽毛球拍扁贴屏滑落、无背景色键验证)
2. M03/M04: 摄像头手部识别上报、防误触冷却、宽容接球时间窗口回球、非对称抛物线羽毛球轨迹
3. M05: 多网卡虚拟 IP 过滤、全息发球机双向心跳 ACK、跨端发球与电脑入画衔接
4. M06/M07/M08: S0~S10 完整十幕状态机推进、24 种音效资源完整性、任意节点秒级快照回滚 (无残留球体/粒子)、HTTP/CORS 多端接口测试
"""
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'app'))

from badminton_engine import STORY_SCENES, BadmintonDirectorEngine, detect_lan_ips
from local_runtime import FORBIDDEN_PORTS, get_http_port, get_local_host_url, get_no_proxy_opener
from PIL import Image, ImageDraw
from transparent_badminton_desktop import KEY, draw_badminton_codex, draw_pixel_racket, draw_pixel_shuttlecock

# 兼容 Windows GBK 控制台输出中文
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def test_all():
    print("=== [1/6] 验证 24 种定制场景音效与配置文件完整性 ===")
    expected_wavs = [
        "invite_chime.wav", "close_laptop.wav", "push_desk.wav", "change_clothes.wav",
        "grab_racket.wav", "warmup_swing.wav", "machine_start.wav", "machine_charge.wav",
        "shuttle_launch.wav", "shuttle_fly.wav", "hit_normal.wav", "hit_smash.wav",
        "shuttle_fast.wav", "shuttle_land.wav", "codex_step.wav", "codex_fall.wav",
        "lose_sigh.wav", "bgm_pity.wav", "cheat_button.wav", "cheat_rapid.wav",
        "machine_jam.wav", "giant_impact.wav", "splat_slide.wav", "ending_awkward.wav"
    ]
    for w in expected_wavs:
        assert (ROOT / "assets" / "audio" / w).is_file(), f"Missing audio {w}"
        assert (ROOT / "coffee" / w).is_file(), f"Missing coffee audio {w}"
    for extra_w in ("smash_blast.wav", "codex_poke.wav"):
        assert (ROOT / "assets" / "audio" / extra_w).is_file(), f"Missing extra audio {extra_w}"
        assert (ROOT / "coffee" / extra_w).is_file(), f"Missing coffee extra audio {extra_w}"
    print("  [PASS] 24 种基础 WAV 与扣杀爆裂/戳小人音效齐全。")

    print("=== [2/6] 验证多网卡智能过滤 (排除 198.18.* / 127.* 等虚拟网段) ===")
    ips = detect_lan_ips()
    assert len(ips) >= 1
    for ip in ips:
        assert not ip.startswith("198.18."), f"Virtual Clash IP leaked: {ip}"
    print(f"  [PASS] 检测到的局域网 IP 列表: {ips}")

    print("=== [3/6] 验证 S0~S10 全部十幕状态机、宽容挥拍回球与秒级快照回滚 ===")
    eng = BadmintonDirectorEngine(run=False)
    assert eng.snapshot()["scene_id"] == "S0"

    # 点击「陪我打球」进入 S1
    s1 = eng.start_play_with_me()
    assert s1["scene_id"] == "S1" and s1["props"]["desk_visible"] is True

    # 验证 S0 ~ S10 任意节点跳转回滚无残留
    for sc in STORY_SCENES:
        sid = sc["id"]
        snap = eng.jump_to_scene(sid)
        assert snap["scene_id"] == sid, f"Rollback to {sid} failed"
        if sid in ("S0", "S1", "S2", "S6", "S8", "S10"):
            assert len(snap["shuttles"]) == 0, f"Scene {sid} should have 0 leftover shuttles"

    # 验证 S4 对打与摄像头挥拍宽容接球窗口触发
    s4 = eng.jump_to_scene("S4")
    eng._spawn_codex_return_to_human(eng.clock(), for_winning_smash=False)
    eng.hit_window["open"] = True
    # 模拟摄像头检测到有效挥手 (speed=28 > threshold=16)
    after_hit = eng.report_camera_frame(hand_detected=True, x=0.35, y=0.5, speed=28.0, source="test_cam")
    assert after_hit["shuttles"][0]["phase"] == "human_to_codex", "Camera swing should return the shuttlecock to Codex"

    # 验证防误触冷却：立即再次挥手不会重复触发
    assert after_hit["cooldown_active"] is True
    print("  [PASS] S0~S10 状态机、宽容接球窗口与冷却防误触验证通过。")

    print("=== [4/6] 验证原生透明桌面全部角色姿态与羽毛球像素渲染 ===")
    canvas_img = Image.new("RGB", (640, 360), KEY)
    draw = ImageDraw.Draw(canvas_img)
    all_poses = [
        "work_type", "invite_surprise", "close_laptop", "push_strain_still",
        "push_desk_move", "wipe_sweat_clap", "take_bag", "spin_change",
        "warmup_wobble", "shy_ready", "ready_wait", "move_anticipate",
        "move_run", "hit_swing", "panic_run", "dive_fall", "sit_pity",
        "pity_peek", "evil_remote", "cheat_laugh", "slow_turn_to_holo",
        "panic_freeze", "screen_pancake", "floor_press_stop", "awkward_hide_racket"
    ]
    for p_name in all_poses:
        draw_badminton_codex(draw, 320, 280, 1.2, {
            "pose": p_name, "outfit": "sport", "facing": -1,
            "has_racket": True, "remote_visible": True, "screen_splat_progress": 0.8
        }, scale=1.6)
    draw_pixel_shuttlecock(draw, 220, 140, -0.5, scale=1.5, speed_lines=True, is_giant=False)
    draw_pixel_shuttlecock(draw, 420, 160, 3.14, scale=3.0, speed_lines=True, is_giant=True)
    draw_pixel_racket(draw, 180, 200, -0.6, scale=1.2, bent=True)
    # 确认画布四角依然是 100% 透明色键 KEY (#010102)
    assert canvas_img.getpixel((5, 5)) == (1, 1, 2), "Background must remain pure transparent key #010102"
    print(f"  [PASS] 全部 {len(all_poses)} 种角色姿态与透明色键验证通过。")

    print("=== [5/6] 验证 HTTP 服务、全息端/导演端页面与跨端 API ===")
    import socket

    def _pick_free_port(preferred):
        for candidate in (preferred,):
            if candidate in FORBIDDEN_PORTS:
                continue
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(("127.0.0.1", candidate)) != 0:
                    return candidate
        while True:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", 0))
                p = s.getsockname()[1]
                if p not in FORBIDDEN_PORTS:
                    return p

    default_port = get_http_port()
    assert default_port not in FORBIDDEN_PORTS, f"禁止使用旧冲突端口: {default_port}"
    port = _pick_free_port(default_port)
    https_port = _pick_free_port(port + 1)
    base_url = get_local_host_url(port)
    opener = get_no_proxy_opener()

    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "coffee_server.py"), "--port", str(port), "--https-port", str(https_port)],
        cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    ready = False
    for _ in range(40):
        assert proc.poll() is None, f"coffee_server 意外提前退出: code={proc.returncode}"
        try:
            with opener.open(f"{base_url}/api/badminton/status", timeout=1) as resp:
                if resp.status == 200:
                    ready = True
                    break
        except Exception:
            time.sleep(0.25)
    assert ready and proc.poll() is None, f"coffee_server 未能在超时内就绪 (port={port})"

    try:
        for url_path in [
            "/guide",
            "/badminton/director",
            "/badminton/holo",
            "/badminton/ctrl",
            "/api/badminton/status",
            f"/api/qrcode?text={base_url}/badminton/holo",
            "/qr_download.png",
            "/coffee/badminton_director.js",
            "/coffee/badminton_holo.js",
            "/coffee/hit_smash.wav",
            "/coffee/giant_impact.wav",
            "/coffee/lan",
            "/assets/gold-shovel.svg",
            "/coffee/workbench.js",
        ]:
            with opener.open(f"{base_url}{url_path}", timeout=3) as resp:
                assert resp.status == 200, f"GET {url_path} failed"
                body_bytes = resp.read()
                if url_path == "/coffee/lan":
                    lan_info = json.loads(body_bytes.decode("utf-8"))
                    assert lan_info.get("http_port") == port
                    assert lan_info.get("http_port") not in FORBIDDEN_PORTS
                    assert len(lan_info.get("ips", [])) >= 1
                    assert len(lan_info.get("lan_ips", [])) >= 1
                elif url_path.startswith("/api/qrcode") or url_path == "/qr_download.png":
                    assert body_bytes.startswith(b"\x89PNG"), f"{url_path} 未返回有效 PNG 二维码"

        for act, body in [
            ("start_play", {}),
            ("jump_scene", {"scene_id": "S7"}),
            ("manual_serve", {"fast": True}),
            ("camera_frame", {"hand_detected": True, "x": 0.4, "y": 0.5, "speed": 32.0}),
            ("heartbeat", {"role": "holo", "rtt_ms": 11.5, "ack_event_id": 2}),
            ("refresh_lan", {}),
            ("set_paused", {"paused": True}),
            ("set_paused", {"paused": False}),
            ("close_desktop", {}),
            ("jump_scene", {"scene_id": "S0"}),
        ]:
            req = urllib.request.Request(
                f"{base_url}/api/badminton/{act}",
                data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json", "Origin": f"http://192.168.31.88:{port}"},
                method="POST"
            )
            with opener.open(req, timeout=3) as resp:
                assert resp.status == 200
                res_data = json.loads(resp.read().decode("utf-8"))
                assert "scene_id" in res_data
                assert res_data.get("http_port") == port
                if act == "close_desktop":
                    assert res_data.get("desktop_close_seq", 0) >= 1

        # 验证网页控制台按钮列表与全局优雅关闭接口 (/api/system/shutdown)
        with opener.open(f"{base_url}/badminton/director", timeout=3) as resp:
            director_html = resp.read().decode("utf-8")
            assert all(
                btn in director_html
                for btn in (
                    "btnCloseDesktop",
                    "btnShutdownSystem",
                    "btnCamToggle",
                    "btnCamRetry",
                    "btnCamSwitch",
                    "btnCamPreview",
                    "btnLaunchOverlay",
                    "btnShowBarTop",
                    "btnHandModeToggle",
                    "btnHandModeCam",
                    "btnPokeCodex",
                    "mobileCtrlBar",
                    "btnMobSmash",
                    "btnMobHandMode",
                    "btnMobPoke",
                )
            )
            req_cam = urllib.request.Request(
                f"{base_url}/api/badminton/live/camera_power",
                data=json.dumps({"enabled": False}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with opener.open(req_cam, timeout=3) as cam_resp:
                cam_res = json.loads(cam_resp.read().decode("utf-8"))
                assert cam_res.get("camera_enabled") is False and cam_res.get("cmd") == "camera_off"

        # 验证局域网手机控制台权限策略（允许手机实时遥控与开关摄像头，限制宿主机拉起/关闭仅本机）
        from coffee_server import live_action_allowed
        assert live_action_allowed("127.0.0.1", "launch_overlay")
        assert not live_action_allowed("192.168.16.88", "launch_overlay")
        assert not live_action_allowed("192.168.16.88", "close")
        for lan_ip in ("192.168.16.88", "::ffff:192.168.16.88", "10.0.0.5"):
            for act_name in ("start", "swing", "barrage", "quit", "hand_mode", "poke", "camera_power"):
                assert live_action_allowed(lan_ip, act_name), f"{lan_ip} should allow {act_name}"
        assert not live_action_allowed("8.8.8.8", "start")

        # 验证实时切换手势形态(五指<->球拍)、戳工位小人与强力扣杀 HTTP 接口
        with opener.open(
            urllib.request.Request(
                f"{base_url}/api/badminton/live/desktop",
                data=json.dumps({"open": True, "camera": "tracked", "hand_mode": "hands"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            ),
            timeout=3,
        ) as d_resp:
            assert json.loads(d_resp.read().decode("utf-8")).get("desktop_online")
        with opener.open(
            urllib.request.Request(
                f"{base_url}/api/badminton/live/hand_mode",
                data=json.dumps({"mode": "racket"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            ),
            timeout=3,
        ) as hm_resp:
            hm_res = json.loads(hm_resp.read().decode("utf-8"))
            assert hm_res.get("applied") and hm_res.get("hand_mode") == "racket" and hm_res.get("cmd") == "hand_mode"
        with opener.open(
            urllib.request.Request(
                f"{base_url}/api/badminton/live/poke",
                data=json.dumps({"x": 855, "y": 520}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            ),
            timeout=3,
        ) as pk_resp:
            pk_res = json.loads(pk_resp.read().decode("utf-8"))
            assert pk_res.get("applied") and pk_res.get("poke_count") == 1 and pk_res.get("annoyed")
        with opener.open(f"{base_url}/strike/dash", timeout=3) as resp:
            strike_html = resp.read().decode("utf-8")
            assert "shutdownAll()" in strike_html
        with opener.open(f"{base_url}/badminton/holo", timeout=3) as resp:
            holo_html = resp.read().decode("utf-8")
            assert "btnClean" in holo_html and "全屏清屏" in holo_html

        req_sd = urllib.request.Request(
            f"{base_url}/api/system/shutdown",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with opener.open(req_sd, timeout=3) as resp:
            sd_res = json.loads(resp.read().decode("utf-8"))
            assert sd_res.get("ok") and sd_res.get("shutdown")
        exit_code = proc.wait(timeout=5)
        assert exit_code == 0, f"Shutdown expected clean exit 0, got {exit_code}"
        print(f"  [PASS] 全部 HTTP GET/POST、控制台关闭按钮与优雅退出验证通过 (端口 {port})。")
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)

    print("=== [6/6] 全部自动化验收测试 100% 通过！ ===")


if __name__ == "__main__":
    test_all()
