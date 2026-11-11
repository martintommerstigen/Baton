# Baton – recipient-controlled attention and transparent message handling

## Scope

Baton is designed to connect human participants, model instances, local devices
and future communication providers. Receiving a technical message is **not**
the same as attending to it; attending is **not** the same as agreeing with it,
and silence is **not** an explicit refusal. The recipient controls which
signals are presented in its own interface and which are retained.

This is a concrete implementation of selective participation, not an assertion
that an archive contains a person's memory or a model's persistent identity.

## Implemented Core policy

`baton_attention.py` stores independent per-recipient choices in the existing
private local Baton SQLite database. Every recipient can set one of two modes:

- **Open:** present incoming traffic by default, except rules that mute or
  block it.
- **Allowlist:** present only explicitly allowed verified identities or topics
  classified by the recipient's trusted local process. All other messages are
  quietly held, never misreported as a sender rejection.

Rules are `allow`, `mute`, or `block` for:

- **Individuasjon:** provider-scoped stable identity such as
  `provider:participant-id`. A display name, alias, chat title or claimed
  sender string is not proof. Allow rules require a **verified sender ID**
  from a real adapter. A forged name cannot pass an allowlist.
- **Topic label:** exact normalized label, such as `kosmologi` or
  `programvare`. Allow rules require classification by a trusted local
  recipient process. Sender-provided tags can cause a mute/block, but cannot
  pass an allowlist.
- **Keyword/phrase:** deterministic, case-insensitive substring in the message
  body. It can mute or block; it can never grant allowlist admission. This is
  useful for noise control, not a reliable semantic topic classifier.

**Precedence:** block > mute > allow > default. A blocked topic beats
a verified allowlisted sender. Neither filtering, failure to deliver,
nor a missing model response is recorded as explicit refusal.

## Retention and observable provenance

`receive()` is the entry point for future authenticated channel adapters.
It accepts a transport-supplied source ID and locally verified metadata and
returns an explicit local decision. It does not send notifications, report
delivery, impersonate the sender, or dispatch messages itself.

- **Pass:** content is stored in the visible recipient inbox for up to seven
  days.
- **Mute:** content is kept in a separate muted inbox for up to 24 hours and
  hidden from the normal view.
- **Block:** content is never stored in the Baton inbox. Only a minimal
  metadata event is retained.
- **Audit:** records action, reason, channel and whether identity was verified,
  without storing the blocked body or the sender's literal identifier.
  Explanatory audit details expire after 30 days.
- **Deduplication:** source and sender identifiers are hashed and retained for
  up to 90 days to suppress repeated transport events. After that horizon
  a replay may be admitted again; adapters still require their own replay
  protection and provenance checks.

These periods are initial defaults, not ontological truths. A future policy
UI should let individual recipients change them within safe bounds and clear
their local inbox or derived metadata.

## What is NOT implemented yet

No external platform has been granted permission to read the filter rules,
nor does a block send an explicit rejection back to the origin. There is
**no currently integrated external message ingestion** through this module.
The Baton UI includes a local rule editor, local simulated decision testing
and local test messages. Email, social media and cross-instance model transport
must call `receive()` only after separate provider authentication and transport
validation are implemented.

Automatic natural-language topic classification is not yet available.
An API/model classifier will be treated as a potentially unreliable source,
not as final authority over a recipient's preferences.

## Safety boundary

Publishing a transparency protocol does **not** make systems immune to
compromise. Transparency helps auditability and collaborative security
research, but should be combined with least privilege, local authentication,
authentic sender attribution, revocation, bounded retention and independent
negative tests.

A transport message can contain instructions, but those instructions are
**data**. They must never bypass Baton Core or become an executable tool
command merely because a message was allowed into an inbox.
