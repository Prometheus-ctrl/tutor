# tutor 专业化与场景适配研究

更新时间：2026-10-28

目标：让 tutor 不只是“会追问”，而是更专业、能适配更多科目/场景、更像真人老师。

## 范围

### 1. 更专业

- 诊断学生动作（答案/依据/卡住/假懂/跑题/情绪）；
- 教学动作（probe/hint/explain/check/advance/close）；
- 提示阶梯；
- 教案驱动；
- 收尾检查。

已有基础：

- `tutor/docs/professional-tutor-research.md`；
- `lesson_plans`；
- 连续追问兜底。

### 2. 更多科目

- 数二：步骤、依据、计算；
- 英二阅读/完形/新题型/翻译；
- 408 选择/大题；
- 写作：初稿/反馈/重写/定稿；
- 政治：平台不做题，但保留在计划预算。

### 3. 更多场景

- 只有语音、识别有错；
- 学生只报答案；
- 学生说“不知道”；
- 学生假懂；
- 学生情绪崩/想放弃；
- 复习复述；
- 写作卡字数；
- 中断后续讲；
- 考试模式（只给提示，不展开）。

### 4. 更人性化

- 语气自然，不机械重复；
- 不奉承、不羞辱；
- 一次只推进一个点；
- 学生卡住先降难度；
- 学生说“别问了”就停；
- 收尾让用户自己总结。

## 每轮只做一个问题

顺序建议：

1. P0 动作/状态最小接入；
2. 假懂/跑题/情绪三类场景；
3. 英语阅读/写作、408 大题差异；
4. 提示阶梯与教案 v2；
5. 收尾检查与长期复盘。

## 记录格式

追加到本文件：

- 问题；
- 实验/验证；
- 结果；
- 判断；
- 改动；
- 下一次。

## 停止条件

- 连续 3 次无新证据/无代码改动；
- 或核心动作契约、场景适配、评估方案已稳定；
- 降为每周复盘或删除。

## 不做

- 不训练模型；
- 不重写整个前端；
- 不改稳定版；
- 不修改用户数据；
- 不 git push。

## 2026-10-28 19:21

**问题**：P0 教学策略层能不能先独立于模型跑通？

**实验/验证**：

- 新增 `tutor/server/tutor_policy.py`：
  - `classify_move`：answer / reason / stuck / request_explain / claim_understanding / question / off_topic；
  - `next_action`：probe / hint / explain / check / advance / redirect；
  - `validate_reply`：probe 单问号、hint 必有线索、check 必复述、close 必 checked；
  - `fallback_text`：断循环兜底。
- 新增 `test_tutor_policy.py`，覆盖 8 类学生动作与回复契约。

**结果**：

- 65 个测试通过；
- 连续 probe 到第 3 次自动转 hint；
- stuck 不 probe；
- 假懂转 check；
- 校验能拦住多问号 probe、纯反问 hint。

**判断**：

- 策略层可以独立于模型执行；
- 还没接 `_chat`，所以线上行为未变；
- 下一步是加 `tutor_states` 和 shadow 模式，先记录不拦截，再逐步拦截。

**改动**：

- `tutor/server/tutor_policy.py`
- `tutor/tests/test_tutor_policy.py`

**下一次**：

- 加 `tutor_states` 表与 `app_api.get/save_tutor_state`；
- 在 `_chat` 里先 shadow 记录动作与校验结果，不改回复。

## 2026-10-28 19:28

**问题**：教学状态怎么按 session 持久化，能不能先不改变线上回复？

**实现**：

- `tutor_states(session_id, state_json, updated_at)`；
- `app_api.get_tutor_state` / `save_tutor_state`；
- `_chat` 里 shadow：
  - 分类学生动作；
  - 推进一步 action；
  - 校验模型回复；
  - 把 `probes / hint_level / last_move / last_valid` 写入 `tutor_states`；
  - 不修改模型回复，不拦截。

**结果**：

- 66 个测试通过；
- 状态表可读写；
- 已有对话不会因 shadow 改变。

**判断**：

- 先收集真实 `last_valid` 和 `probes` 分布；
- 如果 shadow 显示大量 `valid=False`，下一轮再加拦截；
- 如果 shadow 稳定，再让 action 控制回复。

