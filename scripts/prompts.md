# Shadow Archives — AI Prompts

## Script prompt (Gemini, per video)

```
Write a 45-second YouTube Shorts script, mysterious and dramatic tone, for teens aged 13-25.
Topic: {topic}
Format: {format}
Niche: {niche}

Rules:
- 120-150 words. Simple English. Short sentences.
- Start with a 3-second hook: a secret, a shocking number, or a question.
- Structure: Hook -> Setup (2 lines) -> Reveal (3-4 lines) -> Twist (1-2 lines) -> End with one question for viewers.
- Every factual claim must be true and well-known. If you are not sure, say so and pick a safer angle.
- No health, finance, or legal advice. No politics. No conspiracy presented as fact.
- No mention of AI, no "as an AI", no stage directions. Only the spoken words.
- At the very end, on separate lines starting with "SOURCE:", list 2 sources for the main fact (not spoken).
```

## Title prompt

```
Give 3 YouTube Shorts titles for this script, mysterious and dramatic, under 60 characters each, no clickbait lies. Return only the 3 titles, one per line.
Script: {script}
```

## Description template (no AI needed)

```
{hook_line}

{two_line_summary}

Follow Shadow Archives for a secret every day.
#Shorts #Facts #History #WhatIf #{topic_tag}
```

## Image prompt (for AI images, v2)

```
Cinematic, dark, moody, dramatic lighting, photorealistic, 9:16 vertical, no text, no watermark: {scene_description}
```

## Voice settings (fixed — never change mid-channel)

Primary: Piper offline neural voice `en_US-lessac-medium`, length scale 1.15 (slightly slow, dramatic).
Why Piper: edge-tts returns 403 from GitHub's servers (Microsoft blocks datacentre IPs), so Piper — which runs locally on the runner — is the reliable voice.
Fallbacks, in order: edge-tts `en-US-GuyNeural` rate -5%, then gTTS.
Backup Piper voices (only if lessac fails): `en_US-ryan-high`, `en_US-libritts_r-medium`.
