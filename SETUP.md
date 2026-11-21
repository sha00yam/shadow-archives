# Shadow Archives — Setup Guide (click-by-click, ~30 minutes)
## No coding needed. You only copy, paste, and click.

### Step 1 — Create the GitHub repo (5 min)
1. Go to https://github.com/new
2. Repository name: `shadow-archives`
3. Choose **Public** (unlimited free Actions minutes) or Private (2,000 min/month free).
4. Tick "Add a README file". Click **Create repository**.

### Step 2 — Upload these pipeline files (5 min)
1. On your new repo page, click **Add file → Upload files**.
2. Upload everything from this `pipeline/` folder, keeping the folder structure:
   - `.github/workflows/daily-shorts.yml`
   - `scripts/generate.py`
   - `scripts/topics.csv`
   - `scripts/prompts.md`
   - `requirements.txt`
   - `README.md`
3. Click **Commit changes**.

Tip: if GitHub's web upload hides the `.github` folder, use the "upload" button
and drag the whole folder in — it keeps the structure. Or tell Muse and I will
give you the files one by one to paste in the web editor.

### Step 3 — Get your two free API keys (10 min)

**Gemini key (for scripts):**
1. Go to https://aistudio.google.com/apikey
2. Sign in with Google. Click **Create API key**.
3. Copy the key. Keep it private — never post it publicly.

**Pexels key (for stock video):**
1. Go to https://www.pexels.com/api/
2. Click **Request API key**, fill the short form (say "personal YouTube Shorts project").
3. Copy the key from your Pexels profile page.

### Step 4 — Add the keys as GitHub Secrets (5 min)
1. In your repo, go to **Settings → Secrets and variables → Actions**.
2. Click **New repository secret**. Name: `GEMINI_API_KEY`, value: your Gemini key. Save.
3. Again: Name: `PEXELS_API_KEY`, value: your Pexels key. Save.
4. Secrets are hidden — nobody can see them, and they never appear in the code.

### Step 5 — Test run (5 min + ~20 min render)
1. In your repo, go to **Actions → Daily Shorts → Run workflow → Run workflow**.
2. Wait ~15–25 minutes. You can close the tab — it runs on GitHub's servers.
3. When it finishes (green tick), open the run, scroll to **Artifacts**, download `shorts-YYYY-MM-DD`.
4. Watch all 4 videos. Tell Muse what to fix.

### Step 6 — Go live
- The workflow runs automatically every day at 5:00 AM IST.
- Each morning, download the 4 videos from the latest Actions run, review them,
  upload the good ones to YouTube yourself.
- If a run fails (red X), open it, screenshot the error, send it to Muse — I will fix it.

### Daily routine reminder
- 20 minutes: download → watch → upload → mark done.
- Never upload a video you would not watch yourself.
- At upload, tick YouTube's AI-content disclosure box when the video uses AI voice/visuals.
- Audience setting: "Not made for kids" (our audience is teens 13–25).

### If something breaks
- Gemini limit hit? The script falls back to a template script so the video still renders. Tell Muse and we switch to Groq as backup.
- Pexels has no clip for a topic? The script falls back to a dark AI-style background with captions — video still renders.
- Out of GitHub minutes (private repo)? Switch the repo to Public in Settings → General → Danger Zone → Change visibility. Code contains no secrets, so this is safe.
