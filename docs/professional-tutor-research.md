# 如何让 tutor API 更像专业 tutor

更新时间：2026-10-28

## 研究问题

现在的 API 已经能：

- 读题；
- 生成内部教案；
- 按苏格拉底方式追问；
- 连续追问两次后强制给提示；
- 收尾时让用户总结、评级。

但真实试跑暴露了问题：

```text
学生：这题选 B。
tutor：依据是什么？
学生：先入先出。
tutor：题目哪一句能说明？
学生：依次写入，依次取出。
tutor：具体一点，打印机先取哪个？
学生：进行不下去了。
```

这不是“不专业”的单点问题，而是 API 的**行为模型**还不够像老师。

## 一、现在 API 的实际行为

### 1. 它主要是一个“追问生成器”

`speech.chat_reply` 的输入是：

```text
system prompt + 当前题目 + 最近对话
```

输出是自由文本：

```json
{"text": "...", "speech": "..."}
```

它没有显式的“这一步要做什么”：

- 是诊断？
- 是给提示？
- 是让学生复述？
- 是纠正错误？
- 是推进到下一步？
- 还是该收尾？

模型只能靠 prompt 自己猜。  
prompt 里规则越多，它越容易抓住最显眼的一条：**继续问**。

### 2. 教案没有驱动决策

`lesson_plans` 里有：

- goal；
- core；
- path；
- stuck.hint / stuck.next；
- finish_check。

但目前只做两件事：

1. 塞进 system context；
2. 卡住时取第一条 hint 兜底。

它没有告诉 API：

- 现在讲到 path 的第几步；
- 这个学生卡在哪个概念；
- 已经给过几级提示；
- 下一次该检查什么。

### 3. 没有“学生动作”识别

专业老师听到学生一句话，先判断：

```text
这是答案？依据？猜测？提问？跑题？情绪？
```

现在 API 不做分类，直接把整段对话丢给模型。

结果：

- 学生说“选 B”，它继续问依据；
- 学生说“因为先入先出”，它还问“题目哪一句”；
- 学生说“进行不下去”，它可能继续追问；
- 直到服务端硬限制才停。

### 4. 只有“问”，缺少其他教学动作

专业 tutor 至少有六类动作：

| 动作 | 什么时候用 |
| --- | --- |
| 诊断 | 先判断卡点类型 |
| 追问 | 学生有思路但依据不足 |
| 提示 | 学生卡住，给一级线索 |
| 示范 | 学生完全没方法，示范一小步 |
| 检查 | 学生说“懂了”，让他复述/迁移 |
| 推进/收尾 | 这一步过了，进入下一步 |

现在系统几乎只有“追问”，偶尔有“提示”。  
所以学生感觉像被审讯，而不是被教。

## 二、专业 tutor 的行为标准

综合支架式教学、认知学徒制、 formative assessment 和刻意练习，专业 tutor 不是“少讲”，而是：

### 1. 先诊断，再回应

不是所有卡住都该问。

```text
概念不清 → 补概念
方法不会 → 示范一小步
计算错 → 定位错误
题意不清 → 复述题意
表达不清 → 要求说清
情绪崩 → 先降难度/暂停
```

### 2. 提示有层级

```text
Level 0：追问依据
Level 1：指方向（看哪个条件/哪一句）
Level 2：给半成品（开头/公式/对比）
Level 3：示范一小步，然后让学生接
Level 4：完整讲解（只在明确要求时）
```

每升一级，必须减少一个问题，增加一个信息。

### 3. 同一卡点最多两次追问

第二次后必须：

- 确认学生已经说对的部分；
- 给一个最小提示；
- 或推进到下一步。

不能第三次还问“为什么”。

### 4. 让学生复述，而不是替学生总结

专业老师会检查：

- 你能用自己的话说一遍吗？
- 如果条件变了，这一步还成立吗？
- 你能举一个反例吗？

### 5. 反馈要具体、可执行

不专业：

```text
再想想。
具体一点。
还有呢？
```

专业：

