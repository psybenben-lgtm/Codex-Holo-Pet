import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from rally_art import Art, hand_skeleton_points, racket_tip_for_hand
from rally_hand import Hand, HandFilter, openness
from rally_match import Match, SMASH_POWER, player_point, project
from badminton_live import LiveBadminton, View

# Normalized positions for a fanned hand and the same palm with all fingers folded.
OPEN = ((.49,.68),(.46,.64),(.44,.62),(.42,.58),(.39,.54),(.46,.56),(.45,.51),(.44,.46),(.44,.42),
        (.49,.55),(.49,.49),(.49,.43),(.49,.38),(.52,.55),(.53,.50),(.54,.45),(.55,.42),
        (.55,.58),(.57,.54),(.59,.50),(.60,.47))
CLOSED = ((.49,.68),(.46,.64),(.46,.61),(.48,.59),(.52,.60),(.46,.56),(.45,.53),(.47,.56),(.48,.60),
          (.49,.55),(.49,.52),(.50,.55),(.50,.58),(.52,.55),(.53,.53),(.53,.56),(.53,.59),
          (.55,.58),(.56,.56),(.56,.58),(.55,.61))


def geometry(points, dx=0, dy=0, scale=1):
    return tuple((.5+(x-.5)*scale+dx,.58+(y-.58)*scale+dy,0.) for x,y in points)


class HandTest(unittest.TestCase):
    def test_tracking_survives_background_and_brief_occlusion(self):
        filt = HandFilter()
        for i in range(16):
            filt.update([(geometry(OPEN, math.sin(i)*.002), 'Right')],i/30)
        baseline = filt.result.palm
        for i in range(16, 30):
            hand=filt.update([(geometry(OPEN,.26,.01,1.3),'Left'),
                              (geometry(OPEN,math.sin(i)*.002),'Right')],i/30)
            self.assertEqual(len(hand.points),21)
            self.assertLess(abs(hand.palm[0]-baseline[0]),.005)
        before=filt.result.palm
        hand=filt.update([(geometry(OPEN,.26,.01,1.3),'Left')],1.0)
        self.assertFalse(hand.live)
        self.assertEqual(hand.palm,before)
        self.assertGreater(hand.visibility,.70)
        filt.update([(geometry(OPEN),'Right')],1.11)
        self.assertEqual(filt.result.event,0)
        self.assertTrue(filt.result.live)

    def test_open_close_is_one_hit_and_speed_controls_power(self):
        def perform(frames):
            f=HandFilter()
            for i in range(18):
                f.update([(geometry(OPEN),'Right')],i/30)
            for i in range(18,48):
                alpha=min(1.,(i-17)/frames)
                mixed=tuple((x+(xx-x)*alpha,y+(yy-y)*alpha) for (x,y),(xx,yy) in zip(OPEN,CLOSED))
                f.update([(geometry(mixed),'Right')],i/30)
            self.assertEqual(f.result.event,1)
            return f.result.power
        self.assertGreater(openness(geometry(OPEN)),.61)
        self.assertLess(openness(geometry(CLOSED)),.47)
        self.assertGreater(perform(2),perform(12))

    def test_spread_then_together_with_straight_fingers(self):
        f=HandFilter()
        squeezed=list(OPEN)
        for i, x in ((3,.473),(4,.493),(7,.487),(8,.485),(11,.495),(12,.495),
                     (15,.506),(16,.505),(19,.515),(20,.515)):
            squeezed[i]=(x,.43 if i in (4,8,12,16,20) else .49)
        for i in range(16):
            f.update([(geometry(OPEN),'Right')],i/30)
        for i in range(16,32):
            f.update([(geometry(squeezed),'Right')],i/30)
        self.assertEqual(f.result.event,1)

    def test_fast_open_hand_sweep_fires_once(self):
        f=HandFilter()
        for i in range(25):
            x=0 if i<17 else min(.31,(i-16)*.059)
            f.update([(geometry(OPEN,x),'Right')],i/30)
        self.assertEqual(f.result.event,1)
        self.assertGreater(f.result.power,.7)

    def test_racket_grip_fast_sweep_triggers_smash_without_opening_fingers_first(self):
        f=HandFilter()
        for i in range(26):
            x=0 if i<17 else min(.36,(i-16)*.06)
            f.update([(geometry(CLOSED,x),'Right')],i/30)
        self.assertEqual(f.result.event,1)
        self.assertGreaterEqual(f.result.power,SMASH_POWER)

    def test_moderate_sweep_rallies_without_smash(self):
        f=HandFilter()
        for i in range(26):
            x=0 if i<17 else min(.26,(i-16)*.033)
            f.update([(geometry(OPEN,x),'Right')],i/30)
        self.assertEqual(f.result.event,1)
        self.assertLess(f.result.power,SMASH_POWER)

    def test_close_hand_tracks_cleanly_and_renders_compact(self):
        f=HandFilter()
        hand=None
        for i in range(18):
            hand=f.update([(geometry(OPEN,scale=2.8),'Right')],i/30)
        self.assertTrue(hand.live)
        pts,_=hand_skeleton_points(hand)
        w=max(p[0] for p in pts)-min(p[0] for p in pts)
        h=max(p[1] for p in pts)-min(p[1] for p in pts)
        self.assertGreater(max(w,h),90.)
        self.assertLess(max(w,h),140.)


