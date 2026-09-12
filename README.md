# AI Watch：本地个人生活工作台

把本地健康数据、生活经历和素材汇集到同一个工作台，按天回顾，并沿着时间观察自己的变化。

## 当前能力

- **数据中心**：批量选择或拖入 Apple 健康 XML/ZIP、JSONL/JSON/CSV、照片和音视频；显示进度、错误、重试与同步历史；重复文件不会重复入库。
- **每日复盘**：日期切换、步数/睡眠/心率/专注指标、与前一个有记录日期的变化、日内图表、基于记录的总结、经历搜索与证据详情。
- **人物侧栏**：可编辑姓名、身份、城市、自我介绍、近期关注、步数与睡眠目标；展示记录天数和来源数量。
- **个人时间线**：步数、睡眠、心率、专注、活动能量、自评六个维度，支持 7/14/30/90 天曲线、平均值、每日总结和主观感受；点击数据点或某一天可回到复盘。
- **本地持久化**：SQLite 保存事件、档案、自评、反馈和同步历史；可导出当日 JSON。
- **示例体验**：内置虚构人物和 14 天合成数据，与个人记录独立。所有上传进入“我的记录”。

总结目前是本地事实摘要，不调用云端大模型，不根据心率推断心理状态。照片和音视频可以归档、预览和补充场景备注，尚不自动识别素材内容。

## 快速开始

需要 Python 3.10 或以上。Windows 可双击 `start-local-app.bat`，或运行：

```powershell
.\start-local-app.ps1
```

浏览器打开 [本地工作台](http://127.0.0.1:4180)。只监听 `127.0.0.1`，不对局域网或互联网开放。旧的 `/import.html` 会跳转到新数据中心。

端口已占用时可另选端口：

```powershell
python src/local_app.py --port 4182
```

普通运行不需要 Node.js。图表和图标依赖已随仓库提供，可离线使用。音视频导入另外需要 FFmpeg 的 `ffprobe` 在 PATH 中；照片、结构化数据和示例不需要它。

## 日常使用

1. 打开“数据中心”，选择或拖入记录文件。
2. 照片和音视频填写拍摄/录制开始时间。形如 `2026-09-12 18-30.m4a` 的文件名会预填时间，可修改。
3. 点击“同步记录”，处理完成后会切换到个人资料，并定位最新导入日期。
4. 在“每日复盘”查看数据、补充经历和主观感受；点击记录或“证据”查看原始内容。
5. 在“个人时间线”选择维度与时间范围，回看每天的状态。缺失数据保持空白，不按零值补齐。

“同步”指上传到本机工作台，不是手表实时同步，也不自动在不同电脑之间同步私人数据。

## 记录格式

JSON 支持事件数组、单事件对象或 `{"events": [...]}`；JSONL 每行一条事件。CSV 可在数据中心下载模板，也可使用合成测试文件 `tests/fixtures/workbench.csv`。

```json
{
  "timestamp": "2026-09-12T14:00:00+08:00",
  "end_timestamp": "2026-09-12T15:00:00+08:00",
  "source": "manual_context",
  "modality": "focus_session",
  "raw": {},
  "summary": "整理项目方案",
  "context": {"activity": "deep_work"}
}
```

时间必须有时区，工作台统一按 UTC+08:00 划分日期。

| modality | raw | 含义 |
| --- | --- | --- |
| `heart_rate` | `{"bpm":72}` | 心率样本 |
| `step_count` | `{"value":1200,"unit":"count"}` | 本条样本增量，不是全天累计快照 |
| `active_energy` | `{"value":120,"unit":"kcal"}` | 样本能量，也支持 `kJ` |
| `sleep_analysis` | `{"value":"HKCategoryValueSleepAnalysisAsleep"}` | 需要起止时间 |
| `focus_session` | `{}` 或 `{"duration_min":60}` | 需要结束时间或明确分钟数 |
| `context_note` | `{"text":"散步"}` | 生活场景，可配合 summary |
| `mood` | `{"value":4}` | 1-5 的主观自评 |

计算口径、兼容性和接口详见 [工作台开发与验收记录](docs/WORKBENCH.md)。

## 开发与测试

```powershell
python -m unittest discover -s tests -p test_*.py -v
npm ci
npm run check
npm run vendor
```

Python 测试使用临时目录，不接触个人数据。`npm ci` 只用于前端依赖维护；`vendor` 重建离线图表和图标资源。

## 隐私与备份

- 数据库位于 `data/private/workbench.sqlite3`，上传文件位于 `data/private/uploads/`。
- 个人数据、生成结果、转写、本地依赖及测试运行目录被 Git 忽略。
- GitHub 只同步代码、文档、合法公开素材和明确标注的合成样例。
- 当日导出是事件与摘要 JSON，不是包含所有素材和人物设置的完整备份。完整备份请先停止服务，再通过私密加密渠道备份整个 `data/private` 目录。
- 数据当前没有应用层加密或账户登录，不适合共享账户/多人服务器。请依靠系统账户权限和磁盘加密保护本机。

## 项目结构

```text
app/                    工作台页面、离线图表/图标库及示例图片
src/local_app.py         本地 HTTP 接口与上传服务
src/workbench.py         SQLite、导入和每日/跨日统计
src/demo_data.py         独立的 14 天合成数据
src/convert_apple_health.py  Apple 健康数据转换
src/transcribe_audio.py  可选的旧版命令行转写工具
src/generate_cards.py    旧版规则卡片生成器（不驱动当前页面）
tests/                  自动化测试与合成 CSV
docs/WORKBENCH.md        设计决策、计算口径、接口与验收记录
```

## 后续方向

自动设备采集、HealthKit 增量同步、可靠的音视频理解、个人基线和可验证的多模态洞察仍在后续路线中。旧命令行转换和转写工具保留，但不会自动触发当前页面分析。

详见 [项目重审与优化路线](docs/REASSESSMENT-2026-09-12.md) 和 [当前交接状态](PROJECT_STATE.md)。本项目不能用于医学或心理诊断。
