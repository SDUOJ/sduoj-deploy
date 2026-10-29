# 端点探测前端与真实供应商 dev 验收

2026-10-19。承接 [26](26-受控端点探测后端dev验收.md)，AutoLab 最终检查点 `a4bba95`，web2 `2b1a365`。仅 dev、本地小提交；未 push、未改生产或原 Java、schema、角色、镜像与发布链。用户提供的专用 API 免费但有限量，只有该测试端点明确确认三项零价；不据此推断其他端点免费。

## 使用与接口

在 dev `/v2/account/assistant/ports` 选择“探测与结果”。打开只读本人最近任务；停用、价格未知的端点仍可查历史。新探测要求 active、有 key 和明确费率，随后依次获取报价、勾选同意、确认启动。读取报价、刷新结果、关闭重开均不调用模型。

确认冻结端点版本、价格版本、原小数字符串费用上限及 operation_key。最多三次请求，每次预留输入 4096、输出 128 token；正文另受 4096 字节限制。结果未确认时只能显式重试原请求，不生成新 operation。POST 已确认而状态 GET 失败时只重读状态；关闭不会取消已入队任务。取消走原 TaskJob API，已发送请求的结算见“查看用量”。

新增 `GET /ports/{id}/test/latest`（原 `/auto-task/ai` 前缀），在动态 taskId 路由前注册。只查本人、同付款主体/端点/type/harness 的最近任务，返回空值或原状态投影；不创建账号、不加行锁、不解密凭据或访问提供商。状态增加冻结的 `port_version`，历史版本与当前配置不符时明确提示，不能当成当前配置的能力结论。

前端原 Redux 按主体、权限代次、端点版本和请求 ID 隔离数据。端点列表刷新、失败、会话变化清理旧结果；仅同一版本的后台轮询保留当前展示，避免两秒一次卸载任务/取消控件。状态读取失败后不保留旧结果。模型输出、原错误文本和 key 不进入状态或页面。

## 真实 dev 浏览器验收

显式 fixture 为 `tests/platform_v2_probe_browser_harness.py`；未 opt-in 默认跳过。私有控制目录和免费提供商配置均在 Git 外，禁止 showlocals。提供商目标限定用户授权的域与两个模型之一，原 dev Gateway、Java 登录/fresh RPC、自有随机 MySQL、Redis、原独立 worker 与 HTTPS transport 均未替换。此固定协议诊断不使用 SDK，不能冒充 OpenHands 业务 Agent 验收；业务 SDK 链另见 [24](24-首批组件与真实模型浏览器dev验收.md)。

Chromium 在 web2 `355db55`、AutoLab `a4bba95` 上完成：

1. 本地报价与勾选，首次创建排队任务；worker 尚未启动。通过页面取消，任务 attempt=0、模型请求=0。
2. 再次明确确认，创建第二个任务后启动原 worker 进程。经原出口发三次真实 Responses，任务 attempt=1、成功结束，三条 AiRun 完整结算、BYOK 零费用、无 AiLedger 扣分。
3. 页面轮询显示结果，关闭重开仍读同一历史任务，不产生新请求。“查看用量”显示输入 671（缓存 0）、输出 333、在途 0、待对账 0。
4. 375px 下弹窗 clientWidth/scrollWidth 均 359，正文均 311；纵向可滚动，底部操作可见，无横向溢出。浏览器本页无运行时错误，有既有开发 warning。

这次 Qwen3.8-Flash 的有限观察为：

| 项目 | 结果 |
| --- | --- |
| Responses 固定回复 | supported |
| auto 工具调用格式 | not_observed |
| JSON schema 输出 | unknown |
| 模型列表 | unknown（未请求 `/models`） |

128 输出上限下的 not_observed/unknown 不等于模型普遍不支持该能力，不据此放开/关闭其他业务组件。本次未追加提高上限或重复请求。真实 fixture 最终 **1 项通过、487.41 秒、父进程退出 0**；包含人工 CLI 操作等待。观察器确认发送/收到响应各 3 次、fresh 身份调用 31 次、worker 退出 0。该浏览器检查点之后的 `9754334`、`2b1a365` 只做下述隔离回归，未再次调用真实模型。

