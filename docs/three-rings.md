# tutor 三环框架 v0.2

> 这是一个新应用，不是旧学习工作台的补丁。  
> 一个端口、一个 SQLite、三个环。

## 0. 一句话

```
第一环：这道题讲透
第二环：材料在推进
第三环：时间和科目没崩
```

三环不是三个 App，是同一套数据的三种时间尺度。

---

## 1. 设计原则

1. **整题优先**：题目是学习单位，不把知识点背诵当主粮。
2. **大脑拥有解释权**：agent 只提问、记录、排程，不替用户总结。
3. **评级由用户定**：agent 可以给建议和理由，但不能自动写评级。
4. **计划只记事实**：讲过、到期、耗时；不生成“掌握度分数”。
5. **到期只属于题**：计划没有 `next_due`，页面只显示当前到期题。
6. **课程是补丁**：做题卡住才看课/书，不统计课程进度。
7. **数据分开职责**：材料/题目/会话/FSRS 在 tutor 库；时间分配在时间环表。
8. **只提议不越权**：时间 agent 可以重排当天，但不自动改计划。

---

## 2. 总图

```
┌─────────────────────────────────────────────┐
│ 第三环：时间管理（月 / 周 / 日）             │
│ 考试倒排 → 周配额 → 每日科目分配             │
│        ↓ 科目块                             │
├─────────────────────────────────────────────┤
│ 第二环：计划（材料推进）                     │
│ 目标 → 任务 → 计划 → 整卷/章节 → 题目        │
│        ↓ 下一题                             │
├─────────────────────────────────────────────┤
│ 第一环：题目（讲透）                         │
│ 讲题 → 卡住补 → 用户总结 → 启发补缺 → 评级   │
│        ↑ 回写事实：到期/耗时/评级            │
└─────────────────────────────────────────────┘
```

---

## 3. 第一环：题目环

### 3.1 核心问题

> 这道题，我能不能不看提示，从头到尾讲顺？

### 3.2 单位

一道题 / 一个题集。

- 数学：一道题；
- 英语阅读：一篇 + 5 题 = 一个 problem set；
- 英语完型/新题型：一篇 = 一个 set；
- 英语翻译：一篇/5 句 = 一个 problem；
- 政治选择/分析：一道题；
- 408 选择：一道题；
- 408 大题：一个大题 + 小问 = 一个 problem，不拆 FSRS；
- 写作：一个 writing task，不走题目 FSRS。

### 3.3 流程

```
选题
  ↓
你先讲，agent 不打断
  ↓
卡住 / 矛盾 / 关键步骤含糊
  ├─ 缺概念 → 你翻书/看对应课的一小段 → 回题
  ├─ 缺方法 → 最小提示 → 回题
  ├─ 计算错 → 定位错误 → 回题
  └─ 题意不清 → 复述题意 → 回题
  ↓
讲完，点「结束本题」
  ↓
服务端生成内部 rubric（不显示、不返回、不存档）
  ↓
你先用自己的话总结
  ↓
rubric 对比：有缺口 → 一次一个启发式问题，最多 2 次
  ↓
保存用户自己的总结
  ↓
评级建议 + 理由，用户确认
  ↓
FSRS 排下次整题复述
```

### 3.4 Agent 边界

做：

- 听、追问、指方向；
- 判断卡点类型；
- 给最小提示；
- 记录 session、耗时、评级、到期；
- 到点提醒复述。

不做：

- 不自动展示摘要；
- 不生成知识卡；
- 不建知识库；
- 不自动打标签；
- 不判断掌握度；
- 不替用户总结；
- 不直接给完整解法。

### 3.5 状态机

```
new
  ↓ 打开 session
in_session
  ↓ 结束本题 + 用户评级
scheduled（有 due）
  ↓ due <= now
due
  ↓ 整题复述 + 再评级
scheduled（新 due）
```

### 3.6 数据

```
sessions / turns
reviews（problem_id UNIQUE, fsrs_json, due, user_summary）
problem_progress（first_finished_at）
```

### 3.7 验收

- 刷新页面能恢复对话；
- 收尾不显示 rubric；
- 用户总结不被 AI 改写；
- 评级不自动生效；
- 到期题只出现当前 due。

---

## 4. 第二环：计划环

### 4.1 核心问题

> 这份材料推进到哪了？下一题是哪题？

### 4.2 层级

```
目标（4 个）
  ├─ 数二
  ├─ 英二
  ├─ 政治
  └─ 408
       └─ 任务
            └─ 计划
                 └─ 整卷/章节
                      └─ 题目/题集
```

一个计划一份整卷（v1）。  
一个整卷只属于一个计划。  
一道题只属于一个整卷。

### 4.3 计划状态

```
未开始
  ↓ 第一题开始
进行中
  ↓ 所有题至少结束过一次
第一遍完成
  ↓ 用户归档
已归档
```

- 复述周期独立，不影响计划状态；
- 不允许跳过题目；
- “第一遍完成”= 所有 `plan_units` 完成（题目单元 = 至少结束过一次）；
- “第一遍完成”不等于“掌握”。

### 4.4 题目状态

```
new → in_session → scheduled → due → scheduled
```

计划页只显示：

```
未讲 / 已讲 / 当前到期
```

不显示：

- 未来到期日期；
- 掌握度百分比；
- AI 生成的计划总结。

### 4.5 科目建模

| 科目 | 单元 | 特殊规则 |
| --- | --- | --- |
| 数二 | 一道题 | 标准 single |
| 英二阅读 | 一篇 + 5 题 | 一个 reading_set，一个 FSRS |
| 英二完型 | 一篇 | 一个 set |
| 英二新题型 | 一组 | 一个 set |
| 英二翻译 | 一篇/5 句 | 一个 problem |
| 英二写作 | 一篇 | writing_task，有重写周期 |
| 政治选择 | 一道题 | single |
| 政治分析 | 一道题 | single |
| 408 选择 | 一道题 | single |
| 408 大题 | 一个大题 + 小问 | comprehensive，parent_id |

### 4.6 英语阅读 + 生词

```
限时做题
  ↓
tutor 逐题追问：证据、paraphrase、干扰项
  ↓
整篇复述
  ↓
生词回收：用户标记 + tutor 候选，每篇 3~5 个
  ↓
存：单词 + 原句 + 段落 + 所属文章
  ↓
FSRS 排整篇
```

生词不排 FSRS；下次阅读前看原句猜词义。

### 4.7 写作

```
题目 → 提纲 → 初稿 → tutor 反馈 → 重写 → 定稿
```

- 写作任务单独存；
- 重写有 `rewrite_due`；
- 不混进题目 FSRS。

### 4.8 数据

```
subjects / goals / tasks / plans / papers / problems
vocab_items / writing_tasks
```

### 4.9 验收

- 目标/任务/计划能挂载整卷；
- 计划页只显示当前到期数；
- 所有科目都能打开 tutor；
- 阅读/408 大题不被拆成多个 FSRS。

### 4.10 下一题怎么选

默认顺序：

```
1. 当前到期题（按 due 最早的先）
2. 本计划未讲题，按整卷顺序
3. 用户手动点选的其他题
```

- 不允许“跳过”；
- 用户可以打乱顺序，但计划完成仍要求所有题都结束过；
- 没有“下一题”时，计划停在“进行中”，不自动归档。

### 4.11 剩余量从哪来

自动倒排需要每科的“可完成单元”：

```
plan_units
  id
  plan_id
  title
  kind: paper / chapter / passage / question_set / writing
  estimate_min
  status: new / done
```

- 有整卷的计划：单元可由 `papers/problems` 派生；
- 政治章节/背诵：用 `chapter` 单元；
- 英语写作：用 `writing_tasks`，也可映射成 unit；
- 没有单元清单的计划，时间环只能用手动周配额，不能自动倒排。

> 当前 `app.db` 还没有 `plan_units` 表；这是自动倒排的前置条件。

### 4.12 当前计划与顺序

一个任务下可能有多个计划（2013~2026 真题）。时间环只排“当前计划”，不替用户选年份。

```
task.active_plan_id
```

- 默认：该任务下年份最早、未完成的计划；
- 用户可切换当前计划；
- 到期题不受当前计划限制，任何计划到期都要复述；
- 计划完成不自动跳到下一份，用户确认后才切。

没有 `active_plan_id` 时，计划页显示“选择当前计划”，时间环不猜。

### 4.13 计划单元的粒度

同一个计划里，单元必须统一，否则倒排会重复计算。

| 计划类型 | 单元 | 不再重复算 |
| --- | --- | --- |
| 数学整卷 | 一道题 | 不再按“套”算一遍 |
| 英语阅读 | 一篇 set | 5 个小题不单独成单元 |
| 英语完型/新题型 | 一篇 set | 不拆空 |
| 英语翻译 | 一篇/5 句 | 不按句拆 |
| 英语写作 | 一篇 writing_task | 不再算进阅读 |
| 政治章节 | 一章 | 章内题不重复算 |
| 政治肖1000 | 一章的题组 | 不按 1000 道逐题排 |
| 408 选择 | 一道题 | 不按套重复 |
| 408 大题 | 一个大题 | 小问不单独成单元 |

原则：

> 一个 FSRS 对象 = 一个倒排单元。  
> 不能既按套算、又按题算。

---

## 5. 第三环：时间环

### 5.1 核心问题

> 以我现在的时间和精力，今天/本周怎么排才不崩？

### 5.2 三层

```
3A 备考规划（月）
  考试日期 + 四科材料剩余量 + 每周可用小时
  → 周配额

3B 周预算（周）
  周一锁定
  周四重算本周剩余
  周日算下周

3C 每日科目分配（日）
  今天可用分钟 → 2~3 科
  → 每科块：到期复述 → 新题
```

### 5.3 输入

- 考试日期：2026-12-19；
- 四科材料/题量；
- 每科当前计划（`task.active_plan_id`）；
- 阶段目标（`phase_goals`）；
- 每周目标：50h，且不超过 `weekly_free × 80%`；
- 固定课表：
  - 周一 09:55–11:20 移动物联网 SB403；
  - 周一 14:40–16:05 自然语言处理 信息楼332；
  - 周四 09:55–11:20 商务智能综合实训 SD104；
  - 周四 13:00–14:25 商务智能综合实训 SB506；
  - 周四 14:40–16:05 人工智能伦理规范讲座 SB103；
- 正常作息 08:00–24:00；调试模式 12:00 起；
- 每天默认周模板，问“今天按这个吗”。

### 5.4 输出

不是排满的表，是三种队列：

```
最低：只做到期
目标：到期 + 阶段目标
冲刺：到期 + 阶段目标 + 加练
```

默认目标；时间不够降最低。

### 5.5 分配规则

1. 到期优先；
2. 每科有周最低；
3. 每天 2~3 科，不四科全上；
4. 到期预估 > 当天可用 60% → 当天只做到期，不推新题；
5. 每天最多 80% 容量，留 20% 缓冲；
6. 数学/408 是重科，尽量每天有；
7. 周四课满，只排轻量复述/政治；
8. 调试日降到 5~7h，不排早上的数学。

### 5.6 周四 / 周日

- 周一锁定本周配额；
- **周四晚**：重算周五~周日剩余，不改周一到周三；
- **周日晚**：算下周配额；
- 落下的任务不滚债，不自动堆到明天。

### 5.7 落下任务的价值评估

三档：

```
必补：到期、阶段截止、弱科核心
可补：正常新题
不补：额外加练、已超前、低收益重复
```

你确认才补。

### 5.8 课程不是计划项

```
做题 → 卡住 → 看对应课/书 5~20 分钟 → 回题
```

- 不统计课程总时长；
- 不设课程完成度；
- 不排“看完基础课”；
- 课程时间算在这道题里。

### 5.9 数据

```
exam_profile
schedule_events
availability_template
availability_exceptions
phase_goals
weekly_budgets
settings（50h / 20% buffer / 80% cap）
plan_units（自动倒排的剩余量）
daily_plans / queue_items（todo/opened/done/carried + actual_min）
```

### 5.10 验收

- 输入 90 分钟，能出 2~3 科块；
- 有到期时先排复述；
- 草稿必须确认后才算今天执行队列；
- 周四/周日重算可手动触发；
- 不自动改计划。

### 5.11 容量公式（避免 80% 和 20% 重复扣）

每天：

```
free_min      = 课表/作息算出的空闲分钟，或用户手填
usable_min    = floor(free_min × 0.8)
buffer_min    = free_min - usable_min
```

- `usable_min` 是排程上限，已经包含 20% 缓冲；
- 不再从 `usable_min` 里再扣一次 20%；
- 当天所有科目块之和 ≤ `usable_min`；
- 剩余额度显示为“缓冲”，不强行塞题。

周：

```
weekly_target = 3000 分钟（50h）
weekly_planned = Σ subject quota
weekly_planned ≤ weekly_target
```

### 5.12 自动倒排

```
剩余单元 = Σ(plan_units where status=new)
剩余小时 = 剩余单元 × 单元预估 / 60
复习负载 ≈ 当前到期数 × 8 分钟 / 60 × 1.3
需求 = 剩余小时 + 复习负载
可用周数 = max(1, (考试日期 - 今天) / 7)
每周需求 = 需求 / 可用周数
```

判断：

- `每周需求 ≤ 50h`：按科目权重分配；
- `每周需求 > 50h`：不硬排，输出缺口和三个选项：

```
A. 每周加时间
B. 降范围
C. 延后阶段
```

- 分配时给每科一个**最低量**，防止某科整周消失；
- 单元预估先用默认值，之后用实际中位数校准。

### 5.13 到期溢出

如果到期题装不下：

```
1. 当天只做到期，不推新题；
2. 按 due 最早的先做；
3. 只装到 usable_min 为止；
4. 剩余到期题保留在 due 列表，不隐藏；
5. 不把“没做完”标成完成。
```

如果四科同时有到期，但每天只排 2~3 科：

- 先选 due 最早、overdue 最久的科；
- 其他科的到期保留，第二天优先；
- 不为了“清空”硬塞四科。

### 5.14 执行闭环（当前最大缺口）

时间环不能只出队列，还要知道做完没有。

```
queue_items.status:
  todo → opened → done
                ↘ carried（当天没做，顺延）
```

- 点「去复述/去讲题」→ `opened`；
- 第一环结束本题 → `done`，写 `actual_min`；
- 没做 → `carried`，不自动变债务；
- 用户做队列外的题 → 记 `extra`，不破坏当天队列。

`actual_min` 口径：

