# -*- coding: utf-8 -*-
"""
端到端全场景交互与边界回归测试 (tests/test_user_flows_and_state_machines.py)
覆盖用户反馈的全部高频痛点：
1. 嵌入式 Python / 缺少 tkinter 探测拦截（install_rally / launch_component.bat / API 字段）
2. 模式切换竞态条件与闭环（coffee <-> strike <-> badminton，心跳不再覆盖网页权威切换）
3. 「模拟工作中 / Codex CLI 运行中」下的挖土打字、立即扔泥巴、立即泡澡、86°C 过烫、搓澡及桌面像素渲染差分验证
4. 回工位（return_office）、部分重来（coffee / strike / badminton）、整体重来（all）
5. 羽毛球 live/replay、live/reset、live/quit 全状态覆盖
6. 局域网多网卡过滤、自定义 IP 同步、QR 二维码生成及真实非回环局域网 IP 端口绑定可达性
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

from local_runtime import get_no_proxy_opener
import badminton_engine
from badminton_live import LiveBadminton
from strike_engine import StrikeEngine
import strike_desktop
from PIL import ImageChops


def post_json(opener, url, payload):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with opener.open(req, timeout=3) as r:
        assert r.status == 200, f"POST {url} -> {r.status}"
        return json.loads(r.read().decode("utf-8"))


def get_json(opener, url):
    with opener.open(url, timeout=3) as r:
        assert r.status == 200, f"GET {url} -> {r.status}"
        return json.loads(r.read().decode("utf-8"))


class UserFlowsAndStateMachinesTest(unittest.TestCase):
    def test_01_embedded_python_and_launcher_require_tkinter(self):
        # 全部 .bat 必须保持纯 ASCII + CRLF，防止 Windows cmd.exe 在 chcp 65001 下跳转错位闪退 (exit 255)
        for bat_path in [ROOT / "app" / "launch_component.bat", *sorted(ROOT.glob("*.bat"))]:
            raw = bat_path.read_bytes()
            raw.decode("ascii")  # 任何非 ASCII 字节都会直接报错
            self.assertIn(b"\r\n", raw, f"{bat_path.name} 必须保持 CRLF 行尾")

        bat = (ROOT / "app" / "launch_component.bat").read_text(encoding="ascii")
        self.assertIn("import sys,tkinter", bat)
        self.assertNotIn("chcp 65001", bat)

        import install_rally
        with mock.patch.dict(sys.modules, {"tkinter": None}):
            self.assertFalse(install_rally.check_tkinter())

        import launcher
        with mock.patch.dict(sys.modules, {"tkinter": None}):
            self.assertFalse(launcher.check_tkinter())

    def test_06_cp936_explorer_bat_launch_spawns_server_and_pet(self):
        opener = get_no_proxy_opener()
        port, https_port = 29891, 29892
        base = f"http://127.0.0.1:{port}"
        with tempfile.TemporaryDirectory(prefix="桌面 (测试) ") as tmp_dir:
            wrap = Path(tmp_dir) / "run_cp936.bat"
            log = Path(tmp_dir) / "cp936.log"
            bat = ROOT / "0-一键启动_Codex全息桌宠三合一工作台.bat"
            # 通过环境变量指定测试端口与禁止弹浏览器，严格模拟 Windows 资源管理器 CP936 环境启动
            wrap.write_text(
                f'@echo off\r\nchcp 936 >nul\r\nset "CODEX_HOLO_PORT={port}"\r\n'
                f'set "CODEX_HOLO_HTTPS_PORT={https_port}"\r\n'
                f'set "CODEX_LAUNCHER_NO_BROWSER=1"\r\n'
                f'set "CODEX_LAUNCHER_NOPAUSE=1"\r\n'
                f'call "{bat}" > "{log}" 2>&1\r\n',
                encoding="gbk",
            )
            env = os.environ.copy()
            env.pop("PYTHONUTF8", None)
            p = subprocess.Popen(
                ["cmd.exe", "/c", str(wrap)],
                cwd=r"C:\Windows\System32",
                env=env,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            try:
                rc = p.wait(timeout=25)
                log_txt = log.read_text(encoding="utf-8", errors="replace")
                self.assertEqual(rc, 0, f"CP936 .bat 启动失败 rc={rc}:\n{log_txt}")
                info = get_json(opener, f"{base}/api/pet/mode")
                self.assertTrue(info.get("desktop_online"), f"透明桌宠未上线: {info}\n{log_txt}")
            finally:
                try:
                    post_json(opener, f"{base}/api/system/shutdown", {})
                except Exception:
                    pass
                time.sleep(0.5)

    def test_02_lan_ip_detection_filters_virtual_nics_and_prefers_wifi_gateway(self):
        fake_ipconfig = (
            "Windows IP 配置\n\n"
            "未知适配器 Clash:\n"
            "   IPv4 地址 . . . . . . . . . . . . : 198.18.0.1\n\n"
            "以太网适配器 vEthernet (WSL):\n"
            "   IPv4 地址 . . . . . . . . . . . . : 172.25.16.1\n\n"
            "以太网适配器 VirtualBox Host-Only Network:\n"
            "   IPv4 地址 . . . . . . . . . . . . : 192.168.56.1\n\n"
            "未知适配器 Tailscale:\n"
            "   IPv4 地址 . . . . . . . . . . . . : 100.88.12.34\n\n"
            "无线局域网适配器 WLAN:\n"
            "   IPv4 地址 . . . . . . . . . . . . : 192.168.31.66\n"
            "   默认网关. . . . . . . . . . . . . : 192.168.31.1\n"
        ).encode("utf-8")
        with mock.patch.object(sys, "platform", "win32"), \
             mock.patch("badminton_engine.subprocess.check_output", return_value=fake_ipconfig), \
             mock.patch("badminton_engine._probe_outbound_ips", return_value=["192.168.31.66"]), \
             mock.patch("badminton_engine.socket.gethostbyname_ex", return_value=("host", [], ["192.168.56.1", "192.168.31.66"])):
            ips = badminton_engine.detect_lan_ips()
        self.assertGreaterEqual(len(ips), 1)
        self.assertEqual(ips[0], "192.168.31.66", f"应首选带默认网关的 WLAN IP，实际返回: {ips}")
        for bad in ("198.18.0.1", "172.25.16.1", "100.88.12.34"):
            self.assertNotIn(bad, ips)

    def test_03_strike_and_bath_work_even_when_codex_working_and_desktop_renders_visibly(self):
        clock_ms = [1_000_000]
        eng = StrikeEngine(run=False)
        eng.clock = lambda: clock_ms[0]
        eng._reset(clock_ms[0])

        # 1) 模拟 Codex CLI 处于工作中（working=True），随后玩家在挖土模式下敲击键盘！
        eng.record_input(0, working=True, enabled=True)
        self.assertEqual(eng.state, "OFFICE_WORK")

        after_type = eng.record_input(6, working=True, enabled=True, manual_burst=False)
        self.assertEqual(after_type["state"], "LEAVING", "working=True 时主动敲击键盘仍应触发离开工位去挖土！")
        self.assertGreater(after_type["fatigue"], 0)

        # 推进跨屏到达时间并步进（不能被 self.working 抹回 OFFICE_WORK！）
        clock_ms[0] = after_type["cross"]["arrive"] + 20
        eng._step(clock_ms[0])
        self.assertEqual(eng.state, "WORKING")

        # 2) 验证「立即扔泥巴」从 WORKING 或 OFFICE_WORK 均可立即触发并可重复触发
        s_throw = eng.trigger_strike_manually()
        self.assertEqual(s_throw["state"], "THROWING")
        self.assertIsNotNone(s_throw["mud"])
        s_throw2 = eng.trigger_strike_manually()
        self.assertEqual(s_throw2["state"], "THROWING")
        self.assertGreater(s_throw2["throw_serial"], s_throw["throw_serial"])

        # 3) 验证「立即泡澡」与 86°C 过烫变红龙虾状态机不被 working 抹掉
        s_bath = eng.push_bathtub()
        self.assertEqual(s_bath["state"], "BATH_ENTER")
        clock_ms[0] += 900
        eng._step(clock_ms[0])
        self.assertEqual(eng.state, "BATH_SOAK")

        s_hot = eng.update_bath_knob(temp=86)
        self.assertEqual(s_hot["state"], "BATH_SOAK")
        self.assertTrue(s_hot["bath"]["hot_jump"])

        # 4) 验证桌面像素渲染器 render_office 在泡澡/过烫/挖土/甩泥下确实画出明显差分画面
        now = clock_ms[0]
        img_idle = strike_desktop.render_office(1.0, {"state": "OFFICE_WORK", "since": now - 1000}, now)
        img_bath = strike_desktop.render_office(1.0, s_bath, s_bath["since"] + 150)
        img_soak = strike_desktop.render_office(1.0, s_hot, now)
        img_throw = strike_desktop.render_office(1.0, s_throw2, now)
        self.assertIsNotNone(ImageChops.difference(img_idle, img_bath).getbbox(), "推浴缸后桌面画面必须有可见反应！")
        self.assertIsNotNone(ImageChops.difference(img_idle, img_soak).getbbox(), "86°C 泡澡过烫时桌面画面必须有可见反应！")
        self.assertIsNotNone(ImageChops.difference(img_idle, img_throw).getbbox(), "立即甩泥时桌面画面必须有可见反应！")

        # 5) 验证「回到工位」即使 working=True 也能完整走回并最终停留在 OFFICE_WORK 且清除泥巴
        s_ret = eng.return_to_office()
        self.assertEqual(s_ret["state"], "RETURNING")
        self.assertIsNone(s_ret["mud"])
        clock_ms[0] = s_ret["cross"]["arrive"] + 30
        eng._step(clock_ms[0])
        self.assertEqual(eng.state, "OFFICE_WORK")

    def test_04_badminton_live_reset_replay_and_quit_anywhere(self):
        t = [10.0]
        live = LiveBadminton(run=False, clock=lambda: t[0])
        live.action("desktop", {"open": True})

        r_start = live.action("start", {})
        self.assertTrue(r_start["applied"])
        self.assertEqual(r_start["phase"], "clear")

        # 刚进入 clear 时，直接点击重来本局 (replay) 或 收拍回工位 (quit) 均应立刻生效
        t[0] += 0.3
        r_replay = live.action("replay", {})
        self.assertTrue(r_replay["applied"])
        self.assertEqual(r_replay["phase"], "clear")
        self.assertEqual(r_replay["codex_score"], 5)

        t[0] += 2.2
        live._step()
        self.assertEqual(live.snapshot()["phase"], "rally")

        r_reset = live.action("reset", {})
        self.assertTrue(r_reset["applied"])
        self.assertEqual(r_reset["phase"], "desk")
        self.assertEqual(r_reset["player_score"], 0)
        self.assertEqual(r_reset["codex_score"], 5)

        live.action("start", {})
        t[0] += 2.2
        live._step()
        r_quit = live.action("quit", {})
        self.assertTrue(r_quit["applied"])
        self.assertEqual(r_quit["phase"], "quit")

    def test_05_full_server_coordinator_resets_mode_race_and_lan_qr(self):
        opener = get_no_proxy_opener()
        port, https_port = 29885, 29886
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
                        info = get_json(opener, f"{base}/api/pet/mode")
                        ready = True
                        break
                    except Exception:
                        time.sleep(0.25)
                assert ready, "coffee_server 未就绪"
                self.assertIn("desktop_tkinter_ok", info)
                self.assertTrue(info["desktop_tkinter_ok"])

                # A) 验证心跳绝不会把权威切换的模式覆盖回旧模式
                sw = post_json(opener, f"{base}/api/pet/mode", {"mode": "strike", "spawn": False})
                self.assertEqual(sw["mode"], "strike")
                hb_old = post_json(opener, f"{base}/api/pet/heartbeat", {"mode": "coffee", "active_mode": "coffee"})
                self.assertEqual(hb_old["mode"], "strike", "桌面旧心跳绝不允许把网页切换的模式覆写回 coffee！")

                sw_bm = post_json(opener, f"{base}/api/pet/mode", {"mode": "badminton", "spawn": False})
                self.assertEqual(sw_bm["mode"], "badminton")
                self.assertFalse(sw_bm["coffee_desktop_online"], "切入羽毛球模式后应清理 coffee_desktop_at")

                sw_coffee = post_json(opener, f"{base}/api/pet/mode", {"mode": "coffee", "spawn": False})
                self.assertEqual(sw_coffee["mode"], "coffee")

                # B) 验证「模拟工作中」+ 全套按钮状态流 + 部分重来 / 整体重来 / 回工位
                post_json(opener, f"{base}/api/work_state", {"override": "working"})
                post_json(opener, f"{base}/api/pet/mode", {"mode": "strike", "spawn": False})

                # 模拟桌面端上报键击（working=True 时应依然累计挖土！）
                d_hits = post_json(opener, f"{base}/api/strike/desktop", {"enabled": True, "working": True, "hits": 8})
                self.assertEqual(d_hits["state"], "LEAVING")
                self.assertGreater(d_hits["fatigue"], 0)

                trig = post_json(opener, f"{base}/api/strike/trigger", {})
                self.assertEqual(trig["state"], "THROWING")
                bath = post_json(opener, f"{base}/api/strike/bath_push", {})
                self.assertEqual(bath["state"], "BATH_ENTER")

                # 同时倒一杯咖啡 & 开启羽毛球局，检验部分重来 vs 整体重来互不误伤
                c_rst = post_json(opener, f"{base}/coffee/reset", {})
                c_pour = post_json(opener, f"{base}/coffee/pour", {"owner": "test", "seq": 1, "round": c_rst["round"], "amount": 0.8, "flow": 0.9})
                self.assertGreaterEqual(c_pour["sent"], 0.8)

                # 只重来 coffee：strike 仍在泡澡态
                post_json(opener, f"{base}/api/pet/reset", {"scope": "coffee"})
                c_after = get_json(opener, f"{base}/coffee/clock")  # sanity
                self.assertIn("now", c_after)
                st_still = get_json(opener, f"{base}/api/strike/status")
                self.assertIn(st_still["state"], ("BATH_ENTER", "BATH_SOAK"))

                # 整体重来 all：strike/coffee/badminton 全部回到工位初始态
                post_json(opener, f"{base}/api/pet/reset", {"scope": "all"})
                st_reset = get_json(opener, f"{base}/api/strike/status")
                self.assertIn(st_reset["state"], ("OFFICE_WORK", "OFFICE_IDLE"))
                self.assertIsNone(st_reset["mud"])
                bm_reset = get_json(opener, f"{base}/api/badminton/live/status")
                self.assertEqual(bm_reset["phase"], "desk")
                self.assertEqual(bm_reset["codex_score"], 5)

                # C) 验证局域网 IP 刷新、自定义 IP 同步、二维码及非回环 LAN IP 实连
                lan = get_json(opener, f"{base}/coffee/lan?refresh=1")
                self.assertGreaterEqual(len(lan["ips"]), 1)
                custom_lan = post_json(opener, f"{base}/coffee/lan", {"ip": lan["ips"][0]})
                self.assertEqual(custom_lan["ip"], lan["ips"][0])
                if lan["ip"] != "127.0.0.1":
                    with opener.open(f"http://{lan['ip']}:{port}/workbench", timeout=3) as resp:
                        self.assertEqual(resp.status, 200)
                qr_url = urllib.parse.quote(f"http://{lan['ip']}:{port}/coffee/bath", safe="")
                with opener.open(f"{base}/api/qrcode?text={qr_url}", timeout=3) as qresp:
                    self.assertEqual(qresp.status, 200)
                    png = qresp.read()
                    self.assertTrue(png.startswith(b"\x89PNG"))
                # 即便电脑从 127.0.0.1 访问，/qr_download.png 也绝不能编进 127.0.0.1，必须自动转为真实局域网 IP
                import network_helper
                with opener.open(f"{base}/qr_download.png", timeout=3) as dlqr:
                    self.assertEqual(dlqr.status, 200)
                    dl_png = dlqr.read()
                    expected_dl_png = network_helper.make_qr_png_bytes(f"http://{lan['ip']}:{port}/download")
                    self.assertEqual(dl_png, expected_dl_png, "/qr_download.png 未排除 127.0.0.1 回环地址")
            finally:
                try:
                    post_json(opener, f"{base}/api/system/shutdown", {})
                except Exception:
                    pass
                try:
                    srv.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    srv.terminate()
                    srv.wait(timeout=3)
                for s in (srv.stdout, srv.stderr):
                    if s:
                        s.close()

    def test_07_no_console_flash_and_clean_exit(self):
        # 1) 源码静态巡检：实际代码逻辑中绝不使用 DETACHED_PROCESS，工作台不再每 12 秒后台轮询网卡
        for rel in (
            "coffee_server.py",
            "pc_voice.py",
            "coffee_pet.py",
            "strike_desktop.py",
            "app/launcher.py",
            "app/badminton_engine.py",
        ):
            src = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
            self.assertNotIn("getattr(subprocess, 'DETACHED_PROCESS'", src, f"{rel} 仍使用 DETACHED_PROCESS")
            self.assertNotIn("subprocess.DETACHED_PROCESS", src, f"{rel} 仍使用 DETACHED_PROCESS")

        wb_js = (ROOT / "coffee" / "workbench.js").read_text(encoding="utf-8", errors="replace")
        self.assertNotIn("setInterval(() => refreshLan", wb_js, "workbench.js 不应每 12 秒后台轮询刷新网卡")

        pet_py = (ROOT / "coffee_pet.py").read_text(encoding="utf-8", errors="replace")
        self.assertIn("def exit_all(self)", pet_py)
        self.assertIn("info.get('shutdown')", pet_py)

        # 2) Windows 隐藏子进程标志与防火墙缓存验证
        if sys.platform == "win32":
            import launcher
            import pc_voice
            import coffee_server
            for kw in (
                badminton_engine._win_hidden_subprocess_kwargs(),
                launcher._win_hidden_kwargs(),
                coffee_server._win_hidden_subprocess_kwargs(),
                pc_voice._win_hidden_kwargs(),
            ):
                self.assertTrue(kw["creationflags"] & subprocess.CREATE_NO_WINDOW)
                self.assertEqual(kw["startupinfo"].wShowWindow, subprocess.SW_HIDE)

            # 验证真实隐藏调用 detect_lan_ips / check_windows_firewall_status 缓存有效
            ips = badminton_engine.detect_lan_ips()
            self.assertGreaterEqual(len(ips), 1)
            fw1 = coffee_server.check_windows_firewall_status(force=True)
            self.assertIn("rule_ok", fw1)
            fw2 = coffee_server.check_windows_firewall_status()
            self.assertEqual(fw1, fw2)

        # 3) 验证 /api/system/shutdown 立即置位 pet_hub.shutdown=True，通知全部桌宠同步退出
        opener = get_no_proxy_opener()
        port, https_port = 29897, 29898
        base = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        srv = subprocess.Popen(
            [sys.executable, "-u", str(ROOT / "coffee_server.py"), "--port", str(port), "--https-port", str(https_port)],
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            ready = False
            for _ in range(40):
                self.assertIsNone(srv.poll(), "coffee_server 提前退出")
                try:
                    get_json(opener, f"{base}/api/pet/mode")
                    ready = True
                    break
                except Exception:
                    time.sleep(0.25)
            self.assertTrue(ready, "coffee_server 未就绪")
            sd = post_json(opener, f"{base}/api/system/shutdown", {})
            self.assertTrue(sd.get("ok") and sd.get("shutdown"))
            mode_snap = get_json(opener, f"{base}/api/pet/mode")
            self.assertTrue(mode_snap.get("shutdown"), f"shutdown 标志未同步到 pet_hub: {mode_snap}")
            srv.wait(timeout=4)
        finally:
            if srv.poll() is None:
                srv.terminate()
                srv.wait(timeout=3)
            for s in (srv.stdout, srv.stderr):
                if s:
                    s.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
