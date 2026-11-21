# Shadow Archives — AI Prompts (v1.3 — Hinglish, 60 seconds)

## Language
- Voice speaks Hindi (Devanagari script → Piper Hindi voice).
- Captions, titles, descriptions: Hinglish — Hindi written in English letters.
- Topics in topics.csv stay in English; Gemini writes the Hindi script from them.

## Script prompt (Gemini, per video)
(See SCRIPT_PROMPT in scripts/generate.py — it asks for 4 sections: DEVANAGARI, HINGLISH, TITLE, SOURCE.)

- Length: 160-175 Hindi words = ~55-60 seconds spoken.
- Deep, not shallow: 3 specific revelations with names/dates/numbers, plus a mid-video retention hook.
- Structure: Hook → Setup → 3 deep points → Mid-hook → Twist → End question.

## Title rules
- Hinglish, under 60 characters, cut at a word boundary (never mid-word).
- Example: "Yeh Sach Aapko Hairan Kar Dega!"

## Description template (no AI needed)

```
{hinglish_title}

{hinglish_hook_line}

Roz ek naya raaz — Shadow Archives ko follow karo.
#Shorts #Facts #History #WhatIf #{topic_tag} #HindiShorts
```

## Image prompt (for AI images, v2)

```
Cinematic, dark, moody, dramatic lighting, photorealistic, 9:16 vertical, no text, no watermark: {scene_description}
```

## Voice settings (fixed — never change mid-channel)

Primary: Piper offline Hindi voice `hi_IN-pratham-medium` (male), length scale 1.1.
Why Piper: edge-tts returns 403 from GitHub's servers (Microsoft blocks datacentre IPs), so Piper — which runs locally on the runner — is the reliable voice.
Fallbacks, in order: edge-tts `hi-IN-MadhurNeural` rate -5%, then gTTS Hindi.
Backup Piper voices (only if pratham fails): `hi_IN-priyamvada-medium`, `hi_IN-rohan-medium`.

## Captions
- Hinglish (Roman Hindi), bold white, black outline.
- Position: just above middle of screen (ASS Alignment 2, MarginV 900) — clear of YouTube's bottom UI overlays and clear of the centre subject.

## Video spec (YouTube Shorts ready)
- 1080x1920 vertical (9:16), 30fps, H.264 + AAC, max 58 seconds.
- Never exceed 60 seconds. Never change the ratio.
