#!/usr/bin/env python3
"""
Shadow Archives — Daily Shorts pipeline v1.4
Language: Hinglish — Hindi voice (Devanagari script), Roman Hindi captions/titles.
Length: ~60 seconds per Short (YouTube Shorts max).
Ratio: 1080x1920 vertical (9:16), 30fps, H.264 + AAC — ready to upload.
v1.4: per-sentence voice synthesis with measured timing (captions in sync),
pure-Hindi scripts (no English words in Devanagari), loudness normalisation.

Free tools only: Gemini (scripts) + Piper offline Hindi voice + Pixabay
(stock video) + FFmpeg. Pexels kept as fallback if a key ever exists.

Reads scripts/topics.csv, picks the next 4 pending topics,
renders 4 vertical Shorts into output/, and marks topics done.
Run by GitHub Actions daily. Also runnable locally for testing.

Env vars:
  GEMINI_API_KEY — Google AI Studio key (free)
  PIXABAY_API_KEY — Pixabay API key (free)
  PEXELS_API_KEY — Pexels API key (free, optional)
"""
import asyncio
import csv
import math
import os
import random
import re
import subprocess
import sys
from pathlib import Path

import requests

try:
    import edge_tts
except ImportError:
    edge_tts = None

# Piper (offline neural TTS), gTTS and transliteration are lazy-imported
# inside their functions so a missing package never breaks the whole script.

ROOT = Path(__file__).resolve().parent.parent
TOPICS_CSV = ROOT / "scripts" / "topics.csv"
OUTPUT = ROOT / "output"
WORK = ROOT / "work"

# --- Voice: Hindi, male narrator (Piper offline — runs on the GitHub runner,
# never blocked like edge-tts). Tested: ~180 Hindi words/min at length 1.1,
# so 160-175 words = ~55-60 seconds.
PIPER_VOICE = "hi_IN-pratham-medium"
PIPER_MODEL_URL = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
    "hi/hi_IN/pratham/medium/hi_IN-pratham-medium.onnx"
)
PIPER_CONFIG_URL = PIPER_MODEL_URL + ".json"
PIPER_LENGTH_SCALE = 1.05  # near-natural pace (1.15 sounded warbly)
EDGE_VOICE = "hi-IN-MadhurNeural"  # fallback only (blocked on runners)
EDGE_RATE = "-5%"
VIDEOS_PER_DAY = 4
# Gemini model fallback chain — model names get retired, so try newest first.
GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-flash-latest",
]
# YouTube Shorts must be vertical 9:16 and 60 seconds or less.
TARGET_SECONDS = 58

SCRIPT_PROMPT = """You write YouTube Shorts scripts in Hindi for teens aged 13-25, mysterious and dramatic tone.
Topic: {topic}
Format: {format}
Niche: {niche}

The script must be DEEP, not shallow: go into real detail — names, dates, numbers, how it happened, why it matters. The viewer must learn something surprising, not just hear a generic summary.

Return your answer in EXACTLY these 4 sections, with these exact headings:

DEVANAGARI:
Write the full spoken script in Hindi, Devanagari script, 160-175 words (about 55-60 seconds spoken). Simple, spoken Hindi, short sentences.
PURE HINDI ONLY: every single word in Devanagari script. Never write any English word — translate the topic itself into Hindi. Write numbers as Hindi words (दस, सौ, हज़ार, लाख), never digits. English words make the Hindi voice mispronounce them.
Structure:
1. Hook (first 3 seconds): a secret, a shocking number, or a question.
2. Setup (2-3 lines): context — what, when, where.
3. Deep dive (3 points): three surprising details or revelations, each with a specific fact (a name, date, number or reason). Go deeper with each point.
4. Mid-hook (1 line in the middle): "lekin sabse bada raaz abhi baaki hai" type line to keep viewers watching.
5. Twist / payoff (2 lines): the most surprising part.
6. End with one question for viewers to answer in comments.
Every factual claim must be true and well-known. If unsure, pick a safer angle.
No health, finance, or legal advice. No politics. No conspiracy presented as fact. No mention of AI, no stage directions. Only the spoken words.

HINGLISH:
Write the SAME script, word for word in meaning, in Roman Hindi (Hinglish, Hindi written in English letters, natural like "Dimaag ke baare mein yeh sach koi nahi batata"). Same length. This is shown as captions on screen.

TITLE:
One Hinglish (Roman Hindi) YouTube Shorts title, under 60 characters, mysterious and dramatic, no clickbait lies. Only the title, nothing else.

SOURCE:
List 2 sources for the main fact, one per line starting with "SOURCE:".
"""


