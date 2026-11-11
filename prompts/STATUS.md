# Prompt 建设状态

目标：先让 tutor 有一套可组合、可维护的 prompt，再用真实体验调整。

## 组合规则

```
base.md + modes/<mode>.md + subjects/<subject>.md + types/<type>.md
```

## 已建

- base
- modes: tutor / review
- subjects: math2 / english2 / politics / cs408 / generic
- types: single / reading_set / cloze / new_type / translation / writing / politics_choice / politics_analysis / cs_choice / cs_comprehensive / generic

## 下一步

1. 给 types/single 补“分类讨论漏情况”的反例；
2. 给 types/reading_set 补“推断题过度推理”的反例；
3. 不增加新科目，先把现有四科写厚。

已补：base 三组短对话/过长反例/直接讲边界/情绪崩回应/懂了证明/随便讲边界/一次说太多；english2 五类题型追问；politics 干扰项/分析题追问；cs408 选择排除/大题边界/结果无过程/复杂度推导/单位口径/概念混淆/地址表错/结论无步骤/公式记混/绝对化/估算/算法选择；tutor 三类打断/答非所问；reading_set 整篇串联/无证据/证据链缺口/选项像原文/段落功能/主旨判断/作者态度；cs_comprehensive 小问过渡；writing 单点反馈/模板堆砌/开头空泛；cloze 上下文复现/搭配冲突/双搭配/逻辑连接/近义词；translation 句法拆分/漏译添译/语序调整/代词指代；politics_analysis 材料对应原理/三种空转/原理过多/结论无分析/材料过多/原理对材料错/原理名不解释；politics_choice 绝对化/答非所问/因果倒置/主体不一致/因果链过长反例；single 只写答案/跳步/用错公式/会做不会讲/单位符号反例；cs_choice 相似选项；review 复述打断。

## 约束

- 不写完整解法；
- 不替学生总结；
- 不出现“你已经讲完了/可以确认/这题就到这里”；
- 每轮只改一个文件或一个主题；
- 改完必须能通过 `prompt_loader.compose()`。