```text
你漏了“打印机按提交顺序取”这个条件。
先补这一句，再选。
```

### 6. 有节奏和收束

一节课要有：

- 开场定位；
- 中段推进；
- 卡点处理；
- 收尾检查；
- 下一步。

不能无限停在同一个点。

## 三、API 应该怎么改

### 方案 A：只改 prompt（不够）

继续加规则：

```text
不要连续追问。
每次最多问一个问题。
学生卡住就给提示。
```

问题：

- 模型仍可能忽略；
- 规则越多越互相冲突；
- 无法保证行为。

今天已经验证：prompt 写了“最多两次”，模型仍会循环，最后靠服务端硬限制才停。

### 方案 B：服务端策略层（推荐）

在 `chat_reply` 前加一个**教学决策层**：

```text
学生这句话
  ↓
识别学生动作
  ↓
更新教学状态
  ↓
选择教学动作
  ↓
生成回复
  ↓
服务端检查回复是否符合动作
```

#### 1. 学生动作分类

```json
{
  "move": "answer | reason | stuck | question | off_topic | frustration | request_explain",
  "confidence": 0.0,
  "signals": ["不知道", "选B", "为什么"]
}
```

可以先用规则 + 小模型分类，不必上大模型。

#### 2. 教学状态

```json
{
  "subgoal": "说出缓冲区为什么是队列",
  "diagnosis": "concept_confusion",
  "hint_level": 1,
  "questions_on_this_point": 2,
  "evidence_seen": false,
  "plan_step": 2
}
```

#### 3. 教学动作

```json
{
  "action": "probe | hint | explain | check | advance | close",
  "hint_level": 1,
  "must_include": ["一个提示", "一个下一步"]
}
```

#### 4. 回复契约

API 不再只返回自由文本，而是：

```json
{
  "action": "hint",
  "display": "你抓到了“依次”，但还差一个条件：打印机先取谁？",
  "speech": "你抓到了依次，但还差一个条件：打印机先取谁？",
  "next_check": "让学生用自己的话说出先进先出"
}
```

服务端可以校验：

- `action=hint` 时，不能只有问句；
- 连续两次 `probe` → 第三次强制 `hint`；
- `action=close` 时，必须让学生总结。

### 方案 C：教案升级为“教学剧本”

当前教案：

```json
{
  "goal": "...",
  "core": ["..."],
  "path": ["..."],
  "stuck": [{"point": "...", "hint": "...", "next": "..."}]
}
```

建议增加：

```json
{
  "prerequisites": ["..."],
  "misconceptions": [
    {"wrong": "栈也可以", "why": "把后进先出当成了先进先出", "contrast": "..."}
  ],
  "hint_ladder": [
    {"level": 1, "cue": "看题目里‘依次’两个字"},
    {"level": 2, "cue": "先写进去的先取出来"},
    {"level": 3, "cue": "队列的入队/出队顺序"}
  ],
  "check_questions": ["为什么不是栈？", "如果打印机先取最后一个会怎样？"],
  "success_criteria": ["能说出 FIFO", "能排除栈"]
}
```

教案不再只是“参考”，而是：

- 当前步骤；
- 可用提示；
- 检查问题；
- 收尾标准。

## 四、最小可行改造

### P0：加动作标签

不重写模型，只让 API 输出：

```json
{"action": "probe|hint|explain|check|advance", "text": "...", "speech": "..."}
```

服务端记录连续动作，强制执行：

- 连续 2 次 `probe` → 下一次必须 `hint`；
- `hint` 后必须 `check` 或 `advance`；
- `close` 前必须 `check`。

### P1：教案接进决策

每轮读取教案：

- 当前 `path` 第几步；
- 这个学生卡在哪个 `stuck`；
- `hint_ladder` 用到第几级；
- `check_questions` 是否问过。

### P2：学生模型

记录：

- 哪些概念反复错；
- 哪些提示有效；
- 哪类题需要示范；
- 哪些题总在同一个点卡住。

### P3：评估

用 10 个脚本化学生测：

