import argparse
import json
import mimetypes
import re
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from convert_apple_health import convert
from generate_cards import build_timeline, heuristic_cards, load_events


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
PRIVATE_DIR = ROOT / "data" / "private"
CARDS_PATH = APP_DIR / "data" / "cards.json"


def json_response(handler, payload, status=200):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def read_json(handler):
    length = int(handler.headers.get("Content-Length", "0"))
    if length > 2_000_000:
        raise ValueError("请求内容过大")
    return json.loads(handler.rfile.read(length).decode("utf-8"))


def resolve_user_path(value):
    path = Path(value).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"找不到文件：{path}")
    return path


def generate_for_date(target_date):
    events = load_events(ROOT / "data", target_date)
    if not events:
        raise ValueError(f"{target_date} 没有可分析的数据")
    cards = heuristic_cards(events, target_date)
    summary = {
        "eventCount": len(events),
        "sources": count_by(events, "source"),
        "modalities": count_by(events, "modality"),
    }
    result = {
        "date": target_date,
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "mode": "local_heuristic",
        "summary": summary,
        "cards": cards,
        "timeline": build_timeline(events),
    }
    CARDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CARDS_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def count_by(events, field):
    counts = {}
    for event in events:
        value = event.get(field, "unknown")
        counts[value] = counts.get(value, 0) + 1
    return counts


