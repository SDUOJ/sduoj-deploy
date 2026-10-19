# 主观批阅：历史读取与前端合同 dev 验收

2026-10-19。本批继续已批准的原生主观批阅适配，仅本地 dev 和合成资料测试，没有 push、生产写入、新 schema、Java 或构建链修改。批阅组件仍未登记 installed，不能在 M 端开启；本文不宣称整项批阅交付。

## 当前权限与历史争用

通用 saved grading 历史读取同样必须是当前原题单教师：拥有旧快照不允许已撤权但仍属学生组的用户继续读取答卷。原 `bb92676` 修复该绕过后，审计发现多资源读取按不同历史顺序累计锁，会触发跨题单 InnoDB 死锁。该历史结论保留，后续修复已通过独立复审。

| AutoLab 提交 | 范围 | 证据 |
| --- | --- | --- |
| `7737228` | 仅增加六项真实 MySQL 反例 | 根及独立归档均 6 FAIL：跨题单 1213，以及五类原生行争用 1205 |
| `0e4ae11` | saved grading 当前读对所有原生锁使用 NOWAIT；争用返回整页 409 | 同一六条测试未修改转绿，相关 107 PASS；独立复审 213 PASS、1 既有 opt-in SKIP |
| `1c108cb` | 原 TaskJob 的教师本人历史投影 | 根相关 49 PASS；独立 84 PASS，含真实 owned MySQL/HTTP |

新历史读取保留当前 InnoDB 读和原教师权限，争用时回滚整个列表事务。独立测试专门让第一条资源已完成授权、第二条的任一原生行被占用：真实 HTTP 返回 409，不含半页或答卷内容；在占用者仍未释放时，已证明前面资源的锁已释放，重试可读完整两行。原 worker/人工采用的默认原生读取仍等待提交，不被批量改成 NOWAIT。非 grading 的原读取语义保持。

`0e4ae11` 整个后端回归为 **1374 PASS、25 SKIP、983 warnings、141.09 秒、退出 0**，启用真实 SDK 解释器和自有随机 MySQL。provider/Gateway/容器等 opt-in 跳过不计通过。此结果只属于该 SHA，后续历史接口及 capability 增量的完整结果另记。

## 给前端的最小读取合同

新增两个 GET，经原登录身份、当前教师 ACL、本人任务/资源、原 legacy TaskRun 存活及原生来源绑定检查：

- `/native/grading/resources/{resource_id}/tasks?page=1`：每页 20，稳定按创建时间和 ID 排序。
- `/native/grading/tasks/{task_id}`：固定 component/action、状态、attempt、UTC 时间、has_error 和成功候选引用。

两个入口不暴露 worker payload、原日志、provider 错误正文或端点配置。成功任务仅投影 canonical 候选 ID/hash/version；候选详情和采用继续走既有 typed grading 接口。历史可在组件或端点关闭、材料后来变成附件时读取；这不重新放开创建、模型调用或采用。

## 前端类型化接线

| web2 提交 | 范围 | 验收 |
| --- | --- | --- |
| `3f84e83` | 原 request facade 下的预览、创建、saved source、任务历史、候选、采用与取消客户端 | 根 59 新测试 + 36 旧文档客户端测试通过；tsc/ESLint 通过；独立 119 PASS 及精确后端 ASGI 合同 6 PASS |
| `6eb596d` | 原 Redux 的 grading 读取 slice 与 rootReducer 接线 | 根 75 相关测试及 tsc/ESLint 通过；独立原 81 PASS、另 13 边界 PASS |

客户端区分原生主键与学生位置，拒绝不安全 JS 整数和未支持的输入格式；绑定来源 hash/version、任务、attempt、动作、候选和回执。保留空白文本答卷、合法 `-0` 及极小 rubric，不把评分建议和 feedback 混用。未知结果重试所需创建/采用字段有明确类型；不调用旧 edit/adopt 或通用 retry。原 GET facade 使用其实际参数合同。

Redux 只存已投影的页面数据，不存原 provider 错误。本人、username、角色或组变更会推进 epoch 并清除旧答卷；乱序请求、旧主体恢复后的迟到响应、不同 kind/ID 及重复终态均不能覆盖新读取。独立测试还实际触发原 LoginCheck 认证边界事件，确认私有缓存清除。

