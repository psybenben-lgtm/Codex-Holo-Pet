"""Windows transparent overlay for the original Codex desk pet and holographic phone."""
import argparse
import ctypes as C
from ctypes import wintypes as W
import json
import math
import os
from pathlib import Path
from queue import Empty, Queue
import sys
import time
from threading import Event, Thread
import tkinter as tk
from urllib.request import Request
import webbrowser

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'.rally-runtime'))
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'.rally-runtime'/'matplotlib-cache'))

from PIL import Image, ImageDraw, ImageTk
from local_runtime import get_local_host_url, get_no_proxy_opener
from badminton_live import View
from rally_art import Art, W as ART_W, H as ART_H, racket_tip_for_hand
from rally_hand import Camera, Hand
from rally_match import DESK_HITBOX, clamp, player_point, project
from rally_voice import Voice

HOST=get_local_host_url()
API=HOST+'/api/badminton/live/'
HTTP=get_no_proxy_opener()
WM_HOTKEY=0x312


class Point(C.Structure):
    _fields_=[('x',C.c_long),('y',C.c_long)]


class Size(C.Structure):
    _fields_=[('cx',C.c_long),('cy',C.c_long)]


class Blend(C.Structure):
    _fields_=[('operation',C.c_byte),('flags',C.c_byte),('opacity',C.c_ubyte),('format',C.c_byte)]


class BitmapInfo(C.Structure):
    _fields_=[('size',W.DWORD),('width',C.c_long),('height',C.c_long),
              ('planes',W.WORD),('bits',W.WORD),('compression',W.DWORD),('image_size',W.DWORD),
              ('x_ppm',C.c_long),('y_ppm',C.c_long),('used',W.DWORD),('important',W.DWORD),('color',W.DWORD)]


def sig(dll,name,result,*args):
    f=getattr(dll,name)
    f.restype=result
    f.argtypes=list(args)
    return f


class Layer:
    """Per-pixel alpha desktop surface; render only the bounds of visible sprites."""
    def __init__(self):
        user=self.user=C.WinDLL('user32',use_last_error=True)
        gdi=self.gdi=C.WinDLL('gdi32',use_last_error=True)
        self.screen=sig(user,'GetDC',W.HDC,W.HWND)(None)
        self.dc=sig(gdi,'CreateCompatibleDC',W.HDC,W.HDC)(self.screen)
        self.bitmap=None
        self.previous=None
        self.dims=None
        self.select=sig(gdi,'SelectObject',W.HANDLE,W.HDC,W.HANDLE)
        self.delete=sig(gdi,'DeleteObject',W.BOOL,W.HANDLE)
        self.create=sig(gdi,'CreateDIBSection',W.HANDLE,W.HDC,C.POINTER(BitmapInfo),W.UINT,
                        C.POINTER(C.c_void_p),W.HANDLE,W.DWORD)
        self.update=sig(user,'UpdateLayeredWindow',W.BOOL,W.HWND,W.HDC,C.POINTER(Point),
                        C.POINTER(Size),W.HDC,C.POINTER(Point),W.DWORD,C.POINTER(Blend),W.DWORD)
        self.show=sig(user,'ShowWindow',W.BOOL,W.HWND,C.c_int)
        create=sig(user,'CreateWindowExW',W.HWND,W.DWORD,W.LPCWSTR,W.LPCWSTR,W.DWORD,
                   C.c_int,C.c_int,C.c_int,C.c_int,W.HWND,W.HMENU,W.HINSTANCE,C.c_void_p)
        # Dedicated popup: Tk is used for the floating control bar and local camera preview.
        self.hwnd=create(0x80000|0x20|0x80|0x08000000,'Static','Codex 透明桌宠 · 羽毛球',
                         0x80000000,0,0,1,1,None,None,None,None)
        if not self.hwnd or not self.dc:
            raise C.WinError(C.get_last_error())
        self.position=sig(user,'SetWindowPos',W.BOOL,W.HWND,W.HWND,C.c_int,C.c_int,C.c_int,C.c_int,W.UINT)
        self.visible=False

    def rect(self):
        area=W.RECT()
        sig(self.user,'SystemParametersInfoW',W.BOOL,W.UINT,W.UINT,C.c_void_p,W.UINT)(0x30,0,C.byref(area),0)
        return area

    def set_bitmap(self,w,h):
        if self.dims==(w,h):
            return
        if self.bitmap:
            self.select(self.dc,self.previous)
            self.delete(self.bitmap)
        info=BitmapInfo(40,w,-h,1,32)
        self.bits=C.c_void_p()
        self.bitmap=self.create(self.screen,C.byref(info),0,C.byref(self.bits),None,0)
        if not self.bitmap:
            raise C.WinError(C.get_last_error())
        self.previous=self.select(self.dc,self.bitmap)
        self.dims=(w,h)

    def draw(self, img, area):
        box=img.getbbox()
        if not box:
            if self.visible:
                self.show(self.hwnd,0)
                self.visible=False
            return
        sx=(area.right-area.left)/ART_W
        sy=(area.bottom-area.top)/ART_H
        x0,y0,x1,y1=box
        dest=Point(round(area.left+x0*sx),round(area.top+y0*sy))
        w=max(1,round(area.left+x1*sx)-dest.x)
        h=max(1,round(area.top+y1*sy)-dest.y)
        tile=img.crop(box)
        if tile.size!=(w,h):
            tile=tile.resize((w,h),Image.Resampling.BILINEAR)
        raw=tile.convert('RGBa').tobytes('raw','BGRa')
        self.set_bitmap(w,h)
        C.memmove(self.bits,raw,len(raw))
        if not self.update(self.hwnd,self.screen,C.byref(dest),C.byref(Size(w,h)),self.dc,C.byref(Point()),
                           0,C.byref(Blend(0,0,255,1)),2):
            raise C.WinError(C.get_last_error())
        if not self.visible:
            self.position(self.hwnd,W.HWND(-1),0,0,0,0,0x0053)  # Show, keep geometry, don't activate.
            self.visible=True

    def close(self):
        sig(self.user,'DestroyWindow',W.BOOL,W.HWND)(self.hwnd)
        if self.bitmap:
            self.select(self.dc,self.previous)
            self.delete(self.bitmap)
        sig(self.gdi,'DeleteDC',W.BOOL,W.HDC)(self.dc)
        sig(self.user,'ReleaseDC',C.c_int,W.HWND,W.HDC)(None,self.screen)


