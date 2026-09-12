# AI Watch Project State

## Current Baseline: Local Workbench, 2026-09-12

The project now has a local, persistent workbench rather than a static generated-card viewer.

- Daily view: dated metrics, comparisons, intraday charts, factual summaries, searchable episodes, source evidence, manual context, mood check-ins, and feedback.
- Personal timeline: six metric dimensions, 7/14/30/90-day charts, summaries and reflections, navigation back to individual days.
- Sidebar: editable personal introduction, goals, record-day and source counts.
- Imports: batched XML/ZIP/JSONL/JSON/CSV and photo/audio/video uploads with progress, retry, file/event deduplication, and history.
- Storage: SQLite plus private local uploads; isolated synthetic demo dataset.

See [development and verification notes](docs/WORKBENCH.md) for exact behavior and limitations.

## Run

```powershell
python src/local_app.py
```

Open `http://127.0.0.1:4180`. If the port is occupied, pass a different `--port`.
Python 3.10+ is sufficient for the basic workbench. Audio/video imports require FFmpeg/ffprobe. Frontend dependencies are vendored with their licenses for offline use.

## Ownership

- `src/workbench.py`: event normalization, persistence, daily projections and import processing.
- `src/local_app.py`: loopback-only HTTP APIs, upload limits, static-path/origin checks, attachment/media serving.
- `app/`: browser UI, charts and interaction logic.
- `tests/test_workbench.py`: storage and HTTP integration tests using temporary synthetic data.

## Verification

The 2026-09-12 test run passed 26 tests, including actual ffprobe duration extraction, Apple ZIP import, cross-midnight intervals, source deduplication, persistence, privacy boundaries, media ranges and attachments.
Browser acceptance uses a separate `.runtime/ui-test-data` directory, not personal data. The development record describes the flows and viewports checked.

## Git Sync And Privacy

Commit code, documentation, dependency licenses and synthetic fixtures only. Do not commit:

- `data/private/` or `data/raw/`
- recordings, health exports, local databases or generated personal summaries
- local takeover backups, credentials or `.env`

The existing `PROJECT_STATE.local-takeover-2026-06-03.md` backup belongs to the local workspace and is not part of this change.

Before continuing on another computer, fetch the current development branch, read this file and `docs/WORKBENCH.md`, then run tests. Do not assume private data was transferred with the repository.

## Next Development

- Validate import performance against large, consented real-world health exports.
- Add configurable source selection and source-overlap reconciliation; present values can differ from Apple Health totals.
- Add automatic capture and incremental HealthKit ingestion.
- Add validated local/model-assisted multimedia understanding and personal baselines.
- Add explicit private-data export/restore and deletion workflows.

The [reassessment](docs/REASSESSMENT-2026-09-12.md) remains the long-term proposal. Device integrations and model accuracy are not implemented or validated by this UI milestone. `IMPLEMENTATION.md` and the legacy card/transcription scripts are historical context, not the current browser workflow.
