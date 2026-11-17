"""Clock-driven, first-person badminton. No camera, window or network dependencies."""
from dataclasses import dataclass
from math import exp, hypot, sin
from random import Random


def clamp(x, lo=0., hi=1.):
    return min(hi, max(lo, x))


def ease(x):
    x = clamp(x)
    return x*x*(3-2*x)


def mix(a, b, p):
    return a+(b-a)*p


def project(x, z, h=0):
    """World x / court depth / height -> the shared screen coordinate system."""
    size = 1/(1+1.30*z)
    return 512 + x*398*size, 330+320*(1-z)*size-h*size, size


def player_point(palm):
    x, y = palm
    return (mix(145, 925, clamp((x-.10)/.80)), mix(320, 640, clamp((y-.12)/.76)))


DESK_HITBOX = (755, 435, 975, 625)
SMASH_POWER = .72


@dataclass
class Shot:
    start: tuple
    end: tuple
    at: float
    flight: float
    lift: float
    towards: str
    kind: str
    power: float = 0.
    tail: bool = False
    machine: bool = False
    hot: bool = False

    def progress(self, now):
        return (now-self.at)/self.flight

    def position(self, now):
        progress=self.progress(now)
        u = clamp(progress)
        x, z, h = (mix(a, b, u) for a, b in zip(self.start, self.end))
        if progress>1. and self.towards=='player':
            h-=min(h,260*(progress-1.))
        return x, z, h + 4*self.lift*u*(1-u)


