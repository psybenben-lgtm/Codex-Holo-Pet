"""Linked match for the package's existing HTTP/SSE service."""
from collections import deque
from math import isfinite
from queue import Queue, Empty
from threading import Event, RLock, Thread
from time import monotonic
from uuid import uuid4

from rally_match import Match, Shot, clamp, player_point

PROTOCOL = 1


class LiveBadminton:
    def __init__(self, run=True, clock=monotonic):
        self.clock=clock
        self.lock=RLock()
        self.stop=Event()
        self.game=Match(phone=True)
        self.game.reset(clock())
        self.desktop_at=-100.
        self.phone_at=-100.
        self.camera_at=-100.
        self.camera='starting'
        self.camera_enabled=True
        self.camera_index=0
        self.camera_status='正在连接摄像头…'
        self.preview_open=False
        self.bar_visible=True
        self.bar_expanded=True
        self.hand_mode='hands'
        self.cmd_seq=0
        self.cmd_ack=0
        self.cmd=''
        self.cmd_data={}
        self.token=uuid4().hex
        self.seq=0
        self.audio_seq=0
        self.audio=deque(maxlen=12)
        self.clients=set()
        self.close_seq=0
        self.closed=False
        self.last_hand_swing=-100.
        if run:
            Thread(target=self.loop,name='linked badminton',daemon=True).start()

    def _push_cmd(self, cmd, data=None):
        """生成单调递增的控制指令序号，通知桌面叠加层执行一次动作。"""
        self.cmd_seq+=1
        self.cmd=cmd
        self.cmd_data=dict(data or {})

    def _step(self):
        self.game.step(self.clock())
        for name in self.game.events:
            self.audio_seq+=1
            self.audio.append({'id':self.audio_seq,'name':name,'at':self.game.now})
        self.game.events.clear()

    def snapshot(self):
        with self.lock:
            g=self.game
            now=self.clock()
            can_swing=any(b.towards=='player' and .66<=b.progress(now)<=1.15 for b in g.shots)
            return {
                'protocol':PROTOCOL, 'session':self.token, 'seq':self.seq, 'now':now,
                'phase':g.phase,'since':g.since, 'actor':g.actor,'goal':g.actor_goal,
                'desk_offset':g.desk_offset,'clear_court':g.clear_court,'hits':g.hits,
                'smashes':g.smashes, 'player_score':g.player_score,
                'codex_score':g.codex_score, 'codex_max_score':g.codex_max_score,
                'angry':now<g.angry_until, 'annoyed':now<g.annoyed_until,
                'angry_until':g.angry_until, 'annoyed_until':g.annoyed_until,
                'poke_count':g.poke_count, 'poke_react_at':g.poke_react_at,
                'codex_bubble':g.codex_bubble if now<g.codex_bubble_until else '',
                'codex_bubble_until':g.codex_bubble_until,
                'hand_mode':self.hand_mode,
                'fatigue':g.fatigue,'swing_at':g.swing_at,'swing_face':g.swing_face,
                'throw_from':g.throw_from,'ended':g.ended,
                'shots':[vars(b).copy() for b in g.shots],
                'effects':g.effects[:],
                'pending':dict(g.pending) if g.pending else None,
                'launches':[dict(e) for e in g.launches],
                'audio':list(self.audio),
                'camera':self.camera if now-self.camera_at<2.8 else 'offline',
                'camera_enabled':self.camera_enabled,
                'camera_index':self.camera_index,
                'camera_status':self.camera_status,
                'preview_open':self.preview_open,
                'bar_visible':self.bar_visible,
                'bar_expanded':self.bar_expanded,
                'cmd_seq':self.cmd_seq,'cmd':self.cmd,'cmd_data':dict(self.cmd_data),
                'can_swing':can_swing,
                'cooldown_active':now-self.last_hand_swing<.13,
                'last_swing_at':self.last_hand_swing if self.last_hand_swing>0 else None,
                'match_active':g.phase in ('clear','rally','charge','barrage'),
                'phone_online':now-self.phone_at<3.2, 'desktop_online':now-self.desktop_at<3.2,
                'waiting':bool(g.pending and now-self.phone_at>=3.2),
                'close_seq':self.close_seq,'closed':self.closed,
            }

    def _broadcast(self):
        self.seq+=1
        if not self.clients:
            return
        snap=self.snapshot()
        for q in self.clients:
            try:
                q.get_nowait()
            except Empty:
                pass
            q.put_nowait(snap)

    def subscribe(self):
        with self.lock:
            q=Queue(maxsize=1)
            self.clients.add(q)
            q.put_nowait(self.snapshot())
            return q

    def unsubscribe(self,q):
        with self.lock:
            self.clients.discard(q)

    def loop(self):
        while not self.stop.wait(.025):
            with self.lock:
                self._step()
                self._broadcast()

    def action(self, action, data):
        with self.lock:
            self._step()
            now=self.game.now
            applied=True
            launch=None
            if action=='desktop':
                self.desktop_at=now
                if data.get('open'):
                    self.closed=False
                self.camera_at=now
                self.camera=str(data.get('camera','starting'))[:32]
                ack=int(data.get('cmd_ack',self.cmd_seq))
                self.cmd_ack=max(self.cmd_ack,min(ack,self.cmd_seq))
                if 'camera_status' in data:
                    self.camera_status=str(data['camera_status'])[:64]
                if ack>=self.cmd_seq:
                    if 'camera_enabled' in data:
                        self.camera_enabled=bool(data['camera_enabled'])
                    if 'camera_index' in data:
                        self.camera_index=max(0,int(data['camera_index']))
                    if 'preview_open' in data:
                        self.preview_open=bool(data['preview_open'])
                    if 'bar_visible' in data:
                        self.bar_visible=bool(data['bar_visible'])
                    if 'bar_expanded' in data:
                        self.bar_expanded=bool(data['bar_expanded'])
                    if 'hand_mode' in data and str(data['hand_mode']) in ('hands','racket'):
                        self.hand_mode=str(data['hand_mode'])
            elif action=='phone':
                if data.get('visible',True):
                    self.phone_at=now
            elif action=='start':
                applied=not self.closed and now-self.desktop_at<3.2 and self.game.start()
            elif action=='reset':
                self.game.reset(now)
                if data.get('start'):
                    self.game.start()
                applied=True
            elif action=='replay':
                self.game.reset(now)
                applied=self.game.start()
            elif action=='barrage':
                applied=not self.closed and now-self.desktop_at<3.2 and self.game.barrage()
            elif action=='quit':
                if self.game.phase in ('rally','charge','barrage'):
                    self.game.quit_match()
                elif self.game.phase in ('clear','quit','desk'):
                    self.game.reset(now)
                else:
                    applied=False
            elif action=='hand_mode':
                mode=str(data.get('mode','')).strip().lower()
                if mode not in ('hands','racket'):
                    mode='racket' if self.hand_mode=='hands' else 'hands'
                self.hand_mode=mode
                self._push_cmd('hand_mode',{'mode':self.hand_mode})
                applied=not self.closed and now-self.desktop_at<3.2
            elif action=='poke':
                px=float(data.get('x',855.))
                py=float(data.get('y',520.))
                if not (isfinite(px) and isfinite(py)):
                    raise ValueError('invalid poke')
                applied=not self.closed and now-self.desktop_at<3.2 and self.game.poke((px,py))
            elif action=='camera_power':
                on=bool(data['enabled']) if 'enabled' in data else not self.camera_enabled
                self.camera_enabled=on
                self._push_cmd('camera_on' if on else 'camera_off')
                applied=not self.closed and now-self.desktop_at<3.2
            elif action=='camera_retry':
                self.camera_enabled=True
                self._push_cmd('camera_retry')
                applied=not self.closed and now-self.desktop_at<3.2
            elif action=='camera_switch':
                idx=data.get('index')
                self.camera_index=(self.camera_index+1)%3 if idx is None else max(0,int(idx))
                self.camera_enabled=True
                self._push_cmd('camera_switch',{'index':self.camera_index})
                applied=not self.closed and now-self.desktop_at<3.2
            elif action=='camera_preview':
                target=bool(data['open']) if 'open' in data else not self.preview_open
                self.preview_open=target
                self._push_cmd('preview',{'open':target})
                applied=not self.closed and now-self.desktop_at<3.2
            elif action=='bar':
                vis=bool(data.get('visible',True))
                exp=bool(data.get('expanded',True))
                self.bar_visible=vis
                self.bar_expanded=exp
                self._push_cmd('bar',{'visible':vis,'expanded':exp})
                applied=not self.closed and now-self.desktop_at<3.2
            elif action=='launch':
                # A shot starts only when the projection endpoint has received a pending serve.
                applied=(not self.closed and now-self.desktop_at<3.2 and now-self.phone_at<3.2
                         and data.get('session')==self.token and self.game.confirm_serve(int(data['id']), -1 if data.get('side')=='left' else 1))
                if applied:
                    launch=self.game.launches[-1].copy()
            elif action=='swing':
                coords=[float(data[k]) for k in ('x','y','power')]
                if not all(isfinite(v) for v in coords):
                    raise ValueError('invalid swing')
                if now-self.last_hand_swing>=.13 and now-self.desktop_at<3.2 and not self.closed:
                    self.last_hand_swing=now
                    applied=self.game.swing(player_point((coords[0],coords[1])),clamp(coords[2]),
                                            assisted=bool(data.get('assisted')),
                                            force_smash=bool(data.get('force_smash') or data.get('smash')))
                else:
                    applied=False
            elif action=='close':
                self.close_seq+=1
                self.closed=True
                self.game.reset(now)
                self.desktop_at=-100.
            else:
                raise KeyError(action)
            self._step()
            self._broadcast()
            snap=self.snapshot()
            snap['applied']=applied
            if launch:
                snap['launch']=launch
            return snap


