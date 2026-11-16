"""Local capture, 21-joint tracking and intentional gesture edges."""
from collections import deque
from dataclasses import dataclass
from math import exp, hypot
from pathlib import Path
from statistics import median
from threading import Event, Lock, Thread
import time

from rally_match import clamp, mix

MODEL = Path(__file__).resolve().parents[1] / 'assets' / 'hand_landmarker.task'
FINGERS = ((0, 1, 2, 3, 4), (0, 5, 6, 7, 8), (0, 9, 10, 11, 12),
           (0, 13, 14, 15, 16), (0, 17, 18, 19, 20))
PALM = (0, 5, 9, 13, 17)
TIPS = (8, 12, 16, 20)


def center(points):
    return tuple(sum(points[i][d] for i in PALM)/len(PALM) for d in (0, 1))


def span(points):
    return hypot((points[0][0]-points[9][0])*4/3, points[0][1]-points[9][1])


def finger_shape(points):
    # Measure spread separately so bringing straight fingers together counts as well as a fist.
    def distance(a, b):
        x1,y1,z1=points[a]
        x2,y2,z2=points[b]
        return ((4/3*(x1-x2))**2+(y1-y2)**2+(4/3*(z1-z2))**2)**.5
    palm = max(.024, distance(0, 9))
    reach = median(distance(0, i)/palm for i in TIPS)
    spread = distance(4, 20)/palm + distance(8, 20)/palm
    return .61*clamp((reach-1.08)/.86) + .39*clamp((spread-1.18)/1.62), clamp((spread-1.13)/1.55)


def openness(points):
    return finger_shape(points)[0]


@dataclass(frozen=True)
class Hand:
    points: tuple = ()
    palm: tuple = (.5, .5)
    visibility: float = 0.
    live: bool = False
    amount: float = 0.
    event: int = 0
    power: float = 0.
    at: float = 0.


class HandFilter:
    """One active hand. A nearby person or short occlusion doesn't steal the cursor."""
    def __init__(self):
        self.result = Hand()
        self.raw_center = None
        self.velocity = (0., 0.)
        self.last = -10.
        self.size = 0.
        self.label = ''
        self.lock_since = 0.
        self.pending = None
        self.opened = False
        self.strike_at = -10.
        self.motion = deque()
        self.amount = 0.
        self.spread = 0.
        self.fanned = False
        self.flick_ready = True

    def update(self, choices, now):
        valid = []
        for points, label in choices:
            size = span(points)
            pos = center(points)
            # 放宽近距离手掌尺寸上限，手离镜头较近时仍保持稳定追踪
            if .024 <= size <= .85 and all(-.08 < v < 1.08 for v in pos):
                valid.append((points, pos, size, label))
        current = None
        gap = now-self.last
        if valid and self.raw_center is not None and gap < .48:
            aim = tuple(c+v*min(.075, gap) for c,v in zip(self.raw_center,self.velocity))
            close = []
            for item in valid:
                _, p, size, label = item
                distance = hypot(p[0]-aim[0], (p[1]-aim[1])*.85)
                if distance <= clamp(.90*self.size+.065+gap*.26, .12, .42) and .53 < size/self.size < 1.85:
                    score = distance + .17*abs(size-self.size) + (.085 if label != self.label else 0.)
                    close.append((score, item))
            if close:
                current = min(close, key=lambda pair: pair[0])[1]
        elif valid:
            # Acquire a clear foreground hand. Require several coherent frames before showing it.
            current = max(valid, key=lambda e: e[2]-.16*hypot(e[1][0]-.5,e[1][1]-.55))

        if current is None:
            self.pending = None
            if gap > .115:
                self.opened = self.fanned = False
                self.motion.clear()
                self.flick_ready = True
            old = self.result
            visibility = clamp((.34-gap)/.245)
            self.result = Hand(old.points if visibility else (), old.palm, visibility, False,
                               old.amount, old.event, old.power, old.at)
            return self.result

        points, pos, size, label = current
        acquiring = self.raw_center is None or gap >= .48
        if acquiring:
            pending = self.pending
            if not pending or pending[0] != label or hypot(pos[0]-pending[1][0],pos[1]-pending[1][1]) > .13:
                self.pending = (label, pos, now)
                return self.result
            if now-pending[2] < .052:
                return self.result
            self.lock_since = now
            self.motion.clear()
            self.opened = self.fanned = False
            self.velocity = (0., 0.)
            self.size = size

        raw_amount, raw_spread = finger_shape(points)
        dt = clamp(gap, .012, .12)
        old = self.result
        if acquiring or gap > .12 or not old.points:
            filtered = points
            speed = 0.
            self.amount, self.spread = raw_amount, raw_spread
            self.motion.clear()
            self.opened = self.fanned = False
            self.lock_since = now
        else:
            dx, dy = pos[0]-self.raw_center[0], pos[1]-self.raw_center[1]
            speed = hypot(dx*4/3, dy)/dt
            self.velocity = tuple(mix(v, d/dt, .43) for v, d in zip(self.velocity, (dx, dy)))
            filtered = []
            for prior, p in zip(old.points, points):
                distance = hypot(p[0]-prior[0], p[1]-prior[1])
                # Tiny independent joint fluctuations settle; genuine finger motion opens the filter.
                blend = 1-exp(-dt*(7 + min(53., (distance/dt)*28)))
                if distance < .003 and speed < .15:
                    blend *= .29
                filtered.append(tuple(mix(a, b, blend) for a,b in zip(prior,p)))
            filtered = tuple(filtered)
            blend=1-exp(-dt*34.)
            self.amount=mix(self.amount,raw_amount,blend)
            self.spread=mix(self.spread,raw_spread,blend)

        self.raw_center, self.last, self.label = pos, now, label
        self.size = mix(self.size, size, .30)
        self.motion.append((now, self.amount, pos, self.spread))
        while len(self.motion) > 1 and now-self.motion[0][0] > .21:
            self.motion.popleft()
        event, power, at = old.event, old.power, old.at
        if self.amount >= .61:
            self.opened = True
        if self.amount>=.61 and self.spread>=.52:
            self.fanned=True
        if speed < .67:
            self.flick_ready = True

        if now-self.lock_since > .18 and now-self.strike_at >= .215:
            change = max(((v-self.amount)/max(.04, now-st) for st,v,_,_ in self.motion), default=0.)
            folded = self.opened and self.amount <= .47 and raw_amount < .49
            gathered = self.fanned and self.spread <= .25 and raw_spread < .26
            if gathered:
                change=max(change,max(((v-self.spread)/max(.04,now-st) for st,_,_,v in self.motion),default=0.))
            peak = max((v for _,v,_,_ in self.motion), default=self.amount)
            history = [(st,p) for st,_,p,_ in self.motion if .048 <= now-st <= .13]
            travel_ok = any(hypot((pos[0]-p[0])*4/3, pos[1]-p[1])/(now-st) > (1.18 if self.opened else 1.30) for st, p in history)
            flick = self.opened and self.flick_ready and speed > 1.25 and travel_ok
            racket_swing = (not self.opened) and self.flick_ready and speed > 1.38 and travel_ok
            if folded or gathered or flick or racket_swing:
                if flick or racket_swing or gathered or peak-self.amount > .14 or raw_amount <= .35:
                    self.strike_at = now
                    if flick or racket_swing:
                        # 轻微提高杀球所需挥速阈值：常规移动打平球对拉，明显快速挥拍才触发杀球
                        power = clamp((speed - 1.10) / 1.90 + .44, .44, 1.)
                    else:
                        power = clamp(.28+max(change, 0)*.14, .28, 1.)
                    event, at = event+1, now
                    self.flick_ready = False
                if folded or gathered:
                    self.opened = self.fanned = False

        self.result = Hand(filtered, center(filtered), 1., True, self.amount, event, power, at)
        return self.result


