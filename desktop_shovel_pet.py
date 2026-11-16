"""
《我就这样哄自己上班》—— 电脑桌面透明底「农村灰铁铲 + 圆形小金币」桌宠插件 (desktop_shovel_pet.py v3.0)
核心修复：
1. 金币 100% 盛在灰色的铁铲子头里面（绝不会跑到木把手上！）：
   - 直接以水平向右姿态构建灰铁铲：左侧 (x: 3..25) 为老木柄与T型握把，右侧 (x: 26..48) 为冷灰钢铁铲头凹槽！
   - 装在铲斗里的圆形小金币直接绘制在右侧灰色铁铲头的凹槽图层内，随铲子一体旋转，物理级严丝合缝！
2. 根治切换窗口后按 [Enter 回车键] 时灵时不灵的问题：
   - 搭载 Windows 底层全局键盘钩子 (WH_KEYBOARD_LL) + 250Hz 高频异步按键监测双引擎，无论切换到任何软件界面，按回车 100% 秒识别！
   - 支持随时打断重触发（只要间隔 > 0.45s，按回车立即响应，绝不吞键）。
3. 手机全息端已同步开启光学镜像翻转、取消手机震动、改用清脆金币碰撞叮当声、并将【赚钱啦！！！】放大推远至金字塔中央。
"""

import os
import sys
import math
import time
import json
import random
import ctypes
from ctypes import wintypes
import threading
import urllib.request
import winsound
import tkinter as tk
from PIL import Image, ImageTk

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SFX_DIR = os.path.join(BASE_DIR, "sfx")
HOLO_SERVER_URL = (__import__("sys").path.insert(0, BASE_DIR) or True) and __import__("local_runtime").get_local_host_url()
HTTP_OPENER = __import__("local_runtime").get_no_proxy_opener()

TRANSPARENT_KEY = "#010102"
PIXEL_SCALE = 2
TOTAL_COINS = 8


