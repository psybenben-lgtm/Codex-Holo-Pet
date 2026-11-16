# -*- coding: utf-8 -*-
"""
《我就赢了 Codex 一球，它竟然开挂了》核心权威状态机、抛物线羽毛球物理、摄像头挥拍宽容判定与快照回滚引擎
模块涵盖：StoryDirector, Timeline, Shuttlecock, GestureInput, Network, Calibration, AudioEventQueue
"""
from collections import deque
import copy
import json
import math
from pathlib import Path
import queue
import socket
import subprocess
import sys
import threading
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
CONFIG_PATH = ROOT / 'config' / 'default_presets.json'

try:
    from local_runtime import get_http_port, get_https_port
except ImportError:
    def get_http_port():
        return 29765

    def get_https_port():
        return 29766

# S0 ~ S10 完整十幕戏剧节点定义（支持任意节点秒级确定性回滚与单幕重拍）
STORY_SCENES = [
    {"id": "S0", "code": "S0_DAILY_WORK",    "title": "S0｜日常待机",       "desc": "Codex 坐在小办公桌前敲代码工作，偶尔停下思考喝咖啡"},
    {"id": "S1", "code": "S1_CLEAR_DESK",    "title": "S1｜收拾场地",       "desc": "收到打球邀请惊喜起身 → 合上电脑 → 推开椅子 → 吃力推走沉重办公桌 → 擦汗"},
    {"id": "S2", "code": "S2_CHANGE_DRESS",  "title": "S2｜换装和热身",     "desc": "掏出小运动包转身换上运动装 → 拿羽毛球拍试挥两下 → 第二下用力过猛差点失衡 → 站稳待命"},
    {"id": "S3", "code": "S3_MACHINE_START", "title": "S3｜全息发球机启动", "desc": "全息端微型发球机启动抬头蓄力 → 弹出第一颗羽毛球跨屏飞入电脑桌面"},
    {"id": "S4", "code": "S4_RALLY",         "title": "S4｜第一次对打",     "desc": "Codex 移动接球打向真人 → 宽容接球窗口开启 → 真人挥拍回击 → 完成约2回合爽快往返"},
    {"id": "S5", "code": "S5_LOSE_POINT",    "title": "S5｜Codex 输球",     "desc": "真人挥出高速扣杀 → Codex 慌乱奔跑扑空摔倒、球拍甩飞 → 音乐骤停 → 坐地低头叹气"},
    {"id": "S6", "code": "S6_PRETEND_PITY",  "title": "S6｜假装可怜",       "desc": "Codex 委屈捡起球拍缩着肩膀 → 滑稽委屈短音 → 偷偷抬起一只黑豆眼观察用户有没有心软"},
    {"id": "S7", "code": "S7_SECRET_CHEAT",  "title": "S7｜偷偷作弊",       "desc": "委屈秒变坏笑 → 掏出红灯小遥控器按下按钮 → 全息发球机亮红灯加速连发 → Codex 叉腰大笑"},
    {"id": "S8", "code": "S8_MACHINE_JAM",   "title": "S8｜机器失控",       "desc": "全息发球机超速震动卡顿 → 内部羽毛球积压冒烟异响 → Codex 笑声戛然而止，慢慢转头盯向机器"},
    {"id": "S9", "code": "S9_BACKFIRE_SPLAT","title": "S9｜反噬拍扁",       "desc": "全息发球机暴射超大号羽毛球 → 正面击中 Codex → 贴在电脑屏幕上扁平形变并缓慢滑落 → 伸手按停"},
    {"id": "S10","code": "S10_ENDING",       "title": "S10｜结尾恢复",      "desc": "Codex 缓慢爬起检查球拍 → 回头看你一眼 → 尴尬地把球拍藏到身后坏笑，等待重拍或恢复日常"}
]

SCENE_INDEX = {item["id"]: idx for idx, item in enumerate(STORY_SCENES)}


def detect_lan_ips():
    """
    智能识别本机真实局域网 IPv4 地址列表：
    排除 Clash/Mihomo/VPN 虚拟网卡 (198.18.*)、链路本地 (169.254.*)、WSL/Hyper-V/Docker 等虚拟网段，
    将手机真正可连的物理 Wi-Fi / 热点 IP (192.168.x.x / 172.20.10.x / 10.x.x.x) 排在最前！
    """
    candidates = []
    # 1. Windows ipconfig 解析真实无线局域网适配器 WLAN
    if sys.platform == 'win32':
        try:
            out = subprocess.check_output(['ipconfig'], stderr=subprocess.STDOUT, timeout=1.5)
            text = out.decode('gbk', errors='ignore')
            current_adapter = ''
            for line in text.splitlines():
                line_s = line.strip()
                if line and not line.startswith(' ') and ':' in line:
                    current_adapter = line_s.lower()
                elif 'IPv4' in line_s and ':' in line_s:
                    ip = line_s.split(':')[-1].strip().split('(')[0].strip()
                    if _is_valid_lan_ip(ip, current_adapter):
                        # WLAN / Wi-Fi 适配器最高优先级
                        prio = 0 if ('wlan' in current_adapter or 'wi-fi' in current_adapter or '无线' in current_adapter) else 1
                        candidates.append((prio, ip))
        except Exception:
            pass

    # 2. UDP 探测路由出口 IP
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.4)
            s.connect(('223.5.5.5', 80))
            ip = s.getsockname()[0]
            if _is_valid_lan_ip(ip, ''):
                candidates.append((1, ip))
    except Exception:
        pass

    # 3. 主机名关联的所有 IPv4
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if _is_valid_lan_ip(ip, ''):
                prio = 1 if ip.startswith('192.168.') else 2
                candidates.append((prio, ip))
    except Exception:
        pass

    candidates.sort(key=lambda item: (item[0], 0 if item[1].startswith('192.168.') else 1))
    ordered = []
    for _, ip in candidates:
        if ip not in ordered:
            ordered.append(ip)
    if not ordered:
        ordered.append('127.0.0.1')
    return ordered


def _is_valid_lan_ip(ip, adapter_name=''):
    if not ip or ip.startswith('127.') or ip.startswith('169.254.') or ip.startswith('198.18.') or ip.startswith('198.19.'):
        return False
    bad_keywords = ('wsl', 'hyper-v', 'vethernet', 'vmware', 'virtualbox', 'clash', 'meta', 'tailscale', 'zerotier', 'tun', 'tap', 'docker')
    if any(k in adapter_name for k in bad_keywords):
        return False
    parts = ip.split('.')
    if len(parts) != 4:
        return False
    return True


