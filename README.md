# Shadow Archives — Pipeline v1
## What this is

A free, automated pipeline that makes 4 YouTube Shorts per day on GitHub's servers.
No laptop needed. No money needed.

## Files in this folder

- `.github/workflows/daily-shorts.yml` — the GitHub Actions schedule (runs daily, 5 AM IST)
- `scripts/generate.py` — the main pipeline: script → voice → visuals → video
- `scripts/topics.csv` — 30-day topic backlog (2 facts/science + 2 history/what-if per day)
- `scripts/prompts.md` — the exact AI prompts for scripts, titles, descriptions
- `requirements.txt` — Python packages
- `SETUP.md` — click-by-click setup guide (start here)

## How it works

1. GitHub Actions wakes up daily at 5:00 AM IST.
2. `generate.py` picks today's 4 topics from `topics.csv` (skips ones marked `done`).
3. For each topic, Gemini (free tier) writes a 120–150 word script.
4. edge-tts creates a deep, calm voiceover (en-US-GuyNeural, -5% speed).
5. Pexels API fetches free stock clips matching the topic keywords.
6. FFmpeg assembles: 1080x1920 vertical video, slow zoom, dark vignette,
   captions burned in, low royalty-free music bed.
7. The 4 MP4s + a `titles.txt` file are uploaded as a GitHub Actions artifact
   (free, downloadable for 90 days). You download them and upload to YouTube.
8. Topics are marked `done` so nothing ever repeats.

Google Drive auto-upload is v2. For v1, download from the Actions run page —
it is simpler and needs no extra credentials.

## Free limits (all respected)

- Gemini free tier: 4 scripts/day is well inside it.
- Pexels free API: 200 requests/hour, 20,000/month — we use ~12/day.
- GitHub Actions: public repo = unlimited minutes. Private repo = 2,000 min/month.
  Each video render is ~3–5 min, so 4 videos ≈ 20 min/day ≈ 600 min/month. Fits.
- edge-tts: free, no key needed.

## What you need (all free)

1. GitHub account
2. Gemini API key — https://aistudio.google.com/apikey
3. Pexels API key — https://www.pexels.com/api/
4. (Optional) Pixabay key as backup — https://pixabay.com/api/docs/

See SETUP.md for the click-by-click guide.
