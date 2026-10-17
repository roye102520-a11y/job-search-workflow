# Career Studio · 仅恢复 UI

2026-10-15 用户确认，以 `48ca8e4` 的视觉与布局恢复界面，保留 `749c319` 的业务功能、数据规则与安全逻辑。没有整仓回退，没有生产部署，没有操作真实候选人资料或外部求职平台。

## 版本与代码保护

| 用途 | 版本 / 分支 |
| --- | --- |
| 用户确认的视觉基准 | `48ca8e4`：保存改版前本地界面，已包含 JD 逐项分析与求职策略入口 |
| 同一旧版界面 | `8c1a6df`：界面文件与 `48ca8e4` 完全一致，后端数据修复已加入 |
| 更早候选 | `f107ddf`：风格相同，缺少上述本地新增入口，因此未选用 |
| UI 大改提交 | `aa95fc7`：首页、导航、公开页；`eeece37`：JD 三栏与证据选材呈现 |
| 恢复前业务基线 | `749c319754f8751498f8d5178f86624d59172d96` |
| 恢复前备份 | `codex/backup-before-ui-restore-20261015`，指向 `749c319` |
| 实施分支 | `codex/restore-classic-ui` |

开始时 V2 独立仓库干净。原始仓库 `skills/job-search-workflow` 有既存未提交修改，本次未编辑该仓库。所有工作在 `career-studio-v2` 独立仓库完成。未使用 `reset --hard`、`clean -fd`，未覆盖历史材料、台账或事实库。

## 恢复与适配

| 页面 | 恢复内容 | 保留的新版能力 |
| --- | --- | --- |
| 本地总览 | 原大标题、灰白底、蓝色胶囊按钮、原留白与统计卡片 | 主按钮按档案状态变化；下方保留下一步建议，可展开目标、档案完整度、待确认事实、最近岗位、未完成材料与真实提交记录 |
| 导航 | 总览、素材与作品集、JD 简历、投递进度、面试复盘、个人网站 | 原 hash、浏览器前进后退、键盘焦点与 `/studio`、`/strategy` 路径均保留 |
| 素材与作品集 | 原项目卡片与作品集控件位置 | 导入原文、来源复核、按某份独立简历选材、作品集与网站草稿 |
| JD 编辑器 | 原侧栏、米白深绿、左右两栏输入 / 材料预览、原空状态纸张与卡片 | 下方增加证据与选材审阅区，保留四级证据判断、主次方向、原始来源、全部候选、未选原因、预算和项目优先级 |
| 投递进度 | 原偏好设置、推荐与 BOSS 卡片的布局和样式 | 六阶段看板、规则分与概率区分、筛选命中 / 未满足 / 未知条件、来源与未知核验时间 |
| 面试 / 个人网站 | 原独立导航与页面 | 原复盘、个人网站草稿与历史入口；不触发外部发布 |
| 公开预览 | 原落地页布局、四个锚点导航、流程与三份岗位示例 | 首屏合成数据边界；五种使用场景移到使用方式旁展开，保留人工审阅状态说明与完整本地启动指引 |

PDF 沿用 V2 的文字审阅、下载和独立打开入口，不恢复旧版自动加载 PDF iframe。这个适配保留材料功能，避免浏览器内置 PDF 插件差异影响页面。

## 修改文件

- 界面：`assets/career-workspace.html`、`assets/career-workspace.css`、`assets/career-workspace.js`、`assets/jd-studio.html`、`public/index.html`、`public/styles.css`、`public/preview.js`。
- 页面缓存：`assets/sw.js` 只修改壳层版本名为 `career-studio-shell-classic-v3`，保留原缓存白名单、清理策略和网络优先逻辑。
- 测试与证据：`tests/e2e.cjs`、`.github/workflows/career-studio-v2.yml`、`.gitignore`、本目录。
- 使用与设计记录：`README.md`、`PRODUCT.md`、`DESIGN.md`、`.impeccable/design.json`、`references/career-workspace.md`。
- 为避免历史设计被再次误用，给 V2 的 `06-UI-REDESIGN.md`、`09-RELEASE-CHECKLIST.md` 增加历史记录提示，原验收结果与截图保留。

