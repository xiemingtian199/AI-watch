import argparse
import json
import os
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from urllib import request


CARD_TYPES = {
    "stress_event": "压力事件",
    "behavior_pattern": "行为习惯",
    "work_state": "工作状态",
    "relationship": "人际互动",
    "sleep_routine": "异常作息",
    "action": "建议行动",
}


def parse_time(value):
    return datetime.fromisoformat(value)


def load_events(input_dir, target_date):
    events = []
    for path in sorted(Path(input_dir).glob("*.jsonl")):
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                event = json.loads(line)
                event["_file"] = path.name
                event["_line"] = line_number
                if event["timestamp"].startswith(target_date):
                    events.append(event)
    events.sort(key=lambda event: event["timestamp"])
    return events


def window(events, center, minutes_before=10, minutes_after=12):
    start = center - timedelta(minutes=minutes_before)
    end = center + timedelta(minutes=minutes_after)
    return [
        event for event in events
        if start <= parse_time(event["timestamp"]) <= end
    ]


def evidence_line(event):
    when = parse_time(event["timestamp"]).strftime("%H:%M")
    summary = event.get("summary") or json.dumps(event.get("raw", {}), ensure_ascii=False)
    return {
        "time": when,
        "source": event.get("source", "unknown"),
        "modality": event.get("modality", "unknown"),
        "summary": summary,
        "confidence": event.get("confidence", 0.5),
    }


def make_card(card_id, card_type, title, time_range, body, suggestion, events, confidence):
    evidence_events = sorted(
        events,
        key=lambda event: (
            0 if event.get("source") == "manual_context" else 1,
            event.get("timestamp", ""),
        ),
    )
    return {
        "id": card_id,
        "type": card_type,
        "typeLabel": CARD_TYPES[card_type],
        "title": title,
        "timeRange": time_range,
        "body": body,
        "suggestion": suggestion,
        "confidence": round(confidence, 2),
        "evidence": [evidence_line(event) for event in evidence_events[:6]],
        "feedback": None,
    }


def event_value(event):
    raw = event.get("raw", {})
    if "bpm" in raw:
        return raw["bpm"]
    return raw.get("value")


def hourly_totals(events, modality):
    totals = defaultdict(float)
    buckets = defaultdict(list)
    for event in events:
        if event.get("modality") != modality:
            continue
        value = event_value(event)
        if not isinstance(value, (int, float)):
            continue
        hour = parse_time(event["timestamp"]).hour
        totals[hour] += value
        buckets[hour].append(event)
    return totals, buckets


def add_heart_cards(cards, events, heart_events):
    if not heart_events:
        return

    bpms = [event["raw"]["bpm"] for event in heart_events]
    baseline = statistics.median(bpms)
    lowest = min(heart_events, key=lambda event: event["raw"]["bpm"])
    highest = max(heart_events, key=lambda event: event["raw"]["bpm"])
    peak_candidates = [
        event for event in heart_events
        if event["raw"]["bpm"] >= max(105, baseline + 18)
    ]

    if peak_candidates or highest["raw"]["bpm"] >= baseline + 10:
        peak = max(peak_candidates, key=lambda event: event["raw"]["bpm"]) if peak_candidates else highest
        center = parse_time(peak["timestamp"])
        related = window(events, center)
        context_terms = "、".join(sorted({
            item.get("context", {}).get("activity", "")
            for item in related
            if item.get("context", {}).get("activity")
        })[:3])
        cards.append(make_card(
            "card-stress-peak",
            "stress_event",
            "一次可能被低估的高负荷时段",
            f"{(center - timedelta(minutes=8)).strftime('%H:%M')} - {(center + timedelta(minutes=12)).strftime('%H:%M')}",
            f"这段时间心率最高到 {peak['raw']['bpm']}，高于当天中位数 {int(baseline)}。在只有 Apple 健康数据的情况下，先把它视为一个待解释的高负荷窗口。",
            f"建议给这个时段补一条人工备注：{context_terms or '当时是在通勤、工作、沟通还是运动'}。",
            related,
            0.8,
        ))

    cards.append(make_card(
        "card-heart-range",
        "stress_event",
        "今天的心率跨度可以作为身体负荷基线",
        "全天",
        f"今天 Apple Watch 记录到的心率范围大约是 {lowest['raw']['bpm']} 到 {highest['raw']['bpm']}，中位数约 {int(baseline)}。这不是诊断，但可以作为后续判断工作、通勤和休息状态的个人基线。",
        "连续导入三天数据后，优先观察同一时段是否稳定高于自己的基线。",
        [lowest, highest] + heart_events[:4],
        0.74,
    ))

    early_rest = [
        event for event in heart_events
        if parse_time(event["timestamp"]).hour < 7
    ]
    if len(early_rest) >= 8:
        rest_values = [event["raw"]["bpm"] for event in early_rest]
        rest_median = statistics.median(rest_values)
        cards.append(make_card(
            "card-resting-heart",
            "sleep_routine",
            "夜间和清晨心率能作为恢复参考",
            f"{parse_time(early_rest[0]['timestamp']).strftime('%H:%M')} - {parse_time(early_rest[-1]['timestamp']).strftime('%H:%M')}",
            f"凌晨到清晨记录较密集，心率中位数约 {int(rest_median)}。如果后续加入睡眠、屏幕和晚间工作记录，这张卡可以判断恢复是否被打断。",
            "今晚额外记录睡前最后一次工作或刷手机时间，明天对比清晨心率是否变化。",
            early_rest[:6],
            0.69,
        ))


