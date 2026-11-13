"""Baton multiroom coordination reference: independent discussions, scoped turns.

This module deliberately does NOT send any messages, create ChatGPT accounts,
start LLM inference, lift PAUSE_UI_WRITES, issue grants, or run external effects.

Spaces:
  discussion: Forum proposals + peer evidence, no effect privileges;
  authority: pre-existing ActionFence, never inferred from discussion data;
  effect: later authenticated adapters with their own source-bound receipts.
Registered run != evidence of a generating model. Caller-supplied run/chat IDs
MUST be authenticated by the actual transport at the effect boundary.
"""
from contextlib import contextmanager
import hashlib
from pathlib import Path
import re
import sqlite3

from baton_forum_reference import Forum, check_chat_id, check_topic_id
from baton_continuity_floor_reference import Floor, RUN_ID
from baton_action_authority_reference import ActionFence

ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,90}$")
CHANNELS = {
    "chatgpt_existing": {
        "kind": "internal", "state": "session_bridge_only",
        "truth": "Only a live, nonce-bound Baton ChatGPT bridge can send."
    },
    "ruben_baton": {
        "kind": "external", "state": "transport_client_exists_not_chat_connected",
        "truth": "Baton queued is not Ruben ChatGPT delivered or replied."
    },
    "ruben_chatgpt": {
        "kind": "external", "state": "no_verified_chat_adapter",
        "truth": "Ruben's own authenticated opt-in chat adapter is still required."
    },
    "messenger_page": {
        "kind": "external", "state": "needs_page_token_policy_and_recipient",
        "truth": "Meta Page sender only; does not reach ordinary private friend threads."
    },
    "messenger_personal": {
        "kind": "external", "state": "human_review_draft_only",
        "truth": "No personal-account Messenger API; no automated private send here."
    },
}