- 优先用 session 开始/结束时间；
- 含看课/翻书时间；
- 超过 2 小时按 2 小时封顶，避免挂机污染；
- 允许手动改。

### 5.15 预估校准

初始默认：

| 单元 | 默认 |
| --- | --- |
| 数二一道题 | 25 分钟 |
| 408 选择题 | 5 分钟 |
| 408 大题 | 30 分钟 |
| 英语阅读 set | 40 分钟 |
| 英语完型/新题型 | 30 分钟 |
| 英语翻译 | 25 分钟 |
| 政治选择题 | 2 分钟 |
| 政治分析题 | 20 分钟 |

校准：

- 每科至少 3 个实际样本后，用中位数替换默认；
- 不按单次异常值改；
- 模型不参与算时间。

### 5.16 周四 / 周日算法

周一：

```
锁定本周 quotas = [数学 15h, 408 19h, 英语 8h, 政治 8h]
```

周四晚：

```
本周剩余天数 = 周五~周日
每科剩余 = max(0, planned - actual)
按必补/可补/不补重排剩余
不改变周一到周三已发生的事实
不增加本周总配额
```

周日晚：

```
用最新剩余单元重算下周需求
下周 quotas = min(需求, 50h)
若需求 > 50h，给出降范围选项
```

### 5.17 调试模式

```
正常：08:00–24:00
调试：12:00–次日 02:00，目标 5~7h
```

- 调试日不排早上数学；
- 只保到期 + 一科新题；
- 不补前一天欠的账；
- 连续调试两天，第三天默认降量。

### 5.18 失败模式

| 失败 | 处理 |
| --- | --- |
| 每天排满 | 80% 上限 + 缓冲，禁止加塞 |
| 预估过于乐观 | 中位数校准，不按模型猜 |
| 到期雪崩 | 只做到期，按 overdue 排，剩余保留 |
| 一天没学 | 不滚债，周内选择性补 |
| 四科都想抓 | 每天 2~3 科，周最低保底 |
| 计划没单元 | 不自动倒排，退回手动配额 |
| 课程看不完 | 课程不是进度条，卡住才看 |
| 计划卡住 | 不跳过、不自动归档，停在进行中 |

---

### 5.19 50h 与 80% 的关系

50h 是目标，不是 entitlement。

```
weekly_free   = 周模板空闲分钟
weekly_target = min(3000, floor(weekly_free × 0.8))
```

- 空闲 61h → 上限约 48.8h；
- 空闲 40h → 上限 32h，不硬凑 50h；
- 考试周、调课、项目调试都会改变 `weekly_free`；
- 周配额不能超过 `weekly_target`。

### 5.20 科目公平与上限

每天 2~3 科，但要有约束，避免一科吃掉全部：

```
单科单日 ≤ usable × 60%
每科每周 ≥ 周最低
到期-only 日可暂停周最低
```

- 数学/408 是重科，优先，但不保证每天都有；
- 英语/政治靠周最低保底，不靠每天平均；
- 一科到期爆量时，先保它的到期，其他科只保最低；
- 不把四科都排成“每天一点点”。

### 5.21 确认、解锁与重排

```
draft → confirmed → locked
```

- `draft`：可重新生成；
- `confirmed`：今天队列锁定，自动排程不再覆盖；
- 用户点「解锁重排」→ 回到 draft，保留旧版本为 revision；
- 时间 agent 不自动解锁，不偷偷重排；
- 已完成的 queue item 不因重排丢失。

### 5.22 每日例外、休息与调课

```
availability_exceptions(date, start_min, end_min, type)
type: rest / class / exam / other
```

- 半天休息写进 exceptions，时间环不排；
- 临时调课/考试周覆盖周模板；
- 调试模式是例外，不是长期模板；
- 休息不补债，不因休息扣“学习时长”。

### 5.23 到期不只是 FSRS

当前到期包含两类：

```
1. FSRS problem due
2. writing rewrite_due
```

- 计划页的“到期 N”只算 FSRS 题；
- 时间页的“到期优先”把写作重写也算进去；
- 复述预估按题型，不统一 8 分钟：

| 类型 | 复述预估 |
| --- | --- |
| 数学单题 | 8~15 |
| 英语阅读 set | 20~25 |
| 英语完型/新题型 | 15~20 |
| 政治选择 | 2~3 |
| 政治分析 | 15~20 |
| 408 选择 | 3~5 |
| 408 大题 | 20~30 |

- 生词不是 due，只做阅读前 2~3 分钟回顾；
- 写作重写不是 FSRS，但占用当天到期额度。

### 5.24 阶段里程碑

自动倒排需要阶段，不然 7.7 周只有一个总目标。

```
phase_goals
  id
  subject_id
  name
  start_date
  end_date
  target_units
```

建议三阶段（可改）：

```
P1 10/26–11/29：四科真题第一遍 + 卡住补基础
P2 11/30–12/13：套卷/错题/写作/政治背诵
P3 12/14–12/19：模拟 + 错题 + 背诵，不排新内容
```

- 阶段目标由用户确认，agent 不自动编教材范围；
- 周配额在阶段内按剩余量倒排；
- 阶段切换不追溯改已完成记录。

### 5.25 队列 ↔ session 的映射

```
sessions.queue_item_id
```

- 从时间页点「去复述/去讲题」→ 带 `queue_item_id` 打开 tutor；
- 第一环结束本题 → 对应 queue item 标 `done`；
- 从计划页直接打开 → 若有同 `ref_id` 的 opened item，复用；否则记 `extra`；
- `actual_min = min(session 时长, 120)`，可手改；
- 同一题重复打开，不重复生成 queue item。



| 事件 | 谁写 | 谁读 |
| --- | --- | --- |
| 题目结束 + 评级 | 第一环 | 第二环进度、第三环实际用时 |
| FSRS due | 第一环 | 第二环到期数、第三环容量 |
| 计划剩余/顺序 | 第二环 | 第三环配额、下一题 |
| 当前计划切换 | 第二环 | 第三环科目块内选题 |
| 每日科目块 | 第三环 | 第二环/第一环打开题目 |
| 队列项状态 | 第一环结束/第三环确认 | 首页/时间页 |
| 实际用时 | 第一环 session | 第三环校准预估 |
| 写作重写 due | 第二环 writing_tasks | 第三环到期额度 |
| 周四/周日重算 | 第三环 | 更新周配额/日分配 |

---

## 7. 应用与数据架构

- 一个应用，单端口 `127.0.0.1:8793`；
- 不做 8080 网关；
- SQLite：`tutor/data/app.db`；
- 表结构：`tutor/docs/data-model.md`；
- 旧工作台数据一次性迁移，不运行时依赖；
- 已导入旧工作台：4 个目标 / 7 个任务 / 4 个计划；
- 现有整卷：`2013 数二真题`，23 题；
- 5 份早期样本卷已删除，不再作为测试数据。

### 页面

```
/            首页
/plan.html   计划
/time.html   时间
/talk.html   讲题
/correct.html 切题校正
```

### 旧数据

- `store.json`：目标/任务/计划/考试日期；
- `schedule.json`：时间表；
- 只迁结构与考试/课表，不迁 cards/mistakes/focus。

迁移契约：

```
store.json 实际是 {rev, updatedAt, data}
data.tasks     → goals/tasks/plans
data.exam      → exam_profile
schedule.json  events[].date + start/end → schedule_events
```

- 旧 `tasks[].title` → 目标；
- 旧 `problems[].desc` → 任务；
- 旧 `plans[].name` → 计划；
- 旧 `exam.date` → 考试日期；
- 旧时间表只有具体日期，没有重复规则 → 由用户确认周模板。

### 数据生命周期

- `app.db` 和 `samples/` 分开备份；
- `app.db` 是事实源，`result.json` 只保留切题原图/校正结果；
- 讲题页切换前，`reviews.json` 与 `app.db.reviews` 双写；
- 切换后只写 `app.db`，不再保留双源。

---

## 8. 当前实现状态

已实现：

- 第一环：语音、对话、会话落库、启发式收尾、FSRS、到期复述；
- 收尾/评级同步写 `app.db.reviews`；
- 首页：四科进度、考试倒计时、当前到期、今日队列；
- 计划页：目标树、未归档整卷、打开讲题、未归档卷“归到计划”；
- 已导入旧工作台：4 目标 / 7 任务 / 4 计划；
- 已导入 `2013 数二真题`：23 题，挂在 2013 计划；
- 时间页：可用分钟 → 科目块 → 草稿 → 确认；
- 课表周模板、50h 周配额、80% 上限已种子；
- 15 个 Python 测试通过。

未实现：

- **新版 2013 数二尚未完整测试**；
- `schedule.json` 时间表导入（目前只有固定课表模板）；
- 新建目标/任务/计划；
- `plan_units` 剩余量清单（自动倒排前置）；
- `active_plan_id`；
- 周四重算、周日排下周；
- 实际用时回写周配额；
- 队列项执行闭环（todo/opened/done/carried）；
- “下一道新题”落到具体题；
- 学科 profile / 题型路由；
- 阅读/408 父子结构；
- 讲题页直接读 `app.db`；
- 写作/生词 UI。

---

## 9. 下一步顺序

0. **先用新版完整走一遍 2013 数二**：讲题 → 收尾 → 评级 → 到期；
1. Schema migration/backup 框架（加表前必须先有）；
2. `plan_units` + `active_plan_id`；
3. 队列执行闭环 + `sessions/turns` 双写 + committed 账本；
4. 学科 profile / 题型路由；
5. 阅读/408 父子结构；
6. phase_goals / availability_exceptions / estimates；
7. 讲题页切 `app.db`；
8. 写作/生词。

---

## 10. 不做清单

- 不做知识库/拍书；
- 不做自动摘要展示；
- 不做自动知识卡；
- 不做自动标签系统；
- 不做掌握度评分；
- 不做 8080 网关；
- 不做课程完成度；
- 不做 streak/排行榜；
- 不允许跳过题目。

---

## 11. 决策记录

| 日期 | 决定 |
| --- | --- |
| 2026-10-25 | 收尾改启发式：内部 rubric + 用户总结 + 最多 2 次追问 |
| 2026-10-25 | 知识库暂不做 |
| 2026-10-26 | 计划页只显示当前到期，不显示未来日期 |
| 2026-10-26 | 题目不能跳过 |
| 2026-10-26 | 四科目标：数二/英二/政治/408 |
| 2026-10-26 | 英语阅读整篇一个 FSRS；408 大题不拆 |
| 2026-10-26 | 时间环：50h/周、80% 上限、20% 缓冲、2~3 科/天 |
| 2026-10-26 | 周四重算本周剩余，周日算下周 |
| 2026-10-26 | 课程只做即时补丁，不统计进度 |
| 2026-10-26 | 不做 8080 网关，新应用单端口 8793 |

---

## 12. 逻辑漏洞审计（本次）

### 12.1 已修正

| 漏洞 | 修正 |
| --- | --- |
| “80% 上限”和“20% 缓冲”重复扣 | 统一定义：`usable = free × 80%`，剩余 20% 就是缓冲，不再二次扣 |
| 计划层出现“下次到期” | 删除计划级 `next_due`，只保留每道题的 due；页面只显示当前到期 |
| 一天 2~3 科，但四科都到期 | 先选 overdue 最久的 2~3 科；其余到期保留，不硬塞 |
| 到期装不下还推新题 | 到期预估 > 当天可用 60% → 只做到期；仍装不下就按 due 最早取，剩余保留 |
| 队列“下一道新题”是占位 | 必须由计划环返回具体 `problem_id`；占位只允许出现在草稿 v0 |
| 时间环只出队列，不知道做完没有 | 增加 `todo → opened → done/carried` 和 `actual_min` |
| 课程被当成进度条 | 课程只做即时补丁，不统计完成度 |
| 计划不跳过会卡死 | 不跳过、不自动归档；计划停在进行中，不伪造完成 |
| 没有剩余量却自动倒排 | 增加 `plan_units`；没有单元就退回手动周配额 |
| 周四“重算”变成改历史 | 周四只重算周五~周日，不改周一到周三 |
| 四科平均用力 | 每天 2~3 科，周最低保底，重科优先 |
| 讲题页和 app.db 两套数据 | 收尾/评级同步写 `app.db.reviews`；讲题页后续再切 |

### 12.2 仍存在的风险

1. **实际用时口径**：session 时间包含看课/停顿，不是纯专注；先封顶 2h，允许手改。
2. **阅读小题弱点**：阅读 set 只有一个 FSRS，单题弱不会单独排期；先记在 session，不拆 FSRS。
3. **旧数据映射**：旧 `plan` 可能不是“整卷”，导入后需要人工确认挂载。
4. **计划单元不全**：政治章节/英语写作还没有 `plan_units`，自动倒排会低估或漏项。
5. **时间模板变化**：课表固定，但临时调课/考试周需要手动覆盖。
6. **连续调试**：调试模式会压缩早晨，连续两天要自动降量，不能硬顶。

### 12.3 不变式

任何实现都不能破坏：

```
1. 计划没有 next_due
2. 到期只属于 problem
3. 评级只能用户确认
4. rubric 不返回前端
5. 队列未确认不进入执行（草稿可以落库，但不能算今天已完成）
6. 不自动改计划
7. 不把课程当进度
8. 不跳过题目
```

### 12.4 第二遍审计（本次新增）

| 漏洞 | 修正 |
| --- | --- |
| 一个任务下多年真题，时间环不知道排哪年 | 增加 `task.active_plan_id`；默认最早未完成，用户可切 |
| 计划既按套算又按题算，剩余量翻倍 | 明确“一个 FSRS 对象 = 一个倒排单元”，不重复计数 |
| 50h 目标可能超过实际空闲 | `weekly_target = min(3000, weekly_free × 0.8)` |
| 一科吃掉全部时间 | 单科单日 ≤ usable × 60%，每科周最低 |
| 确认后生活变化无法重排 | 增加 `draft → confirmed → locked` 和手动“解锁重排” |
| 半天休息/调课没有落点 | 增加 `availability_exceptions`，休息不补债 |
| 写作重写不算到期 | 时间页把 `rewrite_due` 并入当天到期额度；计划页仍只算 FSRS |
| 复述统一按 8 分钟估 | 按题型分档：阅读 20~25，408 大题 20~30，政治选择 2~3 |
| 没有阶段，7.7 周只有一个总目标 | 增加 `phase_goals`，三阶段，用户确认 |
| 队列和 session 对不上 | `sessions.queue_item_id`，结束本题回写 `done` |
| 讲题页/旧 reviews 双源 | 过渡期双写；切换后单源 `app.db` |

