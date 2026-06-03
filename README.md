# AI Multimodal Watch MVP

This is a local validation kit for a personal AI multimodal watch concept. It implements the first MVP loop:

- Merge Apple Watch/iPhone-style and DIY sensor events into one timeline.
- Generate daily review cards from multimodal data.
- Show a compact card feed and timeline in a browser.
- Capture card feedback for the next review cycle.

## Run

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

The converter extracts heart rate, step count, walking/running distance, active energy, exercise time, flights climbed, and walking speed.

## MVP Boundaries

- This is not a medical or mental health product.
- Card copy intentionally avoids hard diagnosis.
- Raw media paths are represented as local references in sample data.
- Feedback is saved in browser local storage for the demo; production should write it to a user-controlled backend.
