# 整合来源与范围

## 2026-10-11：AI Job Search

核对 [MadsLorentzen/ai-job-search](https://github.com/MadsLorentzen/ai-job-search) master 的 README、`rank.md`、`outcome.md`、upskill Skill（未固定 commit，未运行上游代码）。吸收批量初筛、静默申请跟进、跨岗位缺口聚合思路，独立实现 [求职策略台](search-strategy.md)。没有复制上游代码、采集器或个性化档案。上游 Gmail/Notion 集成、丹麦招聘站、薪资工具不在本轮实现范围。

本地复用已有四方向证据规则，排序是可解释的初筛分，不等同上游多维模型评估。当前 PDF 已检查页数与可提取文本；仍需语义、阅读顺序和视觉审阅。完整对比保存在项目 `skill-reviews/2026-10-11-ai-job-search-comparison.md`。

本 Skill 是基于项目与用户提供摘要写成的独立工作流，没有安装或复制第三方执行代码。

## 本项目

- `skills/job-interview-coach-cn/`：事实源、岗位证据、单题训练和复盘闭环。
- 案例中的 `career-evidence-bank.md` 与 `coaching-state.md`：复用现有事实、纠正记录和求职偏好。个人数据不随 Skill 打包。
- 环境现有 JobOK 与 resume-grower：案例目录与证据优先思路；部分旧 Skill 的外部动作边界更窄，因此不把它们当作自动投递引擎。

## 用户摘要中的项目

2026-09-23 查看以下仓库主页，仅核对公开说明，没有运行或验证成功率：

- [ASu Skills](https://github.com/Hisn00w/ASu-skills)：分模块求职工作流。查看时的入口已包含 great-resume、make-resume、job-match、job-apply 等，不把摘要里的旧命令当成当前调用接口。
- [Job Autopilot](https://github.com/keii-2596/job-autopilot)：本地求职发现、跟踪和申请方向。
- [One-Stop-Resume-Copilot](https://github.com/Esther080310/One-Stop-Resume-Copilot)：JD 定制、事实审核和文档交付方向。
- [Get Offers](https://github.com/kola-official/get-offers)：作为用户提供的申请材料工作流参考入口。

摘要另列 [job-application-assistant](https://github.com/LH-kevin/job-application-assistant)、[Job Application Copilot](https://github.com/cong1005/job-application-copilot)、[ApplyBuddy](https://github.com/hangzhou-hz/ApplyBuddy) 及“芋泥工作流”，本次未进一步核验，均不是依赖项。

没有获得 46 篇原始笔记，不声称逐篇综合。星数、模型 effort 的成功率、Boss 风控、Playwright 稳定性及插件省 token 效果未作实测，不作为规则。英文邮件可由有发送能力的邮件连接器处理，不限定只能 Computer Use。

## 后续视频与六张截图的文字摘要

吸收用户提供的三个标准：成果量化/落地证明、按 JD 定制、简明专业；以及主简历、STAR/XYZ 故事、职位方向探索、限定日期的岗位清单与逐岗申请思路。这里依据文字摘要，没有查看原视频或六张原图。

“500 个申请、24 小时 12 个面试”为未核验个人陈述，不作为预期结果；“确切 ATS 关键词”和“消除全部警示信号”被改为可证据化的匹配与诚实解释。未核验匿名的“4 万星 Skill”或未给定地址的 offer-toolkit，不安装、不列为依赖。截图中的 ChatGPT 代理入口不是本 Skill 的必需操作，也不代表当前 Codex 环境具备相同后台能力。

## 后续 GitHub 复核

2026-09-23 后续查看六个项目的公开说明，新增核验 [Job Application Copilot](https://github.com/cong1005/job-application-copilot) 与 [ApplyBuddy](https://github.com/hangzhou-hz/ApplyBuddy)。读取 [ASu evidence-recap](https://github.com/Hisn00w/ASu-skills/blob/main/skills/evidence-recap/SKILL.md) 与 [网站字段/附件管理参考](https://github.com/cong1005/job-application-copilot/blob/main/references/advanced-features.md)。吸收项目阶段、改动对照、字段知识与答案分离的思路，规则为本项目独立编写，未安装或复制上游执行代码。

本次仅核验文档，未证明上游执行成功率。后续按 [持续改进](upstream-review.md) 处理具体缺口；不是定时更新或后台监控。
