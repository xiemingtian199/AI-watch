"""Local event storage, imports, and evidence-based daily projections."""
import csv
import hashlib
import io
import json
import math
import sqlite3
import statistics
import subprocess
import tempfile
import uuid
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

from convert_apple_health import convert
from demo_data import demo_events


TZ = timezone(timedelta(hours=8))
ACTIVITIES = {'commute': '通勤', 'meeting': '交流讨论', 'deep_work': '专注记录',
              'walking': '散步', 'reading': '阅读', 'work': '工作记录',
              'office_work': '工作记录', 'family_chat': '家庭交流', 'exercise': '运动',
              'lunch': '用餐', 'manual_note': '生活记录'}
MEDIA_TYPES = {'.m4a': 'audio', '.mp3': 'audio', '.wav': 'audio', '.ogg': 'audio',
               '.flac': 'audio', '.aac': 'audio', '.mp4': 'video', '.mov': 'video',
               '.jpg': 'image', '.jpeg': 'image', '.png': 'image', '.webp': 'image'}
METRICS = {'steps': ('步数', '步'), 'sleep': ('睡眠时长', '小时'),
           'heart': ('心率中位数', 'bpm'), 'focus': ('专注记录', '分钟'),
           'energy': ('活动能量', 'kcal'), 'mood': ('状态自评', '/ 5')}


def parse_time(value):
    stamp = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        raise ValueError('时间必须包含时区，例如 2026-09-12T09:00:00+08:00')
    return stamp.astimezone(TZ)


def number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def normalize(row):
    if not isinstance(row, dict) or not row.get('timestamp') or not row.get('modality'):
        raise ValueError('每条记录需要 timestamp 和 modality')
    start = parse_time(row['timestamp'])
    result = {'timestamp': start.isoformat(), 'source': str(row.get('source') or 'local_import')[:100],
              'modality': str(row['modality'])[:100], 'summary': str(row.get('summary') or '')[:4000],
              'location': str(row.get('location') or '')[:200],
              'raw': row.get('raw') or {}, 'context': row.get('context') or {}}
    if not isinstance(result['raw'], dict) or not isinstance(result['context'], dict):
        raise ValueError('raw 和 context 必须为对象')
    raw = result['raw']
    if result['modality'] in {'step_count', 'active_energy', 'mood'}:
        value = number(raw.get('value'))
        if value is None or value < 0:
            raise ValueError('步数、能量和自评记录需要非负的有限 value')
        if result['modality'] == 'mood' and value not in range(1, 6):
            raise ValueError('状态自评为 1-5')
    if result['modality'] == 'focus_session' and not row.get('end_timestamp'):
        duration = number(raw.get('duration_min'))
        if duration is None or not 0 < duration <= 1440:
            raise ValueError('专注记录需要结束时间或 1 天以内的 duration_min')
        row = {**row, 'end_timestamp': (start + timedelta(minutes=duration)).isoformat()}
    if row.get('end_timestamp'):
        end = parse_time(row['end_timestamp'])
        if end < start:
            raise ValueError('结束时间不能早于开始时间')
        if end - start > timedelta(days=366):
            raise ValueError('单条记录不能超过 366 天，请拆分记录')
        result['end_timestamp'] = end.isoformat()
    if row.get('media_id'):
        result['media_id'] = str(row['media_id'])
    if row.get('media_type'):
        result['media_type'] = str(row['media_type'])
    result['id'] = hashlib.sha256(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()).hexdigest()[:24]
    return result


