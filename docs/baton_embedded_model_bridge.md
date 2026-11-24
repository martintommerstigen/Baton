# Baton ↔ ChatGPT ↔ Greg Core — automatic session while UI is open

## Runtime behavior

Launching Baton as Greg's normal user starts a private Core service on 127.0.0.1:52526. If an existing service occupies that port, Baton will use it only when it accepts a harmless authenticated command using the user's private token. Core is owned by Baton while UI runs; no root or external listener.

Opening an existing ChatGPT conversation inside Baton automatically arms the tool bridge for that **exact conversation URL**. A one-time bootstrap asks the model to issue BATON_TOOL_V1 for /usr/bin/hostname; further commands use new request IDs. There is no per-command activation button. Switching chats terminates the previous session and permits a new one when the next page loads. The visible Stop button suspends automatic activation until manually restarted.

Commands execute with the ordinary Linux user's file privileges, including write permission. The program returns BATON_TOOL_RESULT_V1. A reported write must be confirmed by a matching successful result and independent read-back. This is not a ChatGPT-native tool; it works only for the conversation rendered in the running Baton Qt window, and it does not make the model work autonomously while no chat turn is being produced.

## Start

1. Close all Baton windows.
2. On Greg run:

    cd ~/.local/share/baton-evening
    git pull --ff-only origin feature/evening-local-terminal-2026-11-10
    python3 -m unittest -v test_baton_local_runtime.py test_baton_model_bridge.py
    ./run_baton_chatgpt.sh

3. Open an existing chat. Baton should send its bootstrap automatically. The assistant must emit the three-line tool frame; a click is not proof of a successful Core operation.

## Evidence and safety

- test_baton_local_runtime.py performs a real authenticated HTTP write/read-back through a loopback-only Core on the test machine, and verifies unauthenticated requests fail. It is **not** a live test on Greg or proof that the ChatGPT UI accepted a tool response.
- The Core token file is owner-only (0600). Neither that token nor ChatGPT browser cookies should enter messages, GitHub or terminal output.
- Broad user-level command execution presents prompt-injection risk. Use this window only with trusted chats; close Baton or click Stop to disable the model bridge. Stop does not necessarily cancel an already-running OS command.
- The app does not provide root privileges and should not be exposed to a public network.
- If an external Core was started separately before Baton, closing Baton disables the UI-to-Core bridge, not the pre-existing Core process.
- DOM changes, failed sends, incomplete tool frames, duplicate request IDs, and uncertain delivery must fail closed; do not infer successful execution from queued or clicked messages.

## Known limitations

Authentication of the selected ChatGPT turn is currently based on the page's assistant-labelled DOM and a per-session nonce; it is not cryptographic model identity. This implementation does not create native ChatGPT tool registration or prove autonomous A→B→C conversation handoff.