class Link:
    def __init__(self):
        self.stop=Event()
        self.beat=Event()
        self.queue=Queue()
        self.state=None
        self.received=0.
        self.camera='starting'
        self.camera_enabled=True
        self.camera_index=0
        self.camera_status='正在连接摄像头…'
        self.preview_open=False
        self.bar_visible=True
        self.bar_expanded=True
        self.hand_mode='hands'
        self.cmd_ack=0
        Thread(target=self._write,daemon=True).start()
        Thread(target=self._read,daemon=True).start()

    def send(self,action,**body):
        self.queue.put((action,body))

    def wake(self):
        """主动触发一次状态上报，加速网页端状态同步。"""
        self.beat.set()

    def _post(self,action,data):
        req=Request(API+action,json.dumps(data).encode(),{'Content-Type':'application/json'})
        with HTTP.open(req,timeout=.75) as r:
            return json.load(r)

    def _write(self):
        next_beat=0.
        session=None
        while not self.stop.is_set():
            try:
                now=time.monotonic()
                if now>=next_beat or self.beat.is_set():
                    self.beat.clear()
                    s=self.state
                    initial=not session or bool(s and s['session']!=session)
                    payload={
                        'open':initial,
                        'camera':self.camera,
                        'camera_enabled':self.camera_enabled,
                        'camera_index':self.camera_index,
                        'camera_status':self.camera_status,
                        'preview_open':self.preview_open,
                        'bar_visible':self.bar_visible,
                        'bar_expanded':self.bar_expanded,
                        'hand_mode':self.hand_mode,
                        'cmd_ack':self.cmd_ack,
                    }
                    snap=self._post('desktop',payload)
                    if snap.get('closed') and not initial and session!=snap.get('session'):
                        payload['open']=True
                        snap=self._post('desktop',payload)
                    session=snap.get('session')
                    next_beat=time.monotonic()+.8
                try:
                    action,data=self.queue.get(timeout=.10)
                except Empty:
                    continue
                if action=='swing' and time.monotonic()-data.pop('seen',time.monotonic())>.23:
                    continue
                self._post(action,data)
            except (OSError, ValueError):
                self.stop.wait(.25)

    def _read(self):
        while not self.stop.is_set():
            try:
                with HTTP.open(API+'stream',timeout=2.) as stream:
                    for line in stream:
                        if self.stop.is_set():
                            return
                        if line.startswith(b'data: '):
                            self.state=json.loads(line[6:])['data']
                            self.received=time.monotonic()
            except (OSError, ValueError):
                self.stop.wait(.24)


def hotkeys(queue, stop):
    user=C.WinDLL('user32',use_last_error=True)
    keys={i:ord(letter) for i,letter in enumerate('BVFCQPSHDM',1)}
    msg=W.MSG()
    registered=[i for i,k in keys.items() if user.RegisterHotKey(None,i,0x4003,k)]
    if len(registered)!=len(keys):
        print('[hotkeys] unavailable:',sorted(set(keys)-set(registered)),flush=True)
    try:
        while not stop.wait(.023):
            while user.PeekMessageW(C.byref(msg),None,WM_HOTKEY,WM_HOTKEY,1):
                queue.put(chr(keys[msg.wParam]))
    finally:
        for i in registered:
            user.UnregisterHotKey(None,i)


