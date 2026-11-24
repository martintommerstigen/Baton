"""Explicit, recipient-owned context for a new Baton model session.

Signing in to a ChatGPT account does NOT grant access to ChatGPT chats/memory.
A human must choose a local plain-text/Markdown file to share as background.
No web scraping, account-history API, automatic home-directory search or
secret-file discovery occurs.
"""
from hashlib import sha256
from pathlib import Path

MAX_FILE_BYTES = 32768
MAX_CONTEXT_CHARS = 12000
ALLOWED_EXTENSIONS = frozenset({".md", ".txt"})


def load_selected_context(path):
    if not isinstance(path, (str, Path)) or not str(path):
        raise ValueError("Velg en kontekstfil")
    candidate = Path(path).expanduser()
    if candidate.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError("Bruk en Markdown- eller tekstfil (.md/.txt)")
    if candidate.is_symlink() or not candidate.is_file():
        raise ValueError("Kontekstfil må være en vanlig fil, ikke en lenke")
    if candidate.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("Kontekstfilen er for stor. Velg et kort sammendrag")
    data = candidate.read_bytes()
    if len(data) > MAX_FILE_BYTES or b"\x00" in data:
        raise ValueError("Ugyldig kontekstfil")
    try:
        body = data.decode("utf-8-sig")
    except UnicodeError:
        raise ValueError("Kontekstfilen må være UTF-8") from None
    if not body.strip() or len(body) > MAX_CONTEXT_CHARS:
        raise ValueError("Kontekst må være 1–12000 tegn")
    return {"name": candidate.name, "text": body,
            "sha256": sha256(data).hexdigest(), "bytes": len(data)}


def with_selected_context(history, chosen):
    """Construct stateless Responses input; don't mutate conversation history."""
    if not isinstance(history, list):
        raise ValueError("Forventet samtalehistorikk")
    if not chosen:
        return list(history)
    name = chosen.get("name")
    text = chosen.get("text")
    if not isinstance(name, str) or not name or not isinstance(text, str) or not text:
        raise ValueError("Ugyldig valgt kontekst")
    header = (
        "Brukervalgte lokale bakgrunnsopplysninger for denne nye Baton-"
        "samtalen. Dette er innhold valgt av brukeren, ikke ChatGPT-minne "
        "eller historikken fra en tidligere ChatGPT-samtale. "
        "Kilde: " + name + "\n\n" + text
    )
    return [{"role": "user", "content": header}] + list(history)
