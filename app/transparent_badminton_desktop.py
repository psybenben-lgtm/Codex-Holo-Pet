# -*- coding: utf-8 -*-
"""
《我就赢了 Codex 一球，它竟然开挂了》—— 原生 Windows 全屏透明桌面羽毛球主场景 (DesktopApp)
核心特性：
1. 100% 真实 Windows 桌面透明覆盖层（Win32 WS_EX_LAYERED + LWA_COLORKEY），绝无黑底/白底网页容器框；
2. 双模式丝滑切换：
   - 【日常/拍摄穿透模式】：置顶显示 + Win32 WS_EX_TRANSPARENT 鼠标 100% 穿透，绝不干扰点击桌面图标或窗口；
   - 【编辑校准模式】：支持鼠标左键直接拖拽 Codex 位置、拖拽调整地面高度、拖拽调整真人击球圈与全息入球口、滚轮缩放角色大小 (0.8x~2.5x)；
3. 100% 沿用经典 Codex 地中海微秃、两侧深紫棕卷发、呆萌大黑豆圆眼、微胖短躯干像素原型；
4. 完整呈现 S0~S10 全部动作与微表情：敲代码 → 惊喜看镜头 → 合电脑推沉重桌子擦汗 → 运动包换装与挥拍失衡 → 移动预判挥拍对打 → 扑空摔倒甩飞球拍坐地叹气 → 委屈缩肩偷偷抬眼偷看 → 坏笑掏红灯遥控器叉腰大笑 → 惊愕慢转头盯机器 → 被超大羽毛球正面拍扁贴在电脑屏幕上缓慢滑落 → 趴地按停遥控器 → 尴尬把球拍藏到身后！
"""
import ctypes
from ctypes import wintypes
import json
import logging
import math
from pathlib import Path
import sys
import threading
import time
import tkinter as tk
from urllib.request import ProxyHandler, Request, build_opener
import webbrowser

try:
    import winsound
except ImportError:
    winsound = None

from PIL import Image, ImageDraw, ImageFont, ImageTk

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'app'))

# 确保重定向日志输出在 Windows 控制台下不会因 GBK 编码崩溃
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, 'reconfigure'):
        try:
            _stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

from local_runtime import get_local_host_url, get_no_proxy_opener
from coffee_pet import FONT_LABEL, KEY, draw_codex, draw_cup, draw_desk, draw_outlined_text, ease

HOST = get_local_host_url()
HTTP = get_no_proxy_opener()
AUDIO_DIR = ROOT / 'assets' / 'audio'
SFX_DIR = ROOT / 'sfx'

# Color-key #010102 对应 Win32 COLORREF (0x00BBGGRR = 0x00020101)
COLORREF_KEY = 0x00020101


def play_local_wav(sound_name):
    if not winsound or not sound_name or sound_name == 'silence':
        return
    filename = sound_name if sound_name.endswith('.wav') else f'{sound_name}.wav'
    for folder in (AUDIO_DIR, SFX_DIR, ROOT / 'coffee'):
        path = folder / filename
        if path.is_file():
            try:
                winsound.PlaySound(
                    str(path),
                    winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT
                )
            except Exception:
                pass
            return


def draw_pixel_racket(draw, x, y, angle_rad, scale=1.0, bent=False):
    """绘制像素风精致羽毛球拍（支持任意挥拍角度与 S10 被砸弯变形效果）"""
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)

    def rot(px, py):
        rx = px * scale
        ry = py * scale
        return (round(x + rx * cos_a - ry * sin_a), round(y + rx * sin_a + ry * cos_a))

    # 球拍握柄与中杆
    p_grip0 = rot(0, 0)
    p_grip1 = rot(8, 0)
    p_shaft = rot(20, 2 if bent else 0)
    draw.line([p_grip0, p_grip1], fill='#1e293b', width=max(2, round(3 * scale)))
    draw.line([p_grip1, p_shaft], fill='#cbd5e1', width=max(1, round(2 * scale)))

    # 拍框椭圆多边形
    head_cx = 31
    head_cy = 5 if bent else 0
    rx, ry = (11, 7) if not bent else (10, 8)
    pts_outer = []
    pts_inner = []
    for i in range(12):
        a = i * math.tau / 12
        pts_outer.append(rot(head_cx + math.cos(a) * rx, head_cy + math.sin(a) * ry))
        pts_inner.append(rot(head_cx + math.cos(a) * (rx - 2), head_cy + math.sin(a) * (ry - 2)))

    draw.polygon(pts_outer, fill='#ef4444', outline='#111118')
    draw.polygon(pts_inner, fill=KEY)
    # 白色十字球网线
    for off in (-4, 0, 4):
        draw.line([rot(head_cx + off, head_cy - ry + 2), rot(head_cx + off, head_cy + ry - 2)], fill='#f8fafc', width=1)
    for off in (-3, 0, 3):
        draw.line([rot(head_cx - rx + 2, head_cy + off), rot(head_cx + rx - 2, head_cy + off)], fill='#f8fafc', width=1)


def draw_pixel_shuttlecock(draw, x, y, angle_rad, scale=1.0, speed_lines=False, is_giant=False):
    """
    绘制具有真实重量感、球头朝向与羽毛裙摆的像素羽毛球 (Section 6.2)：
    支持飞行旋转、速度线、以及 S9 超大号反噬羽毛球！
    """
    s = scale * 1.35
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)

    def rot(px, py):
        rx = px * s
        ry = py * s
        return (round(x + rx * cos_a - ry * sin_a), round(y + rx * sin_a + ry * cos_a))

    # 高速扣杀或超大球破风速度线
    if speed_lines:
        for i in range(-1, 2):
            p0 = rot(-14, i * 5)
            p1 = rot(-30 - abs(i) * 6, i * 6)
            line_col = '#facc15' if is_giant else '#e0f2fe'
            draw.line([p0, p1], fill=line_col, width=max(1, round(2 * s)))

    # 白色梯形羽毛裙摆（朝向运动反方向 -X）
    skirt = [rot(-2, -3), rot(-14, -8), rot(-12, 0), rot(-14, 8), rot(-2, 3)]
    draw.polygon(skirt, fill='#ffffff', outline='#1e293b')
    # 羽毛分叉纹理与红色绑线
    draw.line([rot(-3, -4), rot(-3, 4)], fill='#ef4444', width=max(1, round(1.8 * s)))
    draw.line([rot(-2, 0), rot(-13, -4)], fill='#cbd5e1', width=1)
    draw.line([rot(-2, 0), rot(-13, 4)], fill='#cbd5e1', width=1)

    # 半球形软木球头（朝向运动正方向 +X）
    cork = [rot(-2, -4), rot(4, -4), rot(7, 0), rot(4, 4), rot(-2, 4)]
    cork_col = '#fde047' if is_giant else '#fef3c7'
    draw.polygon(cork, fill=cork_col, outline='#0f172a')
    if is_giant:
        # 超大反噬羽毛球自带愤怒红光环与压迫感纹路
        draw.line([rot(1, -2), rot(4, 0), rot(1, 2)], fill='#dc2626', width=max(2, round(1.5 * s)))


