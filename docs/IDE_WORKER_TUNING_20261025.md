> 2026-10-26用户确认改为ARM64+cgroup-v2 dev/生产统一权限路线，见[统一权限验收](IDE_CGROUP_V2_SHARED_20261026.md)。本文R6 privileged dev证据保留历史范围，不自动升级为新权限验收。

# Online IDE Worker 修复与资源验收（2026-10-25）

本轮业务合同由用户确认：**500 在线、100 活跃输入用户**。300/500 活跃不作为本轮放行目标。仅修改隔离工作树和本轮 dev 容器，不改生产或其他会话服务。

**本轮结论：单Worker dev验收通过，采用4CPU/6GiB/1024PIDs、C/C++文档48、Java/Python文档32。** 两轮四语言完整API、四语言浏览器、20/50/100活跃、单Java Debug混合、Worker优雅恢复及自有Gateway回滚均已有通过证据。可推进生产同构的预发布验收；当前证据不作为直接全量上线或八副本容量证明。

证据目录：`work/artifacts/ide-worker-tuning-20261025/`。旧 R5 与所有失败结果仍在上一轮 evidence 目录；新记录不覆盖旧锁。

## Debug 原生失败的定位与修复

冻结旧 sandbox SHA256：`bd4b7cff93a4ba68d6844784ac5683fbf8a4e946f809d0d4404024d8fd3b298a`。从停止的 R5 容器提取后逐字节核对，ELF 为 AArch64、静态 GCC7.5/glibc2.27、包含调试符号。

1. 原模板、完整验收代码在 `network=none` 的离线命名空间中，C++/Java 共12次复现3次 SIGABRT，排除必须由 Nacos/Redis/SSH 故障触发的解释。
2. 直接套 live GDB 后8次均成功，说明该仪器改变了失败时序；它不作为修复证据。
3. 原 core 不完整，无法直接展开栈。诊断专用工件只将 `abort` 入口首指令换为 BRK，以保留调用者 LR，6次 trap 均有 `PC=0x426b48 <abort>`、`x30=0x41f3d8`，上一条指令为 `uw_init_context_1+516` 对 abort 的调用。该地址与 pinned binary 的 `__pthread_unwind → _Unwind_ForcedUnwind → uw_init_context_1` 路径吻合；旧 `RequireUsage` 在 wait4 后调用 pthread_cancel。诊断 BRK 工件及 `/run exec` 从未进入服务或发布候选。
4. 源码另有把块局部 timeout_args 地址传给 detached 线程、没有确认线程退出的生命周期问题。修复删除定时线程及 pthread_cancel，改由单一 wait4 所有者用 CLOCK_MONOTONIC 执行原毫秒截止、超时后 kill 并 wait4 回收；停止的子进程不再误当完成。
5. 原模板编译限制不放宽：Java CPU3000ms/real5000ms，C++ CPU5000ms/real7000ms。CPU/内存/输出结果口径保留；毫秒舍入边界仍明确标记真实超时。

修复源位于 `worktrees/sduoj-sandbox-ide-release-20261025`，基于 `13ea99058b8cfccc131140b81f961989d7ac72dc` 独立分支，未混入共享 sandbox 工作区的其他修改。Ubuntu18 arm64 builder 及 GCC7.5/glibc2.27 锁定；fixed v2 SHA256为 `5e349e70d163c365ce81001cbf8ff931c57ad5982420e448c852440001086015`。

## 已完成的回归

| 范围 | 结果 | 限定 |
|---|---|---|
| 原 pinned 编译矩阵 | C++ 4/10、Java 3/10 compileError | 旧失败保留 |
| 修复版独立编译/断点 | C++20/20、Java20/20；40/40 cleanup | 离线 dev 命名空间，非 Gateway E2E |
| watchdog 接口 | fixed 102/102；80ms wall约88ms、停止子进程约124ms正确回收 | 原版存在 abort、秒级 wall 和错误处理 stopped child |
| Worker 全量 | 144通过，51 warnings | 真实 Redis 单元回归；不宣称 warning-free |
| 负载器分类 | 13通过 | null sync/state单列，不错误归为网络失败 |
| R6 Gateway→Redis→Worker 两轮 | C/C++/Python/Java 的 LSP与完整Debug，两轮全部通过 | 分布式 dev：Mini依赖→雷电SSH→MacBook Worker |
| 最终R6/G2/p7连续两轮API | 四语言LSP及完整Debug两轮均通过、退出0 | `p7-g2-api-final-1/r6-acceptance-round-1/2.json`；同一R6镜像、G2、4CPU/6GiB/1024PIDs；父逐语言复核，未增加编译或运行时限 |

