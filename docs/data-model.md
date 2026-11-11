# tutor 新应用数据模型 v0.1

一个 SQLite：`tutor/data/app.db`。三环共用。

## 组织层（二环）

```
subjects（科目：数二/英二/政治/408）
  └─ goals（目标，对应旧工作台的 task）
       └─ tasks（任务，对应旧工作台的 problem）
            └─ plans（计划，如 2010 真题）
                 └─ papers（整卷/章节）
                      └─ problems（题目）
```

- 四个科目各一个目标；
- 一个计划一份整卷（v1）；
- 题目不允许跳过；
- 计划完成 = 所有题至少结束过一次；
- 计划没有 `next_due` 字段，到期只属于题。

## 题目环（一环）

```
problems
  ├─ type: single / reading_set / comprehensive
  ├─ parent_id：阅读 set→小题，408 大题→小问
  └─ status: new / in_session / scheduled / finished

sessions
  └─ turns
```

- 讲题会话仍由 `session_store` 写 `tutor.sqlite`，同时镜像到 app.db；
- app.db 的 `sessions/turns` 用同一 session id，`problem_id/paper_id` 能对上时关联，旧卷找不到时置空；
- 旧库 61 个会话/38 条消息已回填 app.db；新对话继续双写；
- `problems.status`：打开 session 写 `in_session`；评级/收尾同步 review 后写 `scheduled`；`due` 由 `reviews.due` 查询时推导，不单独持久化。

- 阅读：一篇 + 5 题 = 一个 `reading_set`，只有一个 FSRS；
- 408 大题：一个大题 = 一个 `comprehensive`，小问用 `parent_id`，只有一个 FSRS；
- 数学/选择/分析/翻译：`single`。

## FSRS

```
reviews
  problem_id UNIQUE
  fsrs_json
  due
  user_summary
  suggested / reason
```

- FSRS 只排题；
- 到期只查 `due <= now`；
- 未来日期默认不显示。

## 内部教案

```
lesson_plans
  problem_id PRIMARY KEY
  plan_json（goal/core/path/stuck/finish_check/max_followups）
  created_at / updated_at
```

- 首次对话按题目生成一次，之后复用缓存；
- 只注入 system context 帮教练安排追问，不展示给学生；
- `max_followups` 目前固定 2。

## 英语副产品

```
vocab_items（单词 + 原句 + 所属文章）
writing_tasks（题目/提纲/初稿/反馈/重写/rewrite_due/图表数据 chart_data）
writing_plan_units（写作 → 计划单元，定稿后 finished）
```

- 生词不排 FSRS；
- 写作有独立重写周期；
- 图表作文的 `chart_data` 存类型、标题、标签、系列/数值、单位；批改以它为准，不从残缺题干猜；
- 34 篇写作计入英语二计划：119 阅读/完型 + 34 写作 = 153 单元。

## 时间环（三环）

```
exam_profile（考试日期）
schedule_events（课程/考试/休息）
daily_plans（某天可用时间）
queue_items（科目块/数学块的执行项）
```

- 时间 agent 先分科目，再在数学块内排“到期 → 新题”；
- 其他科目同样到期 → 新题；
- 只提议，不自动改计划；
- 队列项状态 `todo → opened → done`；完成写 `actual_min` 并计入周预算；
- 政治不接内容，只保留 30 分钟 `offline` 自主块，不生成新题。

## 时间模板

```
availability_template（周课表：周一/周四固定课）
weekly_budgets（周配额，周一锁定）
settings（50h 目标、20% 缓冲、80% 上限）
```

当前种子：50h/周 = 数学 15h、408 19h、英二 8h、政治 8h。

## 旧数据

| 旧 | 新 |
| --- | --- |
| `store.tasks` | `goals` |
| `tasks[].problems` | `tasks` |
| `problems[].plans` | `plans` |
| `store.exam` | `exam_profile` |
| 8080 `/api/schedule` | `schedule_events` |
| tutor `result.json` | `papers` / `problems` |
| `reviews.json` | `reviews` |
| `tutor.sqlite` | `sessions` / `turns` |

## 迁移

```bash
cd tutor\server
python migrate.py --tutor
python migrate.py --old-store path\to\store.json
python migrate.py --schedule path\to\schedule.json
python migrate.py --all --old-store ... --schedule ...
```

`--tutor` 已导入 `samples/ingest-*` 的 5 份整卷、85 道题。

## 已经切换的页面

- 首页 `/`：`app.db` 的四科进度、当前到期、今日队列；
- 计划 `/plan.html`：目标/任务/计划/整卷；
- 时间 `/time.html`：可用时间 → 科目块 → 确认。

## 尚未切换

讲题页仍读旧的 `result.json` / `reviews.json` / `tutor.sqlite`。  
但「结束本题」和评级会同步写入 `app.db.reviews`，所以首页/计划/时间的到期会跟着更新。

下一步：
- 目标/任务/计划的新建与旧数据导入；
- 讲题页直接读 `app.db`；
- 时间环周四重算/周日排下周。