class Match:
    def __init__(self, seed=None, *, phone=False):
        self.random = Random(seed)
        self.phone = phone
        self.pending = None
        self.launches = []
        self.serve_id = 0
        self.events = []
        self.reset()

    def reset(self, now=0.):
        self.pending = None
        self.launches.clear()
        self.phase = 'desk'
        self.since = self.now = now
        self.clear_court = self.desk_offset = 0.
        self.actor = (0., .78)
        self.actor_goal = self.actor
        self.swing_at = -100.
        self.swing_face = -1
        self.fatigue = 0.
        self.shots = []
        self.effects = []
        self.events.clear()
        self.hits = self.longest = self.rally = self.smashes = self.misses = 0
        self.served = self.burst_sent = self.burst_hits = 0
        self.player_score = 0
        self.codex_max_score = 5
        self.codex_score = self.codex_max_score
        self.angry_until = -100.
        self.annoyed_until = -100.
        self.poke_count = 0
        self.poke_stage = 0
        self.poke_at = -100.
        self.poke_react_at = -100.
        self.bubble_changed_at = -100.
        self.codex_bubble = ''
        self.codex_bubble_until = -100.
        self.next_serve = float('inf')
        self.player_at = -100.
        self.ended = False
        self.desk_moved = False
        self.throw_from = self.actor

    def enter(self, phase):
        self.phase, self.since = phase, self.now

    def sound(self, name):
        self.events.append(name)

    def start(self):
        if self.phase not in ('desk', 'quit'):
            return False
        self.reset(self.now)
        self.enter('clear')
        self.sound('invite_chime')
        return True

    def barrage(self):
        if self.phase == 'rally':
            self.next_serve = float('inf')
            self.pending = None
            self.enter('charge')
            self.angry_until = max(self.angry_until, self.now + 3.6)
            self.codex_bubble = '连扣我 5 分！不讲武德开挂连发七球！' if self.codex_score <= 0 else '哼，不讲武德开挂连发七球！'
            self.codex_bubble_until = self.now + 3.2
            self.bubble_changed_at = self.now
            self.sound('cheat_button')
            self.sound('machine_charge')
            return True
        return False

    def quit_match(self):
        if self.phase in ('rally', 'charge', 'barrage'):
            self.throw_from = self.actor
            self.shots.clear()
            self.pending = None
            self.enter('quit')
            self.sound('lose_sigh')

    def effect(self, pos, kind, power=.4):
        self.effects.append((self.now, pos, kind, power, self.random.random()))

    def swing(self, point, power, *, assisted=False, force_smash=False):
        if self.phase not in ('rally', 'charge', 'barrage'):
            return False
        self.player_at = self.now
        # 宽容的空间与时间接球判定窗口，并明确触发爆裂扣杀或普通回球
        eligible = []
        for ball in self.shots:
            if ball.towards != 'player' or not .66 <= ball.progress(self.now) <= 1.15:
                continue
            bx, by, _ = project(*ball.position(self.now))
            distance = hypot(point[0]-bx, (point[1]-by)*1.05)
            reach = 92 if ball.kind != 'barrage' else 120
            if assisted or distance <= reach:
                eligible.append((distance if not assisted else -ball.progress(self.now), ball))
        if not eligible:
            return False
        _, ball = min(eligible, key=lambda item: item[0])
        self.shots.remove(ball)
        at = ball.position(self.now)
        hot = bool(force_smash or power >= SMASH_POWER)
        eff_power = max(power, .78) if hot else power
        self.hits += 1
        self.rally += 1
        self.longest = max(self.rally, self.longest)
        self.smashes += int(hot)
        if ball.kind == 'barrage':
            self.burst_hits += 1
        self.fatigue = clamp(self.fatigue + .11 + eff_power*.22)
        aim = clamp(-at[0]*.55 + self.random.uniform(-.24, .24), -.66, .66)
        depth = self.random.uniform(.66, .88)
        flight = mix(.92, .45, eff_power) if hot else mix(1.13, .82, eff_power)
        lift = mix(82, 24, eff_power) if hot else mix(132, 95, eff_power)
        self.shots.append(Shot(at, (aim, depth, 68. if hot else 74.), self.now,
                               flight, lift,
                               'codex', ball.kind, eff_power, hot or ball.kind == 'barrage',
                               hot=hot))
        self.effect(at, 'smash' if hot else 'hit', eff_power)
        self.sound('hit_smash' if hot else 'hit_normal')
        return True

    def poke(self, point=(855., 520.)):
        """球拍在工位桌区域戳到 Codex 时，先短缓冲再缓步转头烦躁，多次戳不急躁闪烁切字。"""
        if self.phase != 'desk' or self.now - self.poke_at < .90:
            return False
        was_annoyed = self.now < self.annoyed_until
        self.poke_at = self.now
        self.poke_count += 1
        if not was_annoyed:
            self.poke_react_at = self.now + .22
        self.annoyed_until = self.now + 3.8
        lines = (
            '别戳啦，正忙着呢…',
            '哎呀，把拍子拿开…',
            '一直戳，真的要生气啦！',
            '停下啦，让我歇会儿…',
        )
        # 多次连续戳击时保持同一句生气台词足够久，避免状态文字频繁闪烁切换
        if not self.codex_bubble or self.now >= self.codex_bubble_until or self.now - self.bubble_changed_at >= 3.8:
            self.poke_stage += 1
            self.codex_bubble = lines[(self.poke_stage - 1) % len(lines)]
            self.bubble_changed_at = self.now
        self.codex_bubble_until = self.now + 3.8
        px, py = float(point[0]), float(point[1])
        self.effect((px, py, 1.), 'poke', .85)
        self.sound('codex_poke')
        return True

    def prepare_serve(self, kind):
        self.serve_id += 1
        self.pending = {'id': self.serve_id, 'kind': kind}

    def confirm_serve(self, serve_id, side=1):
        if not self.pending or self.pending['id'] != serve_id:
            return False
        kind = self.pending['kind']
        if (kind == 'barrage' and self.phase != 'barrage') or (kind == 'rally' and self.phase != 'rally'):
            return False
        self.pending = None
        at = self.now + .31
        entry = at + .225
        self.launches.append({'id':serve_id, 'at':at, 'kind':kind})
        self.launches = self.launches[-8:]
        slot = self.burst_sent if kind == 'barrage' else self.served
        x = (-.38, .30, -.14, .42, -.28, .04, .34)[slot % 7]
        depth = (.78, .88, .67, .81)[slot % 4]
        # The ball crosses the right edge after the phone muzzle animation.
        self.shots.append(Shot((2.16*side,.52,60.), (x,depth,69.),
                               entry, .82 if kind=='rally' else 1.03,
                               71., 'codex', kind, .42, kind=='barrage', machine=True))
        if kind == 'barrage':
            self.burst_sent += 1
            self.next_serve = self.now+.42
        else:
            self.served += 1
            self.next_serve = float('inf')
        return True

    def _incoming(self, source, kind='rally'):
        rapid = kind == 'barrage'
        if rapid:
            i = self.burst_sent
            target = (-.45, .29, -.12, .47, -.39, .07, .48)[i]
        else:
            target = self.random.uniform(-.47, .47)
        self.shots.append(Shot(source, (target, .035, 47.), self.now,
                               (1.34+(.07*(self.burst_sent % 3))) if rapid else
                               (1.85 if self.served <= 1 else 1.62),
                               self.random.uniform(85, 125), 'player', kind, .42, rapid))
        if rapid:
            self.burst_sent += 1
            self.effect(source, 'serve', .65)
            if self.burst_sent in (1, 4, 7):
                self.sound('shuttle_launch')

    def _return(self, ball, *, player_return=True):
        contact = ball.position(self.now)
        self.swing_at = self.now
        self.swing_face = -1 if contact[0] <= self.actor[0] else 1
        self.effect(contact, 'hit', .35)
        self.sound('hit_normal')
        # The burst has its own feed; hard shots sent back exhaust Codex.
        if self.phase == 'rally' or (self.phone and self.phase in ('charge','barrage') and player_return):
            target = self.random.uniform(-.55, .55) if ball.kind=='rally' else (-.39,.22,-.12,.37,-.27,.06,.43)[self.burst_sent % 7]
            self.shots.append(Shot(contact, (target, .045, 47.), self.now,
                                   (1.62 + self.fatigue*.24) if ball.kind=='rally' else 1.45,
                                   self.random.uniform(81, 125), 'player', ball.kind, tail=ball.kind=='barrage'))

    def step(self, now):
        dt = clamp(now-self.now, 0, .05)
        self.now = now
        age = now-self.since
        self.fatigue = max(0., self.fatigue-dt*.035)
        if self.phase == 'clear':
            self.desk_offset = ease((age-.35)/1.23)
            self.clear_court = ease((age-.50)/1.38)
            if age >= .35 and not self.desk_moved:
                self.desk_moved = True
                self.sound('push_desk')
            p = ease((age-.26)/.86)
            slide = ease((age-1.14)/.67)
            self.actor = (1.62*p*(1-slide), mix(.47,.78,slide))
            if age >= 1.95:
                self.enter('rally')
                self.next_serve = now+.58

        if self.phase in ('rally', 'charge', 'barrage'):
            self._play(dt, age)

        if self.phase == 'quit':
            age = now-self.since
            if age >= .48:
                p = ease((age-.48)/.91)
                self.actor = (mix(self.throw_from[0], .36, p), mix(self.throw_from[1], .90, p))
            if age > 1.4:
                self.desk_offset = 1-ease((age-1.4)/.94)
                self.clear_court = self.desk_offset
                p = ease((age-1.4)/.94)
                self.actor = (.36*(1-p), mix(.90, .78, p))
            if age >= 2.43:
                self.enter('desk')
                self.ended = True
                self.desk_offset = self.clear_court = 0.
                self.actor = self.actor_goal = (0., .78)

        ttl = lambda kind: 1.25 if kind in ('smash', 'blast', 'score_drop') else (.75 if kind == 'poke' else .67)
        self.effects = [p for p in self.effects if now-p[0] < ttl(p[2])]

    def _play(self, dt, age):
        now = self.now
        if self.phase == 'charge' and age >= .95:
            self.enter('barrage')
            self.next_serve=now
            age = 0.
            self.sound('cheat_rapid')
        if self.phone:
            if not self.pending and now >= self.next_serve:
                if self.phase=='barrage' and self.burst_sent<7:
                    self.prepare_serve('barrage')
                elif self.phase=='rally' and not self.shots:
                    self.prepare_serve('rally')
        else:
            if self.phase == 'barrage' and self.burst_sent < 7 and age >= self.burst_sent*.37:
                self._incoming((.72 if self.burst_sent % 2 else -.72, .87, 70.), 'barrage')
            if self.phase == 'rally' and now >= self.next_serve and not self.shots:
                self.served += 1
                self.next_serve = float('inf')
                self.swing_at = now
                self.swing_face = -1
                source = (self.actor[0]-.15, self.actor[1], 78.)
                self._incoming(source)
                self.effect(source, 'serve')
                self.sound('shuttle_launch')

        incoming = sorted((b for b in self.shots if b.towards == 'codex' and b.at-.19<=now),
                          key=lambda b: b.at+b.flight)
        if incoming:
            b = incoming[0]
            # Move around the far court to meet the actual endpoint of this shot.
            side = 1 if b.end[0] < .1 else -1
            self.actor_goal = (b.end[0]+side*.15, b.end[1])
            self.swing_face = -side
        elif self.phase == 'barrage':
            self.actor_goal = (.32*sin(age*4.1), .79+.095*sin(age*5.1))
        elif self.phase == 'charge':
            self.actor_goal = (0., .86)
        self.actor = tuple(mix(a, b, 1-exp(-dt*mix(9., 5., self.fatigue)))
                           for a, b in zip(self.actor, self.actor_goal))

        for b in self.shots[:]:
            end = b.progress(now)
            if b.towards == 'codex' and end >= 1.:
                self.shots.remove(b)
                from_machine = b.machine
                if not from_machine and (b.hot or b.power >= SMASH_POWER):
                    # 玩家强力扣杀飞入 Codex 半场：爆裂火花 + 爆裂声 + 减一分 + 生气反应
                    self.player_score += 1
                    self.angry_until = max(self.angry_until, now + 2.4)
                    self.swing_at = now
                    self.effect(b.end, 'blast', max(.82, b.power))
                    self.effect((b.end[0], b.end[1], b.end[2] + 46.), 'score_drop', 1.)
                    self.sound('smash_blast')
                    if self.phase == 'rally':
                        self.codex_score = max(0, self.codex_score - 1)
                        rage_lines = {
                            4: '唔，好重的一拍 (-1)',
                            3: '可恶，又掉了一分…',
                            2: '别再这么用力扣杀啦！',
                            1: '只剩 1 分了，好气！',
                            0: '分扣光了！不讲武德看招！',
                        }
                        if self.codex_score == 0 or not self.codex_bubble or now >= self.codex_bubble_until or now - self.bubble_changed_at >= 2.6:
                            self.codex_bubble = rage_lines.get(self.codex_score, '可恶！-1')
                            self.bubble_changed_at = now
                        self.codex_bubble_until = now + 2.4
                        if self.codex_score > 0:
                            self.next_serve = now + .68
                    else:
                        self.fatigue = clamp(self.fatigue + .22)
                        if not self.codex_bubble or now >= self.codex_bubble_until or now - self.bubble_changed_at >= 2.6:
                            self.codex_bubble = '哇，这球力道真猛！'
                            self.bubble_changed_at = now
                        self.codex_bubble_until = now + 1.8
                elif self.phase != 'barrage' or self.fatigue < .81 or from_machine:
                    self._return(b, player_return=not self.phone or from_machine)
                else:
                    self.effect(b.end, 'miss')
            elif b.towards == 'player' and end > 1.15:
                self.shots.remove(b)
                self.misses += 1
                self.rally = 0
                self.effect((b.end[0], b.end[1], 0), 'miss')
                if self.phase == 'rally':
                    self.next_serve = now+.90
                    self.sound('shuttle_land')

        if self.phase == 'rally' and (self.codex_score <= 0 or self.hits >= 8 or (self.served >= 6 and not self.shots)) and not any(b.towards=='codex' for b in self.shots):
            self.barrage()
        if self.phase == 'barrage' and self.burst_sent == 7 and age > 4.1 and not self.shots:
            self.quit_match()

    def cue(self, ball):
        return ball.towards == 'player' and .66 <= ball.progress(self.now) <= 1.15

    def shot_points(self, ball):
        return project(*ball.position(self.now))
