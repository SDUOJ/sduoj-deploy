# 本人端点的 dev 页面与验收

本轮只接本人配置入口，不放行 Agent 业务组件。web2 基线为 c4ef1cc，AutoLab 实现仍沿用 0bf775c；c94e05a 增加专用免费提供商的 opt-in 验收，83f0bda 随后仅硬化测试路径与诊断分类。总体进度见 [11](11-dev实施进度.md)，后端任务链见 [12](12-Agent后端dev验收.md)。

## 页面使用

1. 使用现有 OJ 登录，在 dev 构建打开 `/v2/account/assistant/ports`，或从 AI 工作区的“我的模型端点”进入。普通 USER 可用，不经过 M 布局或 AI provider/积分门禁；release 构建继续移除该路由。
2. 新增名称、HTTPS API 地址、本人模型名、API key 和正数预算。协议固定为 Responses；换地址需新 key。编辑时 key 留空表示保留，接口不返回原值。摘要是指纹，不是密钥尾号。
3. 价格可未知，此时只保存配置，不准入模型任务。明确估价时填写输入、缓存输入、输出的 USD/百万 token，并确认；三项全零还须独立确认免费。地址/模型变化清除旧价格选择。
4. 设为默认需另确认；没有默认不自动选其他端点。停用清除默认，重新启用不恢复旧默认或重跑任务。删除有未结束任务时由原服务端拒绝。
5. 未确认的写结果保留同一操作 key、正文和版本供显式重试，表单锁定。若要改内容，关闭并刷新，核对当前版本后再操作；关闭不表示服务端已撤销旧请求。
6. “模型目录诊断”先读历史/请求范围，明确勾选才建立独立单次目录任务；支持取消、同任务轮询和历史重开，未知写仅重试原操作。它不发送推理，不需要模型价格，不展示模型 ID/提供商正文，也不证明 Responses/工具可用；原三次 Responses 探测保持独立。任务及真实 worker 浏览器验收见 [30](30-models任务与前端dev验收.md)。

密钥只在局部表单和待确认请求 ref 中短暂保留，关闭、会话变化及卸载时清理；脱敏列表通过既有 Redux 管理，不写浏览器持久存储。账号/角色 ABA 和旧响应不能恢复旧确认。配置无效的端点仍可进入修复，不能作为默认。

当前接口对单任务/月预算均要求大于零，不支持设计草案中的“0 表示不限”。无限预算若要引入，应按后端/schema 合同另行实施与验收；前端不把零转换成不限。本人用量/队列见 [25](25-本人端点用量dev验收.md)，探测后端见 [26](26-受控端点探测后端dev验收.md)，前端报价确认、历史/轮询/取消与有界真实提供商验收见 [27](27-端点探测前端与真实供应商dev验收.md)。超管脱敏元数据/停用见 [28](28-端点运营与停用dev验收.md)，更广的聚合运营视图仍待实施；保存成功不能标成“模型测试通过”。

## 已运行验证

- client/Redux 独立审计保留原失败及四类边界修正，最终 82 项通过；页面与弹窗修正的独立竞态集分别 7/7、8/8 通过。
- 069c5f2 上 13 个前端 suites、165 项通过；c4ef1cc 弹窗修正后另跑 3 suites、56 项通过（22.909 秒），不将早期组合标成最终版本全量复跑。TypeScript 和改动目标 ESLint 通过。包含未知/免费价格、换地址新 key、CAS、超时原请求重试、重复点击、卸载、账号/角色 ABA、旧列表、release 路由移除及双语。
- Chromium + 本地 webpack + mock API，以普通 USER 完成新增、默认、编辑、停用、启用、删除。375px 列表宽 367px、弹窗 359px；1440px 文档宽 1432px。预算输入框最终宽 309px、scrollWidth 309px，金额不裁切。新页面运行时无错误；有既有开发依赖 warning。浏览器 API 仅 mock，不能称真实网关或全浏览器验收。

## 专用免费提供商测试

用户明确“免费但有限量”后，在随机自有 MySQL 库中为专用端点保存 `confirmed=true`、`free_confirmed=true` 和三项零价。原 Task worker 经真实 SDK、ModelProxy 和 HTTPS 完成两个模型各 6 条 AiRun；预留 token、usage 完整、零费用、不扣平台积分、候选采用与 receipt 重放均验证。这次早期检查点的 Java 身份 RPC 和 installed 集合只在 fixture 中替换，当时源码安装集为空。后续不替换身份、安装或模型的实际浏览器/Linux worker 组合见 [24](24-首批组件与真实模型浏览器dev验收.md)。

测试位于 AutoLab `tests/test_agent_workflow_sdk_mysql.py::test_opt_in_free_provider_worker_usage_and_human_adoption`。默认 skip；运行需单独 SDK、已校验的 loopback MySQL 随机库 fixture，以及显式设置：

- `AUTOLAB_AGENT_PROVIDER_TEST_CONFIG`：仓库外绝对路径的 0600 JSON，字段 `base_url` / `api_key`，不打印或提交。
- `AUTOLAB_AGENT_TEST_FREE_CONFIRMED=1`：只适用于已明确免费的专用测试端点。
- `AUTOLAB_AGENT_TEST_MODELS`：恰好两个已授权模型名称的 JSON 数组。
- `AUTOLAB_AGENT_PROVIDER_REPORT_DIR`：已有仓库外绝对路径，仅保存脱敏用量与阶段结果。

每模型只新建一次任务、两个阶段，每阶段最多 8 步、1024 输出 token；不自动重试失败。初次 Qwen 任务失败且原因未定位，初次 DeepSeek 被测试的单位字段误断言挡住采用；旧证据保留。修正测试并加观察 wrapper 后的新任务 2 项通过（85.247 秒），不代表已证明稳定性、真实 Gateway、Linux 或业务组件可以启用。

根会话的 CLI 测量另保存为 `root-observed-metrics.json`，注明转录来源而非独立重跑；375px 新增前后快照、窄屏弹窗截图与后续操作请求记录保留，HMR 后的请求记录不包含此前新增请求。诊断路径/枚举硬化只做离线验证，不重复消耗免费额度。零成本调用记录在 AiRun，原实现不会创建金融扣款 AiLedger 行；不能要求两张表行数相等。

后续真实 Gateway、Java 身份、自有 MySQL/Redis、SDK 与本人端点隔离的定向验收见 [20](20-真实网关身份与端点dev验收.md)。本文中的旧待验收表述是此前检查点，新的范围和仍未覆盖项以 20 为准。
