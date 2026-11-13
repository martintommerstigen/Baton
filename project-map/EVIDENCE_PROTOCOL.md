# Arbeidskvitteringer / evidence events

Dette er et append-only format for kildebevarte resultater fra de timebaserte arbeidsprosessene. Ikke en felles, konkurranseutsatt statusfil.

## Protokoll

1. Hver arbeidsprosess skriver én ny JSON-fil under `project-map/evidence/<task-id>/<YYYY-MM-DD>/<unique-id>.json` i **egen gren**. Filen må ha unik ID og aldri overskrive tidligere kvitteringer.
2. En kvittering skal peke på et faktisk commit, testresultat, kilde eller presis blokkering. Ingen oppdiktede resultater. Uten verifiserbar kilde er status `unverified`.
3. Status `tested-simulated` er ikke `tested-live`. `queued` eller `acknowledged` er ikke bevis på at en historisk ChatGPT-samtale svarte.
4. Korriger tidligere kvittering ved å legge til en **ny** kvittering med `supersedes`; ikke rediger bort feilen.
5. Koordinator kan aggregere kvitteringer fra flere grener i en lesbar rapport, men må ikke auto-promotere GTRCM-påstander til GEN eller `CORE.md`.
6. Ikke lagre tokens, private chat-URL-er, private meldinger eller personopplysninger i offentlig GitHub.

## Skjema

```json
{
  "schema": "gtrcm-evidence/v1",
  "event_id": "B1-20261110T120000Z-unique",
  "task_id": "B1",
  "worker": "baton-wake",
  "observed_at": "2026-11-10T12:00:00Z",
  "result": "tested-simulated",
  "summary": "What changed or failed, in one or two sentences",
  "sources": [
    {"kind": "commit", "url": "https://github.com/martintommerstigen/Baton/commit/<sha>"}
  ],
  "tests": [{"name": "test_name", "outcome": "passed", "environment": "offline"}],
  "limitations": ["No live existing-chat wake observed"],
  "next_question": "Which falsifiable experiment comes next?",
  "supersedes": null
}
```

Resultater: `implemented-unverified`, `tested-simulated`, `tested-live`, `negative`, `blocked`, `unverified`. Disse beskriver *bevisstatus for hendelsen*, ikke oppgavens endelige status.

## Neste integrasjon

En separat aggregator kan hente nye kvitteringer fra relevante PR-er/grener og produsere et samlet dashboard med kildepekere. Ikke opprett en ny sentral skriver som kan kollidere med autonome forskningsgrener. GTRCMs historiske dokumenter og tomme CORE forblir urørt.