class View:
    """Draw the same authoritative trajectories between network snapshots."""
    def __init__(self):
        self.phase='desk'
        self.now=self.since=0.
        self.actor=self.actor_goal=self.throw_from=(0.,.78)
        self.fatigue=self.desk_offset=self.clear_court=0.
        self.swing_face=-1
        self.swing_at=self.player_at=-100.
        self.ended=False
        self.effects=[]
        self.shots=[]
        self.hits=0
        self.player_score=0
        self.codex_score=5
        self.codex_max_score=5
        self.angry_until=-100.
        self.annoyed_until=-100.
        self.poke_count=0
        self.poke_react_at=-100.
        self.codex_bubble=''
        self.codex_bubble_until=-100.

    def sync(self,snap,now):
        self.now=now
        for name in ('phase','since','actor','throw_from','fatigue','desk_offset','clear_court',
                     'swing_face','swing_at','ended','effects','hits',
                     'player_score','codex_score','codex_max_score',
                     'angry_until','annoyed_until','poke_count','poke_react_at',
                     'codex_bubble','codex_bubble_until'):
            if name in snap:
                setattr(self,name,snap[name])
        self.actor_goal=snap['goal']
        self.shots=[Shot(**b) for b in snap['shots'] if b['at']<=now]

    def cue(self,ball):
        return Match.cue(self,ball)

    def shot_points(self,ball):
        return Match.shot_points(self,ball)
