import argparse
import json
import zipfile
from datetime import datetime
from pathlib import Path
from xml.etree.ElementTree import iterparse


TYPE_MAP = {
    "HKQuantityTypeIdentifierHeartRate": ("heart_rate", "bpm"),
    "HKQuantityTypeIdentifierStepCount": ("step_count", "count"),
    "HKQuantityTypeIdentifierDistanceWalkingRunning": ("walking_running_distance", "m"),
    "HKQuantityTypeIdentifierActiveEnergyBurned": ("active_energy", "kcal"),
    "HKQuantityTypeIdentifierAppleExerciseTime": ("exercise_time", "min"),
    "HKQuantityTypeIdentifierFlightsClimbed": ("flights_climbed", "count"),
    "HKQuantityTypeIdentifierWalkingSpeed": ("walking_speed", "m/s"),
}


def parse_apple_datetime(value):
    # Apple Health export timestamps are commonly like:
    # 2026-06-01 09:18:00 +0800
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S %z")


def open_export_xml(path):
    path = Path(path)
    if path.suffix.lower() == ".zip":
        archive = zipfile.ZipFile(path)
        for name in archive.namelist():
            if name.endswith("export.xml"):
                return archive.open(name)
        raise FileNotFoundError("export.xml not found inside zip")
    return path.open("rb")


def confidence_for(record_type):
    if record_type == "HKQuantityTypeIdentifierHeartRate":
        return 0.9
    if record_type == "HKQuantityTypeIdentifierStepCount":
        return 0.82
    return 0.75


def source_label(source_name):
    source = (source_name or "").lower()
    if "watch" in source:
        return "apple_watch"
    if "iphone" in source:
        return "iphone"
    return "apple_health"


def build_summary(modality, value, unit):
    if modality == "heart_rate":
        return f"Apple 健康记录心率 {value} {unit}"
    if modality == "step_count":
        return f"Apple 健康记录步数 {value}"
    if modality == "walking_running_distance":
        return f"Apple 健康记录步行/跑步距离 {value} {unit}"
    if modality == "active_energy":
        return f"Apple 健康记录活动能量 {value} {unit}"
    if modality == "exercise_time":
        return f"Apple 健康记录运动时间 {value} {unit}"
    return f"Apple 健康记录 {modality}: {value} {unit}".strip()


def convert(input_path, output_path, date=None, source_filter=None):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0

    source_filter_lower = source_filter.lower() if source_filter else None
    with open_export_xml(input_path) as xml_file, output_path.open("w", encoding="utf-8") as out:
        for _, elem in iterparse(xml_file, events=("end",)):
            if elem.tag != "Record":
                elem.clear()
                continue

            record_type = elem.attrib.get("type")
            if record_type not in TYPE_MAP:
                elem.clear()
                continue

            source_name = elem.attrib.get("sourceName", "")
            if source_filter_lower and source_filter_lower not in source_name.lower():
                elem.clear()
                continue

            try:
                end_time = parse_apple_datetime(elem.attrib["endDate"])
            except (KeyError, ValueError):
                elem.clear()
                continue

            if date and end_time.date().isoformat() != date:
                elem.clear()
                continue

            modality, default_unit = TYPE_MAP[record_type]
            unit = elem.attrib.get("unit") or default_unit
            value_text = elem.attrib.get("value")
            try:
                value = float(value_text)
                if value.is_integer():
                    value = int(value)
            except (TypeError, ValueError):
                elem.clear()
                continue

            raw_key = "bpm" if modality == "heart_rate" else "value"
            event = {
                "timestamp": end_time.isoformat(),
                "source": source_label(source_name),
                "modality": modality,
                "raw": {raw_key: value, "unit": unit, "sourceName": source_name},
                "summary": build_summary(modality, value, unit),
                "confidence": confidence_for(record_type),
                "location": "",
                "context": {"route": "apple", "activity": infer_activity(end_time, modality)},
            }
            out.write(json.dumps(event, ensure_ascii=False) + "\n")
            count += 1
            elem.clear()
    return count


def infer_activity(timestamp, modality):
    hour = timestamp.hour
    if hour < 7:
        return "sleep_or_rest"
    if 7 <= hour < 10:
        return "morning"
    if 10 <= hour < 12:
        return "work"
    if 12 <= hour < 14:
        return "lunch"
    if 14 <= hour < 19:
        return "work"
    if 19 <= hour < 22:
        return "evening"
    return "late_routine"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Apple Health export.zip or export.xml")
    parser.add_argument("--output", required=True, help="Output JSONL path")
    parser.add_argument("--date", help="Only export one date, for example 2026-06-03")
    parser.add_argument("--source-filter", help="Optional sourceName substring, for example Watch")
    args = parser.parse_args()

    count = convert(args.input, args.output, args.date, args.source_filter)
    print(f"Wrote {count} Apple Health events to {args.output}")


if __name__ == "__main__":
    main()