## 审计发现与修复

- `724a669` 最近历史接口：独立 exact archive 85 项通过，另 3 项验证只读 SELECT、literal 路由优先、同时间排序、他人/已删除端点拒绝及历史冻结版本。
- `36e6f21` typed client/Redux：独立 43 项通过，另 8 项生命周期/精度边界通过；公开投影不透出额外字段。
- `bb010e6` UI 初稿相关 46 项通过，但独立追加反例失败：POST 结束时若列表正在刷新，busy 可能不释放。`355db55` 分离同会话的局部清理与严格当前端点校验；独立 16 项通过（含原失败反例），tsc/ESLint 通过。原 needs_fix 保留。
- `8b65db9` 真实 fixture 初稿未执行供应商调用即被独立审计拒绝：持续 worker 可在轮询发现多余任务前发送额外请求；强杀父进程也可能留下独立 session 的 egress 子进程。`a4bba95` 在真实 transport 前绑定 task/owner/地址/模型/key 摘要并限制累计最多 3 次；强杀兜底处理自建子组，日志同时扫描真实 API key。独立 12 项通过、1 项默认跳过，原两个离线反例修复后 2 项通过。原始失败证据保留。
- `355db55` 前端全量为 1285 通过、1 失败（175 suites、343.548 秒、退出 1）。独立诊断确认旧端点写入测试抛超时时，请求已发生、重试按钮实际存在且可用；默认 1 秒 role 查询阻塞了异步呈现。`9754334` 只调整测试为先等请求发生及错误提示，再获取重试按钮，不延长超时或减断言，独立定向 1 项通过（其余 16 项未选）。根修订时曾误用不存在的提示正则，失败日志保留；改为实际提示后，与新 UI/Redux 联合 41 项通过。
- `2b1a365` 修复后台轮询卸载控件：独立 UI/Redux 24 项通过、tsc/ESLint 通过；同一新反例在旧 `355db55` 上失败，修复后同一 DOM 控件持续存在，状态读取失败即清除，跨会话/版本不能保留；不改变确认或调用合同。

较早 `bb010e6` 全量因已确认竞态而终止（退出 143），不记通过。最终 clean AutoLab `a4bba95` 完整 `pytest tests` 为 **1051 通过、23 跳过、0 失败，90.19 秒、父进程退出 0**；启用真实 SDK 解释器和随机自有 MySQL，模型/RPC 定向为替身，Gateway/live-provider 专用用例不在全量中冒充执行。真实浏览器/提供商单列于上节。最终 clean web2 `2b1a365` 全量 Jest 为 **175 suites / 1288 项全部通过，320.29 秒、父进程退出 0**。未将较早失败或手动中止的记录覆写成通过。

## 证据与剩余范围

本机仓库外 `platform-v2-implementation-20261018` 的明确文件包括 `gateway-probe-browser.log`、`probe-browser-20261019/{progress,result}.json`、`probe-browser-{result,reopen,usage}-snapshot.txt`、两张 `probe-real-mobile*.png`、`audit-port-probe-{latest,client,ui,ui-refresh-fix,browser-harness,browser-guard,legacy-retry}.*` 与对应回归日志。不得用 JSON glob 读取证据，目录内另有私有凭据；临时浏览器认证文件已删除，browser、worker、5005/3016 已退出，原 dev 容器未调整。

明确命名的 20 份文本证据及另 12 份日志/文档扫描测试 API key、dev 密码、内部 RPC token 和本地数据库/Redis 密码，均 0 命中；不包含工具输出、图片或扫描之后的日志追加。最终两份全量日志另在结束后复查。

这里只完成受控固定 Responses 探测链。`/models` 受控发现、脱敏运营视图、其他实际端点/模型矩阵、Linux amd64/最终制品及其余 12 个业务组件仍待实现/验收，原 48 项任务继续按实际依赖推进，不整体标 done。
