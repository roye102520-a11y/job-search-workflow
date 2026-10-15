---
name: Career Studio V2
description: 温暖、清楚、以真实经历为依据的个人求职工作区
colors:
  bg: "#f7f6f2"
  surface: "#fff"
  ink: "#242b28"
  muted: "#626b65"
  line: "#d9ded8"
  accent: "#285742"
  accent-hover: "#214b37"
  soft: "#eaf0e9"
  selection: "#d9e9dd"
  warning: "#81551d"
  error: "#9b392c"
  jd-paper: "#f4f5f0"
  jd-ink: "#222d27"
  jd-muted: "#6b756e"
  jd-line: "#dfe5dd"
  jd-field: "#fdfefa"
  jd-gap-bg: "#fbf0dd"
  jd-conflict-bg: "#fae9e6"
typography:
  headline:
    fontFamily: '-apple-system, BlinkMacSystemFont, "PingFang SC", "Helvetica Neue", sans-serif'
    fontSize: "36px"
    lineHeight: 1.25
    letterSpacing: "-.025em"
  headline-mobile:
    fontSize: "30px"
  headline-local:
    fontSize: "36px"
    fontWeight: 650
    lineHeight: 1.25
    letterSpacing: "-.025em"
  headline-jd:
    fontSize: "34px"
    fontWeight: 680
    lineHeight: 1.3
    letterSpacing: "-.025em"
  headline-jd-mobile:
    fontSize: "29px"
  title-public:
    fontSize: "23px"
    lineHeight: 1.35
    letterSpacing: "-.025em"
  title-local:
    fontSize: "24px"
    lineHeight: 1.3
    letterSpacing: "-.025em"
  title-jd:
    fontSize: "17px"
    fontWeight: 650
    letterSpacing: "-.25px"
  body:
    fontFamily: '-apple-system, BlinkMacSystemFont, "PingFang SC", "Helvetica Neue", sans-serif'
    fontSize: "15px"
    lineHeight: 1.65
  body-local:
    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "PingFang SC", "Helvetica Neue", sans-serif'
    fontSize: "15px"
    lineHeight: 1.6
  body-jd:
    fontFamily: '-apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif'
    fontSize: "14px"
    lineHeight: 1.65
  label:
    fontSize: "12px"
  action-local:
    fontSize: "14px"
  action-jd:
    fontSize: "13px"
    fontWeight: 600
rounded:
  control: "8px"
  surface: "12px"
  chip: "4px"
  jd-primary: "9px"
  local-field: "10px"
  local-nav: "20px"
spacing:
  "4": "4px"
  "8": "8px"
  "12": "12px"
  "16": "16px"
  "20": "20px"
  "22": "22px"
  "24": "24px"
  "28": "28px"
  "32": "32px"
  "48": "48px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.surface}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "11px 18px"
  button-primary-hover:
    backgroundColor: "{colors.accent-hover}"
  button-secondary:
    backgroundColor: "{colors.soft}"
    textColor: "{colors.accent}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
  button-text:
    backgroundColor: "transparent"
    textColor: "{colors.accent}"
    padding: "10px 0"
  button-primary-jd:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.surface}"
    typography: "{typography.action-jd}"
    rounded: "{rounded.jd-primary}"
    padding: "11px 18px"
  field-jd:
    backgroundColor: "{colors.jd-field}"
    textColor: "{colors.jd-ink}"
    typography: "{typography.body-jd}"
    rounded: "{rounded.control}"
    padding: "10px 12px"
  navigation-public-current:
    backgroundColor: "{colors.soft}"
    textColor: "{colors.accent}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
  navigation-local-current:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.surface}"
    rounded: "{rounded.local-nav}"
    padding: "8px 17px"
  chip-gap:
    backgroundColor: "{colors.jd-gap-bg}"
    textColor: "{colors.warning}"
    typography: "{typography.label}"
    rounded: "{rounded.chip}"
    padding: "3px 8px"
  card-jd:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.surface}"
    padding: "22px"
---

# Design System: Career Studio V2

## Overview

**Creative North Star: "Apple clarity / Airbnb friendliness"**

以清楚的任务层级、系统字体和温暖中性色承载求职工作。深绿承担主要动作与相关状态，文字、留白和细分隔线组织内容。页面保持接近原生控件的熟悉感，让第一次使用的人也能看懂下一步。

