"""Live art for the first-person court. Every shuttle, hand and prop is drawn from state."""
from functools import lru_cache
from math import atan2, cos, hypot, pi, sin, tau
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from coffee_pet import draw_codex, draw_desk
from rally_hand import FINGERS, PALM, TIPS
from rally_match import SMASH_POWER, clamp, ease, mix, player_point, project
from transparent_badminton_desktop import draw_badminton_codex, draw_pixel_racket

W, H = 1024, 704
MINT = '#aef6db'
AMBER = '#ffd288'
PALETTE = ('#96f7cc', '#7cd2f3', '#ffcc80', '#f89bb6', '#c6acff')
FIRE_PALETTE = ('#fff3b0', '#ffb703', '#fb8500', '#ff5400', '#ef233c')
WIN_FONTS = Path('C:/Windows/Fonts')


@lru_cache(maxsize=24)
def font(size):
    for name in ('msyhbd.ttc', 'msyh.ttc', 'seguisb.ttf'):
        path = WIN_FONTS / name
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size)


def land(x, z, h=0.):
    a, b, _ = project(x, z, h)
    return a, b


def rgba(hex_color, alpha):
    h = hex_color.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4)) + (round(clamp(alpha)*255),)


def glow(g, x, y, rx, ry, color, amount):
    for i in range(4, 0, -1):
        s = i/4.
        g.ellipse((x-rx*s, y-ry*s, x+rx*s, y+ry*s), fill=rgba(color, amount*(1-s*.66)/3))


def racket_tip_for_hand(hand):
    """计算球拍模式下手持球拍锚点、朝向角以及拍头中心坐标 (1024x704 画布)。"""
    cx, cy = player_point(hand.palm)
    ang = -1.15
    if getattr(hand, 'points', None) and len(hand.points) >= 10:
        wx, wy = player_point(hand.points[0][:2])
        mx, my = player_point(hand.points[9][:2])
        dx, dy = mx - wx, my - wy
        if hypot(dx, dy) > 4.:
            ang = atan2(dy, dx)
    ux, uy = cos(ang), sin(ang)
    return cx, cy, ang, cx + ux * 44., cy + uy * 44.


def hand_skeleton_points(hand):
    """将手部 21 关节点映射到桌面画布；近距离时自动收拢视觉比例，保持小巧且不改定位精度。"""
    cx, cy = player_point(hand.palm)
    pts = hand.points
    if not pts:
        return [], 1.
    px0, py0 = hand.palm
    p0, p9 = pts[0], pts[9] if len(pts) > 9 else pts[0]
    dx_p = (p9[0] - p0[0]) * 568.
    dy_p = (p9[1] - p0[1]) * 443.
    dz_p = ((p9[2] - p0[2]) if len(p0) > 2 and len(p9) > 2 else 0.) * 568.
    palm_px = hypot(hypot(dx_p, dy_p), dz_p * .85)
    target_palm = 46. + 10. * clamp((palm_px - 46.) / 140.)
    scale_k = min(1., target_palm / max(1., palm_px)) if palm_px > 1. else 1.
    points = [(cx + (x - px0) * 568. * scale_k, cy + (y - py0) * 443. * scale_k) for x, y, _ in pts]
    return points, scale_k


def _draw_speech_bubble(g, x, y, text, border='#38bdf8', fill='#0f1c2e', text_fill='#f8fafc'):
    if not text:
        return
    f = font(13)
    bbox = g.textbbox((0, 0), text, font=f)
    tw = max(40, bbox[2] - bbox[0])
    th = max(16, bbox[3] - bbox[1])
    pad_x, pad_y = 10, 6
    bw = tw + pad_x * 2
    bh = th + pad_y * 2
    bx = clamp(x - bw / 2, 16, W - bw - 16)
    by = clamp(y - bh, 12, H - bh - 30)
    g.rounded_rectangle((bx, by, bx + bw, by + bh), radius=8,
                        fill=rgba(fill, .90), outline=rgba(border, .96), width=2)
    tx = clamp(x, bx + 12, bx + bw - 12)
    g.polygon([(tx - 5, by + bh - 1), (tx + 5, by + bh - 1), (tx, by + bh + 7)],
              fill=rgba(fill, .90), outline=rgba(border, .96))
    g.text((bx + bw / 2, by + bh / 2), text, anchor='mm', font=f, fill=text_fill)


