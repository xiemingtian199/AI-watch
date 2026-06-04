import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--start", required=True, help="ISO start time, including timezone")
    parser.add_argument("--model", default="small")
    parser.add_argument("--deps", help="Optional folder containing faster-whisper")
    args = parser.parse_args()

    if args.deps:
        sys.path.insert(0, args.deps)

    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise SystemExit(
            "faster-whisper is required. Install it with: "
            "python -m pip install faster-whisper"
        ) from exc

    start = datetime.fromisoformat(args.start)
    model = WhisperModel(args.model, device="cpu", compute_type="int8")
    segments, info = model.transcribe(
        args.audio,
        language="zh",
        beam_size=1,
        best_of=1,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 800},
        condition_on_previous_text=False,
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output.open("w", encoding="utf-8") as handle:
        for segment in segments:
            text = segment.text.strip()
            if not text:
                continue
            event_start = start + timedelta(seconds=segment.start)
            event_end = start + timedelta(seconds=segment.end)
            row = {
                "timestamp": event_start.isoformat(),
                "end_timestamp": event_end.isoformat(),
                "source": "iphone_audio",
                "modality": "audio_transcript",
                "raw": {
                    "text": text,
                    "relative_start_sec": round(segment.start, 2),
                    "relative_end_sec": round(segment.end, 2),
                },
                "summary": text,
                "confidence": 0.65,
                "location": "",
                "context": {"route": "iphone_audio", "activity": "unknown"},
            }
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1

    print(json.dumps({
        "segments": count,
        "language": info.language,
        "language_probability": info.language_probability,
        "output": str(output),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
