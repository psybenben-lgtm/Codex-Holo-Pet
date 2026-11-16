"""The transparent Windows Codex desk pet for the coffee handoff."""
import ctypes
from ctypes import wintypes
import json
import logging
from pathlib import Path
import sys
import threading
import time
import tkinter as tk
from urllib.request import Request
import webbrowser
import winsound

from PIL import Image, ImageDraw, ImageFont, ImageTk

from coffee_work import work_states
from local_runtime import get_local_host_url, get_no_proxy_opener

CHAT_PROMPTS = (
    '你要给我倒咖啡吗？☕',
    '点下面切模式：咖啡 / 搓澡 / 羽毛球！',
    '打字太快我可是要去全息盒罢工搓澡的～🛁',
    '不用摄像头，用鼠标也能和我打羽毛球！🏸',
)

HOST = get_local_host_url()
HTTP_OPENER = get_no_proxy_opener()
KEY = '#010102'
VOICE = Path(__file__).with_name('coffee') / 'thanks.wav'
WIDTH, HEIGHT = 172, 92
WORKSPACE = Path(__file__).resolve().parent

# 加载加粗字体以实现清晰的黄色黑边名字
try:
    FONT_LABEL = ImageFont.truetype('arialbd.ttf', 11)
except Exception:
    FONT_LABEL = ImageFont.load_default()


def draw_outlined_text(draw, x, y, text, fill='#ffdc38', outline='#080909', font=FONT_LABEL):
    """8 邻域加粗描边，确保黄色文字带有清晰浓密的纯黑描边"""
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx or dy:
                draw.text((x + dx, y + dy), text, fill=outline, font=font)
    draw.text((x, y), text, fill=fill, font=font)


def post(action, data):
    request = Request(f'{HOST}/coffee/{action}', json.dumps(data).encode(),
                      {'Origin': HOST, 'Content-Type': 'application/json'})
    with HTTP_OPENER.open(request, timeout=2) as response:
        return json.load(response)


def ease(t):
    t = max(0, min(1, t))
    return t * t * (3 - 2 * t)


def draw_cup(draw, x, y, fill=True):
    draw.polygon([(x-6,y-2),(x+4,y-2),(x+7,y),(x+5,y+7),(x-4,y+7),(x-6,y+4)], fill='#a9d2c5')
    draw.rectangle((x+7,y,x+9,y+4), outline='#88b9b7')
    draw.polygon([(x-4,y),(x+5,y),(x+4,y+5),(x-3,y+5)], fill='#a8693a' if fill else '#344b57')
    if fill:
        draw.line((x-4,y+1,x+5,y+1), fill='#efc48c')
    draw.line((x-4,y-2,x+4,y-2), fill='#e5f4dd')


