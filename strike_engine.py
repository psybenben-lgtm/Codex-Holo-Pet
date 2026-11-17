"""Shared keyboard, character, cross-screen digging/throwing and hologram bath/scrubbing timeline."""
from collections import deque
import math
import queue
import threading
import time
from uuid import uuid4

CONFIG = {
    "KEY_IDLE_MS": 300,            # 停打超过 300ms 立即停铲喘气
    "RATE_WINDOW_MS": 750,
    "FAST_HITS_PER_SEC": 6.0,      # >5 键/秒 线性加速至高速快打带残影
    "WORK_CYCLE_SLOW": 0.72,       # 慢速敲键 (1~2 键/秒) 从容挥铲周期
    "WORK_CYCLE_FAST": 0.24,       # 高速快打 (>5 键/秒) 急速挥铲周期
    "TIRED_CYCLE_MULTIPLIER": 1.25,
    "FATIGUE_GAIN_PER_HIT": 1.45,
    "FAST_FATIGUE_BONUS": 1.65,
    "FATIGUE_RECOVERY_PER_SEC": 2.2,
    "TIRED_THRESHOLD": 32.0,
    "ANGRY_THRESHOLD": 65.0,
    "STRIKE_THRESHOLD": 100.0,
    "LOOK_AT_HANDS_MS": 1100,      # 阶段 1（怀疑人生看双手）时长
    "RAGE_GLARE_MS": 1100,         # 阶段 2（怒火中烧冒十字青筋）时长
    "OFFICE_SIGH_MS": 420,         # 触发挖土前工位深叹气时长
    "WALK_TO_EDGE_MS": 350,        # 电脑端起身走向右边缘 (350 + 200 + 350 = 900ms 跨端匀速接力)
    "CROSS_EDGE_MS": 200,          # 跨端半身拼接重叠窗口
    "HOLO_WALK_MS": 350,           # 全息端从左侧虚空迈入中央
    "RETURN_IDLE_MS": 30000,       # 停铲休息 30 秒无操作才自动回工位，避免打断本地多端调试
    "THROW_WINDUP_MS": 550,        # 阶段 3（深蹲抱大团湿泥蓄力）时长
    "FLY_DURATION_MS": 520,        # 阶段 4（全息甩出后严格在第 520ms 瞬间引爆电脑全屏泥巴）
    "FLY_HANDOFF": 0.48,
    "MUD_ENTRY_Y_RATIO": 0.88,
    "MUD_IMPACT_X_RATIO": 0.50,    # 电脑屏幕正中央受击
    "MUD_IMPACT_Y_RATIO": 0.48,
    "MUD_SCALE": 1.42,             # 大面积浓稠核心湿泥饼
    "MUD_LINGER_SEC": 45.0,        # 保持在屏幕上流淌滴水，直到搓澡洗净或重置
    "HOLO_ENTRY_SIDE": -1,
    "HOLO_SCALE": 1.24,
    "DOCK_BOTTOM_PX": 14,
    "DISCOVERY_INTERVALS": (6, 9, 7, 11),  # 挖土随机彩蛋触发铲数间隔（旧球鞋、易拉罐、小金币）
    "BATH_ENTER_MS": 800,          # 推入浴缸滑入全息中心时长
    "BATH_RETURN_MS": 900,         # 泡完澡湿漉漉走回电脑桌宠时长
    "CLEAN_DONE_MS": 2000,         # 搓完全身冒金星庆祝时长
    "STRIKE_COOLDOWN_MS": 0,
}

VERSION = 3
LEASE_MS = 8000
TICK_MS = 25
HOME_STATES = {"OFFICE_IDLE", "OFFICE_WORK"}
DIG_STATES = {"WORKING", "TIRED"}
BATH_STATES = {"BATH_ENTER", "BATH_SOAK", "BATH_RETURN", "SCRUBBING", "CLEAN_DONE"}