def play_sfx_async(wav_name):
    wav_path = os.path.join(SFX_DIR, wav_name)
    if os.path.exists(wav_path):
        try:
            winsound.PlaySound(wav_path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        except Exception:
            pass


def post_holo_event_async(stage, coin_index=1, total_coins=TOTAL_COINS, mode="work", wave_index=1):
    def _send():
        try:
            url = f"{HOLO_SERVER_URL}/api/manifest_event"
            data = json.dumps({
                "mode": mode,
                "stage": stage,
                "coin_index": coin_index,
                "total_coins": total_coins,
                "wave_index": wave_index,
            }).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
            with HTTP_OPENER.open(req, timeout=0.6) as _:
                pass
        except Exception:
            pass

    threading.Thread(target=_send, daemon=True).start()


# ==============================================================================
# 高精细像素绘制器：木柄在左、灰色铁铲头在右，圆形小金币严丝合缝盛在灰色铲头里！
# ==============================================================================
class FinePixelSprites:
    def __init__(self, scale=PIXEL_SCALE):
        self.s = scale
        self._shovel_empty = None
        self._coin_small_grid = None
        self._coin_tk_cache = {}
        self._composite_cache = {}
        self._ear_cache = {}

    def _upscale(self, img):
        return img.resize((img.width * self.s, img.height * self.s), Image.NEAREST)

    def _build_coin_grid(self):
        """构建 9x9 逻辑像素的正圆形小金币"""
        if self._coin_small_grid is not None:
            return self._coin_small_grid

        im = Image.new("RGBA", (9, 9), (0, 0, 0, 0))
        px = im.load()

        OUTLINE = (120, 53, 15, 255)      # 深褐金外圈
        GOLD_LIGHT = (254, 240, 138, 255) # 亮金高光环
        GOLD_MAIN = (250, 204, 21, 255)   # 纯金主色
        GOLD_CORE = (217, 119, 6, 255)    # 立体内芯
        WHITE = (255, 255, 255, 255)      # 反光白点

        for y in range(9):
            for x in range(9):
                dist = math.hypot(x - 4.0, y - 4.0)
                if 3.1 <= dist <= 4.2:
                    px[x, y] = OUTLINE
                elif dist < 3.1:
                    px[x, y] = GOLD_MAIN

        px[3, 2] = GOLD_LIGHT
        px[4, 2] = GOLD_LIGHT
        px[2, 3] = GOLD_LIGHT
        px[2, 4] = GOLD_LIGHT
        px[4, 4] = GOLD_CORE
        px[5, 4] = GOLD_CORE
        px[4, 5] = GOLD_CORE
        px[3, 3] = WHITE

        self._coin_small_grid = im
        return im

    def get_round_coin_upscaled(self):
        if "default" not in self._coin_tk_cache:
            self._coin_tk_cache["default"] = self._upscale(self._build_coin_grid())
        return self._coin_tk_cache["default"]

    def _build_horizontal_grey_shovel(self):
        """
        在 54x54 逻辑像素画布上直接绘制【水平朝右】的农村灰铁铲：
        - 左侧 (x: 4..8,   y: 22..32): 经典 T 型老木握把
        - 中左 (x: 8..25,  y: 25..29): 细长结实的木质铲杆
        - 颈部 (x: 24..29, y: 24..30): 深铁灰套筒箍圈 + 银白铆钉
        - 右侧 (x: 28..49, y: 20..33): 宽阔微凹的「农村灰铁铲头」（灰色钢铁铲斗，开口朝上盛金币，最右端 x=46..49 为银白亮刃！）
        """
        if self._shovel_empty is not None:
            return self._shovel_empty

        im = Image.new("RGBA", (54, 54), (0, 0, 0, 0))
        px = im.load()

        def rect(x0, y0, w, h, col):
            for yy in range(max(0, y0), min(54, y0 + h)):
                for xx in range(max(0, x0), min(54, x0 + w)):
                    px[xx, yy] = col

        OUTLINE = (15, 23, 42, 255)        # 深黑蓝外轮廓
        WOOD_DARK = (120, 53, 15, 255)     # 木柄暗部
        WOOD_MAIN = (161, 98, 7, 255)      # 木柄主色
        WOOD_LIGHT = (217, 119, 6, 255)    # 木柄亮部
        IRON_DARK = (51, 65, 85, 255)      # 深铁灰阴影
        IRON_MID = (71, 85, 105, 255)      # 铲斗内腔深灰
        IRON_MAIN = (100, 116, 139, 255)   # 农村灰铁铲标准灰
        IRON_LIGHT = (148, 163, 184, 255)  # 铁铲高光灰
        BLADE_EDGE = (226, 232, 240, 255)  # 右端银白锋利铲刃
        RIVET = (248, 250, 252, 255)       # 银铆钉

        # 1. 最左侧：T 型木质握把 (x: 4..8, y: 21..33)
        rect(4, 21, 5, 12, OUTLINE)
        rect(5, 22, 3, 10, WOOD_MAIN)
        rect(5, 22, 1, 10, WOOD_LIGHT)

        # 2. 中左部：细长木质铲柄 (x: 8..25, y: 25..29)
        rect(8, 24, 17, 6, OUTLINE)
        rect(8, 25, 17, 4, WOOD_MAIN)
        rect(8, 25, 17, 1, WOOD_LIGHT)
        rect(8, 28, 17, 1, WOOD_DARK)

        # 3. 中间颈部：灰铁套箍与银色铆钉 (x: 24..29, y: 23..31)
        rect(24, 23, 6, 8, OUTLINE)
        rect(25, 24, 4, 6, IRON_DARK)
        rect(25, 25, 4, 2, IRON_MAIN)
        rect(26, 26, 2, 2, RIVET)

        # 4. 右侧核心：农村灰铁铲头（x: 28..49, y: 19..34）
        # 外轮廓（左宽肩、右微收圆弧尖刃）
        rect(28, 19, 15, 15, OUTLINE)
        rect(43, 20, 4, 13, OUTLINE)
        rect(47, 22, 2, 9, OUTLINE)
        rect(49, 24, 1, 5, OUTLINE)

        # 铲斗灰色钢铁填充
        rect(29, 20, 14, 13, IRON_MAIN)
        rect(43, 21, 3, 11, IRON_MAIN)
        rect(46, 23, 2, 7, IRON_LIGHT)

        # 铲斗上沿高光边与下沿厚重阴影（形成勺状凹槽立体感）
        rect(29, 20, 14, 2, IRON_LIGHT)
        rect(29, 31, 14, 2, IRON_DARK)
        # 铲斗内部深灰凹槽（金币就盛在这个灰色凹槽里！）
        rect(30, 22, 13, 9, IRON_DARK)
        rect(31, 23, 12, 7, IRON_MID)

        # 最右端磨得发亮的银白圆弧铲尖刃口 (x: 45..49)
        rect(45, 21, 1, 11, IRON_LIGHT)
        rect(46, 22, 2, 9, BLADE_EDGE)
        rect(48, 24, 1, 5, RIVET)

        self._shovel_empty = im
        return im

    def get_shovel_with_coins_in_head(self, angle_deg, coin_count=0):
        """
        获取旋转后的灰铁铲图像。
        重点：当 coin_count > 0 时，圆形小金币直接画在右侧【灰色铁铲头】凹槽 (x: 31..45, y: 17..26) 内，
        然后与灰铁铲一起整体旋转！保证金币 100% 永远在灰色铲子头上，绝不可能跑到左边木把手上！
        """
        q_angle = int(round(angle_deg / 2.0) * 2)
        c_cnt = max(0, min(TOTAL_COINS, int(coin_count)))
        key = (q_angle, c_cnt)
        if key in self._composite_cache:
            return self._composite_cache[key]

        base = self._build_horizontal_grey_shovel().copy()
        if c_cnt > 0:
            coin_img = self._build_coin_grid()
            # 8 粒圆形小金币在右侧【灰色铲子头 (x: 30..45)】内部的精确叠放槽位
            # 从最里面 (x=30) 到最靠近铲尖刃口 (x=41) 排布，倾倒时从最靠铲尖的一粒开始减少！
            head_slots = [
                (30, 21), (33, 22), (31, 17), (36, 21),
                (35, 17), (39, 21), (38, 17), (41, 19),
            ]
            for i in range(c_cnt):
                cx, cy = head_slots[i]
                base.alpha_composite(coin_img, (cx, cy))

        # PIL.rotate 默认逆时针，传入 -q_angle 即为顺时针旋转 q_angle 度：
        # q_angle = 0°   -> 木柄在左，灰色铲子头水平朝右 (盛着金币端着走)
        # q_angle = +40° -> 木柄在左上，灰色铲子头朝右下角倾斜 (顺着红箭头方向把铲头里的金币倒出去！)
        rot = base.rotate(-q_angle, resample=Image.NEAREST, expand=False)
        up = self._upscale(rot)
        self._composite_cache[key] = up
        return up

    def get_blade_tip_offset(self, angle_deg):
        """计算当前旋转角度下，右侧灰色铁铲头尖端 (x=46, y=26 相对中心 27,27 为 dx=+19, dy=-1) 的屏幕坐标偏移"""
        rad = math.radians(angle_deg)
        dx = 19.0 * self.s
        dy = -1.0 * self.s
        wx = dx * math.cos(rad) - dy * math.sin(rad)
        wy = dx * math.sin(rad) + dy * math.cos(rad)
        return wx, wy

    def get_ear_sprite(self, angle_deg=0.0, perk_x=0.0, perk_y=0.0, flare=1.0):
        """
        构建夸张灵动的大耳朵像素精灵图：
        - 软骨结构分明，肉粉色主基调，浅粉高光与深暗红耳蜗
        - 支持耳尖快速微抖 (perk_x, perk_y)、朝左细听偷听、朝右下角偏过去撑开 (flare)、以及角度倾斜 (angle_deg)
        """
        from PIL import ImageDraw
        q_angle = int(round(angle_deg / 1.5) * 1.5)
        q_px = int(round(perk_x))
        q_py = int(round(perk_y))
        q_flare = round(flare, 2)
        key = (q_angle, q_px, q_py, q_flare)
        if key in self._ear_cache:
            return self._ear_cache[key]

        w, h = 54, 54
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(im)

        # 自然温润的人体肉肤色系 (Natural Human Flesh Tone，温和健康舒服！)
        C_OUTLINE = (135, 65, 45, 255)      # 温润柔和的红棕轮廓
        C_FLESH = (248, 196, 160, 255)      # 自然健康的人体肉色主色
        C_LIGHT = (255, 228, 206, 255)      # 白皙柔润肉色高光
        C_SHADOW = (220, 150, 115, 255)     # 自然肉色阴影
        C_CONCHA = (185, 105, 80, 255)      # 耳蜗温润暖褐
        C_RIDGE = (255, 240, 225, 255)      # 软骨柔白亮线
        C_LOBE = (245, 175, 150, 255)       # 耳垂自然健康血色

        tip_x = 18 + q_px
        tip_y = 10 + q_py
        top_x = 28 + q_px * 0.4
        top_y = 8 + q_py * 0.3
        back_x = 34 + (q_flare - 1.0) * 14
        back_y = 22

        poly_outer = [
            (30, 42),
            (35, 36),
            (back_x, back_y),
            (top_x + 4, top_y + 4),
            (top_x, top_y),
            (tip_x, tip_y),
            (tip_x - 3, tip_y + 8),
            (18, 26),
            (23, 34),
            (26, 42),
        ]
        draw.polygon(poly_outer, fill=C_FLESH, outline=C_OUTLINE)

        rim_pts = [
            (tip_x, tip_y),
            (top_x, top_y),
            (top_x + 4, top_y + 4),
            (back_x, back_y)
        ]
        for i in range(len(rim_pts) - 1):
            draw.line([rim_pts[i], rim_pts[i+1]], fill=C_LIGHT, width=2)

        poly_concha = [
            (24, 30),
            (28 + (q_flare - 1.0) * 6, 26),
            (27 + (q_flare - 1.0) * 5, 18),
            (20 + q_px * 0.3, 21),
        ]
        draw.polygon(poly_concha, fill=C_CONCHA, outline=C_SHADOW)
        draw.line([(24, 30), (top_x - 2, 16)], fill=C_RIDGE, width=2)
        draw.ellipse([27, 36, 33, 42], fill=C_LOBE, outline=C_OUTLINE)
        draw.ellipse([23, 31, 27, 35], fill=C_LIGHT, outline=C_SHADOW)

        if q_angle != 0.0:
            im = im.rotate(q_angle, resample=Image.BICUBIC, center=(30, 40))

        scaled = self._upscale(im)
        self._ear_cache[key] = scaled
        return scaled


# ==============================================================================
# 双保险全局回车键监听器 (Low-Level Keyboard Hook + 250Hz Async State Polling)
# ==============================================================================
class ReliableGlobalEnterListener:
    def __init__(self, on_enter_callback):
        self.on_enter_callback = on_enter_callback
        self.enabled = True
        self._last_trigger_ts = 0.0
        self._prev_down = False
        self._start_polling_thread()
        self._start_ll_hook_thread()

    def _fire_if_valid(self):
        if not self.enabled:
            return
        now = time.perf_counter()
        # 只要距离上次触发超过 0.45 秒，无论在什么界面按回车都立即触发！
        if now - self._last_trigger_ts >= 0.45:
            self._last_trigger_ts = now
            try:
                self.on_enter_callback()
            except Exception:
                pass

    def _start_polling_thread(self):
        """250Hz 独立高频轮询线程：同时检测 0x8000 (当前按下) 与 0x0001 (过渡锁存位)"""
        def _loop():
            user32 = ctypes.windll.user32
            # 预先清除历史残留位
            user32.GetAsyncKeyState(0x0D)
            while True:
                time.sleep(0.004)
                try:
                    state = user32.GetAsyncKeyState(0x0D)  # VK_RETURN
                    is_down = (state & 0x8000) != 0
                    was_pressed = (state & 0x0001) != 0
                    if (is_down and not self._prev_down) or (was_pressed and not self._prev_down):
                        self._fire_if_valid()
                    self._prev_down = is_down
                except Exception:
                    pass

        threading.Thread(target=_loop, daemon=True).start()

    def _start_ll_hook_thread(self):
        """Windows WH_KEYBOARD_LL (13) 底层全局键盘钩子：切换任何窗口都能 100% 捕获回车"""
        def _hook_loop():
            try:
                user32 = ctypes.windll.user32
                kernel32 = ctypes.windll.kernel32
                WH_KEYBOARD_LL = 13
                WM_KEYDOWN = 0x0100
                WM_SYSKEYDOWN = 0x0104

                class KBDLLHOOKSTRUCT(ctypes.Structure):
                    _fields_ = [
                        ("vkCode", wintypes.DWORD),
                        ("scanCode", wintypes.DWORD),
                        ("flags", wintypes.DWORD),
                        ("time", wintypes.DWORD),
                        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
                    ]

                HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

                def low_level_handler(nCode, wParam, lParam):
                    if nCode >= 0 and wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                        kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                        if kb.vkCode == 0x0D:  # Enter 键
                            self._fire_if_valid()
                    return user32.CallNextHookEx(None, nCode, wParam, lParam)

                self._hook_proc_ref = HOOKPROC(low_level_handler)
                h_mod = kernel32.GetModuleHandleW(None)
                hook_id = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._hook_proc_ref, h_mod, 0)
                if not hook_id:
                    return

                msg = wintypes.MSG()
                while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
            except Exception:
                pass

        threading.Thread(target=_hook_loop, daemon=True).start()