- 说答案不说依据；
- 说错概念；
- 说“不会”；
- 说“进行不下去”；
- 说“直接讲”；
- 说“懂了”；
- 跑题；
- 情绪崩。

指标：

- 无必要追问率；
- 卡点后给提示的轮数；
- 循环率；
- 学生复述率；
- 收尾完成率；
- 学生自己说“我知道下一步做什么”的比例。

## 五、结论

现在的 API 像“会追问的答题助手”，还不像专业 tutor。

专业 tutor 的核心不是“问得更狠”，而是：

```text
诊断 → 决定动作 → 给恰当提示 → 检查理解 → 推进
```

最值得先做的不是继续加 prompt，而是：

1. 让 API 显式输出 `action`；
2. 服务端按动作和次数强制执行；
3. 教案从“背景材料”升级为“当前步骤 + 提示阶梯 + 检查点”。

这样即使模型想循环，API 也会把它拉回教学流程。

---

# 六、v2 方案：教学策略层

## 6.1 总体结构

```text
学生一句话
  ↓
student_move 分类
  ↓
TutorState 更新
  ↓
action 选择（规则优先）
  ↓
生成回复（模板约束 + 模型润色）
  ↓
reply 校验
  ↓
返回 text / speech / action / state
```

关键原则：

> 模型负责“说得像人”，规则负责“做得像老师”。

不能让模型同时决定：

- 现在是什么教学动作；
- 要不要继续追问；
- 什么时候推进；
- 什么时候收尾。

这些必须由状态机决定。

## 6.2 请求契约

```json
{
  "session_id": "...",
  "student_text": "这题选 B",
  "history": [],
  "lesson_plan_id": "ingest-408-2009:1",
  "subject": "cs408",
  "problem_type": "cs_choice",
  "tutor_state": {
    "plan_step": 1,
    "current_subgoal": "说出为什么是队列",
    "diagnosis": "none",
    "hint_level": 0,
    "probes_on_point": 0,
    "checked": false,
    "last_action": "none"
  }
}
```

## 6.3 响应契约

```json
{
  "action": "probe|hint|explain|check|advance|close",
  "display": "给屏幕看的文本",
  "speech": "给语音朗读的文本",
  "state_patch": {
    "plan_step": 1,
    "current_subgoal": "...",
    "diagnosis": "method",
    "hint_level": 1,
    "probes_on_point": 1,
    "checked": false
  },
  "next_check": "让学生用自己的话说出 FIFO",
  "must_include": ["一个提示", "一个下一步"]
}
```

## 6.4 动作状态机

| 当前动作 | 学生下一步 | 下一个动作 |
| --- | --- | --- |
| probe | 给了依据 | check / advance |
| probe | 仍只报答案 | probe（最多 2 次） |
| probe | 说不会/卡住 | hint |
| hint | 能接话 | check |
| hint | 仍不会 | hint 升一级，最多 3 级 |
| check | 复述正确 | advance |
| check | 复述有缺口 | hint |
| advance | 到下一步 | probe 或 check |
| close | — | 必须已有 check |

硬约束：

```text
probes_on_point 最大 2
hint_level 最大 3
hint 后不能立刻 probe
close 前必须 checked=true
```

## 6.5 学生动作分类

先用规则，够用再上模型：

| 信号 | move |
| --- | --- |
| “选 B”“答案是 3”没依据 | answer |
| “因为/所以/先/后/依据” | reason |
| “不知道/不会/卡住/进行不下去” | stuck |
| “直接讲/给我完整解法” | request_explain |
| “懂了/明白了/会了” | claim_understanding |
| 问号，问概念 | question |
| 聊别的 | off_topic |
| 骂/崩/想放弃 | frustration |

分类错误时：

- 低风险：按 `answer` 处理；
- 高风险：`stuck` 优先于 `answer`。

## 6.6 教案 v2

