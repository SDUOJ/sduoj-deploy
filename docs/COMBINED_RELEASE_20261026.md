# Online IDE、LSP、Debugger 与评测沙箱联合发布

本次范围：基础 IDE / Run / 云代码历史 / 正式提交、LSP、Debugger，以及用户确认的评测沙箱答案读取隔离加固。发布前在独立 dev 完整部署并回归。用户于2026-10-28明确授权全部测试通过后上线；该授权不豁免任何门禁。维护规范以闭源 workspace 的[发布检查表](../../docs/maintenance/release-workflow.md)为准；下述候选和验收数字是分阶段历史记录，当前状态以受限发布单及实际 CI/制品收据为准。

## 源码与制品

直接在既有维护分支开发和发布，不新建 branch 或 PR，subagent 同样执行。server-private、Judger、Sandbox、AutoLab 和 Web2 使用 `master`，deploy 使用 `middlewares`；Judger `stable` 是独立开源版本。淘汰的 release 分支先保全、合入并验证提交可达，再删除本地及远端引用。最终精确 SHA 和制品 digest 记录到受限发布单。

| 仓库 | 本次内容 |
|---|---|
| web2 | 最小 Monaco IDE、普通/比赛/题单入口、Run/云代码/正式提交、LSP/Debug；保留本轮准备期间已在线的成绩复查功能，不增加 AI 后台/首页/全站主题 |
| server-private | 继承6a9e54bf的Run/业务上下文/模板memfd修复；Gateway Redis bridge、toolchain/Debug RPC；共享文件DTO显式JSON构造，保留既有RPC重复头/常量时间鉴权与统计隔离 |
| Judger | 继承4636915评测机加固；Run memfd/isolateFS、checker独立case副本、有限内存安全cap、可信cgroup路径、匹配接口包构建；同一镜像按显式模式提供 LSP/Debug |
| sandbox | 继承b58c236加固；旧libseccomp负pseudo系统调用号修正；JDK匿名socketpair与Rust编译器最小匿名握手；外网/命名连接/FD传递仍拒绝 |
| AutoLab | 保留发布前实际在线的题单、成绩复查和 AI 路由，适配 native context RPC 与迁移元数据依赖；不能用早期精简候选覆盖线上功能 |
| deploy | 单Worker权限/资源、独立整栈dev、私有配置渲染、资格/容量/恢复工具、additive迁移与回滚说明 |

已发布4636915 parent index只读确认仍为sha256:7094111e50d5545924d908c5fbbab534b4dcd126d4ac03c50eb61f18882792e0。它不包含本轮新兼容修复，不能作为最终联合制品。

最终交付使用一个 Judger 镜像承载正式评测、Run、LSP 与 Debug。正式评测是默认模式，沿用原有 `tini -> sduoj-judge-entrypoint -> Java` 启动链；Run 仍由 `sduoj.run.worker=true` 和独立队列选择。只有显式的 IDE 模式参数才启动 LSP/Debug 后端，并在启动前检查非 root 身份、固定工具链清单、cgroup 委托和隔离策略。未知模式、root IDE 模式、缺少工具清单或隔离前置条件时必须失败关闭。IDE 工具和调试运行时作为同一镜像的受审 `/opt` 内容构建，不能通过旧本机镜像层、临时 overlay 或额外源码 checkout 注入。

IDE 编译与正式评测使用同一镜像中的加固 sandbox 生产链，但保留独立的编译阶段边界和资源合同；不能把正式评测容器的权限直接授予 IDE 控制进程。Option B 的 user namespace、挂载、cgroup 委托和 CapBnd 门禁必须在目标 ARM64/cgroup-v2 guest 中真实验证，验证前不开放 Debug。旧 R8/R15 及单独 IDE 镜像只作历史证据，不能替代统一镜像的完整验收。

CI 沿用原流程。Judger 保留用户提交 `3817aa18` 的阿里云兼容设置 `provenance: false`、`sbom: false`；不要在整理提交时删除或改造。工具链生产者使用原 GHCR metadata 步骤规范仓库名，再由统一镜像直接消费已核验 digest。SDK 构建成功、统一镜像工具可运行和四角色完整业务验收分别记录。