### 12.5 下一轮必须先补的洞

按优先级：

1. `plan_units` + `task.active_plan_id`；
2. `sessions.queue_item_id` + 队列状态回写；
3. `phase_goals` + 自动倒排；
4. `availability_exceptions`；
5. 写作 `rewrite_due` 并入时间环；
6. 讲题页切 `app.db`。

---

## 13. plan_units / active_plan_id 落地规格

这一节把 §12.5 第 1 条钉成可实现的东西。当前 `db.py` 还没有这两项，所以自动倒排不能开工。

### 13.1 表结构

```sql
ALTER TABLE tasks ADD COLUMN active_plan_id TEXT;
-- SQLite 不能直接给已有表加 REFERENCES，靠应用层校验：
-- active_plan_id 必须属于同一个 task_id。

CREATE TABLE IF NOT EXISTS plan_units (
  id TEXT PRIMARY KEY,
  plan_id TEXT NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN (
    'problem', 'reading_set', 'comprehensive', 'chapter', 'writing'
  )),
  ref_type TEXT NOT NULL DEFAULT 'none'
    CHECK (ref_type IN ('problem', 'paper', 'writing_task', 'none')),
  ref_id TEXT NOT NULL DEFAULT '',
  estimate_min INTEGER NOT NULL DEFAULT 25,
  status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'done')),
  source TEXT NOT NULL DEFAULT 'derived',  -- derived / manual
  created_at INTEGER NOT NULL,
  done_at INTEGER,
  UNIQUE (plan_id, ref_type, ref_id)
);

CREATE INDEX idx_plan_units_plan ON plan_units(plan_id, status);
```

### 13.2 什么算一个 unit

| 计划 | unit | ref |
| --- | --- | --- |
| 数学整卷 | 每个顶层 problem | `problem` + `paper:index` |
| 英语阅读 | 每篇 set 的父 problem | `problem` + set id |
| 英语完型/新题型 | 每篇父 problem | `problem` |
| 英语翻译 | 每篇/每组 problem | `problem` |
| 英语写作 | 每篇 writing_task | `writing_task` |
| 政治章节 | 每章 | `none` |
| 政治肖1000 | 每章题组 | `none` |
| 408 选择 | 每个 problem | `problem` |
| 408 大题 | 每个父 problem | `problem` |

硬规则：

```
parent_id IS NOT NULL 的阅读小题/408 小问，不建 unit。
手动章节：ref_type='none', ref_id=''（不要用 NULL，否则 UNIQUE 不生效）。
```

否则一个阅读 set 会变成 5 个单元，剩余量翻五倍。

### 13.3 状态怎么变

- `problem` / `reading_set` / `comprehensive`：该 problem 第一次结束本题 → `done`，同时写 `done_at`；
- `writing`：`writing_tasks.status = final` → `done`，同时写 `done_at`；
- `chapter`：用户点完成 → `done`，同时写 `done_at`；
- 撤销完成不允许（v1），避免计划进度反复跳；
- 复习到期不把 unit 改回 `new`；第一遍完成是事实，复述是另一层。

### 13.4 active_plan_id 规则

```
tasks.active_plan_id
```

- 必须属于该 task；
- 默认：该 task 下 `year` 最早、且还有 `new` unit 的计划；
- 用户切换后保存；
- 计划完成不自动切换；
- 到期题不按 active plan 过滤；
- 切换 active plan 不修改任何 review/session。

校验：

```text
active_plan_id IS NULL
OR EXISTS (SELECT 1 FROM plans WHERE id=active_plan_id AND task_id=tasks.id)
```

### 13.5 迁移

对每个已有 paper：

1. 取 `problems WHERE parent_id IS NULL`；
2. 每个 problem 建一个 unit；
3. `kind` 按 `problems.type`：
   - `reading_set` → `reading_set`
   - `comprehensive` → `comprehensive`
   - 其他 → `problem`
4. `estimate_min` 先用默认表；
5. `source='derived'`。

对没有 paper 的计划：

- 不自动造 unit；
- 计划页提示“需要手动添加章节/题组”；
- 时间环对手动计划退回手动配额。

### 13.6 验收

```
1. 一个 17 题整卷 → 17 个 unit，不是 34 个；
2. 一篇阅读 + 5 小题 → 1 个 unit；
3. 一个 408 大题 + 3 小问 → 1 个 unit；
4. active_plan 切到 2019，2010 的到期题仍在 due；
5. 全部 unit done → 计划第一遍完成；
6. 删除 paper → units 级联删除。
```

---

## 14. queue_item ↔ session 落地规格

§12.5 第 2 条：队列不能只排，必须知道做完没有。当前 `db.py` 的 `sessions` 没有 `queue_item_id`，`queue_items` 也没有 `opened_at/done_at`，所以执行闭环还没成立。

### 14.1 表结构

```sql
ALTER TABLE sessions ADD COLUMN queue_item_id TEXT;
-- 应用层校验：必须属于同一个 daily_plan 的 queue_items.id

ALTER TABLE queue_items ADD COLUMN opened_at INTEGER;
ALTER TABLE queue_items ADD COLUMN done_at INTEGER;
ALTER TABLE queue_items ADD COLUMN manual_min INTEGER;
```

状态只用：

```
todo / opened / done / carried / extra
```

不再增加 `doing`：`opened` 就是进行中。

### 14.2 打开链路

时间页的“去复述/去讲题”必须带队列 ID：

```
/talk.html?paper=<paper>&index=<i>&queue=<queue_item_id>
```

讲题页：

```
state.queueItemId = URLSearchParams.get('queue')
```

创建 session 时写入：

```
POST /api/session {paper,index,mode,queueItemId}
sessions.queue_item_id = queueItemId
```

规则：

- 同一 `queue_item_id` 同时只能有一个未结束 session；
- 重复打开同一队列项 → 复用已有 opened session，不新建；
- 队列项不属于当天/状态不是 confirmed → 拒绝打开；
- 从计划页直接打开（无 queue 参数）→ 不创建队列项，session 的 `queue_item_id=NULL`，结束本题记 `extra`。

### 14.3 结束链路

`POST /api/finish/complete` 必须带 `sessionId`：

```
{finishId, summary, sessionId}
```

服务端：

```
1. 找到 session.queue_item_id
2. 若为空 → 只写 review，不碰队列
3. 若存在 → queue_items.status='done', done_at=now
4. actual_min = clamp(session 结束 - 开始, 1, 120)
5. 若 manual_min 已手填 → 不覆盖
6. 同一 queue item 重复 complete → 幂等，不重复累加
```

`done` 的条件：

```
必须完成“用户总结 + complete”
只有打开、只有对话、只有评级，都不算 done
```

### 14.4 未完成与顺延

- 当天结束（用户点“收工”或次日首次打开）：
  - `todo` / `opened` → `carried`；
  - `done` 不动；
  - `extra` 不参与队列完成率。
- `carried` 不自动生成明天的新队列项；第二天由时间环重新排。
- 不把 `carried` 变成债务，不累计“欠账分钟”。

### 14.5 与 plan_units 的联动

```
queue done → 对应 plan_unit done
```

- `queue_items.ref_id` 是 problem id；
- 找到 `plan_units.ref_type='problem' AND ref_id=problem_id`；
- 置 `status='done'`；
- 没有对应 unit（计划页直接打开的题）→ 只更新 problem_progress，不伪造 unit。

### 14.6 actual_min 口径

```
actual_min = min(120, max(1, round((ended_at - started_at)/60)))
```

- 含看课/翻书/停顿；
- 超过 2h 封顶，避免挂机污染；
- 手动改 `manual_min` 后，以 manual_min 为准；
- 0 秒 session 不写 actual_min；
- 预估校准只用有 `done` 且 actual_min > 0 的样本。

### 14.7 验收

```
1. 时间页确认后，点复述 → 队列项 opened；
2. 结束本题 → done + actual_min；
3. 只打开不结束 → 次日 carried，不标 done；
4. 同一题重复打开 → 复用 session，不重复 done；
5. 从计划页直接讲 → queue_item_id=NULL，不污染当天队列；
6. 队列 done → 对应 plan_unit done；
7. 手动改 actual_min → 不被 session 时长覆盖。
```

### 14.8 失败处理

| 情况 | 处理 |
| --- | --- |
| session 找不到 | 仍写 review，队列不动，返回警告 |
| queue item 已 done | 幂等，不改 actual_min |
| queue item 属于 draft | 拒绝打开，提示先确认 |
| 用户中途关闭页面 | session 未结束，队列保持 opened；下次复用 |
| actual_min 为 0 | 不写，保留 null |
| 同一题多个 session | 以最后完成的 session 为准，不累加 |

---

## 15. phase_goals 与自动倒排落地规格

§12.5 第 3 条。当前 `db.py` 没有 `phase_goals`，`app_api` 也没有倒排；周配额仍是固定种子。没有阶段目标，7.7 周只有一个总目标，周配额无法解释“为什么这周数学多、政治少”。

### 15.1 表结构

```sql
CREATE TABLE IF NOT EXISTS phase_goals (
  id TEXT PRIMARY KEY,
  subject_id TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  start_date TEXT NOT NULL,   -- YYYY-MM-DD，含
  end_date TEXT NOT NULL,     -- YYYY-MM-DD，含
  target_units INTEGER NOT NULL DEFAULT 0,  -- 0 = 不设上限，按剩余量倒排
  created_at INTEGER NOT NULL,
  CHECK (start_date <= end_date)
);

CREATE INDEX idx_phase_subject ON phase_goals(subject_id, start_date, end_date);

ALTER TABLE plan_units ADD COLUMN done_at INTEGER;
```

`target_units` 是“本阶段完成多少个 unit”，不是“计划总共多少 unit”。

### 15.2 阶段是什么，不是什么

是：

- 一个时间窗；
- 每科一个目标量；
- 自动倒排的约束。

不是：

- 不是新的一套题目；
- 不重置计划进度；
- 不因为进入下一阶段把 `plan_units` 变回 new；
- 不是 agent 自动编教材范围。

### 15.3 同科阶段不能重叠

应用层校验：

```text
同一 subject_id，任意两个 phase 的 [start,end] 不得相交。
```

允许：

- 四科阶段日期不同；
- 某科没有阶段；
- 阶段结束后不自动补下一阶段。

### 15.4 倒排公式

单科：

```
weeks_left = max(1, ceil((end_date - today) / 7))
done_in_phase = count(plan_units where done_at between start_date and end_date)
target_remaining = max(0, target_units - done_in_phase)
required_new_hours = target_remaining × unit_estimate / 60
review_load_hours = due_count × review_estimate / 60 × 1.3
weekly_need = (required_new_hours + review_load_hours) / weeks_left
```

- `target_units=0` → 用该科剩余 new units 到考试日倒排；
- `weeks_left < 1` → 1 周，不除零；
- `unit_estimate` 用中位数，没有则默认表；
- `review_load_hours` 只算当前到期，不预测未来。

四科汇总：

```
weekly_need_total = Σ subject weekly_need
weekly_target = min(3000, weekly_free × 0.8)
```

判断：

- `weekly_need_total ≤ weekly_target`：按 need 分配，剩余给弱科/缓冲；
- `>`：输出缺口，给 A/B/C，不静默砍目标。

### 15.5 分配顺序

```
1. 每科先给 min(weekly_need, 科目上限)
2. 剩余额度按“阶段紧迫度”分
3. 仍不够 → 触发缺口方案
```

阶段紧迫度：

```
紧迫度 = target_remaining / max(1, weeks_left)
```

不在文档里造“学习价值分”；弱科由用户设置优先级，不由 agent 推断。

### 15.6 阶段切换

- 日期进入下一阶段：自动切换当前阶段；
- 不追溯改已完成记录；
- 不自动把上一阶段未完成 unit 变成新阶段目标；
- 未完成 unit 仍在原计划，下一阶段可继续；
- 用户可手动改阶段日期，但必须确认。

### 15.7 验收

```
1. 同科重叠阶段 → 拒绝保存；
2. target_units=0 → 按剩余 unit 倒排；
3. done_at 在阶段内才计入 done_in_phase；
4. 阶段需求 > 50h → 返回缺口与 A/B/C；
5. 阶段切换不重置 plan_units；
6. 没有 plan_units → 返回“无法自动倒排”，退回手动配额；
7. 阶段结束后不自动生成下一阶段。
```

### 15.8 失败处理

| 情况 | 处理 |
| --- | --- |
| 没有阶段 | 用考试日总倒排，周配额标记“未分阶段” |
| 阶段已过 | 不补算，提示用户调整 |
| target 已完成 | weekly_need=0，只排到期 |
| 阶段目标不可能 | 返回缺口，不偷偷降 target |
| 同科重叠 | 拒绝保存并指出冲突区间 |
| 无 plan_units | 不猜，退回手动周配额 |

---

## 16. availability_exceptions 落地规格

§12.5 第 4 条。当前 `db.py` 只有 `availability_template`（固定课表），没有“某天调课/考试/休息”的落点。没有这个，时间环会把休息日当普通日排满。

### 16.1 表结构

```sql
CREATE TABLE IF NOT EXISTS availability_exceptions (
  id TEXT PRIMARY KEY,
  date TEXT NOT NULL,           -- YYYY-MM-DD，本地时区
  start_min INTEGER NOT NULL,   -- 0..1440
  end_min INTEGER NOT NULL,     -- 0..1440
  kind TEXT NOT NULL CHECK (kind IN ('block', 'free')),
  reason TEXT NOT NULL CHECK (reason IN ('rest', 'class', 'exam', 'other')),
  title TEXT,
  created_at INTEGER NOT NULL,
  CHECK (start_min < end_min)
);

CREATE INDEX idx_avail_exc_date ON availability_exceptions(date);
```

语义：

- `block`：从当天可用时间里扣掉；
- `free`：额外加一段可用时间（如课取消）；
- `reason=rest` 必须是 `block`；
- 同一 `date` 的 exceptions 不允许互相重叠（v1 直接拒绝，避免 block/free 谁优先的歧义）。

### 16.2 日窗口

课表只说明“什么时候有课”，还需要“每天几点到几点醒着”。

```sql
CREATE TABLE IF NOT EXISTS day_windows (
  mode TEXT PRIMARY KEY CHECK (mode IN ('normal', 'debug')),
  start_min INTEGER NOT NULL,
  end_min INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS day_modes (
  date TEXT PRIMARY KEY,
  mode TEXT NOT NULL REFERENCES day_windows(mode)
);
```

默认：

```
normal: 08:00–24:00  (480–1440)
debug:  12:00–24:00  (720–1440)
```

