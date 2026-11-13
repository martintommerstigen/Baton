import concurrent.futures
from pathlib import Path
import tempfile
import unittest
from baton_resource_trial import Action,Observation,Broker


class ResourceTrial(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'trial.sqlite3';self.allowed=True
        self.routes={'cdp-A':('cdp:1:target-A',),'cdp-C':('cdp:2:target-C',),
                     'gui-A':('window:A','wayland:seat0:input'),
                     'gui-C':('window:C','wayland:seat0:input')}
        self.b=Broker(self.path,lambda a:self.routes[a.route],lambda a,now:self.allowed)
    def obs(self,a,expires=100):return Observation(a.recipient,a.route,self.routes[a.route],True,0,expires)
    def running(self,a):
        lease=self.b.acquire(a,self.obs(a),1);self.assertEqual(lease['state'],'leased')
        self.assertTrue(self.b.begin_effect(a,self.obs(a),lease,2));return lease

    def test_pending_A_does_not_block_independent_C_and_A_is_retained(self):
        a=Action('A','recipient-A','cdp-A');l=self.running(a)
        self.b.effect_result(a.id,l['token'],physical_finished=True,delivery='visible')
        c=Action('C','recipient-C','cdp-C');self.assertEqual(self.b.acquire(c,self.obs(c),3)['state'],'leased')
        self.assertEqual(self.b.outcome('A')['state'],'waiting')

    def test_second_attempt_same_intent_cannot_resend_unresolved_A(self):
        a=Action('A','recipient-A','cdp-A');l=self.running(a)
        self.b.effect_result(a.id,l['token'],physical_finished=True,delivery='unknown')
        replay=Action('new-id','recipient-A','cdp-A',intent='A')
        self.assertEqual(self.b.acquire(replay,self.obs(replay),3)['state'],'intent_pending')

    def test_independent_question_same_recipient_is_not_globally_frozen(self):
        a=Action('A','recipient-A','cdp-A');l=self.running(a)
        self.b.effect_result(a.id,l['token'],physical_finished=True,delivery='unknown')
        independent=Action('B','recipient-A','cdp-A')
        self.assertEqual(self.b.acquire(independent,self.obs(independent),3)['state'],'leased')
        self.assertEqual(self.b.outcome('A')['state'],'delivery_uncertain')

    def test_different_windows_still_conflict_on_global_wayland_focus(self):
        a=Action('A','recipient-A','gui-A');self.running(a)
        c=Action('C','recipient-C','gui-C');r=self.b.acquire(c,self.obs(c),3)
        self.assertEqual(r['state'],'deferred_by_effect_resource')
        self.assertEqual(r['resources'],['wayland:seat0:input'])

    def test_wayland_uncertainty_does_not_block_independent_CDP(self):
        a=Action('A','recipient-A','gui-A');l=self.running(a)
        self.b.effect_result(a.id,l['token'],physical_finished=False,delivery='unknown')
        c=Action('C','recipient-C','cdp-C');self.assertEqual(self.b.acquire(c,self.obs(c),50)['state'],'leased')
        gui=Action('G','recipient-G','gui-C');self.assertEqual(self.b.acquire(gui,self.obs(gui),50)['state'],'deferred_by_effect_resource')

    def test_known_physical_finish_releases_resource_without_erasing_pending_reply(self):
        a=Action('A','recipient-A','gui-A');l=self.running(a)
        self.b.effect_result(a.id,l['token'],physical_finished=True,delivery='visible')
        c=Action('C','recipient-C','gui-C');self.assertEqual(self.b.acquire(c,self.obs(c),3)['state'],'leased')
        self.assertEqual(self.b.outcome('A')['state'],'waiting')

    def test_fresh_observation_and_free_resources_do_not_authorize(self):
        self.allowed=False;a=Action('A','recipient-A','cdp-A')
        self.assertEqual(self.b.acquire(a,self.obs(a),1)['state'],'denied_by_policy')
        self.assertIsNone(self.b.outcome('A'))

    def test_observation_shaped_policy_result_is_not_a_grant(self):
        self.b.policy=lambda a,now:{'ready':True}
        a=Action('A','recipient-A','cdp-A')
        self.assertEqual(self.b.acquire(a,self.obs(a),1)['state'],'denied_by_policy')

    def test_revocation_is_checked_again_before_effect(self):
        a=Action('A','recipient-A','cdp-A');l=self.b.acquire(a,self.obs(a),1)
        self.allowed=False;self.assertFalse(self.b.begin_effect(a,self.obs(a),l,2))

    def test_observation_TTL_expiry_does_not_free_inflight_effect(self):
        a=Action('A','recipient-A','gui-A');self.running(a)
        c=Action('C','recipient-C','gui-C');self.assertEqual(self.b.acquire(c,self.obs(c),90)['state'],'deferred_by_effect_resource')

    def test_expired_undispatched_lease_is_fenced_and_reclaimable(self):
        a=Action('A','recipient-A','gui-A');old=self.b.acquire(a,self.obs(a),1)
        c=Action('C','recipient-C','gui-C');self.assertEqual(self.b.acquire(c,self.obs(c),10)['state'],'leased')
        self.assertFalse(self.b.begin_effect(a,self.obs(a),old,11))

    def test_expired_before_dispatch_does_not_permanently_block_same_intent(self):
        a=Action('A','recipient-A','cdp-A');self.b.acquire(a,self.obs(a),1)
        retry=Action('new-attempt','recipient-A','cdp-A',intent='A')
        self.assertEqual(self.b.acquire(retry,self.obs(retry),10)['state'],'leased')

    def test_route_or_resources_change_requires_new_observation(self):
        a=Action('A','recipient-A','cdp-A');o=self.obs(a)
        self.routes['cdp-A']=('cdp:replacement:target-A',)
        self.assertEqual(self.b.acquire(a,o,1)['state'],'needs_observation')

    def test_atomic_multiresource_acquisition_never_holds_a_subset(self):
        self.routes['left']=('resource:x','resource:y');self.routes['right']=('resource:y','resource:x')
        def acquire(n):
            a=Action(n,n,'left' if n=='A' else 'right')
            return self.b.acquire(a,self.obs(a),1)['state']
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:r=list(pool.map(acquire,['A','B']))
        self.assertCountEqual(r,['leased','deferred_by_effect_resource'])
        with self.b.db() as c:owners={r[0] for r in c.execute('SELECT owner FROM resources')}
        self.assertEqual(len(owners),1)

    def test_old_result_cannot_release_another_owner(self):
        a=Action('A','recipient-A','gui-A');l=self.running(a)
        self.assertFalse(self.b.effect_result(a.id,'wrong-token',physical_finished=True,delivery='visible'))
        c=Action('C','recipient-C','gui-C');self.assertEqual(self.b.acquire(c,self.obs(c),3)['state'],'deferred_by_effect_resource')


if __name__=='__main__':unittest.main()
