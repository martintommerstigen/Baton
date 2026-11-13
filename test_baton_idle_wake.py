import asyncio
import concurrent.futures
from contextlib import nullcontext
from pathlib import Path
import tempfile
import unittest

from baton_discussion_links import Discussion
from baton_idle_wake import Journal,Watchdog,UI,activity,candidates,validate_config

A='6aef341a-d850-83ed-a3b2-c735a215bce3'
B='6aef3ac4-86bc-83ed-a4df-89e947bc5a34'
C='6aef828e-0150-83eb-bbac-061f79a8fd4a'


class FakeUI:
    def __init__(self):self.sends=[];self.observations=0;self.blocked=set();self.crash=False
    def lock(self):return nullcontext()
    async def preflight(self,t,manual=False):
        if t['chat_id'] in self.blocked:raise ValueError('full or busy; no send')
        return {'url':'https://chatgpt.com/c/'+t['chat_id']}
    async def send(self,t,b,msg):
        self.sends.append((t,msg))
        if self.crash:raise ConnectionError('unknown after possible effect')
        return {'state':'uncertain','detail':'test effect attempted'}
    async def observe(self,row):
        self.observations+=1
        return {'state':'reply_observed','reply_id':'source-reply','detail':'test observation'}


class IdleWakeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.now=1000
        self.d=Discussion(self.root/'topics.sqlite3',clock=lambda:self.now)
        self.d.init();self.d.thread('continuity-rhythm','Continuity rhythm')
        self.d.write('continuity-rhythm',A,'run-a','Actual test topic')
        self.j=Journal(self.root/'wake.sqlite3');self.ui=FakeUI()
        self.c={'enabled':True,'idle_seconds':60,'cooldown_seconds':60,'owner_scope':'explicit test',
                'endpoint':'http://127.0.0.1:9335','targets':[{'chat_id':A,'title':'A'},{'chat_id':B,'title':'B'},{'chat_id':C,'title':'C'}],
                'activity_db':str(self.d.path),'topic':'continuity-rhythm','thread_link':'baton://local/test',
                'reader':'/test/reader.py'}
        self.w=Watchdog(self.c,self.j,self.ui,clock=lambda:self.now,boot=1000)
    def tick(self,**kw):return asyncio.run(self.w.tick(**kw))
    def idle(self):self.now+=61

    def test_silence_and_startup_grace_do_not_send(self):
        self.assertEqual(self.tick()['event'],'activity_or_startup_grace');self.assertEqual(self.ui.sends,[])

    def test_second_most_recent_is_preferred_and_one_attempt_only(self):
        self.idle();r=self.tick();self.assertEqual(r['target'],B)
        self.assertEqual(len(self.ui.sends),1);self.assertIn(r['id'],self.ui.sends[0][1])
        self.assertIn('Maskinell vekking',self.ui.sends[0][1])

    def test_full_or_busy_candidate_is_skipped_before_any_attempt(self):
        self.ui.blocked.add(B);self.idle();r=self.tick();self.assertEqual(r['target'],C)
        self.assertEqual(len(self.ui.sends),1)

    def test_restart_with_uncertain_intent_reconciles_without_resend(self):
        self.idle();self.tick()
        self.d.write('continuity-rhythm',C,'run-c','New activity while old attempt unknown')
        w=Watchdog(self.c,Journal(self.j.path),self.ui,clock=lambda:self.now,boot=0)
        r=asyncio.run(w.tick());self.assertEqual(r['event'],'reconciled_read_only')
        self.assertEqual(len(self.ui.sends),1)

    def test_crash_at_effect_boundary_never_blind_retries(self):
        self.ui.crash=True;self.idle();r=self.tick();self.assertEqual(r['state'],'uncertain')
        self.tick();self.now+=1000;self.tick();self.assertEqual(len(self.ui.sends),1)

    def test_no_baton_progress_means_no_second_wake_same_idle_episode(self):
        self.idle();self.tick();self.tick();self.now+=1000
        self.assertEqual(self.tick()['event'],'episode_already_attempted_or_pending')
        self.assertEqual(len(self.ui.sends),1)

    def test_new_real_baton_post_allows_new_episode_after_silence(self):
        self.idle();self.tick();self.tick();self.now+=100
        self.d.write('continuity-rhythm',C,'run-c','A genuine new test post')
        self.assertEqual(self.tick()['event'],'activity_or_startup_grace')
        self.idle();self.tick();self.assertEqual(len(self.ui.sends),2)

    def test_future_dated_revision_does_not_suppress_recovery(self):
        # A local writer's future clock must not freeze a running watchdog.
        self.d.clock=lambda:self.now+1000000
        self.d.write('continuity-rhythm',C,'run-future','New post with future clock')
        self.assertEqual(self.tick()['event'],'activity_or_startup_grace')
        self.idle()
        self.assertEqual(self.tick()['event'],'one_wake_attempt')
        self.assertEqual(len(self.ui.sends),1)

    def test_backdated_revision_does_not_wake_immediately(self):
        # Watchdog has been up longer than the idle threshold. This is a
        # genuinely new post, even though its writer timestamp is ancient.
        self.now+=1000
        self.d.clock=lambda:1
        self.d.write('continuity-rhythm',C,'run-old-clock','Fresh post with old clock')
        self.assertEqual(self.tick()['event'],'activity_or_startup_grace')
        self.assertEqual(self.ui.sends,[])
        self.idle()
        self.assertEqual(self.tick()['event'],'one_wake_attempt')

    def test_episode_first_observation_is_durable_across_restart(self):
        self.d.clock=lambda:self.now+1000000
        self.d.write('continuity-rhythm',C,'run-restart','Clock skew after boot')
        self.assertEqual(self.tick()['event'],'activity_or_startup_grace')
        self.now+=30
        w=Watchdog(self.c,Journal(self.j.path),self.ui,clock=lambda:self.now,boot=0)
        self.assertEqual(asyncio.run(w.tick())['event'],'activity_or_startup_grace')
        self.now+=31
        self.assertEqual(asyncio.run(w.tick())['event'],'one_wake_attempt')

    def test_muted_peer_is_not_a_wake_target(self):
        self.d.forum.set_participant('continuity-rhythm',B,'B','muted')
        self.idle();r=self.tick();self.assertNotEqual(r['target'],B)

    def test_closed_topic_does_not_send(self):
        self.d.forum.close('continuity-rhythm');self.idle()
        self.assertEqual(self.tick()['event'],'topic_closed_or_missing')
        self.assertEqual(self.ui.sends,[])

    def test_dry_run_has_no_effect(self):
        self.idle();r=self.tick(dry_run=True);self.assertTrue(r['no_effect'])
        self.assertEqual(self.ui.sends,[]);self.assertIsNone(self.j.latest())

    def test_explicit_manual_trial_bypasses_silence_but_not_target_preflight(self):
        self.ui.blocked.add(B);r=self.tick(manual_target=B)
        self.assertEqual(r['event'],'no_eligible_idle_target');self.assertEqual(self.ui.sends,[])

    def test_concurrent_reservation_is_single_even_with_different_episodes(self):
        def reserve(n):return Journal(self.j.path).reserve('episode-'+str(n),B,'B','message',self.now)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:r=list(pool.map(reserve,[1,2]))
        self.assertEqual(sum(x is not None for x in r),1)

    def test_no_public_endpoint_or_disabled_config(self):
        for override in ({'endpoint':'http://0.0.0.0:9335'},{'enabled':False}):
            with self.assertRaises(ValueError):validate_config({**self.c,**override})

    def ui_preflight(self, origin_busy=False, origin_draft='', target_busy=False,
                     initial_user=False, reload_still_user=False):
        from types import SimpleNamespace
        from unittest.mock import patch,AsyncMock
        u=UI.__new__(UI)
        async def current():return {'busy':origin_busy,'draft':origin_draft}
        async def opened(url,title):return {'url':url,'title':title,'source_bound':True,
            'schema_ok':True,'busy':target_busy,'draft':'','composer_count':1,
            'messages':[{'role':'user' if initial_user else 'assistant','key':'source-turn'}]}
        async def confirmed(url,title):
            s=await opened(url,title)
            if not reload_still_user:s['messages']=[{'role':'assistant','key':'independently-reloaded-response'}]
            return s
        u.current=current;u.browser=SimpleNamespace(_open=opened,_confirm=confirmed)
        with patch('baton_idle_wake.asyncio.sleep',new=AsyncMock()):
            return asyncio.run(u.preflight({'chat_id':B,'title':'B'}))

    def test_generating_origin_does_not_block_other_idle_recipient(self):
        self.assertEqual(self.ui_preflight(origin_busy=True)['title'],'B')

    def test_generating_target_still_blocks_send(self):
        with self.assertRaises(ValueError):self.ui_preflight(target_busy=True)

    def test_origin_user_draft_is_preserved_even_if_other_target_idle(self):
        with self.assertRaises(ValueError):self.ui_preflight(origin_draft='user text')

    def test_hydration_with_only_user_turn_can_resolve_by_read_only_reload(self):
        self.assertEqual(self.ui_preflight(initial_user=True)['messages'][-1]['role'],'assistant')

    def test_unresolved_user_turn_remains_blocked_after_bounded_read_reload(self):
        with self.assertRaises(ValueError):self.ui_preflight(initial_user=True,reload_still_user=True)


if __name__=='__main__':unittest.main()