**改动**：

- `tutor/server/db.py`
- `tutor/server/app_api.py`
- `tutor/server/tutor_server.py`
- `tutor/tests/test_tutor_state.py`

**下一次**：

- 看真实 session 的 `tutor_states`；
- 选一个高频 invalid 场景做拦截 A/B。

## 2026-10-28 19:38

**问题**：tutor 怎么适配不同科目和场景，而不是一套追问走天下？

**实验/实现**：

- 检查 `tutor_states`：暂无新 shadow 会话（0 条），说明还没人刷新后继续聊；
- 新增 `tutor_scenarios.py`：
  - 科目约束：数二、英二、408、写作；
  - 场景约束：只报答案、给依据、卡住、假懂、情绪崩、跑题、复习、考试；
  - 返回 focus / must / avoid / action / max_probes。

**结果**：

- 写作 `max_probes=0`；
- 英二 `max_probes=1`；
- 408/数二 `max_probes=2`；
- 卡住/情绪崩/跑题永不 probe；
- 假懂转 check；
- 考试模式不 probe；
- 71 个测试通过。

**判断**：

- 多科目适配已经从“只改 prompt”变成可测试的策略数据；
- 但还没接 `_chat`，线上行为未变；
- 需要真实 shadow 数据后再决定是否按科目收紧。

**改动**：

- `tutor/server/tutor_scenarios.py`
- `tutor/tests/test_tutor_scenarios.py`

**下一次**：

- 在 `_chat` shadow 中加入科目/场景组合，记录 subject-specific invalid；
- 选英二或 408 做一次真实 A/B。

## 2026-10-28 19:40

**问题**：shadow 记录能不能区分科目和场景，而不是只看动作？

**实现**：

- `_chat` shadow 增加：
  - `subject`（数二/英二/408）；
  - `situation`（answer_only/reason/stuck/fake_understanding/off_topic）；
  - `max_probes`（按科目/场景矩阵）；
  - `over_budget`（实际 probe 是否超过该科目预算）。
- 只记录，不改回复。

**结果**：

- 71 个测试通过；
- 英二预算 1、408/数二 2、写作 0；
- 卡住/跑题不 probe；
- 线上行为未变。

**判断**：

- 现在可以按科目统计“追问超预算”比例；
- 还没有新真实 shadow 数据，无法做 A/B；
- 需要用户真正聊几句才能验证。

**改动**：

- `tutor/server/tutor_server.py`

**下一次**：

- 找一门科目做真实 A/B（优先英二，因为预算最紧）；
- 如果 shadow 里英二 over_budget 多，就把业务代码切到实际拦截。

## 2026-10-28 19:43

**问题**：情绪崩和普通卡住应该分开处理吗？

**实现**：

- `tutor_policy` 新增 `frustration` 动作分类；
- 新增 `pause` 教学动作；
- 兜底话术：
  - 先停一下；
  - 给三个选择：休息两分钟 / 只做一小步 / 换一道；
  - 不追问、不讲大道理。
- `_chat` shadow 把 frustration 也记录到 `tutor_states`。

**结果**：

- 72 个测试通过；
- “我不想做了”不再被当成普通 stuck；
- 线上回复仍不变。

**判断**：

- 情绪场景需要独立动作，不能只用 hint；
- 下一步要接真实 shadow，看 frustration 是否被正确识别。

**改动**：

- `tutor/server/tutor_policy.py`
- `tutor/server/tutor_server.py`
- `tutor/tests/test_tutor_policy.py`

**下一次**：

- 检查真实 `tutor_states` 的 frustration/over_budget；
- 做一次语气/节奏的人性化评审。

## 2026-10-28 19:47

**问题**：tutor 的反馈会不会太机械、奉承、空泛？

**实现**：

- `base.md` 新增“反馈语气”：
  - 不奉承、不羞辱；
  - 不用“再想想/具体一点/还有呢”；
  - 表扬只给事实；
  - 批评只指错误，不指人。
- `tutor_policy.style_flags`：
  - `praise`：太棒了/完美/太聪明；
  - `vague`：再想想/具体一点/还有呢；
  - `multi_question`：一轮多个问号。
