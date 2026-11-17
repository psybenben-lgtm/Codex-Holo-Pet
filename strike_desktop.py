"""Windows office pet, keyboard pulse capture, PG-compliant back-view scrubbing, and transparent mud effects."""
from collections import deque
import ctypes
from ctypes import wintypes
import json
import logging
import math
from pathlib import Path
import random
import sys
import threading
import time
import tkinter as tk
from urllib.request import ProxyHandler, Request, build_opener
import webbrowser
import winsound

_RUNTIME_DIR = Path(__file__).resolve().parent / '.rally-runtime'
if _RUNTIME_DIR.is_dir() and str(_RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(_RUNTIME_DIR))

from PIL import Image, ImageDraw, ImageTk

from local_runtime import get_http_port, get_no_proxy_opener
from coffee_pet import (
    FONT_LABEL, HOST, KEY, WIDTH, HEIGHT, WORKSPACE,
    Pet, draw_codex, draw_cup, draw_desk, draw_outlined_text, ease
)
from strike_engine import CONFIG

SFX = WORKSPACE / 'sfx'
HTTP = get_no_proxy_opener()
TYPING_KEYS = {
    *range(0x30, 0x3A), *range(0x41, 0x5B), *range(0x60, 0x70),
    *range(0xBA, 0xC1), *range(0xDB, 0xE0), 0x08, 0x0D, 0x20, 0x2E, 0xE2
}


def play_sfx(filename):
    try:
        path = SFX / filename
        if not path.is_file():
            path = WORKSPACE / 'coffee' / filename
        if path.is_file():
            winsound.PlaySound(
                str(path),
                winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT
            )
    except RuntimeError:
        logging.exception('Could not play %s', filename)


def wall_ms():
    return time.time_ns() / 1_000_000


def draw_Carried_shovel(draw, x, y, step=0, facing=1):
    """小人起身走向屏幕右边缘时手里拎着的铁铲（实现跨屏半身与铲尖拼接）"""
    # 木柄
    sx1, sy1 = x + facing * 6, y - 22 - step
    sx2, sy2 = x + facing * 24, y - 16 - step
    draw.line([(sx1, sy1), (sx2, sy2)], fill='#211c2c', width=4)
    draw.line([(sx1, sy1), (sx2, sy2)], fill='#d9a362', width=2)
    # 铁铲头
    bx = sx2 + facing * 5
    by = sy2 + 2
    blade = [
        (sx2 - facing * 1, sy2 - 3),
        (bx + facing * 4, by - 4),
        (bx + facing * 6, by + 2),
        (sx2 - facing * 1, sy2 + 4),
    ]
    draw.polygon(blade, fill='#333646')
    inner = [
        (sx2, sy2 - 2),
        (bx + facing * 3, by - 3),
        (bx + facing * 4, by + 1),
        (sx2, sy2 + 2),
    ]
    draw.polygon(inner, fill='#9babaf')


def draw_question_mark_badge(draw, cx, cy, bounce=0):
    """搓错位置（搓到头/脸）时头顶弹出的超大黑色问号【❓】（带醒目白金描边确保在任何背景清晰可见）"""
    y = round(cy + bounce)
    x = round(cx)
    # 气泡浅黄白底板让黑色问号在透明背景上极具冲击力
    draw.rounded_rectangle((x - 11, y - 14, x + 11, y + 11), radius=5, fill='#fff9db', outline='#111118', width=2)
    draw.polygon([(x - 3, y + 11), (x + 3, y + 11), (x, y + 15)], fill='#fff9db')
    draw.line([(x - 3, y + 11), (x, y + 15), (x + 3, y + 11)], fill='#111118', width=1)
    # 大大的纯黑像素问号 ❓
    q_rects = [
        (x - 5, y - 11, x + 5, y - 8),   # 顶部横杠
        (x - 6, y - 9, x - 3, y - 6),    # 左上折角
        (x + 3, y - 9, x + 6, y - 3),    # 右上竖弯
        (x - 1, y - 4, x + 4, y - 1),    # 中间斜折
        (x - 2, y - 2, x + 1, y + 2),    # 中心短竖
        (x - 2, y + 4, x + 1, y + 8),    # 底部圆点
    ]
    for rx1, ry1, rx2, ry2 in q_rects:
        draw.rectangle((rx1 - 1, ry1 - 1, rx2 + 1, ry2 + 1), fill='#facc15')
    for rx1, ry1, rx2, ry2 in q_rects:
        draw.rectangle((rx1, ry1, rx2, ry2), fill='#09090d')