## 发布前安全修复

2026-10-29 已只读检查当前生产防火墙、监听、进程及测试目录引用，收紧闲置 staging 备份、两处旧 IDE 测试目录、工具目录和历史运维脚本权限。备份与失败证据保留；没有重启业务、修改防火墙或切换生产流量。具体路径、原权限、回执及验证结果仅放受限发布单。

用户已批准将 AutoLab 代码移至 root 管理的 `/opt/sduoj/releases`，先在 staging 验证，再在本次正式窗口切换；当前线上服务保持原路径。代码目录及全部祖先都不能由服务账号替换，日志、数据、解释器及环境文件沿用原位置。使用[路径迁移与回滚说明](AUTOLAB_RELEASE_PATH_MIGRATION.md)，实际 Linux 权限测试不替代真实 systemd、业务与回滚验收。

## 同构权限和资源合同

目标为ARM64、cgroup-v2、Docker cgroupfs。IDE使用UID/GID10001、非privileged、cap_drop ALL，仅SETUID/SETGID bounding；两个原identity helper无setuid，仅精确filecaps。外层seccomp/AppArmor/systempaths放开以创建嵌套namespace，用户代码内层固定NsJail/seccomp、UID65534、cap0、NoNewPrivs1。仅绑定自己的aggregate子树，禁止Docker socket和host PID，DEV_DEBUG_LAB=0。Docker Desktop基线使用独立容器网络；新执行层VM模板显式使用guest的host network，由VM隔开物理宿主网络命名空间。这个变化必须在新guest重新验收，旧网络收据不转记为通过。

IDE aggregate总额：4CPU/6GiB/1024PIDs/swap0，管理CID与Debug兄弟组都计入；Debug兄弟组1CPU/1.5GiB/512PIDs。语言文档48/48/32/32，clangd-j2，JDTLS2processor/384MiB，concurrency2/2/1/2。Java文档生命周期/持续性能当前仍在诊断，最终配置以新证据冻结，不自行加超时或放宽95%/1秒参考。

R8 guardian30秒CPU预算只统计trusted控制cgroup。目标jail仍受1核速率、既有每次运行20/20/60/40秒墙钟、hard/idle生命周期限制；编译仍有独立nativeCPU上限。CPU预算不能由编译器/adapter/目标累计用量提前消耗。验收客户端按公布runLimit+10秒观察清理，不改服务端或HTTP超时。

当前正式候选是 `six-formal-16c32g`：16vCPU/32GiB guest 内保留六个正式 Judger，每实例1CPU/2560MiB，分别使用核4至9；Run 为2CPU/2560MiB，使用核10至11；IDE aggregate 使用核0至3。执行额度共12CPU/23.5GiB，余4CPU/8.5GiB供系统及开销。原单正式实例24GiB实验不能替代该候选容量验收。Javaheap384MiB、CPU_PER_JUDGER=1、显式SDUOJ_JUDGER_CPU_NODE_INDEX=1；启动核对实际effective cpuset、CPU分配及每个实例的Snowflake身份，不能从含日期的DNS名称推断节点。正式评测和Run沿用tini→sduoj-judge-entrypoint→Java、private cgroup、SYS_ADMIN、AppArmor unconfined、非privileged；与非root IDE权限合同分别验收。Java模板0内存采用operator物理安全cap默认1GiB；heap/CPU/wall配置与正factor公式保持。

## 完整隔离dev

MacBook专属project/network sduoj-combined-release-20261026：OJ数据库副本、原生题单数据库副本、独立Redis、独立Rabbit实例、独立Nacos namespace、六Java服务、AutoLab、新正式Judger/RunWorker、R8Worker与前端生产构建。现有其他任务不重启、不清理。队列名称固定，不能仅换namespace隔离评测。

Gateway与Worker Redis host/port/**DB2**/prefix必须匹配，先用scripts/ide_connection_preflight.py只读核对。仅复制SQL不代表附件存在：本轮fixture通过真实上传/下载创建专属物理文件，避免CAS dedup指向未迁移旧附件。