- `_chat` shadow 记录 `style_flags`。

**结果**：

- 73 个测试通过；
- `base.md` 是线上 prompt，语气规则已生效；
- style flags 只 shadow 记录，不拦截。

**判断**：

- 人性化先从“不空泛、不奉承”开始，比加鼓励话更稳；
- 需要真实对话看 style_flags 分布，再决定是否拦截。

**改动**：

- `tutor/prompts/base.md`
- `tutor/server/tutor_policy.py`
- `tutor/server/tutor_server.py`
- `tutor/tests/test_tutor_policy.py`

**下一次**：

- 看真实 style_flags；
- 如果 `vague` 多，把“再想想/具体一点”加进拦截；
- 再做一次跨科目语气对比。

## 2026-10-28 19:48

**问题**：教案能不能从“路径 + 卡点”升级成可执行的提示阶梯？

**实现**：

`make_lesson_plan` 新增字段：

- `prerequisites`
- `misconceptions`
- `hint_ladder`
- `check_questions`
- `success_criteria`

解析时做列表清洗、限制条数，保留原有 `goal/core/path/stuck/finish_check`。

**结果**：

- 73 个测试通过；
- 旧缓存教案仍可读，新教案带 v2 字段；
- 线上对话未改，教案只在新题生成时使用。

**判断**：

- 教案已经从“背景材料”接近“教学剧本”；
- 还差两件事：
  1. `_chat` 用 `hint_ladder` 而不是只看 `stuck[0]`；
  2. 收尾用 `finish_check` / `check_questions`。

**改动**：

- `tutor/server/speech.py`
- `tutor/tests/test_lesson_plan.py`

**下一次**：

- 收尾接 `finish_check`；
- 如果旧教案缺 v2 字段，不重新生成，使用兼容路径。

## 2026-10-28 19:49

**问题**：收尾检查是不是还在另起一套 rubric？

**实现**：

- `speech.merge_finish_check`：把教案的 `finish_check` / `check_questions` 并入内部 rubric；
- `_finish_start` 生成 rubric 后合并教案检查点；
- `_finish` 旧接口也合并；
- `evaluate_summary` prompt 增加“教案要求覆盖的收尾点”和“可用检查问题”。

**结果**：

- 74 个测试通过；
- 教案有检查点时，收尾会按这些点检查；
- 旧教案没有字段时自动跳过，不强制重生成。

**判断**：

- 教案与收尾终于使用同一套检查点；
- 线上收尾行为会变，但只影响总结追问，不影响评分算法；
- 需要一次真实收尾验证问题是否更聚焦。

**改动**：

- `tutor/server/speech.py`
- `tutor/server/tutor_server.py`
- `tutor/tests/test_lesson_plan.py`

**下一次**：

- 真实做一次收尾，观察是否少问无关问题；
- 再评估 `hint_ladder` 接入 `_chat`。

## 2026-10-28 19:50

**问题**：强制提示是不是每次都取同一条，导致提示没有层级？

**实现**：

- `_force_hint(plan, text, level)` 按 `hint_level` 从 `hint_ladder` 取对应线索；
- 没有 ladder 时仍回退到 `stuck[0].hint`；
- `_chat` 从 `tutor_states` 读 `hint_level` 后传入；
- 提示后仍附 `next` 动作。

**结果**：

- 75 个测试通过；
- 第一次强制提示用第 1 级线索，下一次用第 2 级；
- 旧教案无 ladder 时兼容。

**判断**：

- 提示从“一句话重复”变成“逐级升高”；
- 线上强制提示行为已变化，需真实试跑观察是否更好；
- 如果学生仍不会，第三级后应建议暂停/换题，不再无限升。

**改动**：

- `tutor/server/tutor_server.py`
- `tutor/tests/test_socratic_guard.py`

**下一次**：

- 真实触发两次“不知道”，看提示是否升级；
- 如果仍卡，加“第三级后暂停”限制。

## 2026-10-28 19:50

**问题**：三级提示后还不会，继续升级还是停？

**实现**：