class MatchTest(unittest.TestCase):
    def test_complete_play_from_desk_to_rally_to_barrage_to_desk(self):
        g=Match(seed=11)
        self.assertTrue(g.start())
        self.assertFalse(g.start())
        self.assertFalse(g.swing((512,500),.6))
        reached=set()
        positions=[]
        for i in range(1,2400):
            g.step(i/60)
            reached.add(g.phase)
            positions.append(g.actor)
            for ball in g.shots[:]:
                if not g.cue(ball) or ball.progress(g.now)<.88:
                    continue
                point=project(*ball.position(g.now))[:2]
                self.assertFalse(g.swing((40,140),.65))
                self.assertTrue(g.swing(point,.84 if g.hits%3==2 else .55))
            if g.ended:
                break
        self.assertTrue({'rally','charge','barrage','quit','desk'} <= reached)
        self.assertGreater(max(x for x,_ in positions)-min(x for x,_ in positions), .40)
        self.assertGreater(max(z for _,z in positions)-min(z for _,z in positions), .13)
        self.assertEqual((g.burst_sent,g.burst_hits), (7,7))
        self.assertGreaterEqual(g.hits,12)
        self.assertTrue(g.ended and g.desk_offset==0 and g.clear_court==0)
        self.assertTrue(g.start())
        self.assertEqual(g.hits,0)

    def test_missed_serve_does_not_count_or_freeze(self):
        g=Match(seed=1)
        g.start()
        for i in range(1,455):
            g.step(i/60)
        self.assertEqual(g.hits,0)
        self.assertGreater(g.served,1)
        self.assertGreater(g.misses,0)

    def test_smash_scores_minus_one_and_triggers_barrage_at_zero(self):
        g=Match(seed=5)
        self.assertEqual(g.codex_score,5)
        g.start()
        seen_blast=False
        seen_drop=False
        seen_sound=False
        phases=set()
        for i in range(1,2200):
            g.step(i/60)
            phases.add(g.phase)
            while g.events:
                if g.events.pop(0)=='smash_blast':
                    seen_sound=True
            for _,_,kind,_,_ in g.effects:
                if kind=='blast':
                    seen_blast=True
                elif kind=='score_drop':
                    seen_drop=True
            if g.phase=='rally':
                for ball in g.shots[:]:
                    if g.cue(ball) and ball.progress(g.now)>=.85:
                        pt=project(*ball.position(g.now))[:2]
                        self.assertTrue(g.swing(pt,.86))
                        self.assertTrue(g.shots[-1].hot)
            if 'barrage' in phases:
                break
        self.assertTrue(seen_blast and seen_drop and seen_sound)
        self.assertEqual(g.codex_score,0)
        self.assertEqual(g.player_score,5)
        self.assertIn('连发',g.codex_bubble)
        self.assertIn('charge',phases)
        self.assertIn('barrage',phases)

    def test_gentle_return_continues_rally_without_deducting(self):
        g=Match(seed=7)
        g.start()
        returned_to_player=False
        for i in range(1,600):
            g.step(i/60)
            for ball in g.shots[:]:
                if g.cue(ball) and ball.progress(g.now)>=.88 and g.hits==0:
                    pt=project(*ball.position(g.now))[:2]
                    self.assertTrue(g.swing(pt,.48))
                    self.assertFalse(g.shots[-1].hot)
            if g.hits>=1 and any(b.towards=='player' for b in g.shots):
                returned_to_player=True
                break
        self.assertTrue(returned_to_player)
        self.assertEqual(g.codex_score,5)
        self.assertEqual(g.player_score,0)

    def test_poke_triggers_annoyed_feedback_in_desk_phase_only(self):
        g=Match(seed=3)
        self.assertTrue(g.poke((855,520)))
        self.assertEqual(g.poke_count,1)
        self.assertGreater(g.annoyed_until,g.now)
        self.assertGreater(g.poke_react_at,g.now)
        self.assertIn('codex_poke',g.events)
        self.assertTrue(any(k=='poke' for _,_,k,_,_ in g.effects))
        first_bubble=g.codex_bubble
        self.assertTrue(bool(first_bubble))
        self.assertNotIn('连发',first_bubble)
        # 短时间内多次连戳应有节流缓冲，且生气文案不会频繁闪烁切换
        g.step(g.now+.30)
        self.assertFalse(g.poke((855,520)))
        g.step(g.now+1.10)
        self.assertTrue(g.poke((855,520)))
        self.assertEqual(g.codex_bubble,first_bubble)
        g.step(g.now+3.90)
        self.assertTrue(g.poke((855,520)))
        self.assertNotEqual(g.codex_bubble,first_bubble)
        g.start()
        self.assertFalse(g.poke((855,520)))