def _draw_anger_mark(g, x, y, scale=1.0, col='#ff4d6d'):
    """绘制像素/漫画风格的十字怒火标记 💢。"""
    r = 6.5 * scale
    for sx in (-1, 1):
        for sy in (-1, 1):
            g.line([(x + sx * r * .35, y + sy * r),
                    (x + sx * r * .35, y + sy * r * .35),
                    (x + sx * r, y + sy * r * .35)],
                   fill=rgba(col, .96), width=max(2, round(2.2 * scale)))


class Art:
    def __init__(self):
        self.desk_layer = Image.new('RGBA', (105, 96))

    def _net(self, g, alpha):
        if alpha <= .02:
            return
        z = .50
        l = land(-1.05, z, 75)
        r = land(1.05, z, 75)
        bl = land(-1.05, z, 1)
        br = land(1.05, z, 1)
        g.polygon([l, r, br, bl], fill=rgba('#152838', .17 * alpha))
        for i in range(1, 34):
            u = i / 34
            x = mix(l[0], r[0], u)
            g.line((x, l[1] + 2, x, bl[1]), fill=rgba('#badbcb', .25 * alpha))
        for i in range(1, 7):
            y = mix(l[1], bl[1], i / 7)
            g.line((l[0], y, r[0], y), fill=rgba('#c1e7d8', .25 * alpha))
        g.line([l, r], fill=rgba('#dcfff2', .79 * alpha), width=3)
        for a, b in ((l, bl), (r, br)):
            g.line([a, b], fill=rgba('#aee3d7', .93 * alpha), width=4)
            g.ellipse((a[0] - 3, a[1] - 3, a[0] + 3, a[1] + 3), fill=rgba('#ffe1a9', alpha))

    def _desk(self, img, match, offset, working, seated=False):
        if offset >= .995:
            return
        now = match.now
        annoyed_active = seated and now < getattr(match, 'annoyed_until', -100.)
        react_at = getattr(match, 'poke_react_at', -100.)
        # 戳到后先有一个小缓冲停顿，再缓缓转过头露出烦躁表情
        buffering = annoyed_active and now < react_at
        ramp = ease((now - react_at) / .45) if (annoyed_active and not buffering) else 0.
        annoyed = annoyed_active and ramp > .25
        shake_x = round(sin(now * 16.) * 1.8 * ramp) if annoyed else 0
        shake_y = round(cos(now * 13.) * 0.9 * ramp) if annoyed else 0
        x = 855 + 249 * offset + shake_x
        y = 596 - 32 * offset + shake_y
        layer = self.desk_layer
        layer.paste((0, 0, 0, 0), (0, 0, 105, 96))
        d = ImageDraw.Draw(layer)
        draw_desk(d, now, working and not annoyed, True)
        if seated:
            if annoyed:
                # 缓冲完成后转过头来瞪眼皱眉，表现被球拍戳到后很烦躁的样子
                draw_codex(d, 41, 83, now, 'sigh', False, facing=-1, stride=False)
                # 补画皱起的愤怒八字眉和红晕烦躁表情
                d.line([(29, 44), (35, 47)], fill='#3a1d28', width=2)
                d.line([(41, 44), (36, 47)], fill='#3a1d28', width=2)
                d.rectangle((29, 49, 32, 51), fill='#f472b6')
            else:
                draw_codex(d, 41, 83, now, 'work', working and not buffering)
        layer = layer.resize((196, 179), Image.Resampling.NEAREST)
        img.alpha_composite(layer, (round(x - 84), round(y - 156)))
        if annoyed:
            g = ImageDraw.Draw(img, 'RGBA')
            _draw_anger_mark(g, x + 22, y - 134, 1.1)
            bubble = getattr(match, 'codex_bubble', '') or '别戳啦，正忙着呢…'
            _draw_speech_bubble(g, x - 28, y - 158, bubble, border='#fb7185', fill='#231021', text_fill='#ffe4e6')

    def _actor(self, img, match):
        x, z = match.actor
        px, py, s = project(x, z)
        age = match.now - match.since
        swing = match.now - match.swing_at
        moving = hypot(x - match.actor_goal[0], z - match.actor_goal[1]) > .065
        angry = match.now < getattr(match, 'angry_until', -100.)
        if match.phase == 'clear':
            px, py = 855 + 249 * match.desk_offset, 596 - 32 * match.desk_offset
            if age >= 1.28:
                move = ease((age - 1.28) / .57)
                nx, ny, s = project(0, .78)
                px, py = mix(px, nx, move), mix(py, ny, move)
            pose = 'push_desk_move' if age < 1.28 else 'move_run'
        elif match.phase == 'quit':
            pose = 'rally_angry' if age < .48 else 'move_run'
            if age > .48:
                rx, ry, _ = project(*match.throw_from)
                q = ease((age - .48) / 1.9)
                px, py = mix(rx, 842, q), mix(ry, 588, q)
        elif match.phase == 'charge':
            pose = 'evil_remote'
        elif swing < .35:
            pose = 'hit_swing'
        elif angry and not moving:
            pose = 'rally_angry'
        elif moving:
            pose = 'move_run'
        elif match.fatigue > .62:
            pose = 'rally_tired'
        else:
            pose = 'ready_wait'
        g = ImageDraw.Draw(img, 'RGBA')
        layer = Image.new('RGBA', (234, 168))
        draw_badminton_codex(ImageDraw.Draw(layer), 116, 132, match.now, {
            'pose': pose,
            'outfit': 'work' if match.phase == 'clear' or (match.phase == 'quit' and age > .48) else 'sport',
            'facing': 1 if (match.phase == 'quit' and age > .48) or match.phase == 'clear' else match.swing_face,
            'front': pose in ('ready_wait', 'rally_angry', 'rally_tired', 'evil_remote'),
            'has_racket': match.phase not in ('clear', 'quit'),
            'swing_progress': clamp(swing / .35),
            'hide_name': True,
            'remote_visible': match.phase == 'charge',
        }, scale=2.8 * s)
        img.alpha_composite(layer, (round(px) - 116, round(py) - 132))
        if angry and match.phase in ('rally', 'charge', 'barrage'):
            _draw_anger_mark(g, px + 26 * s, py - 95 * s, max(.9, 1.1 * s))
        if getattr(match, 'codex_bubble', '') and match.now < getattr(match, 'codex_bubble_until', -100.):
            _draw_speech_bubble(g, px, py - 102 * s, match.codex_bubble,
                                border='#fb923c' if angry else '#38bdf8',
                                fill='#1e1424' if angry else '#0f1c2e',
                                text_fill='#fef08a' if angry else '#f8fafc')
        if 0 <= swing < .24 and match.phase not in ('quit', 'clear'):
            q = swing / .24
            g.arc((px - 44, py - 69, px + 44, py - 12), 203 + 72 * q, 233 + 120 * q,
                  fill=rgba('#fff0b4', .83 * (1 - q)), width=2)
        if match.phase == 'quit' and age < .84:
            u = clamp(age / .84)
            rx, ry, _ = project(*match.throw_from)
            xx, yy = rx + 95 * u, ry - 40 - 60 * u + 98 * u * u
            a = -.8 + u * tau
            end = (xx + 17 * cos(a), yy + 17 * sin(a))
            g.line(((xx, yy), end), fill='#e7c7a0', width=2)
            g.ellipse((end[0] - 6, end[1] - 5, end[0] + 6, end[1] + 5), outline='#f78382', width=2)

    def _shuttle(self, g, match, ball):
        t = match.now
        x, y, s = match.shot_points(ball)
        prev = project(*ball.position(t - .025))
        ahead = project(*ball.position(t + .025))
        dx, dy = ahead[0] - prev[0], ahead[1] - prev[1]
        a = atan2(dy, dx)
        px, py, _ = project(*ball.position(t)[:2])
        if py > 364:
            glow(g, px, py, 18 * s, 5 * s, '#0e2530', .62)
        is_hot = getattr(ball, 'hot', False) or ball.power >= SMASH_POWER
        color = '#ff7b00' if is_hot else (PALETTE[(round(ball.at * 9)) % len(PALETTE)] if ball.tail else '#bceedd')
        if ball.tail:
            n = 28
            points = [project(*ball.position(max(ball.at, t - i * .018)))[:2] for i in range(n)]
            phase = ball.at * 17
            palette = FIRE_PALETTE if is_hot else PALETTE
            for band in range(3):
                strip = []
                for i in range(n):
                    p = i / (n - 1)
                    ax, ay = points[i]
                    bx, by = points[min(i + 1, n - 1)]
                    if i == n - 1 or hypot(ax - bx, ay - by) < .05:
                        ax0, ay0 = points[max(0, i - 1)]
                        vx, vy = ax0 - ax, ay0 - ay
                    else:
                        vx, vy = ax - bx, ay - by
                    norm = max(.001, hypot(vx, vy))
                    nx, ny = -vy / norm, vx / norm
                    curl = sin(phase + band * 2.09 + p * 7.9 + t * 3.4)
                    offset = (13. if is_hot else (11.5 if band != 1 else 8.5)) * s * sin(p * pi * .92) * curl
                    half = ((4.8 if band == 1 else 3.4) if is_hot else (2.9 if band != 1 else 4.0)) * s * (1 - p) ** .82 + .25
                    strip.append(((ax + nx * (offset + half), ay + ny * (offset + half)),
                                  (ax + nx * (offset - half), ay + ny * (offset - half))))
                tone = palette[(round(ball.at * 9) + band * 2) % 5]
                for i in range(n - 2, -1, -1):
                    alpha = (.86 if is_hot else (.79 if band == 1 else .66)) * (1 - i / (n - 1)) ** .79
                    g.polygon([strip[i][0], strip[i][1], strip[i + 1][1], strip[i + 1][0]], fill=rgba(tone, alpha))
        else:
            for i in range(6, 0, -1):
                p = project(*ball.position(max(ball.at, t - i * .018)))
                rr = (1.6 + (6 - i) * .31) * s
                g.ellipse((p[0] - rr, p[1] - rr, p[0] + rr, p[1] + rr), fill=rgba(color, (7 - i) * .061))
        glow(g, x, y, (22 if is_hot else 16) * s, (18 if is_hot else 14) * s, color, .52 if is_hot else .36)
        u, v = cos(a) * s, sin(a) * s

        def rot(i, j):
            return x + i * u - j * v, y + i * v + j * u

        g.polygon([rot(1, -4), rot(-13, -9), rot(-16, -6), rot(-15, 0), rot(-16, 6), rot(-13, 9), rot(1, 4)],
                  fill='#fff5df', outline='#6e6873')
        for q in (-5, 0, 5):
            g.line([rot(-13, q), rot(-2, q * .46)], fill='#bbbfba', width=1)
        g.polygon([rot(0, -4), rot(5, -3), rot(8, 0), rot(5, 3), rot(0, 4)], fill=color, outline='#7d655c')
        g.point(rot(4, -1), fill='#ffffff')

    @staticmethod
    def bones(g, points, alpha, scale=1.):
        # 萌系晴空蓝运动手套皮肤：饱满圆润手指 + 运动护腕 + 掌心垫，消除冷色调骷髅感并保留清晰的指关节识别点
        finger_segs = ((1, 2, 3, 4), (5, 6, 7, 8), (9, 10, 11, 12), (13, 14, 15, 16), (17, 18, 19, 20))
        palm_ring = [points[i] for i in (0, 1, 5, 9, 13, 17)]
        palm_loop = palm_ring + [palm_ring[0]]
        border_col = rgba('#1e3a5f', .95 * alpha)
        glove_col = rgba('#38bdf8', .96 * alpha)
        glove_hi = rgba('#7dd3fc', .78 * alpha)
        w_out = max(7, round(11.6 * scale))
        r_out = w_out * .5
        w_in = max(4, round(7.6 * scale))
        r_in = w_in * .5

        # 1. 手背与指套外描边轮廓（去掉掌内射线骨刺，手指更饱满圆润）
        g.polygon(palm_ring, fill=border_col)
        g.line(palm_loop, fill=border_col, width=w_out, joint='curve')
        for x, y in palm_ring:
            g.ellipse((x - r_out, y - r_out, x + r_out, y + r_out), fill=border_col)
        for seg in finger_segs:
            pts = [points[i] for i in seg]
            g.line(pts, fill=border_col, width=w_out, joint='curve')
            for x, y in pts:
                g.ellipse((x - r_out, y - r_out, x + r_out, y + r_out), fill=border_col)

        # 2. 晴空蓝手套主体填充 + 柔和指背立体高光
        g.polygon(palm_ring, fill=glove_col)
        g.line(palm_loop, fill=glove_col, width=w_in, joint='curve')
        for x, y in palm_ring:
            g.ellipse((x - r_in, y - r_in, x + r_in, y + r_in), fill=glove_col)
        for seg in finger_segs:
            pts = [points[i] for i in seg]
            g.line(pts, fill=glove_col, width=w_in, joint='curve')
            for x, y in pts:
                g.ellipse((x - r_in, y - r_in, x + r_in, y + r_in), fill=glove_col)
            g.line(pts, fill=glove_hi, width=max(2, round(3.0 * scale)), joint='curve')

        # 掌心柔和渐变垫与指根弧线缝合线
        g.line([points[i] for i in (5, 9, 13, 17)], fill=rgba('#bae6fd', .68 * alpha), width=max(1, round(1.8 * scale)))
        pcx = sum(points[i][0] for i in PALM) / len(PALM)
        pcy = sum(points[i][1] for i in PALM) / len(PALM)
        pad_r = max(5.5, hypot(points[9][0] - points[0][0], points[9][1] - points[0][1]) * .26)
        g.ellipse((pcx - pad_r, pcy - pad_r, pcx + pad_r, pcy + pad_r),
                  fill=rgba('#bae6fd', .88 * alpha), outline=rgba('#0284c7', .72 * alpha), width=max(1, round(1.4 * scale)))

        # 3. 运动风深蓝金边护腕袖口
        wx, wy = points[0]
        mx, my = points[9]
        ang = atan2(my - wy, mx - wx)
        px, py = -sin(ang), cos(ang)
        ux, uy = cos(ang), sin(ang)
        cuff_half = max(8.0, pad_r * 1.25)
        cuff_a = (wx - px * cuff_half, wy - py * cuff_half)
        cuff_b = (wx + px * cuff_half, wy + py * cuff_half)
        g.line([cuff_a, cuff_b], fill=rgba('#1e3a5f', .96 * alpha), width=max(7, round(9.6 * scale)))
        g.line([cuff_a, cuff_b], fill=rgba('#2563eb', .96 * alpha), width=max(5, round(6.8 * scale)))
        g.line([(cuff_a[0] + ux * 1.6, cuff_a[1] + uy * 1.6), (cuff_b[0] + ux * 1.6, cuff_b[1] + uy * 1.6)],
               fill=rgba('#fbbf24', .98 * alpha), width=max(2, round(2.4 * scale)))

        # 4. 柔和易辨的指关节光点（无机械暗框）+ 暖金萌感指尖垫
        tip_set = {4, 8, 12, 16, 20}
        for i, (x, y) in enumerate(points):
            if i == 0:
                continue
            if i in tip_set:
                rt = max(2.6, 3.1 * scale)
                g.ellipse((x - rt - .8, y - rt - .8, x + rt + .8, y + rt + .8), fill=rgba('#0369a1', .85 * alpha))
                g.ellipse((x - rt, y - rt, x + rt, y + rt), fill=rgba('#fef08a', .98 * alpha))
            else:
                rj = max(1.4, 1.8 * scale)
                g.ellipse((x - rj, y - rj, x + rj, y + rj), fill=rgba('#f0f9ff', .92 * alpha))

    def _hand(self, g, match, hand, hand_mode='hands'):
        if hand.visibility <= .015 or not hand.points:
            return
        alpha = hand.visibility
        if hand_mode == 'racket':
            cx, cy, ang, tx, ty = racket_tip_for_hand(hand)
            # 在透明度支持图层上画一支清晰的发光羽毛球拍
            glow(g, tx, ty, 30, 24, '#38bdf8', .26 * alpha)
            racket_layer = Image.new('RGBA', (160, 160), (0, 0, 0, 0))
            rg = ImageDraw.Draw(racket_layer)
            cos_a, sin_a = cos(ang), sin(ang)
            ox, oy = 60, 80

            def rrot(px, py):
                return (round(ox + px * cos_a - py * sin_a), round(oy + px * sin_a + py * cos_a))

            # 手柄与中杆
            rg.line([rrot(-14, 0), rrot(6, 0)], fill=rgba('#1e293b', alpha), width=6)
            rg.line([rrot(-12, 0), rrot(2, 0)], fill=rgba('#f59e0b', alpha), width=4)
            rg.line([rrot(6, 0), rrot(26, 0)], fill=rgba('#e2e8f0', alpha), width=3)
            # 拍框外圈与网格
            rx_h, ry_h = 22, 16
            head_c = 44
            outer = [rrot(head_c + cos(i * tau / 18) * rx_h, sin(i * tau / 18) * ry_h) for i in range(18)]
            rg.polygon(outer, outline=rgba('#ef4444', alpha), width=4)
            for dx in range(-14, 16, 7):
                span_y = ry_h * (max(.1, 1 - (dx / rx_h) ** 2)) ** .5 - 2
                rg.line([rrot(head_c + dx, -span_y), rrot(head_c + dx, span_y)], fill=rgba('#f8fafc', .85 * alpha), width=1)
            for dy in range(-10, 12, 5):
                span_x = rx_h * (max(.1, 1 - (dy / ry_h) ** 2)) ** .5 - 2
                rg.line([rrot(head_c - span_x, dy), rrot(head_c + span_x, dy)], fill=rgba('#f8fafc', .85 * alpha), width=1)
            rg.polygon(outer, outline=rgba('#38bdf8', .9 * alpha), width=2)
            r_layer_x = round(cx - ox)
            r_layer_y = round(cy - oy)
            g._image.alpha_composite(racket_layer, (r_layer_x, r_layer_y))
            # 挥拍闪光弧线与拍头判定中心微光
            p = clamp((match.now - match.player_at) / .29)
            if p < 1.:
                r = 26 + 22 * ease(p)
                g.arc((tx - r, ty - r, tx + r, ty + r), -45 + 110 * p, 95 + 110 * p,
                      fill=rgba('#ffd166', alpha * (1 - p)), width=4)
                g.arc((tx - r * .8, ty - r * .8, tx + r * .8, ty + r * .8), 135 + 110 * p, 265 + 110 * p,
                      fill=rgba('#73ffe4', alpha * (1 - p)), width=3)
            g.ellipse((tx - 4, ty - 4, tx + 4, ty + 4), outline=rgba('#fde047', .72 * alpha), width=2)
            return

        cx, cy = player_point(hand.palm)
        points, scale_k = hand_skeleton_points(hand)
        self.bones(g, points, alpha, clamp(.85 + .15 * scale_k, .85, 1.))
        p = clamp((match.now - match.player_at) / .29)
        if p < 1.:
            radius = 15 + 14 * ease(p)
            for start in (12, 192):
                g.arc((cx - radius, cy - radius, cx + radius, cy + radius), start, start + 156,
                      fill=rgba('#fde047', alpha * (1. - p)), width=3)
        g.ellipse((cx - 2.5, cy - 2.5, cx + 2.5, cy + 2.5), fill=rgba('#fef08a', alpha * .95),
                  outline=rgba('#0369a1', alpha * .85), width=1)

    def _effects(self, g, match):
        for at, pos, kind, power, seed in match.effects:
            age = match.now - at
            if kind == 'poke':
                x, y = pos[0], pos[1]
                p = clamp(age / .75)
                r = 12 + 34 * ease(p)
                for i in range(10):
                    a = tau * (i / 10 + seed)
                    d0 = r * .35
                    d1 = r * (1.05 if i % 2 == 0 else .72)
                    g.line([(x + cos(a) * d0, y + sin(a) * d0), (x + cos(a) * d1, y + sin(a) * d1)],
                           fill=rgba('#ff4d6d' if i % 2 == 0 else '#ffd166', .95 * (1 - p)), width=3)
                g.ellipse((x - r * .5, y - r * .5, x + r * .5, y + r * .5),
                          outline=rgba('#fff3b0', .85 * (1 - p)), width=2)
                continue

            x, y, s = project(*pos)
            if kind == 'score_drop':
                p = clamp(age / 1.25)
                rise_y = y - 16 - 54 * ease(p)
                fade = clamp(1. - max(0., p - .35) / .65)
                f = font(round(26 + 4 * (1 - p)))
                label = '-1'
                for ox, oy in ((-2, 0), (2, 0), (0, -2), (0, 2), (-2, -2), (2, 2)):
                    g.text((x + ox, rise_y + oy), label, anchor='mm', font=f, fill=rgba('#1a080d', fade))
                g.text((x, rise_y), label, anchor='mm', font=f, fill=rgba('#ff3b30', fade))
                g.text((x + 24, rise_y - 2), '💥', anchor='mm', font=font(18), fill=rgba('#ffd166', fade))
                continue

            if kind in ('smash', 'blast'):
                dur = 1.25 if kind == 'blast' else 1.15
                p = clamp(age / dur)
                scale_k = 1.55 if kind == 'blast' else 1.28
                r = (14 + 82 * ease(p)) * max(.65, s) * scale_k
                # 炽热爆裂双冲击波光环
                g.ellipse((x - r, y - r * .88, x + r, y + r * .88),
                          outline=rgba('#ff9f1c' if kind == 'blast' else '#ffd166', .94 * (1 - p) ** 1.4), width=3)
                r_in = r * .62
                g.ellipse((x - r_in, y - r_in * .88, x + r_in, y + r_in * .88),
                          outline=rgba('#ff3b30', .92 * (1 - p) ** 1.2), width=2)
                if p < .22:
                    flash_r = 22 * (1 - p / .22) * max(.7, s)
                    g.ellipse((x - flash_r, y - flash_r, x + flash_r, y + flash_r),
                              fill=rgba('#fff8dc', .82 * (1 - p / .22)))
                n_sparks = 18 if kind == 'blast' else 14
                for i in range(n_sparks):
                    a = tau * (i / n_sparks + seed)
                    d = (.48 + ((i * 29) % 11) * .065) * r
                    ex = x + cos(a) * d
                    ey = y + sin(a) * d + (34 * p * p)
                    col = FIRE_PALETTE[i % len(FIRE_PALETTE)]
                    g.line((ex, ey, ex - cos(a) * 14 * (1 - p), ey - sin(a) * 14 * (1 - p)),
                           fill=rgba(col, .96 * (1 - p)), width=3 if i % 2 == 0 else 2)
                    g.ellipse((ex - 2.5, ey - 2.5, ex + 2.5, ey + 2.5),
                              fill=rgba('#fff3b0', .92 * (1 - p)))
                if p < .55:
                    tag = 'SMASH!' if kind == 'smash' else '暴击破防!'
                    self._caption(g, x, y - 28 * max(.7, s) - 18 * p, tag, 15 if kind == 'smash' else 14)
                continue

            p = clamp(age / .67)
            if kind == 'miss':
                r = (6 + 51 * ease(p)) * s
                g.ellipse((x - r, y - r * .23, x + r, y + r * .23), outline=rgba('#ffbd8a', .57 * (1 - p)), width=2)
                continue
            r = (9 + 67 * ease(p)) * s * .83
            g.ellipse((x - r, y - r, x + r, y + r), outline=rgba(MINT, .88 * (1 - p) ** 2), width=2)
            for i in range(7):
                a = tau * (i / 7 + seed)
                d = (.66 + (i * 29 % 9) * .085) * r
                ex = x + cos(a) * d
                ey = y + sin(a) * d + 28 * p * p
                g.line((ex, ey, ex - cos(a) * 9 * (1 - p), ey - sin(a) * 9 * (1 - p)),
                       fill=rgba('#fff4bf', .92 * (1 - p)), width=2)

    def _scoreboard(self, g, match):
        if match.phase not in ('clear', 'rally', 'charge', 'barrage'):
            return
        ps = getattr(match, 'player_score', 0)
        cs = getattr(match, 'codex_score', 5)
        cmax = max(1, getattr(match, 'codex_max_score', 5))
        rage = match.phase in ('charge', 'barrage') or cs <= 0
        x0, y0, x1, y1 = 768, 22, 998, 86
        border = '#ef4444' if rage else '#38bdf8'
        g.rounded_rectangle((x0, y0, x1, y1), radius=10,
                            fill=rgba('#091322', .78), outline=rgba(border, .90), width=2)
        title = f'你 {ps}  :  {cs} Codex'
        g.text(((x0 + x1) / 2, y0 + 18), title, anchor='mm', font=font(15),
               fill='#fde047' if not rage else '#fda4af')
        # 绘制 Codex 剩余分数能量格 (扣到 0 分即暴怒七连发)
        pip_w, gap = 22, 6
        total_w = cmax * pip_w + (cmax - 1) * gap
        sx = (x0 + x1 - total_w) / 2
        py = y0 + 36
        for i in range(cmax):
            px0 = sx + i * (pip_w + gap)
            alive = i < cs
            g.rounded_rectangle((px0, py, px0 + pip_w, py + 7), radius=3,
                                fill=rgba('#4ade80' if cs > 2 else '#fb923c', .95) if alive else rgba('#334155', .65))
        sub = '⚠️ Codex 破防开挂！连发七球！' if rage else f'杀球扣 Codex 分 (剩 {cs} 分开挂)'
        g.text(((x0 + x1) / 2, y0 + 54), sub, anchor='mm', font=font(11),
               fill='#fca5a5' if rage else '#bae6fd')

    def frame(self, match, hand, note='', hand_mode='hands'):
        # 仅保留透明前景精灵与清晰HUD提示，无任何不透明背景遮挡桌面
        img = Image.new('RGBA', (W, H))
        g = ImageDraw.Draw(img, 'RGBA')
        age = match.now - match.since
        if match.phase == 'desk':
            self._desk(img, match, 0., True, True)
        else:
            if match.phase == 'clear':
                self._desk(img, match, match.desk_offset, False, age < .26)
            elif match.phase == 'quit' and match.desk_offset < .99:
                self._desk(img, match, match.desk_offset, False)
            if match.phase != 'clear' or age >= .26:
                self._actor(img, match)
        for ball in match.shots:
            if ball.position(match.now)[1] >= .5:
                self._shuttle(g, match, ball)
        self._net(g, match.clear_court)
        for ball in match.shots:
            if ball.position(match.now)[1] < .5:
                self._shuttle(g, match, ball)
            if ball.towards == 'player':
                prog = ball.progress(match.now)
                if match.cue(ball):
                    x, y, _ = match.shot_points(ball)
                    r = 24 + 4 * sin(match.now * 14)
                    for start in (-32, 148):
                        g.arc((x - r, y - r, x + r, y + r), start, start + 92, fill=rgba('#4ade80', .96), width=3)
                    r2 = r + 7
                    g.ellipse((x - r2, y - r2, x + r2, y + r2), outline=rgba('#fde047', .72), width=2)
                    self._caption(g, x, y + r2 + 6, '快挥拍扣杀!', 11)
                elif .42 <= prog < .66:
                    x, y, _ = match.shot_points(ball)
                    r = 16 + 18 * (1 - (prog - .42) / .24)
                    g.ellipse((x - r, y - r, x + r, y + r), outline=rgba('#38bdf8', .48), width=2)
        self._effects(g, match)
        self._hand(g, match, hand, hand_mode=hand_mode)
        self._scoreboard(g, match)
        if note:
            self._caption(g, 845, 638, note, 12)
        if match.phase == 'quit' and age < 1.25:
            px, py, _ = project(*match.throw_from)
            self._caption(g, px, py - 82, '不打了！', 17)
        return img

    @staticmethod
    def _caption(g, x, y, note, size):
        g.text((x, y), note, anchor='ma', font=font(size), fill='#eefff1',
               stroke_width=2, stroke_fill='#183439')