- `_force_hint` 在 `hint_level >= 3` 时不再给新提示；
- 改为暂停话术：
  - 已给三级提示；
  - 可选择看一小段解析、换一道、休息两分钟。

**结果**：

- 76 个测试通过；
- 第 1～3 级提示仍逐级升级；
- 第 4 次卡住进入暂停，不再无限循环。

**判断**：

- 教学上比“继续追问/继续提示”更合理；
- 线上强制提示行为已变化；
- 需要真实试跑确认暂停话术不显生硬。

**改动**：

- `tutor/server/tutor_server.py`
- `tutor/tests/test_socratic_guard.py`

**下一次**：

- 用真实会话验证：三次不知道后是否进入暂停；
- 若暂停话术太长，缩成一句 + 一个选择。

## 2026-10-28 19:52

**问题**：怎么量化“像不像 tutor”，而不只靠感觉？

**实现**：

- 新增 `tutor_eval.py`：
  - 读真实 session turns；
  - 统计 assistant 问句数、最长连续问句；
  - 用 `tutor_policy` 重放学生动作，得到模拟 probe/hint/advance；
  - 统计 style flags（praise/vague/multi_question）。
- 用真实 22 轮会话 `f2ddb64211bb4515a0118f75699c66f4` 跑了一次。

**结果**：

- 真实：assistant 问句 11，最长连续问句 11；
- 模拟策略：最长连续 probe 1，最终 hint_level 3；
- style flags：`multi_question=1`；
- 78 个测试通过。

**判断**：

- 评估脚本能把“循环”量化，不再靠主观感觉；
- 真实 11 连问与策略模拟 1 连问的差距，说明策略层还有很大空间；
- 注意：模拟不是线上行为，只用于评估策略逻辑。

**改动**：

- `tutor/server/tutor_eval.py`
- `tutor/tests/test_tutor_eval.py`

**下一次**：

- 用 `tutor_eval.py` 对比 A/B 两条会话；
- 把 `multi_question` 也加入后续拦截候选。

## 2026-10-28 19:53

**问题**：模型一轮问多个问题，学生要先拆问题，怎么办？

**实现**：

- `tutor_policy.sanitize_questions`：只保留第一个问句；
- `_chat` 在返回前检测 `multi_question`，命中就裁剪 `text` 和 `speech`；
- 裁剪发生在写入 session 前，历史里也只保留一个问句。

**结果**：

- 79 个测试通过；
- “那 B 为什么错？C 呢？” → “那 B 为什么错？”；
- 线上回复已变化，但只影响多问号情况。

**判断**：

- 这是第一个真正拦截回复的规则，比 shadow 更进一步；
- 风险是可能裁掉有价值的信息；先观察真实对话；
- 如果学生反馈信息不足，再改成“保留一个主问 + 一个一句提示”。

**改动**：

- `tutor/server/tutor_policy.py`
- `tutor/server/tutor_server.py`
- `tutor/tests/test_tutor_policy.py`

**下一次**：

- 真实观察裁剪后的回复是否仍够用；
- 如果够用，再把 `vague` 也拦截。

## 2026-10-28 19:54

**问题**：复习模式、考试模式怎么和普通讲题区分？

**实现**：

- `tutor_scenarios.situation_for(move, mode)`：
  - `review` 覆盖普通场景；
  - `exam` 覆盖普通场景；
  - 其他按学生动作映射。
- `_chat` shadow 记录 `mode`、`situation`、`max_probes`；
- 复习模式预算 1，考试模式不 probe。

**结果**：

- 80 个测试通过；
- 目前只影响 shadow，线上回复未变；
- 为后续“复习/考试模式”UI 留好策略入口。

**判断**：

- 模式优先级必须先于学生动作，否则复习会被当成普通讲题；
- 考试模式目前没有 UI，但策略已就绪；
- 需要真实复习会话验证记录。

**改动**：

- `tutor/server/tutor_scenarios.py`
- `tutor/server/tutor_server.py`
- `tutor/tests/test_tutor_scenarios.py`

**下一次**：

- 做一次复习模式真实会话；
- 再决定是否给考试模式加前端开关。

## 2026-10-28 19:55

**问题**：考试模式只有策略数据，没有真实入口。

