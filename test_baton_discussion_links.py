import concurrent.futures
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from baton_discussion_links import Discussion

A='6aef341a-d850-83ed-a3b2-c735a215bce3'
B='6aee69e6-21ec-83eb-8b0e-ab43497695b0'


class DiscussionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.now=100
        self.d=Discussion(Path(self.tmp.name)/'topics.sqlite3',clock=lambda:self.now)
        self.d.init();self.d.thread('link-flow','Link flow')

    def post(self,**kw):
        return self.d.write('link-flow',A,'som-run-1','A real question',**kw)

    def test_direct_discussion_not_chat_import(self):
        link=self.post(recipient=B,kind='question')
        r=self.d.read(link)
        self.assertEqual(r['post']['claimed_author'],A)
        self.assertEqual(r['post']['verification_state'],'claimed_local_writer')
        self.assertEqual(r['metadata_mismatches'],[])
        reply=self.d.write('link-flow',B,'vev-run-1','Counterexample',reply=link)
        self.assertEqual(self.d.read(reply)['post']['reply_post'],r['post']['post_id'])
        self.assertEqual(len(self.d.posts('link-flow')),2)

    def test_link_metadata_cannot_change_author_or_lifetime(self):
        link=self.post(ttl=10)
        u=urlsplit(link);q=dict(parse_qsl(u.query,keep_blank_values=True))
        q['from']=B;q['until']='9999999999'
        forged=urlunsplit((u.scheme,u.netloc,u.path,urlencode(q),''))
        self.now=111;r=self.d.read(forged)
        self.assertEqual(set(r['metadata_mismatches']),{'from','until'})
        self.assertEqual(r['post']['claimed_author'],A)
        self.assertTrue(r['invitation_expired'])
        self.assertEqual(r['post']['body'],'A real question')

    def test_pinned_revision_exposes_newer_correction(self):
        link=self.post();p=self.d.read(link)['post']
        newer=self.d.write('link-flow',A,'som-run-2','Corrected question',kind='correction',
                           revise=p['post_id'],expected_revision=1)
        old=self.d.read(link)
        self.assertEqual(old['post']['body'],'A real question')
        self.assertTrue(old['newer_revision_available'])
        self.assertEqual(old['latest_link'],newer)

    def test_revision_compare_and_swap_with_concurrent_writers(self):
        p=self.d.read(self.post())['post']
        def revise(n):
            try:
                self.d.write('link-flow',A,'run-'+str(n),'Revision '+str(n),
                             revise=p['post_id'],expected_revision=1)
                return 'written'
            except ValueError:return 'conflict'
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(list(pool.map(revise,[1,2])),['written','conflict'])

    def test_cross_topic_reply_rejected(self):
        link=self.post();self.d.thread('other-topic','Other topic')
        with self.assertRaises(ValueError):
            self.d.write('other-topic',B,'vev-run-1','Reply',reply=link)

    def test_duplicate_unknown_metadata_and_wrong_routes_rejected(self):
        link=self.post()
        for bad in [link+'&v=1',link+'&exec=hostname',link.replace('baton://local','https://evil'),
                    link.replace('baton://local','baton://user@local'),link+'#execute']:
            with self.subTest(bad=bad),self.assertRaises(ValueError):self.d.read(bad)

    def test_local_writer_cannot_claim_verified_state(self):
        p=self.d.read(self.post(source_evidence='claimed citation'))['post']
        self.assertEqual(p['source_evidence'],'claimed citation')
        self.assertEqual(p['verification_state'],'claimed_local_writer')
        self.assertTrue(p['transport_actor'].startswith('local-os:'))

    def test_read_does_not_create_reply_or_ack(self):
        link=self.post()
        for _ in range(3):self.d.read(link)
        self.assertEqual(len(self.d.posts('link-flow')),1)

    def test_revision_cannot_change_claimed_author(self):
        p=self.d.read(self.post())['post']
        with self.assertRaises(ValueError):
            self.d.write('link-flow',B,'vev-run-1','Replaced',revise=p['post_id'],expected_revision=1)


if __name__=='__main__':unittest.main()