def decode_records(path):
    text = path.read_text(encoding='utf-8-sig')
    if path.suffix.lower() == '.csv':
        rows = []
        for item in csv.DictReader(io.StringIO(text)):
            raw = json.loads(item['raw']) if item.get('raw') else {}
            if item.get('value'):
                value = number(item['value'])
                if value is None:
                    raise ValueError('CSV value 必须是有限数字')
                raw['bpm' if item.get('modality') == 'heart_rate' else 'value'] = value
            if item.get('unit'):
                raw['unit'] = item['unit']
            rows.append({**item, 'raw': raw, 'context': {'activity': item.get('activity', '')}})
        return rows
    try:
        content = json.loads(text)
        if isinstance(content, dict):
            content = content.get('events', [content])
        if not isinstance(content, list):
            raise ValueError('JSON 必须包含记录数组或 events 数组')
        return content
    except json.JSONDecodeError:
        rows = []
        for index, line in enumerate(text.splitlines(), 1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ValueError(f'第 {index} 行不是有效 JSON') from exc
        return rows


def union_minutes(intervals):
    total, edge = 0, None
    for start, end in sorted(intervals):
        if edge is not None:
            start = max(start, edge)
        if end > start:
            total += (end-start).total_seconds()/60
        edge = max(edge, end) if edge else end
    return total


def summarize(day, events, mood=None):
    start = datetime.combine(datetime.fromisoformat(day).date(), time.min, TZ)
    end = start + timedelta(days=1)
    values = defaultdict(list)
    intervals = defaultdict(list)
    series, episodes, step_series = [], [], []
    selected, aggregation = {}, {}
    # Choose one source per cumulative metric/day; phone and watch totals overlap.
    for modality in ('step_count', 'active_energy'):
        sources = defaultdict(dict)
        for row in events:
            if row['modality'] == modality:
                raw = row['raw']
                source = str(raw.get('sourceName') or row['source'])
                key = (row['timestamp'], row.get('end_timestamp'), str(raw.get('value')), raw.get('unit'))
                sources[source].setdefault(key, row['id'])
        if sources:
            source = sorted(sources, key=lambda name: (-len(sources[name]), name))[0]
            selected[modality] = set(sources[source].values())
            aggregation[modality] = {'source': source, 'sourceCount': len(sources),
                                    'method': 'single_source_most_samples'}
    for row in events:
        modality, raw = row['modality'], row['raw']
        value = number(raw.get('bpm', raw.get('value')))
        stamp = parse_time(row['timestamp'])
        stop = parse_time(row.get('end_timestamp', row['timestamp']))
        if value is not None and (modality not in selected or row['id'] in selected[modality]):
            # Cumulative interval samples are apportioned at local day boundaries.
            part = 1
            if stop > stamp and modality in {'step_count', 'active_energy'}:
                part = max(0, (min(stop,end)-max(stamp,start)).total_seconds())/(stop-stamp).total_seconds()
            if modality == 'active_energy' and raw.get('unit') == 'kJ':
                value /= 4.184
            values[modality].append(value*part)
            if modality == 'step_count':
                point_time = max(stamp, start)
                step_series.append({'x': point_time.hour + point_time.minute/60,
                                    'y': round(value*part, 2)})
        if modality == 'heart_rate' and value is not None and 0 < value < 300:
            series.append({'time': stamp.strftime('%H:%M'), 'x': stamp.hour+stamp.minute/60, 'y': value})
        if modality == 'sleep_analysis' and stop > stamp:
            category = str(raw.get('value', '')).lower()
            if 'asleep' in category or number(raw.get('value')) in {1, 3, 4, 5}:
                intervals['sleep'].append((max(stamp,start), min(stop,end)))
        if modality == 'focus_session':
            if stop <= stamp and number(raw.get('duration_min')) is not None:
                stop = stamp + timedelta(minutes=max(0, number(raw['duration_min'])))
            if stop > stamp:
                intervals['focus'].append((max(stamp,start), min(stop,end)))
        if row.get('summary') and modality not in {'heart_rate', 'step_count', 'active_energy',
                    'sleep_analysis', 'resting_heart_rate', 'heart_rate_variability', 'mood'}:
            activity = row['context'].get('activity','')
            episodes.append({**row, 'time': stamp.strftime('%H:%M'),
                'endTime': stop.strftime('%H:%M') if stop > stamp else '',
                'label': ACTIVITIES.get(activity, '日程计划' if modality=='schedule' else '生活记录'),
                'image': raw.get('image','') if row['source'].startswith('demo_') else '',
                'kind': 'plan' if modality == 'schedule' else 'record'})
    hearts = [p['y'] for p in series]
    metrics = {'steps': round(sum(values['step_count'])) if values['step_count'] else None,
               'energy': round(sum(values['active_energy'])) if values['active_energy'] else None,
               'heart': round(statistics.median(hearts)) if hearts else None,
               'sleep': round(union_minutes(intervals['sleep'])/60, 2) if intervals['sleep'] else None,
               'focus': round(union_minutes(intervals['focus'])) if intervals['focus'] else None,
               'mood': mood if mood is not None else (values['mood'][-1] if values['mood'] else None)}
    counts = dict(Counter(row['source'] for row in events))
    names = list(dict.fromkeys(e['label'] for e in episodes if e['kind'] != 'plan'))
    title = '、'.join(names[:3]) + '，这是有记录的一天' if names else '从今天的记录，慢慢认识自己'
    if not events:
        title = '这一天，等待留下记录'
    body = f'已同步 {len(events)} 条记录，来自 {len(counts)} 个来源。'
    if episodes:
        body += ' 时间线保留了' + '、'.join(names[:4] or ['日程计划']) + '等片段。'
    if metrics['steps'] is not None:
        body += f" 活动记录累计 {metrics['steps']:,} 步。"
    if hearts:
        body += f' 心率样本范围 {min(hearts):g}-{max(hearts):g} bpm，中位数 {metrics["heart"]} bpm。'
    for modality, info in aggregation.items():
        if info['sourceCount'] > 1:
            label = '步数' if modality == 'step_count' else '活动能量'
            body += f' {label}采用当日样本最多的单一来源（{info["source"]}），其他来源未叠加。'
    if not events:
        body = '暂无记录。'
    highlights = []
    if metrics['focus']:
        highlights.append({'type': 'focus', 'title': '留给一件事的时间',
            'body': f"有明确起止时间的专注记录共 {metrics['focus']} 分钟。", 'evidence': [e['id'] for e in events if e['modality']=='focus_session']})
    if hearts:
        peak = max(series, key=lambda p:p['y'])
        highlights.append({'type': 'heart', 'title': '一个值得回看的时刻',
            'body': f"{peak['time']} 记录到最高心率 {peak['y']:g} bpm。可结合当时经历回看，当前记录不能判断心理压力。", 'evidence': [r['id'] for r in events if r['modality']=='heart_rate' and number(r['raw'].get('bpm',r['raw'].get('value')))==peak['y']]})
    return {'date':day, 'title':title, 'summary':body, 'metrics':metrics, 'sources':counts,
            'eventCount':len(events), 'episodes':episodes, 'heartSeries':series,
            'stepSeries':step_series, 'aggregation':aggregation,
            'highlights':highlights, 'events':events, 'keywords':names,
            'generatedAt': datetime.now(TZ).isoformat()}


class Workbench:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.database = self.directory / 'workbench.sqlite3'
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS events (id TEXT, dataset TEXT, start TEXT, end TEXT, body TEXT,
                    PRIMARY KEY(id,dataset));
                CREATE INDEX IF NOT EXISTS event_time ON events(dataset,start,end);
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
                CREATE TABLE IF NOT EXISTS imports (id TEXT PRIMARY KEY, digest TEXT UNIQUE, name TEXT,
                    kind TEXT, size INTEGER, count INTEGER, created TEXT, dates TEXT, path TEXT);
                CREATE TABLE IF NOT EXISTS checkins (dataset TEXT,date TEXT, mood INTEGER,note TEXT,
                    PRIMARY KEY(dataset,date));
                CREATE TABLE IF NOT EXISTS feedback (dataset TEXT,id TEXT,value TEXT,PRIMARY KEY(dataset,id));
            ''')
            if not db.execute("SELECT 1 FROM settings WHERE key='initialized'").fetchone():
                for row in demo_events():
                    self.insert(db, normalize(row), 'demo')
                # Import previous local JSONL records once; originals are preserved.
                warnings = []
                for path in sorted(self.directory.glob('*.jsonl')):
                    try:
                        records = decode_records(path)
                    except (ValueError, OSError) as exc:
                        warnings.append(f'{path.name}: {exc}')
                        continue
                    for row in records:
                        try:
                            self.insert(db, normalize(row), 'personal')
                        except ValueError:
                            warnings.append(f'{path.name}: 一条无效记录未迁移')
                            continue
                db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',
                           ('migrationWarnings', json.dumps(warnings, ensure_ascii=False)))
                db.execute("INSERT INTO settings VALUES ('initialized','true')")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def dataset(value):
        if value not in {'personal','demo'}:
            raise ValueError('数据集无效')
        return value

    @staticmethod
    def insert(db, row, dataset):
        before = db.total_changes
        db.execute('INSERT OR IGNORE INTO events VALUES (?,?,?,?,?)',
                   (row['id'],dataset,row['timestamp'],row.get('end_timestamp',row['timestamp']),json.dumps(row,ensure_ascii=False)))
        return db.total_changes-before

    def profile(self, dataset):
        with self.connect() as db:
            saved = db.execute('SELECT value FROM settings WHERE key=?', ('profile:'+dataset,)).fetchone()
        if saved:
            return json.loads(saved['value'])
        return {'name':'林川' if dataset=='demo' else '我的档案',
                'role':'产品设计师 · 示例人物' if dataset=='demo' else '',
                'city':'上海' if dataset=='demo' else '',
                'bio':'认真工作，也给散步、阅读和生活留一些时间。' if dataset=='demo' else '',
                'goal':'保持规律作息，每天留一点时间给自己。' if dataset=='demo' else '',
                'avatar':'', 'stepGoal':8000, 'sleepGoal':8}

    def save_profile(self, dataset, payload):
        result = self.profile(dataset)
        for key in ('name','role','city','bio','goal'):
            result[key] = str(payload.get(key,result.get(key,''))).strip()[:(400 if key in {'bio','goal'} else 80)]
        if not result['name']:
            raise ValueError('请填写名字')
        for key, low, high in [('stepGoal',100,100000),('sleepGoal',1,16)]:
            value = number(payload.get(key,result[key]))
            if value is None or not low <= value <= high:
                raise ValueError('个人目标超出可设置范围')
            result[key] = value
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', ('profile:'+dataset,json.dumps(result,ensure_ascii=False)))
        return result

    def events(self, dataset):
        with self.connect() as db:
            return [json.loads(r['body']) for r in db.execute('SELECT body FROM events WHERE dataset=? ORDER BY start,id',(dataset,))]

    def daily(self, dataset, day):
        day = datetime.fromisoformat(day).date().isoformat()
        start = datetime.combine(datetime.fromisoformat(day).date(),time.min,TZ)
        end = start+timedelta(days=1)
        with self.connect() as db:
            rows = db.execute('SELECT body FROM events WHERE dataset=? AND start<? AND end>=? ORDER BY start,id',
                              (dataset,end.isoformat(),start.isoformat())).fetchall()
            checkin = db.execute('SELECT mood,note FROM checkins WHERE dataset=? AND date=?',(dataset,day)).fetchone()
            feedback = {r['id']:r['value'] for r in db.execute('SELECT id,value FROM feedback WHERE dataset=?',(dataset,))}
        events = [json.loads(r['body']) for r in rows]
        # A duration ending exactly at midnight belongs to the preceding day.
        events = [r for r in events if parse_time(r['timestamp']) >= start or parse_time(r.get('end_timestamp',r['timestamp'])) > start]
        report = summarize(day, events, checkin['mood'] if checkin else None)
        report['checkin'] = dict(checkin) if checkin else {'mood':None,'note':''}
        report['feedback'] = feedback
        return report

    def overview(self, dataset):
        rows = self.events(dataset)
        dates = set()
        for row in rows:
            start, end = parse_time(row['timestamp']), parse_time(row.get('end_timestamp',row['timestamp']))
            last = (end-timedelta(microseconds=1) if end>start else end).date()
            current = start.date()
            while current <= last:
                dates.add(current.isoformat())
                current += timedelta(days=1)
        with self.connect() as db:
            dates.update(r['date'] for r in db.execute('SELECT date FROM checkins WHERE dataset=?',(dataset,)))
            warning_row = db.execute("SELECT value FROM settings WHERE key='migrationWarnings'").fetchone()
        days = []
        for day in sorted(dates):
            report = self.daily(dataset,day)
            days.append({**{k:report[k] for k in ('date','title','summary','metrics','eventCount','keywords')},
                         'reflection':report['checkin']['note']})
        return {'dataset':dataset,'profile':self.profile(dataset),'days':days,
                'migrationWarnings':json.loads(warning_row['value']) if warning_row and dataset=='personal' else [],
                'sources':dict(Counter(r['source'] for r in rows)), 'eventCount':len(rows)}

    def import_file(self, path, original_name, digest, start=None, summary=''):
        with self.connect() as db:
            exists = db.execute('SELECT count,dates FROM imports WHERE digest=?',(digest,)).fetchone()
        if exists:
            return {'duplicate':True,'added':0,'dates':json.loads(exists['dates'])}
        suffix = path.suffix.lower()
        media_id = uuid.uuid4().hex
        kind = 'records'
        if suffix in {'.xml','.zip'}:
            kind = 'health'
            with tempfile.TemporaryDirectory() as folder:
                converted = Path(folder)/'health.jsonl'
                convert(path,converted)
                rows = decode_records(converted)
        elif suffix in {'.json','.jsonl','.csv'}:
            rows = decode_records(path)
        elif suffix in MEDIA_TYPES:
            kind = MEDIA_TYPES[suffix]
            if not start:
                import re
                match = re.search(r'(\d{4}-\d{2}-\d{2})[ _T](\d{2})[-_:](\d{2})',original_name)
                if match:
                    start = f'{match[1]}T{match[2]}:{match[3]}:00+08:00'
            if not start:
                raise ValueError('请填写这段素材的拍摄/录制开始时间')
            stamp = parse_time(start)
            raw = {'file':original_name}
            row = {'timestamp':stamp.isoformat(),'source':'local_media',
                'modality':{'audio':'audio_session','video':'video_note','image':'photo_note'}[kind],
                'raw':raw, 'summary':summary.strip() or f'已导入{ {"audio":"录音","video":"视频","image":"照片"}[kind]}：{original_name}',
                'media_id':media_id, 'media_type':kind}
            if kind in {'audio','video'}:
                try:
                    probe = subprocess.run(['ffprobe','-v','error','-show_entries','format=duration',
                        '-of','json',str(path)],capture_output=True,text=True,check=True,timeout=60)
                    duration = number(json.loads(probe.stdout)['format']['duration'])
                except (OSError,subprocess.SubprocessError,KeyError,ValueError) as exc:
                    raise ValueError('无法读取音视频。请检查文件是否完整，并安装 FFmpeg/ffprobe。') from exc
                if duration is None or duration <= 0:
                    raise ValueError('音视频时长无效')
                row['end_timestamp'] = (stamp+timedelta(seconds=duration)).isoformat()
                raw['duration_sec'] = duration
            rows = [row]
        else:
            raise ValueError('不支持的文件类型，请选择 XML、ZIP、JSONL、JSON、CSV 或音视频/照片')
        if not rows:
            raise ValueError('文件中没有可导入的记录')
        normalized = [normalize(row) for row in rows]
        dates = set()
        for row in normalized:
            first = parse_time(row['timestamp'])
            last = parse_time(row.get('end_timestamp', row['timestamp']))
            if last > first:
                last -= timedelta(microseconds=1)
            day = first.date()
            while day <= last.date():
                dates.add(day.isoformat())
                day += timedelta(days=1)
        dates = sorted(dates)
        with self.connect() as db:
            added = sum(self.insert(db,row,'personal') for row in normalized)
            db.execute('INSERT INTO imports VALUES (?,?,?,?,?,?,?,?,?)',
                (media_id,digest,original_name,kind,path.stat().st_size,added,datetime.now(TZ).isoformat(),json.dumps(dates),str(path)))
        return {'added':added,'duplicate':False,'dates':dates,'kind':kind}

    def imports(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT id,name,kind,size,count,created,dates FROM imports ORDER BY created DESC')]

    def media(self, media_id):
        with self.connect() as db:
            row = db.execute('SELECT path,kind FROM imports WHERE id=?',(media_id,)).fetchone()
        if not row or row['kind'] not in {'image','video','audio'}:
            raise FileNotFoundError('素材不存在')
        return Path(row['path'])

    def note(self, dataset, payload):
        summary = str(payload.get('text','')).strip()
        if not summary:
            raise ValueError('请填写这段经历')
        row = {'timestamp':payload['timestamp'],'source':'manual_context',
            'modality':'focus_session' if payload.get('activity')=='deep_work' else 'context_note',
            'raw':{'text':summary},'summary':summary,'context':{'activity':payload.get('activity','manual_note')},
            'location':payload.get('location','')}
        if payload.get('end_timestamp'):
            row['end_timestamp'] = payload['end_timestamp']
        if row['modality']=='focus_session' and not payload.get('end_timestamp'):
            raise ValueError('专注记录需要填写结束时间')
        normalized = normalize(row)
        with self.connect() as db:
            self.insert(db,normalized,dataset)
        return normalized

    def checkin(self, dataset, payload):
        day = datetime.fromisoformat(payload['date']).date().isoformat()
        mood = number(payload.get('mood'))
        if mood is not None and (mood not in range(1,6)):
            raise ValueError('状态自评为 1-5')
        note = str(payload.get('note','')).strip()[:2000]
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO checkins VALUES (?,?,?,?)',(dataset,day,mood,note))

    def set_feedback(self, dataset, payload):
        if payload.get('value') not in {'accurate','wrong','watch',''}:
            raise ValueError('反馈无效')
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO feedback VALUES (?,?,?)',(dataset,str(payload['id'])[:120],payload['value']))