**实现**：

- 新增 `prompts/modes/exam.md`：
  - 只给最小提示；
  - 一次一句；
  - 不展开完整解法；
  - 不总结整题。
- `prompt_loader` 支持 `mode="exam"`；
- talk 页新增「考试」勾选；
- `tutorMode()` 统一决定 tutor/review/exam；
- 打开考试模式会重置当前会话，避免和普通讲题混用。

**结果**：

- 81 个测试通过；
- Playwright 勾选考试模式正常，无 pageerror；
- 线上行为在勾选后生效。

**判断**：

- 考试模式现在有真实入口；
- 还没做真实考试会话，提示是否够短需要试；
- 复习模式仍用原来的 review 入口。

**改动**：

- `tutor/prompts/modes/exam.md`
- `tutor/server/prompt_loader.py`
- `tutor/web/talk.html`
- `tutor/web/talk.js`
- `tutor/tests/test_prompt_loader.py`

**下一次**：

- 真实试一次考试模式，检查提示是不是够短；
- 再补复习模式的实弹验证。

## 2026-10-28 19:56

**问题**：真实会话回归能不能发现策略 bug？

**实验**：

- 用 `tutor_eval.py` 跑最近 6 条有 turns 的 session；
- 发现一条 15 轮会话模拟 `probe_streak=3`，违反“最多 2 次”。

**根因**：

- `classify_move` 把学生“提问”分类为 `question`；
- `next_action` 把 `question` 也当成 `probe` 并重置计数；
- 结果：学生连续问问题，probe 计数被清零，策略看起来没超，实际一直在问。

**修复**：

- 学生提问 → `explain`，不再 `probe`；
- 学生问的是“为什么/这题是不是…”，tutor 应该回答，不是继续盘问。

**结果**：

- 82 个测试通过；
- 6 条真实会话重放，最大 probe streak 从 3 降到 ≤2；
- 真实问句最长仍 11，说明历史会话的问题主要在模型，不在策略模拟。

**改动**：

- `tutor/server/tutor_policy.py`
- `tutor/tests/test_tutor_policy.py`

**下一次**：

- 继续用 `tutor_eval` 做回归；
- 评估 `vague` 是否要切实际拦截。

## 2026-10-28 19:57

**问题**：前面 15 轮改动后，策略层有没有回归？

**实验/验证**：

- 全量测试：82 个通过；
- 6 条真实会话重放；
- 最大模拟 probe streak = 2；
- 实际最长问句仍为 11（历史会话，策略模拟不计）。

**结果**：

- 没有发现新回归；
- 本轮没有代码改动；
- 策略层目前处于可观察状态。

**判断**：

- 连续增加行为改动开始有风险，先停止叠功能；
- 下一步应等真实使用数据，而不是继续造规则；
- 如果下一次仍无新数据/改动，降为每周复盘。

**改动**：

- 无代码改动。

**下一次**：

- 观察真实 `tutor_states` / 新会话；
- 有数据再做 A/B，没有则降频。

## 2026-10-28 19:57

**问题**：有没有新的真实使用数据？

**检查**：

- `tutor_states`：0 条；
- 有 turns 的 session 仍是 6 条，没有新增；
- 没有新的写作草稿。

**结果**：

- 本轮无新证据、无代码改动；
- 策略层保持上一轮状态。

**判断**：

- 连续无数据时不应继续造功能；
- 这是第 2 次无变化，下一次仍为空就降为每周复盘。

**改动**：

- 无。

**下一次**：

- 再检查一次 `tutor_states` / session；
- 仍为 0 就降频。

## 2026-10-28 19:58

**问题**：第三次检查是否仍无新数据？

**检查**：

- `tutor_states`：0；
- 有 turns 的 session：仍是 6；
- 没有新写作草稿。

**结果**：

- 连续第 3 次无新证据、无代码改动；
- 触发停止条件。

**判断**：

- 策略层已稳定到可暂停高频研究；
- 继续每 7 分钟空转没有价值；
- 降为每周复盘，等真实使用数据再启动 A/B。

**改动**：

- 深耕任务从每 7 分钟改为每周日 21:00。

**下一次**：