watchdog 接口实验有一次重复执行覆盖原 raw 的流程错误；`execution-provenance.json` 明确原 raw 已丢失、仅原工具 summary 保留。后一次 raw 与副本均有来源，不将二者充当独立重复样本。早期挂载、locale、`/dev/null`、Java参数缺失等测试 setup 错误另列，均不计产品通过或产品失败。

## 真实浏览器发现的状态通知间隙与G2回归

R6的两轮API验收没有覆盖所有浏览器自动检查路径。`browser-e2e-r6-attempt15.json` 的完整网络附件显示：交互stdin和下一停止点正常，自动stackTrace完成后，scopes返回completed，但最后snapshot为`busy=true/stateVersion=27`，随后10秒内没有新的idle响应，Continue仍禁用。该现象不能因API验收通过而忽略，也不能在前端强制把busy改为false。

Worker此前的busy mirror修复已能在actor解锁后将idle持久化，并且busy改变不一定增加事件cursor。进一步定位到Gateway长轮询的状态通知间隙：如果idle事务及wake发生在下一次poll订阅前，下一次初读虽可得到`busy=false`，但旧判断只在`waitSeconds=0`或有新事件时返回；events为空时仍等未来通知或20秒超时。因而数据库已空闲，不代表浏览器会及时收到空闲快照。订阅早于读取本身不能覆盖“通知早于整次请求”的情形。

G2采用可选的当前状态令牌：前端发送上次实际观察的`knownStateVersion`与`knownBusy`，Gateway严格要求两者配对、版本为有界非负整数且busy为布尔值。初次没有令牌时先`waitSeconds=0`读取一次；随后当持久化版本或busy与令牌不同，即使events为空也立即返回当前快照；相同时保留长轮询，避免空闲每300ms空请求。actor解锁不增stateVersion，因此必须比较busy，不能只比较版本。

该修复不生成虚假事件、不推进或确认未投递的cursor、不重放命令，也不从客户端令牌推断真实idle。owner/epoch、live-worker与resolver授权保留原流程；未来通知到达后仍重新读取最新快照。若Redis本身确实保留错误busy=true，应作为独立写入一致性问题调查，不能靠此协议掩盖。

| G2验证 | 实际结果 | 证据与范围 |
|---|---|---|
| 新Gateway状态轮询回归 | 8/8通过 | `gateway-g2-build-output/01-regression-xml/summary.json`；含订阅前idle、版本单独变化、相同状态正常长轮询、wake后fresh read、cursor不变、旧客户端及字段校验 |
| Gateway全套 | 16项中14通过、2跳过 | `02-gateway-suite-xml/summary.json`；2项为环境门控真实Redis测试，不能计作通过 |
| Gateway真实Redis补测 | 2项实际执行、0失败/0错误/0跳过 | `gateway-g2-real-redis-output/`；针对独立UUID前缀、同一源码，保留原skip收据，不把不同运行写成单次16/16 |
| 旧逻辑counterpart红复现 | 2项按预期失败 | `04-legacy-red-xml/summary.json`及`legacy-red-verification.json`；两项均为StepVerifier等待超时，`expectedFailuresVerified=true`，与新8项通过分别记录 |
| 前端目标回归 | 2 suites、26项通过 | `frontend-g2-targeted-unit.log`及对应receipt，退出0 |
| 前端TypeScript | 检查通过 | `frontend-g2-typecheck.receipt.json`退出0 |
| G2/p7四语言真实浏览器 | 4通过、0跳过、0重试，90.3秒 | `browser-g2-p7-final-2/report.json`；真实登录/服务，无mock，模板19/32/38/51；服务补全、键盘选中目标后Tab源码变化、断点/watch41/单步/运行中stdin5/ECHO47，各语言均实际观察G2状态令牌长轮询 |

