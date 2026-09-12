import hashlib
import http.client
import json
import shutil
import sys
import tempfile
import threading
import unittest
import wave
import zipfile
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from local_app import create_server
from workbench import Workbench, normalize


def event(modality='step_count', value=100, stamp='2026-09-11T08:00:00+08:00', **extra):
    return {'timestamp': stamp, 'modality': modality, 'raw': {'value': value}, **extra}


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = Workbench(self.root)

    def put(self, rows, name='events.json'):
        path = self.root / name
        path.write_text(json.dumps(rows), encoding='utf-8')
        return self.store.import_file(path, name, hashlib.sha256(path.read_bytes()).hexdigest())

    def test_demo_is_deterministic_and_separate(self):
        demo = self.store.overview('demo')
        self.assertEqual(len(demo['days']), 14)
        self.assertEqual(demo['eventCount'], 476)
        self.assertEqual(self.store.overview('personal')['eventCount'], 0)

    def test_csv_upload_daily_trend_and_persistence(self):
        path = ROOT / 'tests/fixtures/workbench.csv'
        result = self.store.import_file(path, path.name, hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(result['added'], 6)
        self.assertEqual(result['dates'], ['2026-09-10', '2026-09-11'])
        days = Workbench(self.root).overview('personal')['days']
        self.assertEqual([d['metrics']['steps'] for d in days], [3000, 5000])
        self.assertEqual([d['metrics']['focus'] for d in days], [60, 90])
        self.assertIn('Second project session', self.store.daily('personal', '2026-09-11')['episodes'][0]['summary'])

    def test_file_and_event_deduplication(self):
        self.assertEqual(self.put([event()])['added'], 1)
        self.assertTrue(self.put([event()])['duplicate'])
        self.assertEqual(self.put([event(), event()], 'other.json')['added'], 0)
        self.assertEqual(self.store.overview('personal')['eventCount'], 1)

    def test_invalid_batch_is_atomic(self):
        with self.assertRaises(ValueError):
            self.put([event(), {'modality': 'step_count'}])
        self.assertEqual(self.store.overview('personal')['eventCount'], 0)
        self.assertEqual(self.store.imports(), [])

    def test_jsonl_import(self):
        path = self.root / 'events.jsonl'
        path.write_text(json.dumps(event())+'\n'+json.dumps(event(value=25))+'\n', encoding='utf-8')
        self.assertEqual(self.store.import_file(path, path.name, 'jsonl')['added'], 2)

    @unittest.skipUnless(shutil.which('ffprobe'), 'FFmpeg is optional for audio/video imports')
    def test_audio_duration_and_media_reference(self):
        path = self.root / '2026-09-11 18-00.wav'
        with wave.open(str(path), 'wb') as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(8000)
            audio.writeframes(b'\x00\x00'*8000)
        result = self.store.import_file(path, path.name, 'audio')
        self.assertEqual(result['kind'], 'audio')
        record = self.store.daily('personal', '2026-09-11')['events'][0]
        self.assertEqual(record['raw']['duration_sec'], 1)
        self.assertEqual(record['end_timestamp'], '2026-09-11T18:00:01+08:00')
        self.assertEqual(self.store.media(record['media_id']), path)

    def test_nonfinite_nested_values_rejected(self):
        for bad in (float('nan'), float('inf'), float('-inf')):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                normalize(event('context_note', raw={'nested': [bad]}))

    def test_invalid_cumulative_and_mood_rejected(self):
        for row in (event(value=-1), event(value='NaN'), event('mood', 6), event('mood', True)):
            with self.subTest(row=row), self.assertRaises(ValueError):
                normalize(row)

    def test_timestamp_validation(self):
        for row in (event(stamp='2026-09-11T08:00:00'), event(end_timestamp='2026-09-10T08:00:00+08:00'),
                    event(end_timestamp='2028-09-11T08:00:00+08:00')):
            with self.subTest(row=row), self.assertRaises(ValueError):
                normalize(row)

    def test_timezone_and_midnight_boundary(self):
        self.put([event(stamp='2026-09-10T16:00:00Z')])
        self.assertEqual(self.store.daily('personal', '2026-09-11')['metrics']['steps'], 100)
        self.assertIsNone(self.store.daily('personal', '2026-09-10')['metrics']['steps'])

    def test_cumulative_interval_apportioned_across_days(self):
        result = self.put([event(value=200, stamp='2026-09-10T23:00:00+08:00', end_timestamp='2026-09-11T01:00:00+08:00')])
        self.assertEqual(len(result['dates']), 2)
        for day in result['dates']:
            report = self.store.daily('personal', day)
            self.assertEqual(report['metrics']['steps'], 100)
            self.assertEqual(sum(p['y'] for p in report['stepSeries']), 100)

    def test_single_source_cumulative_totals(self):
        self.put([event(source='watch'), event(source='phone', value=95),
                  event(source='watch', value=20, stamp='2026-09-11T10:00:00+08:00'),
                  event(source='watch', summary='same sample with a changed note')])
        report = self.store.daily('personal', '2026-09-11')
        self.assertEqual(report['metrics']['steps'], 120)
        self.assertEqual(report['aggregation']['step_count']['source'], 'watch')
        self.assertEqual(sum(p['y'] for p in report['stepSeries']), 120)
        self.assertIn('watch', report['summary'])

    def test_kilojoules_to_kilocalories(self):
        self.put([event('active_energy', raw={'value':418.4, 'unit':'kJ'})])
        self.assertEqual(self.store.daily('personal', '2026-09-11')['metrics']['energy'], 100)

    def test_sleep_union_and_in_bed_excluded(self):
        self.put([event('sleep_analysis', 'HKCategoryValueSleepAnalysisAsleepCore', '2026-09-10T23:00:00+08:00', end_timestamp='2026-09-11T07:00:00+08:00'),
                  event('sleep_analysis', 'HKCategoryValueSleepAnalysisAsleepDeep', '2026-09-11T01:00:00+08:00', end_timestamp='2026-09-11T02:00:00+08:00'),
                  event('sleep_analysis', 'HKCategoryValueSleepAnalysisInBed', '2026-09-11T07:00:00+08:00', end_timestamp='2026-09-11T08:00:00+08:00')])
        self.assertEqual(self.store.daily('personal', '2026-09-11')['metrics']['sleep'], 7)
        self.assertEqual(self.store.daily('personal', '2026-09-10')['metrics']['sleep'], 1)

    def test_focus_duration_only_is_indexed_on_both_days(self):
        self.put([event('focus_session', stamp='2026-09-10T23:30:00+08:00', raw={'duration_min':90}, summary='Late project work')])
        self.assertEqual(self.store.daily('personal', '2026-09-10')['metrics']['focus'], 30)
        self.assertEqual(self.store.daily('personal', '2026-09-11')['metrics']['focus'], 60)

    def test_interval_ending_midnight_does_not_add_empty_day(self):
        result = self.put([event('focus_session', stamp='2026-09-10T23:00:00+08:00', end_timestamp='2026-09-11T00:00:00+08:00')])
        self.assertEqual(result['dates'], ['2026-09-10'])
        self.assertEqual(self.store.daily('personal', '2026-09-11')['eventCount'], 0)

    def test_missing_values_stay_null(self):
        self.put([event('context_note', summary='A quiet afternoon')])
        self.assertTrue(all(v is None for v in self.store.daily('personal', '2026-09-11')['metrics'].values()))

    def test_profile_checkin_and_feedback_persist_and_are_isolated(self):
        self.store.save_profile('personal', {'name':'Test Person', 'bio':'A test profile', 'stepGoal':9000})
        self.store.checkin('personal', {'date':'2026-09-11', 'mood':5, 'note':'Test reflection'})
        self.store.set_feedback('personal', {'id':'2026-09-11:heart', 'value':'accurate'})
        saved = Workbench(self.root)
        report = saved.daily('personal', '2026-09-11')
        self.assertEqual(saved.profile('personal')['stepGoal'], 9000)
        self.assertEqual(report['metrics']['mood'], 5)
        self.assertEqual(report['checkin']['note'], 'Test reflection')
        self.assertEqual(report['feedback']['2026-09-11:heart'], 'accurate')
        self.assertNotIn('2026-09-11:heart', saved.daily('demo', '2026-09-11')['feedback'])
        self.assertIsNone(saved.daily('personal', '2026-09-10')['metrics']['mood'])
        self.assertEqual(len(saved.overview('personal')['days']), 1)

    def test_schedule_is_not_presented_as_completed_experience(self):
        self.put([event('schedule', summary='Planned meeting')])
        report = self.store.daily('personal', '2026-09-11')
        self.assertEqual(report['episodes'][0]['kind'], 'plan')
        self.assertEqual(report['keywords'], [])

    def test_legacy_malformed_file_does_not_break_startup(self):
        folder = self.root / 'legacy'
        folder.mkdir()
        (folder / 'broken.jsonl').write_text('not json', encoding='utf-8')
        (folder / 'valid.jsonl').write_text(json.dumps(event()), encoding='utf-8')
        migrated = Workbench(folder).overview('personal')
        self.assertEqual(migrated['eventCount'], 1)
        self.assertEqual(len(migrated['migrationWarnings']), 1)

    def test_apple_xml_and_zip_preserve_intervals_and_deduplicate(self):
        xml = '<HealthData><Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="Watch" startDate="2026-09-10 23:00:00 +0800" endDate="2026-09-11 07:00:00 +0800" value="HKCategoryValueSleepAnalysisAsleep"/></HealthData>'
        path = self.root / 'export.xml'
        path.write_text(xml, encoding='utf-8')
        self.assertEqual(self.store.import_file(path, path.name, 'xml')['added'], 1)
        archive = self.root / 'export.zip'
        with zipfile.ZipFile(archive, 'w') as out:
            out.writestr('apple_health_export/export.xml', xml)
        self.assertEqual(self.store.import_file(archive, archive.name, 'zip')['added'], 0)
        report = self.store.daily('personal', '2026-09-11')
        self.assertEqual(report['metrics']['sleep'], 7)
        self.assertEqual(report['events'][0]['context']['activity'], 'unknown')


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = create_server(0, self.temp.name)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join()
        self.temp.cleanup()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        try:
            connection.request(method, path, body, headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_upload_to_api_daily_and_overview(self):
        status, _, raw = self.request('POST', '/api/upload', (ROOT/'tests/fixtures/workbench.csv').read_bytes(), {'X-Filename':'workbench.csv'})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)['added'], 6)
        status, _, raw = self.request('GET', '/api/day?date=2026-09-11')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)['metrics']['steps'], 5000)
        _, _, raw = self.request('GET', '/api/overview')
        self.assertEqual(len(json.loads(raw)['days']), 2)

    def test_failed_upload_leaves_no_partial_file(self):
        status, _, raw = self.request('POST', '/api/upload', b'[{"invalid":true}]', {'X-Filename':'bad.json'})
        self.assertEqual(status, 400)
        self.assertIn('error', json.loads(raw))
        self.assertEqual(list((Path(self.temp.name)/'uploads').iterdir()), [])

    def test_origin_host_and_static_path_protection(self):
        for headers in ({'Origin':'https://example.com'}, {'Host':'evil.test'}):
            self.assertEqual(self.request('GET', '/api/overview', headers=headers)[0], 403)
        self.assertEqual(self.request('GET', '/%2e%2e/src/workbench.py')[0], 404)
        self.assertEqual(self.request('GET', '/api/day?dataset=other&date=2026-09-11')[0], 400)

    def test_static_assets_and_export(self):
        for path in ('/', '/app.js', '/vendor/chart.umd.js', '/vendor/lucide.js', '/assets/park.jpg', '/api/template', '/api/export?dataset=demo&date=2026-09-11'):
            status, headers, body = self.request('GET', path)
            self.assertEqual(status, 200, path)
            self.assertGreater(len(body), 10)
            self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
            if path.startswith('/api/export'):
                self.assertIn('attachment;', headers['Content-Disposition'])
                self.assertEqual(json.loads(body)['date'], '2026-09-11')

    def test_media_upload_and_range_playback(self):
        data = (ROOT/'app/assets/park.jpg').read_bytes()
        headers = {'X-Filename':quote('scene.jpg'), 'X-Start':quote('2026-09-11T18:00:00+08:00')}
        self.assertEqual(self.request('POST', '/api/upload', data, headers)[0], 200)
        _, _, raw = self.request('GET', '/api/imports')
        media_id = json.loads(raw)['imports'][0]['id']
        status, headers, body = self.request('GET', '/api/media/'+media_id, headers={'Range':'bytes=10-19'})
        self.assertEqual(status, 206)
        self.assertEqual(body, data[10:20])
        self.assertTrue(headers['Content-Range'].startswith('bytes 10-19/'))
        self.assertEqual(self.request('GET', '/api/media/'+media_id, headers={'Range':'bytes=99999999-'})[0], 416)


if __name__ == '__main__':
    unittest.main()