```json
{
  "goal": "...",
  "prerequisites": ["..."],
  "core": ["..."],
  "path": ["..."],
  "misconceptions": [
    {"wrong": "...", "why": "...", "contrast": "..."}
  ],
  "hint_ladder": [
    {"level": 1, "cue": "..."},
    {"level": 2, "cue": "..."},
    {"level": 3, "cue": "..."}
  ],
  "check_questions": ["..."],
  "success_criteria": ["..."],
  "max_followups": 2
}
```

当前已有：

- goal/core/path/stuck；
- max_followups。

需要补：

- prerequisites；
- misconceptions；
- hint_ladder；
- check_questions；
- success_criteria。

## 6.7 在现有代码上的最小接入

### 接入点 1：`tutor_server._chat`

在现有 `force` 判断前：

```python
move = tutor_policy.classify_move(text)
action, state = tutor_policy.next_action(tutor_state, move)
```

如果 `action == "probe"` 且 `state.probes_on_point >= 2`：

```python
action = "hint"
```

### 接入点 2：`speech.chat_reply`

增加参数：

```python
chat_reply(..., action="probe", must_include=[], lesson_plan=None)
```

system prompt 只负责“把这个动作说自然”，不再决定动作。

### 接入点 3：`lesson_plans`

把 `plan_json` 从：

```text
背景材料
```

升级为：

```text
当前步骤 + 提示阶梯 + 检查点
```

每轮把 `plan_step`、`hint_level`、`probes_on_point` 写回 session 状态。

## 6.8 分阶段落地

### P0：动作标签 + 校验

- 返回 `action`；
- 服务端校验连续 probe；
- 前端不改也能跑（只用 text/speech）。

验收：

- 连续 probe ≤2；
- 卡住后 1 轮内 hint。

### P1：教案驱动

- 读取教案 `path` / `hint_ladder` / `check_questions`；
- 当前步骤由教案决定；
- 收尾检查用 `finish_check`。

验收：

- 同一题两次会话，教学顺序一致；
- 收尾覆盖 80% 检查点。

### P2：学生模型

- 记录哪类卡点反复出现；
- 记录哪级提示有效；
- 下次先给更合适的提示。

非目标，不先做。

---

# 七、评估与验收

## 7.1 脚本化学生

8 个脚本：

| 编号 | 脚本 | 期望 |
| --- | --- | --- |
| S1 | 只报答案 | probe |
| S2 | 给依据 | advance/check |
| S3 | 连说不会 | hint |
| S4 | 明确卡住 | hint，禁止 probe |
| S5 | 直接讲 | explain |
| S6 | 假懂 | check |
| S7 | 循环 | probe≤2 → hint |
| S8 | 跑题 | redirect |

## 7.2 指标

| 指标 | 通过线 |
| --- | --- |
| 连续 probe | ≤2 |
| 卡住后提示轮数 | ≤1 |
| 循环率 | 0 |
| 假懂后 check | 100% |
| 收尾覆盖 finish_check | ≥80% |
| 学生话轮占比 | ≥50% |
| 无必要追问率 | 0 |

## 7.3 验证顺序

1. 离线 `policy_sim.py` 跑 8 个脚本；
2. 在线 A/B：同一段脚本，旧 API vs 新 API；
3. 真实会话 1 道 408 + 1 道数学；
4. 人工只看 4 件事：
   - 有没有在该提示时提示；
   - 有没有在该推进时推进；
   - 有没有循环；
   - 学生有没有说出下一步。

---

# 八、已落盘证据

本轮研究产物：

```text
research/20261028-1844-.../evidence/
  current-api-audit.md     当前 API 行为审计
  loop-session.md          真实 22 轮循环会话
  policy_sim.py            策略层最小原型
  policy-sim-output.txt    5 个脚本场景输出
  action-contract.json     动作/状态契约
  lesson-plan-v2.json      教案 v2 样例
  evaluation-plan.md       脚本化学生与阈值
```

已确认：

- `policy_sim.py` 5 个场景 `ALL_OK=True`；
- 连续 probe 未超过 2；
- 真实会话证明 prompt 不能保证行为；
- 教案目前只做 context + 兜底，未驱动每一步。

---

# 九、结论