class StrikeEngine:
    def __init__(self, run=True):
        self.lock = threading.RLock()
        self.listeners = set()
        self.epoch = uuid4().hex
        self.wall_origin = time.time_ns() // 1_000_000
        self.mono_origin = time.monotonic_ns() // 1_000_000
        self.seq = 0
        self.throw_serial = 0
        self.lease = 0
        self.enabled = True
        self.working = False
        self.manual_active = False
        self._manual_dig_until = 0
        self._reset(self.wall_origin)
        self._stop = threading.Event()
        if run:
            threading.Thread(target=self._loop, daemon=True).start()

    def clock(self):
        return self.wall_origin + time.monotonic_ns() // 1_000_000 - self.mono_origin

    def _reset(self, now):
        self.manual_active = False
        self._manual_dig_until = 0
        self.state = "OFFICE_WORK" if self.working else "OFFICE_IDLE"
        self.since = self.last_step = now
        self.last_hit = 0
        self.hits = deque()
        self.key_rate = 0.0
        self.total_hits = 0
        self.fatigue = self.energy = self.dig_rate = 0.0
        self.phase = 0.0
        self.stop_dig_at = 0
        self.cross = self.mud = self.discovery = None
        self.digs = self.finds = self.contacts = 0
        self.leave_after_return = False
        self.angry_stage = 0
        self.bath = {
            "active": False,
            "enter_start_ms": 0,
            "enter_end_ms": 0,
            "water_level": 0.75,
            "temp": 42.0,          # 默认温暖 42°C (20~95°C)
            "foam": 65.0,          # 彩色肥皂泡泡浓度 (0~100)
            "hot_jump": False,
            "soak_progress": 0.0,
            "duck_phase": 0.0,
            "scrub_zone": "none",  # 'none' | 'back' | 'head'
            "scrub_x": 0.5,
            "scrub_y": 0.55,
            "scrub_dx": 0.0,
            "scrub_dy": 0.0,
            "scrub_active_until": 0,
            "question_until": 0,
            "question_serial": 0,
            "clean_progress": 0.0,
            "clean_done_at": 0,
        }

    def _enter(self, state, now):
        self.state, self.since = state, now

    def _leave(self, now):
        cfg = CONFIG
        start = now + cfg["OFFICE_SIGH_MS"] + cfg["WALK_TO_EDGE_MS"]
        end = start + cfg["CROSS_EDGE_MS"]
        self.cross = {
            "sigh_end": now + cfg["OFFICE_SIGH_MS"],
            "start": start,
            "end": end,
            "arrive": end + cfg["HOLO_WALK_MS"],
            "total_relay_ms": cfg["WALK_TO_EDGE_MS"] + cfg["CROSS_EDGE_MS"] + cfg["HOLO_WALK_MS"],
        }
        self._enter("LEAVING", now)

    def _return(self, now):
        cfg = CONFIG
        start = now + cfg["HOLO_WALK_MS"]
        end = start + cfg["CROSS_EDGE_MS"]
        self.cross = {
            "start": start,
            "end": end,
            "arrive": end + cfg["WALK_TO_EDGE_MS"],
            "total_relay_ms": cfg["HOLO_WALK_MS"] + cfg["CROSS_EDGE_MS"] + cfg["WALK_TO_EDGE_MS"],
        }
        self._enter("RETURNING", now)

    def _throw(self, now):
        cfg = CONFIG
        self.throw_serial += 1
        launch = now + cfg["THROW_WINDUP_MS"]
        fly = cfg["FLY_DURATION_MS"]
        self.mud = {
            "serial": self.throw_serial,
            "windup_start_ms": now,
            "launch_time_ms": launch,
            "edge_time_ms": launch + round(fly * cfg["FLY_HANDOFF"]),
            "impact_time_ms": launch + fly,
            "target_x_ratio": cfg["MUD_IMPACT_X_RATIO"],
            "target_y_ratio": cfg["MUD_IMPACT_Y_RATIO"],
            "mud_scale": cfg["MUD_SCALE"],
            "linger_sec": cfg["MUD_LINGER_SEC"],
            "entry_y_ratio": cfg["MUD_ENTRY_Y_RATIO"],
            "zoom_max": 4.5,
            "clean_ratio": 0.0,
        }
        self._enter("THROWING", now)

    def _update_rate(self, now):
        cfg = CONFIG
        while self.hits and self.hits[0] <= now - cfg["RATE_WINDOW_MS"]:
            self.hits.popleft()
        rate = len(self.hits) * 1000.0 / cfg["RATE_WINDOW_MS"]
        self.key_rate = round(rate, 2)
        self.energy = min(1.0, rate / cfg["FAST_HITS_PER_SEC"])
        period = cfg["WORK_CYCLE_SLOW"] + (cfg["WORK_CYCLE_FAST"] - cfg["WORK_CYCLE_SLOW"]) * self.energy
        if self.state == "TIRED":
            period *= cfg["TIRED_CYCLE_MULTIPLIER"]
        self.dig_rate = (1.0 / period) if self.state in DIG_STATES else 0.0

    def _dig(self, until):
        if not self.dig_rate:
            return
        previous = self.phase
        self.phase += max(0, min(until, self.stop_dig_at) - self.last_step) * self.dig_rate / 1000.0
        if int(previous + 0.52) == int(self.phase + 0.52):
            return
        self.digs += 1
        self.contacts += 1
        intervals = CONFIG["DISCOVERY_INTERVALS"]
        if self.digs >= intervals[self.finds % len(intervals)]:
            kind = self.finds % 3
            names = ("破烂旧球鞋", "压扁易拉罐", "闪亮小金币")
            self.discovery = {
                "serial": self.finds + 1,
                "at": until,
                "kind": kind,
                "name": names[kind],
            }
            self.finds += 1
            self.digs = 0

    def _step(self, now):
        cfg = CONFIG
        dt = max(0, now - self.last_step)
        self._dig(now)
        self.last_step = now

        if self.mud:
            clean_r = self.bath.get("clean_progress", 0.0) / 100.0
            self.mud["clean_ratio"] = round(clean_r, 3)
            if clean_r >= 1.0 or now >= self.mud["impact_time_ms"] + self.mud["linger_sec"] * 1000:
                if self.state not in ("THROWING", "STRIKE", "BATH_ENTER", "BATH_SOAK", "BATH_RETURN", "SCRUBBING"):
                    self.mud = None

        if self.lease and now >= self.lease:
            self.lease = 0
            self.working = False

        if self.state == "THROWING":
            if now >= self.mud["impact_time_ms"]:
                self._enter("STRIKE", self.mud["impact_time_ms"])
            return

        if self.state == "BATH_ENTER":
            if now >= self.bath["enter_end_ms"]:
                self._enter("BATH_SOAK", self.bath["enter_end_ms"])
            return

        if self.state == "BATH_SOAK":
            if not self.bath["hot_jump"]:
                self.bath["soak_progress"] = min(100.0, self.bath["soak_progress"] + dt * 0.012)
            return

        if self.state == "BATH_RETURN":
            if self.cross and now >= self.cross["arrive"]:
                self._enter("SCRUBBING", self.cross["arrive"])
            return

        if self.state == "SCRUBBING":
            if now >= self.bath["scrub_active_until"]:
                self.bath["scrub_dx"] *= 0.6
                self.bath["scrub_dy"] *= 0.6
                if now >= self.bath["question_until"] and self.bath["scrub_zone"] != "none":
                    self.bath["scrub_zone"] = "none"
            if self.bath["clean_progress"] >= 100.0:
                self.bath["clean_done_at"] = now
                self.mud = None
                self._enter("CLEAN_DONE", now)
            return

        if self.state == "CLEAN_DONE":
            if now - self.since >= cfg["CLEAN_DONE_MS"]:
                self._reset(now)
            return

        if self.working and not self.manual_active:
            if self.state in ("OFFICE_IDLE", "RESTING"):
                self._enter("OFFICE_WORK", now)
                self.fatigue = 0.0
                self.angry_stage = 0
            return

        if self.state == "OFFICE_WORK" and not self.working:
            self._enter("OFFICE_IDLE", now)

        if self.state == "LEAVING" and now >= self.cross["arrive"]:
            self._enter("WORKING", self.cross["arrive"])
            self.stop_dig_at = max(self.last_hit + cfg["KEY_IDLE_MS"], self._manual_dig_until, now + 450)
            self.phase = 0.22

        if self.state in DIG_STATES and now >= self.stop_dig_at:
            self._enter("RESTING", self.stop_dig_at)

        if self.state == "RESTING" and now - self.since >= cfg["RETURN_IDLE_MS"]:
            self._return(now)

        if self.state == "RETURNING" and now >= self.cross["arrive"]:
            queued = self.leave_after_return
            self._reset(now)
            if queued:
                self.manual_active = True
                self._leave(now)

        if self.state == "STRIKE":
            cooldown = cfg["STRIKE_COOLDOWN_MS"]
            if cooldown and now - max(self.since, self.last_hit) >= cooldown:
                self._reset(now)
            return

        if self.state in {"RESTING", "ANGRY"} and now > self.last_hit + cfg["KEY_IDLE_MS"]:
            self.fatigue = max(0.0, self.fatigue - dt * cfg["FATIGUE_RECOVERY_PER_SEC"] / 1000.0)

        if self.state in DIG_STATES and self.fatigue >= cfg["ANGRY_THRESHOLD"]:
            self.angry_stage = 1
            self._enter("ANGRY", now)
        elif self.state == "WORKING" and self.fatigue >= cfg["TIRED_THRESHOLD"]:
            self._enter("TIRED", now)

        if self.state == "ANGRY":
            elapsed_angry = now - self.since
            if elapsed_angry < cfg["LOOK_AT_HANDS_MS"]:
                self.angry_stage = 1
            else:
                self.angry_stage = 2
            if elapsed_angry >= cfg["LOOK_AT_HANDS_MS"] + cfg["RAGE_GLARE_MS"]:
                if self.fatigue >= cfg["STRIKE_THRESHOLD"] or now < self.last_hit + 900:
                    self._throw(now)
                elif self.fatigue < cfg["ANGRY_THRESHOLD"] - 10:
                    self.angry_stage = 0
                    self._enter("RESTING", now)
            elif self.fatigue >= cfg["STRIKE_THRESHOLD"] and elapsed_angry >= cfg["LOOK_AT_HANDS_MS"] + 450:
                self._throw(now)

    def set_enabled(self, enabled):
        with self.lock:
            now = self.clock()
            self.enabled = bool(enabled)
            if not self.enabled:
                self.lease = 0
                self._reset(now)
            return self._publish(now)

    def record_input(self, hit_count=1, *, working=None, enabled=True, manual_burst=False):
        with self.lock:
            now = self.clock()
            self._step(now)
            self.enabled = bool(enabled)
            if working is not None and enabled:
                self.lease = now + LEASE_MS
            elif enabled and not self.lease:
                self.lease = now + LEASE_MS
            if not enabled:
                self.working, self.lease = False, 0
                self._reset(now)
                return self._publish(now)
            if working is not None:
                self.working = working
                self._step(now)
            if hit_count > 0:
                self.manual_active = True
                self.total_hits += hit_count
                if self.state in HOME_STATES or self.state in BATH_STATES or self.state == "STRIKE":
                    if self.state in BATH_STATES or self.state == "STRIKE":
                        self.bath["active"] = False
                        self.mud = None
                    self._leave(now)
                self.last_hit = now
                self.hits.extend([now] * hit_count)
                self._update_rate(now)
                cfg = CONFIG
                dig_hold = cfg["KEY_IDLE_MS"] if not manual_burst else 2200
                if manual_burst:
                    self._manual_dig_until = max(self._manual_dig_until, now + 2600)
                if self.state == "RETURNING":
                    self.leave_after_return = True
                elif self.state not in ("THROWING", "STRIKE") and self.state not in BATH_STATES:
                    gain = cfg["FATIGUE_GAIN_PER_HIT"] + cfg["FAST_FATIGUE_BONUS"] * (self.energy ** 2)
                    self.fatigue = min(cfg["STRIKE_THRESHOLD"], self.fatigue + hit_count * gain)
                    dig_base = (self.cross or {}).get("arrive", now) if self.state == "LEAVING" else now
                    self.stop_dig_at = max(self.stop_dig_at, dig_base + dig_hold)
                    if self.state == "RESTING":
                        self.phase = int(self.phase) + 1.22
                        self._enter("TIRED" if self.fatigue >= cfg["TIRED_THRESHOLD"] else "WORKING", now)
                self._step(now)
            self._update_rate(now)
            return self._publish(now)

    def trigger_discovery_manually(self, kind=None):
        with self.lock:
            now = self.clock()
            self._step(now)
            self.enabled = True
            self.manual_active = True
            if self.state in HOME_STATES or self.state == "LEAVING":
                self._enter("WORKING", now)
                self.stop_dig_at = now + 1800
            else:
                self.stop_dig_at = max(self.stop_dig_at, now + 1800)
            k = (self.finds % 3) if kind is None else (int(kind) % 3)
            names = ("破烂旧球鞋", "压扁易拉罐", "闪亮小金币")
            self.discovery = {
                "serial": self.finds + 1,
                "at": now,
                "kind": k,
                "name": names[k],
            }
            self.finds += 1
            return self._publish(now)

    def trigger_angry_manually(self, stage=1):
        with self.lock:
            now = self.clock()
            self._step(now)
            self.enabled = True
            self.manual_active = True
            self.fatigue = max(self.fatigue, CONFIG["ANGRY_THRESHOLD"] + 15.0)
            self.angry_stage = 2 if stage == 2 else 1
            offset = CONFIG["LOOK_AT_HANDS_MS"] if stage == 2 else 0
            self._enter("ANGRY", now - offset)
            return self._publish(now)

    def trigger_strike_manually(self):
        with self.lock:
            now = self.clock()
            self._step(now)
            self.enabled = True
            self.manual_active = True
            self.bath["active"] = False
            self.fatigue = CONFIG["STRIKE_THRESHOLD"]
            self._throw(now)
            return self._publish(now)

    def push_bathtub(self):
        with self.lock:
            now = self.clock()
            self._step(now)
            self.enabled = True
            self.manual_active = True
            self.cross = None
            dur = CONFIG["BATH_ENTER_MS"]
            self.bath.update({
                "active": True,
                "enter_start_ms": now,
                "enter_end_ms": now + dur,
                "water_level": 0.78,
                "temp": 42.0,
                "foam": 70.0,
                "hot_jump": False,
                "soak_progress": 15.0,
                "scrub_zone": "none",
                "clean_progress": 0.0,
            })
            self._enter("BATH_ENTER", now)
            return self._publish(now)

    def update_bath_knob(self, temp=None, foam=None, water_level=None):
        with self.lock:
            now = self.clock()
            self._step(now)
            self.enabled = True
            self.manual_active = True
            if self.state not in ("BATH_ENTER", "BATH_SOAK"):
                self.bath["active"] = True
                self.bath["enter_start_ms"] = now - CONFIG["BATH_ENTER_MS"]
                self.bath["enter_end_ms"] = now
                self._enter("BATH_SOAK", now)
            if temp is not None:
                t_val = max(15.0, min(98.0, float(temp)))
                self.bath["temp"] = round(t_val, 1)
                self.bath["hot_jump"] = t_val >= 72.0
            if foam is not None:
                self.bath["foam"] = round(max(20.0, min(100.0, float(foam))), 1)
            if water_level is not None:
                self.bath["water_level"] = round(max(0.4, min(1.0, float(water_level))), 2)
            if not self.bath["hot_jump"]:
                self.bath["soak_progress"] = min(100.0, self.bath["soak_progress"] + 6.0)
            return self._publish(now)

    def start_scrubbing(self, immediate=False):
        with self.lock:
            now = self.clock()
            self._step(now)
            self.enabled = True
            self.manual_active = True
            self.bath["active"] = True
            self.bath["hot_jump"] = False
            self.bath["scrub_zone"] = "none"
            if immediate:
                self._enter("SCRUBBING", now)
            else:
                cfg = CONFIG
                start = now + cfg["HOLO_WALK_MS"]
                end = start + cfg["CROSS_EDGE_MS"]
                self.cross = {
                    "start": start,
                    "end": end,
                    "arrive": end + cfg["WALK_TO_EDGE_MS"],
                    "total_relay_ms": cfg["BATH_RETURN_MS"],
                }
                self._enter("BATH_RETURN", now)
            return self._publish(now)

    def scrub_move(self, x=0.5, y=0.55, dx=0.0, dy=0.0, zone="back", delta=3.5):
        with self.lock:
            now = self.clock()
            self._step(now)
            self.enabled = True
            self.manual_active = True
            if self.state != "SCRUBBING":
                self.bath["active"] = True
                self._enter("SCRUBBING", now)
            self.bath["scrub_x"] = round(max(0.0, min(1.0, float(x))), 3)
            self.bath["scrub_y"] = round(max(0.0, min(1.0, float(y))), 3)
            self.bath["scrub_dx"] = round(max(-1.0, min(1.0, float(dx))), 3)
            self.bath["scrub_dy"] = round(max(-1.0, min(1.0, float(dy))), 3)
            self.bath["scrub_active_until"] = now + 380
            if zone == "head" or float(y) < 0.34:
                self.bath["scrub_zone"] = "head"
                if now >= self.bath["question_until"] - 200:
                    self.bath["question_serial"] += 1
                self.bath["question_until"] = now + 1150
            else:
                self.bath["scrub_zone"] = "back"
                gain = max(0.5, min(100.0, float(delta)))
                self.bath["clean_progress"] = round(min(100.0, self.bath["clean_progress"] + gain), 1)
                if self.mud:
                    self.mud["clean_ratio"] = round(self.bath["clean_progress"] / 100.0, 3)
                if self.bath["clean_progress"] >= 100.0:
                    self.bath["clean_done_at"] = now
                    self.mud = None
                    self._enter("CLEAN_DONE", now)
            return self._publish(now)

    def return_to_office(self, instant=False):
        with self.lock:
            now = self.clock()
            self._step(now)
            self.mud = None
            self.discovery = None
            self.bath["active"] = False
            self.bath["hot_jump"] = False
            self.bath["scrub_zone"] = "none"
            self.fatigue = 0.0
            self.angry_stage = 0
            self.stop_dig_at = 0
            self._manual_dig_until = 0
            self.leave_after_return = False
            if instant or self.state in HOME_STATES:
                self._reset(now)
            else:
                self.manual_active = True
                self._return(now)
            return self._publish(now)

    def reset(self):
        with self.lock:
            now = self.clock()
            self.epoch = uuid4().hex
            self._reset(now)
            return self._publish(now)

    def _snapshot(self, now):
        return {
            "version": VERSION,
            "epoch": self.epoch,
            "seq": self.seq,
            "enabled": bool(self.enabled),
            "state": self.state,
            "since": self.since,
            "state_time": round((now - self.since) / 1000.0, 3),
            "now_ms": now,
            "fatigue": round(self.fatigue, 2),
            "energy": round(self.energy * 10.0, 2),
            "key_rate": self.key_rate,
            "total_hits": self.total_hits,
            "dig_phase": round(self.phase, 4),
            "dig_rate": round(self.dig_rate, 3),
            "stop_dig_at": self.stop_dig_at,
            "angry_stage": self.angry_stage,
            "cross": self.cross,
            "mud": self.mud,
            "discovery": self.discovery,
            "contacts": self.contacts,
            "throw_serial": self.throw_serial,
            "bath": dict(self.bath),
            "config": CONFIG,
        }

    def snapshot(self):
        with self.lock:
            return self._snapshot(self.last_step)

    def _publish(self, now):
        self.seq += 1
        snapshot = self._snapshot(now)
        for listener in list(self.listeners):
            try:
                listener.get_nowait()
            except queue.Empty:
                pass
            try:
                listener.put_nowait(snapshot)
            except queue.Full:
                pass
        return snapshot

    def subscribe(self):
        listener = queue.Queue(maxsize=1)
        with self.lock:
            self.listeners.add(listener)
            listener.put_nowait(self.snapshot())
        return listener

    def unsubscribe(self, listener):
        with self.lock:
            self.listeners.discard(listener)

    def _loop(self):
        heartbeat = 0
        while not self._stop.wait(TICK_MS / 1000.0):
            with self.lock:
                now = self.clock()
                prev = self.state
                self._step(now)
                self._update_rate(now)
                active_anim = (
                    self.state in DIG_STATES
                    or self.state in ("LEAVING", "RETURNING", "ANGRY", "THROWING", "STRIKE")
                    or self.state in BATH_STATES
                )
                if prev != self.state or active_anim or now - heartbeat >= 500:
                    self._publish(now)
                    heartbeat = now