class ControlBar:
    """桌面左下角可拖拽、可收起的轻量悬浮控制台，随时提供摄像头与网页控制台入口。"""
    def __init__(self, desktop):
        self.desktop=desktop
        self.expanded=True
        self.visible=True
        self._drag=None
        self._placed=False
        self._last_sig=None

        w=self.win=tk.Toplevel(desktop.root)
        w.title('Codex 桌宠控制台')
        w.overrideredirect(True)
        w.attributes('-topmost',True)
        w.attributes('-alpha',0.95)
        w.configure(bg='#38bdf8',padx=1,pady=1)

        outer=tk.Frame(w,bg='#0f172a',padx=8,pady=6)
        outer.pack(fill='both',expand=True)

        hdr=self.hdr=tk.Frame(outer,bg='#162033',padx=6,pady=4)
        hdr.pack(fill='x')
        self.lbl_title=tk.Label(
            hdr,text='🏸 桌宠控制台',fg='#fde047',bg='#162033',
            font=('Microsoft YaHei UI',9,'bold'),cursor='fleur',
        )
        self.lbl_title.pack(side='left')

        self.lbl_cam=tk.Label(
            hdr,text='● 摄像头准备中',fg='#facc15',bg='#162033',
            font=('Microsoft YaHei UI',9,'bold'),cursor='fleur',padx=8,
        )
        self.lbl_cam.pack(side='left')

        self.btn_mini_close=self._mkbtn(hdr,'✕',self._on_close_pet,bg='#7f1d1d',fg='#fecaca',padx=6)
        self.btn_mini_close.pack(side='right',padx=(4,0))

        self.btn_fold=self._mkbtn(hdr,'⊟ 收起',self.toggle_expand,bg='#1e293b',fg='#cbd5e1',padx=7)
        self.btn_fold.pack(side='right',padx=(4,0))

        self.btn_mini_cam=self._mkbtn(hdr,'📷 开启',self._on_cam_toggle,bg='#16a34a',fg='#ffffff',padx=7)
        # 仅在收起时放到顶栏，展开时主栏已有更完整的按钮

        body=self.body=tk.Frame(outer,bg='#0f172a',pady=4)
        body.pack(fill='x')

        r0=tk.Frame(body,bg='#0f172a')
        r0.pack(fill='x',pady=(1,4))
        self.btn_mode_coffee=self._mkbtn(r0,'☕ 切倒咖啡',lambda:self._on_switch_mode('coffee'),bg='#1e293b',fg='#fde047')
        self.btn_mode_coffee.pack(side='left',padx=(0,4))
        self.btn_mode_strike=self._mkbtn(r0,'🛁 切搓澡罢工',lambda:self._on_switch_mode('strike'),bg='#1e293b',fg='#7dd3fc')
        self.btn_mode_strike.pack(side='left',padx=(0,4))
        self.btn_mouse_mode=self._mkbtn(r0,'🖱️ 鼠标代打:开',self._on_toggle_mouse,bg='#0369a1',fg='#ffffff')
        self.btn_mouse_mode.pack(side='left',padx=(0,4))
        self.btn_workbench=self._mkbtn(r0,'🌐 工作台',lambda:self.desktop.open_web('/'),bg='#334155',fg='#f8fafc')
        self.btn_workbench.pack(side='left')

        r1=tk.Frame(body,bg='#0f172a')
        r1.pack(fill='x',pady=(2,4))
        self.btn_cam=self._mkbtn(r1,'⏸ 关闭摄像头',self._on_cam_toggle,bg='#334155',fg='#f8fafc')
        self.btn_cam.pack(side='left',padx=(0,4))
        self.btn_retry=self._mkbtn(r1,'🔄 重连',self._on_cam_retry,bg='#1e293b',fg='#e2e8f0')
        self.btn_retry.pack(side='left',padx=(0,4))
        self.btn_switch=self._mkbtn(r1,'🔀 镜头#0',self._on_cam_switch,bg='#1e293b',fg='#38bdf8')
        self.btn_switch.pack(side='left',padx=(0,4))
        self.btn_preview=self._mkbtn(r1,'🪞 镜像预览',self._on_preview,bg='#1e293b',fg='#c4b5fd')
        self.btn_preview.pack(side='left',padx=(0,4))
        self.btn_hand_mode=self._mkbtn(r1,'🖐 五指形态',self._on_hand_mode,bg='#1e293b',fg='#6ee7b7')
        self.btn_hand_mode.pack(side='left')

        r2=tk.Frame(body,bg='#0f172a')
        r2.pack(fill='x')
        self.btn_play=self._mkbtn(r2,'🏸 开始开打',self._on_play,bg='#d97706',fg='#ffffff')
        self.btn_play.pack(side='left',padx=(0,4))
        self.btn_console=self._mkbtn(r2,'🎛️ 网页控制台',self._on_console,bg='#0284c7',fg='#ffffff')
        self.btn_console.pack(side='left',padx=(0,4))
        self.btn_guide=self._mkbtn(r2,'📱 手机扫码',self._on_guide,bg='#1e293b',fg='#38bdf8')
        self.btn_guide.pack(side='left',padx=(0,4))
        self.btn_close=self._mkbtn(r2,'✕ 关桌宠',self._on_close_pet,bg='#475569',fg='#f8fafc')
        self.btn_close.pack(side='left',padx=(0,4))
        self.btn_exit=self._mkbtn(r2,'⏻ 全退出',self._on_shutdown,bg='#b91c1c',fg='#ffffff')
        self.btn_exit.pack(side='left')

        for widget in (hdr,self.lbl_title,self.lbl_cam):
            widget.bind('<ButtonPress-1>',self._start_drag)
            widget.bind('<B1-Motion>',self._do_drag)

        self.refresh(force=True)

    @staticmethod
    def _mkbtn(parent,text,cmd,bg='#1e293b',fg='#f8fafc',padx=8):
        return tk.Button(
            parent,text=text,command=cmd,bg=bg,fg=fg,
            activebackground='#0ea5e9',activeforeground='#ffffff',
            relief='flat',bd=0,padx=padx,pady=3,cursor='hand2',
            font=('Microsoft YaHei UI',9,'bold'),
        )

    def _start_drag(self,event):
        self._drag=(event.x_root-self.win.winfo_x(),event.y_root-self.win.winfo_y())

    def _do_drag(self,event):
        if not self._drag:
            return
        x=event.x_root-self._drag[0]
        y=event.y_root-self._drag[1]
        area=self.desktop.area
        w=max(1,self.win.winfo_width())
        h=max(1,self.win.winfo_height())
        x=max(area.left,min(x,area.right-w))
        y=max(area.top,min(y,area.bottom-h))
        self.win.geometry(f'+{x}+{y}')

    def _fit(self):
        self.win.update_idletasks()
        w=self.win.winfo_reqwidth()
        h=self.win.winfo_reqheight()
        area=self.desktop.area
        if not self._placed:
            x=area.left+16
            y=max(area.top+12,area.bottom-h-16)
            self._placed=True
        else:
            x=max(area.left,min(self.win.winfo_x(),area.right-w))
            y=max(area.top,min(self.win.winfo_y(),area.bottom-h))
        self.win.geometry(f'+{x}+{y}')

    def set_state(self,visible=True,expanded=True):
        self.visible=bool(visible)
        self.expanded=bool(expanded)
        if self.visible:
            self.win.deiconify()
            self.win.attributes('-topmost',True)
        else:
            self.win.withdraw()
        if self.expanded:
            self.btn_mini_cam.pack_forget()
            self.body.pack(fill='x')
            self.btn_fold.config(text='⊟ 收起')
        else:
            self.body.pack_forget()
            self.btn_mini_cam.pack(side='right',padx=(4,0))
            self.btn_fold.config(text='⊞ 展开')
        self._fit()
        self.desktop.link.bar_visible=self.visible
        self.desktop.link.bar_expanded=self.expanded
        self.desktop.link.wake()

    def toggle_expand(self):
        self.set_state(visible=True,expanded=not self.expanded)

    def _on_cam_toggle(self):
        cam=self.desktop.camera
        on=not bool(cam and cam.enabled.is_set())
        self.desktop.set_camera_enabled(on)

    def _on_cam_retry(self):
        self.desktop.retry_camera()

    def _on_cam_switch(self):
        self.desktop.switch_camera()

    def _on_preview(self):
        self.desktop.toggle_preview()

    def _on_hand_mode(self):
        self.desktop.toggle_hand_mode()

    def _on_switch_mode(self,mode):
        self.desktop.switch_suite_mode(mode)

    def _on_toggle_mouse(self):
        self.desktop.mouse_assist=not self.desktop.mouse_assist
        self.refresh(force=True)

    def _on_play(self):
        phase=self.desktop.phase
        if phase=='desk':
            self.desktop.link.send('start')
        elif phase=='rally':
            self.desktop.link.send('barrage')
        else:
            self.desktop.link.send('quit')

    def _on_console(self):
        self.desktop.open_web('/badminton/director')

    def _on_guide(self):
        self.desktop.open_web('/guide')

    def _on_close_pet(self):
        self.desktop.close()

    def _on_shutdown(self):
        self.desktop.shutdown_all()

    def refresh(self,force=False):
        d=self.desktop
        cam_state=d.status()
        enabled=bool(d.camera and d.camera.enabled.is_set())
        idx=d.camera.index if d.camera else 0
        preview_on=bool(d.preview)
        phase=d.phase
        hand_mode=d.hand_mode
        c_score=getattr(d.view,'codex_score',5)
        p_score=getattr(d.view,'player_score',0)
        sig=(cam_state,enabled,idx,preview_on,phase,self.expanded,hand_mode,c_score,p_score,d.mouse_assist)
        if not force and sig==self._last_sig:
            return
        self._last_sig=sig

        status_map={
            'tracked':('● 球拍已就绪' if hand_mode=='racket' else '● 五指已识别','#c084fc' if hand_mode=='racket' else '#4ade80'),
            'looking':('● 摄像头已开启 · 待举手','#38bdf8'),
            'starting':('● 正在连接摄像头…','#facc15'),
            'paused':('● 鼠标代打就绪 (无摄)' if d.mouse_assist else '○ 摄像头已关闭','#38bdf8' if d.mouse_assist else '#94a3b8'),
            'error':('● 鼠标代打就绪 (无摄)' if d.mouse_assist else '✕ 摄像头未就绪','#38bdf8' if d.mouse_assist else '#f87171'),
            'off':('● 鼠标代打就绪 (无摄)' if d.mouse_assist else '○ 摄像头未启用','#38bdf8' if d.mouse_assist else '#94a3b8'),
        }
        txt,col=status_map.get(cam_state,('● 检测中','#facc15'))
        self.lbl_cam.config(text=txt,fg=col)

        if hasattr(self,'btn_mouse_mode'):
            self.btn_mouse_mode.config(
                text='🖱️ 鼠标代打:开' if d.mouse_assist else '🖱️ 鼠标代打:关',
                bg='#0369a1' if d.mouse_assist else '#1e293b',
                fg='#ffffff' if d.mouse_assist else '#94a3b8',
            )

        if enabled and cam_state!='error':
            self.btn_cam.config(text='⏸ 关闭摄像头',bg='#334155',fg='#f8fafc')
            self.btn_mini_cam.config(text='⏸ 关摄',bg='#334155',fg='#f8fafc')
        else:
            self.btn_cam.config(text='📷 开启摄像头',bg='#16a34a',fg='#ffffff')
            self.btn_mini_cam.config(text='📷 开摄',bg='#16a34a',fg='#ffffff')

        self.btn_switch.config(text=f'🔀 镜头#{idx}')
        self.btn_preview.config(
            text='🪞 关闭预览' if preview_on else '🪞 镜像预览',
            bg='#0284c7' if preview_on else '#1e293b',
            fg='#ffffff' if preview_on else '#c4b5fd',
        )
        self.btn_hand_mode.config(
            text='🏸 球拍形态' if hand_mode=='racket' else '🖐 五指形态',
            bg='#7c3aed' if hand_mode=='racket' else '#1e293b',
            fg='#ffffff' if hand_mode=='racket' else '#6ee7b7',
        )
        if phase=='desk':
            self.btn_play.config(text='🏸 开始开打',bg='#d97706')
        elif phase=='rally':
            self.btn_play.config(text=f'⚡ 连发({p_score}:{c_score})',bg='#9333ea')
        else:
            self.btn_play.config(text='🏠 回工位',bg='#475569')
        self._fit()

    def close(self):
        try:
            self.win.destroy()
        except tk.TclError:
            pass


