# AI Multimodal Watch MVP

This is a local validation kit for a personal AI multimodal watch concept. It implements the first MVP loop:

- Merge Apple Watch/iPhone-style and DIY sensor events into one timeline.
- Generate daily review cards from multimodal data.
- Show a compact card feed and timeline in a browser.
- Capture card feedback for the next review cycle.

## Local Analysis Workbench

The recommended way to use the project is the local analysis workbench. It runs only on `127.0.0.1` and keeps imported personal data under the ignored `data/private` directory.

On Windows, double-click:

```text
start-local-app.bat
```

Or run:

```powershell
.\start-local-app.ps1
```

The workbench opens:

```text
http://127.0.0.1:4180/import.html
```

It supports:

- Importing an Apple Health XML/ZIP for a selected date.
- Importing timestamped audio metadata.
- Optional local rough transcription.
- Adding manual scene/context notes.
- Regenerating and viewing daily review cards.

Optional local transcription setup:

```powershell
.\install-local-transcription.ps1
```

Rough transcripts are stored separately and do not automatically influence review cards.

## Command-Line Run

```powershell
cd C:\Users\HK\Documents\Codex\2026-06-03\new-chat\outputs\ai-watch-mvp
python src\generate_cards.py --input data\sample --date 2026-06-01 --output app\data\cards.json
python -m http.server 4173 -d app
```

Open `http://localhost:4173`.

## Optional Cloud Mode

Set `OPENAI_API_KEY` before running the generator to use cloud analysis:

```powershell
$env:OPENAI_API_KEY="..."
python src\generate_cards.py --input data\sample --date 2026-06-01 --output app\data\cards.json --cloud
```

Without an API key, the generator uses a deterministic local heuristic so the demo works offline.

## Data Shape

Every event is normalized to:

```json
{
  "timestamp": "2026-06-01T09:18:00+08:00",
  "source": "apple_watch",
  "modality": "heart_rate",
  "raw": {"bpm": 118},
  "summary": "Heart rate rose during calendar handoff",
  "confidence": 0.9,
  "location": "Shanghai office",
  "context": {"route": "apple", "activity": "pre-meeting"}
}
```

## Convert Apple Health Export

On iPhone:

1. Open Health.
2. Tap your profile picture or initials.
3. Tap Export All Health Data.
4. Share the exported zip to this computer.
5. Put it under `data/raw/apple_export.zip`.

Then convert one day:

```powershell
python src\convert_apple_health.py --input data\raw\apple_export.zip --date 2026-06-03 --output data\sample\apple_2026-06-03.jsonl
python src\generate_cards.py --input data\sample --date 2026-06-03 --output app\data\cards.json
```

The converter extracts heart rate, resting heart rate, walking heart rate, HRV, blood oxygen, respiratory rate, sleep, steps, distance, energy, exercise, standing, environmental audio exposure, physical effort, daylight, stair activity, and walking metrics.

## Transcribe A Timestamped Audio File

Install the optional local transcription dependency:

```powershell
.\install-local-transcription.ps1
```

Then transcribe an audio file using its real start time:

```powershell
python src\transcribe_audio.py `
  --audio "2026-06-03 19-40.m4a" `
  --start "2026-06-03T19:40:00+08:00" `
  --output data\private\audio_2026-06-03_1940.raw-transcript.json `
  --deps .local-deps
```

Use `--input data` when generating cards to include both sample/manual events and private audio events:

```powershell
python src\generate_cards.py --input data --date 2026-06-03 --output app\data\cards.json
```

## MVP Boundaries

- This is not a medical or mental health product.
- Card copy intentionally avoids hard diagnosis.
- Raw media paths are represented as local references in sample data.
- Feedback is saved in browser local storage for the demo; production should write it to a user-controlled backend.
- The workbench accepts local file paths. It does not upload files to a remote service.
- Personal data under `data/private` and generated cards are ignored by Git.