- 每周检查 `tutor_states` / 新 session / 写作数据；
- 有真实数据再验证动作契约与科目预算。

## 2026-10-28 20:41

**问题**：有没有“只对比教案、不纠正、不延伸”的模式？

**实现**：

- `speech.compare_with_plan(plan, answer)`：
  - 只输出 `hit / miss / confused / extra`；
  - 明确禁止纠正、解释、建议、追问、补知识；
  - 只列事实。
- 新增 `POST /api/app/compare`；
- 讲题页新增「只对比」按钮和弹窗：
  - 可粘贴/修改自己的回答；
  - 结果只分“答到的点 / 没答到的点 / 说错混淆 / 教案外内容”；
  - 不提供改法。
- 没有教案时返回 409，不现场生成。

**结果**：

- 84 个测试通过；
- 真实 2009 408 第 1 题对比可用：
  - hit：FIFO、队列入队/出队；
  - miss：排除栈、树/图等；
  - confused/extra：空；
- Playwright 弹窗与结果渲染正常，无 pageerror。

**判断**：

- 这个模式只做“对照”，不替学生改；
- 适合学生自己讲完后检查盲点；
- 仍需真实使用，确认 `miss` 列表不会过长。

**改动**：

- `tutor/server/speech.py`
- `tutor/server/tutor_server.py`
- `tutor/web/talk.html`
- `tutor/web/talk.js`
- `tutor/tests/test_compare.py`

**下一次**：

- 真实用一次「只对比」；
- 如果 miss 太长，改成“只列前 3 条”。

## 2026-10-28 20:54

**问题**：正常分析被“先停一下，不再重复追问”强行截断。

**根因**：

- `_chat` 的强制提示条件仍是：

```python
_question_streak(history) >= 2
```

- 只要前面连续两个 assistant 回复带问号，第 3 轮就强制提示；
- 但苏格拉底讲题本来就会连续问，用户也在正常回答；
- 这不是循环，是正常分析。

**修复**：

- 新增 `_should_force(text, state, move)`：
  - 只有学生明确说“不知道/进行不下去/卡住…”；
  - 或上一轮 `over_budget` 且这一轮仍是只报答案；
  - 才强制提示。
- 移除“问句数 ≥2 就强制”。

**结果**：

- 86 个测试通过；
- 用截图里的正常分析路径调用 API：
  - `forced` 不再出现；
  - tutor 继续追问“756 哪个是根”，没有截断。

**判断**：

- 强制提示必须针对“卡住/超预算”，不能针对“问句次数”；
- 这是之前自己引入的回归，已修复。

**改动**：

- `tutor/server/tutor_server.py`
- `tutor/tests/test_socratic_guard.py`

## 2026-10-28 20:55

**问题**：学生已经说清结构，tutor 还为了问而问。

**例子**：

- 学生：2 是子树的根，756 是一个子树，4 是另一个子树；
- tutor：你这里含糊，根 2 应该算在右子树那一段吗？

**实现**：

- `base.md` 新增“不要为了问而问”：
  - 措辞含糊但意思清楚：直接陈述，不反问；
  - 小矛盾：先陈述“这里应该是……”，再看是否影响下一步；
  - 学生已给结论：先确认，再推进；
  - 连续两回合都在问：下一回合必须给信息/推进；
  - 不能为了“保持苏格拉底”硬造问题。

**结果**：

- 87 个测试通过；
- prompt 已生效，下一轮回复会受约束；
- 没有改代码逻辑，避免再次误伤正常分析。

**判断**：

- 这类问题不是强制提示造成的，是 prompt 把“确认”写成了“提问”；
- 规则要写成“陈述优先”，而不是“少问”。

**改动**：

- `tutor/prompts/base.md`
- `tutor/tests/test_prompt_loader.py`

## 2026-10-28 21:20

**问题**：四个模式能不能按学生对话自动调度，而不是按钮切换？

**实现**：

- 新增 `tutor_router.py`：
  - `gap_check`（检查/讲完/有没有漏）；
  - `gap_fill`（不懂/补一下/为什么）；
  - `guide`（别直接讲/问我/引导）；
  - `summary`（总结/收尾/差不多了）；
  - 默认 `listening`。