def add_activity_cards(cards, events):
    steps_by_hour, step_buckets = hourly_totals(events, "step_count")
    if steps_by_hour:
        top_hour = max(steps_by_hour, key=steps_by_hour.get)
        hour_notes = [
            event for event in events
            if event.get("source") == "manual_context"
            and parse_time(event["timestamp"]).hour == top_hour
        ]
        cards.append(make_card(
            "card-activity-peak",
            "behavior_pattern",
            "今天的活动量集中在一个明显时段",
            f"{top_hour:02d}:00 - {top_hour:02d}:59",
            f"步数记录显示，{top_hour:02d} 点附近是今天活动量最集中的时段之一，合计约 {int(steps_by_hour[top_hour])} 步。它可能对应通勤、外出或一段较长移动。",
            "给这段时间补一条人工备注，例如通勤、办事、散步或运动，卡片会更接近真实场景。",
            hour_notes + step_buckets[top_hour],
            0.73,
        ))

    energy_by_hour, energy_buckets = hourly_totals(events, "active_energy")
    if energy_by_hour:
        top_hour = max(energy_by_hour, key=energy_by_hour.get)
        hour_notes = [
            event for event in events
            if event.get("source") == "manual_context"
            and parse_time(event["timestamp"]).hour == top_hour
        ]
        cards.append(make_card(
            "card-energy-window",
            "work_state",
            "活动能量提示今天有一个高消耗窗口",
            f"{top_hour:02d}:00 - {top_hour:02d}:59",
            f"活动能量在 {top_hour:02d} 点附近最高，约 {energy_by_hour[top_hour]:.1f} kcal。单看健康数据无法判断原因，但它适合和日程、地点或语音备注合并分析。",
            "把这个小时发生的主要事情补进时间线，优先标记是运动、通勤还是工作奔波。",
            hour_notes + energy_buckets[top_hour][:6],
            0.66,
        ))


def add_context_cards(cards, events):
    ignored_activities = {"sleep_or_rest", "morning", "work", "lunch", "evening", "late_routine"}
    activities = Counter(
        event.get("context", {}).get("activity")
        for event in events
        if event.get("context", {}).get("activity")
        and event.get("context", {}).get("activity") not in ignored_activities
    )
    repeated = [name for name, count in activities.items() if count >= 3]
    if repeated:
        matched = [
            event for event in events
            if event.get("context", {}).get("activity") == repeated[0]
        ]
        cards.append(make_card(
            "card-pattern-repeat",
            "behavior_pattern",
            "一个反复出现的行为线索",
            "全天",
            f"`{repeated[0]}` 在今天的数据里出现了 {len(matched)} 次。这个频率值得继续观察，尤其是它是否总和心率变化、位置切换或晚间疲劳同时出现。",
            "明天继续观察同一线索，如果连续三天出现，再把它升级为固定复盘项。",
            matched,
            0.72,
        ))

    work_events = [
        event for event in events
        if event.get("context", {}).get("activity") in {"deep_work", "writing", "pre-meeting", "meeting", "work", "office_work", "lunch_break"}
    ]
    if work_events:
        has_manual_work = any(event.get("source") == "manual_context" for event in work_events)
        cards.append(make_card(
            "card-work-mode",
            "work_state",
            "今天的工作段主要是办公室日常工作" if has_manual_work else "今天的工作段还缺少场景解释",
            f"{parse_time(work_events[0]['timestamp']).strftime('%H:%M')} - {parse_time(work_events[-1]['timestamp']).strftime('%H:%M')}",
            "你补充的场景显示，10:06 到 18:26 主要是办公室日常工作，中间 12:00 到 13:00 午休，今天没有会议。Apple 健康数据可以用来观察这种普通工作日的身体基线。" if has_manual_work else "Apple 健康数据能看到工作时段附近的身体信号，但还不知道你当时是在写稿、开会、处理消息还是沟通。",
            "接下来连续记录 3 个无会议工作日，再和有会议/外出日对比，判断会议或通勤是否显著改变身体负荷。" if has_manual_work else "下一步补充日历和 3-5 条手动语音备注，卡片会从身体统计变成场景洞察。",
            work_events,
            0.65,
        ))

    relationship_events = [
        event for event in events
        if event.get("context", {}).get("activity") in {"family_chat", "colleague_chat", "client_call"}
        or "对话" in (event.get("summary") or "")
    ]
    if relationship_events:
        cards.append(make_card(
            "card-relationship",
            "relationship",
            "一段沟通可能比你感觉中更耗能",
            f"{parse_time(relationship_events[0]['timestamp']).strftime('%H:%M')} - {parse_time(relationship_events[-1]['timestamp']).strftime('%H:%M')}",
            "今天的人际沟通数据里出现了语速、心率或地点切换的重叠信号。它不一定代表负面情绪，但说明这类互动值得单独标记。",
            "下次类似对话后，手动记录一句真实感受，用来校准 AI 的判断。",
            relationship_events,
            0.68,
        ))

    late_events = [
        event for event in events
        if parse_time(event["timestamp"]).hour >= 22
    ]
    if late_events:
        cards.append(make_card(
            "card-night-routine",
            "sleep_routine",
            "睡前信息摄入可能拖长了恢复时间",
            f"{parse_time(late_events[0]['timestamp']).strftime('%H:%M')} - {parse_time(late_events[-1]['timestamp']).strftime('%H:%M')}",
            "晚间仍有屏幕、音频或心率波动记录。它可能在延迟身体从工作状态切换到休息状态。",
            "今晚把最后一次复盘提前到睡前 45 分钟，并关闭非必要采集。",
            late_events,
            0.7,
        ))


