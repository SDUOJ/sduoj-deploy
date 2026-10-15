# SDUOJ AI 教辅平台共享进度与实现说明

> 唯一正文：sduoj-deploy/docs/AI_PLATFORM_PROGRESS.md。前端、后端、运维共同维护此文件；其他位置只放入口。
>
> 基线日期：2026-09-05；后端 P0 续推、前后端并行收口与本轮能力复核日期：2026-09-06。本轮修改了 Autolab 后端、Web2 AI 工作台和共享文档；未修改生产环境。前端既有修缮任务继续独立进行，新增页面不改其既有组件和依赖。

## 2026-09-13 智能管理与 M 端统一（最新调整）

“程序题命题”已替换为 M 端“智能管理”，直接对接 Codex App Server，以预设说明/步骤驱动按用户隔离的持久会话；所有 Agent OJ 读写操作均需逐项审阅确认，使用确认者当前登录会话。查重、批阅、考务统一记录表格与弹窗新建，IDE 产品入口及编辑运行界面已移除。详见 [智能管理实现与验证](INTELLIGENT_MANAGEMENT.md)。当前请求契约为 145 条；真实模型未配置，生产和账务集成边界以该文档为准。

## 2026-09-13 产品入口与题库调整（优先于下文历史描述）

根据实际体验反馈，取消独立 AI 导航和题库页面，功能进入现有 CLayout/MLayout：M 端题组管理提供批量录题和题目解答，编程题页提供辅助命题，题单任务/评阅提供运行、批阅和查重，课程页提供资料与问答；C 端编程题详情提供代码练习，课程和实践页面承载问答与验收。旧 `/ai-*` 地址只作兼容跳转。工具使用现有 AntD 侧栏、表格和抽屉。

客观/主观题以原有 `ProblemObjective` / `ProblemSubjective` / `ProblemGroup` 为唯一权威数据。手工批量录入直接保存原表；文件识别成功后同一事务保存原表并按批次建题组。由于原题组为单一题型，混合批次分别建立客观题组、主观题组。没有额外“录入 OJ”步骤。AI 资源仅保留任务引用、历史快照和分析；解答写回同一原生题目，原生编辑可读回，过期任务不得覆盖新内容。普通批量录入不依赖模型配置或 AI 账户状态。

本轮验证：后端 266 passed / 12 skipped；相关前端 18 suites / 52 tests passed；两套 TypeScript 检查通过；lint 0 errors（143 条既有 warning）；生产构建通过（3 条 lint / bundle 大小 warning）。真实浏览器保存批次 `DEV-原生题组体验-20260913` 得到主观组 #201、客观组 #202，原有列表、原有编辑器及题目与解答均读回成功。当前 Web2 请求契约为 142 条。实际模型仍未配置，OCR/解答/问答等不能宣称完成真实模型验收。环境恢复及此前历史见 [当日记录](DEV_SESSION_20260913.md)。

## 阅读导航