# ==============================================================================
# 电脑桌面透明底灰铁铲桌宠主程序
# ==============================================================================
class DesktopShovelOverlayApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("农村灰铁铲·显化掘金桌宠")

        self.screen_w = self.root.winfo_screenwidth()
        self.screen_h = self.root.winfo_screenheight()

        self.stage_w = self.screen_w
        self.stage_h = 420
        self.stage_x = 0
        self.stage_y = self.screen_h - self.stage_h - 40

        self.root.geometry(f"{self.stage_w}x{self.stage_h}+{self.stage_x}+{self.stage_y}")
        self.root.overrideredirect(True)
        self.root.wm_attributes("-topmost", True)
        self.root.wm_attributes("-transparentcolor", TRANSPARENT_KEY)
        self.root.configure(bg=TRANSPARENT_KEY)

        self.canvas = tk.Canvas(
            self.root,
            width=self.stage_w,
            height=self.stage_h,
            bg=TRANSPARENT_KEY,
            highlightthickness=0,
            bd=0,
        )
        self.canvas.pack(fill="both", expand=True)

        self.sprites = FinePixelSprites(scale=PIXEL_SCALE)
        self._tk_refs = []

        # 精准对齐你实拍照片里的红圈位置
        self.home_x = max(240, self.stage_w - 260)
        self.home_y = self.stage_h - 155
        self.pour_target_x = self.stage_w - 88
        self.pour_target_y = self.stage_h - 115

        # 双模式核心状态：'work' (赚钱铲子) | 'fish' (八卦摸鱼大耳朵)
        self.mode = "cac"
        self.pending_mode_switch = None

        self.shovel_x = float(self.home_x)
        self.shovel_y = float(self.home_y)
        self.shovel_angle = 18.0
        self.coins_in_shovel_head = 0

        # 大耳朵桌宠姿态变量
        self.ear_x = float(self.home_x)
        self.ear_y = float(self.home_y)
        self.ear_angle = 0.0
        self.ear_perk_x = 0.0
        self.ear_perk_y = 0.0
        self.ear_flare = 1.0
        self.fish_waves = []      # 甩出的暖黄弧线八卦声波 [{x, y, vx, vy, idx, notified}]

        self.state = "idle"
        self.state_time = 0.0
        self.global_time = 0.0

        self.dirt_clods = []
        self.flying_coins = []
        self.sound_flags = set()
        self.released_count = 0
        self.notified_count = 0
        self.bubble_text = ""
        self.bubble_timer = 0.0

        self._dragging = False
        self._drag_offset_x = 0

        self.canvas.bind("<ButtonPress-1>", self._on_mouse_down)
        self.canvas.bind("<B1-Motion>", self._on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_up)
        self.canvas.bind("<Button-3>", self._on_right_click)

        self.menu = tk.Menu(self.root, tearoff=0, bg="#1e293b", fg="#f8fafc", activebackground="#38bdf8", activeforeground="#000")
        self.menu.add_command(label="　 ⛏ 赚钱模式 (掘金落袋)", command=lambda: self.switch_mode("work"))
        self.menu.add_command(label="　 🐟 摸鱼模式 (八卦偷听)", command=lambda: self.switch_mode("fish"))
        self.menu.add_command(label="✔ 👋 唤醒未来的 C啊C (语音联动)", command=lambda: self.switch_mode("cac"))
        self.menu.add_separator()
        self.menu.add_command(label="▶ 立即触发一次 (Enter)", command=self.trigger_active_sequence)
        self.menu.add_command(label="🟢 全局回车键监听: 开启中", command=self.toggle_enter_hook)
        self.menu.add_separator()
        self.menu.add_command(label="✖ 退出桌宠", command=self.root.destroy)

        # 启动双保险全局回车监听器（线程安全投递回主线程）
        self._pending_enter_trigger = False
        self.enter_listener = ReliableGlobalEnterListener(self._on_global_enter_detected)

        self.last_tick = time.perf_counter()
        self._tick()

    def _on_global_enter_detected(self):
        self._pending_enter_trigger = True

    def _is_near_shovel(self, mx, my):
        return abs(mx - self.shovel_x) < 75 and abs(my - self.shovel_y) < 75

    def _on_mouse_down(self, event):
        if self._is_near_shovel(event.x, event.y):
            self._dragging = True
            self._drag_start_x = event.x
            self._drag_start_y = event.y
            self._drag_offset_x = event.x - self.shovel_x
            self._drag_offset_y = event.y - self.shovel_y

    def _on_mouse_drag(self, event):
        if self._dragging and self.state == "idle":
            new_x = max(120, min(self.stage_w - 150, event.x - self._drag_offset_x))
            new_y = max(70, min(self.stage_h - 60, event.y - self._drag_offset_y))
            self.home_x = new_x
            self.home_y = new_y
            self.shovel_x = float(new_x)
            self.shovel_y = float(new_y)

    def _on_mouse_up(self, event):
        if self._dragging:
            moved = math.hypot(
                event.x - getattr(self, "_drag_start_x", event.x),
                event.y - getattr(self, "_drag_start_y", event.y),
            )
            self._dragging = False
            if moved < 6:
                self.trigger_active_sequence()

    def _on_right_click(self, event):
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def toggle_enter_hook(self):
        self.enter_listener.enabled = not self.enter_listener.enabled
        label = "🟢 全局回车键监听: 开启中" if self.enter_listener.enabled else "⚪ 全局回车键监听: 已暂停"
        self.menu.entryconfig(5, label=label)

    def switch_mode(self, target_mode):
        if self.mode == target_mode:
            return
        # 铲子正在倒金币时，切换排在这轮结算后
        if self.mode == "work" and self.state in ("pouring", "celebrating"):
            self.pending_mode_switch = target_mode
            return
        self._apply_mode_switch(target_mode)

    def _apply_mode_switch(self, target_mode):
        self.mode = target_mode
        self.pending_mode_switch = None
        work_label = "✔ ⛏ 赚钱模式 (掘金落袋)" if self.mode == "work" else "　 ⛏ 赚钱模式 (掘金落袋)"
        fish_label = "✔ 🐟 摸鱼模式 (八卦偷听)" if self.mode == "fish" else "　 🐟 摸鱼模式 (八卦偷听)"
        cac_label = "✔ 👋 唤醒未来的 C啊C (语音联动)" if self.mode == "cac" else "　 👋 唤醒未来的 C啊C (语音联动)"
        self.menu.entryconfig(0, label=work_label)
        self.menu.entryconfig(1, label=fish_label)
        self.menu.entryconfig(2, label=cac_label)

        self.state = "idle"
        self.state_time = 0.0
        self.flying_coins.clear()
        self.dirt_clods.clear()
        self.fish_waves.clear()
        self.sound_flags.clear()
        self.bubble_timer = 0.0

        if self.mode == "work":
            self.shovel_x = float(self.home_x)
            self.shovel_y = float(self.home_y)
            self.shovel_angle = 16.0
            self.bubble_text = "切换为：⛏ 赚钱模式"
            self.bubble_timer = 1.0
        else:
            self.ear_x = float(self.home_x)
            self.ear_y = float(self.home_y)
            self.ear_angle = 0.0
            self.ear_perk_x = 0.0
            self.ear_perk_y = 0.0
            self.ear_flare = 1.0
            self.bubble_text = "切换为：🐟 摸鱼模式"
            self.bubble_timer = 1.0
            play_sfx_async("ear_wiggle.wav")

        post_holo_event_async("enter_mode", mode=self.mode)

    def trigger_active_sequence(self):
        if self.mode == "work":
            self.trigger_manifest_sequence()
        elif self.mode == "cac":
            self.bubble_text = "🎙️ 电脑呼叫：“唤醒未来的C啊C”"
            self.bubble_timer = 1.2
            post_holo_event_async("wave", mode="cac")
        else:
            self.trigger_fish_sequence()



    def trigger_fish_sequence(self):
        self.state = "fish_listen"
        self.state_time = 0.0
        self.fish_waves.clear()
        self.sound_flags.clear()
        self.bubble_text = "嘘……隔壁有八卦！"
        self.bubble_timer = 1.15
        play_sfx_async("ear_wiggle.wav")
        # 按下回车第 0 秒立即同步手机全息端，确保手机 100% 呈现泳池边晒太阳小人！
        post_holo_event_async("fish_listen", mode="fish")

    def _spawn_fish_wave(self, wave_idx=1):
        # 从耳廓外沿向右下方甩出暖黄八卦弧线
        self.fish_waves.append({
            "x": self.ear_x + 18,
            "y": self.ear_y + 8,
            "vx": random.uniform(185, 235),
            "vy": random.uniform(115, 145),
            "idx": wave_idx,
            "notified": False,
        })

    # -------------------- 启动掘金序列（随时可触发） --------------------
    def trigger_manifest_sequence(self):
        self.state = "react"
        self.state_time = 0.0
        self.shovel_x = float(self.home_x)
        self.shovel_y = float(self.home_y)
        self.shovel_angle = 15.0
        self.coins_in_shovel_head = 0
        self.dirt_clods.clear()
        self.flying_coins.clear()
        self.sound_flags.clear()
        self.released_count = 0
        self.notified_count = 0
        self.bubble_text = "又干活了，好啊好啊"
        self.bubble_timer = 1.15
        play_sfx_async("recognize.wav")

    def _spawn_dirt_clods(self, cx, cy, count=14):
        cols = ["#78350f", "#92400e", "#a16207", "#57534e"]
        for _ in range(count):
            self.dirt_clods.append({
                "x": cx + random.uniform(-14, 14),
                "y": cy + random.uniform(-4, 4),
                "vx": random.uniform(-90, 90),
                "vy": random.uniform(-165, -65),
                "r": random.choice([3, 4, 5]),
                "col": random.choice(cols),
                "life": random.uniform(0.35, 0.65),
            })

    # -------------------- 每帧物理与状态更新 --------------------
    def _update(self, dt):
        if self._pending_enter_trigger:
            self._pending_enter_trigger = False
            self.trigger_active_sequence()

        self.global_time += dt
        self.state_time += dt
        t = self.state_time

        if self.bubble_timer > 0:
            self.bubble_timer = max(0.0, self.bubble_timer - dt)

        for i in range(len(self.dirt_clods) - 1, -1, -1):
            p = self.dirt_clods[i]
            p["life"] -= dt
            if p["life"] <= 0:
                self.dirt_clods.pop(i)
                continue
            p["vy"] += 460 * dt
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt


        # ==================== 🐟 摸鱼模式待机与偷听状态机 ====================
        if self.mode == "fish":
            # 1. 待机状态：大耳朵轻微呼吸，偶尔轻抖耳尖
            if self.state == "idle":
                breathe = math.sin(self.global_time * 2.8) * 3.0
                self.ear_x = float(self.home_x)
                self.ear_y = float(self.home_y) + breathe
                self.ear_angle = math.sin(self.global_time * 1.5) * 2.0
                # 偶尔快速轻抖两下耳尖
                twitch_window = (self.global_time % 3.6) < 0.22
                if twitch_window:
                    self.ear_perk_x = math.sin(self.global_time * 36.0) * 2.8
                    self.ear_perk_y = -abs(math.sin(self.global_time * 36.0)) * 1.8
                else:
                    self.ear_perk_x = 0.0
                    self.ear_perk_y = 0.0
                self.ear_flare = 1.0

            # 2. 偷听序列 (1.25秒): 耳尖快抖 -> 朝左细听 -> 朝右下偏过去撑开 -> 甩出两道暖黄弧线 -> 软骨回弹
            elif self.state == "fish_listen":
                if t < 0.16:
                    # 耳尖先很快抖一下
                    self.ear_perk_x = math.sin(t * 45.0) * 4.5
                    self.ear_perk_y = -abs(math.sin(t * 45.0)) * 3.0
                    self.ear_angle = 0.0
                    self.ear_flare = 1.0
                elif t < 0.46:
                    # 耳朵朝向电脑左边方向在偷听 (耳廓微收，耳孔朝左)
                    k = (t - 0.16) / 0.30
                    self.ear_angle = k * 18.0
                    self.ear_perk_x = -k * 5.0
                    self.ear_flare = 1.0 - k * 0.12
                    self.ear_x = self.home_x - k * 8.0
                elif t < 0.72:
                    # 耳廓朝右下角偏过去、撑开一点 (像听到隔壁说了什么，耳孔对准手机方向)
                    k = (t - 0.46) / 0.26
                    self.ear_angle = 18.0 - k * 34.0  # +18° -> -16°
                    self.ear_flare = 0.88 + k * 0.40  # 撑开到 1.28
                    self.ear_x = self.home_x - 8.0 + k * 16.0
                    self.ear_y = self.home_y + k * 6.0
                    self.ear_perk_x = 2.0
                elif t < 0.96:
                    # 甩出暖黄弧线推进
                    self.ear_angle = -16.0
                    self.ear_flare = 1.28
                    # 甩出第 1 道波
                    if t >= 0.73 and "wave_1" not in self.sound_flags:
                        self.sound_flags.add("wave_1")
                        play_sfx_async("wave_whoosh.wav")
                        self._spawn_fish_wave(wave_idx=1)
                    # 甩出第 2 道波
                    if t >= 0.86 and "wave_2" not in self.sound_flags:
                        self.sound_flags.add("wave_2")
                        play_sfx_async("wave_whoosh.wav")
                        self._spawn_fish_wave(wave_idx=2)
                else:
                    # 耳朵轻轻回弹，恢复待机 (主要变形在耳尖和耳廓，动作像软骨在动)
                    k = (t - 0.96) / 0.28
                    damping = math.exp(-k * 5.5) * math.sin(k * math.pi * 3.2)
                    self.ear_angle = -16.0 * (1.0 - k) + damping * 6.0
                    self.ear_flare = 1.0 + damping * 0.20
                    self.ear_x = self.home_x + (1.0 - k) * 8.0
                    self.ear_y = self.home_y + (1.0 - k) * 6.0
                    self.ear_perk_x = damping * 3.0

                if t >= 1.25:
                    self.state = "idle"
                    self.state_time = 0.0

            # 推进飞出的暖黄八卦弧线声波
            for i in range(len(self.fish_waves) - 1, -1, -1):
                w = self.fish_waves[i]
                w["x"] += w["vx"] * dt
                w["y"] += w["vy"] * dt
                # 弧线顺着电脑右下角滑出屏幕时通知手机全息端接应
                if (w["x"] >= self.stage_w - 20 or w["y"] >= self.stage_h - 20) and not w["notified"]:
                    w["notified"] = True
                    post_holo_event_async("fish_wave", wave_index=w["idx"], mode="fish")
                    if w["idx"] == 2:
                        self.root.after(220, lambda: post_holo_event_async("fish_relax", mode="fish"))
                if w["x"] > self.stage_w + 35 or w["y"] > self.stage_h + 35:
                    self.fish_waves.pop(i)

            return  # 摸鱼模式跳过赚钱分支

        # ==================== 0. IDLE 待机 ====================
        if self.state == "idle":
            self.shovel_x = float(self.home_x)
            self.shovel_y = self.home_y + math.sin(self.global_time * 3.5) * 4.0
            self.shovel_angle = 16.0 + math.sin(self.global_time * 2.0) * 3.0
            self.coins_in_shovel_head = 0

        # ==================== 1. REACT 轻快回应「又干活了，好啊好啊」(0.40s) ====================
        elif self.state == "react":
            jump = math.sin(min(1.0, t / 0.35) * math.pi) * 12.0
            self.shovel_x = float(self.home_x)
            self.shovel_y = self.home_y - jump
            self.shovel_angle = 12.0 - math.sin(t * 22.0) * 8.0
            if t >= 0.40:
                self.state = "digging"
                self.state_time = 0.0

        # ==================== 2. DIGGING 灰色铲子头插进小土包 -> 挑出圆形小金币 -> 盛进右侧灰色铲头里 (1.15s) ====================
        elif self.state == "digging":
            # 小土包位于铲子右下方（正好对准右侧的灰色铲子头！）
            mound_x = self.home_x + 36
            mound_y = self.home_y + 28

            if t < 0.28:
                # 灰色铲子头向右下倾斜 38°，斜插进小土包
                k = t / 0.28
                self.shovel_x = self.home_x - 6 + k * 14
                self.shovel_y = self.home_y - 8 + k * 22
                self.shovel_angle = 10.0 + k * 32.0
                if k > 0.55 and "dig_sfx" not in self.sound_flags:
                    self.sound_flags.add("dig_sfx")
                    play_sfx_async("dig_dirt.wav")
                    self._spawn_dirt_clods(mound_x, mound_y, count=14)
            elif t < 0.58:
                # 灰色铲子头往上一挑 (从 42° 抬平到 0°)，8粒小圆金币从土包蹦起落向灰色铲子头！
                k = (t - 0.28) / 0.30
                self.shovel_angle = 42.0 * (1.0 - k)
                self.shovel_y = self.home_y + 14 - k * 14
                if "unearth" not in self.sound_flags:
                    self.sound_flags.add("unearth")
                    play_sfx_async("coin_unearth.wav")
                    self._spawn_dirt_clods(mound_x, mound_y, count=16)
                    # 生成 8 粒蹦向灰色铲头正上方的圆形小金币
                    tip_dx, tip_dy = self.sprites.get_blade_tip_offset(0.0)
                    head_cx = self.home_x + 8 + tip_dx - 12
                    head_cy = self.home_y + tip_dy
                    for i in range(TOTAL_COINS):
                        self.flying_coins.append({
                            "x": mound_x + random.uniform(-8, 8),
                            "y": mound_y - 4,
                            "vx": (head_cx - mound_x) * 2.2 + random.uniform(-18, 18),
                            "vy": -155 - (i % 3) * 18,
                            "mode": "into_head",
                        })
            else:
                # 0.58 ~ 1.12s 灰铁铲水平端稳 (angle = 0°，木柄在左、灰色铲头在右)
                self.shovel_angle = 0.0
                self.shovel_x = self.home_x + 8

            # 更新蹦起的小圆金币落进右侧灰色铲子头的过程
            tip_dx, tip_dy = self.sprites.get_blade_tip_offset(self.shovel_angle)
            catch_y = self.shovel_y + tip_dy - 2
            caught_this_frame = False
            for i in range(len(self.flying_coins) - 1, -1, -1):
                fc = self.flying_coins[i]
                if fc["mode"] == "into_head":
                    fc["vy"] += 560 * dt
                    fc["x"] += fc["vx"] * dt
                    fc["y"] += fc["vy"] * dt
                    if fc["vy"] > 0 and fc["y"] >= catch_y and t >= 0.50:
                        self.flying_coins.pop(i)
                        self.coins_in_shovel_head = min(TOTAL_COINS, self.coins_in_shovel_head + 1)
                        caught_this_frame = True

            if caught_this_frame:
                self.shovel_y += 2.5
                if "catch_sfx" not in self.sound_flags:
                    self.sound_flags.add("catch_sfx")
                    play_sfx_async("shovel_catch.wav")

            if t >= 1.12:
                self.flying_coins.clear()
                self.coins_in_shovel_head = TOTAL_COINS
                self.state = "carrying"
                self.state_time = 0.0
                self.carry_start_x = self.shovel_x
                self.carry_start_y = self.shovel_y
                # 提前通知手机全息端准备好小钱袋
                post_holo_event_async("prepare_sack", 1, TOTAL_COINS)

        # ==================== 3. CARRYING 木柄在左、灰色铲头盛着8粒圆金币在右，轻快端到右下角红圈处 (1.25s) ====================
        elif self.state == "carrying":
            dur = 1.25
            prog = min(1.0, t / dur)
            smooth_p = prog * prog * (3.0 - 2.0 * prog)
            self.shovel_x = self.carry_start_x + (self.pour_target_x - self.carry_start_x) * smooth_p
            base_y = self.carry_start_y + (self.pour_target_y - self.carry_start_y) * smooth_p

            # 端着金币轻快颠动，angle 保持在 0° 附近（木柄在左，灰色铲子头盛着金币在右！）
            bob = abs(math.sin(t * math.pi * 5.0)) * 4.5
            self.shovel_y = base_y + bob
            self.shovel_angle = -2.0 + math.sin(t * math.pi * 5.0) * 2.5
            self.coins_in_shovel_head = TOTAL_COINS

            if t >= dur:
                self.state = "pouring"
                self.state_time = 0.0

        # ==================== 4. POURING 右侧灰色铲子头向右下角倾斜，金币一粒粒从灰铲尖滑落掉出屏幕 (1.9s) ====================
        elif self.state == "pouring":
            self.shovel_x = float(self.pour_target_x)
            self.shovel_y = float(self.pour_target_y)

            # 灰色铁铲头从水平 0° 向右下角倾斜到 +46°（顺着红圈箭头方向 ↘ 倒金币！）
            tilt_k = min(1.0, t / 0.40)
            self.shovel_angle = tilt_k * 46.0 + math.sin(t * 18.0) * 1.5

            # 每隔 0.13s，灰色铁铲头里的金币减少 1 粒
            # 从铲斗金币堆位置顺着红线抛物线向右下方喷涌飞出屏幕 (完美贴合用户红线弧度！)
            expected_released = min(TOTAL_COINS, int(max(0.0, t - 0.12) / 0.13) + (1 if t >= 0.12 else 0))
            while self.released_count < expected_released:
                self.released_count += 1
                self.coins_in_shovel_head = max(0, TOTAL_COINS - self.released_count)
                rad = math.radians(self.shovel_angle)
                # 金币堆在铲斗内部 (逻辑坐标 dx=+9, dy=-6) 随铲倾斜后的精准产生点
                heap_dx = (9.0 * self.sprites.s) * math.cos(rad) - (-6.0 * self.sprites.s) * math.sin(rad)
                heap_dy = (9.0 * self.sprites.s) * math.sin(rad) + (-6.0 * self.sprites.s) * math.cos(rad)
                self.flying_coins.append({
                    "x": self.shovel_x + heap_dx,
                    "y": self.shovel_y + heap_dy,
                    # 按照截图红线轨迹：微向上拱起，带着充沛的向右动量划出向右下飞扬的优美抛物线！
                    "vx": random.uniform(145, 195),
                    "vy": random.uniform(-45, -15),
                    "mode": "pouring_out",
                    "notified": False,
                })
                play_sfx_async("pour_slide.wav")

            for i in range(len(self.flying_coins) - 1, -1, -1):
                fc = self.flying_coins[i]
                if fc["mode"] == "pouring_out":
                    # 重力加速度：使向上微拱的抛物线在向右飞出的同时顺滑向右下方弯曲
                    fc["vy"] += 520 * dt
                    fc["x"] += fc["vx"] * dt
                    fc["y"] += fc["vy"] * dt
                    # 当金币顺着红线弧线冲到屏幕右边缘或底部时，通知桌上手机全息端接应！
                    if (fc["x"] >= self.stage_w - 20 or fc["y"] >= self.stage_h - 20) and not fc["notified"]:
                        fc["notified"] = True
                        self.notified_count += 1
                        c_num = self.notified_count
                        post_holo_event_async("drop_coin", c_num, TOTAL_COINS)
                        snd_idx = ((c_num - 1) % 4) + 1
                        self.root.after(280, lambda s=snd_idx: play_sfx_async(f"coin_drop_{s}.wav"))
                    # 飞出画布可视范围后销毁
                    if fc["x"] > self.stage_w + 35 or fc["y"] > self.stage_h + 35:
                        self.flying_coins.pop(i)

            if self.released_count >= TOTAL_COINS and len(self.flying_coins) == 0 and t >= 1.75:
                self.state = "celebrating"
                self.state_time = 0.0
                def _start_celeb():
                    post_holo_event_async("celebrate", TOTAL_COINS, TOTAL_COINS)
                    # 播放经典阳光的普通胜利结算音乐 (彻底去除怪叫的牛马声)
                    play_sfx_async("victory_fanfare.wav")

                self.root.after(260, _start_celeb)

        # ==================== 5. CELEBRATING 入袋完成：收起动画素材，出一行庆祝的字【赚钱啦！！！】 ====================
        elif self.state == "celebrating":
            if t >= 2.2:
                self.state = "idle"
                self.state_time = 0.0
                self.shovel_x = float(self.home_x)
                self.shovel_y = float(self.home_y)
                self.shovel_angle = 16.0
                # 如果用户在倒金币期间请求了切换摸鱼，此时结算完毕立即执行切换
                if self.pending_mode_switch:
                    self._apply_mode_switch(self.pending_mode_switch)

    # -------------------- 画面渲染 --------------------
    def _render(self):
        self.canvas.delete("all")
        self._tk_refs.clear()

        # ---------- 摸鱼模式渲染：大耳朵桌宠 + 甩出暖黄八卦弧线 ----------
        if self.mode == "fish":
            # 1. 绘制大耳朵
            ear_pil = self.sprites.get_ear_sprite(
                angle_deg=self.ear_angle,
                perk_x=self.ear_perk_x,
                perk_y=self.ear_perk_y,
                flare=self.ear_flare,
            )
            ear_tk = ImageTk.PhotoImage(ear_pil)
            self._tk_refs.append(ear_tk)
            self.canvas.create_image(int(self.ear_x), int(self.ear_y), image=ear_tk, anchor="center")

            # 2. 绘制从耳廓甩向右下角滑出屏幕的两道暖黄弧线
            for w in self.fish_waves:
                wx = int(w["x"])
                wy = int(w["y"])
                # 暖黄主弧线
                self.canvas.create_arc(
                    wx - 18, wy - 14, wx + 18, wy + 14,
                    start=-35, extent=80, style="arc",
                    outline="#fde047", width=3
                )
                # 金光晕外弧
                self.canvas.create_arc(
                    wx - 20, wy - 16, wx + 20, wy + 16,
                    start=-38, extent=86, style="arc",
                    outline="#f59e0b", width=1
                )

            # 3. 气泡提示
            if self.bubble_timer > 0 and self.bubble_text:
                bx = int(self.ear_x)
                by = int(self.ear_y - 44)
                pad_w = 72
                x0 = max(10, min(self.stage_w - pad_w * 2 - 10, bx - pad_w))
                x1 = x0 + pad_w * 2
                self.canvas.create_rectangle(x0, by - 12, x1, by + 12, fill="#1e293b", outline="#f43f5e", width=2)
                self.canvas.create_text((x0 + x1) // 2, by, text=self.bubble_text, fill="#fecdd3", font=("Microsoft YaHei UI", 9, "bold"))
            return

        # 电脑端保持纯净桌面，不显示“赚钱啦！！！”文字（手机全息金字塔端显示即可）
        # 庆祝阶段灰铁铲在右下角做轻快喜悦的轻微扬起待机

        # 1. 挖掘阶段绘制小土包（位于右侧灰色铁铲头下方）
        if self.state == "digging":
            mx = int(self.home_x + 36)
            my = int(self.home_y + 30)
            self.canvas.create_oval(mx - 26, my - 7, mx + 26, my + 11, fill="#57534e", outline="#1c1917", width=2)
            self.canvas.create_oval(mx - 22, my - 10, mx + 22, my + 7, fill="#78350f", outline="#1c1917", width=2)
            self.canvas.create_oval(mx - 14, my - 8, mx + 14, my + 3, fill="#92400e", outline="")

        # 2. 绘制飞溅的小圆土坷垃颗粒
        for p in self.dirt_clods:
            r = p["r"]
            self.canvas.create_oval(
                int(p["x"] - r), int(p["y"] - r),
                int(p["x"] + r), int(p["y"] + r),
                fill=p["col"], outline="#1c1917"
            )

        # 3. 绘制农村灰铁铲（含直接盛在右侧灰色铁铲头凹槽里的圆形小金币！）
        shovel_pil = self.sprites.get_shovel_with_coins_in_head(
            self.shovel_angle, coin_count=self.coins_in_shovel_head
        )
        shovel_tk = ImageTk.PhotoImage(shovel_pil)
        self._tk_refs.append(shovel_tk)
        self.canvas.create_image(int(self.shovel_x), int(self.shovel_y), image=shovel_tk, anchor="center")

        # 4. 绘制正在空中蹦向铲头、或正在从右侧灰色铲头尖端往屏幕外滑落的圆形小金币
        if self.flying_coins:
            coin_pil = self.sprites.get_round_coin_upscaled()
            coin_tk = ImageTk.PhotoImage(coin_pil)
            self._tk_refs.append(coin_tk)
            for fc in self.flying_coins:
                self.canvas.create_image(int(fc["x"]), int(fc["y"]), image=coin_tk, anchor="center")

        # 5. 刚触发时显示『又干活了，好啊好啊』
        if self.bubble_timer > 0 and self.bubble_text:
            bx = int(self.shovel_x)
            by = int(self.shovel_y - 46)
            pad_w = 74
            x0 = max(10, min(self.stage_w - pad_w * 2 - 10, bx - pad_w))
            x1 = x0 + pad_w * 2
            y0, y1 = by - 13, by + 13
            self.canvas.create_rectangle(x0, y0, x1, y1, fill="#1e293b", outline="#94a3b8", width=2)
            self.canvas.create_text((x0 + x1) // 2, by, text=self.bubble_text, fill="#fef08a", font=("Microsoft YaHei UI", 9, "bold"))

    def _tick(self):
        now = time.perf_counter()
        dt = min(0.05, now - self.last_tick)
        self.last_tick = now

        self._update(dt)
        self._render()

        self.root.after(16, self._tick)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = DesktopShovelOverlayApp()
    app.run()
