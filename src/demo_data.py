"""Deterministic, explicitly fictional data, separate from personal records."""
from datetime import date, datetime, timedelta, timezone


def demo_events():
    rows = []
    end = date(2026, 9, 12)
    for index in range(14):
        day = end - timedelta(days=13-index)
        base = datetime.combine(day, datetime.min.time(), timezone(timedelta(hours=8)))

        def add(hour, modality, raw, summary='', duration=None, activity=''):
            stamp = base + timedelta(hours=hour)
            row = {'timestamp': stamp.isoformat(), 'source': 'demo_watch',
                   'modality': modality, 'raw': raw, 'summary': summary,
                   'context': {'activity': activity}, 'confidence': 1}
            if duration:
                row['end_timestamp'] = (stamp + timedelta(minutes=duration)).isoformat()
            rows.append(row)
            return row

        for hour in range(7, 24):
            add(hour, 'heart_rate', {'bpm': 67 + ((hour*7+index*3) % 21) + (16 if hour == 9 else 0)})
        add(0, 'sleep_analysis', {'value': 'HKCategoryValueSleepAnalysisAsleep', 'unit': 'category'}, duration=402+(index*17)%80)
        add(7, 'resting_heart_rate', {'value': 59+(index*3)%7, 'unit': 'count/min'})
        add(7.1, 'heart_rate_variability', {'value': 38+(index*7)%25, 'unit': 'ms'})
        for hour in [8, 12, 18, 20]:
            add(hour, 'step_count', {'value': 1350+(index*131+hour*31)%1100, 'unit': 'count'})
            add(hour, 'active_energy', {'value': 70+(index*11+hour)%60, 'unit': 'kcal'})
        add(8.15, 'context_note', {'text': '步行到地铁站，听了一段播客。'}, '步行通勤，开启一天', 35, 'commute')['source'] = 'demo_journal'
        add(9.5, 'context_note', {'text': '与团队讨论产品方案，整理了三项待确认事项。'}, '产品方案讨论', 50, 'meeting')['source'] = 'demo_journal'
        add(14, 'focus_session', {'duration_min': 65+(index*13)%70}, '整理方案，完成了一段连续工作', 65+(index*13)%70, 'deep_work')['source'] = 'demo_journal'
        evening = add(18.5, 'photo_note', {'image': '/assets/park.jpg'}, '傍晚散步，给自己留一段空白', 40, 'walking')
        evening['source'] = 'demo_journal'
        evening['location'] = '城市公园'
        add(21, 'context_note', {'text': '读了几页书，记下今天最想保留的一个想法。'}, '阅读与晚间回顾', 30, 'reading')['source'] = 'demo_journal'
        add(21.5, 'mood', {'value': [3,4,3,4,5,4,3,4,4,5,3,4,5,4][index]}, '晚间自评')['source'] = 'demo_journal'
    return rows
