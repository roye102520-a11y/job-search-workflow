# Job Search Workflow Skill

一个可复用的 Codex 求职工作流：用真实经历为每个 JD 建立独立材料包，检查硬门槛，生成中英文简历与邮件草稿，记录真实投递结果并按方向复盘。

[查看合成数据公开预览](https://job-search-workflow-ten.vercel.app)

## 两种 JD 定制入口

在 Codex 中粘贴完整 JD 并要求“按这个 JD 生成简历”，Skill 会从案例事实库选材、输出匹配报告、PDF 和邮件草稿。

也可运行本地工作台：

```bash
python3 -m pip install -r requirements.txt
python3 scripts/resume_server.py --case /absolute/path/to/job-search-cases/example --port 8765
```

在浏览器打开 `http://127.0.0.1:8765`。工作台只绑定本机，材料默认写到案例的 `generated/`；不会上传资料、发送邮件或提交网申。

### 手机与跨平台使用

同一 Wi-Fi 下可让手机访问本机工作台（只在可信网络使用）：

```bash
python3 scripts/resume_server.py --case /absolute/path/to/job-search-cases/example --host 0.0.0.0 --port 8765
```

在电脑查看局域网地址（macOS 可运行 `ipconfig getifaddr en0`），然后用手机打开 `http://电脑局域网地址:8765`。页面带有 PWA manifest 和离线壳，可在手机浏览器中选择“添加到主屏幕”；离线只缓存页面外壳，个人案例与接口不会写入缓存。首次访问会生成本机工作台会话令牌，服务停止后令牌失效。

公开 GitHub 仓库只同步本 Skill 的代码、文档和合成测试夹具；`.gitignore` 默认排除 `job-search-cases/`、生成 PDF、邮箱和投递记录。公开预览只展示合成示例，不能读取本机案例；要跨网络使用完整功能，需要另行部署带认证、持久化存储和 HTTPS 的后端，不应直接把当前本地服务暴露到公网。

### Vercel 公开预览

仓库根目录已有 `vercel.json`，使用 `public/` 作为静态输出。把整个 Skill 仓库导入 Vercel，Framework Preset 选 **Other**，Root Directory 保持仓库根目录，随后部署即可。若将本目录放在更大的仓库中，Root Directory 则设为 `skills/job-search-workflow`。

预览页只演示“岗位要求 → 事实选材 → 简历重点”的变化，所有岗位和经历都标为合成示例。它不是可登录的云端工作台，也不会运行 `scripts/resume_server.py`。本地完整工作台仍需按上面的命令启动；不能把个人案例、邮箱记录或 `DEEPSEEK_API_KEY` 放入 Vercel 静态文件或公开 Git 仓库。

### 可选 DeepSeek 辅助

DeepSeek 调用只在服务端进行，浏览器不会接触 API Key，也不会写入生成文件。复制 `.env.example` 的配置方式并在启动进程环境中设置：

```bash
export DEEPSEEK_API_KEY='你的密钥'
export DEEPSEEK_MODEL='deepseek-chat'   # 可选
```

工作台“投递 → 简历匹配推荐”中的“生成摘要”按钮只发送已选择偏好、推荐岗位标题和页面已展示的理由；没有 Key 时本地规则推荐仍可用。摘要是辅助说明，岗位官网链接、硬门槛和投递状态仍需核验。

首页包含总览图表、素材与作品集、JD 简历、投递看板、面试复盘和个人网站。导入 PDF/Word 后保留原文摘录与来源；综合总结由 Codex 执行。可按完整事实库或某份 JD 简历生成同款作品集网站，本地保存复盘和自评。官网社招通过 Codex 浏览器与投递记录脚本执行，页面不提供无人值守投递服务。详见 [工作台说明](references/career-workspace.md)。

只粘贴完整 JD 也可以生成。若正文中有“公司：”“岗位名称：”等明确标签，工作台会提取它们并在结果中提示复核；没有明确标签时仍会生成审阅稿，但公司或岗位名称会标为待补全，不能外发。

## 事实与隐私

真实案例应包含 `career-evidence-bank.md`、`coaching-state.md` 与派生的 `resume-evidence.json`。后者保存姓名、经历和来源摘要，属于私有候选人数据，**不要提交到公开 GitHub**。`tests/fixtures/` 仅使用合成 JD。

公开同步时提交 `skills/job-search-workflow/` 即可。该目录的 `tests/fixtures/synthetic-case/` 包含可运行的合成事实库与缓存，用于验证安装包不依赖任何个人案例；项目根目录的 `.gitignore` 默认排除真实 `job-search-cases/`、生成材料和本地验收输出。

生成器会拒绝事实源已经变化的旧缓存；会阻断职责不清、与明确硬条件冲突的岗位；会把未确认信息保留为待核实，不写成成果。

## 验证

使用带有 `reportlab` 与 `pypdf` 的 Python 环境运行：

```bash
python3 -m unittest discover -s tests -v
```

测试覆盖本地投递记录、PDF 材料生成、四类 JD 路由、负向岗位拦截、回环页面的跨站/文件隔离，以及恢复和去重逻辑。所有测试均使用临时或合成数据。

详细的数据约定、自动生成和外部执行边界见 [SKILL.md](SKILL.md)。
