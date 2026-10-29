# 本人端点用量 dev 验收

2026-10-19。AutoLab `bfbb295` → `b0d3721`、`98cd585`、`dca6d90`；web2 `7392903`、`a82cbee`。承接 [24](24-首批组件与真实模型浏览器dev验收.md)，本次接通现有账本到本人端点用量弹窗。仅 dev、本地小提交；不 push、不改生产、schema、Java、角色、模型出口或发布链，本轮没有真实模型调用。

## 已实现

`GET /auto-task/ai/ports/{id}/usage?offset=0` 沿用 `cover_header` 和 `own_port`，仅原端点属主可读；superadmin 不因角色获得他人详情。端点停用、没有默认、价格未知或账户暂停时仍可查本人历史，不依赖组件开关或积分。删除端点仍返回 404。GET 不解密 key、不访问提供商、不 upsert 账户、不写账本或取得行锁。

返回 UTC 当月的请求数、完整 token、已结算估价、running/unsettled 预留、当前端点月预算及剩余估算；明细按创建时间和 ID 倒序，每页 20 条，offset 最大 1000000。当前 pending/running/blocked 任务、running/unsettled 请求另按全部月份计数；账户有其他待对账请求时也显示原阻断状态。模型名取历史请求，变更当前模型/费率不会重算旧记录。

金额以十进制字符串传递，保留小于十亿分之一美元的预留，不经前端 Number 四舍五入。未确认 usage 的 token 为 null，不能显示成已确认零值。字段投影不返回 payload、原 usage、provider 错误、session_id、key 或密文。坏账本返回固定 503，不编造零费用。

独立审计发现 `bfbb295` 的 P2：它过滤错绑 owner/payer 的历史 AiRun，但原预算权威按端点全部 AiRun 计入，可能显示有余额却无法调用；未来月份异常记录也有同类差异。`b0d3721` 不修改结算规则，对错绑/孤儿或未来月记录固定 503，不泄露其他任务或给出错误预算。最初 needs_fix、旧代码两个失败反例均保留。

前端“我的模型端点”增加显式“查看用量”，只在用户打开/翻页/刷新时读取，不自动探测模型。弹窗显示账本估价说明、UTC 月份、待对账提醒、请求本地时间到分钟及分页。服务端数据进入既有 Redux；subject/权限 epoch、端点版本、请求 ID、offset 共同拒绝账号/角色 ABA、关闭/重新打开、刷新和翻页后的旧结果。请求失败立即清旧金额；端点版本变化需先刷新列表。

## 验证与审计

- 后端最终定向 60 项通过、3.03 秒，含随机自有 MySQL 十进制/月界验证；不是模型或准入证明。独立 exact archive 60 项通过、3.04 秒；原预算权威反例旧提交 2 项失败、修复后 2 项通过，另 6 类异常在真实 MySQL 通过。
- `98cd585` 在原 Gateway/Java/MySQL/Redis 与 Linux worker/SDK 组合中读取实际生成账本：取消后未知 token/待对账，原零 token 人工对账后，同一 worker 执行六步新任务，读取七条完整记录（六 success、一 reconciled），无残留队列。主验收 1 项通过、20.15 秒；独立 exact archive 1 项通过、17.70 秒。模型仍是合成 broker；不把已知零 token 对账推广为真实供应商取消。
- 前端 client/Redux 原 51 项通过；独立增加合同、精度、DTO 和竞态验证，共 100 项前端通过，另一个后端 SQLite DTO 导出测试通过。TypeScript、目标 ESLint 均通过。SQLite DTO 只证明合同，真实金额验证另列于上。
- 页面与相关 client/Redux 最终六 suites、75 项通过，25.482 秒；页面独立 exact archive 17 项通过、8.675 秒，包括分页失败按原 offset 重试、双端点晚响应和版本/主体 ABA。目标 TypeScript、ESLint、格式检查通过。日志保留 React 异步测试 act warning。
- 当前后端完整 `pytest tests`：1013 通过、22 跳过、0 失败，90.43 秒，父进程退出 0。被测工作树为 `b0d3721` 产品和 `98cd585`，加已在树中的最终 `dca6d90` 显式 harness；随后仅提交该文件，无源码改动。显式浏览器 harness 默认不收集，不计为全量新增通过。

最初页面测试有 5 项在 AntD 打开动画结束前检查可见性而失败，改为等待可见后通过；随后联合运行一次既有“重试原请求”测试超时，单独运行 1 项通过，最终六 suites 75 项通过。原失败日志保留，不回填旧结果。首笔根会话 54 项日志被外部启动脚本复用覆盖，终端输出及独立审计的 54 项原始日志仍保留，不宣称原根日志还在。

`bfbb295` 独立审计为 needs_fix；`b0d3721`、`98cd585`、`dca6d90`、`7392903` 和 `a82cbee` 分别独立 accepted。显式浏览器 fixture 另有 9 项离线 guard/种子/退出测试通过，未把 fake process 或 SQLite 种子检查当成真实浏览器验收。

## 实际浏览器

web2 原 webpack → Gateway → Java 登录 → 自有随机 MySQL 的实际 API，无浏览器 route mock。`dca6d90` 明确种入 23 条合成历史账目（22 settled、一 unsettled），不启动 worker 或模型；实际生成账目链已在上方独立证明。

Chromium 完成停用端点查看、待对账与未知 usage、20/3 分页、返回上一页、关闭并重开回到第一页。显示 settled USD 0.022000000、预留 0.005、剩余 19.973000000；只是种子账本，不是真实 provider 费用。桌面宽 1280，文档宽 1280、弹窗 900、body client/scroll 均 852；375px 下文档宽 375、弹窗 359、body client/scroll 均 311，无横向溢出。登录后本页交互无新 page error，既有开发依赖 warning 保留。

浏览器控制 fixture 1 项通过、383.33 秒，父进程退出 0；这段时间含人工 CLI 操作，不是接口延迟。原 webpack 首编译 12.054 秒、2 项体积 warning、无 TypeScript 错误。关闭浏览器、删除临时 storage state、将 CLI 记录移至仓库外后，临时 5005/3016 均释放，webpack 正常退出 0。原 dev 容器未重启或重配。

本机仓库外 `platform-v2-implementation-20261018` 保存 `port-usage-backend-final.log`、`gateway-linux-worker-port-usage.log`、`port-usage-web-combined.log`、`port-usage-full-sdk-mysql.log`、`gateway-usage-browser.log`、`usage-browser-20261019/{browser-result,result}.json` 与 `audit-port-usage-*`；原失败、needs_fix、修复及监控记录均保留。截图在 web2 忽略的 `output/playwright/usage-*.png`。16 份日志/CLI/控制 JSON 对真实测试 key、dev 密码、RPC token、MySQL/Redis 密码扫描，0 命中。

## 后续范围

本人用量不是全站运营视图，也不是模型能力探测结果。继续经预算确认的受控探测、脱敏运营列表、剩余 12 组件及前端治理接入、原生 MySQL 锁矩阵、Linux amd64/完整 Web 和最终制品验收。账本页为读时快照，不承诺后续调用获得相同剩余额度或并发槽位；最终准入始终由原事务预算权威决定。原 48 项任务不批量改 done。
