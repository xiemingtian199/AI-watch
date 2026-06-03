# MVP Implementation Guide

## What Is Implemented

- A normalized multimodal event format for Apple and DIY routes.
- Sample Apple-style and DIY-style data for one day.
- A daily review generator that merges all events by timestamp.
- A local heuristic card engine, plus optional OpenAI cloud mode.
- A browser demo with review cards, evidence, timeline, filters, and feedback.

## Apple Route

Use this route to validate whether the review cards feel valuable before building hardware.

Minimum capture sources:

- Apple Watch heart rate from HealthKit export or a small iOS app.
- iPhone motion and location from Shortcuts or a native app.
- Calendar events from iOS calendar export.
- Audio notes, recorded intentionally by the user.
- Photo notes, captured manually when context matters.

Normalize every item into JSONL:

```json
{"timestamp":"2026-06-01T09:18:00+08:00","source":"apple_watch","modality":"heart_rate","raw":{"bpm":118},"summary":"会议准备阶段心率快速升高","confidence":0.91,"location":"office","context":{"route":"apple","activity":"pre-meeting"}}
```

Recommended first Apple workflow:

1. Export heart rate samples once per day.
2. Use iPhone Shortcuts to append manual context notes into a JSON or CSV file.
3. Record only intentional audio notes in week one.
4. Convert all data to JSONL before running `src/generate_cards.py`.

## DIY Route

Use this route to validate always-on multimodal capture and hardware ergonomics.

Prototype parts:

- ESP32-S3 or Raspberry Pi Zero 2 W.
- Small camera module.
- I2S microphone.
- IMU module such as MPU-6050 or ICM-20948.
- Heart-rate module such as MAX30102.
- 1,000-2,000 mAh battery.
- 3D printed badge or wrist enclosure.

Minimum firmware behavior:

- Save events locally first.
- Batch upload by day.
- Every sensor packet includes timestamp, source, modality, confidence, and context route.
- Images should start as low-frame-rate snapshots, not continuous video.
- Audio should start as short clips or event labels, not full-day raw recording.

## Card Rules

Every card must:

- Reference a time range.
- Show at least one piece of evidence.
- Use non-diagnostic wording.
- Include one concrete next action.
- Accept one feedback label: accurate, wrong, mute, or watch.

Avoid:

- "You are anxious" style claims.
- Medical, psychological, or relationship diagnosis.
- Cards that expose third-party private information unnecessarily.

## Weekly Validation

Week 1:

- Run Apple-style capture for three days.
- Generate cards every night.
- Keep cards that feel specific and remove generic cards.

Week 2-3:

- Build DIY capture box or badge.
- Compare Apple-only cards with DIY-enhanced cards.
- Track battery life, heat, missing data, and audio/image usefulness.

Week 4:

- Use one unified card feed for both routes.
- Add 20-30 repeatable card templates only after real patterns appear.

Week 5-6:

- Test with 3-5 trusted efficiency users for seven days.
- Measure daily open rate, feedback rate, accuracy, discomfort, and one remembered insight.

## Privacy Defaults Before External Testing

Do not test with external users until these exist:

- Visible capture indicator.
- Pause capture control.
- Per-day raw data folder.
- One-click delete.
- Export of all user data.
- A written note explaining what is captured and where it is sent.