这是已有构建的 Operate / code-led 设计记录，保留当前视觉方向。提取依据是 `public/index.html`、`public/styles.css`、`public/preview.js`、`assets/career-workspace.html`、`assets/career-workspace.css`、`assets/career-workspace.js`、`assets/jd-studio.html` 及存量桌面 / 手机截图。前置 token 记录实际复用值；三种 surface 的差异分别列出，后续屏幕应沿用所属 surface 的值。

**Key Characteristics:**
- 温暖中性色与一个主要深绿强调色。
- 系统字体，清楚标题与易扫描的短段落。
- 平面层次、细分隔线与轻圆角。
- 核心内容先呈现，证据来源与高级功能渐进展开。
- 手机正文顺序堆叠，导航保持可访问。

## Colors

暖白、偏绿灰的文字和边线构成安静的底色；状态色帮助区分证据判断。

### Primary
- **深绿**（`accent`）：公开页主要按钮、链接与选中导航；本地工作台的 `--blue` / `--green` 在 V2 覆盖层均映射到它；JD 工作区以 `--green` 使用同一个值。
- **悬停深绿**（`accent-hover`）：主要按钮的悬停背景。
- **浅绿**（`soft`）：次级动作、直接证据标签、公开页选中导航、JD 选中导航与生成版本按钮的背景。

### Neutral
- **暖白底色**（`bg`）、**白色表面**（`surface`）：公开页 / 本地壳层与内容容器。
- **正文绿灰**（`ink`）、**次级绿灰**（`muted`）、**细边线**（`line`）：公开页 / 本地的文字与分隔层级。
- **JD 纸面**（`jd-paper`）、**JD 正文**（`jd-ink`）、**JD 次级文字**（`jd-muted`）、**JD 边线**（`jd-line`）、**JD 输入面**（`jd-field`）：JD 工作区已实现的独立中性色组。
- **文本选区**（`selection`）：浏览器文字选中背景。

### Status
- **待核实琥珀**（`warning` / `jd-gap-bg`）：部分相关、证据不足及公开页待确认说明。
- **矛盾砖红**（`error` / `jd-conflict-bg`）：JD「明确不满足」状态。
- 标签必须同时显示文字。颜色不单独表达证据等级。

**The Primary Accent Rule.** 新增核心任务组件沿用深绿作为主要强调色。现有次级工具仍含历史蓝、紫及不同状态背景；它们是已实现差异，不是新的全局 palette。

## Typography

**Display / Body Font:** 系统无衬线栈，以 Apple 系统字体和 PingFang SC 为先。完整栈按 surface 记录在 frontmatter；本地栈额外列出 SF Pro Display，JD 栈以 Microsoft YaHei 作中文 fallback。源码没有下载自定义字体。

**Character:** 熟悉、清楚、适合密集事实与说明。主要标题略收紧字距，正文保持宽松行高。

### Hierarchy
- **Headline**：公开页（`headline`）与本地（`headline-local`）桌面标题大小相同；两者在宽度不超过 760px 时使用 `headline-mobile`。JD 使用 `headline-jd`，宽度不超过 870px 时沿用 `headline-jd-mobile`。
- **Title**：公开页一般 h2 用 `title-public`，本地一般 h2 用 `title-local`，JD 用 `title-jd`。公开页决策列 / 卡片标题另为（18px）；本地 h3（18px），公开页 h3（17px）。
- **Body**：公开页用 `body`，本地用 `body-local`，JD 用 `body-jd`。JD 证据正文与选材说明为（13px），材料详情报告为（13px / 1.75）。
- **Label**：说明文字的复用下限为 `label`；导航为（13px）。JD 输入框 placeholder 使用次级文字色，不沿用原先较浅的颜色。
- **Action**：公开页动作继承正文大小，本地主要动作用 `action-local`，JD 主要动作用 `action-jd`。
- 公开页段落最长（72ch），本地首页引导最长（64ch）。这些是已实现容器约束，不是全局强制行长。

**The Surface Type Rule.** 不把公开页、本地和 JD 的字号 / 行高差异写成一套统一值。新增页面先选择所属 surface，再复用它的层级。

## Layout

已复用的间距记录在 frontmatter。它们来自现有 CSS 的实际值，源码没有独立的 spacing 自定义属性；（10px / 11px / 18px）等控件内边距仍按具体组件记录。