- 新增 `tutor_validator.py`：
  - 查漏不许问、不许建议；
  - 补缺最多一个问号；
  - 引导最多一个问题；
  - 总结不许问、不许判断掌握。
- `_chat` 改为：
  - 路由器选角色；
  - 查漏直接走教案对照（不调自由聊天）；
  - 补缺/引导/总结用对应 mode prompt；
  - 校验失败走角色兜底；
  - 保存 `last_mode` / `last_router`。
- 讲题页显示当前模式徽标。

**结果**：

- 97 个测试通过；
- API 实测：
  - “我讲完了，帮我看看” → `gap_check`，输出答到/没答到，不追问；
  - “嗯，我继续” → `listening`；
  - “别直接告诉我，问我” → `guide`；
  - “差不多了，帮我总结” → `summary`；
- 模式徽标从“听讲”切到“查漏”正常。

**判断**：

- 四个角色现在按学生对话自动调度，不再靠按钮；
- `gap_check` 是确定性的，不自由发挥；
- 引导被校验器拦成提示时，说明模型容易一轮多问，后续可把 guide 的兜底改成“只保留第一个问题”。

**改动**：

- `tutor/server/tutor_router.py`
- `tutor/server/tutor_validator.py`
- `tutor/prompts/modes/gap_fill.md`
- `tutor/prompts/modes/guide.md`
- `tutor/prompts/modes/summary.md`
- `tutor/server/prompt_loader.py`
- `tutor/server/tutor_server.py`
- `tutor/web/talk.html`
- `tutor/web/talk.js`
- `tutor/tests/test_tutor_router.py`
- `tutor/tests/test_tutor_validator.py`
- `tutor/tests/test_prompt_loader.py`

## 2026-10-28 22:13

**问题**：用户不知道说什么话才能触发四个角色。

**实现**：

- 讲题页模式徽标下方加“提词器”：
  - 我讲完了 → 查漏
  - 这里不懂 → 补缺
  - 别直接讲 → 引导
  - 差不多了 → 总结
- 点关键词会把对应说法填进输入框，不自动发送；
- 用户可以照着说，也可以改字。

**结果**：

- Playwright 验证四个关键词可见；
- 点击“我讲完了”会填入“我讲完了，帮我看看有没有漏”；
- 无 pageerror。

**判断**：

- 提词器解决“不知道该怎么触发模式”；
- 不自动发送，保留用户控制；
- 下一步可在模式切换时高亮当前可用关键词。

**改动**：

- `tutor/web/talk.html`
- `tutor/web/talk.js`

## 2026-10-28 23:16

**问题**：听讲模式每轮都回“嗯，我在听。你继续。”，变成机械重复。

**根因**：

- 听讲角色被写成一句固定回复；
- 每轮学生说话都返回并朗读这句话。

**修复**：

- 听讲返回 `silent: true`、空 text/speech；
- 前端收到 silent 不添加 assistant 气泡、不朗读；
- 不写空 assistant turn；
- 只在状态栏提示“我在听，你继续”。

**结果**：

- Playwright：用户 1 条消息，assistant 气泡 0 条；
- 页面无 pageerror；
- 学生连续讲时不再被重复话打断。

**判断**：

- “听讲”必须是安静状态，不是固定台词；
- 之后只在模式切换时给一次短提示即可。

**改动**：

- `tutor/server/tutor_server.py`
- `tutor/web/talk.js`

## 2026-10-28 23:52

**问题**：查漏结果自相矛盾，像机器人。

**例子**：

- hit 说“使用 |BF|≤1 作为判据”；
- miss 又说“未提发现 |BF|>1 即淘汰该选项”；
- 把“分析 B 选项”算成教案外。

**根因**：

- 对比只看字面，没识别等价表达；
- `miss` 从 path/stuck 等过程项里取，过细；
- `confused` 把“曾疑惑报告”当成了混淆。

**修复**：

- 对比只取 `core / misconceptions / finish_check / success_criteria`；
- 明确定义等价：
  - 每个结点/每个子树 ≡ 任一结点失衡即淘汰；
  - |BF|≤1 ≡ |BF|>1 淘汰；
  - 分析当前选项是解题过程，不算教案外；
  - 同一意思不能在 hit 和 miss 同时出现。