def log(msg):
    print(f"[shadow] {msg}", flush=True)


# ---------------------------------------------------------------- topics
def load_topics():
    with open(TOPICS_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows


def save_topics(rows):
    with open(TOPICS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def pick_today(rows):
    pending = [r for r in rows if r.get("status", "").strip() == "pending"]
    return pending[:VIDEOS_PER_DAY]


# ---------------------------------------------------------------- scripts
def _gemini_call(prompt, key):
    """Try each Gemini model in turn. Returns script text or raises."""
    last_err = None
    # Keys starting with "AQ." are OAuth-style tokens: send as Bearer header.
    # Standard AI Studio keys (AIza...) go in the ?key= query param.
    use_bearer = key.startswith("AQ.")
    for model in GEMINI_MODELS:
        for api_version in ("v1beta", "v1"):
            url = (
                f"https://generativelanguage.googleapis.com/{api_version}/models/"
                f"{model}:generateContent"
            )
            headers, params = {}, {}
            if use_bearer:
                headers["Authorization"] = f"Bearer {key}"
            else:
                params["key"] = key
            try:
                resp = requests.post(
                    url,
                    headers=headers,
                    params=params,
                    json={"contents": [{"parts": [{"text": prompt}]}]},
                    timeout=90,
                )
                resp.raise_for_status()
                data = resp.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]
            except Exception as e:
                last_err = e
                log(f"Gemini {model} ({api_version}) failed: {e}")
                continue
    raise RuntimeError(f"All Gemini models failed. Last error: {last_err}")


def parse_script_response(text):
    """Split a Gemini reply into (devanagari, hinglish, title, sources).
    Missing sections fall back gracefully."""
    sections = {"devanagari": "", "hinglish": "", "title": ""}
    sources = []
    current = None
    for raw in text.strip().splitlines():
        ln = raw.strip()
        if not ln:
            continue
        upper = ln.upper().rstrip(":")
        if upper in ("DEVANAGARI", "HINGLISH", "TITLE"):
            current = upper.lower()
            # Allow "TITLE: ..." on the same line.
            rest = ln.split(":", 1)[1].strip() if ":" in ln else ""
            if rest:
                sections[current] += rest + " "
            continue
        if ln.upper().startswith("SOURCE:"):
            sources.append(ln[7:].strip())
            current = None
            continue
        if current:
            sections[current] += ln + " "
    dev = re.sub(r"\s+", " ", sections["devanagari"]).strip()
    hin = re.sub(r"\s+", " ", sections["hinglish"]).strip()
    title = re.sub(r"\s+", " ", sections["title"]).strip()
    return dev, hin, title, sources


def gemini_script(topic_row):
    """Write a Hindi script with Gemini. Returns (devanagari, hinglish, title, sources)."""
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set")
    prompt = SCRIPT_PROMPT.format(
        topic=topic_row["topic"], format=topic_row["format"], niche=topic_row["niche"]
    )
    text = _gemini_call(prompt, key)
    dev, hin, title, sources = parse_script_response(text)
    if not dev:
        # Gemini ignored the section format: treat the whole reply as the script.
        dev, sources = split_sources(text)
        hin = ""
    if not hin:
        hin = devanagari_to_hinglish(dev)
    if not title:
        title = make_title(topic_row)
    return dev, hin, title, sources


def split_sources(text):
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    spoken, sources = [], []
    for ln in lines:
        if ln.upper().startswith("SOURCE:"):
            sources.append(ln[7:].strip())
        else:
            spoken.append(ln)
    script = " ".join(spoken)
    script = re.sub(r"\s+", " ", script).strip()
    return script, sources


def devanagari_to_hinglish(dev_text):
    """Transliterate Devanagari to Roman Hinglish (fallback when Gemini gives
    no HINGLISH section). ITRANS output is cleaned to read like natural Hinglish."""
    try:
        from indic_transliteration import sanscript

        roman = sanscript.transliterate(dev_text, sanscript.DEVANAGARI, sanscript.ITRANS)
        roman = roman.replace("|", ". ")  # danda (।) renders as a pipe in ITRANS
    except Exception:
        return dev_text
    # ITRANS uses capitals for long vowels: A->aa, I->ee, U->oo, RRi->ri etc.
    fixes = [
        ("RRi", "ri"), ("RRI", "ri"), ("LLi", "li"),
        ("AU", "au"), ("AI", "ai"),
        ("A", "aa"), ("I", "ee"), ("U", "oo"),
        ("M", "n"), ("H", "h"), ("~N", "n"),
        ("chh", "chh"), ("Sh", "sh"), ("shh", "sh"),
    ]
    for old, new in fixes:
        roman = roman.replace(old, new)
    # Natural Hinglish polish: drop the word-final inherent 'a'
    # ("dimaaga" -> "dimaag", "sacha" -> "sach") and fix common words.
    words = []
    common = {"men": "mein", "koee": "koi", "yaha": "yeh", "aapako": "aapko",
              "hee": "hi", "bhee": "bhi", "vahaa": "waha", "yahaa": "yaha"}
    for w in roman.lower().split():
        w = common.get(w, w)
        if len(w) > 2 and w.endswith("a"):
            w = w[:-1]
        words.append(w)
    roman = " ".join(words)
    # Capitalise the first letter of each sentence.
    roman = re.sub(r"(^|[.!?] )([a-z])", lambda m: m.group(1) + m.group(2).upper(), roman)
    roman = re.sub(r"\s+", " ", roman).strip()
    return roman


def fallback_script(topic_row):
    """Longer Devanagari template used only if Gemini fails, so the video
    still renders at ~55 seconds. Returns (devanagari, hinglish, title, sources).
    PURE Hindi — no English words: the Hindi voice mispronounces Latin text,
    so the topic name is never inserted here."""
    dev = (
        "क्या आपको पता है, इस कहानी के पीछे एक ऐसा सच छिपा है जिसे कोई नहीं बताता। "
        "ज्यादातर लोग सिर्फ ऊपरी कहानी जानते हैं, लेकिन असली कहानी उससे कहीं ज्यादा गहरी है। "
        "पहली बात, वैज्ञानिकों और इतिहासकारों ने इस पर सालों तक शोध किया है, और उन्हें ऐसे सबूत मिले "
        "जो हमारी सोच को पूरी तरह बदल देते हैं। "
        "दूसरी बात, इसके पीछे की वजह इतनी हैरान करने वाली है कि सुनकर आप भी चौंक जाएंगे, "
        "क्योंकि यह हमारी रोज़मर्रा की ज़िंदगी से सीधे जुड़ी हुई है। "
        "लेकिन सबसे बड़ा राज़ अभी बाकी है। "
        "तीसरी और सबसे चौंकाने वाली बात यह है कि इसका असर आज भी हमारे आसपास देखा जा सकता है, "
        "और आने वाले समय में यह और भी बड़ा हो सकता है। "
        "इसीलिए यह कहानी इतनी खास है, और इसीलिए लोग इसके बारे में जानना चाहते हैं। "
        "आपको इस कहानी का कौन सा हिस्सा सबसे ज्यादा हैरान करता है? कमेंट में बताइए।"
    )
    hin = devanagari_to_hinglish(dev)
    return dev, hin, make_title(topic_row), []


def split_sentences(text):
    """Split a script into sentences, keeping the terminator (। . ? !)."""
    parts = re.split(r"(?<=[।.?!])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def make_title(topic_row, title=""):
    """Hinglish title, cut at a word boundary under 60 chars."""
    if title:
        title = title.strip().strip('"').strip()
        if len(title) <= 60:
            return title
        cut = title[:60].rsplit(" ", 1)[0]
        return cut
    templates = [
        "Yeh Sach Aapko Hairan Kar Dega!",
        "Kya Aapko Yeh Pata Tha?",
        "Is Raaz Ko Koi Nahi Batata!",
        "Yeh Kahani Sun Kar Dang Reh Jaoge!",
        "Chhupa Hua Sach, Aakhir Khul Gaya!",
    ]
    return random.choice(templates)


# ---------------------------------------------------------------- voice
def _load_piper_voice():
    """Load the Piper Hindi voice, downloading the model once if needed."""
    from piper import PiperVoice

    model_dir = WORK / "models"
    model_dir.mkdir(exist_ok=True)
    model_path = model_dir / f"{PIPER_VOICE}.onnx"
    config_path = model_dir / f"{PIPER_VOICE}.onnx.json"
    if not model_path.exists():
        log("Downloading Piper Hindi voice model (one-time, ~60MB)...")
        download(PIPER_MODEL_URL, model_path)
        download(PIPER_CONFIG_URL, config_path)
    return PiperVoice.load(str(model_path))


def _voice_piper_sentences(script, out_wav):
    """Synthesize the script ONE SENTENCE AT A TIME with Piper, then join
    the pieces with a short pause between them. Returns (wav_path, windows)
    where windows is a list of (start, end) seconds per sentence — this is
    what keeps the captions in sync with the voice instead of guessing
    with even spacing. Also normalises loudness to stop clipping."""
    import wave

    voice = _load_piper_voice()
    sentences = split_sentences(script)
    if not sentences:
        sentences = [script]
    sr = voice.config.sample_rate
    gap_frames = int(sr * 0.25)  # 0.25s pause between sentences
    silence = b"\x00\x00" * gap_frames

    frames, windows = [], []
    t = 0.0
    for i, sent in enumerate(sentences):
        tmp = out_wav.parent / f"{out_wav.stem}_s{i}.wav"
        with wave.open(str(tmp), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            voice.synthesize(sent, wf, length_scale=PIPER_LENGTH_SCALE)
        with wave.open(str(tmp), "rb") as wf:
            data = wf.readframes(wf.getnframes())
            dur = wf.getnframes() / sr
        frames.append(data)
        windows.append((round(t, 3), round(t + dur, 3)))
        t += dur
        if i < len(sentences) - 1:
            frames.append(silence)
            t += 0.25
        tmp.unlink()
    with wave.open(str(out_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        for fr in frames:
            wf.writeframes(fr)
    return _normalize_audio(out_wav), windows


def _normalize_audio(in_wav):
    """Loudness-normalise the voice to -16 LUFS, true peak -1.5 dB, so the
    audio never clips (run #3 peaked above 0 dB, which sounded jittery)."""
    out_wav = in_wav.parent / (in_wav.stem + "_norm.wav")
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(in_wav),
         "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", str(out_wav)],
        check=True,
    )
    return out_wav


async def _voice_edge(script, out_mp3):
    if edge_tts is None:
        raise RuntimeError("edge-tts not installed")
    communicate = edge_tts.Communicate(script, EDGE_VOICE, rate=EDGE_RATE)
    await communicate.save(str(out_mp3))
    return out_mp3


def _voice_gtts(script, out_mp3):
    from gtts import gTTS

    gTTS(text=script, lang="hi").save(str(out_mp3))
    return out_mp3


def make_voice(script, slug_base):
    """Create the Hindi voiceover. Tries Piper (offline, per-sentence) ->
    edge-tts -> gTTS. Returns (audio_path, windows) where windows is a
    list of (start, end) seconds per sentence, or None for the whole-script
    fallbacks (captions then use even spacing as before)."""
    wav_path = Path(str(slug_base) + "_voice.wav")
    mp3_path = Path(str(slug_base) + "_voice.mp3")
    try:
        log("Voice: trying Piper Hindi (offline neural, per-sentence)...")
        return _voice_piper_sentences(script, wav_path)
    except Exception as e:
        log(f"Piper failed ({e}); trying edge-tts...")
    try:
        return asyncio.run(_voice_edge(script, mp3_path)), None
    except Exception as e:
        log(f"edge-tts failed ({e}); trying gTTS Hindi...")
    return _voice_gtts(script, mp3_path), None


def audio_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


# ---------------------------------------------------------------- visuals
def pexels_clips(keywords, count=5):
    """Fetch free stock video URLs from Pexels. Returns list of mp4 URLs."""
    key = os.environ.get("PEXELS_API_KEY", "")
    if not key:
        return []
    try:
        resp = requests.get(
            "https://api.pexels.com/videos/search",
            headers={"Authorization": key},
            params={"query": keywords, "per_page": count, "orientation": "portrait", "size": "medium"},
            timeout=30,
        )
        resp.raise_for_status()
        urls = []
        for v in resp.json().get("videos", []):
            files = [f for f in v.get("video_files", []) if f.get("file_type") == "video/mp4"]
            if files:
                files.sort(key=lambda f: f.get("width", 0))
                urls.append(files[0]["link"])
        return urls[:count]
    except Exception as e:
        log(f"Pexels failed ({e}); using solid background fallback")
        return []


def download(url, dest):
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    dest.write_bytes(r.content)


def pixabay_clips(keywords, count=5):
    """Fetch free stock video URLs from Pixabay. Returns list of mp4 URLs.
    Pixabay is the primary source when no Pexels key exists (Pexels paused
    new key issuance in Nov 2026)."""
    key = os.environ.get("PIXABAY_API_KEY", "")
    if not key:
        return []
    try:
        resp = requests.get(
            "https://pixabay.com/api/videos/",
            params={"key": key, "q": keywords, "orientation": "vertical",
                    "per_page": count, "safesearch": "true"},
            timeout=30,
        )
        resp.raise_for_status()
        urls = []
        for hit in resp.json().get("hits", []):
            videos = hit.get("videos", {})
            # Prefer medium (vertical-friendly), fall back to small/large.
            for size in ("medium", "small", "large", "tiny"):
                if size in videos and videos[size].get("url"):
                    urls.append(videos[size]["url"])
                    break
        return urls[:count]
    except Exception as e:
        log(f"Pixabay failed ({e}); using solid background fallback")
        return []


# ---------------------------------------------------------------- captions
def make_ass(caption_text, duration, ass_path, windows=None):
    """Split Hinglish captions into timed chunks, styled for Shorts.
    White bold text, black outline, just above middle of screen
    (clear of YouTube's bottom UI overlays).

    When `windows` (per-sentence start/end times from the voice) is given
    and matches the caption sentences, each sentence's words are timed
    inside its own spoken window — captions stay in sync with the voice.
    Otherwise falls back to even spacing across the whole duration."""
    sentences = split_sentences(caption_text)
    timed = bool(windows) and len(windows) == len(sentences)
    if not timed:
        sentences = [caption_text]
        windows = [(0.0, duration)]

    chunks = []  # (start, end, text)
    for sent, (s_start, s_end) in zip(sentences, windows):
        words = sent.split()
        if not words:
            continue
        sent_chunks = [" ".join(words[i:i + 3]) for i in range(0, len(words), 3)]
        span = max(s_end - s_start, 0.1)
        per = span / len(sent_chunks)
        for i, chunk in enumerate(sent_chunks):
            chunks.append((s_start + i * per, min(s_start + (i + 1) * per, duration), chunk))
    if not chunks:
        chunks = [(0.0, duration, "Shadow Archives")]
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,64,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,0,2,60,60,900,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    def fmt(t):
        h = int(t // 3600); m = int((t % 3600) // 60); s = int(t % 60); cs = int((t % 1) * 100)
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"
    events = []
    for start, end, chunk in chunks:
        text = chunk.replace("\\", "").replace("{", "").replace("}", "")
        events.append(f"Dialogue: 0,{fmt(start)},{fmt(end)},Default,,0,0,0,,{text}")
    ass_path.write_text(header + "\n".join(events), encoding="utf-8")


# ---------------------------------------------------------------- assembly
def build_video(clips, voice_path, ass_path, out_mp4, duration):
    """Assemble a 1080x1920 (9:16) 30fps Short with FFmpeg, capped at 58s.
    Stock clips are cropped/scaled to vertical. Falls back to a dark solid
    background if no clips downloaded."""
    dur = min(math.ceil(duration), TARGET_SECONDS)
    if clips:
        # Spread clips evenly across the video, each shown ~8-12s.
        seg = max(5, dur // len(clips))
        inputs, filters = [], []
        for i, c in enumerate(clips):
            inputs += ["-i", str(c)]
            filters.append(
                f"[{i}:v]scale=1080:1920:force_original_aspect_ratio=increase,"
                f"crop=1080:1920,setsar=1,fps=30,trim=0:{seg},setpts=PTS-STARTPTS[v{i}]"
            )
        concat = "".join(f"[v{i}]" for i in range(len(clips)))
        filters.append(
            f"{concat}concat=n={len(clips)}:v=1:a=0,fps=30,trim=0:{dur},"
            f"setpts=PTS-STARTPTS,subtitles={ass_path}[vout]"
        )
        filtergraph = ";".join(filters)
        cmd = ["ffmpeg", "-y"] + inputs + [
            "-i", str(voice_path),
            "-filter_complex", filtergraph,
            "-map", "[vout]", "-map", f"{len(clips)}:a",
            "-t", str(dur), "-c:v", "libx264", "-preset", "veryfast",
            "-c:a", "aac", "-shortest", str(out_mp4),
        ]
    else:
        cmd = ["ffmpeg", "-y",
               "-f", "lavfi", "-i", f"color=c=0x0A0E1A:s=1080x1920:d={dur},fps=30",
               "-i", str(voice_path),
               "-vf", f"subtitles={ass_path}",
               "-t", str(dur), "-c:v", "libx264", "-preset", "veryfast",
               "-c:a", "aac", "-shortest", str(out_mp4)]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


# ---------------------------------------------------------------- main
def main():
    OUTPUT.mkdir(exist_ok=True)
    WORK.mkdir(exist_ok=True)
    rows = load_topics()
    today = pick_today(rows)
    if not today:
        log("No pending topics left in topics.csv — add more topics!")
        sys.exit(0)
    log(f"Today's topics: {len(today)}")

    manifest = []
    for idx, row in enumerate(today, 1):
        slug = f"day{row['day']}_slot{row['slot']}"
        log(f"--- [{idx}/{len(today)}] {row['topic']}")
        try:
            try:
                dev, hin, title, sources = gemini_script(row)
                log(f"Script from Gemini ({len(dev.split())} Hindi words)")
            except Exception as e:
                log(f"Gemini failed ({e}); using fallback script")
                dev, hin, title, sources = fallback_script(row)

            voice_path, windows = make_voice(dev, WORK / slug)
            duration = audio_duration(voice_path)
            log(f"Voice: {duration:.1f}s, {len(windows) if windows else 0} sentence windows")

            # Visuals: Pexels first, Pixabay as primary fallback.
            clip_urls = pexels_clips(row["keywords"], count=5)
            if not clip_urls:
                clip_urls = pixabay_clips(row["keywords"], count=5)
            clips = []
            for j, url in enumerate(clip_urls):
                try:
                    p = WORK / f"{slug}_clip{j}.mp4"
                    download(url, p)
                    clips.append(p)
                except Exception as e:
                    log(f"Clip download failed: {e}")
            log(f"Clips: {len(clips)} downloaded")

            ass_path = WORK / f"{slug}.ass"
            make_ass(hin, min(duration, TARGET_SECONDS), ass_path, windows=windows)

            out_mp4 = OUTPUT / f"{slug}.mp4"
            build_video(clips, voice_path, ass_path, out_mp4, duration)
            log(f"Rendered: {out_mp4.name}")

            tag = re.sub(r"[^A-Za-z0-9]", "", row["topic"].split()[0].capitalize())
            desc = (
                f"{title}\n\n{hin[:180]}...\n\n"
                f"Roz ek naya raaz — Shadow Archives ko follow karo.\n"
                f"#Shorts #Facts #History #WhatIf #{tag} #HindiShorts"
            )
            manifest.append({"file": out_mp4.name, "title": title, "description": desc,
                             "topic": row["topic"], "sources": sources})
            row["status"] = "done"
        except Exception as e:
            log(f"FAILED {slug}: {e} — will retry next run, other videos continue")
            # status stays "pending" so the topic is retried on the next run

    # Titles + descriptions file for easy copy-paste at upload
    lines = []
    for m in manifest:
        lines.append(f"FILE: {m['file']}")
        lines.append(f"TOPIC: {m['topic']}")
        lines.append(f"TITLE: {m['title']}")
        lines.append(f"DESCRIPTION:\n{m['description']}")
        if m["sources"]:
            lines.append("SOURCES: " + " | ".join(m["sources"]))
        lines.append("-" * 40)
    (OUTPUT / "titles.txt").write_text("\n".join(lines), encoding="utf-8")
    save_topics(rows)
    log(f"Done. {len(manifest)} videos in output/")
    if not manifest:
        log("ERROR: 0 videos rendered — failing the run so it shows red, not green")
        sys.exit(1)


if __name__ == "__main__":
    main()