调试日不跨日计算；凌晨学习算个人选择，不进入当天配额。

### 16.3 计算顺序

```
1. 取 day_modes[date]，没有则 normal
2. 取 day_windows[mode] 作为基础窗口
3. 扣掉 availability_template 里该 weekday 的课程
4. 扣掉 kind=block 的 exceptions
5. 加上 kind=free 的 exceptions
6. 合并区间，得到 free_min
7. usable_min = floor(free_min × 0.8)
```

- 休息是 `block + rest`，第 6 步自然变少；
- 调课是 `block + class` + `free + class` 两段；
- 考试周是 `block + exam`；
- 时间 agent 不能把 `rest` 段重新填满，除非用户手动覆盖。

### 16.4 与周配额的关系

```
weekly_free = Σ(date 的 free_min)
weekly_target = min(3000, floor(weekly_free × 0.8))
```

- 周配额锁定后，新增休息/考试导致容量下降：
  - 不自动加回配额；
  - 周四/周日重算时给出缺口；
  - 不静默压缩到“看起来能完成”。
- 新增 `free` 导致容量上升：
  - 也不自动加目标；
  - 用户确认后才加冲刺项。

### 16.5 休息规则

- 半天休息至少 180 分钟；
- `rest` 段不排任何科目块；
- 休息不补债，不扣“学习时长”；
- 连续调试两天，第三天默认降量，不靠意志硬顶；
- 用户手动说“今天不休息”可以覆盖，但覆盖要记录，不静默。

### 16.6 验收

```
1. 周一加一条 14:00–16:00 调课 block → 当天 free 减少 120；
2. 加半天 rest → 时间页不排该段；
3. 加 free 例外 → 可用时间增加；
4. 同一天 block/free 重叠 → 拒绝保存；
5. 考试周 block exam → 周配额下降并提示缺口；
6. debug 模式 → 日窗口变为 12:00 起；
7. 休息段不会被自动排程重新填满。
```

### 16.7 失败处理

| 情况 | 处理 |
| --- | --- |
| start >= end | 拒绝保存 |
| 超出 0..1440 | 拒绝保存 |
| 同一天区间重叠 | 拒绝保存并指出冲突 |
| rest 却是 free | 拒绝 |
| 没有 day_mode | 默认 normal |
| 例外导致周容量不足 | 重算并提示，不静默加目标 |
| 用户手动覆盖休息 | 记录 override，不默认允许 |

---

## 17. writing_tasks 与时间环落地规格

§12.5 第 5 条。写作有 `rewrite_due`，但当前 `app_api._due_rows()` 只查 `reviews`，时间页看不到写作重写；结果“写作安排了”只是计划页有任务，时间环不知道它到期。

### 17.1 写作状态机

```
draft
  ↓ 提交初稿
feedback
  ↓ 用户确认反馈 / tutor 给出反馈
rewrite（设置 rewrite_due）
  ↓ 重写提交
final
```

- `rewrite_due` 只在 `feedback/rewrite` 阶段有意义；
- `draft` 阶段不产生 due；
- `final` 后不再产生 due；
- 一个 writing task 只有一轮重写（v1），不做无限改稿。

### 17.2 字段

```sql
-- 现有 writing_tasks 已有 prompt/outline/draft/feedback/rewrite/status/rewrite_due
ALTER TABLE writing_tasks ADD COLUMN feedback_at INTEGER;
ALTER TABLE writing_tasks ADD COLUMN rewrite_at INTEGER;
ALTER TABLE writing_tasks ADD COLUMN final_at INTEGER;
```

`rewrite_due` 规则：

- 反馈完成时设置，默认 `feedback_at + 2 天`；
- 用户可改，但必须是未来日期；
- `rewrite_due` 不是 FSRS，不参与记忆调度；
- 过期未重写 → 仍算当前到期，不自动顺延。

### 17.3 统一到期视图

时间环的“当前到期”是两类并集：

```
problem_due  = reviews.due <= now
writing_due  = writing_tasks.rewrite_due <= now
             AND status IN ('feedback','rewrite')
```

API 形状：

```json
{
  "type": "writing",
  "id": "writing_task_id",
  "subject_id": "english2",
  "title": "2018 英二大作文",
  "due": "2026-10-28",
  "estimate_min": 25
}
```

规则：

- `/api/app/due` 返回两类并集；
- 计划页的“到期 N”仍只算 FSRS 题，不把写作混进计划进度；
- 时间页的“到期优先”包含写作；
- 写作 due 不占 `reviews` 表，不伪造 problem。

### 17.4 时间环怎么排

英语块内：

```
1. 阅读/完型等到期复述
2. 写作重写 due
3. 新阅读
4. 新写作
```

- 写作重写预估 20~30 分钟；
- 到期写作和阅读 due 谁先：按 `due` 最早；
- 都装不下：只做到期，砍新阅读/新写作；
- 写作重写不能用“看一遍”代替，必须提交改写文本或口述修改。

### 17.5 队列与完成

```
queue_items.type = 'writing'
queue_items.ref_id = writing_task_id
```

- 时间页点“去重写” → 打开写作页/讲题页；
- 完成重写 → `writing_tasks.status='final'`、`final_at=now`；
- queue item → `done`，`actual_min` 回写；
- `plan_units`（kind=writing）→ `done`；
- 只打开不提交 → `opened`，次日 `carried`。

### 17.6 验收

```
1. draft 阶段不产生 rewrite_due；
2. feedback 保存后 rewrite_due 默认 +2 天；
3. rewrite_due 到期 → /api/app/due 出现 writing；
4. 计划页到期数不因写作 +1；
5. 时间页英语块出现“写作重写”；
6. 提交重写 → status=final、queue done、unit done；
7. 过期未重写 → 仍到期，不顺延；
8. 没有 feedback 却写 rewrite_due → 拒绝。
```

### 17.7 失败处理

| 情况 | 处理 |
| --- | --- |
| rewrite_due 早于今天 | 允许保存但立即算到期 |
| 没有 feedback 就设 rewrite_due | 拒绝 |
| 同一 task 重复完成 | 幂等，不重复加 unit |
| 写作 due 挤掉阅读 due | 按 due 最早，不按类型偏心 |
| 用户只想改一句 | 仍算重写完成，但记录实际用时 |
| 写作页没打开 | queue 保持 opened，次日 carried |

---

## 18. 讲题页切 app.db 的割接规格

§12.5 第 6 条。当前讲题页仍读 `/api/paper/<id>` 的 `result.json`；`app.db` 只有题目文本/latex/image/bbox，缺 options/figures/pages，所以不能直接切。硬切会丢选项、图、页数。

### 18.1 缺什么

`problems` 现在没有：

```
position       题目在卷内的稳定顺序
options_json   选项
figures_json   图/表
payload_json   完整 problem 原始结构
text_trusted
continues_next
```

`papers` 没有：

```
pages_json     页数/页面元数据
warnings_json  切题警告
```

不补这些，app.db 版本的讲题页一定比 result.json 少东西。

### 18.2 表结构

```sql
ALTER TABLE papers ADD COLUMN pages_json TEXT;
ALTER TABLE papers ADD COLUMN warnings_json TEXT;

ALTER TABLE problems ADD COLUMN position INTEGER;
ALTER TABLE problems ADD COLUMN options_json TEXT;
ALTER TABLE problems ADD COLUMN figures_json TEXT;
ALTER TABLE problems ADD COLUMN payload_json TEXT;
ALTER TABLE problems ADD COLUMN text_trusted INTEGER NOT NULL DEFAULT 1;
ALTER TABLE problems ADD COLUMN continues_next INTEGER NOT NULL DEFAULT 0;

CREATE INDEX idx_problems_position ON problems(paper_id, position);
```

- `payload_json` 是原始 problem 的完整备份；
- 其余列是给查询/排序/筛选用的投影；
- 不把图片二进制塞进 DB；`image` 仍是相对路径，媒体继续走 `/media/`。

### 18.3 迁移

对每份 `samples/ingest-*/result.json`：

```
papers.pages_json    = result.pages
papers.warnings_json = result.warnings
for i, p in result.problems:
  problems.position      = i
  problems.options_json  = p.options
  problems.figures_json  = p.figures
  problems.payload_json  = p
  text_trusted/continues_next 按 p 复制
```

幂等：

- 以 `(paper_id, position)` 对齐；
- 不按 `no` 排序，因为 no 可能重复/缺失；
- 重复导入只更新 payload，不重置 status/review。

### 18.4 新 API

```
GET /api/app/papers
GET /api/app/paper/<id>
```

返回形状尽量兼容旧 `/api/paper/<id>`：

```json
{
  "id": "...",
  "pages": 4,
  "problems": [
    {"index":0,"no":"1","text":"...","options":[],"figures":[],
     "image_url":"/media/...","page_url":"/media/...","crop_url":"/media/..."}
  ],
  "warnings": []
}
```

兼容字段必须和旧接口同义，否则 talk.js 会出现“同一题两种 index”。

### 18.5 割接顺序

```
1. 加列 + 迁移 payload
2. 加 /api/app/paper 双读接口
3. talk.js 加 ?source=app 开关
4. 逐份卷对比：题数、页数、options、figures、图片 200、latex
5. 现有 2013 先过；以后每新增一份卷逐份过 → 默认 source=app
6. finish/start/complete 改为按 problem_id 读 app.db
7. 移除 talk 对 result.json 的读取
```

回滚：

- URL 去掉 `source=app` 即回旧接口；
- app.db 缺 payload 的卷，自动回退旧接口并显示警告；
- 不允许“半份卷 app.db、半份卷 result.json”混排。

### 18.6 finish/rating 的切换

当前 `_finish_start` 用 `paper_dir` + `result.json` 找题。切 app.db 后：

```
finish/start {problemId}
  → 查 app.db.problems
  → rubric 用 payload_json 的题干
  → review problem_id 直接用
```

- 不再依赖 `paper:index` 拼 id；
- session 保存 `problem_id`；
- 旧 session 迁移时把 `paper:index` 映射到 `problem.id`。

### 18.7 验收

```
1. 每份卷页数一致；
2. 每卷题数一致；
3. options/figures 数量一致；
4. 题图/crop/page 均 200；
5. latex 渲染节点数不减少；
6. 刷新恢复 session；
7. 结束本题 → review 写入 app.db；
8. 去掉 source=app 能回滚；
9. app.db 缺 payload → 明示回退，不静默。
```

### 18.8 失败处理

| 情况 | 处理 |
| --- | --- |
| payload 缺失 | 该卷回退 result.json，显示警告 |
| 页数/题数不一致 | 阻止切默认，列出差异 |
| 图片 404 | 阻止切默认 |
| index 对不上 | 以 position 为准，重建 index |
| finish 仍读旧文件 | 割接未完成，保留开关 |
| 旧 session 无法映射 | 保留只读，不写新 review |

---

## 19. 整卷生命周期与重切规则

§12.5 已覆盖完，但还有一个会直接毁数据的新洞：切题校正/重拍/重切会改题目数量或顺序，而 `reviews`、`plan_units`、`queue_items.ref_id` 都按 problem id 绑定。现在没有任何“重切后怎么办”的规则。

### 19.1 整卷状态

```
active      正常使用
archived    不再新增，但历史/到期保留
deleted     仅限从未产生 session/review 的卷
```

`papers.status` 默认 `active`。

### 19.2 字段

```sql
ALTER TABLE papers ADD COLUMN status TEXT NOT NULL DEFAULT 'active';
ALTER TABLE papers ADD COLUMN revision INTEGER NOT NULL DEFAULT 1;
ALTER TABLE papers ADD COLUMN supersedes_id TEXT;
ALTER TABLE papers ADD COLUMN source_hash TEXT;

CREATE INDEX idx_papers_status ON papers(status);
```

- `source_hash`：原始页图/切题结果的哈希，用于防重复导入；
- `revision`：同一份卷的版本号；
- `supersedes_id`：新版本指向旧版本。

### 19.3 原地修正（允许）

以下操作不改变题目数量/顺序，保留 problem id、review、unit：

```
1. 改题干文字
2. 改选项
3. 改 latex
4. 重拍同一 position 的题图
5. 改 bbox
```

规则：

- 以 `position` 对齐，不按 `no`；
- 更新 `payload_json`；
- 不重置 `reviews`；
- 不重建 `plan_units`；
- 不改变 `problems.id`。

### 19.4 重切（限制）

重切 = 题目数量/顺序/边界变化。

```
未产生任何 session/review 的卷：
  允许重切，事务内重建 problems/units，旧数据删除。

已产生 session/review 的卷：
  禁止原地重切。
  只能新建 revision（新 paper id），旧卷 status=archived。
```

禁止原地重切的原因：

- `reviews` 绑定 problem id；
- `plan_units` 绑定 problem id；
- `queue_items.ref_id` 绑定 problem id；
- 原地换 id 会让到期题指向另一道题。

### 19.5 删除与归档

```
无 session / review / done unit → 可硬删
有任一历史 → 只能 archive
```

归档后：

- 不再出现在“下一题”；
- 到期题仍保留在 due，直到用户处理；
- 不自动删除 FSRS；
- 归档不是“计划完成”。

### 19.6 重复导入

```
source_hash 相同 → 不新建 paper
source_hash 不同但 title 相同 → 警告，让用户确认
```

不按标题去重，因为不同年份可能同名。

### 19.7 整卷挂计划

- 未产生 session/review：可直接改 `papers.plan_id`，同时重建 units；
- 已产生 session/review：不允许换 plan；只能归档后新建；
- 一个 paper 只属于一个 plan；
- 未归档整卷可以不属于任何 plan，但时间环不排它。

### 19.8 验收

```
1. 重拍同一 position → review 仍在；
2. 改文字/选项 → review 仍在；
3. 未讲过的卷重切 → 题数/units 同步；
4. 已讲过的卷重切 → 409，提示新建 revision；
5. 有 review 的卷删除 → 拒绝，提示 archive；
6. 相同 source_hash 导入 → 返回已有 paper；
7. archive 后不再出“下一题”，但到期仍可见；
8. 换 plan 只允许未产生历史的卷。
```

### 19.9 失败处理

| 情况 | 处理 |
| --- | --- |
| 重切后题数变化但已有 review | 拒绝，给出旧/新题数 |
| 重拍 position 越界 | 拒绝，不猜 |
| source_hash 冲突 | 返回已有 paper |
| 删除有历史的卷 | 拒绝，改 archive |
| archive 后仍有 due | 保留 due，提示用户处理 |
| 换 plan 但已有 review | 拒绝，新建 revision |
| 旧 revision 被引用 | 保留只读，不级联删 review |

