# 每日学习报告

更新时间：2026-10-28

## 入口

首页 / 学习报告：

```text
/report.html
```

## 目的

- 随时生成当天学习报告；
- 过一天自动归档；
- 报告存 Markdown；
- 打开时按“秘书汇报老板”的口吻整理。

## 数据来源

从 `tutor/data/app.db` 聚合：

- 当天讲题 session / turns；
- 科目的 session 数、消息数；
- 完成题目数（`problem_progress.first_finished_at`）；
- 当天评级（`reviews.last_rating`）；
- 写作任务状态更新；
- 当天 `queue_items.actual_min`。

## 存储

```text
tutor/data/reports/YYYY-MM-DD.md       润色版
tutor/data/reports/YYYY-MM-DD.raw.md   原始事实
```

## API

```text
GET  /api/app/reports?archive=1     列表；会补生成昨天
GET  /api/app/report?date=YYYY-MM-DD 读取
POST /api/app/report/generate       生成/更新
```

## 原则

- 只使用事实；
- 不判断掌握；
- 不编造；
- 不出现内部 ID / null / 状态码；
- 润色失败时退回原始报告。

## 页面

- 日期按钮；
- 生成/更新今天报告；
- 看最近一份；
- 原始事实折叠。
