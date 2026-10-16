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

在 `/studio` 可粘贴带“职位描述/职位要求”编号的 JD，点击“分析逐项符合度与 7 天补齐计划”，查看每条要求的相关证据、缺口、补齐动作和可交付物。案例中保存 `target-jd.md` 时，可一键载入当前目标岗位。分析是证据初筛，不是录用概率；练习作品不能表述为真实业务项目成果。

### 批量选岗与跟进

在「投递进度 → 批量选岗与跟进」打开 `/strategy`：导入多份完整 JD，查看证据覆盖排序、必需项待核实/不满足、重复链接和截止日期提示；按跨岗位缺口安排补证据与练习，并从确认投递事件生成静默 10 天后的跟进草稿。报告保存在案例 `generated/`，草稿不会自动发送。输入格式、评分边界与 CLI 见 [求职策略台](references/search-strategy.md)。

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

DeepSeek 调用只在服务端进行。填写的 API Key 通过本机工作台送到本地服务，并保存为本机用户配置文件（未加密）；Unix/macOS 将配置目录限制为仅当前用户访问、密钥文件权限设为 `0600`。已保存密钥不会被页面回读，也不写入生成文件、案例目录、项目仓库或 Vercel 预览。在本地工作台「投递进度 → 可选：DeepSeek 推荐摘要」可管理该配置。也可继续在启动进程环境中配置：

```bash
export DEEPSEEK_API_KEY='你的密钥'
export DEEPSEEK_MODEL='deepseek-chat'   # 可选
```

启动环境变量优先于界面保存项，兼容已有配置。界面不会显示或回传已保存的密钥；可随时清除本机保存项。工作台“投递 → 简历匹配推荐”中的“生成摘要”按钮只发送已选择偏好、推荐岗位标题和页面已展示的理由；没有 Key 时本地规则推荐仍可用。保存密钥本身不会联系 DeepSeek，只有点击“生成摘要”才调用服务端 API。摘要是辅助说明，岗位官网链接、硬门槛和投递状态仍需核验。

工作台已按用户确认恢复 `48ca8e4` 的视觉与布局，导航为总览、素材与作品集、JD 简历、投递进度、面试复盘、个人网站；岗位偏好在投递进度中设置。首页主按钮仍按档案状态引导上传、复核或分析岗位，目标、待确认事实与最近记录可在总览展开查看。JD 编辑器恢复左右两栏，下方保留 V2 要求、证据与选材审阅区。导入 PDF/Word 后保留原文摘录与来源；综合总结由 Codex 执行。可按完整事实库或某份 JD 简历生成同款作品集网站，本地保存复盘和自评。官网社招通过 Codex 浏览器与投递记录脚本执行，页面不提供无人值守投递服务。详见 [工作台说明](references/career-workspace.md) 和 [UI 恢复记录](docs/ui-restoration/README.md)。

投递页现在支持 [BOSS 岗位辅助筛选](references/boss-assisted.md)：导入自己持有的岗位 JSON/CSV 与屏蔽公司名单，按薪资、规模、双休等条件审阅，并把核对过的完整 JD 送进简历生成器。这里没有安装 Boss-Plus 私有脚本；筛选结果和招呼语草稿不会自动在 BOSS 开聊或投递。

只粘贴完整 JD 也可以生成。若正文中有“公司：”“岗位名称：”等明确标签，工作台会提取它们并在结果中提示复核；没有明确标签时仍会生成审阅稿，但公司或岗位名称会标为待补全，不能外发。

## 事实与隐私

真实案例应包含 `career-evidence-bank.md`、`coaching-state.md` 与派生的 `resume-evidence.json`。后者保存姓名、经历和来源摘要，属于私有候选人数据，**不要提交到公开 GitHub**。`tests/fixtures/` 仅使用合成 JD。

若要让后续迭代保留先前沟通，可在私有案例内维护 `user-requirements.md`：按日期追加用户目标、偏好、授权范围与实现位置。Skill 启动时先读取它；它不会进入公开预览，也不能替代原始聊天记录、职业事实或真实投递回执。

公开同步时提交 `skills/job-search-workflow/` 即可。该目录的 `tests/fixtures/synthetic-case/` 包含可运行的合成事实库与缓存，用于验证安装包不依赖任何个人案例；项目根目录的 `.gitignore` 默认排除真实 `job-search-cases/`、生成材料和本地验收输出。

生成器会拒绝事实源已经变化的旧缓存；会阻断职责不清、与明确硬条件冲突的岗位；会把未确认信息保留为待核实，不写成成果。

## 验证

使用带有 `reportlab` 与 `pypdf` 的 Python 环境运行：

```bash
python3 -m unittest discover -s tests -v
```

测试覆盖本地投递记录、PDF 材料生成、四类 JD 路由、负向岗位拦截、回环页面的跨站/文件隔离，以及恢复和去重逻辑。所有测试均使用临时或合成数据。

详细的数据约定、自动生成和外部执行边界见 [SKILL.md](SKILL.md)。

## Career Studio V2

本轮审计、匹配规则、兼容方案和真实测试记录在 [docs/career-studio-v2](docs/career-studio-v2/01-PRODUCT-AUDIT.md)。公开页面仍只使用合成数据，本地能力与 Skill 外部执行能力分别记录。没有生产部署或真实投递。

安全体验（临时合成档案，退出即清理）：

```sh
python3 scripts/demo_server.py --port 8875
```

打开 `http://127.0.0.1:8875`；`/demo` 为相同静态公开预览。首次无档案场景可加 `--empty`。真实案例启动仍沿用原命令，本轮没有修改任何真实案例。

岗位分析新增只读 `/api/selection`，展示主次方向、要求四状态、全部候选与未选原因。可调整 `project_priorities` 和 `selection_budget`，再生成独立版本。相同输入与事实复用既有文件；源文件或缓存内容变化会失效。`partial` 不等于满足，不能用于解除必需项阻断。生成材料保持 `preparing`。

浏览器测试使用 Playwright 和临时合成案例：

```sh
npm install
npx playwright install chromium
PYTHON_BIN=python3 npm run test:e2e
```

已有浏览器可用 `BROWSER_EXECUTABLE` 指定路径，避免重复下载。Python 需满足 requirements.txt，PDF 字体可通过 `RESUME_FONT_PATH` 指定；macOS 可使用已有 Arial Unicode。E2E 输出真实 PNG、JSON 和本地服务日志到 docs/career-studio-v2/evidence；本轮截图不是线上部署结果。
