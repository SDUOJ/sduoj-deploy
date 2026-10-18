# 旧管理入口 dev 验收

2026-10-19 检查点，承接 [15](15-旧模型出口dev验收.md)。只改 dev，不 push、不写生产、不启用组件。关闭旧模型传输不能阻止已经生成的 pending 管理操作继续执行，本轮补上这一缺口。

## 提交与实际行为

| 仓库 / 提交 | 结果 |
| --- | --- |
| AutoLab 99987b6 | 旧 start_turn 先验原 owner/admin/账号状态，然后返回不可用，不创建 TaskJob 或读取站点 provider；旧 Agent 构造器只拒绝，不建工作目录或启动 Codex；历史 run_turn 保留 fresh 身份/来源检查后明确拒绝 |
| web2 084e51f | 旧页面仅查看历史、停止、拒绝；独立审计 needs_fix，旧轮询能覆盖停止后的新状态，未把该 SHA 认作可用终态 |
| web2 518eb40 | 轮询和操作后读共享单调详情序号；操作开始使旧响应失效，进行中暂停新轮询，原身份/选择代次继续校验。独立反例已通过，最终修订接受 |
| web2 3615267 | test-only：原 ai-authoring 别名仍保留 canonical URL/query/hash 与窄屏检查，预期从“新建”改为历史提示可见且无新建按钮；仅通过 tools TypeScript 静态检查，未运行真实 dev 浏览器 |

旧批准请求仍先检查 owner/admin、任务、当前 lease、action/hash 和 pending 状态，但有效的旧候选也明确拒绝，不能通过手工设置组件开关恢复执行。拒绝不需要模型、组件启用或 AI 使用资格，状态与结果同事务保存；停止使 pending 变 expired、执行中变 unknown。查看、拒绝与停止仍需原本人管理员权限，不向其他管理员开放私有会话。

execute_action 同时用于手工编程题组引用的来源校验，因此保留原实现：当前请求 Cookie、原接口白名单、禁 redirect、禁环境代理，不持久化 Cookie。不能把这个共用手工 HTTP helper 一并关闭。旧管理批准已不再调用它；新管理 SDK 的受限工具/持久确认链仍待实现。

前端旧管理 API facade 只保留 list/detail/reject/stop，reject 固定 approve=false；页面不再展示新建、发送、批准弹窗。只为 /manage/intelligent 的历史路由启用 allowSuspended，其他 AI 路由默认仍不允许暂停账号进入执行页。服务端原权限继续决定操作是否允许。

私有页面复用原 Redux 的主体/权限 epoch，账号、用户名、角色、组变化及 ABA 都重建页面；迟到列表/详情和旧身份操作后的继续请求被丢弃。列表请求也校验序号，卸载清轮询。此处是旧历史页清理，不是新管理组件的能力发现或 SDK 前端验收。

## 验证和审计

- AutoLab 99987b6：7 个文件联合 120 项通过，8.58 秒；包含管理/网关、原生题库与手工题组来源链。独立回归 4 suites/113 项通过；最终管理测试及外置反例 26 项通过，包括暂停 owner 可 stop、被替代绑定、过期租约不重放、手工 POST/Cookie/body。两组有重叠，不相加为覆盖总数。
- 旧 Codex 协议与多进程批准正向测试随入口退役，改为旧构造器、任务与批准均不可执行的反例。没有将旧 CLI 测试删除说成新管理 SDK 的协议或并发验收成功。
- web2 084e51f 的主测为 5 suites/48 项通过，但独立时序反例仍失败。518eb40 加入 stop/reject 两个旧轮询反例后，同组合 50 项通过，10.785 秒；最终应用 TypeScript 与目标 ESLint 通过。
- 独立审计保留 084e51f needs_fix 记录；原失败反例修复后 2 项通过，4.186 秒；最终独立 4 suites/26 项通过，9.622 秒。先前一次主测失败是 AntD 中文两字按钮空格的测试定位问题，原日志保留，未用修改产品行为修复选择器。
- 3615267 只修正旧真实 dev 浏览器测试的预期。该测试需要专用业务账号和真实 Gateway；本轮未执行，不宣称真实浏览器、MySQL 多进程、身份 RPC、模型调用或生产验证。组件测试中的账户/接口及后端身份 RPC 是隔离 fixture。

工作目录 platform-v2-implementation-20261018 保存 audit-legacy-management-gate.md/json、audit-legacy-management-history-frontend.md/json、084e51f-initial 审计、audit-legacy-management-alias-test.md/json，以及 legacy-management-boundary-regression.log、legacy-management-history-frontend-initial/fixed.log、legacy-management-history-poll-regression.log 与 tsc/eslint 日志。

## 剩余

本检查点关闭了旧管理入口，当时历史记录仍可能先 claim 后在 worker 明确失败。后续旧任务入队/批量/重试和共享持久化见 [17](17-旧任务入队dev验收.md)，claim、运行时与完成检查见 [18](18-历史worker执行边界dev验收.md)；旧候选采用仍待收口。普通文档新 SDK 链保持，INSTALLED_COMPONENTS 仍为空，原 48 项任务状态未修改，platform v2 不作为可以启用的发布候选。