G2的Gradle新回归、全套及bootJar阶段退出0；legacy-red阶段退出1是预期红复现，并经XML核对，不将其称作正常通过。构建metadata与全部XML保存在`gateway-g2-build-output/`。用于dev验证的owned overlay jar SHA256为`7788413637aed3ff75d6bcbbb403d3afd6e87649d7d81ba3e53ff239d9967030`；基于旧冻结jar仅替换`IdeBridge.class`，其余263条本地entry记录字节一致，见`gateway-g2-overlay-provenance.json`。该工件生成收据保留当时`COMPLETE_NOT_DEPLOYED`状态；之后仅部署至自有dev Gateway的证据另在`gateway-g2-deploy-1/`，不覆盖原生成记录或放行生产。

浏览器`final-1`原件保留：C/C++/Python全流程通过，Java用例在服务返回substring且候选可见时未显式选中目标，直接Tab接受了同为合法sub前缀候选的subSequence。只修改测试的真实键盘选中步骤，并断言目标row已focused后才Tab；产品候选、排序与fixture未改，源码变化断言保留。`final-2`重新完整运行四语言，父直接核对原始Playwright报告4个passed/无skip/retry及每个网络附件中的实际G2令牌。登录态保存在私有0600文件，无trace/HAR；前端暂停已解除，终态Worker就绪且文档/Debug资源为0。

## 候选身份

- R6 image：`sha256:aed4d073a034464126a18b21c2c6c88d3af974bc63654efddbe21d81759fb4bf`。
- Debug artifact：`sha256:ccb7fd4b032f8158629bd8ec691d5c614b2627809255b767d3b3541b6fa72970`。
- Native source manifest SHA：`0abe105bd1f8bd82400c0af707f253f82ee5cab77ea60046abf507b7ecfc2efa`。
- 基础 Judge ID 保持原值，但 IDE 私有 rootfs 的编译 supervisor 已覆盖为修复工件，不能称整个 rootfs 未变。artifactDigest 显式包含 sandbox 字节 SHA；source manifest SHA 另外进入 toolchain stamp。
- 原四模板版本/hash、compiler path、Python/debugger路径未改变。未推送 registry、未提交/合并、未对生产放行。

## 资源与业务验收合同

固定500个独立dev账号、4KiB文档、C/C++/Java/Python=40/40/10/10，输入周期2.5s，SYNC到completion间隔300ms；每档20s ramp+75s steady。有效候选、degraded、null、过时revision和异常均分别计数。时延为SYNC开始到completion返回，不是浏览器输入到渲染。95%有效率/有效p95≤1s是工程参考；未独立约定生产SLO。

旧配置每语言32个驻留文档，100 active中C/C++各40个，会引发LRU关闭/重开。clangd本已使用-j2，不能把64个线程简单解释为-j未生效。JDTLS的heap上限也不等于进程RSS上限。R6增加受限数值型 per-language驻留、clangd jobs、JDTLS processors/heap配置，Nacos拒绝越界或参数注入；不开放任意命令字符串。

R6正确性验收暂用4CPU/8GiB/1024PIDs、C48/C++48/Java16/Python16、并发2/2/1/2、clangd-j2、JDTLS APC2/heap384MiB。实际JDTLS argv已独立确认，Debug javac没有设置全局JAVA_TOOL_OPTIONS。后续容量矩阵为了只改变C/C++驻留，固定Java/Python各32，而不是沿用正确性验收时的16；两份配置不可混为同一个实验。

### 六组单Worker资源对照

当前同一R6镜像的六组串行对照均完整执行，500在线/100活跃，实际steady输入约40Hz；所有组均500/500会话清理、无OOM/max事件，容器停止保留。这里只比较LSP，Debug保持空闲，不代替LSP+Debug混合资源验收。每配置单次运行，没有置信区间，也不把临时依赖和缓存差异当成资源参数的确定效果。

