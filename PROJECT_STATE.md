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
- `src/local_app.py`: local-only analysis service for manual imports and review generation.
- `src/transcribe_audio.py`: optional local rough transcription with absolute timestamps.
- `app/import.html`: local analysis workbench.
- `app/index.html`: review cards and timeline.
- `data/sample/apple_2026-06-01.jsonl` and `data/sample/diy_2026-06-01.jsonl`: synthetic sample data.

## Local Run

```powershell
.\start-local-app.ps1
```

Open:

```text
http://127.0.0.1:4180/import.html
```

Optional local rough transcription:

```powershell
.\install-local-transcription.ps1
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

Use the workbench daily:

- Import the latest Apple Health export for the target date.
- Import timestamped recordings and add a short reliable scene summary.
- Add manual context for unexplained heart-rate/activity windows.
- Review cards and track whether audio improves the usefulness of the daily review.