| Surface | 桌面结构 | 窄屏行为 |
| --- | --- | --- |
| 公开演示 | 主内容最大宽度（1160px），页头（1200px）；主内容左右内边距（32px）。任务摘要两列（48px gap），五步流程五列。岗位演示三列等宽，每列内边距（28px）。 | ≤760px 时主内容左右（20px），h1 收缩，任务摘要 / 流程 / 岗位演示堆叠；主导航横向滚动。进度卡片仍两列，≤380px 才单列。 |
| 本地工作台 | 主内容最大宽度（1320px），≥1600px 时（1420px）；左右内边距（48px）。首页摘要比例（1.25fr / 1fr），gap（20px）。 | ≤1000px 时首页两列等宽，≤760px 单列，流程五步顺序堆叠；左右内边距（22px），≤520px 为（16px）。导航在≤520px 横向滚动。求职看板为三列，≤760px 两列，≤420px 单列。 |
| JD 工作区 | 侧栏（170px），主内容最大宽度（1520px），左右内边距（24px）。输入 / 证据与差距 / 选材与下一步三列（`minmax(260px,.9fr) minmax(270px,1fr) minmax(280px,1.05fr)`），gap（16px）。第三列下接材料预览。 | ≤1200px 隐去侧栏形态，导航移到顶部；输入 / 证据两列，第三列跨整行。≤760px 按输入 → 证据 → 选材及预览单列堆叠，左右内边距（16px），输入 / 证据卡内边距（20px）。 |

JD 在 iframe 内使用 `.embedded` 三列等宽，仍在 1200px / 760px 断点改为两列 / 单列。本地 iframe 的高度为桌面（1450px）和≤760px（2500px）；它是固定高度容器。

以上是当前三个具体 surface 的组合方式。新的 surface 可复用间距、阅读次序和渐进展开，不把某一页的列数当作全局模板。

## Elevation & Depth

核心任务页以背景、白色表面和边线建立层次。JD 卡片的 V2 覆盖明确去掉了原阴影与装饰纸张。公开页没有卡片阴影；本地大部分核心容器也没有阴影。

### Shadow Vocabulary
- **作品网站预览**（`box-shadow: 0 15px 45px #00000005`）：本地原有网站预览容器的低强度阴影。
- **对话框遮罩**（`background: #0005`）：本地资料对话框还带（4px）背景模糊，JD 来源对话框仅使用遮罩。

本地在系统允许动态效果时仅保留按钮 / 链接的背景与颜色过渡（.2s）；V2 将 section 入场动画设为 none。JD 输入边线 / 阴影过渡（.15s），忙碌 spinner（1s linear infinite）。源码没有一套命名 motion token。

## Shapes

主要 surface 使用 `surface` 圆角；多数动作与 JD 输入用 `control` 圆角。JD 主按钮保留 `jd-primary`，本地输入用 `local-field`，证据状态标签用 `chip`。

本地主导航保留 `local-nav` 胶囊外形，公开页选中导航和 JD 链接更接近轻圆角矩形。本地偏好选项仍是（999px）胶囊。不同形状是当前组件差异，不统一替换。

## Components

### Buttons
清楚区分主要动作、次级动作与文本动作。

- **Primary**：公开页使用 `button-primary`；本地使用相同颜色 / 形状与 `action-local` 字号；JD 使用 `button-primary-jd`。公开 / 本地主动作最小高度（44px），JD 主动作（45px）。
- **Secondary / Text**：公开页分别使用 `button-secondary` / `button-text`；本地 secondary 内边距（11px 18px）；JD「生成独立简历版本」继承主按钮形状，但用浅绿背景与深绿文字。
- **Hover / Focus**：主按钮悬停使用深绿；键盘 focus-visible 使用深绿（3px）轮廓与（3px）offset。JD 字段有单独的后置 focus-visible 规则，覆盖早先的 outline:none 并去掉 box-shadow。
- **Disabled / Busy**：本地按钮 opacity（.5），JD（.65），指针为 wait。不能把最小主动作高度推广到所有控件：来源按钮 / 合成样例按钮为（36px），更新选材动作（43px）。

### Chips
用短文字标记证据等级，避免仅依赖颜色。

- **Status**：直接证据为浅绿 / 深绿；部分相关和证据不足使用 `chip-gap`；明确不满足用砖红组。复用圆角与标签字号见 frontmatter。
- **Choice**：公开演示岗位切换使用 aria-pressed；本地偏好胶囊中的 checkbox 保留原生表单语义，选中为深色底白字，focus-within 将可见轮廓画在胶囊上。