---

## 20. 周配额账本：committed / actual

§12.5 已覆盖完，但当前 `app_api.generate_time()` 只用 `planned - actual` 算剩余，`actual` 又从未回写。结果是：**每天都能把整周配额再排一遍**，周配额形同虚设。

### 20.1 三个数

```
planned_min   本周计划额度（周一锁定）
committed_min 已确认、但还没完成/释放的预估分钟
actual_min    已完成任务的实际分钟
```

剩余：

```
remaining = max(0, planned - committed - actual)
```

不能用 `planned - actual` 单独算，因为已确认的明天、后天也会重复占用。

### 20.2 字段

```sql
ALTER TABLE weekly_budgets ADD COLUMN committed_min INTEGER NOT NULL DEFAULT 0;
```

`committed_min` 只统计：

```
今天及本周内，daily_plans.status='confirmed'，
且 queue_items.status IN ('todo','opened')
```

不统计：

- draft；
- done；
- carried；
- extra。

### 20.3 状态迁移

确认当天队列：

```
for each queue item:
  committed += estimate_min
```

任务完成：

```
committed -= estimate_min   -- 释放预估
actual    += actual_min     -- 记实际
```

任务顺延/收工未做：

```
committed -= estimate_min   -- 释放，不滚债
```

重排/解锁当天：

```
先释放该日所有非 done 的 committed
再按新队列重新加
```

任务取消：

```
committed -= estimate_min
```

幂等：

- 同一个 queue item 只能从 todo/opened 迁移一次；
- `done` 后重复 complete 不重复加减；
- committed 不出现负数，低了就 clamp 到 0。

### 20.4 generate_time 的算法

```
remaining = max(0, planned - committed - actual)
```

- 每天分配不能超过 `remaining`；
- 如果当天需要超过 `remaining`，说明本周已透支：
  - 不静默压缩；
  - 返回“本周剩余不足”，给“加时间/降范围/跨周”选项；
- 跨周不共享 committed/actual，新周重新开始；
- 历史周只读，不回改。

### 20.5 与周四/周日重算

周四：

```
新剩余 = planned - committed - actual
```

- 释放本周未完成的 committed（如果选择不补）；
- 不把未完成转成新 committed；
- 重算后仍不能超过 remaining。

周日：

- 本周账本封存；
- 新周 `planned` 重新倒排；
- 不把旧周 committed 带入新周。

### 20.6 验收

```
1. 确认 90 分钟数学 → committed +90，remaining 减少；
2. 第二天再排 → 不会再把 90 分钟当“还没用”；
3. 完成实际 70 分钟 → committed -90，actual +70，remaining +20；
4. 顺延 → committed -estimate，不滚债；
5. 解锁重排 → 只释放非 done，不重复计；
6. done 重复提交 → 不重复加减；
7. 本周 remaining=0 → 排程返回不足，不硬排；
8. 跨周 → committed/actual 归零。
```

### 20.7 失败处理

| 情况 | 处理 |
| --- | --- |
| committed 变负 | clamp 0，记警告 |
| actual 为负 | 拒绝 |
| 没有 estimate | 用 0 不允许，退回 15 分钟默认并标记 |
| 同项重复 done | 幂等，不重复 |
| confirmed 后删除队列 | 先释放 committed，再删 |
| 本周透支 | 返回缺口，不静默压缩 |
| 跨周重排 | 拒绝改历史周 |

---

## 21. 双写与对账：reviews.json → app.db

当前过渡期是“先写 `reviews.json`，再 `app_api.sync_review()` 写 `app.db`”。如果第二步失败：

- 旧 review 已落盘；
- `app.db` 没更新；
- 接口可能返回 500；
- 用户重试可能重复；
- 首页/计划/时间的到期与旧讲题页不一致。

这是三环数据一致性的最大风险，必须补 outbox。

### 21.1 过渡期写入顺序

```
1. review_store.upsert / rate  （旧源，先写）
2. 取完整 item（含 fsrs）
3. 尝试 app_api.sync_review
4. 成功 → 返回 ok
5. 失败 → 写 review_sync outbox，返回 ok + warning
```

原则：

- 只要旧源成功，就不能让用户以为“评级丢了”；
- mirror 失败不能回滚旧源；
- 不能静默成功。

### 21.2 outbox 表

```sql
CREATE TABLE IF NOT EXISTS review_sync (
  problem_id TEXT PRIMARY KEY,
  payload_json TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
```

`problem_id` 主键表示“以最新一次为准”，不排队历史版本。

### 21.3 重试

- 每次 finish/rate 后尝试 flush；
- 服务启动时 flush；
- 首页/计划/时间加载时，若有 pending，返回 `reviewSyncPending` 数量；
- 重试成功 → 删除 outbox 行；
- 重试失败 → attempts+1，保留 last_error；
- 超过 5 次不删除，进入“需人工对账”。

### 21.4 对账

```
旧源 reviews.json
  ↕ 比较 problem_id / fsrs.due / state / last_rating
app.db reviews
```

结果：

- 旧有、app.db 无 → 补写 app.db；
- app.db 有、旧无 → 不删，标记 `app_only`；
- 两边 due/state 不同 → 以旧源为准（过渡期），写回 app.db；
- problem_id 在 app.db 不存在 → `orphan`，不伪造 problem，列出来。

对账 API/脚本只读+补写，不删除任何 review。

### 21.5 切换条件

只有同时满足才切 app.db 为主：

```
1. review_sync 为空；
2. orphan = 0；
3. 现有卷 due/rating 对比一致；以后新增卷逐份对比；
4. 讲题页 source=app 验收通过；
5. 备份 reviews.json。
```

切换后：

- `app.db` 是唯一写源；
- `reviews.json` 只读快照；
- 不再双写；
- 回滚只能靠备份，不能靠继续双写。

### 21.6 验收

```
1. app.db sync 失败 → 旧 review 不丢，outbox 有记录；
2. 重启后 flush 成功 → outbox 清空；
3. 同一题重复 finish → 不重复写；
4. rating 成功但 mirror 失败 → 旧 due 正确，dashboard 标记 pending；
5. orphan problem → 不创建假题，列表可见；
6. 对账后 due/state 一致；
7. 切换后旧文件不再被写。
```

### 21.7 失败处理

| 情况 | 处理 |
| --- | --- |
| app.db 锁/忙 | 入 outbox，稍后重试 |
| problem 不存在 | orphan，不插入假数据 |
| 旧 review 损坏 | 不覆盖 app.db，报警 |
| outbox 重复 | 主键 upsert，保留最新 |
| 对账冲突 | 过渡期以旧源为准，记录差异 |
| 切换后旧源被写 | 视为 bug，停写并回滚 |

---

## 22. 预估校准表与当前实现偏差

文档 §5.15 写了“用实际中位数校准”，但 `app_api.py` 现在还是：

```python
NEW_EST = {"math2": 25, "cs408": 25, "english2": 35, "politics": 2}
REVIEW_MIN = 8
```

两个问题：

1. 没有按题型区分：英语阅读复述 8 分钟、408 大题 8 分钟，都会严重低估；
2. 没有从实际样本校准：所有用户、所有阶段都用同一组常数。

时间环的可行性完全建立在这组预估上，不能再拍脑袋。

### 22.1 表结构

```sql
CREATE TABLE IF NOT EXISTS estimates (
  subject_id TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  median_min INTEGER NOT NULL,
  samples INTEGER NOT NULL DEFAULT 0,
  updated_at INTEGER NOT NULL,
  PRIMARY KEY (subject_id, kind)
);
```

`kind`：

```
new_problem
new_reading_set
new_comprehensive
review_problem
review_reading_set
review_comprehensive
review_politics
review_politics_analysis
writing
```

### 22.2 数据来源

只用：

- `queue_items.status='done'`；
- `actual_min > 0`；
- 对应 `problem_id` / `writing_task_id` 存在；
- 排除 `extra`（队列外）样本，避免污染。

不采用：

- agent 自己预测的时间；
- 未完成的 opened/todo；
- 用户手填的预估（只能作为 override，不进入中位数）。

### 22.3 中位数算法

```
1. 取最近 20 个样本
2. 去掉最大 10% / 最小 10%（至少 5 个样本才去尾）
3. 取中位数
4. clamp 到 [1, 120]
5. samples < 3 → 不覆盖默认值
```

- 每科/每 kind 独立；
- 单题异常值不改全科；
- 用户可手动 override 单个 plan_unit，不写回中位数。

### 22.4 默认表

| kind | 默认 |
| --- | --- |
| new_problem（数学） | 25 |
| new_problem（408 选择） | 5 |
| new_comprehensive（408 大题） | 30 |
| new_reading_set | 40 |
| new_problem（政治选择） | 2 |
| review_problem（数学） | 10 |
| review_reading_set | 22 |
| review_comprehensive | 25 |
| review_politics | 3 |
| review_politics_analysis | 18 |
| writing | 25 |

没有对应 kind → 用所属 plan_unit 的 `estimate_min`；再没有 → 25。

### 22.5 在 generate_time 里怎么用

```
due_min = Σ review_estimate(problem.type, subject)
new_min = Σ new_estimate(subject, kind)
```

- 不再用全局 `REVIEW_MIN=8`；
- 不再用单一 `NEW_EST[subject]`；
- 到期题按题型估，阅读/408 大题不会被压成 8 分钟；
- 预估来源可以是 `estimates` 或 `plan_units.estimate_min`，按优先级取。

### 22.6 验收

```
1. 数学 3 个 done 样本 → estimates 有记录；
2. 阅读复述估 22 而不是 8；
3. 408 大题复述估 25 而不是 8；
4. 样本 <3 → 仍用默认；
5. 异常值不改变全科中位数；
6. 校准不改写已完成 unit 的 estimate；
7. generate_time 不再引用 NEW_EST/REVIEW_MIN 常量。
```

### 22.7 失败处理

| 情况 | 处理 |
| --- | --- |
| 样本不足 | 用默认，不猜 |
| 全部超 120 | clamp 120 |
| actual=0 | 不入样 |
| 同一题多次 done | 只取最后一次 |
| kind 缺失 | 回退 plan_unit/25 |
| 校准后配额变化 | 下次 generate_time 生效，不改历史 |

---

## 23. 目标/任务/计划的删除与归档

§12.5 已覆盖完。`papers` 有生命周期，但上层 `goals/tasks/plans` 没有。当前 schema：

```
goals --CASCADE--> tasks --CASCADE--> plans
plans --SET NULL--> papers
papers --CASCADE--> problems --CASCADE--> reviews
```

删一个 plan，可能把 `plan_units` 清空、papers 变未归档，但 reviews 还在；删 goal/task 更会把整棵计划树带走。没有规则就会“点一下删除，历史没了”。

### 23.1 状态

```sql
ALTER TABLE goals ADD COLUMN status TEXT NOT NULL DEFAULT 'active';
ALTER TABLE tasks ADD COLUMN status TEXT NOT NULL DEFAULT 'active';
-- plans 已有 status
```

值：

```
active / archived
```

没有 `deleted` 状态：硬删只用于从未使用的空节点。

### 23.2 删除前置检查

硬删只允许同时满足：

```
没有任何子节点
没有任何 paper
没有任何 session/review/plan_unit
```

否则：

```
只能 archive
```

逐层：

| 节点 | 可硬删条件 | 否则 |
| --- | --- | --- |
| goal | 无 task | archive |
| task | 无 plan | archive |
| plan | 无 paper、无 unit、无 review | archive |
| paper | 无 session/review/unit | 硬删（见 §19） |

### 23.3 归档语义

- 从计划树隐藏，不出现在“当前计划”选择；
- 时间环不再为它排新题；
- 已有 due 仍保留，直到用户处理；
- 不自动删除 reviews/sessions/units；
- 归档不是“计划完成”；
- 可以取消归档，恢复到 active。

### 23.4 级联保护

数据库 FK 不能直接改（SQLite 重建成本高），先用应用层事务：

```
删除/归档前：
  SELECT COUNT(*) FROM ... WHERE parent=...
  if >0 and 不是 archive 请求 → 409
```

硬删顺序：

```
unit → problem → paper → plan/task/goal
```

- 不依赖数据库 `CASCADE` 清理有历史的树；
- 事务失败整体回滚；
- 删除前写 backup 行/日志，至少保留标题和 id。

### 23.5 active_plan 的失效

- task.active_plan_id 指向 archived plan → 自动置 NULL；
- 用户下次打开计划页重新选；
- 不自动选下一个计划，避免“悄悄换年份”。

### 23.6 验收

```
1. 有 paper 的 plan 删除 → 409，提示 archive；
2. 空 plan 删除 → 真删；
3. 有 task 的 goal 删除 → 409；
4. archive plan → 时间环不再排新题，due 仍在；
5. archive task → 其 plans 不再出现在 active 树；
6. active_plan 被归档 → 置 NULL，不自动切换；
7. 硬删事务失败 → 全部回滚；
8. archive 后可恢复 active。
```

### 23.7 失败处理

| 情况 | 处理 |
| --- | --- |
| 有子节点硬删 | 409，返回子节点数量 |
| 有 review 仍删 | 拒绝，改 archive |
| archive 后 due 未处理 | due 保留，首页可见 |
| active_plan 失效 | 置 NULL，不猜 |
| 误删空节点 | 用删除日志恢复标题/id，不恢复内容 |
| 归档 goal 但 task 还 active | 子节点一并归档或拒绝，二选一，不半归档 |

---

## 24. Schema 迁移与备份

前面已经加了 `plan_units`、`active_plan_id`、`queue_item_id`、`phase_goals`、`availability_exceptions`、`estimates`、`paper.status` 等一堆表/列。但 `db.py` 现在只有：

```python
c.executescript(SCHEMA)
# 手工 ALTER queue_items
```

没有版本号、没有迁移顺序、没有备份。下一次改表时，旧 `app.db` 可能半升级，或者 `ALTER` 重复执行报错。这是比单个表更底层的可行性问题。

### 24.1 版本表

```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  applied_at INTEGER NOT NULL
);
```

同时写：

```sql
PRAGMA user_version = <version>;
```

两个都写，便于外部工具和代码一致。

### 24.2 迁移文件

```
tutor/server/migrations/
  001_init.sql
  002_queue_item_meta.sql
  003_plan_units.sql
  004_queue_session.sql
  005_phase_goals.sql
  006_availability_exceptions.sql
  007_estimates.sql
  008_paper_lifecycle.sql
```

规则：