模板templates/combined-release.dev.nacos.json只含占位符。复制env.example至私有0600文件填密码、RPCtoken、Fernetkey及固定镜像；scripts/combined_dev_config.py默认只生成新的私有JSON，显式--apply才发布到loopback Nacos与专用release-dev-* namespace。Problem nativecontext http://autolab:5005/internal/run/context，Gateway /api/ps/**指向autolab:5005，不复制Mac之间SSH拓扑到生产。

六Java基础镜像无tini，采用Docker init:true+java entrypoint；Judger镜像自带tini。专用dev MySQL账号沿用mysql_native_password非TLS合同；生产既有TLS/认证须只读确认，不自动改生产账号。Nacos JAVA_TOOL_OPTIONS ActiveProcessorCount=2避免原生线程/PID配额失配。

## 当前候选与验收边界（2026-10-29）

统一guest的最终业务验收仍在进行，生产尚未切换。以下身份只能作为候选，不能据此开放流量：

- IDE R15：源码e4422e0e、镜像311abf97538f；新guest内已就绪，完整API/浏览器/隔离/容量/恢复门禁待完成。
- Judger产品c5224fbb：修复CPU节点选择，保留原native/rootfs；同一新镜像必须重新完成正式评测和Run验收。后续CI报告提交不修改产品字节。
- server-private e016fc73：buildJar --scan产出的六类服务JAR及lib已逐文件部署到dev；生产实际七个JVM实例（两个WebSocket），Snowflake须按实际进程逐个核验。
- AutoLab 23e651ee：保留发布前213条线上路由与原main/middleware，实际dev API、MySQL行锁和成绩复查回归待完成；生产仍沿既有systemd/Python管理方式。
- Web2 836c095e：975项unit已通过此前阶段；精确最终ref的全量CI与新guest浏览器验收仍待终态，不能沿用旧317项浏览器结果宣布完成。
- Linux manager：固定依赖层及非root工具探针已通过；六正式实例和MQ消费者网络修订须重新冻结运行代码，registry发布和生产KVM引导仍待完成。

生产另有六正式Judger及一个Run，不能将当前单正式实例dev结果当作六实例容量。新增`six-formal-16c32g`候选：16vCPU/32GiB，IDE4CPU/6GiB，六正式各1CPU/2560MiB，Run2CPU/2560MiB，独占cpuset合计0–11，其余用于guest开销。该profile须新实例完整复验和六正式/IDE混合负载后才能替代线上；尚未取得运行资格。Judger/Run没有HTTP server，注册端口不作为ready；验证对应队列消费者、认证heartbeat和实际业务闭环，Run控制RPC指向Problem服务。

生产只读库存已确认主库MySQL8.0.39/utf8mb4_unicode_ci与AutoLab库8.0.31/utf8mb4_unicode_ci。dev库版本和默认collation不同，不能称数据库完全同构。在线备份只供隔离恢复演练，维护窗口仍须建立跨库与文件的一致恢复点。迁移先比较现有结构；已存在且匹配的表/索引不重放DDL，se_value保持MEDIUMTEXT NOT NULL。

## 历史验收基线

完整原始证据在work/artifacts/ide-judger-release-prep-20261026，失败记录不覆盖。下表包含早期Docker Desktop及旧候选结果，只作功能来源与回归基线，不能代替上述最终guest、镜像和配置的验收。