`assets/search-strategy.html` 保留 V2 版本，不回退四级证据标签。所有 `scripts/` 和合成夹具文件均与 `749c319` 逐字节一致，见 [保留校验](evidence/preservation-checks.json)。API Key 服务端接入、令牌、来源 / Host 校验、CSP、路径限制、JD 分类、硬门槛、选材、生成、缓存失效及去重逻辑均未回退。

## 截图对照

真实 Chromium 截图，全部使用临时合成数据。`before-*` 为恢复前 `749c319`，`classic-48ca8e4-*` 为隔离的历史视觉参考；无这些前缀的截图为实际恢复结果。参考预览使用当前后端，因此只用于确认历史外观，不表示旧版具备 V2 的全部功能。

| 页面 | 恢复前 | 恢复后 | 历史参考 |
| --- | --- | --- | --- |
| 本地首页 | [桌面](evidence/before-workspace-desktop.png) | [桌面](evidence/local-desktop.png) / [390px](evidence/local-mobile.png) | [48ca8e4](evidence/classic-48ca8e4-workspace-desktop.png) |
| JD 编辑器 | [桌面](evidence/before-jd-desktop.png) | [桌面](evidence/jd-desktop.png) / [390px](evidence/jd-mobile.png) | [48ca8e4](evidence/classic-48ca8e4-jd-desktop.png) |
| 公开页 | [桌面](evidence/before-public-desktop.png) | [桌面](evidence/public-desktop.png) / [390px](evidence/public-mobile.png) | [48ca8e4](evidence/classic-48ca8e4-public-desktop.png) |

更多证据包含六个本地页面在 360px / 1440px 的截图、JD 生成结果和手机证据审阅区。

## 已确认限制与人工验收

1. **已复现的离线限制，未修复**：`scripts/resume_server.py` 的 `script-src` 只有 nonce，未提供 `worker-src`；恢复后的浏览器已复现 Service Worker 注册被安全策略阻止。服务端文件与恢复前基线哈希一致，因此判断由存量策略导致；未单独运行恢复前版本的离线注册对照。原 V2 E2E 只遍历已有缓存，空缓存也会通过，不能证明离线能力可用。本次浏览器测试显式尝试注册，阻断单独计数，不计作通过。只更新了未来可使用的壳层版本名，未扩大安全策略权限。补充对照命令因自动审批账户额度故障未执行，不是操作被判定为不安全。
2. **原有输入要求**：7 天逐项计划需要「职位描述 / 职位要求」及编号。界面补充提示；测试覆盖未编号报错、保留输入、改为编号后恢复。普通完整 JD 可使用通用证据分析。
3. 真实 DeepSeek Key / 远端服务联调、真实资料、真实投递回执、手机 Safari / PWA 安装、不同浏览器 PDF 插件，以及用户对视觉的最终满意度仍需人工验证。本次未发起任何付费 API 调用或真实外部操作。

没有把未复现的风险写成已修复 Bug。完整结果见 [测试记录](TEST-RESULTS.md)。

## 本地预览与可恢复路径

当前合成数据工作台：[总览](http://127.0.0.1:8875/#overview)、[JD 编辑器](http://127.0.0.1:8875/studio)、[公开预览](http://127.0.0.1:8875/demo/)。预览读取的都是临时案例，不是用户真实档案。

也可在仓库中重新启动：

```sh
python3 scripts/demo_server.py --port 8875
```

停止服务会清理临时合成案例。备份分支保留恢复前完整代码；可以在单独检出目录比较，当前分支的 UI 恢复提交也可单独撤销。不要用整仓硬重置处理 UI。生产部署与真实数据操作仍待用户单独批准。