| profile | CPU / GiB | C/C++驻留 | Java/Python驻留 | JDTLS APC | 有效/steady | 有效率 | 全样本p95 / 有效p95 | Worker采样峰值GiB | 工程参考 |
|---|---|---|---|---|---|---|---|---|
| p0 | 1.5 / 4 | 32 / 32 | 32 / 32 | 2 | 1879/3000 | 62.63% | 1.267 / 1.104s | 3.265 | 未通过 |
| p1 | 4 / 4 | 32 / 32 | 32 / 32 | 2 | 2970/3000 | 99.00% | 1.008 / 0.965s | 2.758 | C++有效p95 1.076s，未通过 |
| p2 | 4 / 8 | 32 / 32 | 32 / 32 | 2 | 2916/2987 | 97.62% | 2.065 / 1.983s | 2.863 | 未通过 |
| p3 | 4 / 8 | 48 / 48 | 32 / 32 | 2 | 3000/3000 | 100% | 0.664 / 0.664s | 2.229 | 各语言均通过 |
| p4 | 4 / 8 | 48 / 48 | 32 / 32 | 默认 | 3000/3000 | 100% | 0.663 / 0.663s | 2.392 | 各语言均通过 |
| p5 | 2 / 6 | 48 / 48 | 32 / 32 | 2 | 2939/3000 | 97.97% | 1.562 / 1.422s | 2.221 | 延迟未通过 |

工程参考要求总体及每语言均达到95%有效率、有效p95≤1s。p1总体有效p95小于1s，但C++没有达到，不能将其标为通过。p2实际输入39.83Hz，其他组40Hz，steady样本数差异保留原值。

关键机制证据是C/C++文档抖动：p2的C/C++分别发生1211/1131次LRU淘汰、1243/1164次open；相同4CPU/8GiB下p3将驻留32改为48后，淘汰均降为0，open各41次（包含预热文档）。100活跃按40/40/10/10分配，每种C语言40个文档可驻留而无需反复关闭/重建解析状态。这一数据支持在当前工作负载中消除驻留不足导致的抖动，不能概括为“增加内存解决了问题”。p1→p2只增加内存并未在该单次序列中改善结果，也不能反向声称更多内存必然降低性能。

p3/p4的相近结果不能证明APC2带来性能收益；APC2作为受限线程配置保留，后续仍需混合Debug与更长运行验证。p5内存约2.22GiB且无OOM，仍未达到延迟参考，说明不能只按RSS把CPU压至2核。

原始数据及来源：`resource-matrix-r6-4/p0..p5/raw.json`、各`summary.json`/`samples.jsonl`以及`comparative-summary.json`，均位于本轮证据目录。六组原始文件、p0–p5定义和历史失败未改写。

### 内存收敛与选型

p6/p7已在`resource-matrix-r6-memory-2/`完成相同CPU/驻留/线程的内存对照。两者均500在线/100活跃、3000/3000有效，各语言均达到工程参考，500/500清理，无guard/OOM；C/C++各open41、Java/Python各11，淘汰均为0。

| profile | CPU / GiB | 全/有效p95 | p99 | Worker采样峰值GiB | C/C++/Java/Python有效p95 |
|---|---|---|---|---|---|
| p6 | 4 / 4 | 0.533s | 0.665s | 2.599 | 0.363 / 0.367 / 0.689 / 0.365s |
| p7 | 4 / 6 | 0.587s | 0.709s | 2.230 | 0.412 / 0.416 / 0.703 / 0.396s |

下一阶段选择**4CPU/6GiB/1024PIDs**：4GiB已经通过LSP，不将它写成失败；但观测到的LSP采样峰值2.599GiB与既有Debug独立硬预算1.5GiB相加已超过4GiB，6GiB可为混合现场及波动留余量，较8GiB配额减少25%。这是一项预算余量选择，不把不同进程/cgroup的采样峰值相加冒充实测混合峰值。Debug正常预算1.25GiB、硬上限1.5GiB、活跃2/驻留8均保持，实际并发资格仍按下述混合验收范围记录。

G2 Gateway替换完成后，p7又独立复测20/50/100活跃：

| 活跃 | 有效/steady样本 | 全/有效p95 | p99 | 实际steady输入Hz | 各语言 |
|---|---|---|---|---|---|
| 20 | 600/600 | 0.580s | 0.670s | 8 | 全部100%有效、有效p95≤1s |
| 50 | 1500/1500 | 0.515s | 1.070s | 20 | 全部100%有效、有效p95≤1s |
| 100 | 3000/3000 | 0.689s | 0.896s | 40 | 全部100%有效、有效p95≤1s |

