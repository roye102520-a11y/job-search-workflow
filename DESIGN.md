---
name: Career Studio Classic
description: 用户确认恢复的经典界面，保留 V2 业务与安全能力
colors:
  bg: "#f5f5f7"
  surface: "#ffffff"
  ink: "#1d1d1f"
  muted: "#6e6e73"
  accent: "#0066cc"
  line: "#e5e5e8"
  public-muted: "#5d5d65"
  public-line: "#dedee2"
  jd-paper: "#f4f5f0"
  jd-ink: "#222d27"
  jd-muted: "#6b756e"
  jd-line: "#dfe5dd"
  jd-green: "#285742"
  jd-soft: "#eaf0e9"
  warning: "#81551d"
  error: "#9b392c"
typography:
  headline-local:
    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "PingFang SC", "Helvetica Neue", sans-serif'
    fontSize: "clamp(38px, 5.3vw, 68px)"
    lineHeight: 1.13
    fontWeight: 650
  headline-public:
    fontSize: "clamp(48px, 5.5vw, 78px)"
    lineHeight: 1.12
    fontWeight: 650
  body-local:
    fontSize: "15px"
    lineHeight: 1.6
  body-public:
    fontSize: "16px"
    lineHeight: 1.6
  body-jd:
    fontSize: "14px"
    lineHeight: 1.65
rounded:
  local-card: "24px"
  local-action: "24px"
  local-nav: "20px"
  jd-card: "16px"
  jd-field: "8px"
spacing:
  local-content: "48px"
  local-hero-top: "72px"
  local-hero-bottom: "62px"
  local-card: "30px"
  jd-review: "26px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.surface}"
    rounded: "{rounded.local-action}"
    padding: "12px 21px"
  navigation-local-current:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.surface}"
    rounded: "{rounded.local-nav}"
  button-primary-jd:
    backgroundColor: "{colors.jd-green}"
    textColor: "{colors.surface}"
  card-jd:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.jd-card}"
---

# Career Studio · 经典界面

## 视觉依据

用户于 2026-10-15 确认恢复 `48ca8e4` 的视觉与布局。`8c1a6df` 的界面文件与其一致。当前业务基线为 `749c319`，不能整仓回退。改版前的真实浏览器参考截图与恢复后截图位于 `docs/ui-restoration/evidence/`。

保留原有大标题、系统字体、冷灰白底、蓝色按钮、圆角卡片、胶囊导航和留白。JD 编辑器沿用原来的米白与深绿，不强行统一成蓝色。用户选定的历史样式优先于通用审美建议；不再把主界面改成暖绿任务面板或五项导航。

## 页面与布局

| 页面 | 当前结构 | 窄屏 |
| --- | --- | --- |
| 本地工作台 | 六项导航：总览 / 素材与作品集 / JD 简历 / 投递进度 / 面试复盘 / 个人网站；主内容最大 1320px，左右 48px；原大标题和五阶段路径 | ≤760px 内容左右 22px，≤520px 为 16px；导航可横向滚动，卡片堆叠 |
| 总览 | 原英雄区、路径、事实标签统计、真实提交统计；新增状态建议和可展开的档案 / 最近进度在下方 | 主按钮按档案状态引导上传、复核或分析；不填充虚构数量 |
| JD 编辑器 | 原侧栏与左右两栏：岗位输入 / 材料预览；分析后在下方展示两列证据与选材审阅区 | ≤870px 审阅区堆叠，沿用原输入与材料区响应式规则 |
| 公开预览 | 原落地页，四个锚点导航、大标题、产品原则、流程、岗位选材示例、BOSS 合成说明与启动方式 | 原有移动断点；五种合成使用路径在使用方式附近按需展开 |
| 投递进度 | 偏好设置回到原位置，原卡片样式承载 V2 六阶段 | 三列 → 两列 → 单列 |

## 交互和兼容

- 保留所有 V2 证据判断、来源原文、已选 / 未选候选、理由、预算与项目优先级、独立版本和过期提示。
- 来源对话框有标题、关闭按钮、键盘焦点；状态由文字和颜色共同表达。
- 保留跳转正文、3px 键盘焦点、原生表单、加载 / 错误 / 空状态以及前进后退。
- PDF 沿用 V2 的文本审阅、下载和独立打开入口，避免恢复旧版自动嵌入 PDF 带来的浏览器差异。
- Service Worker 只更新壳层版本名，不改变缓存白名单或服务端 CSP。当前 CSP 阻止其注册，在线界面可用；不能声称离线验收通过。
- 公开页始终明确合成内容，不能读取真实候选人资料，也不连接 BOSS 账号。

当前恢复范围和实测结果以 `docs/ui-restoration/README.md` 为准。V2 设计文档保留为历史记录。