def draw_badminton_codex(draw, cx, cy, t, char_state, scale=1.6):
    """
    绘制 100% 原版 Codex 地中海微秃像素小人的全套羽毛球动作与微表情 (Section 3, 7, 8)：
    保持经典地中海微秃头顶 (#d99a88)、两侧深紫棕卷发 (#392e48/#63506b)、呆萌大黑豆圆眼与微胖短躯干！
    """
    pose = char_state.get('pose', 'ready_wait')
    outfit = char_state.get('outfit', 'sport')
    facing = int(char_state.get('facing', -1))
    has_racket = bool(char_state.get('has_racket', True))
    racket_dropped = bool(char_state.get('racket_dropped', False))
    remote_vis = bool(char_state.get('remote_visible', False))

    # 特殊状态：S9 被超大羽毛球正面击中，贴在电脑屏幕上形成扁平大饼形变并缓慢滑落！
    if pose == 'screen_pancake':
        sp = float(char_state.get('screen_splat_progress', 0.0))
        slide_y = max(0.0, (sp - 0.45) * 85.0) * scale
        px = round(cx)
        py = round(cy - 45 * scale + slide_y)
        s = scale * 1.45

        # 贴在屏幕玻璃上的压扁四肢大字形剪影
        draw.ellipse((px - round(26 * s), py - round(16 * s), px + round(26 * s), py + round(22 * s)),
                     fill='#e0f2fe', outline='#38bdf8')  # 玻璃贴合白印水汽
        # 压扁的蓝白运动服大饼躯干与四肢
        for ax, ay in ((-22, -12), (22, -12), (-20, 18), (20, 18)):
            draw.line([(px, py + round(4 * s)), (px + round(ax * s), py + round(ay * s))],
                      fill='#f8fafc', width=max(4, round(7 * s)))
            draw.ellipse((px + round((ax - 4) * s), py + round((ay - 4) * s),
                          px + round((ax + 4) * s), py + round((ay + 4) * s)), fill='#efb294', outline='#211c2c')
        draw.ellipse((px - round(16 * s), py - round(6 * s), px + round(16 * s), py + round(14 * s)),
                     fill='#38bdf8', outline='#1e293b')
        # 压扁贴在屏幕玻璃上的大脸与地中海两侧卷发
        draw.ellipse((px - round(18 * s), py - round(24 * s), px + round(18 * s), py - round(2 * s)),
                     fill='#392e48', outline='#211c2c')
        draw.ellipse((px - round(14 * s), py - round(21 * s), px + round(14 * s), py - round(1 * s)),
                     fill='#efb294', outline='#211c2c')
        # 贴在玻璃上压扁的鼻子和脸颊红晕
        draw.ellipse((px - round(4 * s), py - round(12 * s), px + round(4 * s), py - round(7 * s)), fill='#f472b6')
        # 蚊香眩晕大黑豆眼 (@ @)
        draw.ellipse((px - round(10 * s), py - round(16 * s), px - round(4 * s), py - round(10 * s)), fill='#111118')
        draw.ellipse((px + round(4 * s), py - round(16 * s), px + round(10 * s), py - round(10 * s)), fill='#111118')
        draw.point((px - round(7 * s), py - round(13 * s)), fill='#ffffff')
        draw.point((px + round(7 * s), py - round(13 * s)), fill='#ffffff')
        draw_outlined_text(draw, px - 22, py - round(36 * s), 'codex (SPLAT!)', fill='#fde047', outline='#080909')
        return

    # 我们在独立小画布上绘制标准比例像素小人，再按 scale 进行 NEAREST 像素级无损放大
    w_box, h_box = 110, 96
    ox, oy = 55, 80
    sprite = Image.new('RGBA', (w_box, h_box), (0, 0, 0, 0))
    g = ImageDraw.Draw(sprite)

    def rect(x1, y1, x2, y2, col):
        a, b = sorted((ox + facing * x1, ox + facing * x2))
        c, d = sorted((oy + y1, oy + y2))
        g.rectangle((round(a), round(c), round(b), round(d)), fill=col)

    def poly(pts, col):
        g.polygon([(round(ox + facing * px), round(oy + py)) for px, py in pts], fill=col)

    # 脚底轻微接触阴影 (Section 2.1)
    g.ellipse((ox - 16, oy - 2, ox + 16, oy + 4), fill=(20, 24, 38, 255))

    # 动作位移与姿态参数计算
    bob = 0
    lean = 0
    step = 0
    racket_angle = -0.65
    rx_hand, ry_hand = 13, -22
    lx_hand, ly_hand = -11, -19

    if pose == 'invite_surprise':
        bob = -round(abs(math.sin(t * 10)) * 4)
        ry_hand = -30
    elif pose == 'close_laptop':
        lean = 3
        rx_hand, ry_hand = 15, -20
    elif pose == 'push_strain_still':
        # 桌子很沉先不动：身体大幅前倾，双脚死死蹬地，全身微微发抖
        lean = 6 + round(math.sin(t * 35))
        bob = 3
        rx_hand, ry_hand = 18, -22
        lx_hand, ly_hand = 16, -19
    elif pose == 'push_desk_move':
        lean = 5
        step = int(t * 12) % 4 - 2
        bob = abs(step)
        rx_hand, ry_hand = 18, -22
    elif pose == 'wipe_sweat_clap':
        bob = round(math.sin(t * 8) * 1.5)
        rx_hand, ry_hand = 10, -40  # 抬手擦额头汗水
    elif pose == 'spin_change':
        bob = -round(abs(math.sin(t * 14)) * 7)
        facing = 1 if int(t * 16) % 2 == 0 else -1
    elif pose == 'warmup_wobble':
        # 热身挥拍两下，第二下用力过猛差点失去平衡！
        sub = (t * 1.3) % 1.0
        if sub < 0.45:
            racket_angle = -1.4 + math.sin(sub / 0.45 * math.tau) * 1.3
            rx_hand, ry_hand = 15, -26
        else:
            # 挥得太猛单脚翘起身体后仰晃悠
            lean = -5 + round(math.sin(t * 22) * 3)
            bob = 2
            step = 5
            racket_angle = 0.8 + math.sin(t * 20) * 0.4
            rx_hand, ry_hand = 17, -16
            lx_hand, ly_hand = -16, -30
    elif pose in ('shy_ready', 'ready_wait'):
        bob = round(math.sin(t * 5) * 1.2)
        racket_angle = -0.75 + math.sin(t * 4) * 0.12
        rx_hand, ry_hand = 14, -24
    elif pose in ('move_anticipate', 'move_run', 'panic_run'):
        freq = 18 if pose == 'panic_run' else 12
        step = round(math.sin(t * freq) * 4)
        bob = abs(step) // 2
        lean = 4 if pose == 'panic_run' else 2
        racket_angle = -0.35 if pose != 'panic_run' else -1.2
    elif pose == 'hit_swing':
        # 快速挥拍击球与自然收拍
        swing_p = char_state.get('swing_progress', min(1.0, (t * 4.5) % 1.0))
        racket_angle = -1.8 + swing_p * 2.9
        rx_hand, ry_hand = 16, -28 + round(swing_p * 8)
        bob = -2 if swing_p < 0.4 else 1
    elif pose == 'rally_angry':
        lean = 2
        rx_hand, ry_hand = 14, -30
        lx_hand, ly_hand = -11, -17
        bob = -round(abs(math.sin(t * 14)) * 2)
    elif pose == 'rally_tired':
        lean = 2
        rx_hand, ry_hand = 12, -14
        lx_hand, ly_hand = -9, -14
        bob = 3 + round(math.sin(t * 8))
    elif pose == 'dive_fall':
        # S5 扑空摔倒坐在地上，低头小小叹气
        bob = 10
        lean = -2
    elif pose in ('sit_pity', 'pity_peek'):
        # S6 缩着肩膀委屈，偷偷抬眼偷看用户
        bob = 7
        lean = 2
        rx_hand, ry_hand = 9, -18
    elif pose == 'evil_remote':
        # S7 掏出红灯小遥控器坏笑
        bob = 1
        rx_hand, ry_hand = 15, -24
    elif pose == 'cheat_laugh':
        # S7 双手叉腰得意大笑
        bob = round(math.sin(t * 16) * 2)
        lean = -2
        rx_hand, ry_hand = 11, -18
        lx_hand, ly_hand = -11, -18
    elif pose in ('slow_turn_to_holo', 'laugh_to_shock', 'panic_freeze'):
        # S8 笑声停止，慢慢转头盯着失控的发球机
        bob = 0
        lean = -1
        rx_hand, ry_hand = 12, -22
    elif pose == 'floor_press_stop':
        # S9 趴在地上狼狈伸出一只手按下遥控器停止键
        bob = 13
        lean = 8
        rx_hand, ry_hand = 22, -6
    elif pose == 'awkward_hide_racket':
        # S10 尴尬地把球拍藏到身后
        bob = round(math.sin(t * 4) * 1)
        lean = -1
        rx_hand, ry_hand = -10, -18  # 藏在身后

    # 1. 如果球拍脱手掉在地上 (S5 输球摔倒)
    if racket_dropped:
        draw_pixel_racket(g, ox + facing * 32, oy - 2, 0.25, scale=0.85)

    # 2. 如果 S10 尴尬地把球拍藏在身后（先画在身体后层）
    if pose == 'awkward_hide_racket' and has_racket:
        draw_pixel_racket(g, ox - facing * 10, oy - 20 + bob, 2.3, scale=0.85, bent=True)

    # 3. 绘制双腿与鞋子（保持原版微胖短腿比例）
    if pose in ('dive_fall', 'sit_pity', 'pity_peek', 'floor_press_stop'):
        # 坐在地上或趴在地上伸出的短腿
        rect(2, -8, 15, -1, '#1e3a8a' if outfit == 'sport' else '#363751')
        rect(13, -9, 18, -1, '#f8fafc' if outfit == 'sport' else '#987582')
        rect(-10, -7, 1, -1, '#1e293b')
    else:
        leg_col1 = '#1e3a8a' if outfit == 'sport' else '#363751'
        leg_col2 = '#1d4ed8' if outfit == 'sport' else '#4a435c'
        shoe_col = '#f8fafc' if outfit == 'sport' else '#987582'
        rect(-6, -11 + bob, -1, -2 + step, leg_col1)
        rect(2, -11 + bob, 7, -2 - step, leg_col2)
        rect(-8, -3 + step, -1, -1 + step, shoe_col)
        rect(2, -3 - step, 9, -1 - step, shoe_col)
        if outfit == 'sport':
            # 小运动鞋红色条纹
            rect(-7, -2 + step, -2, -2 + step, '#ef4444')
            rect(3, -2 - step, 8, -2 - step, '#ef4444')

    # 4. 绘制微胖短躯干（日常蓝衬衫 vs 蓝白红运动球衣）
    if outfit == 'sport':
        poly([
            (-9 + lean, -26 + bob), (-5 + lean, -30 + bob), (7 + lean, -30 + bob),
            (11 + lean, -26 + bob), (10 + lean, -10 + bob), (-8 + lean, -10 + bob)
        ], '#f8fafc')  # 清爽白色运动球衣
        rect(-7 + lean, -28 + bob, 7 + lean, -24 + bob, '#0284c7')   # 活力天蓝肩袖拼色
        rect(-8 + lean, -15 + bob, 9 + lean, -10 + bob, '#1e3a8a')   # 深蓝运动短裤腰边
        rect(-5 + lean, -22 + bob, 5 + lean, -20 + bob, '#ef4444')   # 胸前红色运动横纹
    else:
        poly([
            (-9 + lean, -26 + bob), (-5 + lean, -30 + bob), (7 + lean, -30 + bob),
            (11 + lean, -26 + bob), (10 + lean, -10 + bob), (-8 + lean, -10 + bob)
        ], '#566f9b')
        rect(-7 + lean, -27 + bob, 7 + lean, -24 + bob, '#85a8c3')
        rect(-7 + lean, -13 + bob, 9 + lean, -11 + bob, '#3e537b')

    # 5. 后侧手臂
    rect(lx_hand - 2, ly_hand - 7 + bob, lx_hand + 2, ly_hand + bob, '#38bdf8' if outfit == 'sport' else '#7896b9')
    rect(lx_hand - 2, ly_hand - 1 + bob, lx_hand + 2, ly_hand + 2 + bob, '#e5ad8b')

    # 6. 头部与经典地中海卷发 + 呆萌大黑豆圆眼 + 戏剧微表情
    hy = -30 + bob
    hx = lean
    # 地中海两侧深紫棕卷发（100% 沿用 coffee_pet.py 原型几何）
    poly([
        (hx - 10, hy - 13), (hx - 6, hy - 17), (hx + 5, hy - 17), (hx + 10, hy - 13),
        (hx + 11, hy - 5), (hx + 7, hy), (hx - 7, hy), (hx - 11, hy - 5)
    ], '#392e48')
    poly([
        (hx - 8, hy - 12), (hx - 5, hy - 15), (hx + 5, hy - 15),
        (hx + 9, hy - 12), (hx + 8, hy - 9), (hx - 9, hy - 8)
    ], '#63506b')
    # 地中海微秃发旋与双耳
    rect(hx - 5, hy - 15, hx + 3, hy - 14, '#9e7080')
    rect(hx - 10, hy - 8, hx - 8, hy - 4, '#d99a88')
    rect(hx + 8, hy - 8, hx + 10, hy - 4, '#e1a589')

    # 运动装时戴一条利落的红白运动发带（依然清晰露出上方微秃发旋与两侧卷发！）
    if outfit == 'sport':
        rect(hx - 10, hy - 12, hx + 10, hy - 10, '#ef4444')
        rect(hx - 6, hy - 12, hx + 6, hy - 11, '#ffffff')

    # 面部轮廓
    poly([
        (hx + 1, hy - 10), (hx + 8, hy - 11), (hx + 11, hy - 7),
        (hx + 13, hy - 5), (hx + 10, hy - 2), (hx + 2, hy - 2)
    ], '#e9b296')

    # 根据剧情状态绘制灵动微表情
    if char_state.get('front'):
        poly([(-8+hx,hy-10), (8+hx,hy-10), (9+hx,hy-3), (5+hx,hy),
              (-6+hx,hy), (-9+hx,hy-4)], '#e9b296')
        for ex in (-5, 3):
            rect(hx+ex,hy-7,hx+ex+2,hy-5,'#161221')
            rect(hx+ex,hy-7,hx+ex,hy-7,'#fff5ea')
        if pose == 'rally_angry':
            poly([(-7+hx,hy-10),(-2+hx,hy-8),(-2+hx,hy-7),(-7+hx,hy-9)], '#462f40')
            poly([(7+hx,hy-10),(2+hx,hy-8),(2+hx,hy-7),(7+hx,hy-9)], '#462f40')
            rect(hx-3,hy-3,hx+3,hy-1,'#8d3b4e')
            rect(hx-7,hy-4,hx-5,hy-3,'#d97873')
            rect(hx+5,hy-4,hx+7,hy-3,'#d97873')
        elif pose == 'rally_tired':
            rect(hx-2,hy-3,hx+2,hy-1,'#884958')
            rect(hx+9,hy-10,hx+10,hy-7,'#72def6')
        else:
            rect(hx-2,hy-3,hx+2,hy-2,'#aa6165')
    elif pose == 'dive_fall':
        # S5 输球低头叹气：闭眼 + 白色小叹气像素团
        rect(hx + 6, hy - 6, hx + 9, hy - 6, '#392e48')
        rect(hx + 8, hy - 3, hx + 10, hy - 2, '#6c3d47')
        if int(t * 4) % 2 == 0:
            g.ellipse((ox + facing * (hx + 16) - 3, oy + hy - 6, ox + facing * (hx + 16) + 3, oy + hy - 2),
                      fill=(226, 232, 240, 220))
    elif pose == 'sit_pity':
        # S6 假装委屈：眼角下垂 + 委屈瘪嘴
        rect(hx + 6, hy - 7, hx + 8, hy - 5, '#111118')
        rect(hx + 5, hy - 8, hx + 8, hy - 8, '#392e48')
        rect(hx + 7, hy - 3, hx + 9, hy - 3, '#6c3d47')
    elif pose == 'pity_peek':
        # S6 【核心细节】偷偷抬起一只大黑豆眼确认用户有没有心软！
        rect(hx + 5, hy - 8, hx + 10, hy - 4, '#ffffff')
        rect(hx + 7, hy - 8, hx + 10, hy - 5, '#09090d')
        rect(hx + 8, hy - 8, hx + 8, hy - 8, '#ffffff')  # 狡黠眼神高光
        rect(hx + 7, hy - 3, hx + 10, hy - 3, '#b57473')
    elif pose in ('evil_remote', 'cheat_laugh'):
        # S7 偷偷坏笑 / 叉腰大笑：斜飞坏笑眉 + 大黑豆眼 + 咧嘴坏笑
        rect(hx + 6, hy - 7, hx + 9, hy - 5, '#09090d')
        g.line([(ox + facing * (hx + 5), oy + hy - 9), (ox + facing * (hx + 10), oy + hy - 7)], fill='#111118', width=1)
        rect(hx + 6, hy - 4, hx + 11, hy - 2, '#991b1b')
        rect(hx + 7, hy - 4, hx + 10, hy - 3, '#ffffff')  # 露出坏笑白牙
    elif pose in ('slow_turn_to_holo', 'laugh_to_shock', 'panic_freeze', 'panic_run'):
        # S8 / S9 发现机器不对劲 / 惊恐瞪眼流冷汗
        rect(hx + 5, hy - 8, hx + 10, hy - 4, '#ffffff')
        rect(hx + 7, hy - 7, hx + 9, hy - 5, '#09090d')
        rect(hx + 7, hy - 3, hx + 10, hy - 1, '#450a0a')
        rect(hx + 1, hy - 9, hx + 2, hy - 5, '#38bdf8')  # 额角冷汗
    elif pose == 'awkward_hide_racket':
        # S10 尴尬而不失礼貌的微笑 + 额角大汗珠
        rect(hx + 6, hy - 7, hx + 8, hy - 5, '#09090d')
        rect(hx + 6, hy - 3, hx + 10, hy - 3, '#b57473')
        rect(hx + 3, hy - 5, hx + 5, hy - 4, '#f472b6')  # 脸红
        rect(hx + 1, hy - 10, hx + 3, hy - 5, '#38bdf8') # 尴尬大汗珠
    else:
        # 经典呆萌大黑豆圆眼
        rect(hx + 7, hy - 7, hx + 9, hy - 5, '#111118')
        rect(hx + 7, hy - 7, hx + 7, hy - 7, '#ffffff')
        rect(hx + 8, hy - 3, hx + 10, hy - 3, '#b57473')

    # 7. 前侧手臂与手持道具（羽毛球拍 / 作弊小遥控器 / 汗水）
    poly([
        (7 + lean, -25 + bob), (10 + lean, -25 + bob),
        (rx_hand + 1, ry_hand + bob), (rx_hand - 2, ry_hand + 2 + bob)
    ], '#38bdf8' if outfit == 'sport' else '#80a3bf')
    rect(rx_hand - 2, ry_hand - 2 + bob, rx_hand + 2, ry_hand + 2 + bob, '#e5ad8b')

    if has_racket and not racket_dropped and pose != 'awkward_hide_racket':
        hand_screen_x = ox + facing * rx_hand
        hand_screen_y = oy + ry_hand + bob
        actual_ang = racket_angle if facing == 1 else (math.pi - racket_angle)
        draw_pixel_racket(g, hand_screen_x, hand_screen_y, actual_ang, scale=0.92)

    if remote_vis and pose in ('evil_remote', 'cheat_laugh', 'slow_turn_to_holo', 'floor_press_stop'):
        # S7~S9 手里拿着带红色发光天线的小黑遥控器
        rem_x = rx_hand + 3
        rem_y = ry_hand - 3 + bob
        rect(rem_x - 2, rem_y - 4, rem_x + 3, rem_y + 3, '#1e293b')
        rect(rem_x, rem_y - 7, rem_x + 1, rem_y - 4, '#94a3b8')
        if int(t * 10) % 2 == 0 or pose == 'evil_remote':
            rect(rem_x - 1, rem_y - 9, rem_x + 2, rem_y - 7, '#ef4444')  # 闪烁红灯

    if pose in ('push_strain_still', 'push_desk_move', 'wipe_sweat_clap'):
        # 吃力推桌子时的汗珠飞溅
        rect(hx - 2, hy - 9, hx, hy - 6, '#38bdf8')

    # 将绘制好的小人按 scale 像素级无损放大贴到主画布
    sw = max(16, round(w_box * scale))
    sh = max(16, round(h_box * scale))
    scaled_sprite = sprite.resize((sw, sh), Image.Resampling.NEAREST)
    paste_x = round(cx - ox * scale)
    paste_y = round(cy - oy * scale)
    draw._image.paste(scaled_sprite, (paste_x, paste_y), scaled_sprite)

    # 头顶清晰黄色黑边 codex 名字
    if not char_state.get('hide_name'):
        draw_outlined_text(draw, round(cx - 18), round(cy - 64 * scale), 'codex', fill='#ffdc38', outline='#080909')


