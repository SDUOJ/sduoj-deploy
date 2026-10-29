# 主观批阅工作台 dev 验收

2026-10-19。继续已批准的原教师权限、本人端点和独立人工采用方案，只改本地 dev 前端及既有教师列表的原生引用投影；没有 push、生产写入、Java、schema、构建或默认开关修改。后端沿用 `2beac1b` 的批阅业务，新增 Gateway 测试 `9f6207c` 和教师列表引用修复 `f318aef`，对应历史验收见 [33](33-主观批阅历史与前端合同dev验收.md)。

## 实现与提交边界

| web2 提交 | 单一目的 | 验收 |
| --- | --- | --- |
| `49426c8` | 旧批阅历史的只读公开投影 | 独立 100 PASS；实际后端旧 schema/教师 GET 合同 4 PASS |
| `17b0c20` | 当前 grading 读取失败时清除全部私有读取及 pending key | 根 1 FAIL → 9 PASS；独立 16 项及既有 82 项通过 |
| `af6258b` | 工作台接入 typed API、原 Redux 与原异步 Task 工作流 | 根 103 PASS；独立审计发现后续作用域刷新缺口，原 needs_fix 结论保留 |
| `ac56204` | 原题单教师使用客户端入口 | 根及独立 4 FAIL → 68 PASS；独立实际 lazy 路由额外 6 PASS |
| `5f487b9` | 能力提示变化后重新验证原生读取权限 | 根及独立 5 FAIL → 5 PASS；整个 grading 定向 108 PASS，独立追加后 112 PASS；复审 accepted |
| `689df0c` | UI 测试等待异步创建前置检查完成 | 27 PASS；不放宽业务断言或增加等待上限 |
| `1ee621a` | portaled 确认弹窗的窄屏按钮换行 | 390px 英文真实浏览器断言 FAIL → PASS；27 项页面测试通过 |
| `6e0056e` | 根 store 的 grading 退出隔离验收 | 父提交独立 1 FAIL、30 PASS；新测试含实际私有缓存预热、epoch 递增和迟到拒绝，40 PASS；不改 reducer |
| `2e33ae1` | 端点权限测试与弹窗装饰动画解耦 | 故意暂停 RAF 时原夹具 1 FAIL；真实 Modal/Form 保留，只移除该夹具 transition，13 PASS；该 SHA 全前端 186 套/1529 项全通过 |
| `23f7d54` → `5722e04` | 行内辅助入口只使用明确原生引用，原手工批阅继续使用下标 | 原实现 11 FAIL，修复后 11 PASS；含工作台/客户端合计 97 PASS，独立额外 17 PASS；两提交独立审计 accepted；该 SHA 全量 1539 PASS、1 FAIL，唯一失败在既有提交导出夹具 |
| `e2eece0` | 全局提交测试等待异步动作结算后再导出 | `5722e04` 原全量出现导出 0 次的断言失败；仅测试改 async act，新增 pending 重测期间不导出用例，4 PASS；独立审计 accepted；该 SHA 全前端 187 套/1541 项全通过 |

每笔提交分别审计。失败必须来自目标行为断言；夹具、路径、类型检查及未完成的测试不计红灯。`af6258b` 中已采用候选仍提示未采用的文案先用独立断言复现，再修正；历史日志保留。

## 页面行为

新任务先预览原题目、文本答卷和 rubric，教师明确勾选已核对；创建前重新取原生快照并比较 hash，重新检查本人端点的有效性和配置版本。未设置默认端点不会暗选第一项，不使用共享模型兜底。grade 与 feedback 分开，不支持的文件/OCR/视觉输入继续拒绝。

历史可恢复本人来源、任务动作、状态、创建时间及候选；取消后重读原任务，不自动新建。创建或采用结果未知时仅重放冻结的原 body 和 operation key，不自动换 key。未确认的候选不会写正式成绩；教师在弹窗对照冻结来源、建议和复核理由后再确认。已有人工成绩或评语需要单独勾选覆盖；feedback 的后端合同仍只更新评语。

来源、建议和旧评语按纯文本显示，不执行 HTML 或读取资料中的外链。旧记录保留只读展示；缺失、超限或附件类型明确不可展示，不能转换成空答卷。真实空白文本答卷独立标记。

使用 devOnly 的 `/v2/workspace/grading`，原题单快捷入口继续依据 `problemSetInfo.isAdmin`；旧 `/v2/ai-grading` 保留 query/hash 并跳转新入口。全站 MLayout 的 admin/superadmin 限制未放宽。生产构建不注册该客户端路由，也不显示题单快捷入口。客户端入口本身不授予题单权限，后端每次读取与写入仍校验当前原教师 ACL。