### Cards / Containers
平面、轻圆角，用内容分组而非装饰吸引注意。

- **Public**：决策三列共用白色容器，列间边线在窄屏变为行间边线；独立进度卡内边距（24px），窄屏（20px）。
- **Local**：首页白色 surface 使用（28px）内边距；V2 后置覆盖使手机上仍为这个值。其他次级工具各自保留现有内边距。
- **JD**：使用 `card-jd` 的 surface / padding 与 JD 边线；手机输入 / 证据卡为（20px），第三列控制区仍（22px）。核心 JD 卡无阴影。

### Inputs / Fields
保留原生输入行为和持续可见的标签。

- **JD**：`field-jd` 配（1px）边线，textarea 最小高度（260px）、文本（13px / 1.8），可竖向调整。选择器和文本输入填满所在列。
- **Local**：输入用白色背景、本地正文色、（10px）圆角与（11px 12px）内边距；文件输入仅存在于本地。
- **Focus**：JD 鼠标 focus 的边线为（#799785），浅光圈为（#e8eee7）；键盘 focus-visible 用前述明确轮廓。公开页可交互的 select、按钮、链接与 summary 有同样的键盘轮廓。本地使用全局 focus-visible，偏好胶囊另有 focus-within。
- **Status**：JD 输入缺失或不足时仍保留内容，将焦点放回 JD 并通过 role=status / aria-live=polite 提示；错误状态使用现有暖红背景。没有新增统一的字段错误或 disabled token。

### Navigation
五个一级入口保持同一顺序：工作台、我的档案、岗位与简历、求职进度、作品展示。

- **Public**：sticky 顶部导航；选中按钮用 `navigation-public-current`，其余为透明底次级字色。
- **Local**：sticky 顶部导航；选中按钮用 `navigation-local-current`，未选中 hover 沿用历史（#e9e9ec）背景。手机横向滚动行为见 Layout。
- **JD**：宽屏侧栏链接，选中项浅绿底；≤1200px 顶部换行导航；嵌入工作台时隐藏侧栏。
- 公开 / 本地的面板切换同步 aria-current 和 URL hash，并将焦点移到当前页面标题。三个 surface 均提供可聚焦的跳转主内容链接。

### Evidence / Selection
按事实判断递进阅读，保留追问依据。

- **分工**：JD 左列只放岗位输入、分析 / 生成动作；中列放要求、状态、理由及来源；右列放项目优先级、篇幅预算、选材与预览。
- **展开**：证据来源、方向依据、全部候选及未选理由用原生 details / summary；查看原始事实打开 dialog，不把全部内容预先堆在主视图。
- **版本**：调整输入或优先级后要求重新分析，旧结果保留作对照；重新生成独立版本。该行为属于 JD 工作区，不是全部页面的全局布局规则。

## Do's and Don'ts

### Do:
- **Do** 沿用所属 surface 的系统字体、字号和中性色组。
- **Do** 让主要动作、状态文字和下一步形成清楚层级。
- **Do** 为按钮、链接、字段、summary 和选择胶囊保留可见键盘焦点。
- **Do** 在窄屏按内容顺序堆叠，并保留可访问的导航。
- **Do** 用文字区分直接证据、部分相关、证据不足与明确不满足。
- **Do** 保留来源和候选理由的渐进展开及独立版本入口。

### Don't:
- **Don't** 将三个 surface 的字号、圆角、间距或响应式规则写成单一默认值。
- **Don't** 为核心任务页添加未确认的第二强调色、装饰插图或入场动画。
- **Don't** 用过浅的说明文字或取消轮廓来隐藏键盘焦点。
- **Don't** 将某一页的三列结构扩大为所有页面的布局要求。

本次文档收尾依据源码和六张存量截图；未另开浏览器、未重新运行测试。独立 finish reviewer 的最终 disposition 为 **ship**，仅对其原三项「三列分工」「小字号 / 颜色」「键盘焦点」确认 **resolved**。这不代表完整线上验收。设计检测器引擎不可用，未成功运行；既有测试摘要还记录线上导航超时及未部署状态。证据位于 `docs/career-studio-v2/evidence/`，后续发布结论须另有实际验证。
