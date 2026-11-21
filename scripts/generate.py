#!/usr/bin/env python3
"""
Shadow Archives — Daily Shorts pipeline v1
Free tools only: Gemini (scripts) + edge-tts (voice) + Pexels (stock video) + FFmpeg.

Reads scripts/topics.csv, picks the next 4 pending topics,
renders 4 vertical Shorts into output/, and marks topics done.
Run by GitHub Actions daily. Also runnable locally for testing.

Env vars:
  GEMINI_API_KEY — Google AI Studio key (free)
  PEXELS_API_KEY — Pexels API key (free)
"""
import asyncio
import csv
import json
import math
import os
import random
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import requests

try:
    import edge_tts
except ImportError:
    edge_tts = None

ROOT = Path(__file__).resolve().parent.parent
TOPICS_CSV = ROOT / "scripts" / "topics.csv"
OUTPUT = ROOT / "output"
WORK = ROOT / "work"

VOICE = "en-US-GuyNeural"
VOICE_RATE = "-5%"
VIDEOS_PER_DAY = 4

SCRIPT_PROMPT = """Write a 45-second YouTube Shorts script, mysterious and dramatic tone, for teens aged 13-25.
Topic: {topic}
Format: {format}
Niche: {niche}

Rules:
- 120-150 words. Simple English. Short sentences.
- Start with a 3-second hook: a secret, a shocking number, or a question.
- Structure: Hook -> Setup (2 lines) -> Reveal (3-4 lines) -> Twist (1-2 lines) -> End with one question for viewers.
- Every factual claim must be true and well-known. If you are not sure, say so and pick a safer angle.
- No health, finance, or legal advice. No politics. No conspiracy presented as fact.
- No mention of AI, no stage directions. Only the spoken words.
- At the very end, on separate lines starting with "SOURCE:", list 2 sources for the main fact (not spoken).
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
def gemini_script(topic_row):
    """Write a script with Gemini free tier. Returns (script_text, sources)."""
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set")
    prompt = SCRIPT_PROMPT.format(
        topic=topic_row["topic"], format=topic_row["format"], niche=topic_row["niche"]
    )
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={key}"
    )
    resp = requests.post(
        url,
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    return split_sources(text)


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


def fallback_script(topic_row):
    """Template script used only if Gemini fails, so the video still renders."""
    t = topic_row["topic"]
    return (
        f"Nobody tells you this about {t.lower()}. "
        f"Most people believe the simple version, but the real story is stranger. "
        f"Scientists and historians have looked at this for years, and what they found "
        f"changes how you see it. The details are hidden in plain sight, once you know "
        f"where to look. And the strangest part? It still affects us today. "
        f"What do you think is the most surprising part of this story?"
    )


def make_title(topic_row, script):
    topic = topic_row["topic"]
    templates = [
        f"The Secret Behind {topic[:40]}",
        f"What Nobody Tells You About {topic[:35]}",
        f"This Changes Everything You Knew",
        f"The Hidden Truth of {topic[:40]}",
    ]
    title = random.choice(templates)
    return title[:60]


# ---------------------------------------------------------------- voice
async def make_voice(script, out_mp3):
    if edge_tts is None:
        raise RuntimeError("edge-tts not installed")
    communicate = edge_tts.Communicate(script, VOICE, rate=VOICE_RATE)
    await communicate.save(str(out_mp3))


def audio_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


# ---------------------------------------------------------------- visuals
def pexels_clips(keywords, count=3):
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


# ---------------------------------------------------------------- captions
def make_ass(script, duration, ass_path):
    """Split script into timed caption chunks, styled for Shorts.
    White bold text, black outline, centred lower-third."""
    words = script.split()
    if not words:
        words = ["Shadow", "Archives"]
    # ~3 words per caption chunk, timed evenly across the audio.
    chunks = [" ".join(words[i:i + 3]) for i in range(0, len(words), 3)]
    per = duration / max(len(chunks), 1)
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,64,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,0,2,60,60,420,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    def fmt(t):
        h = int(t // 3600); m = int((t % 3600) // 60); s = int(t % 60); cs = int((t % 1) * 100)
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"
    events = []
    for i, chunk in enumerate(chunks):
        start = i * per
        end = min((i + 1) * per, duration)
        text = chunk.replace("\\", "").replace("{", "").replace("}", "")
        events.append(f"Dialogue: 0,{fmt(start)},{fmt(end)},Default,,0,0,0,,{text}")
    ass_path.write_text(header + "\n".join(events), encoding="utf-8")


# ---------------------------------------------------------------- assembly
def build_video(clips, voice_mp3, ass_path, out_mp4, duration):
    """Assemble a 1080x1920 Short with FFmpeg.
    Stock clips are cropped/scaled to vertical with a slow zoom.
    Falls back to a dark solid background if no clips downloaded."""
    dur = math.ceil(duration)
    if clips:
        # Build one vertical video from the clips, each shown ~8s.
        seg = max(5, dur // len(clips))
        inputs, filters = [], []
        for i, c in enumerate(clips):
            inputs += ["-i", str(c)]
            filters.append(
                f"[{i}:v]scale=1080:1920:force_original_aspect_ratio=increase,"
                f"crop=1080:1920,setsar=1,trim=0:{seg},setpts=PTS-STARTPTS[v{i}]"
            )
        concat = "".join(f"[v{i}]" for i in range(len(clips)))
        filters.append(f"{concat}concat=n={len(clips)}:v=1:a=0,trim=0:{dur},setpts=PTS-STARTPTS[vout]")
        filtergraph = ";".join(filters)
        cmd = ["ffmpeg", "-y"] + inputs + [
            "-i", str(voice_mp3),
            "-filter_complex", filtergraph,
            "-map", "[vout]", "-map", f"{len(clips)}:a",
            "-vf", f"subtitles={ass_path}",
            "-t", str(dur), "-c:v", "libx264", "-preset", "veryfast",
            "-c:a", "aac", "-shortest", str(out_mp4),
        ]
        # Note: -vf after -filter_complex conflicts; use subtitles inside filtergraph instead.
        # Rebuild with subtitles as the last filter step.
        filters[-1] = (
            f"{concat}concat=n={len(clips)}:v=1:a=0,trim=0:{dur},setpts=PTS-STARTPTS,"
            f"subtitles={ass_path}[vout]"
        )
        filtergraph = ";".join(filters)
        cmd = ["ffmpeg", "-y"] + inputs + [
            "-i", str(voice_mp3),
            "-filter_complex", filtergraph,
            "-map", "[vout]", "-map", f"{len(clips)}:a",
            "-t", str(dur), "-c:v", "libx264", "-preset", "veryfast",
            "-c:a", "aac", "-shortest", str(out_mp4),
        ]
    else:
        cmd = ["ffmpeg", "-y",
               "-f", "lavfi", "-i", f"color=c=0x0A0E1A:s=1080x1920:d={dur}",
               "-i", str(voice_mp3),
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
                script, sources = gemini_script(row)
                log(f"Script from Gemini ({len(script.split())} words)")
            except Exception as e:
                log(f"Gemini failed ({e}); using fallback script")
                script, sources = fallback_script(row), []

            voice_path = WORK / f"{slug}_voice.mp3"
            asyncio.run(make_voice(script, voice_path))
            duration = audio_duration(voice_path)
            log(f"Voice: {duration:.1f}s")

            # Visuals
            clip_urls = pexels_clips(row["keywords"], count=3)
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
            make_ass(script, duration, ass_path)

            out_mp4 = OUTPUT / f"{slug}.mp4"
            build_video(clips, voice_path, ass_path, out_mp4, duration)
            log(f"Rendered: {out_mp4.name}")

            title = make_title(row, script)
            tag = re.sub(r"[^A-Za-z0-9]", "", row["topic"].split()[0].capitalize())
            desc = (
                f"{title}\n\n{script[:180]}...\n\n"
                f"Follow Shadow Archives for a secret every day.\n"
                f"#Shorts #Facts #History #WhatIf #{tag}"
            )
            manifest.append({"file": out_mp4.name, "title": title, "description": desc,
                             "topic": row["topic"], "sources": sources})
            row["status"] = "done"
        except Exception as e:
            log(f"FAILED {slug}: {e} — skipping, other videos continue")
            row["status"] = "failed"

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


if __name__ == "__main__":
    main()
