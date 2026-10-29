# 旧模型出口 dev 验收

2026-10-19 阶段检查点，仅 AutoLab dev，不 push、不写生产、不启用组件。范围来自第一阶段已批准的“旧路径未适配时 unavailable，确定性流程仍按原权限工作”；这次关闭旧模型传输，不表示所有旧业务已迁移。

## 行为与提交

| 提交 | 行为 |
| --- | --- |
| f856af0 | Context.ask、旧 Chat/结构化 helper、管理 ModelProxy 基类、远程 OCR 都明确拒绝，不能使用站点模型、CLI 或未计量 fallback；新 AgentModelProxy 覆盖 forward，继续原 SDK/本人端点/AiRun 链 |
| 7d70512 | course.index、plagiarism.scan、code_similarity 的确定性准入不要求 AI 积分或已对账；原身份、资源权限、账号停用与租约继续生效 |

初审发现直接关闭旧出口会连带中断查重和索引，已在 f856af0 修复。可选内容审核只捕获专用适配器不可用异常，权限/租约错误继续中断。查重保留 JPlag 证据，AI 解释与审核保持待完成，不生成自动处分结论；历史 code_similarity 保留同一确定性扫描路径。

普通文本索引保留分块为 review、父文档为 review，清除 indexed_version，不构造正常审核记录。原分块分页、引用解析和课程 RAG 均要求当前索引版本，故不公开这次待审核索引。本人或原管理权限仍可检查原资料与待审结果。扫描 PDF 需要 OCR 时明确失败，不静默发布缺页文本；索引发布/审核适配仍待实现。

首个普通文档翻译的新 SDK 链继续在每次调用预留前重验来源、策略和本人端点。已失败或达到输出上限的 Responses，已知用量必须先结算失败调用再交给 SDK；缺失用量进入 unsettled 并阻断下一次模型/工具请求。免费测试授权仅适用于用户专用端点，不把其他端点或缺失用量解释为免费。

## 验证与审计

- f856af0 独立审计接受，逐 hunk 复核；审计发现的混合任务中断已修复。独立新 SDK、端点计费与旧 framing 组合 73 项通过；混合任务/原后端组合 114 通过、1 既有跳过。
- f856af0 的 28 个测试文件联合 439 通过、3 跳过、0 失败，69.13 秒。包含真实独立 SDK 子进程、worker 与随机自有 MySQL；供应商和 fresh Java 身份 RPC 使用 fake。
- 3 个跳过为 2 项未 opt-in 的 live provider 测试，以及 test_mysql_concurrent_claims_respect_global_limit。未调用专用测试 API，不消耗试用额度。
- 旧管理代理已不提供模型执行，原 streaming/计费测试改为明确拒绝、临时 token/路由/边界校验。原同任务 MySQL 预算测试随旧代理退役；新增 test_agent_proxy_mysql 验证真实 typed API → queued_binding/claim/current_scope → 新 AgentModelProxy：首请求尚未结算时，第二请求因同任务预算拒绝且不到达假供应商，第一请求正常结算。该用例真实 MySQL 1 项通过；不能替代全局 claim 锁测试。
- 新 SDK failed/incomplete × 已知/缺失用量 4 个反例检查失败结算、幂等回放、零平台扣款和未结算阻断。旧原始 HTTP/CLI 测试改为拒绝前无外部调用及无 AiRun/扣款，未恢复旧传输来满足旧测试。
- 7d70512 的 15 个新增准入反例覆盖三类任务在 submit/claim 时遇到负积分或旧 unsettled 仍可继续，停用账号仍拒绝新建并取消排队任务，后续模型任务仍因账务拒绝。联合原后端/退役测试为 129 通过、1 既有跳过，4.30 秒。
- 7d70512 独立审计接受；另补 9 项反例通过，确认积分豁免不能调用退役模型、绕过实际模型账务或失效的资源权限。它们是外置审计测试，不倒填为仓库内 15 项的一部分。

本机工作目录 platform-v2-implementation-20261018 保存 audit-legacy-model-retirement、audit-mixed-task-admission 审计报告，legacy-retirement-baseline-f856af0.log/xml、legacy-retirement-proxy-mysql.log、mixed-task-admission.log。历史 447 项与本次 439 项测试集合不同，不能只比较总数推断新增或丢失覆盖。没有真实网关、Redis、生产、浏览器或 Linux 安装验收。

## 仍未放行

INSTALLED_COMPONENTS 仍为空。旧 API/批量/重试可排入随后不可用的模型任务，旧 claim/完成/候选采用还需要统一 gate 和来源绑定。后续 99987b6 已单独关闭旧管理 turn 与 pending 批准，并保留历史清理；前端及验证边界见 [16](16-旧管理入口dev验收.md)，不能扩张为所有旧 AI 采用链已迁移。下一批先补其余服务器边界，再接其余前端开关及组件。平台实施继续推进，48 项任务保留原状态，不标为完成；原历史查询、取消、端点修复、确定性管理流程保持独立。