## 开关与教师发现

AutoLab `ac7f522` 增加 scoped grading capability hint：原 PS owner、manageGroup 或 superadmin 不需要全站 admin；普通 admin 仍不能替代题单教师。用当前 PS 行验证权限，仅给有本人可用端点及有效依赖的动作标 can_start；不解密、不调用 provider、不暗选共享或默认端点。未安装或关闭的批阅组件不额外锁原生行。

根六套回归 90 PASS，包含真实 MySQL 旧 RR/identity map 下的撤权及占用返回 409；此前五项缺失提示失败和组件未安装仍取锁的失败记录保留。独立审计又复现了共享旧流程的锁反转：resource scope 先取得 native PS，再对隐藏 internal/批阅组件重复申请 resource write 锁，与原 worker 资源 → native 的顺序相反。父 `1c108cb` 也失败，不称为本批新行锁引入的回归。

后续 `9db09b9` 只增加确定性交错测试，根先得到 worker 的 1213 断言失败；`2beac1b` 保留当前教师 write ACL，跳过 grading 已完成的二次资源 write 检查及不可见组件的无用写锁。相同测试不改转绿，相关七套 91 PASS。可见的非 grading 管理组件仍保留原 resource write 权限检查。两笔独立复审已重现红绿且无新阻塞，最终报告另行保存；原 `ac7f522` needs_fix 结论和 1395 PASS/25 SKIP 记录保留，不作为反例通过的证据。

最终 clean AutoLab **`2beac1b`** 的整个后端回归为 **1396 PASS、25 SKIP、1017 warnings、137.89 秒，父进程退出 0**。启用真实 SDK 解释器与 owned MySQL，未启用 provider/Gateway/容器等专用环境的 25 项测试不计通过。前端 `6eb596d` 本批只有具名定向回归及独立审计，未重跑全前端或浏览器，不能把后端全量结果用于前端交互。

hint 只用于渲染，最终预览、创建、worker 和人工采用仍各自校验。

## 当时尚未完成的业务出口

本检查点的旧 `GradingWorkbench` 尚未接入新客户端/Redux；以下 1–5 已在后续 [34](34-主观批阅工作台dev验收.md) 接线，组合验收仍待完成。本检查点不把类型声明或 reducer 算作交互完成。当时计划为：

1. 原生来源预览与再次确认、本人端点选择，grade/feedback 分开呈现。
2. 当前任务恢复、取消后重读、未知创建/采用结果的精确原请求重放；不能自动换 key 新建任务。
3. 候选与冻结题目/答卷/rubric 对照，当前教师另行确认；已有手工成绩/评语须明确勾选覆盖，feedback 不改分数/锁。
4. 旧历史保留只读展示；未支持的附件格式明确提示，不能把无法解析的资料转换成空答卷。
5. 复用原题单教师入口或独立客户端工作台，不放宽整个 M layout 的 admin 边界；所有读取继续由后端原教师规则授权。
6. 补真实 Java/Gateway 身份、浏览器、SDK/提供商与合成教师冻结集的组合验收，再考虑 installed 登记。默认开关保持关闭。

完整任务状态仍见 [31](31-全平台进度与后续批次.md)。本批没有完成出题平台、查重或考务任务，也没有缩减其原计划和 DAG。

## 仓库外证据

WORK 保留 `grading-history-lock-red/green.log`、`grading-history-red-green.json`、`grading-history-backend-full.log`、`grading-history-api-red/green.log`、`grading-client-contract-red/green.log`、`grading-redux-tests.log`、`grading-capability-*.log`、`grading-capability-worker-red-green.json` 及最终 `grading-capability-worker-backend-full.log`。独立报告包含 `audit-grading-history-contention-tests`、`audit-grading-history-lock-fix`、`audit-grading-history-api`、`audit-grading-client`、`audit-grading-redux`、`audit-grading-capability` 的 `.md/.json` 和后续复审。收集/路径错误日志保留，但不计作缺陷红灯或覆盖证据；私有连接文件不入仓。
