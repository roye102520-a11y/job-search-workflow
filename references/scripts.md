# 本地脚本操作

入口：`scripts/job_data.py`，相对本 Skill 目录定位。Python 3.9+，仅标准库；文件锁依赖 macOS/Linux 的 fcntl，Windows 尚不支持。下面 SKILL、CASE、MANIFEST 代表实际绝对路径，使用时替换并正确引用含空格路径。

## 准备材料

```bash
python3 "$SKILL/scripts/job_data.py" --case "$CASE" validate --manifest "$MANIFEST"
python3 "$SKILL/scripts/job_data.py" --case "$CASE" register --manifest "$MANIFEST"
```

## JD 自动生成与本地工作台

这部分在 `resume-evidence.json` 已依据当前事实库建立后使用。缓存必须留在候选人案例目录，不能放进公开 Skill 或同步到公开 GitHub。输入格式与审阅边界见 [JD 工作台说明](jd-studio.md)。

安装 PDF 依赖，或使用 Codex 提供的 Python runtime：

```bash
python3 -m pip install -r "$SKILL/requirements.txt"
```

准备一个 JSON 请求文件，字段为 `company, title, jd, url, language, family`；`language` 是 `zh` 或 `en`，`family` 是 `auto` 或工作台支持的稳定方向标签。然后运行：

```bash
python3 "$SKILL/scripts/resume_pipeline.py" --case "$CASE" --request "$REQUEST"
```

结果写入 `$CASE/generated/<timestamp>-<id>/`。其中 `match.md` 列出可识别硬门槛的“有证据支持 / 未知 / 当前不满足”，`review.md` 记录追问，`email.md` 默认没有真实收件人且不会发送。没有官网链接时不会创建投递 manifest；已有相同官网链接的岗位包也不会创建第二个 manifest。

本地页面入口：

```bash
python3 "$SKILL/scripts/resume_server.py" --case "$CASE" --port 8765
```

只从输出的 `http://127.0.0.1:8765` 打开页面。服务仅绑定回环地址，使用一次性会话令牌，且仅允许访问 `generated/` 内的安全文件类型。停止服务后页面不能再生成材料。

对带 manifest 的新岗位包，先校验但不要把校验成功误解为可提交：

```bash
python3 "$SKILL/scripts/job_data.py" --case "$CASE" validate --manifest "$MANIFEST"
```

只有真实 JD、事实、硬门槛、最终附件、目标渠道和用户授权都完整后，才按本文件后续的 `start` 流程冻结提交附件。

validate 检查字段、案例内文件路径、附件 SHA-256、精确岗位编号/链接重复；不会解析 PDF 页面、核验事实或授权。register 按 job_key 更新 CSV，保留未知列及提交后的方向/版本。Manifest 放在 `applications/<job-key>/manifest.json`，不要另外维护未归档副本。

artifacts 至少包含 path、sha256，可另记 version；用 Python hashlib 对实际文件字节计算摘要。没有附件内容变化时不要重算摘要以掩盖校验失败。证据引用格式为案例相对路径，可加 `#章节`；脚本只检验文件存在，章节和内容由代理核对。

重复判断只覆盖已登记别名、同租户同岗位编号和去掉已知跟踪参数后的相同链接；不能保证发现未知来源的同一岗位。没有编号且链接不一致时仍需人工/代理核验。

## 提交前与提交后

先确认真实用户授权、材料内容和目标。仅当 manifest 为 ready、必填缺口清空、附件校验通过后：

```bash
python3 "$SKILL/scripts/job_data.py" --case "$CASE" start --manifest "$MANIFEST"
```

这条命令**不会投递**。它创建 UUID attempt_id、冻结附件副本并写 attempt_started，返回副本路径；外部操作必须使用这些副本。执行状态保守记为 submission_unknown，防止代理中断后重复提交。复制的原始附件可继续改，冻结副本不能修改。

有结果后创建事件 JSON 文件并执行 record。事件字段：

- `event_id`：稳定 UUID；同一逻辑事件重试复用该 ID。相同内容重试幂等，不同内容复用 ID 会失败。
- `job_key, attempt_id`：与 start 返回值对应。
- `timestamp`：本次观察/报告时间，ISO 8601 带时区；不能早于已有观察。
- `occurred_at`：实际投递时间，知道才填；不能晚于观察时间。不能用当前时间补历史未知日期。
- `action`：attempt_result。
- `result`：submitted / not_submitted / unknown。已受理或草稿不是 submitted。
- `source`：tool_observation / user_report。
- `evidence_path`：案例内保存的实际回执或用户报告记录；不能伪造。脚本仅验证存在，内容真实性仍需代理判断。

```bash
python3 "$SKILL/scripts/job_data.py" --case "$CASE" record --event "$EVENT"
python3 "$SKILL/scripts/job_data.py" --case "$CASE" reconcile
```

record 追加事件后更新 Tracker；中断时 reconcile 从事件恢复。Manifest 的 status 是准备时快照，实时招聘阶段读 Tracker，不把旧 Manifest 覆盖到已投递阶段。

开始限制在更新 Tracker 前检查；closed 不会因旧 ready 清单自动重开。投递确认晚于面试/拒信到达时只补充确认信息，不降级招聘阶段。成功记录的 resume_path 指向冻结副本；旧事件缺少明确的简历映射时提示核验，不猜附件类型。复盘读取同次尝试开始后的关联反馈，避免晚确认漏掉已发生的面试。

unknown 可追加新的核验结果。not_submitted 仅在确定外部未产生申请时使用，允许新尝试；最终 submitted 后脚本阻止再次 start。重新申请同岗位尚需人工审查和明确迁移，不提供自动 force 绕过。

面试或反馈以 `reply, assessment, interview, offer, rejected, withdrawn` action 记录，包含同样的 job_key、timestamp、source、evidence_path、event_id。咨询和跟进用 outreach/followup，不改变招聘阶段。此工具暂不支持自动导入没有开始事件的历史投递；历史记录在报表中提示未纳入，后续需依据真实档案迁移。

## 分方向与版本复盘

```bash
python3 "$SKILL/scripts/job_data.py" --case "$CASE" report --days 90 --min-age 14 --output "$CASE/direction-review.md"
```

可用 `--as-of` 指定带时区的观察截止时刻。统计基于确认提交事件，按 job_key 去重，以开始事件中的方向与简历版本归组；已面试后被拒仍计入“曾获得面试”。未回复与拒信分开。无数据输出 N/A/缺数据说明，不填 0% 暗示失败。

旧 CSV 的 application_status 与 status 一致时兼容；不一致、缺少 job_key、已重复键等情况直接报错，保留原始文件，先修复迁移再执行。文件锁串行化脚本写入，但不能阻止其他软件直接编辑或其他代理绕过脚本提交。

## 验证

```bash
python3 -m unittest discover -s "$SKILL/tests" -v
```

测试只使用临时目录中的合成样本，不连接招聘网站、邮件或真实案例。测试通过不意味着端到端投递已验证。
