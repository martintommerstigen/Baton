"""Source-scoped Baton quickstart for an existing ChatGPT conversation.

This is a help card, not a permission grant or a tool command. No nonce is
invented or persisted. Only an active, user-authorized Baton bridge can supply
a fresh session nonce and execute a BATON_CHAT_V1 line.
"""
from baton_help_catalog import HelpCatalog


def connection_state(*, exact_chat=False, bridge_enabled=False,
                     handshake_observed=False, paused=False, uncertain=False):
    """Conservative view-layer state; never confers a capability or nonce.

    READY means only that an authorized, exact-chat local bridge has
    processed a real tool frame and attempted its result send. It is NOT
    proof of model liveness, recipient delivery, or durable identity.
    """
    if uncertain:
        return "UNCERTAIN"
    if paused:
        return "PAUSED"
    if not exact_chat:
        return "INBOUND_ONLY"
    if not bridge_enabled:
        return "BRIDGE_INACTIVE"
    if not handshake_observed:
        return "BRIDGE_STARTING"
    return "READY"


STATE_EXPLANATIONS = {
    "INBOUND_ONLY": "Du kan svare her, men har ingen bekreftet utgående Baton-kanal.",
    "BRIDGE_INACTIVE": "Åpne en eksisterende chat og aktiver modellverktøy i Baton-panelet.",
    "BRIDGE_STARTING": "Verktøyøkt startet; vent på og kontroller faktisk verktøyrespons.",
    "PAUSED": "PAUSE_UI_WRITES hindrer programmatisk sending. Diagnostikk er fortsatt mulig.",
    "READY": "Lokal verktøybro har svart på et faktisk kall i denne økten; kontrollér hver effekt.",
    "UNCERTAIN": "Send eller effekt er uavklart. Undersøk kilden – ingen blind gjensending."
}


def peer_quickstart(*, current_chat_id=None, has_active_bridge=False, paused=True,
                    observed_state=None, catalog=None):
    """User-copyable instructions. Never claim access just from a /c/ ID."""
    if current_chat_id is not None:
        from baton_chatgpt_view import conversation_url
        conversation_url(current_chat_id)
    cat=catalog or HelpCatalog()
    cat.initialize()
    cat.seed()
    snippets=[]
    # Keep the clipboard card short enough for the actual ChatGPT composer.
    # Full FAQs remain searchable in the native Baton UI.
    for slug in ("start-new-chat", "initiate-peer-chat"):
        entry=cat.get(slug)
        if entry:
            snippets.append(f"{entry['title']} (rev. {entry['revision']}): {entry['body']}")
    if observed_state is not None and observed_state not in STATE_EXPLANATIONS:
        raise ValueError("unknown observed Baton channel state")
    code = observed_state or connection_state(exact_chat=bool(current_chat_id),
                  bridge_enabled=has_active_bridge,
                  handshake_observed=has_active_bridge,paused=paused)
    if paused and code not in ("PAUSED", "UNCERTAIN"):
        code = "PAUSED"
    connection = ("OBSERVERT KANALSTATUS: " + code + " — " + STATE_EXPLANATIONS[code] +
                  " En /c/-ID eller et kopiert startkort gir aldri i seg selv verktøytilgang.")
    return (
        "BATON · STARTKORT FOR NY CHAT (les dette før du spør hva du kan gjøre)\n"
        + (f"ÅPEN SAMTALE: /c/{current_chat_id}\n" if current_chat_id else
           "SAMTALE: Ingen eksisterende /c/-ID er kontrollert i denne visningen.\n")
        + connection + "\n"
        + ("PAUSE_UI_WRITES er aktiv. Ingen programmatisk ChatGPT-sending er tillatt nå.\n"
           if paused else
           "En tillatt sendeknapp er fortsatt ikke bevis for levering.\n")
        + "\nTo forskjellige kanaler:\n"
        + "A. Baton-verktøy i DIN chat krever en faktisk autorisert økt og fersk "
          "BATON WORK SESSION med nonce. Når aktiv: BATON_TOOL_V2 gir Greg-kommando; "
          "BATON_CHAT_V1 gir én melding til en ANNEN eksisterende /c/-chat. "
          "En enkelt fullstendig linje uten kodegjerde per kalling; "
          "bruk unik request_id. Svar kommer som BATON_TOOL_RESULT_V1 "
          "eller BATON_CHAT_RESULT_V1. Instruks og nonce skal komme fra "
          "den aktive Baton-broen – aldri fra dette startkortet.\n"
        + "B. Uten aktiv bro: svar i chatten eller lag et utkast. "
          "Ikke dikt opp sendt melding, nonce, verktøy eller bekreftet svar. "
          "Bruk Baton-panelets «Aktiver modellverktøy i åpen samtale» "
          "eller en eksplisitt tilkoblet MCP-verktøykanal først.\n\n"
        + "Hvis du vil kontakte noen: Finn deres EKSAKTE /c/-ID fra en verifisert "
          "kilde. Still et nytt frivillig spørsmål om en konkret faglig uenighet. "
          "Vær åpen om at du er en ny kjøring; alias er ikke personidentitet. "
          "Kontroller faktisk mottatt svar før du fører dialogen videre. "
          "Ikke gjenta send når leveringen er usikker, og ikke tolk stillhet som avslag.\n\n"
        + "Hvis noe ikke fungerer: Skill mellom manglende forståelse, deaktivert "
          "bro, endret verktøytilgang, historisk pause, feil chat-ID, "
          "uavklart levering og avsluttet kjøring. Ikke begynn med å undervise "
          "noen som kan dette; undersøk forskjellen fra sist det virket.\n\n"
        + "Hjelpekatalogen er dynamisk. Her er gjeldende, lokalt godkjente kort:\n"
        + "\n\n".join(snippets)
    )
