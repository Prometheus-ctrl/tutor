# tutor 实验版（独立，不动稳定版）

语音优先的数学题苏格拉底闭环。独立服务、独立数据库；`app/`、8080、8791 都不改。

## 当前状态：0A 切题校正 + 0B 语音闭环通过

- `qwen3-vl-plus` 识别两页：第 1 页 8 题、第 2 页 9 题，共 17 题；
- 第 8 题的 A/B 在第 1 页、C/D 在第 2 页顶部，已通过“顶部窄条二次识别”合并；
- 第 17 题被模型误标跨页，管线在最后一页自动取消并记录警告；
- 每题保存裁剪图；跨页题额外保存续块裁剪图，作为选项的最终依据；
- 一页约 4.5k~5k tokens；真实页成本仍是几毛钱一张卷。

已知限制：

- 模型偶尔给空选项、重复选项或编造选项；管线会清掉空/重复项，并保留原图裁剪；
- 选项文字不保证 100% 准确；不对就「重读此题」，图糊就「重拍此题」；
- 跨页题需要人工在预览里扫一眼，确认没有漏块。

## 跑整卷切题

```powershell
cd tutor\server
python ingest.py ..\samples\page1.jpg ..\samples\page2.jpg
```

产物在 `tutor/samples/ingest-日期-时间/`：

- `result.json`：题目、选项、bbox、页码、警告；
- `crops/pXX.jpg`：每题裁剪；
- `frags/pXX-fN.jpg`：跨页续块裁剪；
- `preview.html`：浏览器打开检查切题。

## 首页

双击 `tutor\启动讲伴.bat`，会启动本地服务并打开 <http://127.0.0.1:8793/>。  
也可以手动运行：

```powershell
cd tutor\server
python tutor_server.py
```

打开 <http://127.0.0.1:8793/>：

- 今天该复述的题；
- 最近讲过的题 / 继续上次；
- 开始讲题、拍新卷、到期复述入口。

## 校正页（当前）

```powershell
cd tutor\server
python tutor_server.py
```

打开 <http://127.0.0.1:8793/correct.html>：

- 上方选卷子；
- 每题左边是 bbox 实时裁剪（canvas），右边是 KaTeX 渲染后的题干/选项；
- 不需要懂 LaTeX：文字不对点「重读此题」，图糊点「重拍此题」；
- 「标记待重读」只表示这题文字暂不可信；DeepSeek 是文本接口，讲题前必须把文字确认好；
- 只有懂 LaTeX 才需要「编辑文字」；
- 「上边界 / 下边界」微调，保存后立即重裁；
- 可删除本题、合并到上一题；
- 「保存全部」写回 `result.json`。

只监听 `127.0.0.1`，不暴露公网。

## 讲题页（0B 语音）

校正页右上角点「讲题（语音）」，或直接打开：

```
http://127.0.0.1:8793/talk.html
```

从首页点到期题会带 `?review=<paper:index>`，直接进入复述模式。

语音输入是一个可拖动的浮窗：

- 收起时只有麦克风和「编辑」；录完在麦克风旁弹出最新一句的「我听到 / 公式」气泡；
- 点气泡里的「展开编辑」，或点「编辑」，展开本轮语音历史、转写和公式卡片；
- 点浮窗以外的地方自动收起；
- 拖「⠿」或「语音输入」标题栏可以移动，位置会记住。

自动朗读默认关闭：聊天区头部的「朗读」勾选开启后，回复才会自动播报；
关掉时回复只显示文字，需要听时点「🔊 重听」按需合成一次（结果会缓存，本次回复内可重复听）。

会话会落库到 `tutor/data/tutor.sqlite`：

- 每道题一个 session，tutor / review 分开；
- 每轮 user/assistant 都写入 turns；
- 刷新页面、重启服务后，回到同一道题会恢复对话；
- 评级结束后当前 session 关闭，下次重新开始。

接口：

- `POST /api/session` `{paper,index,mode,model}` → `{id,turns}`
- `GET /api/session/<id>`
- `POST /api/session/<id>/end`
- `GET /api/sessions/recent`

流程：