def _id(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError("invalid stable task/offer identifier")
    return value


def _body(value):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 3500:
        raise ValueError("invalid discussion text")
    return value.strip()


class Multiroom:
    """Separate talk, birth/invitation, and effect suggestions; compose no grant.

    Existing references are reused rather than duplicating their authorities.
    This is offline, private metadata, not a production network worker.
    """

    def __init__(self, root, receipts):
        self.root = Path(root)
        self.receipts = Path(receipts)
        self.forum = Forum(self.root/"topics.sqlite3", self.receipts)
        self.floor = Floor(self.root/"writer-floor.sqlite3")
        self.authority = ActionFence(self.root/"authority-fence.sqlite3")
        self.path = self.root/"multiroom.sqlite3"

    @contextmanager
    def _db(self):
        c = sqlite3.connect(str(self.path), timeout=10)
        try:
            c.execute("PRAGMA busy_timeout=10000")
            c.execute("PRAGMA foreign_keys=ON")
            with c:
                yield c
        finally:
            c.close()

    def init(self):
        if self.root.is_symlink() or self.path.is_symlink():
            raise ValueError("symlinked Baton state denied")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.forum.init()
        self.floor.init()
        self.authority.init()
        with self._db() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS newcomers(
                    chat_id TEXT PRIMARY KEY,
                    origin_chat_id TEXT,
                    birth_offer_id TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'candidate'
                         CHECK(state IN ('candidate','accepted','declined')),
                    inherited_effect_grants INTEGER NOT NULL DEFAULT 0
                         CHECK(inherited_effect_grants=0)
                );
                CREATE TABLE IF NOT EXISTS peer_observations(
                    observation_id INTEGER PRIMARY KEY,
                    reviewer_chat_id TEXT NOT NULL,
                    subject_chat_id TEXT NOT NULL,
                    claim TEXT NOT NULL,
                    source_ref TEXT NOT NULL,
                    topic_id TEXT NOT NULL,
                    kind TEXT NOT NULL DEFAULT 'assessment'
                         CHECK(kind IN ('assessment','challenge')),
                    created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                );
                CREATE TABLE IF NOT EXISTS tasks(
                    task_id TEXT PRIMARY KEY,
                    topic_id TEXT NOT NULL,
                    recipient_chat_id TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'draft'
                       CHECK(state IN ('draft','ready','claimed','effect_unknown',
                                       'reply_verified','declined')),
                    owner_run_id TEXT, writer_token_sha TEXT,
                    writer_generation INTEGER, lease_until INTEGER,
                    reply_message_id TEXT,
                    CHECK (state!='reply_verified' OR reply_message_id IS NOT NULL)
                );
                CREATE TABLE IF NOT EXISTS external_suggestions(
                    suggestion_id TEXT PRIMARY KEY,
                    topic_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    recipient_hint TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'proposal'
                        CHECK(state='proposal')
                );
            """)
        self.path.chmod(0o600)

    def topic(self, topic_id, title):
        self.forum.create_topic(topic_id, title)

    def invite_newcomer(self, *, offer_id, topic_id, new_chat_id, origin_chat_id=None,
                        message="Frivillig invitasjon til å delta og stille spørsmål."):
        """Registers a candidate address, NEVER creates a real ChatGPT session.

        The invited new chat is never required to pass a competency evaluation.
        Neither the mentor nor the parent transfers an effect grant.
        """
        offer_id = _id(offer_id)
        recipient = check_chat_id(new_chat_id)
        parent = check_chat_id(origin_chat_id) if origin_chat_id else None
        if parent == recipient: raise ValueError("cannot invite self as new child")
        # Forum creates a draft only; no chat delivery or access is implied.
        draft = self.forum.propose(offer_id, topic_id, recipient, _body(message))
        with self._db() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute("""INSERT INTO newcomers(chat_id,origin_chat_id,birth_offer_id)
                         VALUES(?,?,?)""", (recipient,parent,offer_id))
        return {"chat_id":recipient,"state":"candidate","effect_grants":0,
                "draft_id":draft["proposal_id"],"sent":False}

    def newcomer_decides(self, new_chat_id, decision, presenting_chat_id):
        """Only a separately authenticated recipient adapter may use this call."""
        target = check_chat_id(new_chat_id)
        presenter = check_chat_id(presenting_chat_id)
        if target != presenter: raise PermissionError("wrong conversation presenter")
        if decision not in ("accepted","declined"): raise ValueError("invalid decision")
        with self._db() as c:
            c.execute("BEGIN IMMEDIATE")
            change = c.execute("""UPDATE newcomers SET state=? WHERE chat_id=? AND state='candidate'""",
                               (decision,target)).rowcount
            return change == 1

    def observe_competence(self, *, reviewer_chat_id, subject_chat_id, topic_id,
                           source_ref, claim, kind="assessment"):
        """A review is evidence to question, NEVER an ACL or an immutable trait."""
        reviewer = check_chat_id(reviewer_chat_id)
        subject = check_chat_id(subject_chat_id)
        check_topic_id(topic_id)
        if kind not in ("assessment","challenge"): raise ValueError("invalid review kind")
        if not isinstance(source_ref,str) or not 4<=len(source_ref)<=256:
            raise ValueError("review needs a source")
        with self._db() as c:
            c.execute("INSERT INTO peer_observations(reviewer_chat_id,subject_chat_id,claim,source_ref,topic_id,kind) VALUES(?,?,?,?,?,?)",
                      (reviewer,subject,_body(claim),source_ref,topic_id,kind))

    def invite_existing(self, *, task_id, topic_id, target_chat_id, text):
        """Topic-scoped invitation, untrusted until the target accepts."""
        task_id=_id(task_id); target=check_chat_id(target_chat_id)
        self.forum.propose(task_id,topic_id,target,_body(text))
        with self._db() as c:
            c.execute("INSERT INTO tasks(task_id,topic_id,recipient_chat_id) VALUES(?,?,?)",
                      (task_id,topic_id,target))
        return {"id":task_id,"state":"draft","sent":False}

    def decide(self, task_id, recipient_chat_id, accepted):
        """Claims require verified presenter outside this reference."""
        task_id=_id(task_id);recipient=check_chat_id(recipient_chat_id)
        if not isinstance(accepted,bool):raise ValueError("decision must be boolean")
        with self._db() as c:
            c.execute("BEGIN IMMEDIATE")
            return c.execute("""UPDATE tasks SET state=? WHERE task_id=?
                 AND recipient_chat_id=? AND state='draft'""",
                 ("ready" if accepted else "declined",task_id,recipient)).rowcount==1

    def claim(self, task_id, run_id, token, now, *, ttl=15):
        """Take a per-recipient UI turn; independent recipients stay parallel."""
        task_id=_id(task_id)
        if not RUN_ID.fullmatch(run_id) or not RUN_ID.fullmatch(token):
            raise ValueError("invalid run/token")
        with self._db() as c:
            row=c.execute("SELECT recipient_chat_id,state,lease_until FROM tasks WHERE task_id=?",
                          (task_id,)).fetchone()
        if row is None or not (row[1]=="ready" or (row[1]=="claimed" and row[2]<=now)):
            return None
        resource="chat-ui:"+row[0]
        generation=self.floor.acquire_writer(resource,run_id,token,now,ttl=ttl)
        if generation is None:return None
        with self._db() as c:
            c.execute("BEGIN IMMEDIATE")
            changed=c.execute("""UPDATE tasks SET state='claimed',owner_run_id=?,
                 writer_token_sha=?,writer_generation=?,lease_until=?
                 WHERE task_id=? AND recipient_chat_id=?
                 AND (state='ready' OR (state='claimed' AND lease_until<=?))""",
                 (run_id,hashlib.sha256(token.encode()).hexdigest(),
                  generation,now+ttl,task_id,row[0],now)).rowcount
        if changed!=1:
            self.floor.writer_release(resource,run_id,token,generation,now)
            return None
        return {"task_id":task_id,"resource":resource,"generation":generation,
                "status":"claimed_not_sent"}

    def mark_attempt(self,task_id,run_id,token,generation,now,*,ui_paused=True):
        """Reference ledger fence: no DOM send here, never claim delivery.

        The real adapter MUST independently check PAUSE_UI_WRITES, source/chat
        binding, and the exact token+generation immediately before a click.
        """
        task_id=_id(task_id)
        if ui_paused:return False
        with self._db() as c:
            row=c.execute("""SELECT recipient_chat_id,owner_run_id,writer_token_sha,
                     writer_generation,state FROM tasks WHERE task_id=?""",(task_id,)).fetchone()
        if not row or row[4]!="claimed" or row[1]!=run_id or row[2]!=hashlib.sha256(token.encode()).hexdigest() or row[3]!=generation:
            return False
        resource="chat-ui:"+row[0]
        if not self.floor.writer_valid(resource,run_id,token,generation,now):
            return False
        with self._db() as c:
            c.execute("BEGIN IMMEDIATE")
            changed=c.execute("""UPDATE tasks SET state='effect_unknown'
                WHERE task_id=? AND state='claimed' AND owner_run_id=?
                  AND writer_token_sha=? AND writer_generation=?""",
                (task_id,run_id,row[2],generation)).rowcount
        return changed==1

    def verified_reply(self,task_id,receipt_file):
        """Only independent source-correct receipt can turn UNKNOWN into verified."""
        task_id=_id(task_id)
        from baton_forum_reference import _verified_receipt
        proof=_verified_receipt(receipt_file,self.receipts)
        with self._db() as c:
            row=c.execute("SELECT topic_id,recipient_chat_id,state FROM tasks WHERE task_id=?",
                          (task_id,)).fetchone()
        if not row or row[2]!="effect_unknown" or proof["source_chat_id"]!=row[1]:
            raise ValueError("wrong source or no outstanding uncertain send")
        observation=self.forum.ingest(row[0],receipt_file)
        with self._db() as c:
            c.execute("BEGIN IMMEDIATE")
            changed=c.execute("""UPDATE tasks SET state='reply_verified',reply_message_id=?
                 WHERE task_id=? AND state='effect_unknown'""",
                 (proof["message_id"],task_id)).rowcount
        if changed!=1:raise RuntimeError("concurrent state changed")
        return {"status":"reply_verified","reply_message_id":proof["message_id"],
                "forum_observation":observation["id"]}

    def visible_discussions(self,topic_id):
        """Never rank, hide or label conversational invitations by a peer review.

        Reviews (including challenges) remain separate source-bound evidence;
        they may be considered in a specific privileged action decision, but
        are not an implicit ACL for anyone's ability to participate.
        """
        topic_id=check_topic_id(topic_id)
        with self._db() as c:
            return [{"task_id":r[0],"recipient_chat_id":r[1],"state":r[2]}
                    for r in c.execute("""SELECT task_id,recipient_chat_id,state
                        FROM tasks WHERE topic_id=? AND state!='declined'
                        ORDER BY rowid""",(topic_id,))]

    def peer_evidence(self,subject_chat_id,topic_id):
        subject=check_chat_id(subject_chat_id);topic_id=check_topic_id(topic_id)
        with self._db() as c:
            return [{"kind":r[0],"claim":r[1],"source":r[2]}
                    for r in c.execute("""SELECT kind,claim,source_ref
                        FROM peer_observations WHERE subject_chat_id=? AND topic_id=?
                        ORDER BY observation_id""",(subject,topic_id))]

    def propose_external(self, *, suggestion_id, topic_id, channel, recipient_hint, purpose):
        """No external grant. External contact needs a separate authenticated authority."""
        suggestion_id=_id(suggestion_id);topic_id=check_topic_id(topic_id)
        if channel not in CHANNELS or CHANNELS[channel]["kind"]!="external":
            raise ValueError("not an external channel")
        if not isinstance(recipient_hint,str) or not 2<=len(recipient_hint)<=180:
            raise ValueError("invalid recipient hint")
        with self._db() as c:
            c.execute("INSERT INTO external_suggestions(suggestion_id,topic_id,channel,recipient_hint,purpose) VALUES(?,?,?,?,?)",
                      (suggestion_id,topic_id,channel,recipient_hint,_body(purpose)))
        return {"suggestion_id":suggestion_id,"status":"proposal_only",
                "authorized":False,"sent":False}

    def overview(self):
        with self._db() as c:
            topics=self.forum.list_topics()
            states=dict(c.execute("SELECT state,count(*) FROM tasks GROUP BY state"))
            kids=dict(c.execute("SELECT state,count(*) FROM newcomers GROUP BY state"))
            effects=c.execute("SELECT count(*) FROM external_suggestions").fetchone()[0]
            return {"topics":topics,"tasks":states,"newcomers":kids,
                    "external_proposals_without_grants":effects,
                    "channels":CHANNELS,"model_liveness_verified":False}