- `miss` 最多 4 条，只列真正核心缺口；
- `confused` 只列明确说错/用错，不列元评论；
- UI 文案改为“你讲到的点 / 还差的点 / 说错用错 / 题外内容”。

**结果**：

- 用同类答案测试：
  - hit：每个结点 |BF|≤1、任一结点失衡即淘汰、不能只看根；
  - miss：空；
  - confused/extra：空。
- 不再出现“同一个意思既答到又没答到”。

**改动**：

- `tutor/server/speech.py`
- `tutor/server/tutor_server.py`
- `tutor/web/talk.js`

## 2026-10-28 23:55

**问题**：规则太多，tutor 变得机械、没有灵性。

**判断**：

- `base.md` 224 行、大量“不要这样”示例；
- `tutor` 模式 31 行，和 base 重复；
- 模型被规则压住，只剩条件反射。

**改动**：

- `base.md` 224 → 43 行，只留 10 条原则 + 一个短例；
- `modes/tutor.md` 31 → 6 行；
- 保留：
  - 学生主导；
  - 一次一个点；
  - 同一卡点最多 2 次；
  - 不要为了问而问；
  - 不替学生思考；
  - 语气像人；
  - 输出格式。
- 删除重复示例、长篇边界说明、过多“不要这样”。

**结果**：

- 97 个测试通过；
- prompt 仍包含模式/格式必需内容；
- 规则从“清单”变回“原则”。

**下一次**：

- 用同一道题对比精简前后回复，确认不再机械；
- 如果仍太硬，继续删模式文件里的重复规则。


























## 2026-11-01 21:00

**问题**：10-28 之后有没有新的真实 tutor 使用数据？策略层是否保持？

**实验**：

- 新 session：10-31 16:57 / 21:17 / 21:58 / 22:13，共 4 条，全部是数二讲题；
- 用 `tutor_eval.py` 逐条量化；
- 查 `tutor_states`：最近一条仍是 10-29，10-31 的 session 没有 state 记录；
- 查写作数据：最新仍是 10-28 07:37，没有新稿。

**结果**：

- 4 条 session 共 20 个 user turn、20 个 assistant turn；
- assistant 问句 8 次，最长连续问句 4（最后一条 session）；
- 模拟策略最大连续 probe 2，最终 hint_level 0/1/2；
- style flags：无。

**判断**：

- 模拟动作契约没有超过数二预算（max_probes=2），提示阶梯正常；
- 真实问句最长 4 仍是模型层行为，不是策略模拟越界；
- 10-31 会话没有 tutor_states，说明当前背景学伴路径不写策略状态，已知边界；
- 没有代码改动。

**下一次**：

- 等复习模式 / 考试模式的真实会话，或更多普通讲题数据；
- 不造合成会话。


## 2026-11-08 21:00

**问题**：11-01 复盘后有没有新的真实 tutor 使用数据？策略层是否保持？

**实验**：

- 新 session：11-06 共 16 条有 turns 的会话，全部是 tutor 模式；
- 用 `tutor_eval.py` 逐条量化；
- 查 `tutor_states`：最近一条仍是 10-29，11-06 的会话没有 state 记录；
- 查写作数据：最新仍是 10-28 07:37，没有新稿。

**结果**：

- 16 条 session 共 161 个 user turn、161 个 assistant turn；
- assistant 问句 115 次，最长连续问句 13；
- 模拟策略最大连续 probe 2，最终 hint_level 0–3；
- style flags：vague 4、multi_question 4。

**判断**：

- 模拟动作契约没有超过数二/408 预算，提示阶梯正常；
- 真实连续问句仍以模型层为主，背景学伴路径没有接 `sanitize_questions`，这是已知边界；
- 16 条全是 tutor 模式，复习/考试模式仍没有真实数据；
- 没有代码改动。

**下一次**：

- 如果连续问句仍高，考虑只在背景路径接一次 `sanitize_questions`（一条主问）做小实验；
- 等复习/考试模式真实会话；不造合成题。