def draw_scrubbing_codex(draw, t, state, now):
    """
    电脑端搓澡去污专属像素渲染（100% 严格遵循 PG 级健康合规标准与地中海原型铁律）：
    1. 100% 完全背对镜头（背影朝向用户），绝不展示正面或侧身；
    2. 全程穿着深蓝色、带黄色小鸭子图案的宽松卡通平角大短裤；
    3. 胸部以下包裹膨胀的厚实纯白肥皂泡泡云团，腰部关键部位自带滑稽像素马赛克方块；
    4. 搓后背：身体受力弹性形变，擦除深褐色泥斑、炸开白色雪花泡沫，舒服眯眼哼哼；
    5. 搓到头部：动作瞬间一僵，脑袋猛扭回头，头顶弹出大大的黑色问号【❓】，无语瞪视海绵擦！
    """
    bath = state.get('bath') or {}
    clean_pct = float(bath.get('clean_progress', 0.0))
    dirty_ratio = max(0.0, 1.0 - clean_pct / 100.0)
    zone = bath.get('scrub_zone', 'none')
    is_question = (zone == 'head') or (now < bath.get('question_until', 0))
    is_scrubbing_back = (zone == 'back') and (now < bath.get('scrub_active_until', 0))
    is_clean_done = state.get('state') == 'CLEAN_DONE'

    # 基础中心坐标（站在办公桌前显眼位置）
    cx = 108
    cy = 84

    # 受力弹性形变计算（搓后背时身体产生 Q 弹水平位移与垂直挤压拉伸；搓到头时瞬间僵直！）
    if is_question:
        dx_shift = 0
        dy_squish = 0
    elif is_clean_done:
        jump = abs(math.sin(t * 9.0)) * 6.0
        dx_shift = 0
        dy_squish = -round(jump)
    elif is_scrubbing_back:
        raw_dx = float(bath.get('scrub_dx', 0.0))
        raw_dy = float(bath.get('scrub_dy', 0.0))
        dx_shift = round(raw_dx * 5.0 + math.sin(t * 28.0) * 2.2)
        dy_squish = round(raw_dy * 3.0 + math.cos(t * 28.0) * 1.6)
    else:
        dx_shift = 0
        dy_squish = round(math.sin(t * 4.0) * 0.8)

    x = cx + dx_shift
    y = cy + dy_squish

    # 地面水渍与阴影
    draw.ellipse((x - 22, cy - 3, x + 22, cy + 4), fill='#2c4257')
    draw.ellipse((x - 16, cy - 2, x + 16, cy + 3), fill='#527b96')

    # 1. 双腿与脚丫（微胖短腿）
    draw.rectangle((x - 10, y - 9, x - 4, y + 1), fill='#dca58e')
    draw.rectangle((x + 4, y - 9, x + 10, y + 1), fill='#dca58e')

    # 2. 【合规铁律】深蓝色、带小黄鸭图案的宽松卡通平角大短裤
    shorts_top = y - 21
    shorts_bot = y - 6
    draw.rounded_rectangle((x - 15, shorts_top, x + 15, shorts_bot), radius=2, fill='#1d3b6e', outline='#102242')
    # 短裤深色裤腿分界与松紧腰带
    draw.rectangle((x - 14, shorts_top, x + 14, shorts_top + 3), fill='#2e5aa6')
    draw.line((x, shorts_top + 5, x, shorts_bot), fill='#102242', width=2)
    # 短裤上的可爱小黄鸭像素图案 (左右裤腿各一只小黄鸭)
    for duck_x, duck_y in ((x - 8, shorts_top + 8), (x + 7, shorts_top + 9)):
        draw.rectangle((duck_x - 2, duck_y, duck_x + 2, duck_y + 2), fill='#facc15')     # 鸭身
        draw.rectangle((duck_x - 1, duck_y - 2, duck_x + 1, duck_y), fill='#fde047')     # 鸭头
        draw.point((duck_x + 2, duck_y - 1), fill='#f97316')                              # 鸭嘴

    # 3. 背部躯干（100% 背对镜头，与 draw_codex 完全同比例的微胖短躯干）
    torso_top = y - 38
    torso_bot = y - 18
    draw.polygon([
        (x - 14, torso_top + 4),
        (x - 10, torso_top),
        (x + 10, torso_top),
        (x + 14, torso_top + 4),
        (x + 13, torso_bot),
        (x - 13, torso_bot),
    ], fill='#e5ad8b', outline='#483749')
    # 背部肩胛骨与脊柱柔和像素线（体现 100% 背面视角）
    draw.line((x, torso_top + 3, x, torso_bot - 4), fill='#ca8e7e', width=1)
    draw.line((x - 7, torso_top + 5, x - 4, torso_top + 7), fill='#ca8e7e', width=1)
    draw.line((x + 4, torso_top + 7, x + 7, torso_top + 5), fill='#ca8e7e', width=1)

    # 双臂（背对镜头：搓背时舒展微抬，搓错头时僵直垂下，洗净时高举欢呼）
    if is_clean_done:
        draw.polygon([(x - 13, torso_top + 5), (x - 20, torso_top - 8), (x - 16, torso_top - 10), (x - 11, torso_top + 2)], fill='#e5ad8b')
        draw.polygon([(x + 13, torso_top + 5), (x + 20, torso_top - 8), (x + 16, torso_top - 10), (x + 11, torso_top + 2)], fill='#e5ad8b')
    elif is_question:
        # 瞬间僵住
        draw.rectangle((x - 17, torso_top + 3, x - 13, torso_top + 15), fill='#dca58e', outline='#483749')
        draw.rectangle((x + 13, torso_top + 3, x + 17, torso_top + 15), fill='#dca58e', outline='#483749')
    else:
        arm_wave = round(math.sin(t * 18.0) * 2) if is_scrubbing_back else 0
        draw.rectangle((x - 18, torso_top + 2 + arm_wave, x - 13, torso_top + 13 + arm_wave), fill='#e5ad8b', outline='#483749')
        draw.rectangle((x + 13, torso_top + 2 - arm_wave, x + 18, torso_top + 13 - arm_wave), fill='#e5ad8b', outline='#483749')

    # 4. 背部深褐色泥斑（随 clean_progress 擦拭逐渐减少直至完全干净！）
    mud_patches = [
        (-8, -34, 6, 4), (3, -35, 7, 5), (-3, -29, 7, 4),
        (-10, -26, 5, 4), (5, -27, 6, 4), (-5, -36, 4, 3),
    ]
    visible_patches = int(math.ceil(len(mud_patches) * dirty_ratio))
    for mx, my, mw, mh in mud_patches[:visible_patches]:
        draw.rectangle((x + mx, y + my, x + mx + mw, y + my + mh), fill='#5c3824')
        draw.rectangle((x + mx + 1, y + my + 1, x + mx + mw - 1, y + my + mh - 1), fill='#3b2214')

    # 5. 【合规铁律】胸部以下包裹膨胀的厚实纯白肥皂泡泡云团 + 腰部搞笑像素马赛克方块
    bubble_circles = [
        (-13, -19, 6), (-7, -21, 7), (0, -22, 7), (7, -21, 7), (13, -19, 6),
        (-11, -14, 6), (11, -14, 6), (-5, -15, 6), (5, -15, 6),
    ]
    for bx, by, br in bubble_circles:
        pulse = round(math.sin(t * 7.0 + bx) * 0.8)
        r = br + pulse
        draw.ellipse((x + bx - r, y + by - r, x + bx + r, y + by + r), fill='#f4fbff', outline='#bae6fd')
        draw.point((x + bx - r // 2, y + by - r // 2), fill='#ffffff')

    # 腰部关键部位自带一小块【滑稽搞笑的像素马赛克（Pixelated Mosaic 方块）】
    mosaic_colors = ('#f8dfa1', '#d4957a', '#f3c69f', '#b87b64', '#fae8c8', '#c78870')
    seed_step = int(t * 6)
    for row in range(3):
        for col in range(5):
            mc = mosaic_colors[(row * 5 + col + seed_step) % len(mosaic_colors)]
            mx1 = x - 10 + col * 4
            my1 = y - 21 + row * 3
            draw.rectangle((mx1, my1, mx1 + 3, my1 + 2), fill=mc)
    draw.rectangle((x - 10, y - 21, x + 10, y - 12), outline='#94a3b8')

    # 6. 头部（100% 经典 Codex 地中海微秃、两侧卷发原型！）
    head_y = y - 38
    if is_scrubbing_back and not is_question:
        # 搓后背舒服得微微仰头晃脑
        head_x = x + round(math.sin(t * 14.0) * 1.5)
        head_y -= 1
    else:
        head_x = x

    # 地中海两侧与后脑勺深紫棕卷发轮廓（与 draw_codex 100% 同色系与几何）
    draw.polygon([
        (head_x - 12, head_y - 15),
        (head_x - 7, head_y - 19),
        (head_x + 7, head_y - 19),
        (head_x + 12, head_y - 15),
        (head_x + 13, head_y - 6),
        (head_x + 9, head_y),
        (head_x - 9, head_y),
        (head_x - 13, head_y - 6),
    ], fill='#392e48')
    draw.polygon([
        (head_x - 10, head_y - 14),
        (head_x - 6, head_y - 17),
        (head_x + 6, head_y - 17),
        (head_x + 10, head_y - 14),
        (head_x + 9, head_y - 10),
        (head_x - 10, head_y - 10),
    ], fill='#63506b')
    # 地中海微秃头顶发旋高光与圆润双耳
    draw.rectangle((head_x - 6, head_y - 17, head_x + 5, head_y - 14), fill='#d99a88')
    draw.rectangle((head_x - 13, head_y - 10, head_x - 10, head_y - 5), fill='#d99a88')
    draw.rectangle((head_x + 10, head_y - 10, head_x + 13, head_y - 5), fill='#e1a589')

    if is_question:
        # 【核心微表情】：搓错位置（搓到头/脸）—— 动作瞬间一僵，脑袋猛扭回头瞪着海绵擦！
        # 在后脑勺右侧转出半张脸 + 圆睁的大黑豆眼 + 无语平直嘴 + 汗珠
        draw.polygon([
            (head_x - 2, head_y - 13),
            (head_x + 11, head_y - 13),
            (head_x + 13, head_y - 3),
            (head_x - 2, head_y - 2),
        ], fill='#e9b296')
        # 猛扭回头瞪大的两颗大黑豆圆眼（带白色惊愕高光点）
        draw.rectangle((head_x + 1, head_y - 10, head_x + 4, head_y - 7), fill='#111118')
        draw.point((head_x + 1, head_y - 10), fill='#ffffff')
        draw.rectangle((head_x + 7, head_y - 10, head_x + 10, head_y - 7), fill='#111118')
        draw.point((head_x + 7, head_y - 10), fill='#ffffff')
        # 紧皱的无语横眉与撇嘴
        draw.line((head_x, head_y - 12, head_x + 4, head_y - 11), fill='#392e48', width=1)
        draw.line((head_x + 7, head_y - 11, head_x + 11, head_y - 12), fill='#392e48', width=1)
        draw.rectangle((head_x + 4, head_y - 4, head_x + 8, head_y - 3), fill='#6c3d47')
        # 额角流下一滴无语冷汗
        draw.rectangle((head_x - 4, head_y - 11, head_x - 2, head_y - 6), fill='#7dd3fc')
        # 头顶弹出大大的黑色问号【❓】
        bounce = math.sin(t * 24.0) * 2.0
        draw_question_mark_badge(draw, head_x + 2, head_y - 34, bounce)
    elif is_scrubbing_back:
        # 【核心微表情】：搓后背舒服得眯眼哼哼（侧脸颊泛起红晕 + 欢快音符与泡沫飞溅）
        draw.rectangle((head_x - 13, head_y - 7, head_x - 10, head_y - 5), fill='#f472b6')
        draw.rectangle((head_x + 10, head_y - 7, head_x + 13, head_y - 5), fill='#f472b6')
        # 舒服哼哼气泡 "~ ♪"
        note_y = head_y - 27 - round((t * 14) % 8)
        draw_outlined_text(draw, head_x + 14, note_y, '~♪', fill='#fde047', outline='#080909')

    # 7. 绘制正在擦拭的清洁海绵擦（Cleaning Sponge / 搓澡巾）与白色雪花泡沫星光
    if now < bath.get('scrub_active_until', 0) + 180 and not is_clean_done:
        sx = x + round((float(bath.get('scrub_x', 0.5)) - 0.5) * 26)
        sy = (head_y - 10) if is_question else (y - 30 + round((float(bath.get('scrub_y', 0.55)) - 0.55) * 18))
        # 双层海绵擦（粗糙亮黄海绵面 + 翠绿百洁布背衬 + 气孔像素点）
        draw.rounded_rectangle((sx - 9, sy - 6, sx + 9, sy + 6), radius=3, fill='#facc15', outline='#ca8a04')
        draw.rectangle((sx - 8, sy + 3, sx + 8, sy + 6), fill='#16a34a')
        for px_off, py_off in ((-5, -2), (0, -3), (4, -1), (-3, 1), (3, 1)):
            draw.point((sx + px_off, sy + py_off), fill='#a16207')
        # 摩擦炸开的白色雪花泡沫粒子
        for i in range(6):
            ang = t * 10.0 + i * 1.05
            rad = 10 + (i % 3) * 4
            fx = sx + round(math.cos(ang) * rad)
            fy = sy + round(math.sin(ang) * rad * 0.7)
            draw.ellipse((fx - 2, fy - 2, fx + 2, fy + 2), fill='#ffffff', outline='#bae6fd')

    # 8. 搓完全身（CLEAN_DONE）：周身“叮”的一声冒出金色小星星 ✨
    if is_clean_done:
        star_offsets = [(-24, -46), (24, -44), (-28, -22), (27, -20), (0, -60), (-16, -56), (17, -55)]
        for idx, (ox, oy) in enumerate(star_offsets):
            twinkle = (int(t * 12) + idx) % 3
            if twinkle != 0:
                sx, sy = x + ox, y + oy
                r = 3 if twinkle == 1 else 2
                draw.line((sx - r, sy, sx + r, sy), fill='#fde047', width=2)
                draw.line((sx, sy - r, sx, sy + r), fill='#fde047', width=2)
                draw.point((sx, sy), fill='#ffffff')
        draw_outlined_text(draw, x - 22, y - 72, 'SPARKLE!', fill='#fde047', outline='#080909')
    elif not is_question:
        draw_outlined_text(draw, x - 18, head_y - 29, 'codex', fill='#ffdc38', outline='#080909')


def render_office(t, state, now):
    """桌面端统一渲染入口：支持办公、深叹气握铲跨端走位、以及背对镜头合规搓澡与问号微表情。"""
    image = Image.new('RGB', (WIDTH, HEIGHT), KEY)
    draw = ImageDraw.Draw(image)
    phase = state.get('state', 'OFFICE_IDLE')
    working = phase == 'OFFICE_WORK'
    idle_t = max(0.0, (now - state.get('since', now)) / 1000.0)
    idle = idle_t % 13.0

    # 工位桌子始终绘制在左侧背景
    show_coffee_on_desk = not working and not (phase == 'OFFICE_IDLE' and 2.1 <= idle < 3.5)
    draw_desk(draw, t, working, show_coffee_on_desk)

    if working:
        draw_codex(draw, 41, 85, t, 'work', True)
    elif phase == 'OFFICE_IDLE':
        if 2.1 <= idle < 3.5:
            bob = round(math.sin((idle - 2.1) * 5.0))
            draw_codex(draw, 41, 85 + bob, t, 'sip', False)
            draw_cup(draw, 55, 51 + bob)
        elif 5.0 <= idle < 10.8:
            draw_codex(draw, 41, 85, t, 'phone', False)
            draw.rounded_rectangle((53, 54, 60, 64), radius=1, fill='#352e43')
            draw.rectangle((54, 55, 59, 61), fill='#8cd1cf')
            scroll = int(t * 3) % 4
            draw.line((55, 56 + scroll, 58, 56 + scroll), fill='#e5efe0')
        else:
            draw_codex(draw, 41, 85, t, 'work', False)
    elif phase == 'LEAVING':
        cross = state.get('cross') or {}
        elapsed = now - state.get('since', now)
        config = state.get('config', CONFIG)
        sigh = config.get('OFFICE_SIGH_MS', 420)
        if elapsed < sigh:
            # 肩膀耷拉、胸口下沉、嘴里呼出一小团白色叹气像素团
            sink = round(3.0 * math.sin(math.pi * max(0.0, elapsed) / sigh))
            draw_codex(draw, 41, 85 + sink, t, 'sigh', False)
            for i in range(4):
                p = elapsed / sigh - i * 0.12
                if 0.0 < p < 1.0:
                    px = round(56 + p * 16)
                    py = round(48 - p * 8 + i * 2)
                    r = 2 + (i % 2)
                    draw.ellipse((px - r, py - r, px + r, py + r), fill=('#dce8df', '#f1f5f9', '#cbd5e1', '#ffffff')[i])
        elif now < cross.get('end', 0):
            # 站起身抓起铁铲往右侧屏幕边缘走去（与全息端 900ms 严丝合缝半身拼接）
            seam = (now - cross['start']) / max(1, (cross['end'] - cross['start']))
            if seam < 0:
                walk_p = ease((elapsed - sigh) / max(1, config.get('WALK_TO_EDGE_MS', 350)))
                x = 41 + (WIDTH - 14 - 41) * walk_p
            else:
                x = WIDTH - 14 + 32 * seam
            step_t = max(0.0, (now - sigh - state.get('since', now)) / 1000.0)
            step_bob = int(step_t * 9) % 4 - 2
            draw_codex(draw, round(x), 85, step_t, 'walk', False)
            draw_Carried_shovel(draw, round(x), 85, step_bob, 1)
        else:
            draw_outlined_text(draw, 84, 24, 'DIG!', fill='#fde047', outline='#080909')
    elif phase in ('WORKING', 'TIRED', 'RESTING'):
        # 全息盒正在挖土/累趴/喘气：电脑工位空座 + 漂浮挖土提示与飞溅土粒，明确表示小人在全息端忙碌！
        badge = 'REST...' if phase == 'RESTING' else ('TIRED!' if phase == 'TIRED' else 'DIG!')
        badge_col = '#93c5fd' if phase == 'RESTING' else ('#fb923c' if phase == 'TIRED' else '#fde047')
        bob = round(math.sin(t * 7.0) * 1.8)
        draw_outlined_text(draw, 86, 22 + bob, badge, fill=badge_col, outline='#080909')
        for i in range(4):
            px = 148 - int((t * 36 + i * 11) % 34)
            py = 68 - int(abs(math.sin(t * 8 + i)) * 18)
            draw.rectangle((px, py, px + 3, py + 3), fill='#8f5834' if i % 2 == 0 else '#fde047')
    elif phase in ('ANGRY', 'THROWING', 'STRIKE'):
        shake = round(math.sin(t * 38.0) * 2.0)
        msg = 'MUD!!' if phase == 'THROWING' else ('SPLAT!' if phase == 'STRIKE' else 'ANGRY!')
        draw_outlined_text(draw, 80 + shake, 22, msg, fill='#f87171', outline='#080909')
        # 右侧红温叹号
        draw.rectangle((146 + shake, 34, 151 + shake, 48), fill='#ef4444', outline='#080909')
        draw.rectangle((146 + shake, 51, 151 + shake, 56), fill='#ef4444', outline='#080909')
    elif phase in ('BATH_ENTER', 'BATH_SOAK'):
        bath = state.get('bath') or {}
        elapsed = max(0, now - state.get('since', now))
        if phase == 'BATH_ENTER' and elapsed < 520:
            # 推入浴缸瞬间：小人高兴地抱起橡皮小黄鸭朝右侧全息浴缸快步跑去！
            p = ease(elapsed / 520.0)
            x = round(41 + (WIDTH - 12 - 41) * p)
            draw_codex(draw, x, 85, t * 1.4, 'walk', False)
            # 怀里可爱黄色橡皮小鸭
            draw.rectangle((x + 11, 56, x + 18, 62), fill='#facc15', outline='#080909')
            draw.rectangle((x + 13, 52, x + 17, 56), fill='#fde047')
            draw.rectangle((x + 17, 53, x + 20, 55), fill='#f97316')
        else:
            # 全息端泡澡中：电脑桌边冒起彩色肥皂泡泡，过烫(>=72°C)时桌面同步弹红温龙虾警报！
            is_hot = bool(bath.get('hot_jump')) or float(bath.get('temp', 42.0)) >= 72.0
            for i in range(6):
                bx = 104 + (i % 3) * 18 + round(math.sin(t * 4.5 + i) * 4)
                by = 76 - int((t * 28 + i * 13) % 52)
                br = 3 + (i % 2)
                col = ('#fca5a5', '#fdba74', '#fef08a')[i % 3] if is_hot else ('#ffffff', '#bae6fd', '#fbcfe8')[i % 3]
                draw.ellipse((bx - br, by - br, bx + br, by + br), fill=col, outline='#7dd3fc' if not is_hot else '#ef4444')
            if is_hot:
                jump = abs(round(math.sin(t * 16.0) * 5.0))
                draw_outlined_text(draw, 84, 22 - jump, f"HOT {int(bath.get('temp', 86))}C!", fill='#ff4d6d', outline='#080909')
            else:
                draw_outlined_text(draw, 88, 22, f"BATH {int(bath.get('temp', 42))}C", fill='#7dd3fc', outline='#080909')
    elif phase in ('RETURNING', 'BATH_RETURN'):
        cross = state.get('cross') or {}
        if cross and now >= cross.get('start', 0):
            if now < cross['end']:
                seam = (now - cross['start']) / max(1, (cross['end'] - cross['start']))
                x = WIDTH + 16 - 32 * seam
            else:
                home = ease((now - cross['end']) / max(1, (cross['arrive'] - cross['end'])))
                target_x = 108 if phase == 'BATH_RETURN' else 41
                x = WIDTH - 16 + (target_x - WIDTH + 16) * home
            walk_t = (now - cross['start']) / 1000.0
            draw_codex(draw, round(x), 85, walk_t, 'walk', False, -1)
            if phase == 'BATH_RETURN':
                # 泡完澡湿漉漉走回电脑桌宠窗口，身上滴落水珠
                for i in range(3):
                    wy = 55 + ((int(now / 60) + i * 7) % 24)
                    wx = round(x) - 8 + i * 8
                    draw.rectangle((wx, wy, wx + 1, wy + 3), fill='#38bdf8')
    elif phase in ('SCRUBBING', 'CLEAN_DONE'):
        draw_scrubbing_codex(draw, t, state, now)

    return image


class KeyboardPulse:
    """The hook retains only which typing keys are down. The app receives counts."""
    def __init__(self, on_hit):
        self.on_hit = on_hit
        self.thread_id = None
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._listen, daemon=True)
        self.thread.start()

    def stop(self):
        self.stopped.set()
        if self.thread_id is not None:
            ctypes.windll.user32.PostThreadMessageW(self.thread_id, 0x12, 0, 0)
        if self.thread.is_alive() and threading.current_thread() is not self.thread:
            self.thread.join(timeout=0.35)

    def _listen(self):
        user = ctypes.WinDLL('user32', use_last_error=True)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        user.SetWindowsHookExW.argtypes = (ctypes.c_int, callback_type, wintypes.HINSTANCE, wintypes.DWORD)
        user.SetWindowsHookExW.restype = wintypes.HHOOK
        user.CallNextHookEx.argtypes = (wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        user.CallNextHookEx.restype = ctypes.c_ssize_t
        user.UnhookWindowsHookEx.argtypes = (wintypes.HHOOK,)
        user.GetMessageW.argtypes = (ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT)
        user.PeekMessageW.argtypes = (*user.GetMessageW.argtypes, wintypes.UINT)
        kernel.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
        kernel.GetModuleHandleW.restype = wintypes.HMODULE
        down = set()
        ctrl, alt, win = {0xA2, 0xA3}, {0xA4, 0xA5}, {0x5B, 0x5C}

        @callback_type
        def on_key(code, message, pointer):
            if code == 0:
                vk = ctypes.cast(pointer, ctypes.POINTER(wintypes.DWORD))[0]
                if message in (0x101, 0x105):
                    down.discard(vk)
                elif message in (0x100, 0x104) and vk not in down:
                    down.add(vk)
                    shortcut = down & (ctrl | alt | win) and not (0xA5 in down and 0xA2 in down)
                    if vk in TYPING_KEYS and not shortcut and not self.stopped.is_set():
                        self.on_hit()
            return user.CallNextHookEx(None, code, message, pointer)

        hook = user.SetWindowsHookExW(13, on_key, kernel.GetModuleHandleW(None), 0)
        if not hook:
            logging.error('Global typing hook unavailable: %s', ctypes.get_last_error())
            return
        logging.info('Global typing hook installed')
        message = wintypes.MSG()
        try:
            user.PeekMessageW(ctypes.byref(message), None, 0, 0, 0)
            self.thread_id = kernel.GetCurrentThreadId()
            while not self.stopped.is_set() and user.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                pass
        finally:
            user.UnhookWindowsHookEx(hook)


MUD_DARK = '#24120b'
MUD_EDGE = '#3e2115'
MUD_BODY = '#633b25'
MUD_RIDGE = '#8f5834'
MUD_GLOSS = '#c48d56'
MUD_SPECULAR = '#e6be8a'


def mud_clod(draw, x, y, rx, ry, spin=0):
    points = []
    for i, r in enumerate((0.94, 1.14, 0.86, 1.08, 0.9, 1.02, 1.12, 0.85, 1.06, 0.91)):
        a = spin + i * math.tau / 10
        points.append((x + math.cos(a) * r * rx, y + math.sin(a) * r * ry))
    draw.polygon(points, fill=MUD_DARK)
    draw.polygon([(x + (px - x) * 0.86, y + (py - y) * 0.82 - ry * 0.1) for px, py in points], fill=MUD_BODY)
    draw.line(
        [(x - rx * 0.5, y - ry * 0.23), (x - rx * 0.23, y - ry * 0.52), (x + rx * 0.3, y - ry * 0.5)],
        fill=MUD_GLOSS, width=max(1, round(ry * 0.15))
    )
    draw.ellipse((x + rx * 0.08, y + ry * 0.05, x + rx * 0.55, y + ry * 0.41), fill=MUD_EDGE)


def rounded_contour(points):
    """Interpolate the wet edge through its lobes with a closed Catmull-Rom curve."""
    outline = []
    n = len(points)
    for i, start in enumerate(points):
        a, end, d = points[i - 1], points[(i + 1) % n], points[(i + 2) % n]
        for step in range(6):
            t = step / 6
            outline.append(tuple(
                0.5 * (
                    2 * b + (-p + c) * t
                    + (2 * p - 5 * b + 4 * c - q) * t * t
                    + (-p + 3 * b - 3 * c + q) * t * t * t
                )
                for p, b, c, q in zip(a, start, end, d)
            ))
    return outline


class MudSplat:
    """大面积浓稠湿泥饼 + 飞溅泥块粒子 + 重力挂壁流淌黏液与断开下坠水滴。"""
    def __init__(self, event):
        self.event = event
        rng = random.Random(event['serial'])
        points = []
        for i in range(36):
            a = (i + rng.uniform(-0.25, 0.25)) * math.tau / 36
            r = rng.uniform(0.82, 1.08) + (rng.uniform(0.28, 0.62) if i % 4 == 0 else 0)
            points.append((math.cos(a) * r, math.sin(a) * r))
        self.contour = rounded_contour(points)
        self.drops = []
        for _ in range(64):
            a = rng.uniform(0, math.tau)
            v = rng.uniform(110, 720)
            self.drops.append((
                v * math.cos(a),
                v * math.sin(a) - 85,
                rng.uniform(2.0, 10.5),
                rng.uniform(0.22, 0.64),
                rng.choice((MUD_DARK, MUD_EDGE, MUD_BODY, MUD_RIDGE)),
            ))
        # 14 道受重力向下挂壁拉长的黏液流痕 + 断开下坠水滴参数
        self.drips = [
            (
                rng.uniform(-0.88, 0.88),
                rng.uniform(35, 165),
                rng.uniform(3.2, 8.5),
                rng.uniform(0.6, 1.8),  # 水滴断开周期偏移
            )
            for _ in range(14)
        ]

    def draw(self, draw, x, y, age, clean_ratio=0.0):
        # 随搓澡进度缩小消退
        remain = max(0.15, 1.0 - clean_ratio * 0.85)
        scale = self.event.get('mud_scale', 1.42) * remain
        bounce = 1 + 0.24 * math.exp(-age * 9.5) * math.cos(age * 32)
        spread = min(1.0, 0.72 + age * 8.5)
        rx, ry = 118 * scale * spread * bounce, 82 * scale * spread / bounce

        # 1. 绘制重力挂壁拉长的黏液流痕与尾部断开下坠的小水滴
        for dx, length, width, drop_offset in self.drips:
            sy = y + ry * (0.32 + 0.34 * (1 - abs(dx)))
            creep = 1.0 - math.exp(-age * 0.85)
            ey = sy + length * scale * creep
            px = x + rx * dx
            w = width * scale
            # 挂壁流痕主体
            draw.polygon(
                ((px - w, sy), (px + w, sy), (px + w * 0.42, ey), (px - w * 0.42, ey)),
                fill=MUD_DARK
            )
            draw.polygon(
                ((px - w * 0.7, sy), (px + w * 0.7, sy), (px + w * 0.3, ey - 2), (px - w * 0.3, ey - 2)),
                fill=MUD_EDGE
            )
            # 尾部汇聚的饱满挂珠
            bulb_r = w * 0.82
            draw.ellipse((px - bulb_r, ey - bulb_r, px + bulb_r, ey + bulb_r * 1.25), fill=MUD_EDGE)
            if ey - sy > 16:
                draw.line(((px - w * 0.18, sy + 4), (px, ey - 4)), fill=MUD_BODY, width=max(1, round(w * 0.35)))
                draw.point((round(px - bulb_r * 0.3), round(ey)), fill=MUD_GLOSS)

            # 尾部断开并加速下坠的独立泥水滴 (Detached falling droplets)
            if age > 0.35:
                cycle = (age * 0.9 + drop_offset) % 1.6
                if cycle < 1.1:
                    fall_p = cycle / 1.1
                    drop_y = ey + bulb_r + (fall_p ** 1.8) * 135 * scale
                    dr = max(2.0, bulb_r * (0.78 - 0.25 * fall_p))
                    draw.ellipse((px - dr * 0.75, drop_y - dr * 1.2, px + dr * 0.75, drop_y + dr * 1.2), fill=MUD_DARK)
                    draw.ellipse((px - dr * 0.55, drop_y - dr * 0.9, px + dr * 0.55, drop_y + dr * 0.9), fill=MUD_BODY)
                    draw.point((round(px - dr * 0.2), round(drop_y - dr * 0.3)), fill=MUD_GLOSS)

        # 2. 绘制多层厚重交错的核心湿泥饼（深褐底层、暗褐中层、亮褐主层、高光湿润脊）
        for size, offset, color in (
            (1.04, 7, MUD_DARK),
            (0.97, 2, MUD_EDGE),
            (0.82, -4, MUD_BODY),
            (0.56, -9, MUD_RIDGE),
        ):
            draw.polygon(
                [(x + dx * rx * size, y + dy * ry * size + offset * scale) for dx, dy in self.contour],
                fill=color
            )

        # 3. 表面湿润高光与黏稠厚度纹理
        for dx, dy, width, color in (
            (-0.62, -0.32, 0.48, MUD_RIDGE),
            (-0.52, -0.36, 0.26, MUD_GLOSS),
            (-0.46, -0.38, 0.12, MUD_SPECULAR),
            (0.18, -0.45, 0.32, MUD_GLOSS),
            (0.36, 0.20, 0.25, MUD_EDGE),
            (-0.34, 0.32, 0.44, MUD_DARK),
            (0.05, 0.12, 0.30, MUD_RIDGE),
        ):
            px, py = x + dx * rx, y + dy * ry
            draw.line(
                ((px, py + ry * 0.09), (px + width * rx * 0.35, py), (px + width * rx, py - ry * 0.03)),
                fill=color, width=max(2, round(ry * 0.075))
            )

        # 4. 向四周炸开的几十颗不规则小泥块与飞溅粒子
        for vx, vy, size, stick, color in self.drops:
            t = min(age, stick)
            drift = t / (1 + 1.45 * t)
            px = x + vx * drift * scale
            py = y + (vy * drift + 360 * t * t + max(0.0, age - stick) * size * 1.4) * scale
            r = size * scale
            draw.ellipse((px - r, py - r * 0.72, px + r, py + r * 0.72), fill=MUD_DARK)
            draw.ellipse((px - r * 0.82, py - r * 0.58, px + r * 0.82, py + r * 0.58), fill=color)
            if r >= 4.0:
                draw.point((round(px - r * 0.3), round(py - r * 0.35)), fill=MUD_GLOSS)


class MudOverlay:
    """全屏置顶透明点击穿透层（Win32 WS_EX_TRANSPARENT 100% 穿透鼠标点击）。"""
    def __init__(self, master):
        self.window = tk.Toplevel(master)
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.attributes('-topmost', True)
        self.window.attributes('-transparentcolor', KEY)
        self.window.config(background=KEY)
        self.canvas = tk.Canvas(self.window, background=KEY, highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        self.sprite = self.canvas.create_image(0, 0, anchor='nw')
        self.width, self.height = master.winfo_screenwidth(), master.winfo_screenheight()
        self.active = False
        self.event_id = self.impact_id = self.launch_id = None
        user = ctypes.windll.user32
        user.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
        user.GetAncestor.restype = wintypes.HWND
        self.hwnd = user.GetAncestor(self.window.winfo_id(), 2)
        user.GetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int)
        user.SetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_long)
        user.SetWindowPos.argtypes = (
            wintypes.HWND, wintypes.HWND, ctypes.c_int,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT
        )
        # WS_EX_NOACTIVATE (0x08000000) | WS_EX_LAYERED (0x80000) | WS_EX_TRANSPARENT (0x20) | WS_EX_TOOLWINDOW (0x80)
        flags = 0x08000000 | 0x00080000 | 0x00000020 | 0x00000080
        user.SetWindowLongW(self.hwnd, -20, user.GetWindowLongW(self.hwnd, -20) | flags)
        self.user = user
        self.bounds = None
        self.alpha = 1.0

    def hide(self):
        if self.active:
            self.window.withdraw()
            self.active = False
            self.bounds = None

    def render(self, state, now):
        event = state.get('mud')
        if not event:
            self.hide()
            return
        event_id = (state.get('epoch'), event.get('serial'))
        launch, edge, impact = (event[k] for k in ('launch_time_ms', 'edge_time_ms', 'impact_time_ms'))
        age = (now - impact) / 1000.0
        clean_ratio = float(event.get('clean_ratio', 0.0))

        if now >= launch and self.launch_id != event_id:
            self.launch_id = event_id
            if now < launch + 180:
                play_sfx('mud_throw.wav')

        if now < edge - 28 or age >= event.get('linger_sec', 45.0) or clean_ratio >= 1.0:
            self.hide()
            return

        if self.event_id != event_id:
            self.event_id = event_id
            self.splat = MudSplat(event)

        scale = event.get('mud_scale', 1.42)
        tx = round(self.width * event.get('target_x_ratio', 0.5))
        ty = round(self.height * event.get('target_y_ratio', 0.48))

        if age < 0:
            p = max(0.0, min(1.0, (now - edge) / max(1, (impact - edge))))
            x = self.width + (tx - self.width) * p
            ey = self.height * event.get('entry_y_ratio', 0.88)
            y = ey + (ty - ey) * p - self.height * 0.12 * 4 * p * (1 - p)
            rx, ry = (20 + 36 * p) * scale, (14 + 26 * p) * scale
            radius_x, radius_y = rx * 1.35 + 6, ry * 1.35 + 6
        else:
            x, y = tx, ty
            radius_x, radius_y = 380 * scale, 390 * scale

        left, top = max(0, math.floor(x - radius_x)), max(0, math.floor(y - radius_y))
        right = min(self.width, math.ceil(x + radius_x))
        bottom = min(self.height, math.ceil(y + radius_y))
        if right <= left or bottom <= top:
            self.hide()
            return

        image = Image.new('RGB', (right - left, bottom - top), KEY)
        draw = ImageDraw.Draw(image)
        if age < 0:
            mud_clod(draw, x - left, y - top, rx, ry, p * 3.8)
        else:
            self.splat.draw(draw, x - left, y - top, age, clean_ratio)

        self.photo = ImageTk.PhotoImage(image)
        self.canvas.itemconfigure(self.sprite, image=self.photo)
        bounds = (left, top, right - left, bottom - top)
        if bounds != self.bounds:
            self.window.geometry(f'{bounds[2]}x{bounds[3]}+{left}+{top}')
            self.bounds = bounds
        if not self.active:
            self.window.deiconify()
            self.window.update_idletasks()
            self.user.SetWindowPos(self.hwnd, -1, 0, 0, 0, 0, 0x1 | 0x2 | 0x10 | 0x40)
            self.active = True

        # 保持 Win32 LWA_COLORKEY (0x1) 透明色键有效，避免 Tkinter attributes(-alpha) 覆盖透明色键导致泥巴不显示
        self.user.SetLayeredWindowAttributes(self.hwnd, 0x00020101, 255, 0x1)

        if age >= 0 and self.impact_id != event_id:
            self.impact_id = event_id
            if age < 0.20:
                play_sfx('mud_splat.wav')
            logging.info('Mud impact %s at (%d, %d), frame %.0f ms after contact', event_id, tx, ty, age * 1000)


class StrikeDesktopApp(Pet):
    def __init__(self, requested_mode=lambda: None, initial_mode='strike'):
        self.requested_mode = requested_mode
        self.enabled = False
        self.strike = {}
        self.offset_strike = 0
        self.pending_hits = deque(maxlen=48)
        self.wake_sender = threading.Event()
        self.closed = threading.Event()
        self.keyboard = None
        self.keyboard_capture = True
        self._coord_mode_seq = -1
        self.sigh_id = None
        self.question_id = None
        self.clean_done_id = None
        self.hot_jump_id = None
        self.last_scrub_sfx = 0
        super().__init__(lambda: False)
        self.overlay = MudOverlay(self.root)

        # 丰富完善的右键快捷控制菜单（新增【回到工位】与全流程测试项）
        self.menu.add_separator()
        self.menu.add_command(label='🏠 回到工位 (收起铲子回办公室)', command=self.return_to_office)
        self.menu.add_command(label='⛏️ 立即出门挖土 (挖矿)', command=lambda: self._async_post('input', {'hits': 12, 'manual_burst': True}))
        self.menu.add_command(label='💥 立即演练暴怒跨屏甩泥', command=lambda: self._async_post('trigger', {}))
        self.menu.add_command(label='🛁 推入浴缸泡澡 -> 准备搓澡', command=lambda: self._async_post('bath_push', {}))
        self.menu.add_command(label='🦞 演练 86°C 过烫变红龙虾跳出', command=lambda: self._async_post('bath_knob', {'temp': 86}))
        self.menu.add_command(label='🧽 开始电脑桌宠背向搓澡', command=lambda: self._async_post('scrub_start', {'immediate': True}))
        self.menu.add_command(label='❓ 演练搓错头部弹出黑问号', command=lambda: self._async_post('scrub_move', {'zone': 'head', 'y': 0.2}))
        self.menu.add_command(label='📊 打开三端同屏联调控制台', command=lambda: webbrowser.open(HOST + '/strike/dash'))
        self.menu.add_command(label='🔄 重置挖土与清除泥巴', command=self.reset_strike)
        self.menu.entryconfigure('仅隐藏桌宠 (保留网页)', command=self.close)
        self.menu.entryconfigure('退出 Codex 桌宠', command=self.exit_all)

        # 双击桌宠快速回到屏幕右下角工位
        self.canvas.bind('<Double-Button-1>', lambda _e: self.reset_to_corner())
        self.root.protocol('WM_DELETE_WINDOW', self.exit_all)
        self.sender = threading.Thread(target=self._send_pulses, daemon=True)
        self.sender.start()
        threading.Thread(target=self._listen_strike, daemon=True).start()
        self.set_mode(initial_mode)

    def _async_post(self, action, payload):
        threading.Thread(target=self._post, args=(action, payload), daemon=True).start()

    def on_coordinator_state(self, info, _prev_seq):
        if self.closed.is_set():
            return
        kc = bool(info.get('keyboard_capture', True))
        if kc != self.keyboard_capture:
            self.keyboard_capture = kc
            if not kc and self.keyboard is not None:
                self.keyboard.stop()
                self.keyboard = None
            elif kc and self.enabled and self.keyboard is None:
                self.keyboard = KeyboardPulse(self._hit)
        mode = info.get('mode', 'coffee')
        seq = info.get('mode_seq', -1)
        if mode == 'badminton':
            self.close()
            return
        self._refresh_dock_mode(mode)
        if mode in ('coffee', 'strike') and seq != self._coord_mode_seq:
            self._coord_mode_seq = seq
            if (mode == 'strike') != self.enabled:
                self.set_mode(mode)

    def set_mode(self, mode):
        enabled = mode == 'strike'
        if self.enabled != enabled:
            self.enabled = enabled
            self.pending_hits.clear()
            self.strike = {}
            self.overlay.hide()
            self.wake_sender.set()
            if enabled:
                threading.Thread(target=self._fetch_strike_snapshot, daemon=True).start()
        if enabled and self.keyboard_capture and self.keyboard is None:
            self.keyboard = KeyboardPulse(self._hit)
        elif (not enabled or not self.keyboard_capture) and self.keyboard is not None:
            self.keyboard.stop()
            self.keyboard = None
        self._refresh_dock_mode('strike' if enabled else 'coffee')
        self.show_at_corner()

    def _fetch_strike_snapshot(self):
        try:
            with HTTP.open(HOST + '/api/strike/status', timeout=0.8) as r:
                snap = json.load(r)
            if isinstance(snap, dict) and self.enabled:
                self.strike = snap
        except (OSError, ValueError):
            pass

    def toggle_strike(self):
        self.set_mode('coffee' if self.enabled else 'strike')

    def return_to_office(self):
        """点击【回到工位】立即收起铲子，平滑转场走回办公室敲电脑模式"""
        if self.enabled:
            self._async_post('return_office', {})
        else:
            self.reset_to_corner()

    def reset_to_corner(self):
        if not self.enabled:
            return super().reset_to_corner()
        _, _, right, bottom = self.work_area
        dock = self.strike.get('config', CONFIG)['DOCK_BOTTOM_PX']
        self.root.geometry(f'{self.size[0]}x{self.size[1]}+{right - self.size[0]}+{bottom - self.size[1] - dock}')

    def on_drag_motion(self, event):
        # 允许在任何模式下自由拖拽桌宠窗口
        super().on_drag_motion(event)

    def center_on_screen(self):
        super().center_on_screen()

    def copy_holo(self):
        try:
            with HTTP.open(HOST + '/coffee/lan', timeout=0.6) as response:
                data = json.load(response)
                ip = data['ip']
                port = data.get('http_port') or get_http_port()
        except (OSError, ValueError, KeyError):
            logging.warning('Could not discover LAN address')
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(f'http://{ip}:{port}/strike')

    def reset_strike(self):
        if self.enabled:
            self._async_post('reset', {})

    def close(self):
        if self.closed.is_set():
            return
        self.closed.set()
        try:
            req = Request(HOST + '/api/pet/heartbeat', b'{"closing":true}', {'Content-Type': 'application/json'})
            HTTP.open(req, timeout=0.45).close()
        except (OSError, ValueError):
            pass
        if self.keyboard:
            self.keyboard.stop()
            self.keyboard = None
        self.wake_sender.set()
        self.sender.join(timeout=0.65)
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _hit(self):
        if self.enabled and self.keyboard_capture:
            self.pending_hits.append(time.monotonic())
            self.wake_sender.set()

    def _post(self, action, data):
        request = Request(
            f'{HOST}/api/strike/{action}',
            json.dumps(data).encode('utf-8'),
            {'Content-Type': 'application/json'}
        )
        try:
            with HTTP.open(request, timeout=0.55) as response:
                response.read()
        except OSError:
            pass

    def _send_pulses(self):
        last = (False, False)
        heartbeat = 0
        while not self.closed.is_set():
            self.wake_sender.wait(0.020)
            self.wake_sender.clear()
            enabled, working = self.enabled, self.work == 'working'
            count = 0
            now = time.monotonic()
            while count < 24:
                try:
                    tapped = self.pending_hits.popleft()
                except IndexError:
                    break
                if now - tapped < 0.25:
                    count += 1
            if (enabled, working) == last and not (enabled and (count or now >= heartbeat)):
                continue
            if enabled or last[0]:
                self._post('desktop', {'enabled': enabled, 'working': working, 'hits': min(24, count)})
            last, heartbeat = (enabled, working), now + 1.2
        if self.enabled:
            self._post('desktop', {'enabled': False, 'working': False, 'hits': 0})

    def _listen_strike(self):
        while not self.closed.is_set():
            try:
                start = wall_ms()
                with HTTP.open(HOST + '/api/strike/clock', timeout=0.8) as response:
                    now = json.load(response)['now']
                self.offset_strike = now - (start + wall_ms()) / 2
                with HTTP.open(HOST + '/api/strike/stream', timeout=4.0) as response:
                    for line in response:
                        if self.closed.is_set():
                            return
                        if self.enabled and line.startswith(b'data: '):
                            self.strike = json.loads(line[6:])['data']
            except (OSError, ValueError, KeyError):
                self.closed.wait(0.25)

    def tick(self):
        requested = self.requested_mode()
        if requested:
            self.set_mode(requested)
        if not self.enabled:
            return super().tick()
        now = wall_ms() + self.offset_strike
        state = self.strike or {'state': 'OFFICE_WORK' if self.work == 'working' else 'OFFICE_IDLE'}
        if self.work == 'working' and state.get('state') in ('OFFICE_IDLE', 'OFFICE_WORK'):
            state = {**state, 'state': 'OFFICE_WORK'}

        # 1. 触发挖土离场叹气音效
        if state.get('state') == 'LEAVING':
            sigh_id = (state.get('epoch'), state.get('since'))
            if sigh_id != self.sigh_id:
                self.sigh_id = sigh_id
                if now < state.get('since', now) + 250:
                    play_sfx('relax_sigh.wav')

        # 2. 搓澡阶段微表情音效（过烫跳出、搓头弹出大黑问号、搓后背泡泡音效）
        bath = state.get('bath') or {}
        if state.get('state') in ('BATH_ENTER', 'BATH_SOAK') and bath.get('hot_jump'):
            hj_id = (state.get('epoch'), round(float(bath.get('temp', 86))))
            if hj_id != self.hot_jump_id:
                self.hot_jump_id = hj_id
                play_sfx('hot_jump.wav')
        elif not bath.get('hot_jump'):
            self.hot_jump_id = None

        if state.get('state') == 'SCRUBBING':
            q_serial = bath.get('question_serial', 0)
            if q_serial and (state.get('epoch'), q_serial) != self.question_id:
                self.question_id = (state.get('epoch'), q_serial)
                play_sfx('question_pop.wav')
            elif bath.get('scrub_zone') == 'back' and now < bath.get('scrub_active_until', 0):
                if now - self.last_scrub_sfx > 320:
                    self.last_scrub_sfx = now
                    play_sfx('bubble_scrub.wav')

        # 3. 搓完全身冒金星庆祝音效
        if state.get('state') == 'CLEAN_DONE':
            done_id = (state.get('epoch'), bath.get('clean_done_at'))
            if done_id != self.clean_done_id:
                self.clean_done_id = done_id
                play_sfx('clean_sparkle.wav')

        self.overlay.render(state, now)
        self._position_chat()
        frame = render_office(time.monotonic() - self.animation_origin, state, now)
        self.photo = ImageTk.PhotoImage(frame.resize(self.size, Image.Resampling.NEAREST))
        self.canvas.itemconfigure(self.sprite, image=self.photo)
        self.root.after(20, self.tick)


if __name__ == '__main__':
    import sys
    from coffee_pet import main
    sys.argv.append('--strike')
    main()