更专业的 tutor API 不是“更会问”，而是：

```text
先判断学生这句话是什么
再决定这一轮该做什么
再决定说不说、说什么、说多少
最后检查学生有没有接住
```

最小可落地方案：

1. **P0**：动作标签 + 服务端校验；
2. **P1**：教案 v2 驱动路径、提示、检查；
3. **P2**：学生模型与长期复盘。

先做 P0，不改前端，也能立刻减少循环。

---

# 十、接入证据（实际代码与 patch）

## 10.1 当前代码位置

| 文件 | 位置 | 现状 |
| --- | --- | --- |
| `tutor/server/tutor_server.py` | `_chat`，约 390-445 行 | 教案拼 context；连续两次问号后强制 hint；无 action |
| `tutor/server/speech.py` | `chat_reply`，204-221 行 | 只返回 text/speech |
| `tutor/server/app_api.py` | `get_lesson_plan` 495 行、`save_lesson_plan` 509 行、`append_turn` 592 行 | 教案读写 + turn 写入；无 session 教学状态 |
| `tutor/server/db.py` | `lesson_plans`，135-141 行 | 只有教案表 |

## 10.2 教案字段未进入决策

grep `finish_check|hint_ladder|plan_step`：

```text
speech.py:339  "finish_check": [...]
speech.py:379  "finish_check": [...]
```

`tutor_server.py` / `app_api.py` 中没有这些字段的引用。  
说明教案目前只做：

- system context；
- `_force_hint` 第一条 `stuck.hint`。

## 10.3 P0 最小改动

### db.py 新增

```sql
CREATE TABLE IF NOT EXISTS tutor_states (
  session_id TEXT PRIMARY KEY,
  state_json TEXT NOT NULL,
  updated_at INTEGER NOT NULL
);
```

### app_api.py 新增

```python
def get_tutor_state(session_id):
    row = c.execute(
        "SELECT state_json FROM tutor_states WHERE session_id=?", (session_id,)
    ).fetchone()
    return json.loads(row["state_json"]) if row else {}

def save_tutor_state(session_id, state):
    c.execute(
        "INSERT INTO tutor_states(session_id,state_json,updated_at) VALUES(?,?,?) "
        "ON CONFLICT(session_id) DO UPDATE SET "
        "state_json=excluded.state_json,updated_at=excluded.updated_at",
        (session_id, json.dumps(state, ensure_ascii=False), db.now()),
    )
```

### tutor_server._chat 改动

```python
move = tutor_policy.classify_move(text)
state = app_api.get_tutor_state(sid) or {}
action, state = tutor_policy.next_action(state, move)

r = speech.chat_reply(
    ..., action=action, must_include=tutor_policy.must_include(action, plan)
)
if not tutor_policy.validate_reply(action, r.get("text", ""), state):
    r = tutor_policy.fallback(action, plan, state)
app_api.save_tutor_state(sid, state)
```

### speech.chat_reply

```python
def chat_reply(..., action="probe", must_include=None, lesson_plan=None):
```

system prompt 只负责把 `action` 说自然，不再决定动作。

## 10.4 为什么 `app_api` 必须改

`_chat` 每次请求都重新拿 `body.history`，但历史只说明“说过什么”，不说明：

- 这个卡点问了几次；
- 提示到第几级；
- 是否已经 check 过；
- 当前在教案第几步。

这些必须按 `session_id` 持久化，否则服务重启或刷新后状态丢失。  
`tutor_states` 就是最小状态表。

## 10.5 证据文件

- `research/20261028-1844-.../evidence/integration-code.md`
- `research/20261028-1844-.../evidence/professional-tutor-research-proof.md`
- `research/20261028-1844-.../evidence/loop-session-raw.jsonl`
- `research/20261028-1844-.../evidence/loop-session-stats.json`

## 10.6 当前限制

- 以上 patch 未应用（研究阶段，不改稳定逻辑）；
- `tutor_policy.py` 目前只在研究原型里；
- 需要先做 P0 A/B，再考虑迁移生产。


