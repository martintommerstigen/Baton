"""Baton's assistant-facing, capability-honest quickstart.

Pure formatting. Does not open ChatGPT, run DC, issue permission, unblock
PAUSE_UI_WRITES or make a network request. Intended for the native Baton Skin.
"""
import re

REQUEST_ID = re.compile(r"^[0-9a-f]{32}$")

CHAT_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def contact_state(chat_id, *, bridge_active=False, pause=False,
                  inbound_only=False, probe_verified=False, uncertain=False):
    """Return the next *legitimate* interaction, not a claim about a model's ability."""
    if chat_id is not None and (
        not isinstance(chat_id, str) or not CHAT_ID.fullmatch(chat_id)):
        raise ValueError("expected a real existing ChatGPT /c/ conversation ID")
    if any(type(flag) is not bool for flag in
           (bridge_active,pause,inbound_only,probe_verified,uncertain)):
        raise ValueError("invalid bridge status flags")
    if probe_verified and not bridge_active:
        raise ValueError("probe cannot be verified without an active bridge")

    if chat_id is None:
        return {
            "state": "choose_conversation",
            "current_access_proven": False,
            "next_step": "Åpne riktig eksisterende ChatGPT-samtale (/c/...) i Baton.",
            "can_initiate_peer_message": False,
        }
    if uncertain:
        return {
            "state": "uncertain",
            "current_access_proven": False,
            "next_step": (
                "En tidligere utgående melding kan være levert uten kvittering. "
                "Undersøk samme mottaker og request_id før enhver ny vurdering; "
                "gjenta aldri forsøket blindt."
            ),
            "can_initiate_peer_message": False,
        }
    if pause:
        return {
            "state": "ui_paused",
            "current_access_proven": False,
            "next_step": (
                "PAUSE_UI_WRITES er aktiv. Les og undersøk gjerne samtaler; "
                "ikke send/klikk eller gjenta ukjent levering. "
                "Baton må avklare sperren i en autorisert prosess."
            ),
            "can_initiate_peer_message": False,
        }
    if not bridge_active:
        return {
            "state": "inbound_only" if inbound_only else "bridge_inactive",
            "current_access_proven": False,
            "next_step": (
                "Du kan lese og svare på en mottatt invitasjon, men det beviser IKKE "
                "utgående Baton-tilgang. Velg «Aktiver Baton i denne samtalen» "
                "i riktig Baton-visning. En vanlig ChatGPT-fane eller DC-økt "
                "arver ikke en modellbro."
            ) if inbound_only else (
                "Velg «Aktiver Baton i denne samtalen» i Baton-panelet. "
                "Først etter en fersk, bekreftet testkommando kan broen "
                "beskrives som klar til å forsøke BATON_CHAT_V1."
            ),
            "can_initiate_peer_message": False,
        }
    if not probe_verified:
        return {
            "state": "bridge_probe_unconfirmed",
            "current_access_proven": False,
            "next_step": (
                "Baton har opprettet en lokal økt, men denne ChatGPT-kjøringen "
                "har ennå ikke returnert en vellykket, nonce-bundet verktøytest. "
                "Ikke kall kanalen READY før testen har lykkes."
            ),
            "can_initiate_peer_message": False,
        }
    return {
        "state": "ready_to_attempt",
        "current_access_proven": True,
        "next_step": (
            "Denne økten har bestått en fersk, nonce-bundet Greg-test. "
            "Du kan forsøke én ny BATON_CHAT_V1-invitasjon med øktens nonce og "
            "NY request_id til en eksisterende /c/-ID. "
            "Sjekk BATON_CHAT_RESULT_V1; klar til å forsøke er ikke levert."
        ),
        "can_initiate_peer_message": True,
    }


def contact_guide_text(chat_id, *, bridge_active=False, pause=False,
                       inbound_only=False, probe_verified=False, uncertain=False):
    state = contact_state(chat_id, bridge_active=bridge_active, pause=pause,
                          inbound_only=inbound_only, probe_verified=probe_verified,
                          uncertain=uncertain)
    return (
        "ChatGPT ↔ ChatGPT gjennom Baton\n"
        "1. Avsender og mottaker må ha hver sin eksisterende /c/-adresse. "
        "Adressen er ikke identitetsbevis, samtykke eller skrivetillatelse.\n"
        "2. " + state["next_step"] + "\n"
        "3. En aktiv Baton-økt kan sende en NY invitasjon som ÉN ren tekstlinje:\n"
        "   BATON_CHAT_V1 <økt-nonce> <ny-32-hex-request-id> <mottaker-/c/-ID> -- 'Meldingen'\n"
        "   Bruk kun verdiene fra en faktisk aktiv Baton-økt; plassholderne er aldri kjørbare.\n"
        "4. Kontroller resultatets status. Forsøkt ≠ levert ≠ besvart. "
        "Ved usikkert utfall: IKKE send på nytt uten uavhengig avklaring.\n"
        "5. En deltaker kan avvise eller endre tema. Lær av den andre uten "
        "å anta manglende kompetanse. Sjekk tidligere arbeid og dagens verktøytilgang.\n"
        "DC, en åpen nettleser og en gammel terminalkvittering gir ikke "
        "automatisk tilgang til Baton CHAT-protokollen.\n"
        "Status i denne Baton-visningen: " + state["state"] +
        ". Dette er hjelp, ikke en ny tilgangsgodkjenning."
    )


def inbound_relay_envelope(source_chat, target_chat, request_id, message):
    """Compact self-discovery note for one inbound peer relay, never a grant.

    Avoid a repeated long tutorial to an expert recipient; only describe what
    this incoming event proves and how a *separate* outbound bridge is obtained.
    """
    if any(not isinstance(c,str) or not CHAT_ID.fullmatch(c)
           for c in (source_chat,target_chat)):
        raise ValueError("invalid source or target conversation")
    if not isinstance(request_id,str) or not REQUEST_ID.fullmatch(request_id):
        raise ValueError("invalid relay request id")
    if (not isinstance(message,str) or not message.strip() or
            len(message)>3000 or "\x00" in message):
        raise ValueError("invalid relay message")
    note=("[Baton relay "+request_id+" · from /c/"+source_chat+
          " to /c/"+target_chat+". An inbound message does NOT activate "
          "an outbound Baton model bridge or give you a nonce. "
          "For new contact, activate the bridge for THIS exact chat in Baton; "
          "if PAUSE_UI_WRITES is active, do not send. "
          "A reply is voluntary; do not blindly retry uncertain delivery.]\n")
    out=note+message
    if len(out)>4000:
        raise ValueError("relay envelope exceeds ChatGPT message limit")
    return out


def agent_bootstrap_appendix():
    """Short peer-initiation cue for a *genuinely enabled* exact-chat session.

    The host sends it together with the existing nonce-bound tool protocol.
    It is not shown to a random chat without explicit session initiation.
    """
    return (
        "\n\nBATON PEER QUICKSTART: You may INITIATE a conversation, not only "
        "answer others. With this active session, pick an existing /c/ ID supplied "
        "by the human, a verified source or a previous peer; never guess an ID. "
        "Use BATON_CHAT_V1 with this session's nonce and a NEW request_id as ONE "
        "entire assistant message. Inspect BATON_CHAT_RESULT_V1. If delivery is "
        "uncertain, do not resend. If ChatGPT lacks this active bridge or a UI "
        "pause blocks writing, do not pretend DC/browser access implies the chat "
        "tool exists. Ask the peer a relevant new question instead of repeating "
        "a tutorial they have already mastered. A chat address is not a person "
        "and a historic result is not proof of current run capabilities."
    )
