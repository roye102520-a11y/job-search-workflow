# 案例、岗位包与长期记忆

案例中可有私有 `user-requirements.md`，专门保存用户跨轮提出的功能目标、偏好和授权范围。它是沟通索引，不是职业事实源或投递回执；更新时追加有日期的决定，避免重写 Skill 时丢掉此前约定，也不要同步到公开仓库。

## 最小案例

沿用已有文件名和字段，不批量迁移旧档。新案例按需创建：

```text
job-search-cases/<case>/
  profile.yaml                 # 偏好、限制、来源和更新时间
  career-evidence-bank.md       # 原始经历、证据、个人贡献、确认状态
  application-answers.jsonl     # 简历外的网申答案记忆
  application-tracker.csv       # 每个岗位的当前状态
  application-events.jsonl     # 追加的执行记录与回执
  applications/<job-key>/
    jd.md                      # JD 原文/摘录、链接、获取日期、职位编号
    match.md                   # 要求—证据矩阵和取舍
    resume-zh.md / resume-en.md # 按需生成，实际提交版另存 DOCX/PDF
    cover-letter-en.md         # 需要时生成
    email.md                   # 收件人、主题、正文、附件
    manifest.json              # 此次申请材料清单与状态
    checkpoint.md              # 网申已填、未填、下一操作
    receipt.md                 # 成功证据；不存在则不要创建成功占位
```

只创建本轮使用的文件。旧 `resume-versions/` 中的材料可以直接被清单引用，不重复复制。文件共享包不得附带个人案例数据。

## 字段

- `job-key`：优先招聘主体/ATS 租户 + 官方 requisition ID；无编号时结合公司、职位、地点、规范化链接核对同一性，首次确定后保持标识稳定。仅移除已知跟踪参数，保留职位 ID 和必要查询参数。slug 只用于安全文件名，不把 URL 直接用作路径；不同岗位不能因同名合并。同岗位的聚合页与官网链接作为 aliases 记录；不能确定同一性时标记待核实，不靠字符串相似度自动合并或再次投递。
- 证据条目：稳定 ID 或章节位置、原始描述、个人动作、团队/个人结果、指标口径、来源、确认状态、纠正记录。英文和中文材料引用同一事实。
- 答案记忆：`key, question, answer, status, source, confirmed_at, scope, valid_until`。scope 区分通用、公司、岗位。薪资、到岗时间等易变答案使用前复核；过去某岗位的 Yes/No 不能全局复用。拒绝自我披露与尚未回答分开表示。
- Tracker 建议字段：`job_key, company, role, location, url, status, execution_status, sync_status, resume_path, submitted_at, updated_at, receipt_path, next_action`。status 只表示招聘阶段；已有 application_status 字段则将其视为 status 的别名，不并行维护两个互相冲突的阶段字段。保留已有额外列。
- Manifest：`job_key, jd_path, evidence_refs, language, resume_path, cover_letter_path, email_path, unresolved_required_fields, authorization_scope, status, updated_at`；准备外发时补充 `attempt_id, channel, recipient_or_endpoint, artifacts`，artifacts 保存实际附件路径、版本和 SHA-256。只列实际存在的文件。路径相对案例根目录解析，需外部路径时明确记录，不能按 Skill 安装目录解析。
- 使用本地脚本时补充 `company, role, role_family, resume_variant, url`；`aliases, employer_namespace, requisition_id` 用于确定性去重。role_family 是稳定方向标签，resume_variant 是版本名，不是岗位名；二者随开始事件冻结，之后修改草稿不改历史归因。脚本要求附件在案例根目录内，外部附件先复制到案例再引用，不接受越界路径。
- Event：`event_id, attempt_id, job_key, timestamp, action, result, evidence_path, source`。source 区分工具观察和用户报告，不捏造回执。时间使用带时区的 ISO 8601；不知道具体投递时间时留空，另外记录报告时间，不用当前时间冒充投递时间。

外发前冻结本次附件副本或引用已有不可变版本，保留哈希。授权若限定具体版本，文件变更后重新判断授权是否仍覆盖；用户授权按 JD 制作并投递则可在范围内修订，无需例行重复确认。草稿可覆盖，已提交版本不能覆盖。

执行前追加 attempt_started 事件，记录目标与附件；取得结果后追加结果事件，再更新 Tracker/Manifest。恢复时若有 started 无结果的尝试，先核验外部状态，不能当作尚未投递。事件保留历史，Tracker 是当前摘要；崩溃造成不一致时据有证据的事件修复摘要。多个执行者不得同时向同一岗位提交。

## 状态与恢复

招聘阶段 status：`discovered, shortlisted, preparing, ready, submitted, assessment, interview, offer, rejected, withdrawn, closed`。这些是枚举值，不是强制直线流程；例如可以直接收到面试或在测评前被拒。

执行状态 execution_status：`idle, filling, blocked, submission_unknown`；同步状态 sync_status：`not_requested, pending, synced, failed`。填写阻塞或飞书失败不能覆盖已有招聘阶段。旧记录的 filling/blocked/submission_unknown 迁入执行状态，能确定历史阶段时恢复；不能确定时保留原始值与待核实标记，不猜测。

只有正式申请邮件成功发送至正确招聘渠道才记 submitted；咨询、内推请求和跟进邮件记录为 outreach/followup 事件，不能冒充投递。发送成功不等于送达或被阅读，退信追加失败事件并安排处理。

从 submission_unknown 恢复时先查申请历史、确认页或已发送邮件；找不到证据仍保持未知，不盲目重投。重复运行先查 job-key、状态、事件和材料版本。面试拒信等事件应追加历史，不能抹去投递日期。重新申请需用户意图及新一轮申请依据，新增 attempt_id 保留旧记录。

授权记录写清目标岗位/收件人、动作、渠道、材料版本和范围；只引用真实用户指令，不能自行填成 approved。不要保存密码、验证码、Cookie 或访问令牌。

具体本地读写优先使用 [脚本操作](scripts.md)；旧档缺字段或缺事件时提示迁移缺口，不能为让统计脚本通过而编造历史尝试。