class Desktop:
    def __init__(self,args):
        self.root=tk.Tk()
        self.root.title('Codex 透明桌宠 · 羽毛球')
        self.root.withdraw()
        self.layer=Layer()
        self.area=self.layer.rect()
        self.stop=Event()
        self.commands=Queue()
        self.art=Art()
        self.view=View()
        self.link=Link()
        self.camera=Camera(args.camera,auto_start=not args.no_camera)
        self.voice=None if args.no_voice else Voice()
        self.voice_req=self.hand_event=0
        self.hand=Hand()
        self.start_at=time.monotonic()
        self.next_frame=self.start_at
        self.end_at=self.start_at+args.quit_after if args.quit_after else float('inf')
        self.next_area=0.
        self.started=False
        self.note_until=self.start_at+8
        self.preview=None
        self.preview_at=0.
        self.audio=-1
        self.session=None
        self.last_cmd_seq=0
        self.snapshot=args.snapshot
        self.testing=args.test_hand
        self.mouse_assist=True
        self.frame_count=0
        self.phase='desk'
        self.hand_mode='racket' if args.no_camera else 'hands'
        self.prev_cursor=None
        self.prev_cursor_at=0.
        self.last_prox_swing_at=-100.
        self.last_poke_at=-100.
        self.was_in_desk=False
        self.bar=None if args.snapshot else ControlBar(self)
        Thread(target=hotkeys,args=(self.commands,self.stop),daemon=True).start()
        self.root.protocol('WM_DELETE_WINDOW',self.close)
        self.root.after(0,self.tick)

    def switch_suite_mode(self, target_mode):
        """从羽毛球桌宠悬浮栏一键切换到倒咖啡 / 搓澡罢工模式。"""
        def _req():
            try:
                req=Request(HOST+'/api/pet/mode',json.dumps({'mode':target_mode,'spawn':True}).encode('utf-8'),
                            {'Content-Type':'application/json'})
                HTTP.open(req,timeout=1.5).close()
            except (OSError,ValueError):
                pass
        Thread(target=_req,daemon=True).start()
        self.close(remote=True)

    def _mouse_hand(self, now):
        """零权限纯鼠标模式：通过标准 Win32 GetCursorPos 生成实时手套/球拍手势，无需摄像头！"""
        pt=W.POINT()
        if not C.windll.user32.GetCursorPos(C.byref(pt)):
            return Hand()
        aw=max(1,self.area.right-self.area.left)
        ah=max(1,self.area.bottom-self.area.top)
        ax=(pt.x-self.area.left)*ART_W/aw
        ay=(pt.y-self.area.top)*ART_H/ah
        nx=clamp(.10+.80*((ax-145.)/780.),.02,.98)
        ny=clamp(.12+.76*((ay-320.)/320.),.02,.98)
        base=((.49,.68),(.46,.64),(.44,.62),(.42,.58),(.39,.54),(.46,.56),(.45,.51),(.44,.46),(.44,.42),
              (.49,.55),(.49,.49),(.49,.43),(.49,.38),(.52,.55),(.53,.50),(.54,.45),(.55,.42),
              (.55,.58),(.57,.54),(.59,.50),(.60,.47))
        dx,dy=nx-.50,ny-.59
        pts=tuple((x+dx,y+dy,0.) for x,y in base)
        return Hand(points=pts,palm=(nx,ny),visibility=1.,live=True,at=now)

    def status(self):
        if not self.camera:
            return 'off'
        if not self.camera.enabled.is_set():
            return 'paused'
        if self.camera.last_frame_at and time.monotonic()-self.camera.last_frame_at<.42:
            return 'tracked' if self.camera.hand.live else 'looking'
        if self.camera.status and not self.camera.status.startswith('正在'):
            return 'error'
        return 'starting'

    def set_camera_enabled(self,on):
        if not self.camera:
            return
        self.camera.set_enabled(bool(on))
        self.note_until=time.monotonic()+8
        self.link.wake()

    def retry_camera(self):
        if not self.camera:
            return
        self.camera.set_enabled(True)
        self.note_until=time.monotonic()+8
        self.link.wake()

    def switch_camera(self,index=None):
        if not self.camera:
            return
        self.camera.switch_index(index)
        self.note_until=time.monotonic()+8
        self.link.wake()

    def open_web(self,suffix):
        Thread(target=lambda:webbrowser.open(HOST+suffix),daemon=True).start()

    def shutdown_all(self):
        def _req():
            try:
                req=Request(HOST+'/api/system/shutdown',b'{}',{'Content-Type':'application/json'})
                HTTP.open(req,timeout=1.2).close()
            except (OSError,ValueError):
                pass
        Thread(target=_req,daemon=True).start()
        self.close(remote=True)

    def _apply_hand_mode(self,mode,*,notify=False):
        target=str(mode or 'hands').strip().lower()
        if target not in ('hands','racket'):
            target='hands'
        self.hand_mode=target
        self.link.hand_mode=target
        self.was_in_desk=False
        self.note_until=time.monotonic()+6
        if notify:
            self.link.send('hand_mode',mode=target)
            self.link.wake()
        if self.bar:
            self.bar.refresh(force=True)

    def toggle_hand_mode(self,force=None):
        target=force if force is not None else ('racket' if self.hand_mode=='hands' else 'hands')
        self._apply_hand_mode(target,notify=True)

    def _handle_remote_cmd(self,cmd,data):
        if cmd=='camera_on':
            self.set_camera_enabled(True)
        elif cmd=='camera_off':
            self.set_camera_enabled(False)
        elif cmd=='camera_retry':
            self.retry_camera()
        elif cmd=='camera_switch':
            self.switch_camera(data.get('index'))
        elif cmd=='preview':
            self.toggle_preview(force=data.get('open'))
        elif cmd=='bar' and self.bar:
            self.bar.set_state(visible=data.get('visible',True),expanded=data.get('expanded',True))
        elif cmd=='hand_mode':
            self._apply_hand_mode(data.get('mode'),notify=False)

    def command(self,key):
        if key=='B':
            self.link.send('start')
        elif key=='F':
            self.link.send('barrage')
        elif key=='S':
            self.link.send('swing',x=.5,y=.5,power=.86,assisted=True,force_smash=True)
        elif key=='C':
            self.retry_camera()
        elif key=='Q':
            self.close()
        elif key=='P':
            self.open_web('/guide')
        elif key=='D':
            self.open_web('/badminton/director')
        elif key=='H' and self.bar:
            self.bar.toggle_expand()
        elif key=='V':
            self.toggle_preview()
        elif key=='M':
            self.toggle_hand_mode()

    def toggle_preview(self,force=None):
        if not self.camera:
            return
        if force is False and not self.preview:
            return
        if force is True and self.preview:
            self.preview.deiconify()
            self.preview.lift()
            return
        if self.preview:
            self.camera.preview_on.clear()
            self.preview.destroy()
            self.preview=None
            self.link.wake()
            return
        if not self.camera.enabled.is_set():
            self.camera.set_enabled(True)
        self.preview=tk.Toplevel(self.root)
        self.preview.title('本机手部校准 · 不录像')
        self.preview.attributes('-topmost',True)
        self.preview.resizable(False,False)
        self.preview.protocol('WM_DELETE_WINDOW',self.toggle_preview)
        self.preview.bind('<Escape>',lambda _:self.toggle_preview())
        self.camera.preview_on.set()
        self.preview_view=tk.Label(self.preview,text='等待摄像头…',bg='#182c34',fg='#dffbed',padx=8,pady=8)
        self.preview_view.pack()
        self.preview_status=tk.Label(self.preview,text='',fg='#173439',padx=8,pady=7)
        self.preview_status.pack()
        self.link.wake()

    def draw_preview(self,now):
        if not self.preview or now<self.preview_at:
            return
        self.preview_at=now+.065
        self.camera.preview_on.set()
        sample=self.camera.preview
        if sample is not None and now-self.camera.last_frame_at<.42:
            rgb,hand=sample
            img=Image.fromarray(rgb)
            if hand.points:
                points=[(x*img.width,y*img.height) for x,y,_ in hand.points]
                self.art.bones(ImageDraw.Draw(img,'RGBA'),points,hand.visibility,.78)
            self.preview_photo=ImageTk.PhotoImage(img,master=self.preview)
            self.preview_view.config(image=self.preview_photo,text='')
        else:
            self.preview_view.config(image='',text=self.camera.status or '等待摄像头…')
        message='已锁定 · 五指 21 点' if self.hand.live else '举一只手，露出手腕和五指'
        self.preview_status.config(text=message)

    def _process_hand_interactions(self, now):
        if not self.hand.live:
            self.prev_cursor=None
            self.was_in_desk=False
            return
        cx,cy=player_point(self.hand.palm)
        if self.hand_mode=='racket':
            _,_,_,tx,ty=racket_tip_for_hand(self.hand)
        else:
            tx,ty=cx,cy
        hx,hy=(tx,ty) if self.hand_mode=='racket' else (cx,cy)
        speed_px_s=0.
        smash_speed_px_s=0.
        if self.prev_cursor is not None:
            dt_cur=now-self.prev_cursor_at
            if .008<=dt_cur<=.25:
                dx_cur,dy_cur=hx-self.prev_cursor[0],hy-self.prev_cursor[1]
                speed_px_s=math.hypot(dx_cur,dy_cur)/dt_cur
                smash_speed_px_s=math.hypot(dx_cur,dy_cur*1.45)/dt_cur
        self.prev_cursor=(hx,hy)
        self.prev_cursor_at=now

        # 球拍形态下伸入 Codex 工位区域触发“被戳烦”反馈
        if self.phase=='desk':
            if self.hand_mode=='racket':
                x0,y0,x1,y1=DESK_HITBOX
                in_desk=(x0<=tx<=x1 and y0<=ty<=y1) or (x0<=cx<=x1 and y0<=cy<=y1)
                if in_desk and (not self.was_in_desk or speed_px_s>=70.) and now-self.last_poke_at>=.95:
                    self.last_poke_at=now
                    self.link.send('poke',x=tx,y=ty)
                self.was_in_desk=in_desk
            else:
                self.was_in_desk=False
            return

        self.was_in_desk=False
        # 对局阶段贴近球头直接截击/挥拍判定，让视觉命中和挥拍扣杀一致
        if self.phase in ('rally','charge','barrage') and now-self.last_prox_swing_at>=.26 and speed_px_s>=110.:
            best=None
            for ball in self.view.shots:
                if ball.towards!='player' or not .76<=ball.progress(self.view.now)<=1.13:
                    continue
                bx,by,_=project(*ball.position(self.view.now))
                d_tip=math.hypot(tx-bx,(ty-by)*1.05)
                d_palm=math.hypot(cx-bx,(cy-by)*1.05)
                pt,dist=((tx,ty),d_tip) if d_tip<=d_palm else ((cx,cy),d_palm)
                reach=74 if ball.kind!='barrage' else 92
                if dist<=reach and (best is None or dist<best[0]):
                    best=(dist,pt)
            if best is not None:
                _,pt=best
                # 稍微收紧近身拦截时的杀球速度映射：慢中速对打回普通球，明显快速挥拍才算杀球
                prox_power=clamp(smash_speed_px_s/900.,.38,.96)
                nx=clamp(.10+.80*((pt[0]-145.)/780.),0.,1.)
                ny=clamp(.12+.76*((pt[1]-320.)/320.),0.,1.)
                self.last_prox_swing_at=now
                self.view.player_at=now
                self.link.send('swing',x=nx,y=ny,power=prox_power,seen=now)

    def tick(self):
        if self.stop.is_set():
            return
        now=time.monotonic()
        if now>=self.end_at:
            print(f'[overlay] {self.frame_count} frames; camera={self.status()}; voice={self.voice.status if self.voice else "off"}',
                  flush=True)
            self.close()
            return
        while not self.commands.empty():
            self.command(self.commands.get_nowait())
        if self.stop.is_set():
            return
        cam_state=self.status()
        self.link.camera=cam_state
        self.link.camera_enabled=bool(self.camera and self.camera.enabled.is_set())
        self.link.camera_index=self.camera.index if self.camera else 0
        self.link.camera_status=self.camera.status if self.camera else ''
        self.link.preview_open=bool(self.preview)
        if self.bar:
            self.link.bar_visible=self.bar.visible
            self.link.bar_expanded=self.bar.expanded
        self.link.hand_mode=self.hand_mode

        self.hand=self.camera.hand if self.camera else Hand()
        if self.camera and now-self.camera.last_frame_at>.38:
            self.hand=Hand(event=self.hand.event)
        if not self.hand.live and not self.testing and self.mouse_assist and not self.snapshot:
            self.hand=self._mouse_hand(now)
        if self.testing:
            dx=math.sin(now*2)*.14
            joints=((.49,.68),(.46,.64),(.44,.62),(.42,.58),(.39,.54),(.46,.56),(.45,.51),(.44,.46),(.44,.42),
                    (.49,.55),(.49,.49),(.49,.43),(.49,.38),(.52,.55),(.53,.50),(.54,.45),(.55,.42),
                    (.55,.58),(.57,.54),(.59,.50),(.60,.47))
            self.hand=Hand(tuple((x+dx,y,0) for x,y in joints),(.50+dx,.59),1.,True)
        if self.hand.event!=self.hand_event:
            self.hand_event=self.hand.event
            if self.hand.live and now-self.hand.at<.23:
                self.view.player_at=now
                sx,sy=self.hand.palm
                if self.hand_mode=='racket':
                    _,_,_,tx,ty=racket_tip_for_hand(self.hand)
                    sx=clamp(.10+.80*((tx-145.)/780.),0.,1.)
                    sy=clamp(.12+.76*((ty-320.)/320.),0.,1.)
                self.link.send('swing',x=sx,y=sy,power=self.hand.power,seen=self.hand.at)

        snap=self.link.state
        if snap:
            cmd_seq=int(snap.get('cmd_seq') or 0)
            if self.session!=snap['session']:
                self.session=snap['session']
                self.audio=max((event['id'] for event in snap['audio']),default=0)
                self.last_cmd_seq=cmd_seq
                if cmd_seq>0 and snap.get('hand_mode') in ('hands','racket'):
                    self._apply_hand_mode(snap['hand_mode'],notify=False)
            elif cmd_seq>self.last_cmd_seq:
                self.last_cmd_seq=cmd_seq
                self._handle_remote_cmd(snap.get('cmd',''),snap.get('cmd_data') or {})
                self.link.cmd_ack=cmd_seq
                self.link.camera_enabled=bool(self.camera and self.camera.enabled.is_set())
                self.link.camera_index=self.camera.index if self.camera else 0
                self.link.preview_open=bool(self.preview)
                self.link.hand_mode=self.hand_mode
                if self.bar:
                    self.link.bar_visible=self.bar.visible
                    self.link.bar_expanded=self.bar.expanded
                self.link.wake()
            if snap['closed'] and self.started:
                self.close(remote=True)
                return
            self.started=self.started or not snap['closed']
            age=min(.11,max(0.,now-self.link.received))
            self.view.sync(snap,snap['now']+age)
            self.phase=snap['phase']
            if now-self.link.received<.4:
                from transparent_badminton_desktop import play_local_wav
                for event in snap['audio']:
                    if event['id']>self.audio:
                        self.audio=event['id']
                        if event['at']>snap['now']-.25:
                            play_local_wav(event['name'])
        else:
            self.view.now=now
        self._process_hand_interactions(now)
        if self.voice:
            request=self.voice.request
            if self.phase=='desk':
                self.voice.active.set()
                if self.voice_req!=request:
                    self.link.send('start')
            else:
                self.voice.active.clear()
            self.voice_req=request

        note=''
        if not self.camera or cam_state in ('paused','off','error'):
            if self.mouse_assist:
                note='纯鼠标模式 · 晃动鼠标接球或点工作台操作（免摄像头权限）'
            elif cam_state=='paused':
                note='摄像头已关闭 · 点击控制台「开启摄像头」'
            else:
                note=f'{self.camera.status or "摄像头未就绪"} · 点击重连或开启鼠标代打'
        elif snap and snap.get('waiting'):
            note='等待全息手机发球机连接（也可直接在电脑工作台同屏预览触发）'
        if now>=self.next_area:
            self.area=self.layer.rect()
            self.next_area=now+2.
        frame=self.art.frame(self.view,self.hand,note,hand_mode=self.hand_mode)
        try:
            self.layer.draw(frame,self.area)
        except OSError as e:
            print(f'[overlay] display: {e}',flush=True)
            self.close()
            return
        self.frame_count+=1
        if self.snapshot and self.frame_count==12:
            frame.save(self.snapshot)
        self.draw_preview(now)
        if self.bar:
            self.bar.refresh()
        self.next_frame+=.023
        end=time.monotonic()
        if end-self.next_frame>.06:
            self.next_frame=end
        self.root.after(max(1,round((self.next_frame-end)*1000)),self.tick)

    def close(self,remote=False):
        if self.stop.is_set():
            return
        self.stop.set()
        if self.camera:
            self.camera.close()
        if self.voice:
            self.voice.stop.set()
            self.voice.active.set()
        self.link.stop.set()
        if not remote and self.started:
            try:
                self.link._post('close',{})
            except (OSError,ValueError):
                pass
        if self.bar:
            self.bar.close()
        self.layer.close()
        self.root.destroy()


