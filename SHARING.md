# Baton preview for Ruben

This folder contains source code and tests only. No server credentials, private database or conversation history. It is not a live endpoint.

Android: after Martin configures a secure HTTPS endpoint and gives Ruben his own token, open https://<configured-host>/mobile in Chrome. Do not publish port 8765 directly. No Android ChatGPT session integration is claimed.

To run local tests from this folder:

python3 -m unittest discover -s mobile -p 'test_*.py' -v
python3 -m unittest discover -s desktop -p 'test_*.py' -v
python3 -m unittest discover -s . -p 'test_baton.py' -v

Source must be reviewed for security before internet deployment.