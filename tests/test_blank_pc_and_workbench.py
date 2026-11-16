# -*- coding: utf-8 -*-
"""
空白电脑零权限与三合一工作台全链路自动化验收测试 (tests/test_blank_pc_and_workbench.py)
验证：
1. 隔离模拟没有 ~/.codex/sessions 的完全空白用户目录，验证服务与状态模拟零报错运行。
2. 验证三合一工作台 (/)、3 张 SVG 原理图、咖啡/搓澡/羽毛球全页与 1图/4图切换参数。
3. 验证 /api/work_state 手动模拟工作/空闲、/api/privacy 关闭键盘读取(屏蔽 desktop hits)、
   以及不拖拽/无手机条件下的倒咖啡与搓澡纯按钮全流程。
4. 验证无摄像头纯鼠标模式下 `badminton_overlay.py --no-camera --quit-after 1.5 --snapshot` 真实桌面渲染成功。
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))

from local_runtime import get_no_proxy_opener

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def req_json(opener, url, payload=None):
    if payload is None:
        with opener.open(url, timeout=3) as r:
            assert r.status == 200, f"GET {url} -> {r.status}"
            return json.loads(r.read().decode("utf-8"))
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with opener.open(req, timeout=3) as r:
        assert r.status == 200, f"POST {url} -> {r.status}"
        return json.loads(r.read().decode("utf-8"))


def test_blank_pc_and_workbench():
    opener = get_no_proxy_opener()
    port, https_port = 29875, 29876
    base = f"http://127.0.0.1:{port}"

    with tempfile.TemporaryDirectory() as blank_home:
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["USERPROFILE"] = blank_home
        env["HOME"] = blank_home
        env["CODEX_HOLO_PORT"] = str(port)
        env["CODEX_HOLO_HTTPS_PORT"] = str(https_port)

        srv = subprocess.Popen(
            [sys.executable, str(ROOT / "coffee_server.py"), "--port", str(port), "--https-port", str(https_port)],
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            ready = False
            for _ in range(40):
                assert srv.poll() is None, "coffee_server 提前退出"
                try:
                    info = req_json(opener, f"{base}/api/pet/mode")
                    ready = True
                    break
                except Exception:
                    time.sleep(0.25)
            assert ready, "coffee_server 未就绪"
            assert info["codex_cli_detected"] is False, "模拟空白电脑中不应检测到 .codex 会话"
            print("[1/5] 空白用户目录(无 .codex) 启动与检测通过:", info["codex_cli_detected"], "OK")

            # 检查工作台主页、3张SVG图及三端静态页面
            for route in (
                "/",
                "/workbench",
                "/coffee/workbench.js",
                "/docs/diagrams/peppers_ghost_optics.svg",
                "/docs/diagrams/multi_screen_architecture.svg",
                "/docs/diagrams/zero_permission_fallbacks.svg",
                "/coffee/holo?mode=coffee&faces=1",
                "/coffee/holo?mode=strike&faces=4",
                "/coffee/bath",
                "/coffee/pour",
                "/coffee/desk",
                "/badminton/holo?faces=1",
                "/badminton/director",
            ):
                with opener.open(f"{base}{route}", timeout=3) as resp:
                    assert resp.status == 200, f"GET {route} status={resp.status}"
                    data = resp.read()
                    assert len(data) > 100
            print("[2/5] 三合一工作台、3 张 SVG 光学/架构图及单图/四面页面全部 200 OK")

            # 手动模拟 Codex 工作/空闲切换 & 三模式切换
            st_work = req_json(opener, f"{base}/api/work_state", {"override": "working"})
            assert st_work["effective_work"] == "working"
            st_idle = req_json(opener, f"{base}/api/work_state", {"override": "idle"})
            assert st_idle["effective_work"] == "idle"
            for m in ("coffee", "strike", "badminton", "coffee"):
                m_res = req_json(opener, f"{base}/api/pet/mode", {"mode": m, "spawn": False})
                assert m_res["mode"] == m
            print("[3/5] 空白电脑模拟 Codex 工作/空闲及三合一模式切换接口通过")

            # 隐私控制：关闭键盘读写后 desktop keyboard hits 必须被忽略，纯按钮搓澡流程照样跑通
            priv = req_json(opener, f"{base}/api/privacy", {"keyboard_capture": False, "badminton_control": "mouse", "holo_faces": 1})
            assert priv["keyboard_capture"] is False and priv["holo_faces"] == 1
            req_json(opener, f"{base}/api/strike/reset", {})
            d_res = req_json(opener, f"{base}/api/strike/desktop", {"enabled": True, "working": False, "hits": 20})
            assert d_res["fatigue"] == 0, f"关闭键盘捕捉后不应累计疲劳，实际 fatigue={d_res['fatigue']}"

            # 纯按钮体验完整搓澡链路（无需推浴缸手势与键盘敲击）
            req_json(opener, f"{base}/api/strike/input", {"hits": 12})
            trig = req_json(opener, f"{base}/api/strike/trigger", {})
            assert trig["state"] in ("THROWING", "MUDDY", "STRIKE", "WORKING")
            bath = req_json(opener, f"{base}/api/strike/bath_push", {})
            assert bath["state"] in ("BATH_ENTER", "BATH_SOAK", "SCRUBBING", "THROWING", "STRIKE")
            req_json(opener, f"{base}/api/strike/bath_knob", {"temp": 86})
            req_json(opener, f"{base}/api/strike/scrub_start", {"immediate": True})
            req_json(opener, f"{base}/api/strike/scrub_move", {"zone": "head", "y": 0.2})
            req_json(opener, f"{base}/api/strike/scrub_move", {"zone": "back", "delta": 100.0})
            req_json(opener, f"{base}/api/strike/return_office", {})

            # 无手机免滑动倒咖啡流程
            c_rst = req_json(opener, f"{base}/coffee/reset", {})
            c_fin = req_json(opener, f"{base}/coffee/pour", {"owner": "carafe-test", "seq": 1, "round": c_rst["round"], "amount": 0.8, "flow": 0.9})
            assert c_fin["sent"] >= 0.8
            print("[4/5] 零权限纯按钮（关读键盘 + 免拖拽搓澡 + 免手机倒咖啡）全流程通过")

            # 验证无摄像头纯鼠标桌面羽毛球启动与帧渲染（无需 webcam/cv2）
            snap_png = Path(blank_home) / "mouse_overlay.png"
            ov = subprocess.run(
                [sys.executable, str(ROOT / "app" / "badminton_overlay.py"),
                 "--no-camera", "--no-voice", "--quit-after", "1.3", "--snapshot", str(snap_png)],
                cwd=str(ROOT),
                env=env,
                timeout=15,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            assert ov.returncode == 0, f"overlay failed: {ov.stderr}"
            assert snap_png.is_file() and snap_png.stat().st_size > 1000, "纯鼠标羽毛球透明层未写出截图"
            print("[5/5] 无摄像头纯鼠标透明桌面渲染 (badminton_overlay --no-camera) 验收通过:", ov.stdout.strip())
        finally:
            try:
                req_json(opener, f"{base}/api/system/shutdown", {})
            except Exception:
                pass
            try:
                srv.wait(timeout=3)
            except subprocess.TimeoutExpired:
                srv.terminate()
                srv.wait(timeout=3)
    print("ALL BLANK-PC & WORKBENCH CHECKS PASSED!")


if __name__ == "__main__":
    test_blank_pc_and_workbench()
