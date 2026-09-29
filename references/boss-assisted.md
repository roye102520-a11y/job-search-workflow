# BOSS 岗位辅助筛选

本模块吸收用户描述的 Boss-Plus 功能诉求，但独立实现为**本地导入与审阅**。没有获得或安装 dddvi 的私有脚本，也没有验证其版本、导出格式或权限。工作台不读取 BOSS 账户、不操作网页、不批量开聊、不提交简历。

可核验的 BOSS 官方 [2019 年用户协议页面](https://www.zhipin.com/web/common/protocol/protocol-2019-09-30.html) 对未经许可的第三方工具、插件、拟人程序等有限制；当前应以用户账户展示的最新版协议为准。因此不要把“控制每天投递量”写成规避限制的保证，也不要在无授权接口的情况下新增自动投递脚本。

## 工作台使用

在本地工作台的“投递进度 → BOSS 岗位辅助筛选”中：

1. 设置关键词、城市、月薪 K 区间、公司规模、双休线索及公司在招岗位数上限。`0` 表示不限制。筛选设置保存在**当前案例** `boss-settings.json`；首次打开会沿用 `search-preferences.json` 的地点和排除公司。
2. 如已有个人屏蔽名单，从本人可访问的页面复制公司名称，一行一个粘贴导入；该按钮只处理你粘贴的文字，不会从 BOSS 隐私设置自动读取。公司名按规范化后的完整名称匹配，简称、品牌别名及子公司关系需要人工核实。
3. 粘贴或选择你已合法取得的 JSON/CSV 岗位列表。工作台一次最多 500 条、2 MB，至少包含 `url/company/title` 或 `岗位链接/公司/岗位`，可补充 `city/salary/company_size/open_positions/tags/description` 等字段。数据保存在当前案例 `boss-jobs.json`；修改偏好后会重新筛选原列表。
4. 结果分为**候选**、**待核实**、**排除**、**重复**。薪资未公开、双休未明确、岗位链接无法识别时不猜测。匹配只基于导入文字，不能证明岗位仍在招。
5. 可填写自己的招呼语模板，仅允许 `{company}`、`{title}` 两个占位符；确认模板后生成**待复制草稿**。草稿不发送，也不视为已沟通。
6. 对完整 JD，本人核对并勾选后可送入 `/studio` 自动生成岗位匹配、简历 PDF 和邮件草稿；只有职位摘要时先补齐 JD。JD 生成后仍是本地审阅稿，不能计为已投递。

标准 BOSS 职位详情 URL 的已知会话参数会从结果链接移除，按详情路径中的岗位 ID 去重。无法识别的 URL 保留待核实，不能用相同公司和标题就合并。冲突记录必须人工检查。

## CLI 与数据边界

不使用页面时可运行：

```bash
python3 scripts/boss_assist.py --jobs /absolute/path/jobs.csv --config /absolute/path/boss-settings.json --blocked-companies /absolute/path/blocked.txt --output /absolute/path/review.json
```

CLI 也只生成本地筛选结果，不登录 BOSS。JSON 接受岗位数组或 `{ "jobs": [...] }`；CSV 接受中英文表头。结果中的 `shortlist` 仅表示符合已提供条件，`needs_verification` 不是失败或成功投递。

真正投递仍按 [投递执行](application.md) 使用独立 JD 材料、明确授权和真实回执。BOSS 的手动开聊或投递可由用户报告并附截图/回执记录，但不能因复制招呼语或打开职位链接就将台账改为 `submitted`。官网社招搜索继续按 [社招筛选](social-recruitment.md) 单独处理。
