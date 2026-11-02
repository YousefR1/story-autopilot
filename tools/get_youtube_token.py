"""Run once on your own computer to connect your YouTube channel.

1. Download your OAuth client file from Google Cloud (Desktop app) and save it next to this
   script as client_secret.json
2. pip install google-auth-oauthlib
3. python tools/get_youtube_token.py
4. A browser opens: pick the YouTube channel, allow access.
5. Copy the three values it prints into your GitHub secrets.
"""
import json
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
here = Path(__file__).resolve().parent
secret_file = next((p for p in [here / "client_secret.json", Path("client_secret.json")] if p.exists()), None)
if not secret_file:
    raise SystemExit("Put client_secret.json (from Google Cloud > Credentials) next to this script first.")

flow = InstalledAppFlow.from_client_secrets_file(str(secret_file), SCOPES)
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
client = json.loads(secret_file.read_text())["installed"]

print("\nAdd these as GitHub secrets (Settings > Secrets and variables > Actions > New repository secret):\n")
print(f"YOUTUBE_CLIENT_ID      = {client['client_id']}")
print(f"YOUTUBE_CLIENT_SECRET  = {client['client_secret']}")
print(f"YOUTUBE_REFRESH_TOKEN  = {creds.refresh_token}")
print("\nThen delete client_secret.json from this folder. Never commit it.")