## 权限刷新反例与修复

终态任务停止业务轮询后，能力提示可能返回失败或隐藏动作，旧私有答卷却仍在页面上。这与账号/组变更的 epoch 清理是两个独立场景；仅禁用采用按钮不足以验证材料读取权限。

修复按能力请求 ID 对当前来源和仅预览来源各重读一次原生接口。真正的读取失败沿原 Redux 请求协议清除全部材料并关闭确认框；迟到的旧主体响应仍拒绝。能力查询失败、组件关闭或端点停用本身不等于撤销历史读取：原生接口仍允许时保留历史。读取期间保留选中来源的 PS 绑定，避免临时 loading 导致 scope 在 navigation/PS 间循环切换。

新增五项回归在父实现全部失败，再在修复后通过，覆盖终态权限失效、预览阶段撤权，以及能力错误/组件关闭但原生接口仍授权。最初仅依据能力失败就要求删除历史的独立反例过强，已由权威原生读取结果替代，原报告和失败记录保留。

## 教师列表的显示位置与原生引用

原 `get_judge_list_by_psid_page` 返回的 `gid/pid` 是显示下标；第一行可能为 0，后续正整数也不能按主键解释。直接将其传给新工作台，会拒绝零值或选择错误对象。AutoLab `32f65e9` 先加实际 SQL 投影回归，2 FAIL；`f318aef` 仅增加 `native_ref={psid,gid,pid,username}`，其中 gid/pid 是原生主键，原字段及手工审核请求保持下标。三文件 131 PASS，独立追加跨题单、跨页、不同学生检查 2 PASS；两提交分别审计 accepted。该模型层测试不代替 HTTP 或 ACL 验收。

web2 `23f7d54` 在真实 Review 组件中先复现 11 项目标失败；`5722e04` 复用严格 `readGradingRef`，将明确引用与路由题单、原列表学生绑定。缺失、跨题单、跨学生、零值、布尔/字符串/不安全整数或额外字段时不显示行内辅助按钮，不回退到下标。原手工按钮仍用原 gid/pid。修复后相同断言通过，工作台/客户端合计 97 PASS，TypeScript/目标 ESLint 通过。独立审计在精确旧实现使用最终测试夹具仍得到相同 11 项目标失败，精确修复归档 97 PASS，额外 17 PASS 覆盖 safe integer 上限、Unicode 学生名、原 row 不变及实际 FeatureAction 的生产隐藏；两个提交分别审计 accepted。首次绿灯尝试因测试 mock 丢失 i18next 初始化接口而未加载测试，已保留并作废；修复夹具只补实际模块其余导出，不把该错误算作产品红灯。

## 真实 Gateway 的读取与默认关闭验收

AutoLab `9f6207c` 仅新增显式 opt-in 测试。经现有本地 Gateway 登录和真实 Java fresh identity RPC，调用原生 grade/feedback 预览；验证未写成绩、空文本保留、附件拒绝、错误关联/非整数引用拒绝、伪造匿名身份不能取得材料。保持实际 installed 集合未含 grading，创建返回 409，TaskJob/AiRun/孤立 grading 资源均未生成。四项全部真实执行通过；没有模型调用或身份依赖覆写。

测试只在 `mysql_target` 自动创建并清理的随机 schema 中写合成原生行，不选择现有业务 schema、不改 Java 角色、组件安装状态或生产配置。使用既有专用 dev 登录账号，此账号不等同于普通 USER 教师角色矩阵，也不证明独立 worker 或模型链。首轮把 Gateway 校验错误误期望为 422（实际为 400），仅修正测试后通过；该失败不算产品缺陷复现。

## 验证范围与下一出口

当前定向结果：工作台 27 项、grading 客户端/旧历史/reducer 合计 108 项；路由、release 隔离和原 MLayout 合计 68 项，TypeScript 与目标 ESLint 通过。浏览器使用本地 webpack 和合成 API，已检查普通教师历史、中文 390px、英文 390px 与 1440px 确认弹窗。英文窄屏原 dialog client 374px、scroll 512px，修复后均 374px，桌面均 520px；这只验证渲染布局，不证明真实身份或模型链。