def main():
    os.chdir(ROOT)
    if not sys.stderr or not sys.stdout:
        log=ROOT/'coffee'/'.lan-certificate'/'badminton-overlay.log'
        log.parent.mkdir(parents=True,exist_ok=True)
        sys.stdout=sys.stderr=log.open('a',encoding='utf-8',buffering=1)
    parser=argparse.ArgumentParser()
    parser.add_argument('--camera',type=int,default=0)
    parser.add_argument('--no-camera',action='store_true')
    parser.add_argument('--no-voice',action='store_true')
    parser.add_argument('--quit-after',type=float,default=0.)
    parser.add_argument('--snapshot')
    parser.add_argument('--test-hand',action='store_true')
    args=parser.parse_args()
    kernel=C.WinDLL('kernel32',use_last_error=True)
    lock=sig(kernel,'CreateMutexW',W.HANDLE,C.c_void_p,W.BOOL,W.LPCWSTR)(None,False,'Local\\Codex-Badminton-Transparent')
    if C.get_last_error()==183:
        if lock:
            sig(kernel,'CloseHandle',W.BOOL,W.HANDLE)(lock)
        return
    try:
        print('[overlay] starting native transparent desk pet',flush=True)
        app=Desktop(args)
        app.root.mainloop()
    finally:
        if lock:
            sig(kernel,'CloseHandle',W.BOOL,W.HANDLE)(lock)


if __name__=='__main__':
    main()