class LinkedTest(unittest.TestCase):
    def test_phone_confirmation_precedes_desktop_ball_and_cannot_replay(self):
        now=[100.]
        app=LiveBadminton(run=False,clock=lambda:now[0])
        app.action('desktop',{'open':True,'camera':'tracked'})
        self.assertTrue(app.action('start',{})['applied'])
        now[0]+=2.0
        app.action('desktop',{'camera':'tracked'})
        now[0]+=.65
        waiting=app.action('desktop',{'camera':'tracked'})
        self.assertTrue(waiting['waiting'])
        self.assertEqual(waiting['shots'],[])
        pending=waiting['pending']
        payload={'session':waiting['session'],'id':pending['id'],'side':'left'}
        self.assertFalse(app.action('launch',payload)['applied'])
        app.action('phone',{'visible':False})
        self.assertFalse(app.action('launch',payload)['applied'])
        app.action('phone',{'visible':True})
        self.assertFalse(app.action('launch',dict(payload,session='stale'))['applied'])
        sent=app.action('launch',payload)
        self.assertTrue(sent['applied'])
        self.assertLess(sent['shots'][0]['start'][0],-2.)
        self.assertAlmostEqual(sent['shots'][0]['at']-sent['launch']['at'],.225)
        self.assertFalse(app.action('launch',payload)['applied'])
        self.assertEqual(len(app.snapshot()['shots']),1)
        app.action('close',{})
        self.assertFalse(app.action('launch',payload)['applied'])
        self.assertFalse(app.snapshot()['shots'])


    def test_camera_and_console_controls(self):
        now=[200.]
        app=LiveBadminton(run=False,clock=lambda:now[0])
        app.action('desktop',{'open':True,'camera':'looking','camera_enabled':True,'camera_index':0})
        off=app.action('camera_power',{'enabled':False})
        self.assertTrue(off['applied'])
        self.assertFalse(off['camera_enabled'])
        self.assertEqual(off['cmd'],'camera_off')
        seq1=off['cmd_seq']

        on=app.action('camera_power',{'enabled':True})
        self.assertTrue(on['applied'])
        self.assertTrue(on['camera_enabled'])
        self.assertEqual(on['cmd'],'camera_on')
        self.assertEqual(on['cmd_seq'],seq1+1)

        sw=app.action('camera_switch',{})
        self.assertEqual(sw['camera_index'],1)
        self.assertEqual(sw['cmd'],'camera_switch')

        pv=app.action('camera_preview',{'open':True})
        self.assertTrue(pv['preview_open'])
        self.assertEqual(pv['cmd'],'preview')
        stale=app.action('desktop',{'camera':'looking','preview_open':False,'cmd_ack':pv['cmd_seq']-1})
        self.assertTrue(stale['preview_open'])
        synced=app.action('desktop',{'camera':'looking','preview_open':True,'cmd_ack':pv['cmd_seq']})
        self.assertTrue(synced['preview_open'])

        bar=app.action('bar',{'visible':True,'expanded':False})
        self.assertTrue(bar['bar_visible'])
        self.assertFalse(bar['bar_expanded'])
        self.assertEqual(bar['cmd'],'bar')

        self.assertTrue(app.action('start',{})['applied'])
        now[0]+=2.2
        app.action('desktop',{'camera':'tracked'})
        self.assertEqual(app.snapshot()['phase'],'rally')
        qt=app.action('quit',{})
        self.assertTrue(qt['applied'])
        self.assertEqual(qt['phase'],'quit')

    def test_hand_mode_and_poke_and_force_smash_sync(self):
        now=[300.]
        app=LiveBadminton(run=False,clock=lambda:now[0])
        app.action('desktop',{'open':True,'camera':'tracked','hand_mode':'hands'})
        hm=app.action('hand_mode',{'mode':'racket'})
        self.assertTrue(hm['applied'])
        self.assertEqual(hm['hand_mode'],'racket')
        self.assertEqual(hm['cmd'],'hand_mode')
        stale=app.action('desktop',{'camera':'tracked','hand_mode':'hands','cmd_ack':hm['cmd_seq']-1})
        self.assertEqual(stale['hand_mode'],'racket')
        synced=app.action('desktop',{'camera':'tracked','hand_mode':'racket','cmd_ack':hm['cmd_seq']})
        self.assertEqual(synced['hand_mode'],'racket')

        pk=app.action('poke',{'x':855,'y':520})
        self.assertTrue(pk['applied'])
        self.assertEqual(pk['poke_count'],1)
        self.assertTrue(pk['annoyed'])
        self.assertTrue(any(e['name']=='codex_poke' for e in pk['audio']))

        self.assertTrue(app.action('start',{})['applied'])
        app.action('phone',{'visible':True})
        now[0]+=2.2
        app.action('desktop',{'camera':'tracked'})
        now[0]+=.65
        waiting=app.action('desktop',{'camera':'tracked'})
        pending=waiting['pending']
        self.assertIsNotNone(pending)
        launched=app.action('launch',{'session':waiting['session'],'id':pending['id'],'side':'right'})
        self.assertTrue(launched['applied'])
        ready=launched
        for _ in range(30):
            if ready['can_swing']:
                break
            now[0]+=.12
            ready=app.action('desktop',{'camera':'tracked'})
        self.assertTrue(ready['can_swing'])
        sw=app.action('swing',{'x':.5,'y':.5,'power':.50,'assisted':True,'force_smash':True})
        self.assertTrue(sw['applied'])
        self.assertTrue(any(b['hot'] for b in sw['shots']))

    def test_art_renders_racket_mode_and_annoyed_desk_without_error(self):
        view=View()
        view.now=10.
        view.annoyed_until=12.
        view.codex_bubble='别戳啦！正敲代码呢！'
        view.codex_bubble_until=12.
        hand=Hand(tuple((x,y,0.) for x,y in OPEN),(.50,.59),1.,True)
        cx,cy=player_point(hand.palm)
        _,_,_,tx,ty=racket_tip_for_hand(hand)
        self.assertGreater(math.hypot(tx-cx,ty-cy),30.)
        frame=Art().frame(view,hand,'测试',hand_mode='racket')
        self.assertEqual(frame.size,(1024,704))
        self.assertIsNotNone(frame.getbbox())


if __name__=='__main__':
    unittest.main()