- 文件名前缀必须连续；
- 已应用版本不能改内容；
- 只允许 forward migration，不写 down migration；
- 每个文件只做一件事；
- 新表用 `CREATE TABLE IF NOT EXISTS`，加列用应用层检查 `PRAGMA table_info`。

### 24.3 启动流程

```
1. 打开 app.db
2. 读取 schema_migrations 最大 version
3. 若为 0 且库里已有表 → 视为 legacy，先备份
4. 按版本顺序应用未执行文件
5. 每个 migration 在事务内；失败即回滚
6. 成功后写 schema_migrations + PRAGMA user_version
7. 最后 PRAGMA integrity_check
```

- 不把 `executescript(SCHEMA)` 当迁移；
- `ALTER TABLE` 必须幂等；
- 迁移期间停止写入（单进程本地服务可做到）。

### 24.4 备份

迁移前：

```
1. PRAGMA wal_checkpoint(TRUNCATE)
2. 复制 app.db → app.db.bak-YYYYMMDD-HHMMSS
3. 校验备份能打开、integrity_check ok
4. 再执行 migration
```

- 备份失败 → 不迁移；
- 磁盘空间不足 → 不迁移；
- 迁移失败 → 自动恢复备份，服务进入只读；
- 不删除旧备份，保留最近 5 份。

### 24.5 数据回填

单独 migration 处理：

```
queue_items.title/meta
papers.plan_id 为空 → 未归档
problems.position → 按 result.json 顺序
plan_units → 从 papers/problems 派生
```

回填必须：

- 幂等；
- 不覆盖已有用户数据；
- 回填前记录数量，回填后对比；
- 不一致则中止，不强行写。

### 24.6 验收

```
1. 全新空库 → 一次迁移到最新版；
2. 已有一版库 → 只跑新增 migration；
3. 重复启动 → 不重复执行；
4. 迁移中途失败 → 回滚 + 备份恢复；
5. 备份不可用 → 拒绝迁移；
6. integrity_check 失败 → 停写并报警；
7. queue_items 旧库升级后 title/meta 存在；
8. schema_migrations 与 user_version 一致。
```

### 24.7 失败处理

| 情况 | 处理 |
| --- | --- |
| 迁移文件缺号 | 拒绝启动，列出缺口 |
| 已应用文件被改 | 拒绝，提示版本不一致 |
| 磁盘不足 | 不迁移，保留旧库 |
| 迁移 SQL 错误 | 回滚，恢复备份 |
| 备份损坏 | 不迁移，人工处理 |
| 并发写 | 本地单进程；多进程加文件锁 |
| 回填数量不一致 | 中止，不写半成品 |

---

## 25. 旧工作台迁移与首次启动

当前 `migrate.py` 的 `import_old_store()` 只认裸 `{tasks,...}`，但云端实际是 `{rev,updatedAt,data}`；`import_schedule()` 只取 `start`，没有拼 `date + start/end`；未知科目还会默认成 `math2`。这三处都会把旧数据导歪。

### 25.1 输入

```
/var/lib/workbench-sync/store.json
/var/lib/workbench-sync/schedule.json
```

`store.json` 两种形状都要支持：

```json
{"rev":1,"updatedAt":"...","data":{"tasks":[...]}}
{"tasks":[...]}
```

只迁：

```
data.tasks
data.exam
schedule.events
```

不迁：

```
dailies / cards / mistakes / focus / trash / queues
```

### 25.2 映射

| 旧 | 新 | 规则 |
| --- | --- | --- |
| `data.tasks[]` | `goals` | 每个旧 task 一个 goal |
| `task.problems[]` | `tasks` | 每个旧 problem 一个 task |
| `problem.plans[]` | `plans` | 每个旧 plan 一个 plan |
| `data.exam` | `exam_profile` | label + date |
| `schedule.events[]` | `schedule_events` | date + start/end |

不自动创建 paper/problem：

- 旧 plan 没有整卷；
- 迁移后计划页显示“还没有整卷”；
- 由用户上传/关联。

### 25.3 科目推断

```
标题包含 数二/数学 → math2
标题包含 英二/英语 → english2
标题包含 政治 → politics
标题包含 408/计算机 → cs408
其他 → other
```

- 未知科创建 `other` 科目，不默认 math2；
- 迁移报告列出 unknown；
- 用户确认后再改 subject_id；
- 不允许静默把政治/英语塞进数学。

### 25.4 ID 与幂等

```
goal_id = g_<old_task_id>
task_id = t_<old_problem_id>
plan_id = p_<old_plan_id>
```

- 保留 `external_id`；
- 重跑只更新 title/parent，不重复插入；
- ID 已存在但 parent 不同 → 中止，不覆盖；
- 旧 ID 缺失 → 用内容哈希生成稳定 ID，重跑一致。

唯一性：

```sql
CREATE UNIQUE INDEX IF NOT EXISTS ux_goals_external
  ON goals(subject_id, external_id) WHERE external_id <> '';
CREATE UNIQUE INDEX IF NOT EXISTS ux_tasks_external
  ON tasks(goal_id, external_id) WHERE external_id <> '';
CREATE UNIQUE INDEX IF NOT EXISTS ux_plans_external
  ON plans(task_id, external_id) WHERE external_id <> '';
```

### 25.5 时间表

旧事件形状：

```json
{"date":"2026-10-26","start":"09:55","end":"11:20","title":"移动物联网","type":"class"}
```

迁移：

```
start_at = date + 'T' + start + ':00+08:00'
end_at   = date + 'T' + end   + ':00+08:00'
```

规则：

- 只迁未来 30 天；
- 不迁历史事件；
- 事件 ID 用 `date+start+title` 哈希，重跑幂等；
- 不自动覆盖 `availability_template`；
- 如果同一 weekday/time/title 出现 ≥2 次，生成“建议周模板”，让用户确认；
- 一次性讲座/考试只进 `schedule_events`，不进周模板。

### 25.6 事务与备份

```
1. 备份 app.db
2. BEGIN IMMEDIATE
3. 导入 goals/tasks/plans/exam/schedule
4. 计数校验
5. COMMIT
6. 失败 ROLLBACK + 恢复备份
```

计数校验：

```
旧 tasks 数 == 新 goals 数
旧 problems 数 == 新 tasks 数
旧 plans 数 == 新 plans 数
未知科目数 == 报告数
```

### 25.7 验收

```
1. 两种 store 形状都能导入；
2. 重跑不重复；
3. 未知科目进 other，不默认数学；
4. 旧 exam 日期正确；
5. 时间表拼出完整 ISO 时间；
6. 未来 30 天外事件不迁；
7. 计数一致；
8. 失败回滚，app.db 不半写。
```

### 25.8 首次启动

如果 `goals=0`：

- 不自动 seed 假目标；
- 首页显示“导入旧数据 / 新建目标”；
- 计划页显示空态；
- 时间环的手动配额仍可用；
- 不因为空库就硬编码四科目标。

### 25.9 失败处理

| 情况 | 处理 |
| --- | --- |
| JSON 损坏 | 不导入，保留原文件 |
| 未知科目 | other + 报告，不猜 |
| ID 冲突 | 中止，列出冲突 |
| 日期/时间非法 | 跳过该 event，报告 |
| 重跑 parent 不同 | 中止，不覆盖 |
| 计数不一致 | 回滚 |
| 备份失败 | 不导入 |

---

## 26. ingest → app.db 同步规格

这次 2013 数二真题是手工 upsert 进 `app.db` 的：跑完 `ingest.py` 生成 `result.json`，再单独写 papers/problems，再手动挂到 2013 计划。这不是正式链路，下一次上传还得再手写一遍。

真实链路必须是：

```
上传/拍照
  → ingest.py 切题
  → result.json
  → 自动同步 app.db.papers/problems
  → 未归档
  → 用户归到计划
```

### 26.1 入口

```bash
python ingest.py --title "2013 数二真题" --plan p_x462_mvkyasix img1 img2 ...
```

- `--title` 可选，默认用目录名；
- `--plan` 可选；不传则未归档；
- 不再要求手工跑第二段导入；
- 成功后输出：

```
paper=ingest-...
problems=23
plan=... / unassigned
```

### 26.2 同步函数

```
sync_paper_to_app(result_dir, title=None, plan_id=None) -> paper_id
```

步骤：

1. 读 `result.json`；
2. 计算 `source_hash = sha256(按页顺序的页图)`；
3. 按 `source_hash` 找已有 paper：
   - 有 → 更新 title/plan_id，不新建；
   - 无 → 新建 paper；
4. 每个顶层 problem 建/更新：
   - `id = paper_id:position`
   - `position = 数组下标`
   - `no/text/latex/image/bbox`
   - `parent_id = null`（阅读/408 子题后续再拆）
5. 事务提交；
6. 不删除已有 review。

### 26.3 与计划的关系

- 默认 `plan_id=null`，进「未归档」；
- `--plan` 只在科目一致时生效；
- 同步后计划页立即能看到；
- 归到计划仍可走现有「归到计划」按钮；
- 已产生 session/review 的 paper 不因同步改 plan。

### 26.4 重复导入

```
source_hash 相同 → 不新建 paper
source_hash 不同、title 相同 → 警告，让用户确认
```

- 同一份卷重跑 ingest 不会产生第二份；
- 重新切题（题数/顺序变化）走 §19 的 revision 规则；
- 手工补题（如 2013 漏了 9~11）也要走同一同步函数，不单独写 SQL。

### 26.5 校正保存同步

`POST /api/paper/<id>/save` 现在只写 `result.json`。要补：

```
1. 先校验：已有 review 且题数/顺序变化 → 409
2. 写 result.json
3. sync_paper_to_app 更新文本/选项/bbox
4. 重建 crop
5. 不重置 status/review
```

`retake` / `reread` 同理。

### 26.6 手工补题

2013 的 9~11 是页面下半段补识别出来的。正式流程要支持：

```
POST /api/paper/<id>/insert-problem
  {position, no, text, latex, bbox, page}
```

- 插入后重排 position；
- 重建该页之后的 crop 编号；
- 同步 app.db；
- 已有 review 的卷禁止插入（§19）。

### 26.7 验收

```
1. 5 页 ingest → app.db paper 23 题；
2. 重跑同一批图 → 不新增 paper；
3. --plan 合法 → 直接挂计划；
4. --plan 科目不一致 → 拒绝，仍进未归档；
5. 改题干 save → app.db text 同步，review 不变；
6. 有 review 后改题数 → 409；
7. 插入 9~11 → position 连续，crop 不错位；
8. 失败 → 不写半份 paper。
```

### 26.8 失败处理

| 情况 | 处理 |
| --- | --- |
| result.json 缺失 | 不同步，保留目录 |
| 页图缺失 | 用已有 hash 失败，报告 |
| 同一 hash 不同 title | 用已有 paper，更新 title |
| 同 title 不同 hash | 警告，不自动覆盖 |
| 事务失败 | 回滚，result.json 仍保留 |
| 已有 review 改题数 | 409，提示新建 revision |
| plan_id 不存在 | 同步为未归档，报告 |

> 本次 2013 手工导入是临时操作；下一次上传前必须先把这条链路做成代码。

---

## 27. 学科 Profile 与题型路由

当前 `speech.py` 只有一段写死的：

```python
"你是数学题的苏格拉底教练……"
```

`chat_reply()` 只看 `mode=tutor/review`，没有 subject / problem_type。  
所以就算上传了英二、政治、408，tutor 还是会用数学口径讲。四科测试前必须先补这层。

### 27.1 路由输入

每次 `/api/chat` 必须带：

```json
{
  "subjectId": "english2",
  "problemType": "reading_set",
  "mode": "tutor"
}
```

来源：

- `subjectId`：paper.subject_id / app.db；
- `problemType`：problems.type；
- `mode`：tutor / review / writing。

缺省不能默认 `math2`；缺省走 `generic`，并记录 warning。

### 27.2 Profile 结构

v1 用代码内置，不入库：

```python
SUBJECT_PROFILES = {
  "math2": {...},
  "english2": {...},
  "politics": {...},
  "cs408": {...},
  "generic": {...},
}

TYPE_PROFILES = {
  "single": {...},
  "reading_set": {...},
  "cloze": {...},
  "new_type": {...},
  "translation": {...},
  "writing": {...},
  "politics_choice": {...},
  "politics_analysis": {...},
  "cs_choice": {...},
  "cs_comprehensive": {...},
  "generic": {...},
}
```

最终 system prompt：

```
BASE（苏格拉底规则）
+ SUBJECT_PROFILE
+ TYPE_PROFILE
+ MODE_PROFILE
+ 当前题目 context
```

### 27.3 各科口径

**数二**

```
步骤、依据、等价变形；不跳步；公式用 LaTeX。
```

**英二阅读 set**

```
先让学生定位题干关键词 → 回原文找证据 → paraphrase → 说明其他选项为什么错。
不逐句翻译；不直接给答案；整篇复述时讲结构 + 5 题依据。
```

**英二完型/新题型**

```
完型：上下文逻辑、搭配、复现；
新题型：段落功能、衔接、指代；
不把完型当语法填空逐空讲。
```

**英二翻译**

```
先拆句法，再处理词义，最后通顺；
允许意译，但不能漏信息。
```

**英二写作**

```
审题 → 提纲 → 成文 → 按评分点反馈；
不代写；重写必须学生自己提交。
```

**政治选择**

```
概念边界、选项陷阱、为什么对/为什么错；
不背题干；不直接报答案。
```

**政治分析**

```
审题 → 原理 → 结合材料 → 结构；
先问框架，不直接给标准答案。
```

**408 选择**

```
考点、排除、边界条件；
不把选择题讲成大题。
```

**408 大题**

```
场景 → 每问怎么做 → 复杂度/边界 → 易错点；
小问不拆 FSRS，整题复述。
```

### 27.4 题型映射

| 科目 | 题型 | problemType |
| --- | --- | --- |
| 数二 | 单题 | single |
| 英二 | 阅读 | reading_set |
| 英二 | 完型 | cloze |
| 英二 | 新题型 | new_type |
| 英二 | 翻译 | translation |
| 英二 | 写作 | writing |
| 政治 | 选择 | politics_choice |
| 政治 | 分析 | politics_analysis |
| 408 | 选择 | cs_choice |
| 408 | 大题 | cs_comprehensive |

不允许把所有题都存成 `single`；否则 router 无法区分。

### 27.5 Review 模式

`mode=review` 时：

- 仍然先听完，不主动提示；
- 数学复述整题解法；
- 阅读复述结构 + 每题证据；
- 政治复述概念边界/答题框架；
- 408 复述过程 + 复杂度/边界；
- 不因为进入 review 就放宽“不直接给答案”。

