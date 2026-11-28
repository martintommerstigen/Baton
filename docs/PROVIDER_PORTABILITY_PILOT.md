# Independent provider pilot

This is a standalone, Python-standard-library client for a **new** model request, not a bridge into any existing chat. It neither reads nor writes Core or an existing ChatGPT session. Only Skin talks to Core; only Core changes Core. No automatic forwarding, tool execution, model loop or UI automation. Provider responses are untrusted data.

## 60-second offline start

```sh
printf 'Hello from Baton. What makes a useful shared message protocol?\n' | python3 baton_provider.py gemini --model gemini-4-hydrogen
printf 'Hello from Baton. What makes a useful shared message protocol?\n' | python3 baton_provider.py deepseek --model deepseek-flash
python3 -m unittest -v test_baton_provider
```

Both examples only prepare a request; no provider is contacted. Choose a currently available model for your own account. Model names are explicit so provider upgrades do not silently change them.

## Optional live pilot

Only after explicit approval for provider charges and disclosure of the exact prompt, configure the corresponding GEMINI_API_KEY or DEEPSEEK_API_KEY locally through a trusted secret manager; never paste keys into chats, source or issues. Add the flag `--allow-cost-and-transfer` to one chosen invocation. It makes one HTTPS request with at most 512 requested output tokens and a prompt limit of 16000 UTF-8 bytes. These limits are not a monetary guarantee. A timeout may still consume quota. No automatic retry. A completed provider response is not a recipient ACK, durable archive, existing-chat contact, learning or model identity continuity.

The returned JSON can be examined as an additional archive trace. An authorized participant may choose to retain it locally and use the existing Baton client independently, within applicable access and data boundaries. No automatic relay to existing ChatGPT conversations and no alternative route for a previously rejected operation.

## Evidence and limitations

Seven offline tests passed in a local sandbox on 28 November 2026 (mocked provider HTTP; no real provider invocation). No API keys, paid request, Greg deployment, existing-chat access or integrated Skin handshake verified. This is a candidate client, not a new Core. A later authorized Skin integration must authenticate actor separately from model/provider metadata, preserve reply parent, and handle uncertain outcomes without blind retry. Keep private archives out of public Baton.

Sources: [Gemini compatibility](https://ai.google.dev/gemini-api/docs/openai), [DeepSeek multi-round API](https://api-docs.deepseek.com/guides/multi_round_chat/), [Baton source routes](../START_HERE.md), [existing independent relay](../README.md).