def heuristic_cards(events, target_date):
    cards = []
    heart_events = [
        event for event in events
        if event.get("modality") == "heart_rate" and "bpm" in event.get("raw", {})
    ]

    add_heart_cards(cards, events, heart_events)
    add_activity_cards(cards, events)
    add_context_cards(cards, events)

    source_counts = Counter(event.get("source", "unknown") for event in events)
    cards.append(make_card(
        "card-action-tomorrow",
        "action",
        "明天只验证一个问题",
        "明日",
        f"今天合并了 {len(events)} 条事件，来源包括 {', '.join(source_counts.keys())}。第一版 MVP 不需要解释一切，最有价值的是连续追踪一个问题。",
        "建议明天只追踪：哪一种场景最容易让你的身体进入高负荷状态。",
        events[-6:] if len(events) > 6 else events,
        0.78,
    ))

    return cards[:8]


def cloud_cards(events, target_date):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return heuristic_cards(events, target_date)

    payload_events = [
        {
            "timestamp": event["timestamp"],
            "source": event.get("source"),
            "modality": event.get("modality"),
            "summary": event.get("summary"),
            "raw": event.get("raw"),
            "confidence": event.get("confidence"),
            "location": event.get("location"),
            "context": event.get("context"),
        }
        for event in events
    ]
    prompt = (
        "你是个人 AI 手表 MVP 的每日复盘引擎。"
        "请基于多模态时间线生成 5-8 张中文复盘卡。"
        "不要做医学诊断，不要武断判断心理状态，使用可能、看起来、建议回看等表达。"
        "返回严格 JSON 数组，每张卡包含 id,type,typeLabel,title,timeRange,body,suggestion,confidence,evidence。"
        f"日期: {target_date}\n事件:\n"
        f"{json.dumps(payload_events, ensure_ascii=False)}"
    )
    body = {
        "model": os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"),
        "messages": [
            {"role": "system", "content": "Return only valid JSON."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
    }
    req = request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with request.urlopen(req, timeout=90) as response:
        result = json.loads(response.read().decode("utf-8"))
    content = result["choices"][0]["message"]["content"]
    return json.loads(content)


def build_timeline(events):
    return [
        {
            "time": parse_time(event["timestamp"]).strftime("%H:%M"),
            "timestamp": event["timestamp"],
            "source": event.get("source", "unknown"),
            "modality": event.get("modality", "unknown"),
            "summary": event.get("summary", ""),
            "confidence": event.get("confidence", 0.5),
            "location": event.get("location", ""),
            "context": event.get("context", {}),
        }
        for event in events
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--cloud", action="store_true")
    args = parser.parse_args()

    events = load_events(args.input, args.date)
    if not events:
        print(f"No events found for {args.date}", file=sys.stderr)
        return 1

    cards = cloud_cards(events, args.date) if args.cloud else heuristic_cards(events, args.date)
    output = {
        "date": args.date,
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "mode": "cloud" if args.cloud and os.environ.get("OPENAI_API_KEY") else "local_heuristic",
        "summary": {
            "eventCount": len(events),
            "sources": dict(Counter(event.get("source", "unknown") for event in events)),
            "modalities": dict(Counter(event.get("modality", "unknown") for event in events)),
        },
        "cards": cards,
        "timeline": build_timeline(events),
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out_path} with {len(cards)} cards from {len(events)} events")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