该轮Worker采样峰值2.087GiB，500/500清理、无guard/OOM；100档C/C++/Java/Python有效p95为0.482/0.490/0.901/0.479s。原始依据为`resource-matrix-r6-p7-final-1/p7/raw.json`、`result.json`与`samples.jsonl`，raw SHA已核对。这里的100活跃仍指既定2.5秒输入周期、4KiB及40/40/10/10语言比例，不外推为任意触发频率或语言偏斜的容量承诺。

### 独立LSP与Debug混合验收

`mixed-p7-final-1/`在同一R6/G2和p7资源下独立执行500在线/100活跃LSP加1个Java21 Debug。它使用单独scope和supervisor，保持原20秒ramp/75秒steady与所有产品时限，不并入LSP-only对照。可选的0600独占生命周期JSONL给出真实steady时钟锚，steady+5秒才创建Debug；原负载的HTTP、summary及report/contract口径不变。

- LSP为3000/3000有效，整体有效p95为0.579s、p99为0.705s，40Hz；C/C++/Java/Python有效p95为0.396/0.390/0.696/0.393s，各语言100%有效。
- 唯一已核对SID/epoch的Java现场完成编译、首断点、watch41、暂停驻留20.010秒、next新stopId、continue至running后stdin5、第二断点、继续及ECHO47；没有预填暂停stdin以避开运行计时。
- Debug与LSP steady实际重叠26.668秒；Worker采样峰值2.761GiB，未触发5.25GiB守卫、OOM或max事件。500个LSP加1个Debug清理确认，最终五组件就绪且文档/Debug资源为0，随后仅停止本轮容器。
- `executedComplete=true`与`diagnosticQualified=true`分别记录，退出0；低有效率的完整运行会记为未达标而非通过。父复核了raw SHA、各语言完整性、暂停/重叠时间与最终五组件清理。

该结果只资格化1个Java Debug伴随100活跃LSP，不将配置中的active2/resident8上限改写为已测的任意语言现场容量。之后同一候选已连续通过两轮四语言完整API，覆盖LSP语义、真实断点/watch/单步重放去重/运行中输入/ECHO47、编译错误、运行超时及跨用户拒绝；见`p7-g2-api-final-1/`。四语言UI及下述优雅恢复另有独立通过证据；生产并发、长稳与异常退出仍需同构环境验收。

## dev权限边界与优雅恢复

`p7-g2-boundaries.json`的8项真实边界检查通过：身份伪造拒绝、非可信Origin拒绝、旧history路由保留、非法创建释放、restore保留现场、replace先回收、stop释放账号占用，以及限流返回quiet-null。它不替代生产故障注入。

`graceful-p7-recovery-2/`完成一次已明确指定的自有p7 Worker优雅重启：创建C++17暂停现场并保存已完成step账本；仅发一次SIGTERM，确认Docker die exit0、没有signal9，再核对同一容器owner/不可变镜像/4CPU6GiB1024PIDs后start。新组件epochs与Debug incarnation变化，旧现场命令被fence且账本不变；新现场完成watch/step重放去重/running后stdin5/ECHO47，最终四语言文档及Debug预算为0。没有清未知reservation或操作其他服务。

清理证据结合matching-epoch的Worker `cleanup.clean`、已捕获原scene guardian路径、die0/no9及启动后旧scene-specific cgroup/state目录不存在；启动后的检查位于新namespace/tmpfs，不能单独当作已扫描停止namespace或crash孤儿进程的证明。该结果是受控优雅恢复，不是SIGKILL、Redis中断或生产HA验收。

首次`graceful-p7-recovery-1/`在只读snapshot阶段结束，未发TERM或其他mutation。父用实际异常包装后的嵌套源码纯本地复现IndentationError：外层包装缩进进入了raw probe字符串；修复dedent并增加真实wire回归后11项纯测试通过，再以新目录运行第2次。旧失败、根因记录和原prepared SHA保留，不将其写成Worker恢复失败或成功。

`gateway-rollback-old-1/`先将同一个自有Gateway回滚到旧冻结jar，健康后进行真实认证capabilities冒烟；`gateway-rollback-g2-1/`再恢复G2，健康后8项boundary重新通过。两次均固定原runtime image，仅`--no-deps`更新Gateway，52个其他运行容器ID均未变。最终G2只读挂载的jar SHA仍为`77884136…9967030`，Worker保持R6/p7、唯一registry与新epochs、文档/Debug资源为0，前端PID92712运行且暂停标记为false。该演练覆盖dev回滚机制，不把旧jar的健康冒烟当成它已修复G2状态通知问题。