def probe_audio(path):
    command = [
        "ffprobe", "-v", "error",
        "-show_entries",
        "format=duration,size,bit_rate,format_name:format_tags:stream=codec_name,sample_rate,channels,bit_rate",
        "-of", "json", str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def write_audio_session(path, start_iso, summary):
    metadata = probe_audio(path)
    stream = (metadata.get("streams") or [{}])[0]
    fmt = metadata.get("format") or {}
    start = datetime.fromisoformat(start_iso)
    duration = float(fmt.get("duration", 0))
    end = start + timedelta(seconds=duration)
    size = int(fmt.get("size", path.stat().st_size))
    bit_rate = int(fmt.get("bit_rate", stream.get("bit_rate", 0)) or 0)
    row = {
        "timestamp": start.isoformat(),
        "end_timestamp": end.isoformat(),
        "source": "audio_analysis",
        "modality": "audio_session",
        "raw": {
            "file": path.name,
            "duration_sec": round(duration, 2),
            "size_bytes": size,
            "codec": stream.get("codec_name"),
            "sample_rate_hz": int(stream.get("sample_rate", 0) or 0),
            "channels": stream.get("channels"),
            "bit_rate_bps": bit_rate,
            "size_mb_per_hour": round(size / 1024 / 1024 / max(duration / 3600, 0.001), 2),
        },
        "summary": summary or "手动导入的录音，尚未补充场景摘要。",
        "confidence": 0.7 if summary else 0.5,
        "location": "",
        "context": {"route": "iphone_audio", "activity": "imported_audio"},
    }
    PRIVATE_DIR.mkdir(parents=True, exist_ok=True)
    output = PRIVATE_DIR / f"audio_session_{start.strftime('%Y-%m-%d_%H%M')}.jsonl"
    output.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    return row, output


def infer_audio_start(path):
    match = re.search(
        r"(?P<date>\d{4}-\d{2}-\d{2})[ _](?P<hour>\d{2})[-_:](?P<minute>\d{2})",
        path.stem,
    )
    if not match:
        return None
    return f"{match.group('date')}T{match.group('hour')}:{match.group('minute')}:00+08:00"


def transcribe_audio(path, start_iso):
    deps = ROOT / ".local-deps"
    if not deps.exists():
        raise RuntimeError("尚未安装本地转写组件，请先运行 install-local-transcription.ps1")
    output = PRIVATE_DIR / f"audio_{datetime.fromisoformat(start_iso).strftime('%Y-%m-%d_%H%M')}.raw-transcript.json"
    command = [
        sys.executable, str(ROOT / "src" / "transcribe_audio.py"),
        "--audio", str(path),
        "--output", str(output),
        "--start", start_iso,
        "--model", "small",
        "--deps", str(deps),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    last_line = result.stdout.strip().splitlines()[-1]
    return json.loads(last_line), output


def append_context(payload):
    timestamp = datetime.fromisoformat(payload["timestamp"])
    text = payload["text"].strip()
    if not text:
        raise ValueError("场景说明不能为空")
    event = {
        "timestamp": timestamp.isoformat(),
        "source": "manual_context",
        "modality": "context_note",
        "raw": {"text": text},
        "summary": text,
        "confidence": 1.0,
        "location": payload.get("location", ""),
        "context": {
            "route": "manual",
            "activity": payload.get("activity", "manual_note"),
        },
    }
    PRIVATE_DIR.mkdir(parents=True, exist_ok=True)
    output = PRIVATE_DIR / f"manual_context_{timestamp.date().isoformat()}.jsonl"
    with output.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event, output


class LocalHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        parsed = urlparse(path).path
        relative = unquote(parsed).lstrip("/") or "index.html"
        return str((APP_DIR / relative).resolve())

    def log_message(self, format, *args):
        print(f"[local-app] {self.address_string()} {format % args}")

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/status":
            return json_response(self, {
                "ok": True,
                "root": str(ROOT),
                "privateDir": str(PRIVATE_DIR),
                "cardsExists": CARDS_PATH.exists(),
                "privacy": "所有导入数据仅保存在本机 data/private，默认不会提交到 GitHub。",
            })
        return super().do_GET()

    def do_POST(self):
        try:
            payload = read_json(self)
            path = urlparse(self.path).path
            if path == "/api/import-health":
                target_date = payload["date"]
                source = resolve_user_path(payload["path"])
                PRIVATE_DIR.mkdir(parents=True, exist_ok=True)
                output = PRIVATE_DIR / f"apple_{target_date}.jsonl"
                count = convert(source, output, date=target_date)
                result = generate_for_date(target_date)
                return json_response(self, {
                    "ok": True, "message": f"已导入 {count} 条 Apple 健康数据",
                    "output": str(output), "result": result,
                })
            if path == "/api/import-audio":
                source = resolve_user_path(payload["path"])
                start_iso = payload.get("start") or infer_audio_start(source)
                if not start_iso:
                    raise ValueError("无法从文件名识别开始时间，请手动填写")
                row, output = write_audio_session(
                    source, start_iso, payload.get("summary", "").strip()
                )
                transcript = None
                transcript_output = None
                if payload.get("transcribe"):
                    transcript, transcript_output = transcribe_audio(source, payload["start"])
                result = generate_for_date(row["timestamp"][:10])
                return json_response(self, {
                    "ok": True, "message": "录音元数据已导入",
                    "output": str(output), "audio": row,
                    "transcript": transcript,
                    "transcriptOutput": str(transcript_output) if transcript_output else None,
                    "result": result,
                })
            if path == "/api/import-audios":
                items = payload.get("items") or []
                if not items:
                    raise ValueError("请至少添加一段录音")
                imported = []
                dates = set()
                for item in items:
                    source = resolve_user_path(item["path"])
                    start_iso = item.get("start") or infer_audio_start(source)
                    if not start_iso:
                        raise ValueError(f"无法从文件名识别开始时间：{source.name}")
                    row, output = write_audio_session(
                        source, start_iso, item.get("summary", "").strip()
                    )
                    imported.append({
                        "file": source.name,
                        "start": row["timestamp"],
                        "end": row["end_timestamp"],
                        "output": str(output),
                        "sizeMbPerHour": row["raw"]["size_mb_per_hour"],
                    })
                    dates.add(row["timestamp"][:10])
                results = {date: generate_for_date(date) for date in sorted(dates)}
                latest = results[sorted(results)[-1]]
                return json_response(self, {
                    "ok": True,
                    "message": f"已导入 {len(imported)} 段录音",
                    "imported": imported,
                    "results": results,
                    "result": latest,
                })
            if path == "/api/add-context":
                event, output = append_context(payload)
                result = generate_for_date(event["timestamp"][:10])
                return json_response(self, {
                    "ok": True, "message": "场景说明已加入时间线",
                    "output": str(output), "result": result,
                })
            if path == "/api/generate":
                result = generate_for_date(payload["date"])
                return json_response(self, {"ok": True, "message": "复盘已生成", "result": result})
            return json_response(self, {"ok": False, "error": "未知接口"}, 404)
        except Exception as exc:
            return json_response(self, {"ok": False, "error": str(exc)}, 400)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=4180)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    PRIVATE_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), LocalHandler)
    url = f"http://127.0.0.1:{args.port}/import.html"
    print(f"AI Watch 本地分析工作台：{url}")
    print("数据只在本机处理。按 Ctrl+C 停止。")
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
