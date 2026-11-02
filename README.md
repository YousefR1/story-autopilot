# Story Autopilot

Every day this makes a ~60-second story video and posts it:

1. **Claude** picks a fresh story in a rotating genre and writes the script, title and captions.
2. **OpenAI** reads it aloud with a natural AI voice, then times every word for captions.
3. **OpenAI** paints one picture per scene, and the video slowly zooms or pans across each one.
   (Optional: switch `visuals.source` to `stock` for Pexels stock video instead.)
4. **ffmpeg** edits it into a 1080×1920 video with bold, word-by-word captions.
5. Quality checks run (length, size, audio not silent). If anything fails, nothing is posted.
6. **YouTube**: posted publicly as a Short, with the AI label set.
   **TikTok**: sent to your TikTok inbox as a draft. You get a notification and tap **Post**.
7. The run is logged to your **dashboard**. After 3 failures in a row it pauses itself.

It all runs free on **GitHub Actions**. The only running costs are the AI calls, roughly a few
cents per video (check current prices on each site).

---

## Setup (about 45-60 minutes, once)

### 1. GitHub (where it runs)
1. Make a free account at **github.com** if you don't have one.
2. Create a new repository named **`story-autopilot`**, set to **Public** (needed for the free dashboard
   site; your keys stay hidden in Secrets).
3. Upload everything in this folder. Click **Add file → Upload files** and drag the folder contents in.
   - If the hidden `.github` folder doesn't come along, click **Add file → Create new file**, type
     `.github/workflows/daily.yml` as the name, and paste in that file's contents.
4. **Settings → Actions → General → Workflow permissions**: choose **Read and write**, then Save.
5. **Settings → Pages**: Source **Deploy from a branch**, branch **main**, folder **/docs**, then Save.
   Your dashboard will be at `https://YOUR-GITHUB-NAME.github.io/story-autopilot/`.
6. Edit `config.yaml` → set `channel.name`. Edit `docs/privacy.html` and `docs/terms.html` → replace
   `Your Channel Name` and `[your contact email]`.

### 2. AI and footage keys
| Site | What to do | Secret name |
|---|---|---|
| console.anthropic.com | Add a little credit, create an API key | `ANTHROPIC_API_KEY` |
| platform.openai.com | Add a little credit, create an API key | `OPENAI_API_KEY` |

### 3. YouTube
1. Create a new Google account (or use yours) and create the YouTube channel on youtube.com.
2. Go to **console.cloud.google.com** → create a project, e.g. "Story Autopilot".
3. **APIs & Services → Library** → enable **YouTube Data API v3**.
4. **OAuth consent screen** (Google Auth Platform): User type **External**; fill in app name and your email.
   Add the scope `.../auth/youtube.upload`. Add your channel's Google account as a test user.
5. Important: on the **Audience** page click **Publish app** (status "In production").
   If it stays in "Testing", Google expires the login after 7 days and uploads stop. You don't need
   Google's verification. You'll just see an "unverified app" warning when you log in, which is fine
   since you're the only user.
6. **Credentials → Create credentials → OAuth client ID → Desktop app**. Download the JSON and save it
   as `tools/client_secret.json` on your computer.
7. On your computer, in this folder:
   ```
   pip install google-auth-oauthlib requests
   python tools/get_youtube_token.py
   ```
   Log in with the channel's account, choose the channel, click through the warning, and allow.
   It prints `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET` and `YOUTUBE_REFRESH_TOKEN`.
   Then delete `client_secret.json`.

### 4. TikTok
1. Create the TikTok account in the app.
2. Go to **developers.tiktok.com** → log in → **Manage apps → Connect an app**.
3. Fill in:
   - **App icon, name, category** (Entertainment), short description ("Uploads my own story videos to my account").
   - **Terms of Service URL**: `https://YOUR-GITHUB-NAME.github.io/story-autopilot/terms.html`
   - **Privacy Policy URL**: `https://YOUR-GITHUB-NAME.github.io/story-autopilot/privacy.html`
   - **Platform**: Web, URL `https://YOUR-GITHUB-NAME.github.io/story-autopilot/`.
     If TikTok asks you to verify it, it gives you a small file. Put that file in `docs/` on GitHub.
4. **Add products**: **Login Kit** and **Content Posting API**.
   - Login Kit → Redirect URI: `https://YOUR-GITHUB-NAME.github.io/story-autopilot/callback.html`
   - Scopes: `user.info.basic`, `video.upload`
5. To test right away, switch to **Sandbox**, add your TikTok account as a **target user**, and use the
   sandbox Client key/secret. For daily use, **Submit for review**. Upload-to-inbox is the simple tier.
   Reviews can take days to weeks.
6. On your computer:
   ```
   python tools/get_tiktok_token.py
   ```
   Paste the Client key and secret, allow access in the browser, copy the code shown on the callback
   page back into the terminal. It prints the three TikTok secrets.

### 5. Add the secrets to GitHub
**Repository → Settings → Secrets and variables → Actions → New repository secret**, one per line:

```
ANTHROPIC_API_KEY      OPENAI_API_KEY
YOUTUBE_CLIENT_ID      YOUTUBE_CLIENT_SECRET YOUTUBE_REFRESH_TOKEN
TIKTOK_CLIENT_KEY      TIKTOK_CLIENT_SECRET  TIKTOK_REFRESH_TOKEN
```
Optional:
- `DISCORD_WEBHOOK_URL`: a message in your Discord when a video posts or something fails
  (Discord channel → Edit → Integrations → Webhooks).
- `GH_PAT`: a GitHub token with "Secrets: read and write" on this repo, so a renewed TikTok login
  is saved automatically.

### 6. Test run (doesn't post)
**Actions → Daily story video → Run workflow** (leave "dry run" ticked) → Run.
After ~3-5 minutes, open the run and download the video under **Artifacts**. Watch it.

### 7. Go live
Nothing else is needed. It runs every day at 16:41 Oslo time (winter). To change the time, edit the
`cron` line in `.github/workflows/daily.yml` (it's in UTC).

---

## Everyday control
- **Pause:** in `config.yaml` set `agent.enabled: false`.
- **Change style:** edit genres, tone, voice and length in `config.yaml`.
- **Background music:** add royalty-free `.mp3` files to `assets/music/`.
- **Fully automatic TikTok:** if TikTok approves Direct Post (`video.publish`) for your app, re-run
  `get_tiktok_token.py` (answer "y"), update the secret, and set `tiktok.mode: direct`.
- **After a pause from failures:** check the error on the dashboard, fix it, then run the workflow with
  **force** ticked and dry run unticked.

## Good to know
- YouTube doesn't pay out for mass-produced, repetitive content. The rotating genres, no-repeat memory
  and fresh footage help. The best protection is to check the videos now and then and keep the
  writing distinct (tweak `tone` and `genres`).
- Videos are labelled as AI-generated on both platforms. OpenAI's terms require telling viewers the
  voice is AI, and the YouTube description does this.
- True stories are written from the model's memory and can contain mistakes. Set
  `allow_true_stories: false` for fiction only.
- Pictures are AI-generated (OpenAI). OpenAI may require organization verification before its image
  models work: platform.openai.com → Settings → Organization → Verify.