最后在当前重启incarnation执行`final-four-lsp-warmup-1/`：四个真实账号各验证一个实际服务端completion并finally close。`final-live-ready.json`记录当前四语言readyProcesses均1、documents均0，Debug active/resident/queued/grantedBytes均0，五组件registry唯一且epochs一致；G2健康及只读jar、前端运行状态再次核验。该记录是即时预热确认，不承诺provider永久驻留。所有本轮测试/监控进程均结束，dev服务保持可测试状态。

本轮源码只在五个隔离工作树形成46个owned文件的增量；各仓库patch均对已核验baseline执行apply-check，已记录共享源检查无变化，已知500个私有账号密码扫描0匹配。Worker的51个运行时源文件与实际R6构建context逐字节SHA一致，Gateway仅替换已测IdeBridge.class。最终证据与源码/配置SHA由本轮独立release lock保存，不改写R5或原始失败收据。

两次内存补测的首次setup因Docker按可变tag返回No such image、同时按冻结ID可读且RepoTags含该tag而停止，未产生负载；保留在`resource-matrix-r6-memory-1/`。随后编排按实际执行所用的冻结ID检查对象及Entrypoint，运行仍使用`--pull never`和同一ID，不重标tag、不拉取或替换镜像；错误ID/Entrypoint均有fail-closed纯测试。旧六组和失败raw未改写。

### dev配置落地

- 当前矩阵直接使用独立远端Docker容器及逐profile Nacos配置；实际配置保存在`resource-matrix-r6-4/p*/nacos.json`，独立dataId以`ide-worker-matrix-dev-20261025-`开头。运行参数见对应`profile.json`/`result.json`，不需要修改生产模板。
- 已新增`templates/ide-worker.nacos.worker-tuning.dev.json`，完整environment与实测p7逐键相同，资源字段为`SDUOJ_IDE_{C,CPP,JAVA,PYTHON}_MAX_DOCUMENTS=48/48/32/32`、clangd jobs2、JDTLS processors2/heap384MiB。凭据仍为`${AUTOLAB_REDIS_URL}`/`${DEV_RPC_TOKEN}`，不写入源码。现有MacBook dev使用`host.docker.internal:19882`经有线SSH转发访问Mini Problem RPC。
- 已新增独立`compose.ide-worker-tuning.dev.yaml`，固定R6 image ID、4CPU、默认6GiB、1024PIDs；使用现有私有0600 env文件和显式独立owner/network/worker ID。它是仅Worker的MacBook dev配置，不会启动Gateway或其他dev服务；当前矩阵容器由等价的显式Docker参数启动，并非调用此Compose文件。新模板和Compose已做无服务启动的schema验证。旧`compose.ide-release-gates.dev.yaml`仍指R5，不作为R6 Worker启动文件。
- 本轮Gateway仅用固定旧runtime image和G2单类overlay替换自有服务，52个其他运行容器ID核对不变，健康HTTP200。`gateway-g2-deploy-1/receipt.json`保存部署依据和旧jar回滚入口。生产模板未修改。

## 生产放行前门槛

- 当前为Mini Gateway/依赖经有线SSH连接MacBook ARM64 Worker的cgroup-v2、privileged dev。生产cgroup-v1、非root、实际namespace/seccomp/UID映射与外置Debug预算计账仍需同构验证；不能将dev容器总额6GiB直接视为生产外置Debug后的总资源包络。
- 100活跃按本文4KiB、2.5秒周期和40/40/10/10语言比例达标；正式SLO、其他语言偏斜/触发频率、更长稳态、active2/resident8的实际语言组合，以及多Worker扩容需另有合同和实测。配置上限不是已测容量。
- Redis/控制面中断、SIGKILL及崩溃孤儿现场恢复、生产多副本灰度和回滚仍未在正式环境验证。本轮受控优雅恢复与dev Gateway回滚不能替代它们。
- 尚未提交/合并、推送registry或修改生产开关。正式accepted profile必须与生产镜像、native、模板、权限和实际资源配置匹配，dev profile不能复制为正式验收证明。
