# AI Watch MVP Project State

## Purpose

Personal AI multimodal watch MVP for efficiency users. The current focus is the Apple Watch + iPhone route:

- Convert Apple Health exports into normalized timeline events.
- Add lightweight manual context for important time windows.
- Generate daily review cards.
- View cards, evidence, timeline, filters, and feedback in a local browser demo.

## Current Implementation

- `src/convert_apple_health.py`: converts Apple Health `export.xml` or export zip into JSONL timeline events.
- `src/generate_cards.py`: generates daily review cards from JSONL events.
- `app/`: static browser demo.
- `data/sample/apple_2026-06-01.jsonl` and `data/sample/diy_2026-06-01.jsonl`: synthetic sample data.

## Local Run

```powershell
python src\generate_cards.py --input data\sample --date 2026-06-01 --output app\data\cards.json
python -m http.server 4173 -d app
```

Open:

```text
http://localhost:4173
```

## Privacy Policy For Git Sync

Do not commit personal exports or generated personal cards by default:

- `data/raw/`
- `data/private/`
- `data/sample/apple_20*.jsonl`
- `data/sample/manual_context_20*.jsonl`
- `app/data/cards.json`
- `HANDOFF.md`

If personal data needs to move between computers, use a private encrypted channel or explicitly approve committing it to a private GitHub repository.

## Latest Local Experiment Summary

On the original machine, Apple Health data for 2026-06-03 was converted and combined with manual context:

- 513 Apple Health events
- 7 manual context events
- 520 total events
- 8 review cards generated

Manual context captured:

- 07:43-08:03: leaving home, elevator, walking to subway, subway ride and transfer.
- 07:00-07:59: waking up, washing, breakfast, then commute start.
- 10:06-18:26: office routine work, 12:00-13:00 lunch break, no meetings.

This personal data is intentionally excluded from Git by default.

## Next Step

Test VoxRec for lightweight audio capture:

- Space Saver AAC.
- Voice Activation / Sound Threshold.
- No real-time transcription at first.
- 30-60 minute commute or office segment.
- Record file size, battery drain, export behavior, and whether start time is preserved.

Then add an audio manifest such as:

```csv
start,end,source,file,scene,notes
2026-06-04T07:30:00+08:00,2026-06-04T08:00:00+08:00,voxrec,2026-06-04_0730_commute.m4a,commute,voice activated recording
```

