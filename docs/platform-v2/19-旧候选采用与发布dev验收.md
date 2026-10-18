# 旧候选采用与发布 dev 验收

2026-10-19，承接 [18](18-历史worker执行边界dev验收.md)。仅 dev 和隔离测试；本轮没有真实模型调用、push、生产写入或组件启用。此前已获准的第一阶段提案明确要求旧入口、完成和采用重核，以下不新增角色、schema、凭据或沙箱权限。

## 实际行为

| AutoLab 提交 | 范围 |
| --- | --- |
| 49b682c | 服务器资源 kind 决定旧候选类型；旧 grading/interview/authoring 和未知类型不能批准。原生评分与访谈评分在原来源/答卷快照/手工覆盖检查之后、实际写入之前拒绝未适配候选；exam/plagiarism 的确定性审阅保留 |
| 52f45f0 | test-only：访谈手工评分竞争改用现有随机自有 loopback MySQL fixture，测试确实到达“答卷自邀请后变化”的原检查，不以适配器拒绝代替竞争验收 |
| bfddebb | 修复独立审计发现的相邻问题：通用 review 的接受和拒绝均不能改写 adopted 历史，保留原 ACL/CAS 先行 |
| e40a78c | authoring native-plan/native-finalize 及通用 program-plan/bind 的 authoring 分支在 Java/文件读取前拒绝；写事务再次检查。人工 question 编程题发布保持原路径 |

候选 JSON、旧任务 task_type、harness、port_id、validated/approved 状态或组件开关不能把旧结果变成已绑定的 SDK 候选。旧完成限制不能替代采用检查。新普通文档候选仍走已有完整来源/当前策略/本人端点/结算/receipt 检查，不复用此旧候选豁免。

未采用候选仍可按原权限拒绝清理；已采用历史保持不可变，原已采用评分和已完成出题 publication receipt 只读重放保留。历史读取、出题包导出、手工题库、手工 Java 编程题发布和确定性考务/查重未整体关闭。通用 program bind 继续检查原发布者、statement、marker、题组类型与权限，不因为保留手工路径而允许旧 authoring 候选旁路。

native-finalize 原 checkpoint 文件/hash、顺序/分值、judge template、公开样例与原发布者检查提取为私有只读 verifier。其成功证明制品检查函数的行为，不证明旧 AI 发布可执行，也不证明新的 SDK 出题组件已实现。当前旧 API 正向发布测试改成明确拒绝，制品检查用直接函数回归保留，没有全局 mock gate、恢复 raw provider 或 debug 绕过。

## 测试与审计证据

- 49b682c 主测 163 通过、2 跳过。独立 exact SHA 回归 158 通过、3 跳过，但外置反例失败：通用拒绝能将已采用访谈改成 rejected。该提交的审计保留 needs_fix，不能单独视为最终可用版本。
- 52f45f0 主测真实随机自有 MySQL 8 通过、3.11 秒；默认 SQLite 7 通过、1 跳过。独立 exact SHA 分别 8 通过、3.03 秒和 7 通过、1 跳过，审计接受。仅测试 fixture/断言变更，不宣称测试模拟了完整网关或真实模型。
- bfddebb 主测相关回归 140 通过、2 跳过；独立 exact SHA 156 通过、2 跳过、5.69 秒。原外置失败反例转为通过，另外两项验证历史 GET、原 ACL/CAS 及数据不变，审计接受。49b682c 的初始记录未覆盖。
- e40a78c 主测相关回归 169 通过、2 跳过、5.24 秒，包含旧出题四入口、原权限、历史 receipt、制品字节/十类不一致和手工编程发布正反例。独立 exact SHA 审计 184 通过、2 既有跳过、6.18 秒；外置四项反例通过、0.38 秒，覆盖原 CAS、禁止通用编辑注入回执、历史 receipt 精确正文与当前 owner ACL 后才重放，审计接受。
- e40a78c 完整 tests，启用随机自有 MySQL 和真实 SDK 解释器：**977 通过、16 跳过、0 失败，86.27 秒，退出码 0**。独立运行监控保存退出结果，没有把定向套件数量相加。

16 项跳过：真实提供商两项显式关闭；真实 authoring 容器一项、其他本地容器九项未启用；旧固定 MySQL 锁测试一项、旧 schema 专用数据库配置三项未启用。上一检查点的 17 项中，访谈手工评分竞争现已在自有 MySQL 运行。SDK/MySQL 联合用例中的身份 RPC 和 Responses 供应商仍有 fixture，不等同于真实 Gateway/Redis/Java 身份业务链。SQLite Decimal 警告也不作为真实 MySQL 精度验收。

当前任务 work/platform-v2-implementation-20261018 保存 legacy-candidate-initial.log、legacy-candidate-interview-mysql.log、legacy-candidate-interview-sqlite.log、legacy-candidate-immutable-fixed.log、authoring-publication-final.log、candidate-boundary-full-sdk-mysql.log 和 candidate-boundary-full-monitor.md/json。独立证据为 audit-legacy-candidate-admission、audit-interview-mysql-fixture、audit-adopted-review-immutable、audit-authoring-publication-gate 的 md/json/log；初始失败和修复后报告分开保存。

## 下一步

以上关闭已定位的旧候选写入入口，不代表全体业务组件已迁移。继续真实 Gateway/身份 RPC/Redis、Linux 安装、浏览器与取消恢复整链，之后按组件逐步适配。INSTALLED_COMPONENTS 仍为空，原 48 项任务不改 done，当前不能启用为发布候选。专用测试端点“免费但限量”的授权持续有效，本轮未消耗其额度，其他端点不得自动按免费处理。
