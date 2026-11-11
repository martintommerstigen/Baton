"""Provider-neutral Baton connection declarations.

No 'login to any LLM' illusion: actual auth is implemented per provider,
and no provider gets filesystem or external-post access merely by being listed.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Provider:
    key: str
    display: str
    connection: str
    auth: str
    state: str
    notes: str


PROVIDERS = (
    Provider("chatgpt", "ChatGPT / OpenAI", "local-mcp", "official-client",
             "implemented", "Requires installed official ChatGPT desktop and enabled Baton MCP."),
    Provider("mcp", "Annen MCP-kompatibel LLM-klient", "local-mcp", "client-specific",
             "adapter-available", "Client must register Baton STDIO MCP explicitly."),
    Provider("ollama", "Lokal modell (Ollama / OpenAI-kompatibel)", "openai-compatible",
             "local-endpoint", "planned", "No account required for loopback models."),
    Provider("api", "LLM-API (OpenAI / Anthropic / Gemini m.fl.)", "provider-api",
             "scoped-api-key-or-oauth", "planned", "Each provider requires its own supported auth adapter."),
)


def provider_catalog():
    return tuple(PROVIDERS)


def installed_capabilities(provider_key, *, core_live, mcp_configured=False):
    if provider_key not in {p.key for p in PROVIDERS}:
        raise ValueError("unknown model provider")
    return {
        "device_exec": bool(core_live and mcp_configured and provider_key in ("chatgpt", "mcp")),
        "external_post": False,
        "external_contacts": False,
        "model_chat": provider_key == "chatgpt" and mcp_configured,
    }


def can_request_device_access(*, core_live, authenticated, user_approved,
                              local_mcp_capable, revoked):
    """Explicit authorization is required before opening the user's device."""
    return bool(core_live and authenticated and user_approved
                and local_mcp_capable and not revoked)