def draw_desk(draw, t, working, coffee):
    draw.polygon([(13,52),(68,52),(75,59),(12,59)], fill='#ad7161')
    draw.rectangle((12,59,75,63), fill='#774857')
    draw.rectangle((15,63,18,81), fill='#684153')
    draw.rectangle((69,63,73,81), fill='#684153')
    draw.rectangle((58,64,68,77), fill='#855363')
    draw.line((59,71,67,71), fill='#4c3245')
    draw.line((61,67,64,67), fill='#c88a6e')
    draw.line((61,74,64,74), fill='#c88a6e')
    draw.rectangle((35,46,39,53), fill='#5f536a')
    draw.rectangle((29,51,46,53), fill='#5f536a')
    draw.rounded_rectangle((18,27,54,47), radius=2, fill='#786078', outline='#372f49')
    draw.rectangle((21,30,51,44), fill='#1f3746')
    beat = int(t * 12) % 24
    active_line = (beat // 6) % 3 if working else -1
    for i, color in enumerate(('#75c8b0','#c79680','#9ab6cf')):
        y = 33 + i*4
        draw.line((24,y,29,y), fill='#577689')
        end = 36 + beat % 6 * 2 if i == active_line else 45 - i * 3
        draw.line((32,y,end,y), fill=color)
        if i == active_line:
            draw.rectangle((end+1,y-1,end+2,y+1), fill='#d0f4bd')
    if working:
        draw.point((49,31), fill='#a0e8b9')
    draw.rectangle((29,55,53,57), fill='#443a4c')
    draw.line((30,55,52,55), fill='#e9cbb7')
    draw.line([(64,52),(66,41),(71,37)], fill='#a27577', width=2)
    draw.polygon([(69,35),(76,35),(80,40),(66,40)], fill='#edb57b')
    draw.line((67,40,79,40), fill='#ffe2ad')
    draw.line((62,52,69,52), fill='#c28b74', width=2)
    if coffee:
        draw_cup(draw,57,47)


def draw_codex(draw, x, y, t, pose, working, facing=1, stride=True):
    def polygon(points, color):
        draw.polygon([(x+facing*px,y+py) for px,py in points], fill=color)

    def rect(x1,y1,x2,y2,color):
        a,b=sorted((x+facing*x1,x+facing*x2))
        draw.rectangle((a,y+y1,b,y+y2), fill=color)

    back = pose == 'work'
    beat = int(t * 12) % 24
    step = int(t*9)%4-2 if pose == 'walk' and stride else 0
    if back:
        rect(-11,-15,11,-2,'#483749')
        rect(-11,-16,11,-13,'#a3696b')
        rect(-7,-2,-5,2,'#574353'); rect(5,-2,7,2,'#574353')
        if working and 5 <= beat < 18:
            y -= 1
    else:
        rect(-6,-11,-1,-2+step,'#363751'); rect(2,-11,7,-2-step,'#4a435c')
        rect(-8,-3+step,-1,-1+step,'#987582'); rect(2,-3-step,9,-1-step,'#b48b87')
    polygon([(-9,-26),(-5,-30),(7,-30),(11,-26),(10,-10),(-8,-10)],'#566f9b')
    rect(-7,-27,7,-24,'#85a8c3'); rect(-7,-13,9,-11,'#3e537b')
    rect(-4,-26,4,-22,'#3d4b6a'); rect(-2,-25,2,-24,'#b2cad5')
    if back:
        left_tap = working and beat in (0, 3, 4, 8, 12, 15, 18)
        right_tap = working and beat in (1, 5, 6, 10, 13, 16, 19)
        for side, tapping, sleeve, skin in ((-1, left_tap, '#779abc', '#dca58e'),
                                           (1, right_tap, '#87a8c5', '#e8b69a')):
            hand_x = side * (9 if tapping else 14)
            hand_y = -33 if tapping else -29
            polygon([(side*10,-19),(side*16,-21),(hand_x+side*2,hand_y),
                     (hand_x-side*2,hand_y+2)], sleeve)
            rect(hand_x-2,hand_y-2,hand_x+2,hand_y+1,skin)
            if tapping:
                rect(hand_x-1,hand_y-3,hand_x+1,hand_y-2,'#f2d394')
    else:
        rect(-12,-26,-9,-17,'#7896b9'); rect(-12,-18,-9,-15,'#cb8e7c')
        aim = {'catch':(18,-19),'sip':(11,-31),'phone':(13,-25),
               'sigh':(12,-15),'walk':(12-step,-19-step)}.get(pose,(13,-18))
        polygon([(7,-26),(11,-26),(aim[0]+1,aim[1]),(aim[0]-2,aim[1]+3),(8,-20)],'#80a3bf')
        rect(aim[0]-1,aim[1]-1,aim[0]+2,aim[1]+1,'#e5ad8b')
    polygon([(-10,-43),(-6,-47),(5,-47),(10,-43),(11,-35),(7,-30),(-7,-30),(-11,-35)],'#392e48')
    polygon([(-8,-42),(-5,-45),(5,-45),(9,-42),(8,-39),(-9,-38)],'#63506b')
    rect(-5,-45,3,-44,'#9e7080'); rect(-10,-38,-8,-34,'#d99a88')
    rect(8,-38,10,-34,'#e1a589'); rect(-4,-31,5,-30,'#ca8e7e')
    if not back:
        polygon([(3,-40),(8,-41),(11,-37),(13,-35),(10,-32),(4,-32)],'#e9b296')
        rect(8,-37,9,-36,'#42364c')
        if pose == 'sigh':
            rect(9,-34,11,-32,'#6c3d47')
        else:
            rect(9,-33,11,-33,'#b57473')

    # 头顶绘制黄色黑边的 "codex" 名字
    name_x = x - 18 if pose == 'walk' else max(2, min(WIDTH - 38, x - 18))
    draw_outlined_text(draw, name_x, y - 62, 'codex', fill='#ffdc38', outline='#080909')


def render(t, since, working):
    image = Image.new('RGB', (WIDTH,HEIGHT), KEY)
    draw = ImageDraw.Draw(image)
    draw_desk(draw,t,working,since>=2.22)
    if -1.34 <= since < .03:
        p = ease((since+1.27)/1.04)
        x,y = round(41+111*p),round(85-3*p)
        draw_codex(draw,x,y,t,'walk' if since<-.23 else 'catch',working)
        if since>=-.1:
            draw_cup(draw,round(180-11*ease((since+.1)/.13)),63)
    elif .03 <= since < 1.28:
        p = ease((since-.08)/1.2)
        x = round(152-111*p)
        draw_codex(draw,x,84,t,'walk',working,-1)
        draw_cup(draw,x-15,65)
    elif 1.28 <= since < 2.22:
        draw_codex(draw,41,84,t,'sip',working)
        draw_cup(draw,54,49)
    else:
        draw_codex(draw,41,85,t,'work',working)
    if 1.52 <= since < 2.70:
        draw.rounded_rectangle((61,16,109,29),radius=2,fill='#f6d7af')
        draw.polygon([(61,26),(61,32),(68,28)],fill='#f6d7af')
        draw.text((66,16),'Thanks.',fill='#412b39')
    return image


class Pet:
    def __init__(self, show_requested):
        self.show_requested = show_requested
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title('Codex 咖啡桌宠')
        self.root.report_callback_exception = lambda *error: logging.error('Desktop pet callback failed', exc_info=error)
        area = wintypes.RECT()
        ctypes.windll.user32.SystemParametersInfoW(0x0030,0,ctypes.byref(area),0)
        self.work_area = (area.left, area.top, area.right, area.bottom)
        scale = 2 if area.right-area.left >= 900 else 1
        self.size = WIDTH*scale,HEIGHT*scale
        x = max(0, area.right - self.size[0] - 30)
        y = max(0, area.bottom - self.size[1] - 20)
        self.root.geometry(f'{self.size[0]}x{self.size[1]}+{x}+{y}')
        self.root.overrideredirect(True)
        self.root.attributes('-topmost',True)
        self.root.attributes('-transparentcolor',KEY)
        self.root.config(background=KEY)

        self.canvas = tk.Canvas(self.root,width=self.size[0],height=self.size[1],bg=KEY,highlightthickness=0)
        self.canvas.pack()
        self.sprite = self.canvas.create_image(0,0,anchor='nw')

        # 鼠标点击对话 & 拖拽移动支持（短按弹出互动对话气泡，按住拖动位置）
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._win_start_x = x
        self._win_start_y = y
        self._drag_moved = False
        self._chat_idx = 0
        self._chat_until = 0.0
        self._chat_win = None
        self._chat_lbl = None
        self._last_chat_seq = 0
        self._dock_win = None
        self._dock_expanded = True
        self._dock_body = None
        self._dock_btn_fold = None
        self._dock_btns = {}
        self.canvas.bind('<ButtonPress-1>', self.on_drag_start)
        self.canvas.bind('<B1-Motion>', self.on_drag_motion)
        self.canvas.bind('<ButtonRelease-1>', self.on_click_release)

        # 右键上下文菜单
        self.menu = tk.Menu(self.root,tearoff=0)
        self.menu.add_command(label='💬 戳一下小人聊天', command=self.cycle_chat)
        self.menu.add_command(label='☕ 切换：跨屏倒咖啡', command=lambda: self.switch_suite_mode('coffee'))
        self.menu.add_command(label='🛁 切换：挖土罢工与全息搓澡', command=lambda: self.switch_suite_mode('strike'))
        self.menu.add_command(label='🏸 切换：透明桌面羽毛球', command=lambda: self.switch_suite_mode('badminton'))
        self.menu.add_command(label='🌐 打开三合一网页工作台', command=lambda: webbrowser.open(HOST + '/'))
        self.menu.add_separator()
        self.menu.add_command(label='移到屏幕右下角', command=self.reset_to_corner)
        self.menu.add_command(label='移到屏幕正中央', command=self.center_on_screen)
        self.menu.add_separator()
        self.menu.add_command(label='重新倒一杯',command=lambda: self.send('reset',{'round':self.snapshot.get('round')}))
        self.menu.add_command(label='退出 Codex 桌宠',command=self.root.destroy)
        self.canvas.bind('<Button-3>',self.show_menu)

        self.snapshot = {}
        self.offset = 0
        self.spoken = None
        self.work = 'waiting'
        self.animation_origin = time.monotonic()
        self.android_coffee = True
        self._build_dock_bar()
        threading.Thread(target=self.listen,daemon=True).start()
        threading.Thread(target=self.follow_work,daemon=True).start()
        self.show_at_corner()
        self.show_chat('你要给我倒咖啡吗？☕（点击我或下方切换模式）', 5.5)
        self.root.after(0, self.tick)

    def _build_dock_bar(self):
        """左下角可折叠三合一快速切换条（与羽毛球悬浮条视觉统一，拍视频可收起）。"""
        win = tk.Toplevel(self.root)
        win.withdraw()
        win.overrideredirect(True)
        win.attributes('-topmost', True)
        win.configure(bg='#0f172a', highlightthickness=1, highlightbackground='#38bdf8')
        outer = tk.Frame(win, bg='#0f172a', padx=8, pady=6)
        outer.pack(fill='both', expand=True)

        hdr = tk.Frame(outer, bg='#0f172a')
        hdr.pack(fill='x')
        title = tk.Label(hdr, text='✨ Codex 三合一桌宠', fg='#38bdf8', bg='#0f172a',
                         font=('Microsoft YaHei UI', 9, 'bold'))
        title.pack(side='left', padx=(0, 8))
        btn_fold = tk.Button(hdr, text='⊟ 收起', bg='#1e293b', fg='#cbd5e1', relief='flat', bd=0,
                             padx=6, pady=2, cursor='hand2', font=('Microsoft YaHei UI', 8, 'bold'),
                             command=self._toggle_dock)
        btn_fold.pack(side='right')

        body = tk.Frame(outer, bg='#0f172a')
        body.pack(fill='x', pady=(6, 0))
        specs = [
            ('coffee', '☕ 倒咖啡', lambda: self.switch_suite_mode('coffee')),
            ('strike', '🛁 搓澡', lambda: self.switch_suite_mode('strike')),
            ('badminton', '🏸 羽毛球', lambda: self.switch_suite_mode('badminton')),
            ('chat', '💬 对话', self.cycle_chat),
            ('web', '🌐 工作台', lambda: webbrowser.open(HOST + '/')),
        ]
        for key, label, cmd in specs:
            b = tk.Button(body, text=label, bg='#1e293b', fg='#f8fafc', activebackground='#0284c7',
                          activeforeground='#ffffff', relief='flat', bd=0, padx=8, pady=4,
                          cursor='hand2', font=('Microsoft YaHei UI', 9, 'bold'), command=cmd)
            b.pack(side='left', padx=(0, 4))
            self._dock_btns[key] = b

        self._dock_win = win
        self._dock_body = body
        self._dock_btn_fold = btn_fold
        win.update_idletasks()
        _, _, _, bottom = self.work_area
        win.geometry(f'+16+{max(12, bottom - win.winfo_reqheight() - 16)}')
        win.deiconify()
        win.attributes('-topmost', True)

    def _toggle_dock(self):
        self._dock_expanded = not self._dock_expanded
        if self._dock_expanded:
            self._dock_body.pack(fill='x', pady=(6, 0))
            self._dock_btn_fold.config(text='⊟ 收起')
        else:
            self._dock_body.pack_forget()
            self._dock_btn_fold.config(text='⊞ 展开')
        self._dock_win.update_idletasks()
        _, _, _, bottom = self.work_area
        self._dock_win.geometry(f'+16+{max(12, bottom - self._dock_win.winfo_reqheight() - 16)}')

    def _refresh_dock_mode(self, mode_name):
        if not self._dock_btns:
            return
        for key in ('coffee', 'strike', 'badminton'):
            b = self._dock_btns.get(key)
            if b:
                active = (key == mode_name)
                b.config(bg='#0284c7' if active else '#1e293b', fg='#ffffff' if active else '#cbd5e1')

    def switch_suite_mode(self, target_mode):
        def run():
            try:
                req = Request(f'{HOST}/api/pet/mode', json.dumps({'mode': target_mode, 'spawn': True}).encode(),
                              {'Content-Type': 'application/json'})
                HTTP_OPENER.open(req, timeout=2.0).read()
            except OSError:
                pass
        threading.Thread(target=run, daemon=True).start()
        if target_mode == 'coffee':
            self.show_chat('已切到【跨屏倒咖啡】！用手机或工作台倒满杯吧 ☕', 4.0)
        elif target_mode == 'strike':
            self.show_chat('已切到【挖土罢工与全息搓澡】！不想读键盘可点工作台纯按钮触发 🛁', 4.0)

    def cycle_chat(self):
        msg = CHAT_PROMPTS[self._chat_idx % len(CHAT_PROMPTS)]
        self._chat_idx += 1
        self.show_chat(msg, 4.5)

    def show_chat(self, text, duration=4.2):
        self._chat_until = time.monotonic() + duration
        if not self._chat_win:
            w = tk.Toplevel(self.root)
            w.withdraw()
            w.overrideredirect(True)
            w.attributes('-topmost', True)
            lbl = tk.Label(w, text=text, bg='#fef9c3', fg='#0f172a',
                           font=('Microsoft YaHei UI', 9, 'bold'), padx=10, pady=5,
                           relief='solid', bd=1, wraplength=240, justify='left')
            lbl.pack()
            lbl.bind('<Button-1>', lambda _e: self.cycle_chat())
            self._chat_win = w
            self._chat_lbl = lbl
        else:
            self._chat_lbl.config(text=text)
        self._position_chat()

    def _position_chat(self):
        if not self._chat_win:
            return
        if time.monotonic() >= self._chat_until:
            self._chat_win.withdraw()
            return
        self._chat_win.update_idletasks()
        bw = self._chat_win.winfo_reqwidth()
        bh = self._chat_win.winfo_reqheight()
        left, top, right, _ = self.work_area
        px = max(left + 8, min(right - bw - 8, self.root.winfo_x() + self.size[0] // 2 - bw // 2))
        py = max(top + 8, self.root.winfo_y() - bh - 6)
        self._chat_win.geometry(f'+{px}+{py}')
        self._chat_win.deiconify()
        self._chat_win.attributes('-topmost', True)

    def on_drag_start(self, event):
        self._drag_start_x = event.x_root
        self._drag_start_y = event.y_root
        self._win_start_x = self.root.winfo_x()
        self._win_start_y = self.root.winfo_y()
        self._drag_moved = False

    def on_drag_motion(self, event):
        dx = event.x_root - self._drag_start_x
        dy = event.y_root - self._drag_start_y
        if abs(dx) >= 4 or abs(dy) >= 4:
            self._drag_moved = True
        self.root.geometry(f"+{self._win_start_x + dx}+{self._win_start_y + dy}")
        if self._chat_win and time.monotonic() < self._chat_until:
            self._position_chat()

    def on_click_release(self, _event):
        if not self._drag_moved:
            self.cycle_chat()

    def reset_to_corner(self):
        _, _, right, bottom = self.work_area
        x = max(0, right - self.size[0] - 30)
        y = max(0, bottom - self.size[1] - 20)
        self.root.geometry(f'{self.size[0]}x{self.size[1]}+{x}+{y}')

    def show_at_corner(self):
        self.reset_to_corner()
        self.root.deiconify()
        self.root.update_idletasks()
        user32 = ctypes.windll.user32
        user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        user32.GetAncestor.restype = wintypes.HWND
        user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                        ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
        hwnd = user32.GetAncestor(self.root.winfo_id(), 2)  # GA_ROOT: Tk's outer window
        flags = 0x0001 | 0x0002 | 0x0010 | 0x0040  # Keep size and position, show without focus
        if not hwnd or not user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, flags):
            self.root.lift()

    def center_on_screen(self):
        left, top, right, bottom = self.work_area
        x = max(0, left + (right - left - self.size[0]) // 2)
        y = max(0, top + (bottom - top - self.size[1]) // 2)
        self.root.geometry(f'{self.size[0]}x{self.size[1]}+{x}+{y}')

    def show_menu(self,event):
        try:
            self.menu.tk_popup(event.x_root,event.y_root)
        finally:
            self.menu.grab_release()

    def send(self,action,data):
        def run():
            try:
                post(action,data)
            except OSError:
                pass
        threading.Thread(target=run,daemon=True).start()

    def mode(self, coffee):
        self.android_coffee = coffee
        self.send('mode',{'coffee':coffee})

    def listen(self):
        threading.Thread(target=self._poll_coordinator, daemon=True).start()
        while True:
            try:
                started = time.time()*1000
                with HTTP_OPENER.open(f'{HOST}/coffee/clock',timeout=2) as response:
                    self.offset = json.load(response)['now']-(started+time.time()*1000)/2
                post('mode',{'coffee':self.android_coffee})
                with HTTP_OPENER.open(f'{HOST}/coffee/events',timeout=9) as response:
                    for line in response:
                        if line.startswith(b'data: '):
                            snap = json.loads(line[6:])
                            self.snapshot = snap
                            if snap.get('work') in ('working', 'idle', 'waiting'):
                                self.work = snap['work']
                            if snap.get('shutdown'):
                                cb = getattr(self, 'close', self.root.destroy)
                                self.root.after(0, cb)
                                return
            except (OSError,ValueError):
                pass
            time.sleep(1)

    def _poll_coordinator(self):
        last_mode_seq = -1
        while True:
            try:
                cur_mode = 'strike' if getattr(self, 'enabled', False) else 'coffee'
                req = Request(
                    f'{HOST}/api/pet/heartbeat',
                    json.dumps({'mode': cur_mode}).encode('utf-8'),
                    {'Content-Type': 'application/json'}
                )
                with HTTP_OPENER.open(req, timeout=1.2) as resp:
                    info = json.load(resp)
                if hasattr(self, 'on_coordinator_state'):
                    self.root.after(0, lambda d=info: self.on_coordinator_state(d, last_mode_seq))
                else:
                    self.root.after(0, lambda m=info.get('mode', 'coffee'): self._refresh_dock_mode(m))
                last_mode_seq = info.get('mode_seq', last_mode_seq)
                eff = info.get('effective_work')
                if eff in ('working', 'idle', 'waiting'):
                    self.work = eff
                c_seq = info.get('chat_seq', 0)
                if c_seq and c_seq != self._last_chat_seq:
                    self._last_chat_seq = c_seq
                    txt = info.get('chat_text') or CHAT_PROMPTS[0]
                    self.root.after(0, lambda t=txt: self.show_chat(t, 4.5))
            except (OSError, ValueError):
                pass
            time.sleep(0.45)

    def follow_work(self):
        for phase in work_states(WORKSPACE):
            if phase == 'working':
                self.animation_origin = time.monotonic()
            self.work = phase
            logging.info('Codex work phase: %s', phase)

    def tick(self):
        if self.show_requested():
            self.show_at_corner()
        self._position_chat()
        now = time.time()
        state = self.snapshot
        since = (now*1000+self.offset-state['lastLand']-1500)/1000 if state.get('sent',0)>=.8 else -float('inf')
        if 1.52 <= since < 1.85 and self.spoken != state.get('round'):
            self.spoken = state.get('round')
            winsound.PlaySound(str(VOICE), winsound.SND_FILENAME | winsound.SND_ASYNC)
        frame = render(time.monotonic()-self.animation_origin,since,self.work=='working')
        self.photo = ImageTk.PhotoImage(frame.resize(self.size,Image.Resampling.NEAREST))
        self.canvas.itemconfigure(self.sprite,image=self.photo)
        self.root.after(33,self.tick)


def main():
    log_file = Path(__file__).resolve().parent / 'coffee' / '.lan-certificate' / 'pet-errors.log'
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=log_file, encoding='utf-8', level=logging.INFO,
                        format='[%(asctime)s] PID=%(process)d %(message)s')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateEventW.restype = wintypes.HANDLE
    kernel.CreateEventW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.SetEvent.argtypes = [wintypes.HANDLE]
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    events = {}
    mutex = None
    requested = 'strike' if '--strike' in sys.argv else 'coffee'
    try:
        for mode, event_name in (('coffee', 'CodexCoffeePetShow'), ('strike', 'CodexPetEnableStrike')):
            events[mode] = kernel.CreateEventW(None, False, False, 'Local\\' + event_name)
            if not events[mode]:
                raise ctypes.WinError(ctypes.get_last_error())
        mutex = kernel.CreateMutexW(None, False, 'Local\\CodexCoffeePet')
        last_error = ctypes.get_last_error()
        if not mutex:
            raise ctypes.WinError(last_error)
        if last_error == 183:  # ERROR_ALREADY_EXISTS
            if not kernel.SetEvent(events[requested]):
                raise ctypes.WinError(ctypes.get_last_error())
            logging.info('Requested the existing desktop pet to show')
            return
        def requested_mode():
            return next((mode for mode, event in events.items()
                         if kernel.WaitForSingleObject(event, 0) == 0), None)

        # Both launchers use the same desktop window and original office renderer.
        from strike_desktop import StrikeDesktopApp
        pet = StrikeDesktopApp(requested_mode, requested)
        logging.info('Desktop pet window ready')
        pet.root.mainloop()
    except Exception:
        logging.exception('Could not start the desktop pet')
    finally:
        if mutex:
            kernel.CloseHandle(mutex)
        for event in events.values():
            if event:
                kernel.CloseHandle(event)


if __name__ == '__main__':
    main()