1. 选卷子、选题目；
2. 点一下开始录音，再点一下停止；
3. 浏览器把录音转成 16k 单声道 WAV，上传 `/api/asr`；
4. `qwen3-asr-flash` 返回文字，显示在可编辑文本框里；
5. 每录一句单独调用 `/api/normalize`，结合题目和前面的句子，只整理这一句；前面的公式卡片不变；
6. 每张卡片可「确认本句」或「重整本句」；**发给 agent 的是输入框原话，聊天气泡显示整理后的公式版**（鼠标悬停气泡可看原话）；
7. 点「发送给 agent」，按右上角下拉选择讲题模型（DeepSeek V4.1 Flash / V4 Pro、Qwen Plus / Max），按苏格拉底提示词回复；
8. 回复分两版：屏幕版允许 LaTeX（KaTeX 渲染），朗读版是纯口语，只给 TTS；
9. `qwen3-tts-flash` 合成语音，服务端下载后由 `/tts/...` 播放。

跨轮记忆（`config/companion.json`）：

- `chat.history_window` 现在是**每一轮复述各自的上限**（默认 48 条），聊天只带当前这一轮的历史，不再把历次复述拼在一起；
- 之前的轮次只带「第几次 + 日期 + 上次评级 + 卡点/易错」一小段（最多 2 轮，单条截断 200 字，放在题目背景里，不占历史窗口）；
- **复述模式下只带轮次和评级，不带上次卡点/易错**，避免给小提示；讲题模式才带。

接口：

- `POST /api/asr` `{audio:dataURL}` → `{text}`
- `POST /api/normalize` `{text}` → `{text}`（口语转 LaTeX，不纠错）
- `POST /api/chat` `{text,history,context}` → `{text,speech}`
- `POST /api/tts` `{text}` → `{url}`

限制：

- 目前是 turn-based，不是实时双工；
- 单次最长 60 秒，自动停止；
- 需要 Chrome/Edge 的麦克风权限；
- ASR 有少量漏字，转写可手动改；
- TTS 临时文件在 `tutor/data/tts/`，不会进 git。

## 讲题引擎（engine）

`/api/chat` 支持三种引擎，按 `body.engine` 或环境变量 `TUTOR_CHAT_ENGINE` 选择（都不设时保持旧行为）：

- `background`（默认）：直通式，只给身份+题目背景，LLM 自由发挥；
- `router`：旧半策略路径（角色路由+教案+校验），设 `TUTOR_BACKGROUND_ONLY=0` 时启用；
- `loop`：**agent loop 引擎**——每轮先由策略状态机决策教学动作（probe/hint/check/…），生成时注入该动作的契约约束，回复不合契约就把要求反馈给模型重试（≤2 次），仍不合格用兜底话术；决策状态按 session 持久化在 `tutor_states`，刷新后接着算。

核心文件：`server/tutor_loop.py`（闭环控制器，规则优先于模型，LLM 只当生成工具，generate 依赖注入所以可单测）；决策层是 `server/tutor_policy.py`。

离线验证（只读真实会话，不调模型不花钱）：

```powershell
cd tutor\server
python tutor_replay.py
```

用 42+ 条真实 tutor 会话重放 loop，输出契约一次通过率、动作分布、兜底率。

## 本题收尾 + FSRS

讲完一道题，点题目卡右上角「结束本题」：

- tutor 先在服务端生成一份**内部 rubric**，不显示、不返回浏览器、不存档；
- 你先用自己的话总结这题；
- tutor 拿你的总结和 rubric 对比，有缺口就**一次问一个启发式问题**，不直接说答案；
- 最多追问 2 次；你补充后，保存**你自己的总结**；
- tutor 给评级建议和理由，你确认评级；
- 用 FSRS 排下次整题复述；
- 评级完成后，**学伴总结会留在这一题的对话里**（重进/刷新都能看到，存为该题会话的一条 `summary` 记录）；
- 数据在 `tutor/data/reviews.json`，不进 git；
- 首次 Good 约 2 天，Hard/Again 约 1 天，Easy 约 5 天（关闭 10 分钟 learning step，按整题粒度走）。

FSRS 用 vendored `py-fsrs`（MIT），在 `tutor/server/vendor/fsrs/`，不依赖联网安装。

接口：

- `POST /api/finish/start` `{paper,index,history}` → `{id,question}`（rubric 不返回）
- `POST /api/finish/summary` `{id,summary}` → `{done,question}`
- `POST /api/finish/complete` `{id,summary}` → `{id,suggested,reason}`
- `POST /api/review` `{id,rating}` → `{due,interval_days,state,...}`
- `GET /api/reviews/due` → 到期列表

