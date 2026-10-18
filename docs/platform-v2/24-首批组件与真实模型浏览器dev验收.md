# 首批组件与真实模型浏览器 dev 验收

2026-10-19。AutoLab `786c8ea` / `956fd23`，web2 保持 `3615267`。承接 [23](23-Linux完整worker与取消锁序dev验收.md)，本次在同一个任务内实际组合浏览器、原 Gateway/Java 身份、自有 MySQL/Redis、Linux worker、OpenHands SDK 和用户授权的免费测试模型。仅 dev，本地提交，不 push、不写生产，不修改 Java、schema、镜像或发布链。

## 首批源码登记

`786c8ea` 将两项已实现适配登记到源码目录，治理安装集直接从目录派生：

| 组件 | 本次已登记范围 | 启用方式 |
| --- | --- | --- |
| `content.review` | 普通 `document` 输入审核，内部依赖，无独立业务创建入口 | 原 superadmin 的组件/action CAS 管理接口 |
| `document.translate` | 普通纯文本文档，中文/英文，审核后生成独立候选译文 | 同上，须同时满足全局、依赖和 action 开关 |

源码默认策略仍全部关闭；本次只在随机自有测试库通过原 M 管理 API 显式启用。其他 12 组件继续未安装。题目、authoring、collection 和原生文档等来源不能借这个登记获得翻译能力；OCR、扫描 PDF、题目翻译等仍未实现。`agent-components.yaml` 保留设计范围，不能代替运行时源码目录或验收证据。

目录变更会改变 catalog revision。旧排队任务、运行绑定或候选不能通过改写快照恢复，应在核对当前原文和权限后重新准入；组件关闭再开启也不恢复旧代次。

独立 exact-archive 审计：220 项通过；另 6 项无安装状态替换的反例通过，覆盖默认全关、内部审核不能直接启动、未适配来源拒绝和旧目录快照失效。未为该审计调用真实模型。

## 同一任务的实际链路

`956fd23` 新增显式 harness，默认测试发现不收集它；运行需额外的免费授权标记、仓库外 0600 提供商配置、新建私有控制目录和既有 Linux 双解释器目录。真实密钥通过原端点 API 加密保存，不进入 Docker 参数、模型子进程或浏览器本地存储。

实际浏览器以专用 dev 账号经原 `/user/login` 建立会话，使用 web2 原 webpack 代理到 Gateway。端点未设默认，因此新建按钮起初禁用；在页面显式选择本人端点后，只创建一个普通文档任务。端点预置使用原 API，不把本次测试冒称浏览器输入密钥或完整端点 CRUD 验收。

Linux arm64 原 `worker.run()`、Python 3.9.23 和独立 Python 3.13 SDK 沿用 23 的环境及只读挂载；Web 仍运行在 macOS。没有安装集、API、身份或模型响应替身。观察器原样调用 fresh Java RPC 和原 HTTPS transport；每次外呼先固定核对唯一免费目标的 URL、模型和密钥指纹，整个 worker 最多允许 16 次实际请求，首次任务失败/自动重试会使验收失败。

这次模型为 `Ali-dashscope/Qwen3.8-Flash`，协议 Responses。仅发送合成句子 `A queue processes items in first-in, first-out order.`，不发送真实用户资料或生产数据。审核和翻译共 6 次真实请求，形成 6 条成功 AiRun：

- 一个任务成功，attempt=1；worker 统计 6 次调用、6 次完成及 169 次原 fresh 身份检查。
- 每次输入/输出预留为正，供应商 usage 完整；本专用端点明确确认三项零费率，成本为零，未产生平台积分扣款。
- 浏览器显示候选“队列按先进先出（FIFO）的顺序处理各个元素。”；对照原文后勾选人工确认、填写说明并保存。
- 实际 MySQL 核对文档版本从 1 到 2、原文保持、独立译文非空。模型完成本身不直接修改原文档。
- 原 worker 正常 SIGTERM 退出 0、容器 RestartCount=0、Redis 订阅回到基线；本次随机容器与临时配置清理，5005 释放。

主验收 1 项通过，216.28 秒，父进程退出 0。随后同一提交的原 Linux 运行中取消/对账/继续任务链另 1 项通过，18.63 秒；这项使用合成提供商，不把它说成真实模型取消。

## 回归、审计与保留记录

当前代码树完整 `pytest tests` 使用随机自有 MySQL 和宿主实际 SDK：996 通过、22 跳过、0 失败，90.20 秒，父进程退出 0。显式浏览器组合和 Linux worker 在上述定向验收中另行运行。全量中的真实模型、容器、固定锁/专用 schema 等跳过仍保留，不以新定向链替代其覆盖。

`956fd23` exact-archive 独立审计 40 项离线检查通过：原环境拒绝、逐次目标约束、并发请求上限、失败请求计数、showlocals 在私有配置读取前拒绝、配置权限/别名、真实/合成 factory 的挂载和异常清理。审计者复核了主验收结果，没有声称独立重复浏览器或模型调用。

首轮 preflight 尚未创建任务时，预审指出仅在启动检查免费端点不足以限制后续测试误选另一端点。主动停止首轮，保留 1 项失败、187.41 秒的无任务结束记录；增加逐次 URL/model/key 指纹检查后，使用新的控制目录及日志运行最终验收。该首轮没有任务或模型调用，不将其记成产品故障，也不删除失败记录。

本机仓库外 `platform-v2-implementation-20261018` 保存 `gateway-real-provider-browser{,-final}.log`、`provider-browser-final-20261019/result.json`、`shipped-adapters-full-sdk-mysql.log`、`gateway-linux-worker-shipped-regression.log`、`audit-shipped-document-adapters.*`、`audit-real-provider-browser-harness.*` 和独立监控记录。前端 webpack 首编译 15.192 秒，无 TypeScript 错误，有 2 项体积 warning。实际交互期间页面无新运行错误；清理后能力刷新失败会关闭新建控制，不能把清理后的截图当仍在运行的服务。

15 份本轮日志、控制 JSON 和 CLI 记录按真实测试密钥、dev 密码、RPC token、MySQL/Redis 密码扫描，0 命中；临时浏览器 storage state 已删除。截图保存在 web2 的忽略输出目录，CLI 记录移至仓库外。

## 仍需完成

这是一条普通文档的 dev 定向链，不是完整 platform v2 发布验收。继续端点能力探测与脱敏运营视图、其他 12 组件迁移、其余页面能力接入、原生题目 MySQL 锁矩阵、Linux amd64、完整 Linux Web 及原发布流程最终制品。此前 DeepSeek 的独立后端测试见 [13](13-本人端点dev验收.md)，本轮未重复该模型的浏览器链。原 48 项任务不因本页验收而批量改 done。