class Camera:
    def __init__(self, index=0, auto_start=True):
        self.index = max(0, int(index))
        self.stop_event = Event()
        self.enabled = Event()
        if auto_start:
            self.enabled.set()
        self.retry = Event()
        self.preview_on = Event()
        self.preview = None
        self.detected_once = False
        self.status = f'正在连接摄像头 #{self.index}…' if auto_start else '摄像头已关闭 · 点击开启'
        self.hand = Hand()
        self.last_frame_at = 0.
        self.thread = Thread(target=self._run, name='hand inference', daemon=True)
        self.thread.start()

    def set_enabled(self, on=True, index=None):
        """开启或关闭本地摄像头采集，并立即唤醒采集线程。"""
        if index is not None:
            self.index = max(0, int(index))
        if on:
            self.status = f'正在连接摄像头 #{self.index}…'
            self.enabled.set()
        else:
            self.enabled.clear()
            self.preview = None
            self.status = '摄像头已关闭 · 点击开启'
        self.retry.set()

    def switch_index(self, index=None):
        """切换摄像头索引号（0/1/2 轮换或指定索引）并立即重连。"""
        self.index = (self.index + 1) % 3 if index is None else max(0, int(index))
        self.status = f'正在切换至摄像头 #{self.index}…'
        self.enabled.set()
        self.retry.set()
        return self.index

    def close(self):
        self.stop_event.set()
        self.enabled.clear()
        self.retry.set()

    def _run(self):
        while not self.stop_event.is_set():
            self.retry.clear()
            if not self.enabled.is_set():
                self.hand = Hand(event=self.hand.event)
                self.last_frame_at = 0.
                self.preview = None
                self.status = '摄像头已关闭 · 点击开启'
                self.retry.wait()
                continue
            try:
                self._session()
            except Exception as e:
                self.hand = Hand(event=self.hand.event)
                self.status = str(e) if isinstance(e, RuntimeError) else '摄像头暂不可用 · 请点击重连或切换镜头'
                print(f'[camera] {type(e).__name__}: {e}', flush=True)
            if not self.enabled.is_set():
                self.hand = Hand(event=self.hand.event)
                self.last_frame_at = 0.
                self.preview = None
                self.status = '摄像头已关闭 · 点击开启'
            if self.stop_event.is_set():
                break
            if not self.retry.is_set():
                self.retry.wait()

    def _session(self):
        try:
            import cv2
            import mediapipe as mp
            from mediapipe.tasks.python import vision
            from mediapipe.tasks.python import BaseOptions
        except (ImportError, OSError) as e:
            print(e, flush=True)
            raise RuntimeError('未安装摄像头组件 · 已支持纯鼠标挥拍(无需权限)') from e
        if not MODEL.is_file():
            raise RuntimeError('缺少手部识别模型 · 已支持纯鼠标挥拍')

        self.status = f'正在连接摄像头 #{self.index}…'
        cv2.setNumThreads(1)
        # Feed model bytes instead of a Unicode Windows path into the native runtime.
        options = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_buffer=MODEL.read_bytes()),
            running_mode=vision.RunningMode.VIDEO, num_hands=2,
            min_hand_detection_confidence=.50, min_hand_presence_confidence=.52,
            min_tracking_confidence=.54)
        frame_lock, frame_ready = Lock(), Event()
        latest = [None, 0.]
        failure = []
        stop_capture = Event()

        def capture():
            cap = None
            try:
                for backend in (cv2.CAP_DSHOW, cv2.CAP_MSMF):
                    cap = cv2.VideoCapture(self.index, backend)
                    if cap.isOpened():
                        break
                    cap.release()
                if not cap or not cap.isOpened():
                    failure.append(f'摄像头 #{self.index} 被占用或未授权 · 可点击切换镜头')
                    return
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                cap.set(cv2.CAP_PROP_FPS, 30)
                last_ok = time.monotonic()
                while not (self.stop_event.is_set() or self.retry.is_set() or stop_capture.is_set() or not self.enabled.is_set()):
                    ok, bgr = cap.read()
                    at = time.monotonic()
                    if not ok:
                        if at-last_ok > 1.5:
                            failure.append('摄像头已断开 · 请点击重连')
                            return
                        stop_capture.wait(.018)
                        continue
                    last_ok = at
                    with frame_lock:
                        latest[:] = bgr, at
                        frame_ready.set()
            finally:
                if cap is not None:
                    cap.release()
                frame_ready.set()

        def infer(bgr, stamp, tracker, landmarker, tick):
            height, width = bgr.shape[:2]
            factor = min(1., 640/width)
            if factor < 1.:
                bgr = cv2.resize(bgr, (round(width*factor),round(height*factor)), interpolation=cv2.INTER_AREA)
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            result = landmarker.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB,data=rgb), tick)
            choices = [(tuple((1.-p.x,p.y,p.z) for p in joints), side[0].category_name if side else '')
                       for joints,side in zip(result.hand_landmarks,result.handedness) if len(joints) == 21]
            hand=tracker.update(choices,stamp)
            if self.preview_on.is_set():
                preview=cv2.resize(rgb,(320,round(320*height/width)),interpolation=cv2.INTER_AREA)
                self.preview=(cv2.flip(preview,1),hand)
            elif self.preview is not None:
                self.preview=None
            return hand

        tracker = HandFilter()
        tracker.result = Hand(event=self.hand.event)
        last_stamp, last_tick = 0., 0
        with vision.HandLandmarker.create_from_options(options) as landmarker:
            worker = Thread(target=capture, name='camera capture', daemon=True)
            worker.start()
            try:
                while not (self.stop_event.is_set() or self.retry.is_set() or not self.enabled.is_set()):
                    frame_ready.wait(.09)
                    if self.stop_event.is_set() or self.retry.is_set() or not self.enabled.is_set():
                        return
                    if failure or not worker.is_alive():
                        raise RuntimeError(failure[0] if failure else '摄像头已断开 · 请点击重连')
                    with frame_lock:
                        bgr, stamp = latest
                        frame_ready.clear()
                    if bgr is None or stamp == last_stamp:
                        if self.last_frame_at and time.monotonic()-self.last_frame_at > .25:
                            self.hand = tracker.update([], time.monotonic())
                        continue
                    if not last_stamp:
                        print('[camera] local frames received', flush=True)
                    last_stamp = stamp
                    last_tick = max(last_tick+1, int(stamp*1000))
                    self.hand = infer(bgr, stamp, tracker, landmarker, last_tick)
                    if self.hand.live and not self.detected_once:
                        self.detected_once=True
                        print('[camera] tracking 21 joints',flush=True)
                    self.last_frame_at = stamp
                    self.status = ''
            finally:
                stop_capture.set()
                worker.join(timeout=2.)