`5f487b9` 的首次整前端运行在 31 套输出 PASS 后以 139 退出，未产生完整汇总，不算通过。macOS 诊断记录为 Node/V8 GC 的 SIGSEGV，不能由此认定某项测试失败或忽略未运行项；原日志保留。`1ee621a` 随后完成整轮：185 套/1527 项通过、1 套/1 项失败，退出 1。唯一失败是根 logout 兼容测试未排除新 grading 单调 epoch 的全 state 初值比较，不能把 reducer 改回清零来迁就测试。`6e0056e` 补充强于原比较的显式退出边界检查，定向及独立审计通过；`6e0056e` 整轮同为 185 套/1527 项通过、1 项失败，退出 1；logout 已通过，唯一失败是既有端点运营 role ABA 测试等弹窗可见超时。以暂停 RAF 的用例复现后，`2e33ae1` 仅修订该文件的装饰动画夹具，该 SHA 完整回归为 **186/186 套、1529/1529 项通过，0 失败、0 跳过，338.273 秒，退出 0**；起止源码一致且洁净。没有改产品或全局测试配置，也没有延长等待或删掉可见性/权限断言。

`5722e04` 完整前端回归为 **186 套/1539 项通过、1 套/1 项失败、0 跳过，348.61 秒，退出 1**。新增 Review 引用测试通过；唯一失败是既有全局提交测试在期待默认正式导出时，实际 API 调用为 0。`e2eece0` 只修正测试的异步动作等待，保留全部原断言和等待上限，另加受控 pending 重测的导出禁用与结算后恢复检查；不改产品实现。这是测试夹具修订，不能据此声称生产导出有缺陷，也不声称旧夹具在每个环境都会失败。独立精确父版定向 3 PASS、新版 4 PASS；deferred 用例显示“API 已调用”时动作仍可未结算，另将导出 includeTasks 注入为 true 后默认 false 断言真实失败。未确定性复现负载下 antd 内部 loading 窗口，348.61 秒的实际全量失败为原始记录，不由定向通过覆盖。

web2 最终 `e2eece0` 使用原 Node/Jest 命令完整回归：**187/187 套、1541/1541 项通过，0 失败、0 跳过，359.907 秒，退出 0**；起止 SHA 相同且洁净。此前各次未完成、失败及对应夹具修订分别记录，不删除失败历史，不把旧 SHA 的结果当新树通过。

AutoLab 最终 `f318aef` 完整后端回归：**1398 PASS、0 FAIL、29 SKIP，142.03 秒，退出 0**；启用自有随机 MySQL 与 SDK 解释器，起止 SHA 相同且洁净。29 项跳过为 Gateway 配置 12、容器 opt-in 9、隔离数据库配置 3、提供商授权/私有配置 2、authoring opt-in 1、MySQL locking 1、Linux worker runtime 1，均未算通过；四项真实 Gateway 专项已另行显式执行，不改变完整回归中未配置的跳过记录。

批阅组件仍未登记 installed，14 项注册组件默认全关闭。下一步仍需组合真实 Java/Gateway 身份、原 worker/Linux SDK、用户 Responses 端点与合成教师冻结集，验证创建、取消、确认采用、撤权、未知结果和失败恢复。纯 Jest、静态路由或模拟 API 浏览器不替代该出口；本页接线不意味着整项 S2-10 完成。

下一组合批次按顺序验证：真实普通教师/管理组教师/超管与无权用户；原 worker/Linux SDK 下 grade、feedback 和取消恢复；免费测试端点仅发送合成答卷；独立教师确认、覆盖已有手工成绩、来源变化及未知结果回执；最后用教师冻结集记录质量/偏差与费用，再决定组件 installed 登记。未放行格式及其他组件不随批阅接线开放。

全平台 48 项状态和出题、查重、考务原 DAG 不变，见 [31](31-全平台进度与后续批次.md)。

## 仓库外证据

WORK 保存 `grading-review-ref-red/green.log`、`grading-review-entry-red.log`/`grading-review-entry-green-final.log`、`grading-web-full-2e33ae1.log`、`grading-backend-full-f318aef.log`、`grading-web-full-5722e04.log`、`grading-web-full-e2eece0.log` 及对应 monitor 报告、`global-submissions-actions-green-final.log`、`grading-page-focused.log`、`grading-page-adopted-red.log`、`grading-route-red-first.log`/`grading-route-green.log`、`grading-scope-red.log`/`grading-scope-green.log`、`grading-page-scope-focused.log`、`grading-mobile-dialog-red/green.log`、`grading-mobile-dialog-dimensions-after.txt`、`grading-desktop-dialog-green.log`、`grading-gateway-native-first.log`/`grading-gateway-native.log`，及 `audit-grading-legacy`、`audit-grading-read-failure`、`audit-grading-page`、`audit-grading-route`、`audit-grading-scope-fix`、`audit-grading-preflight-test`、`audit-grading-dialog-layout`、`audit-grading-gateway-read`、`audit-grading-root-logout`、`audit-port-operations-transitions`、`audit-grading-review-reference-red/fix`、`audit-grading-review-entry-red/fix`、`audit-global-submissions-action-fixture` 的具名报告。初次循环实现的进程已终止，记录保留但不算验收；未提交私有配置。
