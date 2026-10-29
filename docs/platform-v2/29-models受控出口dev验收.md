# models 受控出口 dev 验收

2026-10-19，承接 [27](27-端点探测前端与真实供应商dev验收.md)。仅补充显式元数据出口，不增加 HTTP API、前端按钮或组件安装，不改变原 `port.test` 的三次 Responses、报价、预留、结算或历史投影。原 UI 的 `model_list_supported` 仍为 unknown；本页不是其端到端交付。

## 合同

AutoLab `port_transport.probe_models` 经原 worker-owned 子进程协议执行一次 GET：端点基路径后追加固定 `/models`。不提供任意 method/route、分页、跟随 next URL、重试或 Responses 回落。旧 POST 协议保持原四字段；新协议只接受 base_url/api_key/operation=models/timeout_seconds，不能混入 body 或 route。

沿用 HTTPS 公网全部 DNS 结果检查、数字 IP 绑定、原主机 TLS/SNI 验证和 Host、禁止代理/redirect/retry、环境白名单和私有 stdin。元数据响应上限 262144 字节，拒绝压缩；父总期限、租约/取消检查和子进程内核定时器继续生效。真实 key 不进入 argv、环境或公开结果。

模型目录只检查 data 数组：最多 1000 个条目，ID 为不重复、无首尾空白/控制字符、最长 512 字符的非空字符串；空目录允许。提供商原字段和模型 ID 不进入 IPC 成功结果。返回闭合投影：

| 情况 | reachable | model_list_supported | model_count |
| --- | --- | --- | --- |
| 合法目录 | supported | supported | 0–1000 整数 |
| HTTP 404/405/501 | supported | not_observed | null |
| 其他非 200（含重定向、鉴权、限频及服务错误） | supported | unknown | null |
| JSON 对象内目录形状不合规 | supported | unknown | null |
| DNS/网络/解析/大小/压缩等不能完成有效结果 | unknown | unknown | null |

这里的 reachable 仅为本次出口观察，不是鉴权成功、长期可用或 Responses/工具/结构化输出能力。`/models` 404 不能关掉原 Responses；200 也不能授权工具执行。父侧再次验证闭合 DTO、状态组合与整数范围，拒绝额外 provider 字段。

## 验证记录

提交 `319e42c`：egress、transport、models 和原 probe 定向组合 101 项通过，5.19 秒，退出 0。覆盖固定 GET/IP/TLS/禁止代理与重试、404/鉴权/限频、超大/压缩/畸形目录、混合私网 DNS、禁止任意路由/额外协议字段、真实子进程拒绝 loopback、私有 stdin、返回前撤权和异常 DTO；原三次 Responses 回归保留。

独立 exact archive 审计 accepted，无阻塞：同四套 101 项通过，5.34 秒；另 5 项 metadata 专属边界通过，3.39 秒，验证 262144/262145 字节、真实 stalled child 的父期限/取消，以及无父 watchdog 时子进程自身 SIGALRM。附加探针只使用合成网络和实际子进程，未读真实凭据或调用提供商。

最终 clean `319e42c` 完整 `pytest tests`：**1106 通过、24 跳过、800 条 warning，92.54 秒，父进程实际退出 0**。真实 SDK 解释器和随机自有 MySQL 已启用；live-provider、Gateway、容器及固定库等显式 opt-in 仍保留跳过，不把离线/合成测试扩称为这些环境通过。本轮不改前端，未重复前端全量或浏览器验收。

用户已明确专用测试端点为免费、限量但额度较充足的试用。对该端点在此提交运行一次显式元数据 helper：0.146 秒，transport_completed=true，目录 supported，21 个模型；0 推理请求、无 SDK/Task worker、无 TaskJob/AiRun 写入或模拟结算。没有输出模型 ID、provider 原响应或凭据。只证明该 helper 到真实 HTTPS 的观察，不代表原 Gateway/登录/属主任务/浏览器链已接入。外部 launcher 首次因缺少导入所需的隔离 env 而在读凭据前退出，补齐 fake env 后才执行上述请求；不是产品问题，不记作供应商失败或第二次请求。

## 后续与证据

本页提交时尚需接入本人端点任务/前端；随后完成的独立诊断、限频、冻结、取消/历史和真实 worker 浏览器链见 [30](30-models任务与前端dev验收.md)，不改写本页 helper 的验收范围。不得把它偷偷加为现有三请求任务的第四次请求。元数据 GET 不产生模型 token usage，不能伪造 AiRun 为零用量来冒充模型计费验收。若后续供应商将元数据本身计费，应先明确准入和费用合同。

仓库外 WORK 保存 `port-models-targeted.log`、`port-models-full-sdk-mysql.log`、`port-models-live-result.json`、`run_port_models_live.py`、`audit-port-models-transport.md/json`、额外边界日志及监控记录；该目录也含私有配置，禁止 glob 读取 JSON。没有 push、生产、Java、schema、角色、镜像、CI、seccomp 或根 submodule pin 变更；原 48 项任务状态不变，S2-03 仍 partial/in_progress。