class BadmintonDirectorEngine:
    """
    电脑端唯一权威状态管理端 (Section 10 & 11)：
    统一管理：
    - S0 ~ S10 剧情节点状态机与快照回滚 (Timeline & StoryDirector)
    - 羽毛球 2D 抛物线物理轨迹与跨屏坐标映射 (Shuttlecock)
    - 摄像头挥拍宽容时间窗口判定与防误触冷却 (GestureInput)
    - 全息发球机状态与多设备在线心跳确认 (Hologram & Network)
    - 音效与情绪音乐关键帧事件流 (Audio)
    """
    def __init__(self, run=True):
        self.lock = threading.RLock()
        self.listeners = set()
        self.session_id = uuid4().hex[:12]
        self.wall_origin = time.time_ns() // 1_000_000
        self.mono_origin = time.monotonic_ns() // 1_000_000
        self.seq = 0
        self.event_seq = 0

        # 加载预设配置
        self._load_config()

        # 运行模式: 'single' (A.单机测试模式) | 'multi' (B.多设备实机模式) | 'director' (C.导演拍摄模式)
        self.system_mode = 'director'
        self.compact_version = False  # False=完整开场版(约26s), True=短视频紧凑版(约20s)
        self.paused = False
        self.pause_started_ms = 0

        # 多设备在线心跳与确认表
        self.devices = {
            "desktop": {"online": False, "last_seen": 0, "rtt_ms": 0, "mode": "click_through"},
            "holo":    {"online": False, "last_seen": 0, "rtt_ms": 0, "last_ack_event": 0},
            "ctrl":    {"online": False, "last_seen": 0, "rtt_ms": 0},
            "camera":  {"online": False, "last_seen": 0, "hand_detected": False, "speed": 0.0, "hand_x": 0.5, "hand_y": 0.5, "source": "none"}
        }
        self.lan_ips = detect_lan_ips()
        self.preferred_ip = self.lan_ips[0]
        self.http_port = get_http_port()
        self.https_port = get_https_port()
        self.desktop_close_seq = 0
        self.system_shutdown = False

        # 音效事件队列 (保留最近 16 条带唯一 event_id 的音效指令，各端按 event_id 去重播放)
        self.audio_events = deque(maxlen=16)
        # 统一跨端事件流记录 (Section 10.1)
        self.unified_events = deque(maxlen=24)

        # 初始化到 S0 日常待机
        now = self.clock()
        self._init_scene_state("S0", now)

        self._stop = threading.Event()
        if run:
            threading.Thread(target=self._loop, daemon=True).start()

    def clock(self):
        return self.wall_origin + (time.monotonic_ns() // 1_000_000 - self.mono_origin)

    def _load_config(self):
        try:
            raw = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
        except Exception:
            raw = {"active_preset": "daily", "presets": {}, "court_layout": {}}
        self.active_preset = raw.get("active_preset", "daily")
        self.presets = raw.get("presets", {})
        self.params = copy.deepcopy(self.presets.get(self.active_preset) or {
            "name": "日常体验", "char_scale": 1.6, "char_speed": 1.0,
            "shuttle_speed": 1.0, "arc_height": 1.0, "smash_speed": 1.45,
            "sensitivity": "easy", "sensitivity_threshold": 18.0,
            "hit_window_ms": 680, "cooldown_ms": 240, "serve_interval_ms": 1150,
            "reaction_delay_ms": 90, "master_volume": 0.9, "sfx_volume": 0.95,
            "bgm_volume": 0.7, "voice_volume": 0.9, "audio_offset_ms": 0,
            "holo_offset_x": 0.0, "holo_offset_y": 0.0
        })
        self.court = copy.deepcopy(raw.get("court_layout") or {
            "ground_y_ratio": 0.82, "codex_home_x_ratio": 0.68,
            "human_zone_x_ratio": 0.24, "human_zone_y_ratio": 0.56,
            "holo_entry_x_ratio": 0.92, "holo_entry_y_ratio": 0.64,
            "facing_direction": -1, "show_guide_lines": False,
            "desktop_edit_mode": False, "icon_safe_avoidance": True
        })

    def _emit_audio(self, sound_name, now, volume=1.0, pan=0.0, bgm=None):
        self.event_seq += 1
        evt = {
            "id": self.event_seq,
            "sound": sound_name,
            "at": now + int(self.params.get("audio_offset_ms", 0)),
            "volume": round(volume, 2),
            "pan": round(pan, 2),
            "bgm": bgm,
        }
        self.audio_events.append(evt)
        return evt

    def _emit_unified_event(self, evt_type, target_device, now, planned_ms=None, payload=None):
        self.event_seq += 1
        evt = {
            "scene_id": self.scene_id,
            "event_id": self.event_seq,
            "event_type": evt_type,
            "created_at": now,
            "planned_at": planned_ms or now,
            "params": payload or {},
            "version": self.seq + 1,
            "target": target_device,
            "status": "scheduled",
        }
        self.unified_events.append(evt)
        return evt

    def _init_scene_state(self, scene_id, now):
        """
        确定性场景初始化与快照恢复 (Section 11.2)：
        点击任意 S0~S10 节点时，彻底清理旧球体、旧粒子、旧延迟任务，精准恢复该幕对应的桌椅、服装、球拍、发球机与角色位置！
        """
        if scene_id not in SCENE_INDEX:
            scene_id = "S0"
        self.scene_id = scene_id
        self.scene_since = now
        self.last_step = now
        self.shuttles = []
        self.particles = []
        self.hit_window = {"open": False, "start_ms": 0, "end_ms": 0, "shuttle_id": None}
        self.last_swing_ms = 0
        self.last_valid_hit_ms = 0
        self.rally_count = 0
        self.target_rallies = 2  # S4 完成 2 回合往返后进入 S5 决胜扣杀

        home_x = float(self.court.get("codex_home_x_ratio", 0.68))
        ground_y = float(self.court.get("ground_y_ratio", 0.82))

        # 默认角色、桌椅与全息发球机状态
        self.character = {
            "x": home_x,
            "y": ground_y,
            "vx": 0.0,
            "outfit": "office" if scene_id in ("S0", "S1") else "sport",
            "has_racket": scene_id not in ("S0", "S1"),
            "racket_dropped": False,
            "racket_x": home_x - 0.08,
            "pose": "work_type",
            "emotion": "calm",
            "facing": -1,
            "sub_phase": 0.0,
            "remote_visible": False,
            "screen_splat_progress": 0.0,
        }
        self.props = {
            "desk_visible": scene_id in ("S0", "S1"),
            "desk_x": home_x - 0.02 if scene_id == "S0" else (home_x if scene_id == "S1" else 0.94),
            "desk_stored": scene_id not in ("S0", "S1"),
            "laptop_open": scene_id == "S0",
            "sport_bag_visible": scene_id == "S2",
            "sport_bag_x": home_x + 0.07,
        }
        self.hologram = {
            "mode": "standby",      # standby | warmup | serving | cheat_red | jammed | backfire | off
            "barrel_angle": 12.0,   # 发球口仰角
            "charge": 0.0,          # 蓄力进度 0..1
            "shuttles_left": 5,     # 透明储球管内可见羽毛球数量
            "red_led": False,       # 作弊模式红灯
            "vibration": 0.0,       # 震动强度
            "jam_pile": 0,          # 卡顿时积压的羽毛球数
            "last_launch_ms": 0,
        }

        # 根据目标节点精准布置初始状态与开场音效
        if scene_id == "S0":
            self.character["pose"] = "work_type"
            self.character["emotion"] = "calm"
            self._emit_audio("silence", now, bgm="stop")
        elif scene_id == "S1":
            self.character["pose"] = "invite_surprise"
            self.character["emotion"] = "surprised"
            self.props["desk_x"] = home_x - 0.02
            self._emit_audio("invite_chime", now, bgm="prep")
        elif scene_id == "S2":
            self.character["outfit"] = "office"
            self.character["has_racket"] = False
            self.character["pose"] = "take_bag"
            self.character["emotion"] = "happy"
            self._emit_audio("change_clothes", now, bgm="prep")
        elif scene_id == "S3":
            self.character["pose"] = "ready_wait"
            self.character["emotion"] = "focused"
            self.hologram["mode"] = "warmup"
            self.hologram["barrel_angle"] = 24.0
            self._emit_audio("machine_start", now, bgm="rally")
            self._emit_unified_event("holo_warmup", "holo", now, now + 350)
        elif scene_id == "S4":
            self.character["pose"] = "ready_wait"
            self.character["emotion"] = "focused"
            self.hologram["mode"] = "serving"
            self._spawn_serve_from_hologram(now + 260, fast=False)
        elif scene_id == "S5":
            self.character["pose"] = "ready_wait"
            self.character["emotion"] = "focused"
            self.hologram["mode"] = "serving"
            # 直接生成一颗飞向真人、等待真人挥拍触发决胜扣杀的球（或立即触发扣杀落点）
            self._spawn_codex_return_to_human(now, for_winning_smash=True)
        elif scene_id == "S6":
            self.character["pose"] = "sit_pity"
            self.character["emotion"] = "pity_peek"
            self.character["racket_dropped"] = False
            self._emit_audio("bgm_pity", now, bgm="pity")
        elif scene_id == "S7":
            self.character["pose"] = "evil_remote"
            self.character["emotion"] = "evil_grin"
            self.character["remote_visible"] = True
            self.hologram["mode"] = "cheat_red"
            self.hologram["red_led"] = True
            self.hologram["vibration"] = 0.45
            self._emit_audio("cheat_button", now, bgm="cheat")
            self._emit_unified_event("holo_cheat_rapid", "holo", now, now + 450)
        elif scene_id == "S8":
            self.character["pose"] = "laugh_to_shock"
            self.character["emotion"] = "shocked"
            self.character["remote_visible"] = True
            self.hologram["mode"] = "jammed"
            self.hologram["red_led"] = True
            self.hologram["vibration"] = 1.0
            self.hologram["jam_pile"] = 4
            self._emit_audio("machine_jam", now, bgm="stop")
            self._emit_unified_event("holo_jammed", "holo", now)
        elif scene_id == "S9":
            self.character["pose"] = "panic_freeze"
            self.character["emotion"] = "terrified"
            self.character["remote_visible"] = True
            self.hologram["mode"] = "backfire"
            self.hologram["red_led"] = True
            self._spawn_giant_backfire_shuttle(now + 280)
        elif scene_id == "S10":
            self.character["pose"] = "awkward_hide_racket"
            self.character["emotion"] = "awkward_smile"
            self.hologram["mode"] = "off"
            self._emit_audio("ending_awkward", now, bgm="stop")

    # =========================================================================
    # 羽毛球 2D 抛物线物理与跨屏空间衔接系统 (Section 6)
    # =========================================================================
    def _spawn_serve_from_hologram(self, launch_ms, fast=False):
        """
        第一步 & 第二步：全息发球机蓄力发射 → 羽毛球沿抛物线进入电脑透明桌面 → 飞向 Codex 接球点
        """
        speed_mul = float(self.params.get("shuttle_speed", 1.0)) * (1.35 if fast else 1.0)
        flight_ms = round(680 / max(0.4, speed_mul))
        entry_ms = launch_ms + 140  # 全息端出球口飞出后 140ms 进入电脑屏幕右边界
        arrive_ms = entry_ms + flight_ms

        start_x = float(self.court.get("holo_entry_x_ratio", 0.92))
        start_y = float(self.court.get("holo_entry_y_ratio", 0.64))
        target_x = float(self.court.get("codex_home_x_ratio", 0.68)) + (0.04 if fast else -0.02)
        target_y = float(self.court.get("ground_y_ratio", 0.82)) - 0.14

        shuttle = {
            "id": uuid4().hex[:8],
            "kind": "normal" if not fast else "cheat_fast",
            "phase": "holo_to_codex",  # holo_to_codex | codex_to_human | human_to_codex | landed | deflected
            "launch_ms": launch_ms,
            "start_ms": entry_ms,
            "end_ms": arrive_ms,
            "x0": start_x, "y0": start_y,
            "x1": target_x, "y1": target_y,
            "arc_h": 0.18 * float(self.params.get("arc_height", 1.0)),
            "x": start_x, "y": start_y,
            "vx": -0.5, "vy": -0.3,
            "angle": -2.4,
            "scale": 1.0,
            "speed_lines": fast,
            "for_winning_smash": False,
        }
        self.shuttles.append(shuttle)
        self.hologram["last_launch_ms"] = launch_ms
        self.hologram["shuttles_left"] = max(1, (self.hologram["shuttles_left"] - 1) % 6 or 5)
        self._emit_unified_event("serve_launch", "all", self.clock(), launch_ms, {
            "shuttle_id": shuttle["id"], "entry_ms": entry_ms, "arrive_ms": arrive_ms
        })
        return shuttle

    def _spawn_codex_return_to_human(self, now, for_winning_smash=False):
        """
        第三步 & 第四步：Codex 挥拍击球 → 羽毛球沿高远抛物线飞向真人接球区 → 开启宽容接球窗口 (300~800ms)
        """
        speed_mul = float(self.params.get("shuttle_speed", 1.0))
        flight_ms = round(760 / max(0.4, speed_mul))
        start_x = self.character["x"] - 0.04
        start_y = float(self.court.get("ground_y_ratio", 0.82)) - 0.15
        human_x = float(self.court.get("human_zone_x_ratio", 0.24))
        human_y = float(self.court.get("human_zone_y_ratio", 0.56))

        arrive_ms = now + flight_ms
        win_len = int(self.params.get("hit_window_ms", 680))
        win_start = arrive_ms - int(win_len * 0.55)
        win_end = arrive_ms + int(win_len * 0.65)

        shuttle_id = uuid4().hex[:8]
        shuttle = {
            "id": shuttle_id,
            "kind": "normal",
            "phase": "codex_to_human",
            "launch_ms": now,
            "start_ms": now,
            "end_ms": arrive_ms,
            "x0": start_x, "y0": start_y,
            "x1": human_x, "y1": human_y,
            "arc_h": 0.24 * float(self.params.get("arc_height", 1.0)),
            "x": start_x, "y": start_y,
            "vx": -0.6, "vy": -0.4,
            "angle": -2.6,
            "scale": 1.0,
            "speed_lines": False,
            "for_winning_smash": for_winning_smash,
        }
        self.shuttles = [shuttle]
        self.hit_window = {
            "open": False,
            "start_ms": win_start,
            "end_ms": win_end,
            "shuttle_id": shuttle_id,
            "for_winning_smash": for_winning_smash,
        }
        self._emit_audio("hit_normal", now, pan=0.35)
        return shuttle

    def _trigger_human_return_shot(self, now, shuttle, is_smash=False):
        """
        第五步 & 第六步：真人挥手击球成功 → 自动修正击球点 → 播放清脆/强力击球音效 → 球反向飞向 Codex
        """
        smash = is_smash or shuttle.get("for_winning_smash", False) or (self.rally_count >= self.target_rallies)
        speed_mul = float(self.params.get("smash_speed", 1.45)) if smash else float(self.params.get("shuttle_speed", 1.0)) * 1.15
        flight_ms = round((460 if smash else 640) / max(0.4, speed_mul))

        start_x = float(self.court.get("human_zone_x_ratio", 0.24))
        start_y = float(self.court.get("human_zone_y_ratio", 0.56))
        home_x = float(self.court.get("codex_home_x_ratio", 0.68))
        ground_y = float(self.court.get("ground_y_ratio", 0.82))

        # 决胜扣杀打向大角度边线，让 Codex 慌乱飞扑摔倒！
        target_x = (home_x + 0.16) if smash else (home_x + (-0.06 if self.rally_count % 2 == 0 else 0.05))
        target_y = (ground_y - 0.02) if smash else (ground_y - 0.14)

        shuttle.update({
            "phase": "human_to_codex",
            "kind": "smash" if smash else "normal",
            "launch_ms": now,
            "start_ms": now,
            "end_ms": now + flight_ms,
            "x0": start_x, "y0": start_y,
            "x1": target_x, "y1": target_y,
            "arc_h": (0.09 if smash else 0.19) * float(self.params.get("arc_height", 1.0)),
            "speed_lines": smash,
            "for_winning_smash": smash,
        })
        self.hit_window["open"] = False
        self.hit_window["shuttle_id"] = None
        self.last_valid_hit_ms = now

        # 击球粒子火花
        self.particles.append({
            "kind": "hit_spark",
            "x": start_x, "y": start_y,
            "at": now, "dur": 320,
            "smash": smash,
        })

        if smash:
            self._emit_audio("hit_smash", now, volume=1.0, pan=-0.4)
            self._emit_audio("shuttle_fast", now + 45, volume=0.9, pan=0.0)
            if self.scene_id == "S4":
                self.scene_id = "S5"
                self.scene_since = now
            self.character["pose"] = "panic_run"
            self.character["emotion"] = "panic"
        else:
            self._emit_audio("hit_normal", now, volume=0.9, pan=-0.35)
            self._emit_audio("shuttle_fly", now + 40, volume=0.6, pan=0.0)
            self.character["pose"] = "move_anticipate"
            self.character["emotion"] = "focused"

    def _spawn_giant_backfire_shuttle(self, launch_ms):
        """S9 反噬：全息发球机暴射一颗夸张的超大号羽毛球直击 Codex 面门"""
        entry_ms = launch_ms + 90
        impact_ms = entry_ms + 420
        start_x = float(self.court.get("holo_entry_x_ratio", 0.92))
        start_y = float(self.court.get("holo_entry_y_ratio", 0.64))
        target_x = self.character["x"]
        target_y = float(self.court.get("ground_y_ratio", 0.82)) - 0.12

        shuttle = {
            "id": "giant-" + uuid4().hex[:6],
            "kind": "giant_boss",
            "phase": "giant_to_codex",
            "launch_ms": launch_ms,
            "start_ms": entry_ms,
            "end_ms": impact_ms,
            "x0": start_x, "y0": start_y,
            "x1": target_x, "y1": target_y,
            "arc_h": 0.06,
            "x": start_x, "y": start_y,
            "vx": -1.2, "vy": 0.0,
            "angle": math.pi,
            "scale": 3.4,
            "speed_lines": True,
        }
        self.shuttles = [shuttle]
        self._emit_audio("shuttle_fast", launch_ms, volume=1.0, pan=0.6)
        self._emit_unified_event("giant_backfire", "all", self.clock(), launch_ms)

    def _step_shuttles(self, now):
        ground_y = float(self.court.get("ground_y_ratio", 0.82))
        active = []
        for s in self.shuttles:
            ph = s["phase"]
            if ph == "landed":
                if now - s["end_ms"] < 1400:
                    active.append(s)
                continue
            if ph == "deflected":
                p = max(0.0, min(1.0, (now - s["start_ms"]) / 380.0))
                s["x"] = s["x0"] + (s["x1"] - s["x0"]) * p
                s["y"] = s["y0"] + (s["y1"] - s["y0"]) * p - 0.12 * 4 * p * (1 - p)
                s["angle"] += 0.35
                if p < 1.0:
                    active.append(s)
                continue

            if now < s["start_ms"]:
                active.append(s)
                continue

            dur = max(1, s["end_ms"] - s["start_ms"])
            raw_u = max(0.0, min(1.0, (now - s["start_ms"]) / dur))
            # 羽毛球真实空气阻力缓动：出球快 -> 最高点减速 -> 明显下落趋势 (Section 6.2)
            if ph in ("holo_to_codex", "codex_to_human"):
                u = 1.0 - (1.0 - raw_u) ** 1.35
            else:
                u = raw_u ** 0.88

            prev_x, prev_y = s["x"], s["y"]
            s["x"] = s["x0"] + (s["x1"] - s["x0"]) * u
            # 非对称抛物线（最高点偏后，下落更陡峭自然）
            arc = 4.0 * raw_u * (1.0 - raw_u) * (1.0 + 0.25 * raw_u) * s["arc_h"]
            s["y"] = s["y0"] + (s["y1"] - s["y0"]) * raw_u - arc
            dx = s["x"] - prev_x
            dy = s["y"] - prev_y
            if abs(dx) + abs(dy) > 0.0005:
                s["angle"] = math.atan2(dy, dx)
            s["scale"] = 3.4 if s["kind"] == "giant_boss" else (1.0 + 0.38 * math.sin(raw_u * math.pi))

            # 更新宽容接球窗口开启状态
            if ph == "codex_to_human" and self.hit_window.get("shuttle_id") == s["id"]:
                self.hit_window["open"] = (self.hit_window["start_ms"] <= now <= self.hit_window["end_ms"])

            # 到达终点判定
            if raw_u >= 1.0:
                if ph == "holo_to_codex":
                    if self.scene_id in ("S3", "S4"):
                        if self.scene_id == "S3":
                            self.scene_id = "S4"
                            self.scene_since = now
                        self.character["pose"] = "hit_swing"
                        self.character["sub_phase"] = 0.0
                        self._spawn_codex_return_to_human(now, for_winning_smash=(self.rally_count >= self.target_rallies))
                        return
                    elif self.scene_id == "S7":
                        # 作弊连发模式下球飞向真人端
                        s["phase"] = "codex_to_human"
                        s["start_ms"] = now
                        s["end_ms"] = now + 450
                        s["x0"], s["y0"] = s["x"], s["y"]
                        s["x1"] = float(self.court.get("human_zone_x_ratio", 0.24)) + ((len(active) % 3) - 1) * 0.06
                        s["y1"] = float(self.court.get("human_zone_y_ratio", 0.56)) + ((len(active) % 2) - 0.5) * 0.08
                        active.append(s)
                        continue
                elif ph == "codex_to_human":
                    # 若过了宽容接球窗口末尾真人仍未挥拍：球轻轻落地，Codex 疑惑等待并可重新发球
                    if now > self.hit_window.get("end_ms", now):
                        self.hit_window["open"] = False
                        s["phase"] = "landed"
                        s["y"] = ground_y
                        s["end_ms"] = now
                        self._emit_audio("shuttle_land", now, volume=0.7, pan=-0.3)
                        if self.scene_id in ("S4", "S5"):
                            self.character["pose"] = "wait_puzzled"
                            self.character["emotion"] = "puzzled"
                        active.append(s)
                        continue
                    else:
                        active.append(s)
                        continue
                elif ph == "human_to_codex":
                    if s.get("for_winning_smash") or self.scene_id == "S5":
                        # S5 Codex 扑空摔倒输球！
                        s["phase"] = "landed"
                        s["y"] = ground_y
                        s["end_ms"] = now
                        self.character["pose"] = "dive_fall"
                        self.character["emotion"] = "sad_sigh"
                        self.character["racket_dropped"] = True
                        self.character["racket_x"] = min(0.92, self.character["x"] + 0.11)
                        self._emit_audio("codex_fall", now, volume=0.95, bgm="stop")
                        self._emit_audio("shuttle_land", now + 110, volume=0.8)
                        active.append(s)
                        continue
                    else:
                        # Codex 正常移动接球成功并回球
                        self.rally_count += 1
                        self.character["pose"] = "hit_swing"
                        self._spawn_codex_return_to_human(now, for_winning_smash=(self.rally_count >= self.target_rallies))
                        return
                elif ph == "giant_to_codex":
                    # S9 超大羽毛球正面击中 Codex，拍扁贴在电脑屏幕上！
                    self.character["pose"] = "screen_pancake"
                    self.character["emotion"] = "pancake"
                    self.character["screen_splat_progress"] = 0.01
                    self.particles.append({
                        "kind": "giant_boom",
                        "x": self.character["x"], "y": s["y"],
                        "at": now, "dur": 650, "smash": True
                    })
                    self._emit_audio("giant_impact", now, volume=1.0, bgm="stop")
                    continue
            else:
                active.append(s)

        self.shuttles = active
        self.particles = [pt for pt in self.particles if now - pt["at"] < pt.get("dur", 400)]

    # =========================================================================
    # S0 ~ S10 剧情导演状态机推进 (Section 3, 7, 8)
    # =========================================================================
    def _step_story(self, now, dt_ms):
        if self.paused:
            return
        elapsed = (now - self.scene_since) / 1000.0
        speed_factor = 1.35 if self.compact_version else 1.0
        sc = self.scene_id
        home_x = float(self.court.get("codex_home_x_ratio", 0.68))

        if sc == "S0":
            self.character["pose"] = "work_type"
            self.character["sub_phase"] = elapsed

        elif sc == "S1":
            # S1 收拾场地：
            # 0..0.6s: 停下打字，抬头看摄像头，惊喜起身
            # 0.6..1.2s: 合上电脑，推开椅子
            # 1.2..1.7s: 身体前倾双手抵住桌子，双脚用力但桌子沉重先不动！
            # 1.7..3.4s: 吃力把桌子缓慢推向屏幕右侧边缘收纳
            # 3.4..4.2s: 对桌面图标区域做嫌弃/推开手势，拍拍手擦掉额头汗水 -> 进入 S2
            t = elapsed * speed_factor
            if t < 0.6:
                self.character["pose"] = "invite_surprise"
            elif t < 1.2:
                if self.props["laptop_open"]:
                    self.props["laptop_open"] = False
                    self._emit_audio("close_laptop", now)
                self.character["pose"] = "close_laptop"
            elif t < 1.75:
                if self.character["pose"] != "push_strain_still":
                    self.character["pose"] = "push_strain_still"
                    self._emit_audio("push_desk", now)
            elif t < 3.4:
                self.character["pose"] = "push_desk_move"
                push_p = (t - 1.75) / (3.4 - 1.75)
                self.props["desk_x"] = home_x - 0.02 + push_p * 0.28
                self.character["x"] = self.props["desk_x"] - 0.06
            elif t < 4.3:
                self.props["desk_stored"] = True
                self.character["pose"] = "wipe_sweat_clap"
                self.character["x"] = home_x + (0.94 - home_x) * max(0.0, 1.0 - (t - 3.4) / 0.8)
            else:
                self._init_scene_state("S2", now)

        elif sc == "S2":
            # S2 换装和热身：
            # 0..0.8s: 从旁边拿出小运动包
            # 0.8..1.5s: 短促跳跃旋转完成运动装换装，拿起羽毛球拍
            # 1.5..2.5s: 左右挥拍试拍两下，第二下用力过猛单脚晃悠差点失去平衡！
            # 2.5..3.3s: 不好意思地挠头站稳，摆出准备接球姿势 -> 进入 S3
            t = elapsed * speed_factor
            if t < 0.8:
                self.character["pose"] = "take_bag"
            elif t < 1.5:
                if self.character["outfit"] != "sport":
                    self.character["outfit"] = "sport"
                    self.character["has_racket"] = True
                    self.props["sport_bag_visible"] = False
                    self._emit_audio("grab_racket", now)
                self.character["pose"] = "spin_change"
            elif t < 2.5:
                if self.character["pose"] != "warmup_wobble":
                    self.character["pose"] = "warmup_wobble"
                    self._emit_audio("warmup_swing", now)
            elif t < 3.3:
                self.character["pose"] = "shy_ready"
                self.character["emotion"] = "shy_smile"
            else:
                self._init_scene_state("S3", now)

        elif sc == "S3":
            # S3 全息发球机启动：抬头 -> 蓄力 -> 发射第一球进入 S4
            t = elapsed * speed_factor
            self.hologram["charge"] = min(1.0, t / 1.1)
            if 0.35 <= t < 0.45 and self.hologram["mode"] == "warmup":
                self.hologram["mode"] = "serving"
                self._emit_audio("machine_charge", now)
            if t >= 1.15 and not self.shuttles:
                self._emit_audio("shuttle_launch", now, pan=0.6)
                self._spawn_serve_from_hologram(now, fast=False)

        elif sc == "S4":
            # S4 第一次对打：若球落地超过 1.3s，自动由发球机补发一球保持流畅体验
            if self.shuttles and self.shuttles[0]["phase"] == "codex_to_human":
                self.character["pose"] = "ready_wait"
            elif self.shuttles and self.shuttles[0]["phase"] == "human_to_codex":
                s = self.shuttles[0]
                self.character["x"] += (s["x1"] - self.character["x"]) * 0.14
                self.character["pose"] = "move_run"
            elif self.shuttles and self.shuttles[0]["phase"] == "landed":
                if now - self.shuttles[0]["end_ms"] > 1200:
                    self.shuttles.clear()
                    self._emit_audio("shuttle_launch", now, pan=0.6)
                    self._spawn_serve_from_hologram(now, fast=False)

        elif sc == "S5":
            # S5 Codex 输球：扑空摔倒 -> 坐地看向用户 -> 低头小小叹气 -> 情绪留白 -> 进入 S6
            if self.character["pose"] == "panic_run" and self.shuttles:
                s = self.shuttles[0]
                self.character["x"] += (s["x1"] - 0.04 - self.character["x"]) * 0.12
            elif self.character["pose"] == "dive_fall":
                land_at = self.shuttles[0]["end_ms"] if self.shuttles else self.scene_since
                since_fall = (now - land_at) / 1000.0
                if 0.85 <= since_fall < 2.2:
                    if self.character["emotion"] != "sighing":
                        self.character["emotion"] = "sighing"
                        self._emit_audio("lose_sigh", now)
                elif since_fall >= 2.4:
                    self._init_scene_state("S6", now)

        elif sc == "S6":
            # S6 假装可怜：捡起球拍缩肩膀 -> 偷偷抬眼看用户有没有心软 -> 进入 S7
            t = elapsed * speed_factor
            if t < 1.3:
                self.character["pose"] = "sit_pity"
                self.character["emotion"] = "pity_sad"
            elif t < 2.7:
                self.character["pose"] = "pity_peek"
                self.character["emotion"] = "pity_peek"
            else:
                self._init_scene_state("S7", now)

        elif sc == "S7":
            # S7 偷偷作弊：坏笑按下小遥控器 -> 全息发球机红灯高速连发 -> Codex 叉腰大笑
            t = elapsed * speed_factor
            if t < 0.9:
                self.character["pose"] = "evil_remote"
            else:
                self.character["pose"] = "cheat_laugh"
                self.character["emotion"] = "evil_laugh"
                # 每隔 380ms 发射一颗作弊高速球（最多连发 6 颗）
                if t < 3.5 and now - self.hologram["last_launch_ms"] >= 380:
                    self._emit_audio("cheat_rapid", now, volume=0.75, pan=0.55)
                    self._spawn_serve_from_hologram(now, fast=True)
                elif t >= 3.8:
                    self._init_scene_state("S8", now)

        elif sc == "S8":
            # S8 机器失控：发球机超速卡顿积压异响 -> Codex 笑声停止，慢慢转头盯着机器
            t = elapsed * speed_factor
            self.hologram["jam_pile"] = min(6, 2 + int(t * 2))
            if t < 0.7:
                self.character["pose"] = "cheat_laugh"
            elif t < 2.3:
                self.character["pose"] = "slow_turn_to_holo"
                self.character["emotion"] = "uh_oh"
                self.character["facing"] = 1  # 转头看向右侧全息发球机
            else:
                self._init_scene_state("S9", now)

        elif sc == "S9":
            # S9 反噬：被超大羽毛球正面拍扁在屏幕上 -> 停顿片刻缓慢滑落 -> 趴地伸手按停遥控器
            if self.character["pose"] == "screen_pancake":
                self.character["screen_splat_progress"] += dt_ms / 1000.0
                sp = self.character["screen_splat_progress"]
                if 0.45 <= sp < 0.55:
                    self._emit_audio("splat_slide", now)
                elif sp >= 2.2:
                    self.character["pose"] = "floor_press_stop"
                    self.character["emotion"] = "dizzy"
                    self.hologram["mode"] = "off"
                    self.hologram["red_led"] = False
                    self.hologram["vibration"] = 0.0
                    self._emit_audio("close_laptop", now)
            elif self.character["pose"] == "floor_press_stop":
                if elapsed > 3.6:
                    self._init_scene_state("S10", now)

        elif sc == "S10":
            # S10 结尾恢复：缓慢爬起 -> 检查球拍 -> 尴尬藏到身后停留在当前画面
            self.character["pose"] = "awkward_hide_racket"
            self.character["facing"] = -1

    # =========================================================================
    # 摄像头手部识别与宽容挥拍判定接口 (Section 4 & 5)
    # =========================================================================
    def report_camera_frame(self, hand_detected, x=0.5, y=0.5, speed=0.0, vx=0.0, vy=0.0, source="webrtc"):
        """
        接收来自 WebRTC MediaPipe/Canvas 动捕或 Python OpenCV 动捕的实时帧数据：
        实现：手部可见 + 有效挥动 + 处于可接球窗口 + 冷却防误触 = 成功回球
        """
        with self.lock:
            now = self.clock()
            self.devices["camera"].update({
                "online": True,
                "last_seen": now,
                "hand_detected": bool(hand_detected),
                "hand_x": round(float(x), 3),
                "hand_y": round(float(y), 3),
                "speed": round(float(speed), 2),
                "source": source,
            })
            if not hand_detected:
                return self._publish(now)

            threshold = float(self.params.get("sensitivity_threshold", 18.0))
            cooldown = int(self.params.get("cooldown_ms", 240))

            if float(speed) >= threshold and (now - self.last_swing_ms) >= cooldown:
                self.last_swing_ms = now
                self._handle_valid_swing(now, float(speed), source="camera_hand")

            return self._publish(now)

    def trigger_manual_swing(self, power=32.0, source="director_manual"):
        """导演控制台或单机测试手动触发挥拍（明确区分真实摄像头输入与导演手动触发）"""
        with self.lock:
            now = self.clock()
            self.last_swing_ms = now
            self._handle_valid_swing(now, float(power), source=source)
            return self._publish(now)

    def _handle_valid_swing(self, now, speed, source="camera_hand"):
        # 1. 若处于 S4 / S5 且存在飞向真人的球：检查宽容接球窗口
        if self.scene_id in ("S4", "S5"):
            for s in self.shuttles:
                if s["phase"] == "codex_to_human":
                    # 在宽容窗口内（或导演拍摄模式下球已飞过 35% 路程）即可成功击回！
                    in_window = (self.hit_window.get("open") or
                                 (self.system_mode == "director" and now >= s["start_ms"] + (s["end_ms"] - s["start_ms"]) * 0.32))
                    if in_window:
                        is_smash = (speed >= float(self.params.get("sensitivity_threshold", 18.0)) * 1.65) or (self.scene_id == "S5")
                        self._trigger_human_return_shot(now, s, is_smash=is_smash)
                        self._emit_unified_event("human_hit_success", "all", now, now, {
                            "source": source, "speed": round(speed, 1), "smash": is_smash
                        })
                        return
        # 2. 若处于 S7 作弊连发阶段：真人挥拍可将飞来的作弊羽毛球挡飞/弹开！
        if self.scene_id == "S7":
            for s in self.shuttles:
                if s["phase"] in ("holo_to_codex", "codex_to_human"):
                    s["phase"] = "deflected"
                    s["start_ms"] = now
                    s["x0"], s["y0"] = s["x"], s["y"]
                    s["x1"] = 0.15 + (now % 5) * 0.14
                    s["y1"] = 0.25
                    self.particles.append({
                        "kind": "hit_spark", "x": s["x"], "y": s["y"],
                        "at": now, "dur": 260, "smash": False
                    })
                    self._emit_audio("hit_normal", now, volume=0.85, pan=-0.2)
                    break

    # =========================================================================
    # 导演控制台操作与回滚 API (Section 11 & 12)
    # =========================================================================
    def start_play_with_me(self):
        """点击「陪我打球」：从 S0 进入 S1 收拾场地开启完整互动短剧"""
        with self.lock:
            now = self.clock()
            self.paused = False
            self._init_scene_state("S1", now)
            return self._publish(now)

    def jump_to_scene(self, scene_id):
        """运行时剧情快照回滚：跳转到任意 S0~S10 节点并彻底清理残留状态"""
        with self.lock:
            now = self.clock()
            self.paused = False
            self._init_scene_state(scene_id, now)
            self._emit_unified_event("scene_rollback", "all", now, now, {"scene_id": scene_id})
            return self._publish(now)

    def prev_scene(self):
        with self.lock:
            idx = max(0, SCENE_INDEX.get(self.scene_id, 0) - 1)
            return self.jump_to_scene(STORY_SCENES[idx]["id"])

    def next_scene(self):
        with self.lock:
            idx = min(len(STORY_SCENES) - 1, SCENE_INDEX.get(self.scene_id, 0) + 1)
            return self.jump_to_scene(STORY_SCENES[idx]["id"])

    def replay_current_scene(self):
        with self.lock:
            return self.jump_to_scene(self.scene_id)

    def set_paused(self, paused):
        with self.lock:
            now = self.clock()
            if paused and not self.paused:
                self.paused = True
                self.pause_started_ms = now
                self._emit_audio("silence", now, bgm="pause")
            elif not paused and self.paused:
                delta = now - self.pause_started_ms
                self.scene_since += delta
                for s in self.shuttles:
                    s["launch_ms"] += delta
                    s["start_ms"] += delta
                    s["end_ms"] += delta
                self.paused = False
            return self._publish(now)

    def manual_serve(self, fast=False):
        with self.lock:
            now = self.clock()
            if self.scene_id in ("S0", "S1", "S2"):
                self._init_scene_state("S4", now)
            else:
                self._emit_audio("shuttle_launch", now, pan=0.6)
                self._spawn_serve_from_hologram(now, fast=fast)
            return self._publish(now)

    def update_params(self, updates):
        with self.lock:
            now = self.clock()
            if "preset" in updates and updates["preset"] in self.presets:
                self.active_preset = updates["preset"]
                self.params = copy.deepcopy(self.presets[self.active_preset])
            if "system_mode" in updates and updates["system_mode"] in ("single", "multi", "director"):
                self.system_mode = updates["system_mode"]
            if "compact_version" in updates:
                self.compact_version = bool(updates["compact_version"])
            if "preferred_ip" in updates and updates["preferred_ip"]:
                self.preferred_ip = str(updates["preferred_ip"])
            for k, v in updates.get("params", {}).items():
                if k in self.params:
                    self.params[k] = v
            # 灵敏度档位联动阈值
            sens = self.params.get("sensitivity")
            if sens == "easy" and "sensitivity_threshold" not in updates.get("params", {}):
                self.params["sensitivity_threshold"] = 16.0
                self.params["hit_window_ms"] = 720
            elif sens == "normal" and "sensitivity_threshold" not in updates.get("params", {}):
                self.params["sensitivity_threshold"] = 24.0
                self.params["hit_window_ms"] = 580
            elif sens == "hard" and "sensitivity_threshold" not in updates.get("params", {}):
                self.params["sensitivity_threshold"] = 34.0
                self.params["hit_window_ms"] = 420

            for k, v in updates.get("court", {}).items():
                if k in self.court:
                    self.court[k] = v
            return self._publish(now)

    def refresh_lan_ips(self):
        """重新扫描物理局域网网卡 IP 列表（支持热插拔 Wi-Fi 或切换热点后实时刷新）。"""
        with self.lock:
            now = self.clock()
            self.lan_ips = detect_lan_ips()
            if self.preferred_ip not in self.lan_ips:
                self.preferred_ip = self.lan_ips[0]
            return self._publish(now)

    def request_desktop_close(self):
        """通知透明桌面端窗口安全关闭（保留后台服务与网页导演端继续运行）。"""
        with self.lock:
            now = self.clock()
            self.desktop_close_seq += 1
            self.devices["desktop"]["online"] = False
            return self._publish(now)

    def request_system_shutdown(self):
        """广播全系统关闭信号（关闭桌面端与服务）。"""
        with self.lock:
            now = self.clock()
            self.system_shutdown = True
            self.desktop_close_seq += 1
            self.devices["desktop"]["online"] = False
            return self._publish(now)

    def heartbeat_device(self, role, rtt_ms=0, ack_event_id=0, extra=None):
        with self.lock:
            now = self.clock()
            if role in self.devices:
                self.devices[role]["online"] = True
                self.devices[role]["last_seen"] = now
                if rtt_ms:
                    self.devices[role]["rtt_ms"] = round(float(rtt_ms), 1)
                if ack_event_id:
                    self.devices[role]["last_ack_event"] = int(ack_event_id)
                if isinstance(extra, dict):
                    if role == "desktop" and extra.get("reset_close"):
                        self.system_shutdown = False
                    self.devices[role].update(
                        {k: v for k, v in extra.items() if k != "reset_close"}
                    )
            return self._snapshot(now)

    def _snapshot(self, now):
        # 检查设备在线超时 (超过 6 秒未心跳视为离线)
        for role, info in self.devices.items():
            if info["last_seen"] and (now - info["last_seen"] > 6000):
                info["online"] = False

        scene_meta = STORY_SCENES[SCENE_INDEX.get(self.scene_id, 0)]
        return {
            "session_id": self.session_id,
            "seq": self.seq,
            "now_ms": now,
            "system_mode": self.system_mode,
            "compact_version": self.compact_version,
            "paused": self.paused,
            "desktop_close_seq": self.desktop_close_seq,
            "system_shutdown": self.system_shutdown,
            "scene_id": self.scene_id,
            "scene_code": scene_meta["code"],
            "scene_title": scene_meta["title"],
            "scene_desc": scene_meta["desc"],
            "scene_elapsed_sec": round((now - self.scene_since) / 1000.0, 2),
            "scenes_catalog": STORY_SCENES,
            "rally_count": self.rally_count,
            "character": copy.deepcopy(self.character),
            "props": copy.deepcopy(self.props),
            "hologram": copy.deepcopy(self.hologram),
            "shuttles": copy.deepcopy(self.shuttles),
            "particles": copy.deepcopy(self.particles),
            "hit_window": copy.deepcopy(self.hit_window),
            "cooldown_active": (now - self.last_swing_ms) < int(self.params.get("cooldown_ms", 240)),
            "last_swing_ms": self.last_swing_ms,
            "last_valid_hit_ms": self.last_valid_hit_ms,
            "active_preset": self.active_preset,
            "params": copy.deepcopy(self.params),
            "court": copy.deepcopy(self.court),
            "devices": copy.deepcopy(self.devices),
            "lan_ips": self.lan_ips,
            "preferred_ip": self.preferred_ip,
            "http_port": self.http_port,
            "https_port": self.https_port,
            "audio_events": list(self.audio_events),
            "unified_events": list(self.unified_events)[-8:],
        }

    def snapshot(self):
        with self.lock:
            return self._snapshot(self.clock())

    def _publish(self, now):
        self.seq += 1
        snap = self._snapshot(now)
        for q in list(self.listeners):
            try:
                q.get_nowait()
            except queue.Empty:
                pass
            try:
                q.put_nowait(snap)
            except queue.Full:
                pass
        return snap

    def subscribe(self):
        q = queue.Queue(maxsize=1)
        with self.lock:
            self.listeners.add(q)
            q.put_nowait(self.snapshot())
        return q

    def unsubscribe(self, q):
        with self.lock:
            self.listeners.discard(q)

    def _loop(self):
        while not self._stop.wait(0.025):
            with self.lock:
                now = self.clock()
                dt_ms = max(1, now - self.last_step)
                self._step_shuttles(now)
                self._step_story(now, dt_ms)
                self.last_step = now
                self._publish(now)