| 验收 | 已有结果 |
|---|---|
| 前端quality/coverage/生产build | 147 suites /955 tests通过；format/type/lint/validation/安全/恢复/制品/静态门禁通过 |
| 标准浏览器CI | 320例：317通过、0失败、0flaky、3个既有desktop不适用抽屉分支跳过。WebKit精确既有通知15例各1次，其他pageerror0 |
| 真实业务浏览器 | 最终生产产品内容6/6：运行、取消/刷新恢复、云代码精确bytes、正式AC100/WS回放、比赛与题单context、生产路由隔离 |
| R8 IDE专项 | 两轮完整四语言API及各轮边界通过；真实浏览器4/4无skip/retry；真实隔离12/12通过 |
| server | 147实际通过，7个Redis条件测试另在真实独立Redis7/7、0skip；DTO新增测试通过，新DTO服务已部署，真实6业务浏览器及最终Judger/Run聚合回归完成；新IDE候选仍须联合复验 |
| 部署合同 | 120项通过（含连接DB及超时观察合同） |
| AutoLab | 新native11/11；课程/教室/题单/UserProfile真实API通过；全仓旧AI测试缺实现、另5旧mock断言在干净基线同样失败，保留边界 |
| 新sandbox native | Mini与MacBook各自原23integration/10runtime/2cgroup/20次4并发PID及supervisor death通过；expanded27含Java/Rust/匿名握手/外部网络与FD传递拒绝通过 |
| Linux Judger | 新DTO制品9类42 tests：41通过、1条件跳过、0失败；实际CI smoke含Java8/17/21真实编译运行与helper隔离通过 |
| 广泛API | 最终DTO候选多phase聚合已完成132/132 checker×语言Run、12/12正式语言、23次meta（22种配置含合同重复）、6类故障及隔离/取消；原失败收据保留，取消只证明4秒投影不变，不单独证明晚到callback已到达 |
| 容量 | R8的20/50/100活跃、500在线75秒各语言/总体100%有效，p95 .488/.462/.542秒；mixed通过；持续第1轮Java85.33%/p95 1.070秒未达门槛。后续R11虽短档延迟通过，但关闭后残留15个项目且provider退役，仍判失败；当前修复文档切换与异步项目删除竞态，900秒/最终恢复尚未完成 |
| 恢复/故障/回滚 | 前端artifact事务/独立回滚本机演练16/16；Judger/Run安全同native镜像回退→C++formal/RunAC→恢复最终DTO→meta生成/公开导入及5个旧正式投影不变均通过；最终IDE候选graceful/crash尚未完成，Redis共享整栈故障不混入负载 |

用户已在当前会话明确采用以下正式灰度质量门槛：500在线/100活跃，每种语言与总体validRate>=95%、validP95<=1秒，且无持续provider退役、资源泄漏或隔离失败。批准收据为work/artifacts/ide-judger-release-prep-20261026/GRAY_ACCEPTANCE_CONTRACT.json；该决定只批准验收标准，不批准生产切换，也不改变历史失败候选的资格。统计必须同时保留allP95、失败/timeout/degraded/null；不能称所有请求p95<1秒。15分钟累计稳态也不是24小时长稳。

### Java LSP 当前修复边界

R14首次失败发生在cleanup的第一个 `java.project.getAll`，等待2.0015秒，删除命令尚未发送，队列等待约25微秒。独立真实JVM线程栈确认，JDT在executeCommand分派前同步调用IndexManager.waitForIndex，RPC reader因此阻塞；同时JDK21模块索引仍在运行。初始化job此前已结束，不能把失败归因于初始化通知、删除job或内存不足。空workspace getAll的对照实验仍失败；可信内部Java文档完成生命周期后等待索引、正常关闭，才消除了该复现。

R15源码 `e4422e0e547b0d29068a3e392f12e56fb6572076` 将这段准备放入既有30秒provider启动总预算，业务deadline和cleanup2秒预算不变。184项单测通过；真实10session/100revision更新99ready、1timeout，项目数在运行中固定20、关闭后0，provider starts1、cleanup失败0；同镜像四语言warm通过，Java冷启动2次degraded完整保留。该结果来自Docker Desktop基线，只说明有界复现与预热通过；不是统一guest、500/100容量、900秒稳态或故障恢复资格。精确R15镜像和后续阶段以本轮 `IDE_LATEST_STAGE.json` 为准。

## 发布顺序与回滚

