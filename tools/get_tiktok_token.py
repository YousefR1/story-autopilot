"""Run once on your own computer to connect your TikTok account.

Before running:
- In your TikTok developer app, add this Redirect URI under Login Kit:
    https://YOUR-GITHUB-NAME.github.io/story-autopilot/callback.html
- Have your Client key and Client secret ready.

python tools/get_tiktok_token.py
"""
import secrets
import urllib.parse
import webbrowser

import requests

client_key = input("TikTok Client key: ").strip()
client_secret = input("TikTok Client secret: ").strip()
gh_user = input("Your GitHub username: ").strip()
redirect = f"https://{gh_user}.github.io/story-autopilot/callback.html"
direct = input("Has TikTok approved Direct Post (video.publish) for your app? [y/N]: ").strip().lower() == "y"
scopes = "user.info.basic,video.upload" + (",video.publish" if direct else "")

url = "https://www.tiktok.com/v2/auth/authorize/?" + urllib.parse.urlencode({
    "client_key": client_key,
    "scope": scopes,
    "response_type": "code",
    "redirect_uri": redirect,
    "state": secrets.token_urlsafe(12),
})
print("\nOpening TikTok. Log in with the channel's account and allow access.")
print("If the browser doesn't open, paste this link into it:\n" + url + "\n")
webbrowser.open(url)

code = urllib.parse.unquote(input("Paste the code shown on the callback page: ").strip())
r = requests.post(
    "https://open.tiktokapis.com/v2/oauth/token/",
    headers={"Content-Type": "application/x-www-form-urlencoded"},
    data={
        "client_key": client_key,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect,
    },
    timeout=30,
)
data = r.json()
if "refresh_token" not in data:
    raise SystemExit(f"TikTok didn't return a token: {data}")

print("\nAdd these as GitHub secrets:\n")
print(f"TIKTOK_CLIENT_KEY      = {client_key}")
print(f"TIKTOK_CLIENT_SECRET   = {client_secret}")
print(f"TIKTOK_REFRESH_TOKEN   = {data['refresh_token']}")
print(f"\nGranted scopes: {data.get('scope')}")
print("The refresh token lasts about a year. Re-run this script if TikTok uploads start failing with a login error.")