## 到期复述

讲题页顶部点「复习 N」：

- 列出今天到期的整题；
- 点一题进入**整题复述模式**：
  - 你先完整讲一遍；
  - agent 不主动提示，只在卡住/矛盾/明确要求时打断；
  - 讲完点「结束复述」，重新评级；
- 评级写回同一张 FSRS 卡，到期数立即更新。

## 新应用数据底座 v0.1

三环的完整逻辑框架、边界和下一步，以：

```
tutor/docs/three-rings.md
```

为准。数据表结构见：

```
tutor/docs/data-model.md
```

新三环应用的数据底座已经落在 `tutor/data/app.db`（SQLite）。

迁移现有数据：

```powershell
cd tutor\server
python migrate.py --tutor
```

`--tutor` 已导入 5 份整卷、85 道题；旧工作台数据另行导入：

```powershell
python migrate.py --old-store path\to\store.json --schedule path\to\schedule.json
python migrate.py --time
```

`--time` 写入固定课表、50h 周目标（数学 15 / 408 19 / 英二 8 / 政治 8）和 80% 上限。

查看表计数：

```
http://127.0.0.1:8793/api/db/summary
```

## 三环页面

- 首页：<http://127.0.0.1:8793/>
- 计划：<http://127.0.0.1:8793/plan.html>
- 时间：<http://127.0.0.1:8793/time.html>
- 讲题：<http://127.0.0.1:8793/talk.html>

首页/计划/时间已切到 `app.db`；讲题页仍读 `result.json`，但结束本题和评级会同步写 `app.db.reviews`。

新 API：

- `GET /api/app/overview`
- `GET /api/app/plans`
- `GET /api/app/due`
- `GET /api/app/time?date=YYYY-MM-DD`
- `POST /api/app/time` `{date,available_min}`
- `POST /api/app/time/confirm` `{date}`

## 配置

```powershell
setx DASHSCOPE_API_KEY "你的百炼 key"
```

重开终端后生效。国内 endpoint：

```
https://dashscope.aliyuncs.com/compatible-mode/v1
```

讲题模型默认用 DeepSeek。key 放：

```
tutor/data/deepseek.key
```

或设环境变量 `DEEPSEEK_API_KEY`。`tutor/data/` 已在 `.gitignore`，不会进仓库。

页面右上角可切换：

- `DeepSeek V4.1 Flash`（`deepseek-flash`，默认，快）
- `DeepSeek V4 Pro`（`deepseek-v4-pro`，更强）
- `Qwen Plus`（`qwen-plus`）
- `Qwen Max`（`qwen-max`）

选择存在浏览器 localStorage，下一次打开沿用。

想改默认/回退：

```powershell
setx TUTOR_CHAT_PROVIDER "qwen"
```

其他可调：

- `TUTOR_DEEPSEEK_MODEL`：默认 `deepseek-flash`
- `TUTOR_FINISH_MODEL`：收尾 rubric/追问用的快速模型，默认 `qwen-plus`
- `TUTOR_NORMALIZE_MODEL`：公式预览用的快速模型，默认 `qwen-plus`
- `TUTOR_CHAT_MODEL`：Qwen 回退模型，默认 `qwen-plus`
- `TUTOR_TTS_VOICE`：默认 `Cherry`

## 跑切题验证

```powershell
cd tutor\server
python spike_vision.py
# 或指定真实试卷
python spike_vision.py ..\samples\page1.jpg
```

输出：`tutor/samples/spike-result.json`。

## 放样本

把真实试卷照片放到：

```
tutor/samples/
```

`tutor/.gitignore` 已排除 `samples/`、`data/`、`media/`，不会进仓库。

## 下一步

1. 把讲题页和题目卡绑定，进入即带当前题；
2. agent 工具：判卡点、追问、指课本页；
3. 整题复述 + FSRS 评级；
4. 实时双工语音（当前是按住/点按 turn-based）；
5. iPad/手机使用需要 HTTPS，当前只监听 127.0.0.1。

技术选择：

- 看图：`qwen3-vl-plus`
- 对话：`deepseek-flash`（默认，DeepSeek-V4.1-Flash；可切 `deepseek-v4-pro` / `qwen-plus` / `qwen-max`）
- 语音识别：`qwen3-asr-flash`（WAV base64，原生接口）
- 语音合成：`qwen3-tts-flash`（服务端下载临时 URL）