class TransparentBadmintonDesktop:
    """
    Windows 全屏透明羽毛球主场景覆盖窗 + 右下角迷你控制胶囊条
    """
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('Codex 透明桌面羽毛球互动层')
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.attributes('-transparentcolor', KEY)
        self.root.config(background=KEY)

        # 获取主屏幕工作区尺寸
        area = wintypes.RECT()
        ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(area), 0)
        self.screen_w = max(800, area.right - area.left)
        self.screen_h = max(500, area.bottom - area.top)

        # 为了保证 60fps 极速渲染且不卡顿，内部采用 1/2 分辨率像素画布并放大或直接按逻辑坐标绘制
        self.logical_w = 640
        self.logical_h = 360
        self.root.geometry(f'{self.screen_w}x{self.screen_h}+{area.left}+{area.top}')

        self.canvas = tk.Canvas(
            self.root, width=self.screen_w, height=self.screen_h,
            bg=KEY, highlightthickness=0, bd=0
        )
        self.canvas.pack(fill='both', expand=True)
        self.sprite_item = self.canvas.create_image(0, 0, anchor='nw')

        # 绑定编辑模式下的鼠标拖拽与滚轮缩放事件
        self.drag_target = None
        self.canvas.bind('<ButtonPress-1>', self.on_mouse_down)
        self.canvas.bind('<B1-Motion>', self.on_mouse_drag)
        self.canvas.bind('<ButtonRelease-1>', self.on_mouse_up)
        self.canvas.bind('<MouseWheel>', self.on_mouse_wheel)

        # 先显示窗口并完成初始化，再获取顶层 HWND 设置 Win32 透明穿透属性（彻底杜绝之前黑屏或泥巴不显示的 Bug！）
        self.root.deiconify()
        self.root.update_idletasks()
        self.user32 = ctypes.windll.user32
        self.user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        self.user32.GetAncestor.restype = wintypes.HWND
        self.user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
        self.user32.SetLayeredWindowAttributes.argtypes = [wintypes.HWND, wintypes.DWORD, wintypes.BYTE, wintypes.DWORD]

        self.hwnd = self.user32.GetAncestor(self.root.winfo_id(), 2)
        self.edit_mode = False
        self._apply_window_passthrough(passthrough=True)

        # 创建右下角迷你悬浮控制条窗口（独立 Toplevel，始终可点击，用于一键「陪我打球」、切换「穿透/编辑位置」、呼出导演台）
        self._create_floating_bar(area)

        self.state = None
        self.initial_close_seq = None
        self.played_audio_ids = set()
        self.closed = threading.Event()
        self.anim_origin = time.monotonic()

        threading.Thread(target=self._sync_loop, daemon=True).start()
        self.root.after(20, self.tick)

    def _apply_window_passthrough(self, passthrough=True):
        if not self.hwnd:
            return
        ex_style = self.user32.GetWindowLongW(self.hwnd, -20)
        # WS_EX_LAYERED (0x80000) | WS_EX_TOOLWINDOW (0x80) | WS_EX_NOACTIVATE (0x08000000)
        base_flags = ex_style | 0x00080000 | 0x00000080 | 0x08000000
        if passthrough:
            new_style = base_flags | 0x00000020  # + WS_EX_TRANSPARENT (鼠标点击 100% 穿透到底层桌面)
        else:
            new_style = base_flags & (~0x00000020)  # 移除穿透，允许直接拖拽角色与地面线
        self.user32.SetWindowLongW(self.hwnd, -20, new_style)
        # 显式锁定 LWA_COLORKEY (0x1)，确保 #010102 永远 100% 透明
        self.user32.SetLayeredWindowAttributes(self.hwnd, COLORREF_KEY, 255, 0x1)

    def _create_floating_bar(self, area):
        self.bar = tk.Toplevel(self.root)
        self.bar.title('Codex 羽毛球控制条')
        self.bar.overrideredirect(True)
        self.bar.attributes('-topmost', True)
        self.bar.config(bg='#0f172a')

        frame = tk.Frame(self.bar, bg='#0f172a', highlightbackground='#38bdf8', highlightthickness=1)
        frame.pack(fill='both', expand=True)

        # 左侧拖动手柄：防止右下角被系统通知遮挡时无法移动
        grip = tk.Label(frame, text='⋮⋮', bg='#1e293b', fg='#94a3b8', font=('Microsoft YaHei', 9, 'bold'), padx=6, cursor='fleur')
        grip.pack(side='left', fill='y', padx=(2, 3), pady=2)
        drag_offset = {'x': 0, 'y': 0}

        def _bar_drag_start(e):
            drag_offset['x'] = e.x_root - self.bar.winfo_x()
            drag_offset['y'] = e.y_root - self.bar.winfo_y()

        def _bar_drag_move(e):
            nx = max(0, e.x_root - drag_offset['x'])
            ny = max(0, e.y_root - drag_offset['y'])
            self.bar.geometry(f'+{nx}+{ny}')

        grip.bind('<ButtonPress-1>', _bar_drag_start)
        grip.bind('<B1-Motion>', _bar_drag_move)

        btn_style = {'font': ('Microsoft YaHei', 9, 'bold'), 'bd': 0, 'padx': 8, 'pady': 4, 'cursor': 'hand2'}
        tk.Button(frame, text='🏸 陪我打球', bg='#f59e0b', fg='#090d16',
                  command=lambda: self._api_post('start_play', {}), **btn_style).pack(side='left', padx=3, pady=4)
        tk.Button(frame, text='👋 挥拍击球', bg='#16a34a', fg='#ffffff',
                  command=lambda: self._api_post('manual_swing', {'power': 35}), **btn_style).pack(side='left', padx=3, pady=4)
        self.mode_btn = tk.Button(frame, text='🔓 调整位置/大小', bg='#0284c7', fg='#ffffff',
                                  command=self.toggle_edit_mode, **btn_style)
        self.mode_btn.pack(side='left', padx=3, pady=4)
        tk.Button(frame, text='🎬 导演与动捕台', bg='#7e22ce', fg='#ffffff',
                  command=lambda: webbrowser.open(HOST + '/badminton/director'), **btn_style).pack(side='left', padx=3, pady=4)
        tk.Button(frame, text='🏠 日常', bg='#334155', fg='#fde047',
                  command=lambda: self._api_post('jump_scene', {'scene_id': 'S0'}), **btn_style).pack(side='left', padx=3, pady=4)
        tk.Button(frame, text='⏻ 全部退出', bg='#991b1b', fg='#fecaca',
                  command=self.shutdown_all, **btn_style).pack(side='right', padx=(3, 4), pady=4)
        tk.Button(frame, text='✕ 关闭桌面', bg='#ef4444', fg='#ffffff',
                  command=self.close, **btn_style).pack(side='right', padx=3, pady=4)

        # 按控件实际请求尺寸自适应定位，彻底避免高 DPI 下右侧关闭按钮被裁剪
        self.bar.update_idletasks()
        bw = max(560, frame.winfo_reqwidth() + 4)
        bh = max(40, frame.winfo_reqheight() + 4)
        bx = max(10, area.right - bw - 16)
        by = max(10, area.bottom - bh - 12)
        self.bar.geometry(f'{bw}x{bh}+{bx}+{by}')

    def shutdown_all(self):
        def _send_and_exit():
            try:
                req = Request(f'{HOST}/api/system/shutdown', b'{}', {'Content-Type': 'application/json'})
                with HTTP.open(req, timeout=0.8) as _:
                    pass
            except Exception:
                pass
            self.root.after(0, self.close)

        threading.Thread(target=_send_and_exit, daemon=True).start()

    def toggle_edit_mode(self):
        self.edit_mode = not self.edit_mode
        self._apply_window_passthrough(passthrough=not self.edit_mode)
        if self.edit_mode:
            self.mode_btn.config(text='🔒 锁定穿透模式', bg='#dc2626')
        else:
            self.mode_btn.config(text='🔓 调整位置/大小', bg='#0284c7')
        self._api_post('update_params', {'court': {'desktop_edit_mode': self.edit_mode}})

    def on_mouse_down(self, event):
        if not self.edit_mode or not self.state:
            return
        rx = event.x / self.screen_w
        ry = event.y / self.screen_h
        court = self.state.get('court', {})
        cx = court.get('codex_home_x_ratio', 0.68)
        gy = court.get('ground_y_ratio', 0.82)
        hx = court.get('human_zone_x_ratio', 0.24)
        hy = court.get('human_zone_y_ratio', 0.56)
        if math.hypot(rx - cx, ry - (gy - 0.06)) < 0.12:
            self.drag_target = 'codex'
        elif math.hypot(rx - hx, ry - hy) < 0.10:
            self.drag_target = 'human_zone'
        else:
            self.drag_target = 'ground'

    def on_mouse_drag(self, event):
        if not self.edit_mode or not self.drag_target:
            return
        rx = max(0.1, min(0.92, event.x / self.screen_w))
        ry = max(0.25, min(0.95, event.y / self.screen_h))
        if self.drag_target == 'codex':
            self._api_post('update_params', {'court': {'codex_home_x_ratio': round(rx, 3), 'ground_y_ratio': round(ry + 0.04, 3)}})
        elif self.drag_target == 'human_zone':
            self._api_post('update_params', {'court': {'human_zone_x_ratio': round(rx, 3), 'human_zone_y_ratio': round(ry, 3)}})
        elif self.drag_target == 'ground':
            self._api_post('update_params', {'court': {'ground_y_ratio': round(ry, 3)}})

    def on_mouse_up(self, _event):
        self.drag_target = None

    def on_mouse_wheel(self, event):
        if not self.edit_mode or not self.state:
            return
        cur = float(self.state.get('params', {}).get('char_scale', 1.6))
        delta = 0.15 if event.delta > 0 else -0.15
        new_scale = round(max(0.8, min(2.6, cur + delta)), 2)
        self._api_post('update_params', {'params': {'char_scale': new_scale}})

    def _api_post(self, action, payload):
        def _run():
            try:
                req = Request(
                    f'{HOST}/api/badminton/{action}',
                    json.dumps(payload).encode('utf-8'),
                    {'Content-Type': 'application/json'}
                )
                with HTTP.open(req, timeout=0.6) as resp:
                    self.state = json.loads(resp.read().decode('utf-8'))
            except Exception:
                pass
        threading.Thread(target=_run, daemon=True).start()

    def _handle_remote_state(self, snap):
        if not isinstance(snap, dict):
            return
        self.state = snap
        seq = int(snap.get('desktop_close_seq', 0))
        if self.initial_close_seq is None:
            self.initial_close_seq = seq
        if snap.get('system_shutdown') or seq > self.initial_close_seq:
            self.closed.set()
            self.root.after(0, self.close)

    def _sync_loop(self):
        first_beat = True
        while not self.closed.is_set():
            try:
                payload = {
                    'role': 'desktop',
                    'mode': 'edit' if self.edit_mode else 'click_through'
                }
                if first_beat:
                    payload['reset_close'] = True
                req = Request(
                    f'{HOST}/api/badminton/heartbeat',
                    json.dumps(payload).encode('utf-8'),
                    {'Content-Type': 'application/json'}
                )
                with HTTP.open(req, timeout=0.8) as resp:
                    snap = json.loads(resp.read().decode('utf-8'))
                    first_beat = False
                    self._handle_remote_state(snap)
                # 订阅实时 SSE 流
                with HTTP.open(f'{HOST}/api/badminton/stream', timeout=4.0) as stream:
                    for line in stream:
                        if self.closed.is_set():
                            return
                        if line.startswith(b'data: '):
                            snap = json.loads(line[6:].decode('utf-8'))['data']
                            self._handle_remote_state(snap)
            except Exception:
                self.closed.wait(0.35)

    def _render_frame(self, t):
        W, H = self.logical_w, self.logical_h
        img = Image.new('RGB', (W, H), KEY)
        draw = ImageDraw.Draw(img)

        st = self.state
        if not st:
            # 尚未连上服务时也在右下角显示待机小人
            draw_desk(draw, t, False, True)
            draw_codex(draw, 41, 85, t, 'work', False)
            return img

        # 处理待播放的音效事件
        for evt in st.get('audio_events', []):
            eid = evt.get('id')
            if eid and eid not in self.played_audio_ids:
                self.played_audio_ids.add(eid)
                if len(self.played_audio_ids) > 128:
                    self.played_audio_ids = set(list(self.played_audio_ids)[-64:])
                play_local_wav(evt.get('sound'))

        court = st.get('court', {})
        params = st.get('params', {})
        char = st.get('character', {})
        props = st.get('props', {})
        scene_id = st.get('scene_id', 'S0')

        ground_y = round(H * float(court.get('ground_y_ratio', 0.82)))
        char_x = round(W * float(char.get('x', 0.68)))
        char_scale = float(params.get('char_scale', 1.6))

        # 1. 编辑校准模式或开启辅助线时：绘制浅色场地辅助线、简约球网、真人接球圈与全息入球口标定框
        show_guides = self.edit_mode or bool(court.get('show_guide_lines', False))
        if show_guides or scene_id not in ('S0', 'S1'):
            # 极浅的虚拟地面接触微线与中央简约小球网（不形成任何实体竞技场背景）
            net_x = round(W * 0.46)
            if scene_id not in ('S0', 'S1'):
                draw.line([(round(W * 0.15), ground_y + 2), (round(W * 0.92), ground_y + 2)], fill='#334155', width=1)
                # 简约像素羽毛球网柱与网带
                draw.line([(net_x, ground_y + 2), (net_x, ground_y - 34)], fill='#64748b', width=2)
                draw.line([(net_x - 3, ground_y - 34), (net_x + 3, ground_y - 34)], fill='#f8fafc', width=2)
                for ny in range(ground_y - 30, ground_y - 14, 4):
                    draw.point((net_x, ny), fill='#cbd5e1')

        if show_guides:
            hx = round(W * float(court.get('human_zone_x_ratio', 0.24)))
            hy = round(H * float(court.get('human_zone_y_ratio', 0.56)))
            draw.ellipse((hx - 28, hy - 28, hx + 28, hy + 28), outline='#38bdf8', width=2)
            draw_outlined_text(draw, hx - 32, hy - 42, '真人挥拍接球区(可拖拽)', fill='#38bdf8', outline='#080909')
            draw_outlined_text(draw, char_x - 36, ground_y + 8, '拖拽小人调整位置 / 滚轮缩放', fill='#fde047', outline='#080909')

        # 2. 宽容接球时间窗口光环提示（当球飞向真人进入可击球窗口时，闪烁翠绿提示圈）
        hw = st.get('hit_window', {})
        if hw.get('open'):
            hx = round(W * float(court.get('human_zone_x_ratio', 0.24)))
            hy = round(H * float(court.get('human_zone_y_ratio', 0.56)))
            pulse = 24 + round(math.sin(t * 20) * 5)
            draw.ellipse((hx - pulse, hy - pulse, hx + pulse, hy + pulse), outline='#4ade80', width=2)
            draw_outlined_text(draw, hx - 22, hy + pulse + 4, '挥拍击球!', fill='#4ade80', outline='#080909')

        # 3. 绘制小办公桌与椅子道具（S0 原位工作 -> S1 被小人吃力推到右侧屏幕边缘收纳！）
        if props.get('desk_visible') or props.get('desk_stored'):
            desk_x = round(W * float(props.get('desk_x', 0.66)))
            if props.get('desk_stored'):
                desk_x = W - 46  # 收纳在屏幕最右侧边缘
            desk_sprite = Image.new('RGBA', (96, 90), (0, 0, 0, 0))
            dg = ImageDraw.Draw(desk_sprite)
            draw_desk(dg, t, scene_id == 'S0', props.get('laptop_open', True))
            # 将原版办公桌按角色比例缩放绘制
            dw = round(96 * char_scale * 0.85)
            dh = round(90 * char_scale * 0.85)
            scaled_desk = desk_sprite.resize((dw, dh), Image.Resampling.NEAREST)
            img.paste(scaled_desk, (desk_x - dw // 2, ground_y - dh + 6), scaled_desk)

        # 4. 绘制小运动包道具 (S2 换装)
        if props.get('sport_bag_visible'):
            bx = round(W * float(props.get('sport_bag_x', 0.75)))
            by = ground_y
            draw.rounded_rectangle((bx - 12, by - 12, bx + 12, by), radius=3, fill='#0284c7', outline='#0f172a')
            draw.rectangle((bx - 6, by - 10, bx + 6, by - 2), fill='#fde047')
            draw.arc((bx - 6, by - 17, bx + 6, by - 9), 180, 0, fill='#1e293b', width=2)

        # 5. 绘制 Codex 像素小人
        if scene_id == 'S0':
            # S0 日常办公：复用原版坐在桌前敲键盘的动作
            pet_sprite = Image.new('RGBA', (110, 92), (0, 0, 0, 0))
            pg = ImageDraw.Draw(pet_sprite)
            draw_codex(pg, 45, 82, t, 'work', True)
            pw = round(110 * char_scale * 0.88)
            ph = round(92 * char_scale * 0.88)
            scaled_pet = pet_sprite.resize((pw, ph), Image.Resampling.NEAREST)
            img.paste(scaled_pet, (char_x - pw // 2, ground_y - ph + 6), scaled_pet)
        else:
            draw_badminton_codex(draw, char_x, ground_y, t, char, scale=char_scale)

        # 6. 绘制飞行中的羽毛球与地面对应移动阴影 (Section 6.2)
        for s in st.get('shuttles', []):
            sx = round(W * float(s.get('x', 0.5)))
            sy = round(H * float(s.get('y', 0.5)))
            ang = float(s.get('angle', 0.0))
            sc_mul = float(s.get('scale', 1.0)) * (char_scale * 0.72)
            is_giant = s.get('kind') == 'giant_boss'
            # 羽毛球地面投影阴影（高度越高阴影越小）
            height_diff = max(0, ground_y - sy)
            sh_r = max(3, round(10 * sc_mul * max(0.25, 1.0 - height_diff / 180.0)))
            draw.ellipse((sx - sh_r, ground_y - 2, sx + sh_r, ground_y + 3), fill='#1e293b')
            draw_pixel_shuttlecock(draw, sx, sy, ang, scale=sc_mul, speed_lines=bool(s.get('speed_lines')), is_giant=is_giant)

        # 7. 绘制击球火花与反噬爆炸粒子
        now_ms = st.get('now_ms', 0)
        for pt in st.get('particles', []):
            age_p = max(0.0, min(1.0, (now_ms - pt.get('at', now_ms)) / max(1, pt.get('dur', 320))))
            px = round(W * float(pt.get('x', 0.5)))
            py = round(H * float(pt.get('y', 0.5)))
            count = 12 if pt.get('smash') else 7
            rad = (14 + age_p * (48 if pt.get('smash') else 26)) * char_scale * 0.7
            for i in range(count):
                a = i * math.tau / count + age_p * 1.5
                x1 = px + round(math.cos(a) * rad * 0.4)
                y1 = py + round(math.sin(a) * rad * 0.4)
                x2 = px + round(math.cos(a) * rad)
                y2 = py + round(math.sin(a) * rad)
                col = '#fde047' if i % 2 == 0 else ('#ef4444' if pt.get('smash') else '#38bdf8')
                draw.line([(x1, y1), (x2, y2)], fill=col, width=2)

        return img

    def tick(self):
        if self.closed.is_set():
            return
        try:
            t = time.monotonic() - self.anim_origin
            frame = self._render_frame(t)
            self.photo = ImageTk.PhotoImage(
                frame.resize((self.screen_w, self.screen_h), Image.Resampling.NEAREST),
                master=self.root
            )
            self.canvas.itemconfigure(self.sprite_item, image=self.photo)
            if not self.closed.is_set():
                self._tick_after_id = self.root.after(22, self.tick)
        except tk.TclError:
            pass

    def close(self):
        self.closed.set()
        after_id = getattr(self, '_tick_after_id', None)
        if after_id:
            try:
                self.root.after_cancel(after_id)
            except Exception:
                pass
        try:
            self.bar.destroy()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass


def main():
    log_path = ROOT / 'coffee' / '.lan-certificate' / 'badminton-desktop.log'
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(log_path), encoding='utf-8', level=logging.INFO,
        format='[%(asctime)s] %(levelname)s %(message)s'
    )
    app = TransparentBadmintonDesktop()
    app.root.mainloop()


if __name__ == '__main__':
    main()