1. 冻结提交、镜像 digest、包坐标及校验值、配置与 schema 依赖。本地先由 server `publishToMavenLocal`，Judger 使用匹配的 `Versions.sduoj`；GitHub 先由 server 原 Actions 发布 GitHub Packages，再验证 Judger 独立消费。沿用既有包凭据，不新增 Deploy key，不额外 checkout server 源码、不使用 composite/includeBuild。Sandbox 经原 judging-containers 工作流发布，Judger 沿原 Dockerfile 构建和 Actions 推送。此前临时源码密钥与替代构建入口已撤销，不作为发布步骤。
2. 备份并实际恢复演练后，对比目标schema，按migrations/online-ide/README仅选择本次功能确实缺少的additive表/索引。逐份记录SQL校验值、目标、锁与耗时；不盲目重放已存在结构。回滚不drop表，不改历史正式结果。
3. 完成整个新候选功能/安全/容量/持续运行/恢复与artifact回滚，生成最终精确镜像专属资格锁。历史R7/R8及失败候选收据只保留来源，不用于新镜像冒充通过。
4. 生产目标基础环境先具备同一内核能力与cgroup/driver，再做只读preflight和节点资格。当前主机不满足，见下节。
5. 全部门禁通过、精确候选与既定范围核对后，按用户2026-10-28的条件上线授权执行。排空后按兼容接口/schema服务→评测/Run→IDEWorker→Gateway入口→前端顺序灰度，不在执行中替换sandbox或重放Debug命令。授权收据为work/artifacts/ide-judger-release-prep-20261026/release-readiness-20261028/USER_RELEASE_AUTHORIZATION.json；测试未通过时禁止切换。
6. 正式/v2使用scripts/release-v2-artifact.sh提升已验收artifact，不重建；独立staging/SHA验证/备份/切换/smoke/rollback已完成本机隔离真实rsync/TLS16项演练。现有release-v2-pre脚本只处理/v2-pre，不用于正式v2。详见FRONTEND_V2_ARTIFACT_RELEASE.md。

回滚先停新建、保留查询/取消，确认进程树/cgroup清空后恢复上版固定镜像与配置。保留additive数据，不FLUSHDB、不清未知reservation。前端保留v2-backup并提供独立rollback；评测回退旧安全边界须显式记录，不能自动回退成答案可读来掩盖失败。

## 当前生产环境阻塞与VM路径

已只读核对sduoj-prod10.102.33.79：ARM64/64CPU/约188GiB，Ubuntu20.04.2/Linux5.4，Docker27.1/cgroupfs/**v1**。存在/sys/fs/cgroup/unified不代表Docker使用v2。Landlock version-only syscall返回ENOSYS38，新sandbox不能直接运行。

/dev/kvm可用，KVM_GET_API_VERSION只读返回12，当前账号可访问；尚未创建虚拟机。普通Docker共享宿主内核，Docker-in-Docker也不能解决；可用完整ARM64 Linux VM提供新内核，再在其中运行同一套Docker。若要求基础系统也一致，dev与生产须从同一固定guest基础盘重新验收，不能把Docker Desktop旧收据自动转给未启动VM。

详见[虚拟机环境方案](PRODUCTION_VM_ENVIRONMENT.md)。未修改生产内核/Docker/cgroup/网络/服务/数据库、未重启或创建VM，当前仅准备和只读审计。

用户已选择执行层VM迁移范围（IDEWorker/Judger/RunWorker）；数据库与业务服务保留现位置。虚拟机管理包正在准备，未启动生产VM。

## 同源guest制备补充

16vCPU/24GiB/GICv3/HVF的同源内核直接引导已实测成功，cloud-init完成且guest干净poweroff；UEFI组合的早期启动失败仍保留，不转记通过。dev与生产共同采用固定direct-kernel合同：同一prepared根盘、从该盘核验并冻结的kernel/initrd、精确PARTUUID和command line。独立dev guest已实际安装固定离线Docker29.2.1，29个锁包逐项版本/架构核对通过；cgroup2/cgroupfs、Landlock ABI6与active LSM、pidfd/close_range均已通过。2026-10-28身份清理、正常关机、独立盘转换/check/0400冻结及关机后只读身份复核完成，磁盘SHA256为9f449eedd2dc43a52fb1d6d260dbdeb4003d22c67019aa1a2eae69715d8cbe47。完整收据为DEV_GUEST_FREEZE_RESULT_20261028.json，状态仍为PREPARED_NOT_GUEST_QUALIFIED。新dev集成guest已启动并通过同一内核/boot字节、Docker和路由探针，执行层业务、容量与生产KVM资格仍须实际完成。
