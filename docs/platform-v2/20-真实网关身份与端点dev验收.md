# 真实网关、身份与端点 dev 验收

2026-10-19，承接 [19](19-旧候选采用与发布dev验收.md)。本轮使用现有本机开发 Gateway/Java 服务和任务自有 MySQL/Redis，不改生产、不 push、不发布组件。没有真实模型调用。

## 提交与真实路径

| AutoLab 提交 | 验证 |
| --- | --- |
| f5637bf | 临时运行当前 main 应用，经原 `/api/ps/auto-task/ai` Gateway 路由登录、端点创建/查询/默认/停用/启用/删除、操作回执和加密检查；匿名伪造身份头拒绝；原 Java 内部 RPC 缺 token 被拒绝；HTTP 确定性任务入队后收到真实 Redis wake 消息，再由 run_once 完成并从 MySQL 回读 |
| 6fd9a96 | 实际 HTTP 配置策略、创建文档及本人端点、typed 文档准入，worker 调用 SDK 子进程、ModelProxy/AiRun 结算、候选读取、人工采用与精确回执重放；领取前取消后显式新准入，再次执行与采用 |
| 297ee15 | 原 Java addUsers 创建随机专用普通 USER，原登录、fresh RPC 确认角色；本人端点换钥更新、陈旧 CAS/换地址缺 key 拒绝、AI 账号暂停仍可修复；超管无法操作另一人的端点；删除后旧创建回执不复活记录。最后原 logout/delete 清理仅本次新建账号 |

Gateway、Java 身份 RPC、MySQL、Redis 与 SDK 进程均实际执行。SDK 用例中的身份观察 wrapper 原样调用 fetch_actor，检查调用均 fresh=True，不返回合成身份。main 应用没有 authentication dependency override。普通 USER 由原管理 API 固定赋予 USER，没有直接改 Java 角色、SQL 或 session。

新文档用例仅在测试内投影 document.translate/content.review 两个安装状态，策略更新仍经过原 superadmin HTTP/CAS/receipt。发行源码的 INSTALLED_COMPONENTS 仍为空，不以此验收启用组件。模型端由 synthetic Responses 函数替换，检查后续模型请求实际收到读取文本及审核/候选回执，共两次成功任务、12 次合成调用。AiRun 用显式合成零费率记录完整 usage；未调用专用免费端点，也未证明供应商实际收费。

## 结果与初始失败

- f5637bf 主测两项通过、2.30 秒；独立 exact archive 两项通过、2.35 秒，accepted。初始一次为 1 PASS/1 ERROR：临时服务退出后的 TCP TIME_WAIT 导致重新绑定失败，以 SO_REUSEADDR 修复，不使用 SO_REUSEPORT，不停止或替换占用端口的进程。
- 6fd9a96 主测一项通过、15.47 秒；独立 exact archive 一项通过、15.53 秒，accepted。早期 fixture 未显式导入依赖，以及候选 GET 的 data 嵌套层断言错误日志保留；未改产品来迁就测试。
- 297ee15 主测一项通过、2.03 秒；独立 exact archive 一项通过、1.71 秒，accepted。随机账号创建成功后才进入清理区，删除参数仅引用本次新建用户名，现有账号不会列入清理。

证据在当前任务 work/platform-v2-implementation-20261018：real-gateway-ports-initial.log、real-gateway-ports-fixed.log、real-gateway-sdk-initial/fixed1/fixed2.log、real-gateway-user-port-initial.log，以及 audit-real-gateway-baseline、audit-real-gateway-sdk、audit-real-gateway-user-ports 的 md/json/log。baseline 独立 loader 首次日志路径替换遗漏，覆盖了旧成功日志，已将该次 exact 输出保存独立 audit log，并在报告中记录；原 TIME_WAIT 失败日志未覆盖，不将覆盖后的文件冒称原主测。

19 的 977 PASS/16 SKIP 是 e40a78c 的全量检查点；本轮新增定向用例的结果单独列出，不相加为后续完整代码树全量复跑。

## 复验约束

AutoLab 测试为 test_platform_v2_gateway_dev.py、test_platform_v2_gateway_sdk_dev.py、test_platform_v2_gateway_ports_dev.py。默认 skip；设置 AUTOLAB_PV2_GATEWAY_TEST=1、AUTOLAB_PV2_GATEWAY_TEST_CONFIG、AUTOLAB_PORT_TEST_CONFIG，SDK 用例还需 AUTOLAB_OPENHANDS_TEST_PYTHON。

Gateway 配置是仓库外绝对路径的本人 0600 JSON，包含固定本机 gateway_url 与仓库外 credentials_file；凭据文件也需 0600，现有专用账号须 ai_dev_ 前缀。密钥/Cookie/请求正文不进入诊断。各服务环境变量必须在 Python 导入前由仓库外 loader 装入；不得打印 env 或凭据文件。

测试固定 Gateway 为 loopback 的原开发端口，身份为本机 Java 服务，Redis 为任务自有实例。MySQL fixture 只创建、最终删除随机自有测试库，不复用现有业务库。schema 是当前模型的新库初始化，不是迁移或备份恢复演练。临时 main 监听原开发端口；若已有 listener 则失败，绝不 kill 其他服务。5005 测试必须串行；每项与审计均确认退出后释放。

## 尚未覆盖

worker 仍是当前 pytest 进程调用 run_once，SDK 是独立子进程；不代表长期独立 worker 部署、Linux worker、并发浏览器、WebSocket 或原正式提交全链。本轮 Redis wake delivery 在确定性任务用例中断言，SDK 用例未单独断言其配送。真实供应商与真实 Java 身份的组合、Linux 安装、浏览器/前端真 API 和运行中取消/恢复仍需后续验收。

手工题库、正式提交、Run、云保存继续原流程；本轮没有改其产品实现。原 48 项任务不改 done，14 个业务组件的其余迁移和 platform-v2 其余阶段仍未完成。