### 27.6 验收

```
1. 英二阅读不会收到“数学题”提示；
2. 阅读会追问原文证据/paraphrase/干扰项；
3. 完型不会被逐空讲语法；
4. 政治选择会问“为什么其他选项错”；
5. 408 大题会问复杂度/边界；
6. 数二口径不变；
7. 未知 subject/type → generic，不冒充数学；
8. review 模式仍不主动提示。
```

### 27.7 失败处理

| 情况 | 处理 |
| --- | --- |
| subject 缺失 | generic + warning，不默认 math2 |
| type 缺失 | single/generic，按 subject 判断 |
| profile 不存在 | generic |
| 阅读 set 没有 children | 按单题讲，提示结构缺失 |
| 408 大题没有 children | 按整题讲，不拆 FSRS |
| 写作走成题目 review | 拒绝，转 writing 模式 |
| 四科 prompt 混用 | 视为 bug，记录 subject/type |

> 四科测试的前置条件：先把 `/api/chat` 的 subjectId/problemType 打通；否则测出来的不是“英二/政治/408”，只是“数学口径套了别的题”。

---

### 27.9 公式化与语言开关

讲题页现在对所有输入都调用 `/api/normalize`：

```
语音原文 → 数学公式化 → 气泡显示
```

这个 prompt 写死“数学语音转写”。英二/政治没有公式，继续走它会把普通句子当数学表达式处理；写作也不该有公式预览。

按学科设置：

| subject | formulaMode | 说明 |
| --- | --- | --- |
| math2 | on | 正常公式化 |
| cs408 | on | 允许公式/复杂度 |
| english2 | off | 原文显示，不转 LaTeX |
| politics | off | 原文显示 |
| writing | off | 原文显示 |
| generic | off | 不猜 |

规则：

- `formulaMode=off` 时，不调用 `/api/normalize`；
- 气泡直接显示 ASR 原文；
- 不显示“公式预览/展开编辑”；
- 发送给 agent 的仍是原文；
- 数学/408 保持现状；
- TTS 仍用中文音色，不因英文材料切英文音色（v1）。

验收：

```
1. 英二阅读录入 → 不出现公式预览；
2. 数字/年份不被转成 LaTeX；
3. 数二仍正常公式化；
4. 408 公式仍保留；
5. 政治选项文字不被当公式；
6. 未知科目默认 off，不冒充数学。
```

> 四科测试时，英语/政治先关公式化；否则“公式预览”本身就会制造噪音。

---

## 28. 题型父子结构与 FSRS 归属

§27 定了 `reading_set` / `comprehensive` 等题型，但 `app.db.problems` 现在没有“父题 + 子题”的正式结构：

- 迁移时所有题都写成 `single`；
- `parent_id` 列存在，但没有使用规则；
- 阅读 5 小题、408 大题小问如果直接入库，会变成 5 个/3 个 FSRS 对象；
- 这与“一篇阅读一个 FSRS、一个 408 大题一个 FSRS”冲突。

### 28.1 题型表

| type | 是否有子题 | FSRS 在谁身上 |
| --- | --- | --- |
| `single` | 否 | 自己 |
| `reading_set` | 是（5 小题） | 父题 |
| `cloze` | 可选（空格） | 父题 |
| `new_type` | 可选（匹配项） | 父题 |
| `translation` | 可选（句子） | 父题 |
| `comprehensive` | 是（小问） | 父题 |
| `writing` | 否 | 不进 problems，进 writing_tasks |
| `politics_choice` | 否 | 自己 |
| `politics_analysis` | 否 | 自己 |
| `cs_choice` | 否 | 自己 |

### 28.2 不变量

```
1. 只有 parent_id IS NULL 的 problem 能有 review。
2. 子题不允许有 review / plan_units / queue_items。
3. 一个 reading_set 必须恰好一个父题 + N 个子题。
4. 一个 comprehensive 必须恰好一个父题 + N 个小问。
5. 子题的 no 可以是 1..5，但 FSRS 只认父题。
6. 父题删除 → 子题级联删除。
7. 父题已有 review 后，禁止改父子结构（只能新 revision）。
```

### 28.3 字段

```sql
-- 已有 parent_id；补：
ALTER TABLE problems ADD COLUMN passage TEXT;
ALTER TABLE problems ADD COLUMN payload_json TEXT;
ALTER TABLE problems ADD COLUMN position INTEGER;
```

- `passage` 存阅读/完型原文，父题独有；
- 子题 `passage` 为空，通过 parent 取；
- `payload_json` 保留原始结构；
- `position` 是卷内稳定顺序，父子都用。

### 28.4 入库规则

阅读：

```
父题：type=reading_set, parent_id=NULL, passage=原文, no=Text 1
子题：type=reading_question, parent_id=父, no=1..5
```

408 大题：

```
父题：type=comprehensive, parent_id=NULL, no=22
子题：type=comprehensive_part, parent_id=父, no=22-1..22-3
```

政治：

```
选择题：type=politics_choice, parent_id=NULL
分析题：type=politics_analysis, parent_id=NULL（不再拆小问，除非题干明确多问）
```

英语写作：

```
writing_tasks，不进 problems
```

### 28.5 入库前必须确认

- 阅读：原文 + 5 题是否属于同一篇；
- 408：小问是否属于同一个大题场景；
- 完型：是否按整篇一个 FSRS，而不是每个空；
- 翻译：是否按整篇/5 句一个 FSRS；
- 写作：是否走 writing_tasks。

自动切题无法稳定判断“同一篇/同一大题”时：

```
先按单题入库，标记 needs_grouping=1；
用户在计划页/校正页手动合并；
合并前不生成 review。
```

### 28.6 队列与计划

- `plan_units` 只为父题建 unit；
- 时间页 queue item 的 `ref_id` 指向父题；
- 打开阅读 set：显示原文 + 5 小题，一次 session；
- 结束本题：只给父题写 review；
- 计划进度：一个 reading_set 算 1 题，不是 5 题。

### 28.7 验收

```
1. 阅读 1 父 + 5 子 → reviews 只有 1 条；
2. plan_units 只有 1 个；
3. 408 1 父 + 3 子 → 同上；
4. 子题不能单独出现在 due；
5. 子题不能单独进 queue；
6. 删除父题 → 子题一起消失；
7. 父题有 review 后改父子结构 → 409；
8. writing 不建 problem、不建 review。
```

### 28.8 失败处理

| 情况 | 处理 |
| --- | --- |
| 子题被写成 parent_id=NULL | 标记 needs_grouping，不生成 review |
| 父题无 passage | 拒绝入库 reading_set |
| 阅读只有 4 子题 | 警告，允许但标记不完整 |
| 408 小问独立成题 | 合并或标记 needs_grouping |
| 子题已有 review | 拒绝合并，提示先归档 |
| 父题删除 | 级联子题；review 一并删，需先确认 |
| 题型未知 | 按 single，不猜父子 |

> 四科测试前，先保证“阅读/408 大题只产生一个 FSRS”；否则测试数据会从一开始就错。

---

## 29. sessions / turns 双写与队列耗时

`app.db` 有 `sessions` / `turns`，但现在讲题页仍走旧的 `session_store`（`tutor.sqlite`）：

- 新建 session 只写旧库；
- `/api/chat` 只往旧库追加 turn；
- `app.db.sessions` 一直是 0；
- 时间环的 `actual_min`、队列 `opened/done` 没有真实 session 可挂。

这会让“实际用时校准”“队列执行闭环”全部悬空。

### 29.1 写入顺序

```
1. session_store.get_or_create / append / end（旧源）
2. 映射 problem_id = paper:index
3. 写 app.db.sessions / turns
4. 成功 → 返回
5. 失败 → 入 session_sync outbox，返回 ok + warning
```

原则同 §21：

- 旧源成功，不能告诉用户“对话丢了”；
- mirror 失败不能回滚旧源；
- 不能静默成功。

### 29.2 outbox

```sql
CREATE TABLE IF NOT EXISTS session_sync (
  session_id TEXT PRIMARY KEY,
  payload_json TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
```

- 以 session 最新完整快照为准；
- 重试时 upsert session + 全量 turns（或按 turn id 增量）；
- 启动时 flush；
- 超过 5 次进人工对账。

### 29.3 创建

`POST /api/session` 增加：

```
paper, index, mode, model, queueItemId
```

服务端：

```
session_id = old.get_or_create(...)
problem_id = paper:index
app.db.sessions:
  id, problem_id, paper_id, mode, model,
  started_at = old.created_at,
  queue_item_id = queueItemId
```

- 同 `queue_item_id` 已有未结束 session → 复用，不新建；
- `problem_id` 不存在 → orphan，不插入假题；
- `queue_item_id` 不属于 confirmed 当天 → 拒绝。

### 29.4 追加 turn

`/api/chat` 成功后：

```
app.db.turns:
  session_id, role, content, speech, created_at
```

- role 只允许 user/assistant/system；
- 同一 `(session_id, turn_id)` 幂等；
- 旧库 turn 没有全局 id，用 `session_id + 序号 + created_at` 做去重键；
- 不把 TTS 音频写 DB，只存 speech 文本。

### 29.5 结束

`POST /api/session/<id>/end`：

```
old.end(id)
app.db.sessions.ended_at = now
```

- `actual_min = clamp((ended_at-started_at)/60, 1, 120)`；
- 若 queue_item_id 存在 → 更新 queue item actual/done（§14）；
- 重复 end 幂等，不改 actual。

### 29.6 对账

```
旧 tutor.sqlite sessions/turns
  ↕
app.db.sessions/turns
```

- 旧有、appdb 无 → 补写；
- appdb 有、旧无 → 不删，标记 app_only；
- problem_id 映射失败 → orphan，列出来；
- 只读+补写，不删除。

### 29.7 验收

```
1. 新建 session → app.db 有 1 行；
2. 发一轮 → app.db 有 user/assistant 两条 turn；
3. 刷新/重启 → session 仍可恢复；
4. end → ended_at 有值，actual_min 合理；
5. queue 项 → done + actual；
6. mirror 失败 → outbox 有记录，旧对话不丢；
7. problem 不存在 → orphan，不创建假题；
8. 重复 end/重复 turn → 不重复。
```

### 29.8 失败处理

| 情况 | 处理 |
| --- | --- |
| app.db 锁/忙 | 入 outbox，稍后重试 |
| problem 缺失 | orphan，旧对话保留 |
| queue 未确认 | 拒绝绑定，session 仍可讲 |
| 重复 session | 复用旧 id |
| 旧库损坏 | 不覆盖 app.db，报警 |
| 切 app.db 为主后旧库仍写 | 视为 bug，停写并回滚 |

> 在 §29 完成前，时间页的 actual_min 只能手填，不能假装已经从 session 自动回写。

---

## 30. 时区、日期边界与 due 比较

三环现在混用了三种时间：

```
reviews.due              ISO 时间（FSRS，通常 +00:00）
sessions.started_at       epoch 秒
daily_plans.date          YYYY-MM-DD（本地日期）
```

`app_api._due_rows()` 现在是：

```python
WHERE r.due <= ?   # now 也是 ISO 字符串
```

如果 due 里出现 `+08:00`、`Z`、`+00:00` 混用，字符串比较不等于时间比较。计划页/首页/时间页可能提前或延后一天显示到期。

### 30.1 统一格式

- 所有绝对时间：ISO 8601，带 offset；
- 写入前统一转 UTC，序列化成 `YYYY-MM-DDTHH:MM:SSZ`；
- `sessions` 继续用 epoch 秒；
- `daily_plans.date`、`weekly_budgets.week` 用 `Asia/Shanghai` 本地日期；
- 用户看到的时间默认 `Asia/Shanghai`。

### 30.2 比较规则

```
due <= now  → 解析成 datetime 比较
```

禁止：

```
字符串直接比 due
按 due 的日期部分截断
用 UTC 日期当本地日期
```

`today`：

```
local_today = date in Asia/Shanghai
week_start = local_today - weekday()
```

### 30.3 到期显示

- “当前到期” = `due_instant <= now_instant`；
- 不是 `due_date <= local_today`；
- 不显示未来日期（产品规则）；
- 跨日 due：
  - due 23:30 UTC = 次日 07:30 北京时间；
  - 北京时间早上才显示到期；
- 计划页只显示 `due` 数量，不显示日期。

### 30.4 每日计划与跨零点

- daily_plan 按本地日期；
- 00:00 后算新的一天；
- 调试模式到凌晨，不把凌晨算前一天；
- 但允许用户手动把凌晨 session 归到前一天（v1 不做自动猜测）；
- 不因为“学到凌晨”自动延长前一天配额。

### 30.5 数据库迁移

已有 due 文本：

```
1. 能解析的 → 转 UTC 标准串
2. 无 offset 的 → 视为 UTC，记录 warning
3. 无法解析的 → 保留原值，标记 invalid_due
4. 迁移前备份
```

- `invalid_due` 不进入 due 列表；
- 不静默删 review；
- 对账报告列出 invalid。

### 30.6 验收

```
1. due=00:00+08:00 在北京时间 00:00 到期；
2. due=23:30Z 在次日 07:30 北京时间到期；
3. 混用 Z / +00:00 / +08:00 排序正确；
4. 首页/计划/时间三处 due 数量一致；
5. daily_plan 用本地日期，不用 UTC 日期；
6. 周一 00:00 本地开始新周；
7. 无 offset 的旧 due 被标 warning，不静默错算；
8. 凌晨 session 不被自动算到前一天。
```

### 30.7 失败处理

| 情况 | 处理 |
| --- | --- |
| due 无 offset | 视为 UTC + warning |
| due 无法解析 | invalid_due，不显示到期 |
| 本地时区不是 +08 | 以用户设置为准，默认 Asia/Shanghai |
| 跨日 due | 按瞬时比较，不按日期截断 |
| 旧数据混格式 | 迁移标准化，保留报告 |
| 00:00 后打开 | 新 daily_plan，不沿用昨天 |

---

## 31. 2013 数二验收基线

新版目前只有这一份真实材料。测试前先固定基线，避免“感觉能讲”但数据已经错了。

### 31.1 数据库基线

```text
paper id      ingest-20261026-031615
title         2013 数二真题
plan          p_x462_mvkyasix（数二 / 真题（数二） / 2013真题）
pages         5
problems      23
no            1..23
reviews       0
sessions      0
daily_plans   0
queue_items   0
```

检查 SQL：