1. [当前结论与状态口径](#1-当前结论与状态口径)
2. [范围、架构及历史方案处理](#2-范围架构及历史方案处理)
3. [能力总表](#3-能力总表)
4. [各模块实现与差距](#4-各模块实现与差距)
5. [前后端共享契约与接入清单](#5-前后端共享契约与接入清单)
6. [未完成工作及优先级](#6-未完成工作及优先级)
7. [验证证据与环境状态](#7-验证证据与环境状态)
8. [里程碑与完成标准](#8-里程碑与完成标准)
9. [维护规则与变更记录](#9-维护规则与变更记录)
10. [源码与文档索引](#10-源码与文档索引)

## 1. 当前结论与状态口径

当前处于“Autolab 后端已补强多条能力，原生 OJ 三类题目在本机 dev 双向对接，Web2 AI 工作台已覆盖主要管理与教学入口但仅局部验收，生产替换尚未验收”阶段。2026-09-06 续推了可在本机关闭的后端 P0：身份/Gateway fail-closed、Worker 首尾再授权、墓碑语义及文件/数据库孤儿补偿；随后并行补齐任务监控、命题、批阅、考务、课程、查重、验收和管理页面。测试映射与复现流程见 [开发验收流程](../../sduoj-autolab/docs/AI_BACKEND_DEV_ACCEPTANCE.md)。

已经做成的核心工作，是把任务执行、数据存储与身份边界放进现有 Autolab：FastAPI + SQLAlchemy + MySQL + Redis，保留原任务接口，新增 AI 业务 API。它不是只有接口名称的规划，但也不能表述成“原 Problem Stack 的所有功能已经完整、等价地迁完”。

特别需要区分：

- 91 条 AI API 路径存在，不等于 91 条产品流程完成；机器契约已通过脚本从当前路由生成。
- 模型夹具不等于真实模型验收；本轮另行通过本机 MySQL、四语言容器、JPlag 和 dev OJ 真实判题测试。
- 原 Problem Stack 在 .223 上的历史 E2E，不等于新 Autolab 在 .79 上通过。
- Web2 当前请求契约包含 141 条路径，其中 62 条为 `/auto-task/ai`；并新增 9 个 AI 工作台入口（含 1 个验收会话详情路由，共 10 条路由记录）。页面、按钮和数据闭环仍需按能力分别验收，不能由路由存在推导完成。
- 已有不可变任务输入和追加式资源修订记录，但没有迁移前历史回填、跨 Java exactly-once 或生产高可用证据。
- 本机开发库已建表，不等于生产已迁移；当前也未配置本机新提供者的模型/API key。

本文件的状态词含义：

| 状态 | 含义 |
| --- | --- |
| 已实现，局部验证 | 当前代码有真实逻辑，并有相应自动测试或本机检查；不代表整条产品链已验收 |
| 部分实现 | 有实现基础，但缺少原需求中的关键环节、字段、边界或交互 |
| 契约准备 | 只有 schema、校验或说明，尚无业务调用/页面证据 |
| 未完成/未验收 | 无实现证据，或尚未完成所需运行验证 |
| 已调整归属 | 功能由原 OJ/Autolab 承担，取消独立题栈副本；仍需验证跳转/调用和数据闭环 |

不提供没有业务权重依据的“总完成百分比”。项目进度以能力闭环和里程碑验收为准。

### 1.1 当前环境快照

| 项目 | 本轮事实 |
| --- | --- |
| 新后端源码 | 在 sduoj-autolab 实际工作树，含未提交/未跟踪变更；HEAD 参考 da27fc8，不能用它代表新实现 |
| Web2 | 当前工作树 React 18.3.1、Ant Design 5.29.3、React Router 5；HEAD 检查时为 c1fc0df，仍在修缮；AI 工作区路由测试覆盖 10 条 |
| 共享维护仓库 | sduoj-deploy，HEAD 参考 ffb3e45；其现有本地部署变更仍在工作树 |
| 本机后端 | 127.0.0.1:5005；当前机器契约有 91 条 `/auto-task/ai` 路径 |
| 本机数据库 | debug / 127.0.0.1:7360，累计 13 张 AI 扩展表；含任务输入/修订及原生查重快照/提交表 |
| 本机 dev 管理账号 | 已用本地 OJ 的 `superadmin` 会话验证 AI 能力、账户、资源、队列和设置接口；凭证不写入文档 |
| 新模型配置 | runtime 版本 1；has_key=0，provider/model 未设置。没有读取或输出密钥 |
| 本机 Worker | 未检出 python -m auto_task.worker 命令进程；未取得持续消费证据，不据此排除所有可能的外部托管方式 |
| 生产 | 本轮未重新检查或变更；不能依据本机情况宣布 .79 已更新 |

因此，当前可以从 Web2 进入主要 AI 工作台并完成部分开发流程，但不能宣称全部 AI 教学流程已闭环。真实提供者、生产执行环境、角色矩阵和端到端验收仍有工作。

## 2. 范围、架构及历史方案处理

### 2.1 最终目标

全面使用 Web2 前端和 Autolab 后端，AI 能力扩展现有异步 task 线，避免独立题栈应用的前后端、数据库和用户体系。

- 账号、登录、全局身份/角色继续由 OJ 管理。
- 课程、题单、主观/客观题、答题卡、最终成绩使用原 Autolab 模型。
- 编程题、正式评测使用原 Java problem/submission 服务。
- AI 使用资格、任务、候选结果、模型运行、费用和工作文件由 Autolab 的 AI 扩展保存。
- AI 停用只作用于 AI/task 功能，不停用 OJ 账号，也不阻断原交卷和人工批阅。
- Web2 不新增第二个 React 应用；本轮已在现有题目、题单、课程、批阅和任务管理入口增加 AI 工作区跳转及上下文参数。完整原生页面替换、角色回归和生产发布仍需统一排期。
- Java 后端暂不纳入新发布体系；生产配置和发布仍由用户人工执行。

### 2.2 当前代码路径

~~~text
Web2 现有页面 / 后续 AI 交互
  -> /api/ps/auto-task/... 或 /api/ps/auto-task/ai/...
  -> SDUOJ Gateway（OJ session，清理/注入身份 header）
  -> Autolab FastAPI
       -> 原 MySQL 业务表
       -> auto_task_* 扩展表
       -> Redis 唤醒通知
       -> 独立 Autolab Worker
            -> Codex CLI / 兼容 HTTP 提供者
            -> 隔离运行器接口（Docker-compatible）
            -> 本地持久文件与 workspace
~~~

用户请求、任务执行和副作用提交是不同阶段。Web 主要做授权、参数检查和入队；模型和程序运行在独立 Worker。原 Nacos /api/ps/** 路由已覆盖这些地址，目标架构无需为新 AI 能力再增加独立题栈服务名。

### 2.3 已废弃或需重新解释的旧规划

| 旧规划 | 当前处理 |
| --- | --- |
| 独立 Next.js 题栈前端和 /problem-stack 页面服务 | 不作为当前目标；浏览器统一 Web2 |
| 独立题栈 Node API/PostgreSQL 迁至 .79 | 改为功能合入 Autolab/MySQL，不直接复制 PostgreSQL 数据卷 |
| 本地 User、密码登录、第二套 session | 不迁入新系统；外部 OJ 身份 + AI 使用资格 |
| Autolab 与题栈之间 HMAC 回调写自己的成绩 | 同一 MySQL 内的候选与采用可用事务，不再需要这条自我回调；未来跨 Java/外部系统操作仍需幂等和可靠投递 |
| “前端 React 17”作为迁移前提 | 已过时；本轮看到 Web2 工作树已是 React 18.3.1，升级是否全量验收由前端任务记录 |
| Codex 必须通过 MCP 主动工具写业务结果 | 当前实现改为结构化输出、Pydantic 校验和服务端提交；自主工具/文件工作流并未等价迁回，见 AI-03 |
| 独立考试账号、密码条和考务主数据副本 | 归回 OJ/Autolab；具体提供和交付流程仍需接通，不能仅因归属明确就算功能完成 |

## 3. 能力总表

下表均指“新 Autolab 实现”。Web2 已新增任务、题库、命题、批阅、考务、课程、查重、验收和管理入口，并分别登记实现与验证边界；生产统一未验收。测试通过不关闭缺少完整产品流程的能力。

| ID | 能力 | 后端状态 | Web2 状态 | 主要剩余工作 |
| --- | --- | --- | --- | --- |
| AI-01 | 持久队列、恢复、并发 | 已实现并通过本机 MySQL/进程强退验证 | 任务列表、费用、SSE/取消/重试；真实 dev Gateway SSE 通过 | 生产多机故障与负载演练、外部副作用核对 |
| AI-02 | OJ 身份、资源授权 | 已实现，局部验证 | 10 条 AI 路由经 `AIRouteBoundary` 预检 OJ/AI 资格；`/v2/ai-admin` 提供本人状态、管理员资格管理与操作历史；后端仍是最终授权点 | 可信入口、撤权时效、后台执行权限、完整角色矩阵 |
| AI-03 | 模型、Codex workspace | 部分实现，局部验证（分用途模型与费率） | `/v2/ai-admin` 支持 provider、模型、费率、health，key 不回显；无 Codex workspace/tooling 管理 UI | dev 配置、真实 CLI/模型、工具能力决策 |
| AI-04 | 费用和积分 | 调用意图、额度预留、月度个人/课程预算、未知用量及幂等对账 | 管理页已支持预算/分模型费率、账本/对账；组件与页面加载验证 | 真实供应商账单；CLI/视觉计费预留不是供应商硬预算 |
| AI-05 | 内容审核和 AI 停用 | 部分实现，局部验证（责任归属审计） | `/v2/ai-admin` 支持复核、资格暂停/恢复与历史；无完整申诉/批量审核 UI | 真实模型准确率、完整审核历史与申诉流程 |
| AI-06 | 文字/照片/文档录题 | 部分实现（PPTX/图形基础补齐） | `/v2/ai-bank` 接通文字/文件录题、预览/编辑；E2E 为模拟文字录入和原生导入，未验收 OCR/手机拍照 | 精度评测、自动后续流程与手机拍照交互 |
| AI-07 | 去重、检索、标签 | 作用域检索、精确/近似去重、重复项拆分/重连、标签别名 | 题库和标签治理已实现；组件/模拟流程及页面加载验证 | 大库检索召回与误合并质量评测 |
| AI-08 | 解题、验证、追问、纠错 | 部分实现，局部验证（版本化追问/恢复） | `/v2/ai-bank` 支持解答、验证、追问、编辑、历史恢复和失败重试；专项测试未覆盖真实模型 | 真实模型验算、质量基准与已发布题同步 |
| AI-09 | 题集/多人协作录题 | 稳定题号、批次幂等、邀请接受、角色、分工、撤权阻断任务链 | 已接成员管理、分工/批次、拆分恢复；组件验证 | 多用户真实并发/大题集验收 |
| AI-10 | AI 命题和程序包 | 部分实现，局部验证（迭代、generator/validator、checkpoint） | `/v2/ai-authoring` 支持生成、终态、版本冲突、复核、bundle 和原生发布恢复；无真实模型/浏览器 E2E | 真实模型质量、大测试集上传体验与 Java 跨库恢复 |
| AI-11 | 原生三类题库对接 | 三类题导入/发布；命题包原生测试点映射/校验 | 题库/命题页均已接；原生导入有真实浏览器验证 | Java 创建响应未知时仍需核对恢复，旧题更新策略 |
| AI-12 | 考试、名单、座位与考务 | 原生 TEST 证书/FORMAL 门禁、课程座位绑定/恢复、监控/CSV | 已实现；4 项组件测试及真实 dev 页面加载/布局通过 | 真实考场全流程、生产回滚与监考业务验收 |
| AI-13 | 视觉批阅与采用 | 原生快照、逐项编辑、并发冲突与教师采用 | 已实现；3 项组件测试及真实 dev 页面加载通过 | 真实模型/图片精度、多教师完整页面回归 |
| AI-14 | JPlag + AI 查重 | 部分实现，局部验证（快照/全候选/幂等回写） | `/v2/ai-plagiarism` 支持快照、JPlag 区间、AI 证据、逐对复核、报告和终态锁定；仅 mock 页面测试 | 大班性能、真实 AI 解释质量和页面闭环 |
| AI-15 | 四语言 IDE/指导 | 四语言沙箱、可见样例、原生提交、绑定考试禁用 | 已实现；3 项组件测试及真实 dev 页面加载通过 | 统一考试时段策略、提示质量、生产隔离验收 |
| AI-16 | 课程资料/RAG | 版本/来源哈希、受限检索/引用解析、多轮上下文、同内容文档重传复用 | 上传/索引/引用回跳页已实现；组件及页面加载通过 | 文档/OCR/检索质量基准，真实跨格式问答验收 |
| AI-17 | 实验验收/面试 | 邀请/逐轮媒体、缺片检查、重试/重邀、教师复核/采用、完整终态筛选 | 已实现；组件及真实 dev 列表加载通过 | 真机摄录、离线恢复/转写质量、真实教学验收 |
| AI-18 | 文件、媒体、证据 | 部分实现，局部验证（配额/补偿/孤儿审计） | `/v2/ai-admin` 接存储审计/dry-run 清理，验收页接媒体 manifest/重传；无对象存储/长媒体真实测试 | 缺片/重传、workspace 配额、保留期/对象存储 |
| AI-19 | 旧任务/题栈数据迁移 | 离线 Prisma 导出转换、映射、资产校验复制、幂等导入；42 个模型分资源/历史审计处理 | 非页面事项；已有转换和导入 CLI | 真实源导出/身份课程映射、余额结转决策与最终全量对账 |
| AI-20 | 发布、运维、高可用 | 制品构建校验/原子切换/回滚/备份工具、systemd/nginx模板和手动 CI 已实现 | 统一 Web2/Autolab 制品预检；Java 运维不变 | CI 凭证/保护环境配置、生产依赖/备份/灰度/多机演练 |

## 4. 各模块实现与差距

### AI-01：异步任务执行

**已实现逻辑**

1. 新请求先验证 OJ 主体、AI 资格、资源范围、排队和余额条件；同事务保存 immutable task input snapshot（JSON、版本、kind、SHA-256）。Worker 在处理前和提交结果前各刷新一次 OJ 身份/权限；修复了 monotonic 初值导致进程启动后短窗口可能跳过首次刷新的问题。
2. 同一事务写 auto_task_run、payload 日志和 auto_task_job。按 owner_id + operation_key 去重；不同输入冲突返回 409。
3. 事务提交后才发送 Redis 唤醒。通知失败不撤销数据库任务，Worker 还能轮询。
4. claim 在 runtime 配置行上加锁，计算全局/个人/类别并发；使用 SKIP LOCKED 选任务，attempt 加一，签发随机 lease_token 和 60 秒租约。
5. Worker 心跳约 10 秒一次，执行检查也可续租。过期任务重领或最终失败，普通失败指数退避，默认最多 3 次尝试。
6. 完成时再次校验租约和资源 version；结果、资源更新及终态日志在同一事务提交。旧 attempt 不能覆盖新结果。
7. 原接口保留，删除改留痕；有游标事件/SSE与队列概要。Web 默认不再为每个 Gunicorn 进程启动消费者。

**尚未完成**

本轮已增强：旧任务不再通过 Redis list 作为唯一执行依据；写入 `auto_task_run`、`auto_task_job` 和 payload 审计后才发布 Redis 唤醒；新增 `blocked` 欠费等待、任务队列配额、按 agent/sandbox/document lane 的并发限制、SSE 事件流、租约丢失后的失败关闭、旧 task 删除留痕、重试审计和 MySQL 大文本/时间精度适配。随后又补充了旧任务兼容、题库候选、文件/事件授权、worker 异常、操作键冲突、处理前/完成前 OJ 再授权及启动窗口回归。当前最新快速全量为 245 passed/12 skipped；独立 MySQL 快照为 230 passed/9 skipped，另有 101 项迁移/幂等 MySQL 专项通过；不同时间快照不拼成一次全量结果，均不是生产高可用验收。

- “只执行一次可见数据库结果”不等于所有外部动作只执行一次。模型调用、文件生成、旧报表上传的重复和孤儿产物需单独处理。
- claim 已按 created_at/id 作 keyset 分页，前 100 条受阻不再饿死后续任务；损坏快照单独标 failed 并继续领取，已有测试。
- authoring.generate 被归为 agent，但其内部还执行沙箱；类别上限并未为每个子步骤单独计数。不能把它描述成所有实际沙箱进程都已全局受限。
- 本机独立 MySQL 已用子进程 os._exit(99) 验证强退后调用意图留存、租约恢复、未知用量阻断重复调用；数据库断连、Redis 恢复、长期过载、多机及共享 workspace 晚到写入仍未实测。
- auto_task_revision 在业务事务内追加保存内容、版本、状态、删除标记、hash、actor_id 和 task_id；history 按当前权限读取。它从启用时开始记录，不回填迁移前已覆盖的数据。
- 本轮已增加 `auto_task_input`，保存任务创建时的资源 JSON、kind、version 和 SHA-256，Worker 领取时校验快照。它与资源修订表分别承担执行输入和变更审计职责；JSON 历史不等于文件二进制历史/WORM 存证。
- 旧接口批量入队、幂等、重试和新状态展示还需真实 Web2 回归。

证据：[store.py](../../sduoj-autolab/auto_task/store.py)、[worker.py](../../sduoj-autolab/auto_task/worker.py)、[model/auto_task.py](../../sduoj-autolab/model/auto_task.py)。

### AI-02：身份、权限和领域数据

**已实现逻辑**

- 同时解析原 `SDUOJUserInfo` 与 `SDUOJUserInfo-UserId`，要求两者各且仅各一份；修正 form URL 编码中 `+` 的解析，拒绝重复 JSON key、非规范 claim、非规范十进制 ID 及两个 header 身份不一致。
- Gateway 网络边界在 debug 未配置时只信任 loopback；release 缺失/错误/全网 CIDR 均 fail-closed。若 Uvicorn 已用 X-Forwarded-For 覆盖直连 peer，release 返回 503，避免把浏览器来源误当 Gateway 来源。
- AiAccount 只有使用资格和费用，不存本地密码。正常 OJ 登录沿用现有系统。
- 资源先检查课程/题单范围，再判断本人、绑定学生、共享课程内容或教师权限。
- 会话/IDE保持私人范围；管理角色用于模型、积分、审核等平台操作，不自动开放所有课程资料。
- AiResource 以 kind + JSON 承载题库、草案、会话等，引用现有 course_id/psid；最终采用成绩写原答题卡。

**尚未完成**

- 应用层已严格校验双 header 和直连 peer，但 header 本身仍不是密码学签名；必须让 Gunicorn/Uvicorn 保留直连 Gateway TCP peer，配置可信 CIDR，并以网络策略关闭绕过 Gateway 的入口。
- roles/groups 仍来自请求会话快照；即时撤权、账号删除、改名、学期归档及后台执行时再授权没有完整事件/查询闭环。
- course_id/psid 引用不等于源资源删除已自动联动清理；需统一资源生命周期。
- 部分 data 仍是通用 dict，需要逐领域 schema、字段约束、审批和历史记录。
- 完整 ADMIN/SUPERADMIN、课程教师、助教、学生、撤权和归档矩阵还未验收。

证据：[auth.py](../../sduoj-autolab/auth.py)、[resources.py](../../sduoj-autolab/auto_task/resources.py)、[entities.py](../../sduoj-autolab/auto_task/entities.py)。

### AI-03：模型调用与 Codex

**已实现逻辑**

- 一个 runtime 配置保存 provider、base_url、model、思考强度、费率及限额。API key 用 Fernet 加密，读取只返回 has_api_key。
- 支持 Codex CLI 的 Responses 接入，以及兼容 Chat Completions 的 HTTP JSON Schema 输出；可读取提供者 /models。
- Codex 使用每资源 workspace、每次 run 子目录、.codex-home 和 sessions.json；按 schema title + model 记录可恢复会话。
- CLI 输出 JSONL 事件；使用输出 schema、结果文件、Pydantic 校验，再由后端提交结果。shell_tool 被禁用。
- 原文档/视觉辅助函数在 ACTIVE_CONTEXT 下进入新模型与计费上下文。

**尚未完成**

- 本机新 runtime 尚无模型、provider 和 key 配置，因此没有本机新链路真实模型执行证据。
- 同一提供者支持 moderation/grading/authoring/tutor 分用途模型，覆盖配置必须提供完整且有限的费率；每用途不同提供者/密钥尚未实现。
- 原 MCP 主动 save_*、Agent 自主编译/试验/编辑 workspace 的机制未等价迁入。是否恢复这些能力需形成明确 ADR，而非写成“Codex 功能已原样迁移”。
- 提供者兼容性、断流/失败用量、版本固定、ARM64 CLI、会话恢复及长时间运行需真实验证。
- 当前 workspace 持久化不等于已具备完整题面/代码/报告/证据目录协议、容量管理和可审计快照。

证据：[configuration.py](../../sduoj-autolab/auto_task/configuration.py)、[runtime.py](../../sduoj-autolab/auto_task/runtime.py)、[llm_client.py](../../sduoj-autolab/auto_task/llm_client.py)。

### AI-04：成本、积分与预算

**已实现逻辑**

请求发出前保存 running AiRun 与费率，返回或失败时按输入/缓存/输出 token 计算 USD，乘 1000 得积分，事务结算。缺少完整用量或遗留调用租约过期后标 unsettled，阻断同付款主体后续 AI 任务；非 AI 执行有例外。管理员依据供应商证据调用对账接口，相同请求重放不重复扣费，不同请求冲突，晚到 Worker 不覆盖人工结算。学生验收由创建者付费。

**尚未完成**

- 当前按 run 扣费，与旧原型按导入/工作流 billing scope 汇总的账单语义不同，需要前后端和产品统一。
- 已补崩溃后未知用量标记与人工幂等对账；供应商账单自动拉取和实际账单比对尚未验收。
- max_task_cost_usd 在下一次调用前检查已知累计成本，属于软停止条件，不是不可超支的硬预算。
- 费率可为 0、用量可能未知，需要显示“未知/未配置”，不能伪装成免费或完整账单。
- 课程/考试共享预算、预留额度、超支处理、失败补偿、价格版本校准与财务对账尚未完成。
- `/v2/ai-admin` 隔离管理页已接账户、积分、审核、队列和存储审计；旧账号区域、批量审核、申诉和完整审计闭环仍未接入。

证据：[runtime.py](../../sduoj-autolab/auto_task/runtime.py)、[store.py](../../sduoj-autolab/auto_task/store.py)。

### AI-05：审核与 AI 功能停用

部分工作流在运行前请求 normal/warning/violation 分类；三种结论均记录审计，滚动七日三次警告或违规会停用并取消该主体 AI 任务。管理员修改结论后重算资格，禁止自我复核。停用不改 OJ 全局账号，旧 auto-task 路由也加了资格检查。

course.index、subjective.grade、plagiarism.scan 和原生批阅适配路径已补第三方内容审核日志，标记 attribution=third_party/account_action=none，不把学生材料风险处罚到教师账号。该日志也不是对学生违规的自动认定；责任归属、申诉、人工处置与 UI 仍需闭环。

证据：[handlers.moderation](../../sduoj-autolab/auto_task/handlers.py)、[store.recalculate_access](../../sduoj-autolab/auto_task/store.py)。

### AI-06：录题、转录与题图

上传保存文件元数据与 SHA-256，创建 collection/question 资源后异步提取。图片直接传模型；其他文档先取文本。Extraction 要求原文/中文题干、独立选项、答案、解释、标签及题图。题图按归一化 bbox 用 Pillow 裁切，SVG拒绝脚本/危险属性，最后在有效租约下入库并关联文件。

差距：没有真实 OCR/数学/代码精度基准；多题切分、残缺题、重复片段和人工校正仍需闭环。提取、解题和验证是可独立投递的任务，还不是所有录入后无答案题都自动解题/复核的完整管线。空提取结果保留既有题集并标记 needs_input；后续批次按 ID 增量合并，不清空已有题目。复杂 Word 公式和图形保真有限，支持格式须以入口与解析器的交集为准；不能将辅助函数支持扩展名等同上传入口已支持。Web2 已接文件录题，但手机相机采集/上传新流程尚未接通。PPTX 现在有基础 slide XML 提取，但图片、备注、主题结构和复杂图表未处理。

证据：[handlers.py](../../sduoj-autolab/auto_task/handlers.py)、[assets.py](../../sduoj-autolab/auto_task/assets.py)、[files/upload](../../sduoj-autolab/server/auto_task_ai.py)。

### AI-07：检索、去重和标签

- 检索：MySQL FULLTEXT ngram 相关度与转义子串匹配；再做授权/标签过滤。
- 精确去重：NFC、换行规范化和题干/题型/排序后的选项内容哈希；范围是本人或课程，不是全站无边界共享。
- 近似去重：扫描范围内最近 500 条，SequenceMatcher 达到 0.75 后选最多 5 条交模型判断是否严格相同；保存前核验候选 ID、版本和范围。
- 标签：每题最多处理 6 个建议，NFKC、别名匹配和 0.82 字符相似度归并，管理员维护名称/别名。

差距：模型语义判重仍可能误合并；字符相似标签不等于语义分类精准。需要黄金集、误合并撤销、标签合并历史、跨语言/公式格式测试和大库召回。当前读取/权限过滤部分发生在应用层，未做目标规模性能验收。精确、近似、原生导入和题集物化路径已有墓碑回归，但其他未来导入器也必须遵守显式恢复规则。

证据：[resources.py](../../sduoj-autolab/auto_task/resources.py)、[handlers.match_duplicate](../../sduoj-autolab/auto_task/handlers.py)、[resources/list](../../sduoj-autolab/server/auto_task_ai.py)。

### AI-08 / AI-09：解题、验证、追问、纠错与题集

solve 生成中文答案；verify 生成校验报告，声明需要执行时调用隔离运行器，比对用例后才可通过；chat 保存消息。`question-workflows/intake` 以 batch ID 幂等追加文字/文件批次，保留稳定题号和原始提取内容；题目可从集合拆出、恢复或从重复项物化。录入可选择自动串联 solve/verify，自动链默认禁止代码执行，提交失败会保留明确状态而不覆盖已录入内容。题目 follow-up 和 revision restore 均检查版本。

删除后的物化题、精确重复题和原生导入题不会由普通去重、题集重连或重放隐式复活；题集重连遇墓碑返回 409，恢复只能走显式版本恢复 API。差距：是否需要执行仍主要由模型声明；没有全覆盖的确定性验算策略。Web2 已有题目历史、恢复、题集 manifest 和局部操作 UI，但多人同时编辑、缺题局部重试、原生已发布题同步和共享 course 附件口径仍需真实回归。

证据：[handlers.py](../../sduoj-autolab/auto_task/handlers.py)、[ResourceCreate/Update](../../sduoj-autolab/ser/auto_task_ai.py)。

### AI-10 / AI-11：命题与发布

authoring v2 支持带 instruction 的幂等迭代修订，保存 parent/package hash；候选包含题面、单份标程、公开/隐藏测试、generator、validator 和种子。后端两次运行 generator 检查确定性，并让 validator、标程逐例通过后规范化测试分值。教师批准后，native-plan 输出 Java 原生题目、描述和 checkpoint 上传计划；native-finalize 回读每个 checkpoint 的原始输入/输出字节并复核哈希、分值、模板、题面和 source marker，全部一致后才绑定 ProblemGroup。bundle 继续导出题面、参考程序、测试文件与验证信息。非编程题发布检查现有组管理权限和资源版本，将答案标签映射到原生选项位置，然后创建原题型记录并加入 ProblemGroup。

本轮新增原生 import、程序题 plan/bind。客观题保留原生单选/多选/不定项类型和答案映射；主观题保留 subtype、config/rubric；程序题通过浏览器 OJ 会话调用 Java create/updateDescription，再核验 source 标识、版本、题面、发布者并事务绑定 ProblemGroup。内部 query 的默认描述必须再用 defaultDescriptionId 查询，不能把 descriptionId=0 当作完整题面。原生导入在 RPC 后复查题组权限和成员关系，源题移出题组后撤销导入资源访问。

真实 dev 已验证三类题的录入/重放，程序题另经原生测试点与 C++14 模板得到 Accepted/100。单元/接口测试已覆盖 generator/validator、非确定性拒绝、checkpoint 被篡改时不绑定题组；真实模型仍未配置。测试点上传目前由调用方按 native-plan 执行，Java 创建与 Autolab 事务不能跨库原子提交；响应未知时仍须依据 source marker/题号核对。大测试集、跨库补偿、原生旧题版本更新和真实命题质量仍开放。

证据：[authoring protocol](../../sduoj-autolab/auto_task/authoring.py)、[native plan/finalize](../../sduoj-autolab/server/auto_task_authoring.py)、[publish/bundle](../../sduoj-autolab/server/auto_task_actions.py)。

### AI-12：考试与考务

CSV 解析支持学号、姓名、可选用户名，可调用 OJ 解析 userId；exam.plan 按容量选择尽量少的考场，分配座位并可确定性随机化。草案生成后先 prepare 保存规范化的原生 problem_set_base 及 publication_hash，并进入待复核版本；review 后 publish 必须与已准备的内容哈希一致才创建 ProblemSet.type=1。更改草案或重新编排会清除准备内容；重放也校验哈希。

发布后可读取原生课程教室及禁用座位，把计划内学生与当前 OJ group userId 重新核对后写入 ojClassUser；替换需要显式确认，回滚前会比较当前座位，避免覆盖后来人工调整。TEST 模式必须至少存在一张真实完成的原生答题卡才能签发验证证书；监控接口和防公式注入 CSV 提供 NOT_STARTED/WORKING/SUBMITTED 快照。

差距：FORMAL 发布对 TEST 证书的消费和独立正式命名空间仍需完整验收，座位绑定与 Java/Autolab 发布也不是跨库原子事务。账号、密码条仍归 OJ，批量 provision/受控打印没有因此自动完成；真实大考场并发、到场状态、差异名单、回滚和页面仍需验证。

证据：[plan_exam/parse_roster](../../sduoj-autolab/auto_task/handlers.py)、[publish_exam](../../sduoj-autolab/server/auto_task_actions.py)、[native examination binding](../../sduoj-autolab/server/auto_task_exams.py)。

### AI-13：主观题批阅与成绩采用

存在以下路径，必须分清：

1. 原 subjective_review 请求继续兼容；新增 native/grading/create 验证题单→题组→主观题关系、管理权限与原答题记录，在提交事务冻结 source/hash。Worker 复用原文字/附件解析，在执行前和写候选时检查原答案、量表、人工分是否变化；结果带 source、input_hash、grade_hash、candidate_job_id。
2. 新 subjective.grade：针对通用 grading 资源生成逐项候选分与置信度，并检查量表名称/满分。
3. adopt：目前要求第 1 类来源信息；锁答题卡并复查题面、答案、量表和当前评分，教师确认后写 judgeLog/judgeComment，并审计。已有人工分需要显式覆盖确认。

原生来源任务已有创建→候选→教师逐项编辑→采用的数据库测试；编辑只改候选并保存操作者/理由，采用时仍重新冻结并比较原答题、量表和人工分。自由输入的 grading 候选仍不能任意绑定答题卡，普通 resource/review 只改状态。低置信度策略、证据定位、相关程序提交版本和缓存/并发边界仍待补。原文档转换分支会把图片转为文字，不能宣称所有旧批阅路径均已做到模型直接读取原图且不依赖转录。

Web2 已新增 `/v2/ai-grading`，接入新候选生成、来源/置信度展示、逐项编辑、人工覆盖确认和采用操作；当前没有该页专项测试或真实页面回归。任务 success 仍应显示“生成完成/待复核”，不能当作“已完成正式评分”。

证据：[legacy_bridge.py](../../sduoj-autolab/auto_task/legacy_bridge.py)、[candidate edit](../../sduoj-autolab/server/auto_task_management.py)、[adopt_grade](../../sduoj-autolab/server/auto_task_actions.py)。

### AI-14：查重

服务可从原生题单/编程题冻结每名学生的一份提交，保存 submission ID、代码/整体哈希、判题信息和选择策略；也接受 2–1000 份显式代码及 base_code。隔离运行 JPlag，解析器兼容旧 overview.json 和 6.3 的 topComparisons/submissionMappings/comparisons，不再只保留 top 100；限制单条解压内容 10 MiB，不展开不可信路径。命中区间和相似度送入 AI 解释；逐对 CLEAR/SUSPICIOUS/CONFIRMED 复核保存教师、理由及版本历史，授权 report 接口提供压缩报告。所有候选复核完成后可按快照和版本幂等写回原生 antiCheatingResult，输入或既有结果改变时拒绝覆盖。

实际 JPlag 6.3 Java 报告已通过容器测试。此前故障定位为该 JAR 要求 Java 25 且 Java parser 需要 JDK，默认改用 eclipse-temurin:25-jdk；没有放宽 noexec 策略。Web2 已新增 `/v2/ai-plagiarism`，支持候选列表、逐对复核、报告下载和幂等写回，但 AI 解读在测试中仍使用夹具，JPlag 四种语言的完整质量评测、大班性能、候选策略和真实页面尚未完成。

证据：[plagiarism.py](../../sduoj-autolab/auto_task/plagiarism.py)、[native snapshot](../../sduoj-autolab/server/auto_task_native.py)、[review/writeback](../../sduoj-autolab/server/auto_task_actions.py)。

### AI-15：教学 IDE

四语言使用固定命令模板和 Docker-compatible 镜像；无网络、只读根、非 root、资源/超时限制。stdin 使用非阻塞写入，stdout 与编译/运行 diagnostics 分离，返回退出码和 timed_out；支持 1–20 个可见样例及逐例结果，标记 scope=visible_tests。tutor 利用代码、题面和历史消息给诊断提示。明确绑定 psid 且 ProblemSet.type=1 时阻止教学任务。

差距：运行器默认关闭，生产隔离、rootless/权限、镜像 digest、ARM64和限制实际生效未验收。本机已实测 C/C++/Python/Java、编译失败、超时和网络不可达；可见样例不是隐藏测试，也不替代 Java 正式判题。只检查显式绑定的 psid，未形成统一考试时段/来源策略；没有 psid 的私有 IDE 不能据此宣称也被考试策略覆盖。“不输出完整答案”主要是 prompt 约束，需要行为评测。Web2 `/v2/ai-workbench` 已接入四语言编辑、样例运行、指导和正式 OJ 提交，但没有该页专项浏览器回归，也未接入既有代码编辑器。

证据：[sandbox.py](../../sduoj-autolab/auto_task/sandbox.py)、[create_job](../../sduoj-autolab/server/auto_task_ai.py)。

### AI-16：课程资料与 RAG

PDF 用 PyMuPDF 取文本，空文本页渲染图片再转录；DOCX 用 python-docx 取段落/表格；支持文本/Markdown。每 1200 字符起一块、最多取 1500 字符，保留页号/偏移引用。旧块软删除、按 indexed_version 判定有效。问答最多读取 5000 个块，以词频和中文二元片段计分取前 8 个；显式 external_research 才查询 Crossref。模型引用 ID 必须属于候选集。

差距：

- PPTX 上传、ZIP 体量检查和按真实 slide 序号解析已接通；图片/备注/图表和复杂版式仍未处理。
- DOCX 统一 page=1，不是真实 Word 页码；公式、内嵌图片和复杂版式未完整保真。
- 当前是词法启发式检索，不是向量检索，也不是已验证的大规模高质量 RAG；前 5000 块上限与逐块父资源查询需改进。
- 有检索片段时必须返回至少一条允许引用；这验证 ID 集合，不证明引用在语义上真正支持结论。
- 引用 ID 已包含 resource/version/file/page/offset；前端回跳、文件二进制历史和完整多版本浏览仍待接通。
- 已使用最近 8 条对话作为上下文；长对话压缩及真实追问质量仍待验收。
- 文档重传按内容 hash 幂等、自动索引、课程归档清理、审核和引用回跳 UI 仍未完全闭环；`/v2/ai-course` 已提供基础上传、问答、引用抽屉和 PDF 页码回跳。

证据：[documents.py](../../sduoj-autolab/auto_task/documents.py)。

### AI-17：实验验收

已有邀请、student_id 与可选原生主观题答案快照绑定、preflight、逐轮 response、事件、取消、失败重试和续邀接口；按 operation_key 幂等，按 sequence 防止错轮回答，校验过期/时长。媒体片段按 track/sequence/hash 关联回答，manifest 阻止缺片终结；模型可问下一题或结束，保存逐项 rubric、摘要、分数、置信度和证据位置。教师审批固定 candidate/source hash，采用前再次检查原答题/量表/人工分，显式确认后才写原答题卡。

与原型相比，当前是简化状态机；本轮补充了 rubric 名称/满分校验、逐项 candidate criteria、置信度和 integrity conclusion，但以下不能标成完成：

- 已实现 criteria、previous_answer_evaluation、source_type/行号、integrity_conclusion；教师 rubric 名称/满分必须一致，后端重算总分，低置信度或风险事件转 review。真实模型的评分稳定性、证据准确率与申诉口径仍未验证。
- 媒体分片已有回答/轨道/序号关联和缺片门禁，但没有完整服务端转写/转写校准、断点上传、长时回放和对象存储流程。
- 预检目前信任客户端证据布尔值，不等于真实校验屏幕/人脸/前置摄像头，也不是不可绕过的考试保证。
- 单条邀请、学生/教师字段裁剪与最终成绩采用已有后端测试；`/v2/ai-interviews` 及会话页已接状态筛选、邀请、重邀/重试/取消、媒体重传、教师复核和采用确认，但批量邀请、课程撤权、真机媒体、真实刷新/断网恢复仍未验收。
- 已修复结束时追加未回答问题，并保存前一轮评价；真实超时、续邀、失败重试和付费归属仍需完整状态机回归。
- 跨刷新缺片恢复、音画回放、问题时间线、IndexedDB 重传、替代验收/申诉与硬件测试未完成。
- 旧题栈中的录像、语音和人脸组件没有因后端 API 存在而自动出现在 Web2。

证据：[InterviewTurn](../../sduoj-autolab/ser/auto_task_ai.py)、[interview lifecycle API](../../sduoj-autolab/server/auto_task_interviews.py)、[handler](../../sduoj-autolab/auto_task/handlers.py)。

### AI-18：文件与证据

文件按随机 ID 存本地目录，记录 hash、大小、声明 MIME 和资源关联；限制单文件 50 MiB、图片像素、DOCX/PPTX 解压体量，下载检查资源授权，sequence 可对分片重放去重。

差距：哈希不是完整证据链；声明 MIME 不是媒体格式/时长的完整验证。已按账户锁检查累计上传配额（默认 512 MiB，可配置 max_storage_mb），同序列重放不重复占额，异常回滚会移除本次文件；storage 接口返回容量。新增管理员只读审计可报告磁盘孤儿、DB 缺失文件、size 不一致、特殊条目和非法路径；显式清理默认 dry-run，要求原因、至少 1 小时宽限并限制单批文件数/字节，删除前复查数据库与 inode/mtime/size，避免误删并发注册或替换文件。这为进程崩溃后磁盘孤儿提供补偿，但尚不是自动修复 DB 缺失/内容篡改，也不替代备份。工作目录/转录产物配额、保留期、对象存储、加密备份、WORM 和长媒体缺片流程仍未完成。生产不能让用户业务直接控制宿主 Docker 权限。

### AI-19 / AI-20：数据迁移、发布和运维

migrate 命令默认检查、显式 apply 建表/索引。旧 pending/running task 导入要求人工 actor-map 和停止旧消费者的确认，不把被评分学生当发起人。已增加中性 Problem Stack JSON resource 导入函数：按 source ID/内容哈希幂等，要求逐项映射到已核验 OJ 主体，来源变化或未解析映射会阻止整次应用；它不直连旧 PostgreSQL。领域字段完整转换、账本、文件校验搬迁和生产对账仍未完成，旧服务/旧任务尚未生产退役。

本机开发环境、文档和 SQL 参考已具备；完整前后端制品、内网 runner、Ansible/systemd 发布、配置漂移检测、灰度、备份恢复和回滚仍主要是方案。原 GitHub Pages workflow 不等于当前生产发布流水线。生产的 Nacos 认证、TLS 入口、端口限制、ARM64运行器及磁盘治理需要用户按变更窗口验证执行。本轮没有再次测量生产，之前的磁盘/服务记录只能作为历史线索。

## 5. 前后端共享契约与接入清单

### 5.1 已有准备

- 后端机器契约：[auto-task-ai-openapi.json](../../sduoj-autolab/docs/auto-task-ai-openapi.json)，91 条路径；export_ai_contracts.py 可生成和验证 API/13 表 DDL。
- Web2 的 [autolab.json](../../sduoj-web2/src/Config/validation/autolab.json) 当前包含 135 条请求路径，其中 56 条为新 AI 请求校验规则。
- [export-autolab-contracts.py](../../sduoj-web2/scripts/export-autolab-contracts.py) 从后端路由/Pydantic导出 schema；这属于前端任务已有工作。
- 现有 [AutoTask.tsx](../../sduoj-web2/src/Component/problemSet/AutoTask.tsx) 和 [c-api.ts](../../sduoj-web2/src/Utils/API/c-api.ts) 仍主要调用原 auto-task 路径。新增 AI 工作区页面分别使用 ai-platform.ts、ai-workbench.ts、ai-authoring.ts、course-knowledge.ts 和 ai-plagiarism.ts；旧题库、课程、任务入口尚未统一切换。

本轮修改仅限新增 AI 页面/API client/专项测试与一处顶层路由；未改当前修缮中的表单、布局、组件或依赖。最终全站 TypeScript 检查通过；新增页面 ESLint/单测/浏览器通过，不等于全站发布构建或全部 E2E 已通过。

### 5.2 必须共同固定的语义

| 契约 | 统一口径 |
| --- | --- |
| 身份 | 浏览器只带原 OJ Cookie，不自行构造身份 header；AI 资格单独查询 |
| 三种状态 | job 的 success、资源的 approved/adopted、验收的 completed 是不同概念 |
| 幂等 | 一次用户意图使用一个 operation_key，网络重试复用；主动重算创建新键 |
| 版本 | 更新带 version；409 显示冲突并刷新，不能悄悄覆盖 |
| 费用 | 展示当前余额、已知实际成本和未知用量；不要把 0 费率/缺失 usage 等同真实免费 |
| 停用/欠费 | 停用仅留原因/复核状态；欠费限制 AI，不能退出 OJ 或阻断交卷 |
| 发布 | dry_run 是检查，不是正式提交；候选批准与最终落库要区分 |
| 流式事件 | 记录 cursor，重连继续读取；能解析旧纯文本日志和新结构化内容 |
| 文件 | 统一走授权文件 API；媒体关联资源、题次、类型和序号必须共同定义 |
| 领域 payload | 通用 dict 还需细化，前端校验不能代替后端校验；枚举/空值以运行契约为准 |

### 5.3 前端后续工作队列（隔离工作区已接通，旧入口和真实验收待排期）

| 编号 | 原生入口 | 当前状态 | 后续交互/验收 | 依赖 |
| --- | --- | --- | --- | --- |
| FE-01 | 现有任务页/通用任务框架 | `/v2/ai-workbench` 已接任务监控和 IDE；AutoTask 已增加带 psid 的入口 | 统一旧任务页的任务详情/费用/事件视图；真实 SSE/故障回归 | AI-01/04；旧路由一致性 |
| FE-02 | 现有批阅页 | `/v2/ai-grading` 已接候选对照、编辑和采用；Review 已增加带来源参数的入口 | 完整嵌入原批阅页；真实图片/成绩并发回归 | AI-13 来源/审核契约 |
| FE-03 | 题库/题单录题入口 | `/v2/ai-bank` 已接批次录入、预览、纠错/题集操作；题目管理已增加入口 | 手机相机、原题库完整融合、真实 OCR/去重质量 | AI-06/07/08/09 |
| FE-04 | 命题/题单管理 | `/v2/ai-authoring` 已接草案、验证、导出和发布恢复；题单页已增加入口 | 完整接入原命题/题单管理；真实模型和跨库回归 | AI-10/11/12 |
| FE-05 | 原课程页 | `/v2/ai-course` 已接资料、索引、问答和引用回跳；课程列表已增加 course_id 上下文入口 | 完整接入原课程页；真实权限、长文档和 RAG 质量 | AI-16 |
| FE-06 | 原代码编辑/练习入口 | `/v2/ai-workbench` 已接四语言运行、样例和指导 | 接入原代码编辑器；考试禁用和生产隔离验收 | AI-15 安全运行器与策略 |
| FE-07 | 验收/题单入口 | `/v2/ai-interviews` 已接邀请、会话、媒体重传和教师采用；题单页已增加入口 | 真机媒体、断网恢复、批量邀请和学生可见性 | AI-17/18 详细状态机 |
| FE-08 | 管理/账号相关区域 | `/v2/ai-admin` 已接模型、预算/积分、审核、停用和存储审计 | 角色矩阵、申诉、自动账单和生产权限回归 | AI-02/03/04/05 |
| FE-09 | 原监控/考务页 | `/v2/ai-exams` 已接名单、座位、监控和导出；题单/课程页已增加考务入口 | 差异名单、大考场和回滚回归；完整嵌入原考务页 | AI-12 原生映射 |

### 5.4 本轮新增 AI 工作区页面

Web2 在 `src/Pages/Manage/AI/` 新增 9 个导航入口及 1 个验收会话详情路由，均只依赖现有 Web2 请求封装和 Autolab AI API：

- `/v2/ai-workbench`：任务列表、SSE/轮询监控、四语言 IDE、样例运行、指导和正式 OJ 提交。
- `/v2/ai-bank`：question 检索分页、文字/文件录入、版本/题集操作和原生三类题导入。
- `/v2/ai-authoring`：命题生成、修订、复核、bundle、checkpoint 和原生发布恢复。
- `/v2/ai-grading`：原生主观题候选、来源/置信度、逐项编辑、人工覆盖确认和采用。
- `/v2/ai-exams`：名单/考场/计划、TEST/FORMAL 发布门禁、座位绑定、监控和 CSV。
- `/v2/ai-course`：课程资料上传/索引、问答、课外检索开关、引用详情和 PDF 回跳。
- `/v2/ai-plagiarism`：原生快照、候选对、JPlag 证据、逐对复核、报告和幂等写回。
- `/v2/ai-interviews` 与 `/v2/ai-interviews/:id`：验收邀请、会话、媒体、状态筛选、教师复核和采用。
- `/v2/ai-admin`：AI 账户、provider/模型、积分/账务、审核停用、队列和存储审计。

这些是新增隔离页面，未重写当前 AutoTask、课程或题单页面。前端审计后修复了 AIAdmin 重复清理弹窗、Form 连接警告、旧 Excel `xlsx` 依赖迁移、jsdom `crypto.randomUUID` 依赖、考务/批阅/IDE 专项测试缺口和验收终态筛选；当前统一 AI 页面/API/路由/菜单专项为 22 suites、66 tests 通过。真实 dev Gateway + OJ 登录后的工作区浏览器检查 `ai-workspace.spec.ts` 为 3/3，题库 native 浏览器为 1/1；题目录入独立夹具受 Ant Design Select/HMR 交互时序影响，未取得稳定通过，因此不将其计入通过证据。这些仍不等于真实模型、真机媒体或全角色生产回归。完整发布预检曾在 Node 24 V8 GC 出现原生 SIGSEGV，已用测试专用 `NODE_OPTIONS=--jitless` 完成 Jest，production build 使用正常 WebAssembly Node；失败原因已保留在 release runbook。

发现一个具体旧路径差异供前端任务后续核查：通用 AutoTaskFramework 调用 cApi.deleteAutoTask，其路径是 /auto-task/delete/...；题单专用方法是 /ps/auto-task/delete/...。在当前 /api 基址下，二者并不相同。此处只登记，不修改前端。

## 6. 未完成工作及优先级

优先级 P0 指相应上线/切换前的阻断项，不表示本轮自动授权修改生产。负责角色是建议分工，并非已经指派给其他任务。

| 编号 | 优先级 | 工作及明确完成条件 | 建议负责 | 依赖/关联 |
| --- | --- | --- | --- | --- |
| BE-01 | P0 | 建立真实提供者/CLI验证：模型列表、文字/图像、续会话、失败/取消、usage均有可追溯证据 | 后端+运维 | AI-03；本机配置缺失 |
| AI01-OPS | P0 | 在预生产执行多 Worker 崩溃、租约过期、数据库断连、Redis 不可用、重复副作用和队列公平性演练；确认旧消费者已停止 | 后端+运维 | AI-01；不能用本机夹具替代 |
| SEC-01 | P0 | 已补双身份头、CIDR fail-closed 与 Worker 首尾再授权；仍需预生产直连 peer、网络隔离、完整角色/撤权矩阵 | 后端+运维 | AI-02；所有新功能 |
| SEC-02 | P0 | 将旧 `const.py` 中的 release 环境凭证常量迁至受控密钥配置，并在任何生产发布前完成轮换与扫描验证；文档和日志不得记录凭证值 | 后端+运维 | AI-03/20；发布前阻断 |
| RUN-01 | P0 | ARM64隔离执行器四语言/JPlag实测，资源限制与取消生效，无宿主敏感权限 | 后端+运维 | AI-10/14/15 |
| BE-02 | P0 | 通用批阅/验收来源与原答题卡绑定，教师编辑/采用不覆盖新人工分；真实页面回归 | 后端+前端 | AI-13/17、FE-02 |
| BE-03 | P0 | 已补不可变输入/历史、墓碑与孤儿文件补偿；仍需统一源资源归档/删除、二进制历史、保留期及生产清理审计 | 后端 | AI-01/02/07/18 |
| BILL-01 | P0 | 明确 run/scope结算口径、崩溃补账/未知usage、预算边界，账目可核对 | 后端+产品/运维 | AI-04 |
| EXAM-01 | P0 | 发布绑定已批准计划，TEST/FORMAL门禁、原生参与和回滚明确 | 后端+教学负责人 | AI-12，正式考试前 |
| INT-01 | P0 | 完整验收rubric/逐轮证据、终态/失败恢复、学生可见性、媒体关联通过 | 后端+前端 | AI-17；开启验收前 |
| DATA-01 | P0 | 旧task/题栈数据与文件映射对账，停止旧消费者，明确唯一写入者 | 后端+运维 | AI-19；切换前 |
| OPS-01 | P0 | 预生产、备份恢复、灰度/回滚、配置和端口基线完成，用户批准生产变更 | 运维+前后端 | AI-20 |
| QA-01 | P0 | 旧5项过期夹具已修正；当前快速 pytest 245/12、独立 MySQL 8 快照 230/9；继续真实模型、全角色权限和峰值测试 | 测试+相关维护者 | 第7节 |
| DOC-01 | P1 | PPTX、复杂PDF/DOCX/公式图形、批量导入和质量基准 | 后端 | AI-06/16 |
| RAG-01 | P1 | 检索质量/规模、文档版本化引用、至少一条有效引用、多轮上下文和回跳 | 后端+前端 | AI-16、FE-05 |
| PLAG-01 | P1 | 已补原生快照/完整候选/逐对回写；仍需大班性能、候选策略、真实 AI 质量和前端闭环 | 后端+前端 | AI-14 |
| AUTH-01 | P1 | 已补迭代命题、generator/validator 与 checkpoint 复核；仍需真实模型、大测试集体验和跨 Java 恢复 | 后端+Java接口负责人 | AI-10；Java保持原运维 |
| BANK-01 | P1 | 录入后自动解题/验证、多人题集/缺题拼接、纠错版本、去重撤销和标签治理 | 后端+前端 | AI-06–09 |
| MEDIA-01 | P1 | IndexedDB重传、缺片、回放时间线、对象存储/配额/保留/隐私流程 | 前后端+运维 | AI-18；重要部分随INT-01升级为P0 |
| OPS-02 | P1 | 单一制品、受保护发布、配置漂移、独立Worker托管和观测告警 | 运维+前后端 | AI-20 |
| ADR-01 | 待决策 | 明确是否恢复MCP自主工具、采用何种领域历史模型及分模型策略，记录取舍 | 技术/产品负责人 | AI-02/03/10 |

以上待办必须保留“实现”和“验证”两个栏目的证据。不能把尚无真实结果的需求，仅改成“已实现待配置”而关闭。

## 7. 验证证据与环境状态

以 7.1 的本轮最终收敛结果为准；早期 47/59/109/143/211/230 等计数保留在历史会话，不继续作为当前结果。测试命令和数据前提见 [开发验收流程](../../sduoj-autolab/docs/AI_BACKEND_DEV_ACCEPTANCE.md)。生产迁移/灰度和真实模型验收未执行。

最初 5 个课程/座位失败来自旧测试夹具与当前接口不一致，修正的是测试。后续 AI 管理页重复弹窗、未连接 Form 和 crypto.randomUUID 不可用、验收状态过滤等问题有源码修复和专项回归，不能与旧夹具问题混为一谈。

dev 验证记录使用带 AI-DEV 标记的题组与本地专用账号。凭证位于 ignored 私有 dev 目录且权限 0600；本轮未将它写入文档、模型输入或 Git。原有 A+B 题只读，新测试点引用/提交写入本轮新题。

本轮没有生产写入/发布、Nginx/Nacos 修改、付费模型调用、长期 Worker 启动或旧数据退役。独立 MySQL 测试使用临时容器；Web2 保留原 3000 服务，新检查使用 3012。

### 7.1 2026-09-06 最终收敛证据

- 后端快速全量：245 passed / 12 skipped；跳过项是 MySQL 专用锁/强退用例及 Docker opt-in。
- 独立 MySQL 全量：230 passed / 9 skipped（此前代码快照）；随后对文档幂等及完整迁移变更另跑 101 项 MySQL 专项通过；不能将不同时间结果拼成一次全量结果。
- 真实容器/命题专项：16 passed，其中 8 项四语言/JPlag、1 项 generator/validator/标程真实执行，其他 7 项为命题接口夹具。
- 本机真实 OJ：题组 198/199/200，程序题 SDUOJ-1813，submission c45f8fec28db00d，Accepted/100/10 checkpoints。报告仍位于 ignored 的 data/dev/ai-integration/report.json。
- Web2 AI 专项：22 suites / 66 tests 通过；覆盖页面/API、路由/导航、管理菜单、账户/标签、考务、批阅、IDE 和上下文预填。考务/批阅仍可能输出 AntD/jsdom act warning，但测试通过。
- 新增真实 dev 浏览器检查 tests/local/ai-workspace.spec.ts：3/3 通过。9 个工作区用真实 OJ 登录和 API 加载，检查 1440px/390px、旧管理入口上下文和真实 Gateway SSE 创建/取消；题库 native 浏览器配置 1/1 通过；题目录入夹具曾受开发服务依赖安装影响，已修复依赖与类型检查。页面加载不等于各业务模型闭环。
- API 机器契约：91 路径，13 扩展表；Web2 JSON 请求合同 141 路径，其中 62 条 AI 请求。
- 2026-09-06 前端审计发现的重复弹窗、useForm 警告、路由资格边界、缺少考务/批阅/IDE测试、验收终态筛选、标签治理和协作缺口均已有对应本轮修复/实现；不继承审计之前的旧缺口或假定已有真实业务 E2E。
- release 配置现在必须从环境读取服务凭证，移除旧源码中的硬编码。dev 配置保持原样；生产应用新制品前必须填写 templates/systemd/autolab.env.example 对应环境，Web unit 保留直连 Gateway peer。
- 真实付费模型、摄录硬件、历史生产导出迁移、生产 Nginx/Nacos/部署/回滚均没有执行。本轮没有访问或写入生产。

## 8. 里程碑与完成标准

| 里程碑 | 当前状态 | 通过条件 |
| --- | --- | --- |
| M0 共享基线 | 本文已建立 | 前后端使用同一正文、编号和证据口径；旧方案不再误作当前进度 |
| M1 后端可运行 | 未完成 | 实际模型/执行器配置、真实任务消费、费用和隔离验证，阻断错误有明确反馈 |
| M2 核心教学闭环 | 未完成 | Web2录题/检索/问答、任务观测、批阅采用、停用和费用在真实数据夹具下跑通 |
| M3 完整替换验收 | 未完成 | 20条能力线逐项有完成/调整归属记录，尤其面试、查重、考务和资料格式不再缺关键环节 |
| M4 迁移与灰度 | 未完成 | 身份/账本/文件对账、单写入者、回滚、用户人工生产变更和业务观察窗 |
| M5 正式退役旧线 | 未完成 | 业务负责人验收、恢复演练通过、旧服务/队列安全停用、历史可追溯 |

推荐近期顺序：先 BE-01/RUN-01/SEC-01 与 QA-01，完成真实模型与生产边界验证；再把已接上下文入口的隔离工作台完整嵌入原批阅、题库、课程和任务页面，并进行真实用户角色回归；面试、正式考试、完整查重和数据退役各自满足专项门禁后启用。

## 9. 维护规则与变更记录

### 单一事实来源

- 正文归 sduoj-deploy/docs；Autolab/Web2文档入口不复制正文。
- 当前共享在本机并列检出目录中生效，本轮没有提交或推送。跨仓库相对链接按这一目录约定解析；独立检出或发布到 Git 网页时，应同时提供共享仓库的正式文档地址/固定修订链接，不能把本机共享误写成远端已发布。
- 本文负责跨端进度/逻辑/差距；后端 OpenAPI负责机器契约，专项实现文档负责操作细节，生产发布记录负责实际上线状态。
- 前后端独立仓库提交时，在本文记录各自 commit/PR；当前未提交变更必须注明“工作树”，不能用 HEAD 冒充实现版本。
- 旧原型、旧部署方案和旧截图保留历史标签，不累加成当前完成率。

### 每次相关变更必须更新

1. 更新对应 AI-xx/FE-xx/待办编号的状态、实际逻辑及剩余差距。
2. 填写后端/前端修订、接口变更和是否需要数据迁移。
3. 添加测试命令、时间、环境、结果和证据位置；标明 mock/真实依赖。
4. 改动响应字段/状态机时双方确认契约；前端等待项不能被后端单方面标“完成”。
5. 部署后另补目标主机、制品、配置/迁移版本、验证和回滚记录。代码合并不自动变成已上线。
6. 多个任务同时编辑时按编号维护相应段落，冲突以最新源码和测试证据解决，不整份覆盖旧快照。

建议变更记录格式：

| 日期 | 变更编号 | 端/负责人 | 修订/PR | 实现变化 | 验证证据 | 剩余项 |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-09-06 | BACKEND-P0-003 | 后端 | 工作树 | 双身份头/CIDR fail-closed、Worker 首尾再授权、墓碑显式恢复、有界孤儿文件审计/清理；同步 91 路径/13 表契约 | 245/12 快速全量、230/9 MySQL 快照、真实沙箱与 dev OJ、发布工具契约校验 | 真实模型、预生产 peer/权限矩阵、源生命周期与生产门禁仍开放 |
| 2026-09-06 | FRONTEND-AI-001 | Web2 | 工作树 | 10 条 AI 路由记录、9 个工作区入口、API client、隔离工作台、路由边界、账户/标签管理、旧管理入口上下文和页面测试 | 22 suites/66 tests、全站 Jest 77/365、真实工作区 Playwright 3/3、题库 native 1/1、tsc 通过；题目录入夹具未稳定 | 真实模型/媒体/角色回归、旧页面完整融合和生产门禁仍开放 |
| 2026-09-05 | BACKEND-DEV-002 | 后端/独立页面 | 工作树 | 原生三类题库、持久调用账务、输入/历史、PPTX/RAG、沙箱/JPlag、批阅、考试发布绑定、配额 | 第7节、开发验收流程 | 真实模型、隔离工作台旧入口集成和生产门禁仍开放 |
| 2026-09-05 | BASELINE-001 | 共享文档维护 | 工作树审计 | 首次统一历史原型、Autolab实现、Web2契约准备和生产门禁 | 本文第7节 | 第6节仍开放 |

后续负责人实际姓名、排期和接受标准由项目负责人分配；本文没有向其他任务发送工作指令，也没有建立定时自动维护任务。保持更新依赖上述提交/验收流程。

## 10. 源码与文档索引

| 类别 | 入口 |
| --- | --- |
| Autolab集成说明 | [auto-task-ai-integration.md](../../sduoj-autolab/docs/auto-task-ai-integration.md) |
| API机器契约 | [auto-task-ai-openapi.json](../../sduoj-autolab/docs/auto-task-ai-openapi.json) |
| SQL参考/迁移 | [SQL](../../sduoj-autolab/docs/sql/20260905_auto_task_ai.sql)、[migrate.py](../../sduoj-autolab/auto_task/migrate.py) |
| 新路由/原生动作 | [auto_task_ai.py](../../sduoj-autolab/server/auto_task_ai.py)、[auto_task_actions.py](../../sduoj-autolab/server/auto_task_actions.py) |
| 类型和数据 | [ser](../../sduoj-autolab/ser/auto_task_ai.py)、[entities](../../sduoj-autolab/auto_task/entities.py) |
| 测试 | [test_ai_backend.py](../../sduoj-autolab/tests/test_ai_backend.py) |
| Web2旧任务页 | [AutoTask.tsx](../../sduoj-web2/src/Component/problemSet/AutoTask.tsx)、[AutoTaskFramework.tsx](../../sduoj-web2/src/Component/common/AutoTask/AutoTaskFramework.tsx) |
| Web2请求与契约 | [c-api](../../sduoj-web2/src/Utils/API/c-api.ts)、[validation](../../sduoj-web2/src/Config/validation/autolab.json)、[exporter](../../sduoj-web2/scripts/export-autolab-contracts.py) |
| 本机原栈环境 | [DEV.md](../DEV.md) |

原 Problem Stack 参考位于本机 /Users/yhf2000/Documents/Codex/2026-09-04/wo/work/lixi-ai-tutor：docs/education-platform-requirements.md、docs/ai-interview-design.md、docs/testing.md、docs/adr-001-workflow-and-workspace.md，以及实际 lib/app 源码。本机路径不是生产部署版本；后续应将需保留的需求基线按版本归档到共享仓库。
<!-- Current verification note: the latest local backend run is 245 passed / 12 skipped; Web2 full Jest is 77 suites / 365 tests, AI workspace subset is 22 suites / 66 tests, and the real workspace Playwright check is 3/3. The question-intake fixture is intentionally not counted as passed until its Ant Design Select timing is stable. -->


### 2026-09-13 本机开发恢复补记

本机 Docker 栈与 Web2/Autolab/独立 Worker 现已运行。真实消费发现并修复 Java 内部 RPC 的 userId/groups 字符串 ID 适配，身份专项 38 passed；真实队列和 Docker 沙箱四语言运行通过。9 个工作台已进行真实登录页面加载检查。模型仍未配置，不能据此关闭 BE-01 或 M1 的真实模型门禁。详情和启动方法见 [本轮记录](DEV_SESSION_20260913.md) 和 [DEV.md](../DEV.md)。此前环境快照中的“Worker 未运行”不再代表当前运行状态；历史测试数字保持其原验证日期和范围。
