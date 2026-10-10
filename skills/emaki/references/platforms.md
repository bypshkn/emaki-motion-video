# Platforms and delivery specs

| platform | aspect | final size | typical length | notes |
|---|---|---|---|---|
| Instagram Reels | 9:16 | 1080x1920 | 10-60 s | feed preview crops to 4:5 around the centre |
| TikTok | 9:16 | 1080x1920 | 10-60 s | right column of buttons, caption at the bottom |
| YouTube Shorts | 9:16 | 1080x1920 | 15-60 s | subscribe/like column on the right |
| YouTube / web | 16:9 | 1920x1080 | 30-120 s | |
| LinkedIn feed | 1:1 or 4:5 | 1080x1080 / 1080x1350 | 15-60 s | mostly watched muted: copy must carry the message |
| Client presentation | 16:9 | 1920x1080 | 20-90 s | played in a meeting: slower pace, larger copy, -16..-14 LUFS |
| Web loop | any | as designed | 4-12 s | seamless loop, `--webm-loop`, often muted |

All finals: H.264 High, yuv420p, BT.709, +faststart, AAC 256 kb/s 48 kHz stereo, 30 fps
(60 on request), 1080 px on the short side.

## Safe zones (9:16, px at 1080x1920)

Source: Upload-Post safe-zone checker, based on each platform's ad specs (checked 2026-09-23).
Organic UI is usually smaller, so QA reports these as WARN; the 8% frame margin is the hard rule.

| platform | top | bottom | left | right |
|---|---|---|---|---|
| TikTok | 240 | 660 | 120 | 120 |
| Reels | 269 | 672 | 65 | 65 |
| Shorts | 288 | 672 | 48 | 192 |

Practical: keep the main message in the middle band (y 290-1250); put the CTA above y 1250.

## Loudness

-14 LUFS integrated, -1 dBTP true peak suits YouTube, Instagram, TikTok and most players.
For a video played in a meeting room or embedded with other material, -16 LUFS is also fine
(`sound.loudness: -16`).

## Muted viewing

Most feed video starts muted. The story must work without sound: on-screen copy carries the
message, sound adds energy.