```sql
SELECT COUNT(*) FROM problems WHERE paper_id='ingest-20261026-031615';
-- 23

SELECT p.no FROM problems p
WHERE p.paper_id='ingest-20261026-031615'
ORDER BY p.id;
-- 1..23
```

### 31.2 已知识别修正

| 题号 | 情况 | 处理 |
| --- | --- | --- |
| 9~11 | 第一遍自动切题漏掉 | 用第 1 页下半段重新识别后插入 |
| 9 | 填空极限题 | 检查 LaTeX/题图是否对 |
| 10 | 反函数导数 | 检查积分上限/下标 |
| 11 | 极坐标面积 | 检查 `θ` 范围 |

这 3 题是人工补的，测试时优先看它们，不要只看第 1 题。

### 31.3 验收步骤

```
1. 计划页：数二 → 2013真题 → 2013 数二真题（23题）
2. 讲题页：第 1 题能显示，题图不 404
3. 第 9/10/11 题：文字、公式、题图都在
4. 第 1 题：说一段 → agent 追问（不是直接给答案）
5. 结束本题：先让你总结 → 有缺口才追问 → 再评级
6. 评级后：当前到期 +1，计划页已讲 1/23
7. 时间页：90 分钟排程，数学块先出现第 1 题复述
```

### 31.4 通过标准

- 23 题都能选到；
- 第 9~11 题题图/公式不空；
- 无 pageerror；
- 结束本题不展示 AI 摘要；
- 评级由用户点击；
- 首页/计划/时间三处到期数量一致；
- 时间页能排出“复述优先”。

### 31.5 当前已知未闭环

即使上述通过，也只是第一环：

- app.db sessions/turns 仍为 0（讲题页写旧库）；
- queue item 没有 `queue_item_id`，实际耗时不会自动回写；
- 计划没有 `plan_units`，进度靠 reviews 计数；
- 时间页周配额没有 committed 账本，重排会重复用额度。

所以这轮测试只验：

> 2013 题目能讲、能收尾、能评级、能出现在 due。

不要把这轮当成三环全部验收。

### 31.6 测试后清理

如果只是测试，不想留评级：

```
1. 备份 app.db
2. 删除该 paper 的 reviews/problem_progress
3. 删除当天 daily_plans/queue_items
4. 不删 paper/problems
```

不要删 2013 整卷，否则要重新切题。

---

## 32. 目标/任务/计划 CRUD 最小规格

计划页现在只能读：旧数据导入后，用户无法添加 2015~2026 新计划、英二新阅读计划、408 新章节。四科要往下走，必须有最小新建能力。

### 32.1 API

```
POST /api/app/goals        {subjectId, title}
POST /api/app/tasks        {goalId, title}
POST /api/app/plans        {taskId, name, year?}
PATCH /api/app/goals/<id>  {title}
PATCH /api/app/tasks/<id>  {title}
PATCH /api/app/plans/<id>  {name, year?}
POST /api/app/tasks/<id>/active-plan {planId}
```

删除/归档走 §23，不在 CRUD 里硬删。

### 32.2 校验

- subjectId 必须存在；
- goalId / taskId 必须存在且属于同一棵；
- title/name 去空格后非空；
- year 可空；能从名字解析就填；
- plan 只能挂到 task；
- 不允许跨科目挂载；
- 同一父下重名允许，但返回 warning；
- 新建 plan 时，如果 task 没有 active_plan_id，自动设为新 plan。

#### 32.2.1 归到计划的历史检查

`assign_paper()` 现在只查：

```
app.db.sessions
app.db.reviews
```

但过渡期讲题页的 session 还在旧 `tutor.sqlite`，reviews 可能只在 `reviews.json`。  
如果一份卷有旧对话、但 `app.db` 还没有对应记录，`assign_paper` 会误判“无历史”，允许换计划。

规则：

- 过渡期必须同时查旧 `session_store` 和 `reviews.json`；
- 任一有记录 → 拒绝换计划（409）；
- 等 §21/§29 双写完成后，才允许只查 `app.db`；
- 拒绝时提示“已有旧版讲题记录，先完成对账”。

验收：

```
1. 旧 tutor.sqlite 有该 paper 的 session、app.db 无 → 拒绝换计划；
2. 旧 reviews.json 有该 paper、app.db 无 → 拒绝；
3. 两边都无 → 允许；
4. 双写完成后 → 以 app.db 为准。
```

### 32.3 ID 与状态

```
g_<uuid> / t_<uuid> / p_<uuid>
```

- `source='manual'`（区别于 legacy/derived）；
- goal/task status=active；
- plan status=active；
- created_at 当前时间；
- 旧 external_id 留空。

### 32.4 UI

计划页每层一个“＋”：

```
目标 · 数二        ＋ 任务
任务 · 真题        ＋ 计划
计划 · 2013真题    （已挂整卷）
```

- 内联输入，不弹大表单；
- 回车保存，Esc 取消；
- 保存后局部刷新树，不整页跳；
- 新建计划后提示“可以归整卷了”；
- 新建目标默认选中当前科。

### 32.5 验收

```
1. 在数二下新建任务“真题二刷” → 出现在树里；
2. 在“真题二刷”下新建计划“2015” → year=2015；
3. 新计划自动成为 active_plan（原为空时）；
4. 空标题 → 拒绝；
5. 跨科目挂 task/plan → 拒绝；
6. 重名 → 允许 + warning；
7. 刷新页面后仍在；
8. 旧数据不受影响。
```

### 32.6 失败处理

| 情况 | 处理 |
| --- | --- |
| parent 不存在 | 404 |
| 空标题 | 400 |
| 跨科目 | 400 |
| 重名 | 201 + warning，不自动改名 |
| 并发重复提交 | 前端按钮禁用 + 后端幂等键（v1 可只做禁用） |
| 已归档 parent 下新建 | 拒绝，先恢复 active |
| year 非法 | 置空，不猜 |

> 没有 CRUD，计划页只能“看旧数据”，不能长出新计划；四科测试会被材料结构卡住。

---

## 33. 深耕日志

| 时间 | 轮次 | 改动 | 剩余风险 |
| --- | --- | --- | --- |
| 2026-10-26 02:18 | availability_exceptions 落地规格 | 补例外表、day_windows/day_modes、计算顺序、休息/调课/考试语义、周配额联动、7 条验收与失败处理 | 例外表尚未实现；当前时间页只收 available_min，没有自动算空闲 |
| 2026-10-26 02:21 | writing_tasks 与时间环落地规格 | 补写作状态机、rewrite_due 默认/校验、统一 due 视图、英语块排序、queue/unit 联动、8 条验收与失败处理 | 写作 due 尚未并入 `_due_rows`；计划页仍只算 FSRS |
| 2026-10-26 02:24 | 讲题页切 app.db 割接规格 | 补 pages/options/figures/payload 列、position、/api/app/paper、source=app 开关、逐卷对比、finish 切换、9 条验收与回滚 | payload 未导入；finish 仍读 result.json；图片 404 尚未检查 |
| 2026-10-26 02:27 | 整卷生命周期与重切规则 | 补 paper status/revision/source_hash、原地修正边界、重切禁止条件、删除/归档、重复导入、换 plan、8 条验收与失败处理 | 现有 `papers`/`correction` 没有 status/source_hash；重切 409 未实现 |
| 2026-10-26 02:30 | 周配额 committed/actual 账本 | 补 committed_min、remaining 公式、确认/完成/顺延/重排状态迁移、幂等、周四/周日封存、8 条验收与失败处理 | `weekly_budgets.committed_min` 未实现；`generate_time` 仍用 planned-actual，会重复排整周 |
| 2026-10-26 02:33 | 双写与对账 outbox | 补 review_sync 表、旧源先写/mirror 失败入队、启动 flush、对账规则、切换 5 条件、7 条验收与失败处理 | 当前 sync 失败直接 500 且旧源已写；outbox/orphan 未实现 |
| 2026-10-26 02:36 | 预估校准表 | 补 estimates 表、kind、中位数/去尾/样本门槛、默认表、generate_time 取值、7 条验收与失败处理 | 代码仍是 NEW_EST/REVIEW_MIN 常数；reading/408 复述仍按 8 分钟低估 |
| 2026-10-26 02:39 | 目标/任务/计划删除与归档 | 补 goals/tasks status、硬删前置检查、归档语义、级联保护、active_plan 失效、8 条验收与失败处理 | goals/tasks 无 status；现 FK 会级联删计划树，尚未加应用层保护 |
| 2026-10-26 02:42 | Schema 迁移与备份 | 补 schema_migrations、迁移文件顺序、启动流程、迁移前备份、回填规则、8 条验收与失败处理 | 现 `db.init` 仍 executescript + 手工 ALTER，无版本/备份/回滚 |
| 2026-10-26 02:45 | 旧工作台迁移与首次启动 | 补 store 两种形状、映射、未知科目 other、ID 幂等、时间表拼接/30 天、事务备份、8 条验收与失败处理 | `migrate.py` 仍默认未知科目 math2、未拆 wrapper、未拼 date+start；首次启动空态未做 |
| 2026-10-26 03:20 | ingest → app.db 同步规格 | 补 ingest 自动同步、source_hash 去重、--plan、校正/补题同步、8 条验收与失败处理 | 本次 2013 是手工 upsert；ingest.py 无同步钩子；save 仍只写 result.json |
| 2026-10-26 03:50 | 学科 Profile 与题型路由 | 补 subject/type/mode 路由、四科口径、题型映射、review 规则、8 条验收与失败处理 | speech.py 仍写死数学 prompt；/api/chat 无 subjectId/problemType |
| 2026-10-26 04:20 | 题型父子结构与 FSRS 归属 | 补 reading_set/comprehensive 父子规则、passage/payload/position、只父题有 review/unit/queue、合并与验收 | 现有题全为 single；无分组/合并 UI；子题若入库会各自生成 FSRS |
| 2026-10-26 04:50 | sessions/turns 双写与队列耗时 | 补 app.db session/turn 双写、session_sync outbox、queueItemId、actual_min、对账、8 条验收与失败处理 | app.db sessions/turns 仍为 0；讲题页只写旧 tutor.sqlite；队列耗时无来源 |
| 2026-10-26 05:20 | 当前实现状态校准 | 修正 §7/§8/§9：旧数据已导入、样本卷已删、2013 23 题已接；未实现列表改为真实缺口；下一步顺序重排 | 新版 2013 尚未完整测试；多项规格仍未落地 |
| 2026-10-26 05:50 | 时区、日期边界与 due 比较 | 补 UTC/本地日期规则、按 datetime 比较、跨日 due、凌晨归属、旧数据标准化、8 条验收与失败处理 | `_due_rows` 仍字符串比 due；daily_plan 本地日期未统一；旧 due 未标准化 |
| 2026-10-26 06:20 | 2013 数二验收基线 | 固定 paper/plan/23题/0 review 基线，标注 9~11 人工补题，列 7 步验收、通过标准、未闭环与测试后清理 | 测试后若留 review，会影响后续时间页测试；app.db session 仍为 0 |
| 2026-10-26 06:50 | 公式化与语言开关 | 补 subject.formulaMode、英二/政治/写作关闭 normalize、验收与默认 off | 讲题页仍对所有输入调用 /api/normalize；非数学会被公式化 |
| 2026-10-26 07:20 | 目标/任务/计划 CRUD 最小规格 | 补 API、校验、ID/状态、内联 UI、8 条验收与失败处理 | 计划页仍只读；无新建目标/任务/计划接口；2015+ 计划无法添加 |
| 2026-10-26 08:20 | 归到计划的历史检查 | 补过渡期同时查旧 session_store/reviews.json 的规则，防止 app.db 无记录时误换计划 | `assign_paper` 仍只查 app.db；旧会话/旧 reviews 未对账时会误判无历史 |

## 2026-10-27 当前落地补记

这一节只记已经进代码、可验证的事实；不把规格当成已实现。

- **时间环队列执行**：`review/new/writing` 都有 `todo → opened → done`；`queue_done` 回写 `actual_min` 并计入 `weekly_budgets`。写作项与定稿联动，不重复加时间。
- **讲题会话双写**：`session_store` 仍写旧库，同时把 `sessions/turns` 镜像进 app.db；旧库 61 个会话/38 条消息已回填；新对话继续双写。`reviews` 仍为 0，FSRS 评级待真实试跑验证。
- **题目状态机**：打开 session 写 `problems.status='in_session'`；`sync_review` 写 `scheduled`；`due` 由 `reviews.due` 查询推导，不在读取时反复改库。45 个测试通过。
- **计划环**：计划阶段由单元/题目状态推导为 `未开始 / 进行中 / 第一遍完成 / 已归档`；整卷按标题年份排序；`/api/app/plan/<id>/next` 返回到期最早，否则按整卷顺序的第一道未完成题；计划页显示「下一题」入口。47 个测试通过。
- **内部教案**：首次对话按题目生成并缓存 `lesson_plans`（目标、核心、路径、预期卡点/提示、收尾检查、同一卡点最多追问 2 次），只注入 system context 供教练安排追问，不显示给学生；2009 408 第 1 题已生成样例。52 个测试通过。
- **刷新后的上次提示**：题目页显示这题上次练习时间、轮次、是否还没结束；未结束的会话发第一句会接回旧对话；53 个测试通过。
- **政治**：平台不导入政治题；可用 ≥120 分钟时保留 30 分钟 `offline` 自主块，不生成“下一道新题”。
- **写作计划单元**：新增 `writing_plan_units`；34 篇写作计入英语二计划，总单元 153（119 阅读/完型 + 34 写作）；定稿同步 `finished`。
- **写作批改**：`must_fix` 只收五类硬伤（图表数据、要求覆盖、段落逻辑、句子可读、影响意思的语法）；`optional` 不影响定稿；无硬伤状态 `ready`，不设 `rewrite_due`；评分默认隐藏。
- **英语二完型**：17 套选项均 20 行；文章重新 OCR 后复核，2014 仅空格差异，判定稳定；定时复核任务已删除。
- **数学图题**：1991/2001/2003/2005/2008/2015/2016 已挂图；1994 源 PDF 缺图，暂放。
- **408 2009 第 4 题**：四个树形选项拆成 A-D 图片，2×2 渲染。
- **TTS**：默认走云端 `qwen3-tts-flash`（本地 Serena 有时读不出，先停用）；本地 TTS 保留为可选，设 `TUTOR_TTS_PROVIDER=local` 再开。ASR 仍为云端，本地 ASR 暂不做。
- **仍等用户**：写作模板照片、统一试跑、写作真实草稿；见 `tutor/docs/user-pending.md`。

