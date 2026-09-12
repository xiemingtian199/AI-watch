import argparse
import json
import zipfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from xml.etree.ElementTree import iterparse


TYPE_MAP = {
    "HKQuantityTypeIdentifierHeartRate": ("heart_rate", "bpm", True),
    "HKQuantityTypeIdentifierRestingHeartRate": ("resting_heart_rate", "bpm", True),
    "HKQuantityTypeIdentifierWalkingHeartRateAverage": ("walking_heart_rate_average", "bpm", True),
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": ("heart_rate_variability", "value", True),
    "HKQuantityTypeIdentifierOxygenSaturation": ("oxygen_saturation", "value", True),
    "HKQuantityTypeIdentifierRespiratoryRate": ("respiratory_rate", "value", True),
    "HKQuantityTypeIdentifierStepCount": ("step_count", "value", True),
    "HKQuantityTypeIdentifierDistanceWalkingRunning": ("walking_running_distance", "value", True),
    "HKQuantityTypeIdentifierActiveEnergyBurned": ("active_energy", "value", True),
    "HKQuantityTypeIdentifierBasalEnergyBurned": ("basal_energy", "value", True),
    "HKQuantityTypeIdentifierAppleExerciseTime": ("exercise_time", "value", True),
    "HKQuantityTypeIdentifierAppleStandTime": ("stand_time", "value", True),
    "HKQuantityTypeIdentifierFlightsClimbed": ("flights_climbed", "value", True),
    "HKQuantityTypeIdentifierWalkingSpeed": ("walking_speed", "value", True),
    "HKQuantityTypeIdentifierWalkingStepLength": ("walking_step_length", "value", True),
    "HKQuantityTypeIdentifierWalkingAsymmetryPercentage": ("walking_asymmetry", "value", True),
    "HKQuantityTypeIdentifierWalkingDoubleSupportPercentage": ("walking_double_support", "value", True),
    "HKQuantityTypeIdentifierStairAscentSpeed": ("stair_ascent_speed", "value", True),
    "HKQuantityTypeIdentifierStairDescentSpeed": ("stair_descent_speed", "value", True),
    "HKQuantityTypeIdentifierEnvironmentalAudioExposure": ("environmental_audio_exposure", "value", True),
    "HKQuantityTypeIdentifierTimeInDaylight": ("time_in_daylight", "value", True),
    "HKQuantityTypeIdentifierPhysicalEffort": ("physical_effort", "value", True),
    "HKCategoryTypeIdentifierSleepAnalysis": ("sleep_analysis", "value", False),
    "HKCategoryTypeIdentifierAppleStandHour": ("stand_hour", "value", False),
}


def parse_apple_datetime(value):
    # Apple Health export timestamps are commonly like:
    # 2026-06-01 09:18:00 +0800
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S %z")


@contextmanager
def open_export_xml(path):
    path = Path(path)
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if name.endswith("export.xml"):
                    with archive.open(name) as stream:
                        yield stream
                    return
            raise FileNotFoundError("export.xml not found inside zip")
    else:
        with path.open("rb") as stream:
            yield stream


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
    labels = {
        "heart_rate": "心率",
        "resting_heart_rate": "静息心率",
        "walking_heart_rate_average": "步行平均心率",
        "heart_rate_variability": "心率变异性",
        "oxygen_saturation": "血氧",
        "respiratory_rate": "呼吸频率",
        "step_count": "步数",
        "walking_running_distance": "步行/跑步距离",
        "active_energy": "活动能量",
        "basal_energy": "基础能量",
        "exercise_time": "运动时间",
        "stand_time": "站立时间",
        "flights_climbed": "爬楼层数",
        "walking_speed": "步行速度",
        "walking_step_length": "步长",
        "walking_asymmetry": "步行不对称比例",
        "walking_double_support": "双脚支撑比例",
        "stair_ascent_speed": "上楼速度",
        "stair_descent_speed": "下楼速度",
        "environmental_audio_exposure": "环境声音暴露",
        "time_in_daylight": "日光时间",
        "physical_effort": "身体活动强度",
        "sleep_analysis": "睡眠状态",
        "stand_hour": "站立小时",
    }
    return f"Apple 健康记录{labels.get(modality, modality)}：{value} {unit}".strip()


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
                start_time = parse_apple_datetime(elem.attrib.get("startDate", elem.attrib["endDate"]))
            except (KeyError, ValueError):
                elem.clear()
                continue

            if date and not (start_time.date().isoformat() <= date <= end_time.date().isoformat()):
                elem.clear()
                continue

            modality, default_unit, numeric = TYPE_MAP[record_type]
            unit = elem.attrib.get("unit") or default_unit
            value_text = elem.attrib.get("value")
            if numeric:
                try:
                    value = float(value_text)
                    if value.is_integer():
                        value = int(value)
                except (TypeError, ValueError):
                    elem.clear()
                    continue
            else:
                value = value_text or "unknown"

            raw_key = "bpm" if modality == "heart_rate" else "value"
            event = {
                "timestamp": start_time.isoformat(),
                "end_timestamp": end_time.isoformat(),
                "source": source_label(source_name),
                "modality": modality,
                "raw": {raw_key: value, "unit": unit, "sourceName": source_name},
                "summary": build_summary(modality, value, unit),
                "confidence": confidence_for(record_type),
                "location": "",
                "context": {"route": "apple", "activity": "unknown"},
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
