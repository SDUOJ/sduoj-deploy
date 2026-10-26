# Online IDE、LSP、Debugger 与评测沙箱联合发布

本次范围：基础 IDE / Run / 云代码历史 / 正式提交、LSP、Debugger，以及用户确认的评测沙箱答案读取隔离加固。发布前在独立 dev 完整部署并回归。当前生产流量未切换，本地提交与新镜像未推送。

## 源码与制品

六仓库均使用独立 release/ide-judger-20261026 分支；最终精确 SHA 和制品 digest 统一记录到本轮发布锁。

| 仓库 | 本次内容 |
|---|---|
| web2 | 最小 Monaco IDE、普通/比赛/题单入口、Run/云代码/正式提交、LSP/Debug 与真实测试；不携带新 AI 后台/首页/全站主题 |
| server-private | 继承6a9e54bf的Run/业务上下文/模板memfd修复；Gateway Redis bridge、toolchain/Debug RPC；共享文件DTO显式JSON构造，保留既有RPC重复头/常量时间鉴权与统计隔离 |
| Judger | 继承4636915加固；Run memfd/isolateFS、checker独立case副本、有限内存安全cap、可信cgroup路径、匹配接口源码构建；独立IDE Worker |
| sandbox | 继承b58c236加固；旧libseccomp负pseudo系统调用号修正；JDK匿名socketpair与Rust编译器最小匿名握手；外网/命名连接/FD传递仍拒绝 |
| AutoLab | 基于55591c6原生题单，仅增加严格身份校验和Run/IDE native context RPC，无新AI任务模块 |
| deploy | 单Worker权限/资源、独立整栈dev、私有配置渲染、资格/容量/恢复工具、additive迁移与回滚说明 |

已发布4636915 parent index只读确认仍为sha256:7094111e50d5545924d908c5fbbab534b4dcd126d4ac03c50eb61f18882792e0。它不包含本轮新兼容修复，不能作为最终联合制品。

IDE编译rootfs/native与正式评测sandbox是两个独立受控工件，分别锁定。R8从精确R7派生，仅修改外部guardian/launcher/runtime三文件；82236个/opt文件除三文件逐字节一致，编译器/rootfs/native/adapter未换。R7旧资格锁不用于R8。

## 同构权限和资源合同

目标为ARM64、cgroup-v2、Docker cgroupfs。IDE使用UID/GID10001、非privileged、cap_drop ALL，仅SETUID/SETGID bounding；两个原identity helper无setuid，仅精确filecaps。外层seccomp/AppArmor/systempaths放开以创建嵌套namespace，用户代码内层固定NsJail/seccomp、UID65534、cap0、NoNewPrivs1。仅绑定自己的aggregate子树，禁止Docker socket/host PID/network，DEV_DEBUG_LAB=0。

IDE aggregate总额：4CPU/6GiB/1024PIDs/swap0，管理CID与Debug兄弟组都计入；Debug兄弟组1CPU/1.5GiB/512PIDs。语言文档48/48/32/32，clangd-j2，JDTLS2processor/384MiB，concurrency2/2/1/2。Java文档生命周期/持续性能当前仍在诊断，最终配置以新证据冻结，不自行加超时或放宽95%/1秒参考。

R8 guardian30秒CPU预算只统计trusted控制cgroup。目标jail仍受1核速率、既有每次运行20/20/60/40秒墙钟、hard/idle生命周期限制；编译仍有独立nativeCPU上限。CPU预算不能由编译器/adapter/目标累计用量提前消耗。验收客户端按公布runLimit+10秒观察清理，不改服务端或HTTP超时。

正式Judger与Run各2CPU/2560MiB/1024PIDs，Javaheap384MiB，CPU_PER_JUDGER=1。当前18核dev专属cpuset分别2-3/4-5，实际执行核2/4，避免两个node1争抢首核。生产CPU编号须根据目标节点确认。两条服务使用tini→sduoj-judge-entrypoint→Java、private cgroup、SYS_ADMIN、AppArmor unconfined、非privileged；与非root IDE权限合同分别验收。Java模板0内存不是0字节，明确operator物理安全cap默认1GiB；heap/CPU/wall配置与正factor公式保持。

## 完整隔离dev

MacBook专属project/network sduoj-combined-release-20261026：OJ数据库副本、原生题单数据库副本、独立Redis、独立Rabbit实例、独立Nacos namespace、六Java服务、AutoLab、新正式Judger/RunWorker、R8Worker与前端生产构建。现有其他任务不重启、不清理。队列名称固定，不能仅换namespace隔离评测。

Gateway与Worker Redis host/port/**DB2**/prefix必须匹配，先用scripts/ide_connection_preflight.py只读核对。仅复制SQL不代表附件存在：本轮fixture通过真实上传/下载创建专属物理文件，避免CAS dedup指向未迁移旧附件。

模板templates/combined-release.dev.nacos.json只含占位符。复制env.example至私有0600文件填密码、RPCtoken、Fernetkey及固定镜像；scripts/combined_dev_config.py默认只生成新的私有JSON，显式--apply才发布到loopback Nacos与专用release-dev-* namespace。Problem nativecontext http://autolab:5005/internal/run/context，Gateway /api/ps/**指向autolab:5005，不复制Mac之间SSH拓扑到生产。

六Java基础镜像无tini，采用Docker init:true+java entrypoint；Judger镜像自带tini。专用dev MySQL账号沿用mysql_native_password非TLS合同；生产既有TLS/认证须只读确认，不自动改生产账号。Nacos JAVA_TOOL_OPTIONS ActiveProcessorCount=2避免原生线程/PID配额失配。

## 验收状态

完整原始证据在work/artifacts/ide-judger-release-prep-20261026，失败记录不覆盖。以下是当前已完成与未完成边界，不是生产激活声明。

| 验收 | 已有结果 |
|---|---|
| 前端quality/coverage/生产build | 147 suites /955 tests通过；format/type/lint/validation/安全/恢复/制品/静态门禁通过 |
| 标准浏览器CI | 320例：317通过、0失败、0flaky、3个既有desktop不适用抽屉分支跳过。WebKit精确既有通知15例各1次，其他pageerror0 |
| 真实业务浏览器 | 最终生产产品内容6/6：运行、取消/刷新恢复、云代码精确bytes、正式AC100/WS回放、比赛与题单context、生产路由隔离 |
| R8 IDE专项 | 两轮完整四语言API及各轮边界通过；真实浏览器4/4无skip/retry；真实隔离12/12通过 |
| 初始server | 147实际通过，7个Redis条件测试另在真实独立Redis7/7、0skip；DTO新增测试通过，更新服务尚待最终联合回归 |
| 部署合同 | 120项通过（含连接DB及超时观察合同） |
| AutoLab | 新native11/11；课程/教室/题单/UserProfile真实API通过；全仓旧AI测试缺实现、另5旧mock断言在干净基线同样失败，保留边界 |
| 新sandbox native | Mini与MacBook各自原23integration/10runtime/2cgroup/20次4并发PID及supervisor death通过；expanded27含Java/Rust/匿名握手/外部网络与FD传递拒绝通过 |
| Linux Judger | 新DTO制品9类42 tests：41通过、1条件跳过、0失败；实际CI smoke含Java8/17/21真实编译运行与helper隔离通过 |
| 广泛API | 一轮132/132 checker×语言Run及12/12正式语言通过，随后meta发现共享DTO解码错误；已修，新整轮正在复测，后续未完成不能算通过 |
| 容量 | 20/50/100活跃、500在线75秒各语言/总体100%有效，p95 .488/.462/.542秒；mixed通过；持续第1轮Java85.33%/p95 1.070秒未达门槛，900秒未完成，正在定位JDT生命周期 |
| 恢复/故障/回滚 | 专属graceful/crash脚本已准备，最终新候选尚未执行；Redis共享整栈故障不混入负载 |

工程参考是每语言和总体validRate>=95%、validP95<=1秒，同时保留allP95与降级/null；不能称所有请求p95<1秒，也不能把参考改称正式业务SLO。15分钟累计稳态也不是24小时长稳。

## 发布顺序与回滚

1. 冻结精确本地提交、镜像/registrydigest、源码/工件hash、配置与schema依赖。先发布sandbox与server-private依赖提交，再发布引用它们的Judger。跨私有仓库CI要求只读SDUOJ_SERVER_SOURCE_TOKEN，缺失失败关闭；本机gh未登录，尚不能核对secret实际是否配置。
2. 按migrations/online-ide/README顺序备份并应用additive表/索引；独立dev已只读确认9表/6索引/1列与checker MEDIUMTEXT。回滚不drop表，不改历史正式结果。
3. 完成整个新候选功能/安全/容量/持续运行/恢复与artifact回滚，生成R8专属资格锁。历史收据只保留来源，不用于新镜像冒充通过。
4. 生产目标基础环境先具备同一内核能力与cgroup/driver，再做只读preflight和节点资格。当前主机不满足，见下节。
5. 最后审核具体候选和切换范围。排空后按兼容接口/schema服务→评测/Run→IDEWorker→Gateway入口→前端顺序灰度，不在执行中替换sandbox或重放Debug命令。
6. 正式/v2必须用已验收artifact的独立staging/SHA验证/备份/切换/smoke/rollback入口；现有release-v2-pre脚本只处理/v2-pre且会重建，不可拿它替代正式/v2发布。具体正式脚本另文准备。

回滚先停新建、保留查询/取消，确认进程树/cgroup清空后恢复上版固定镜像与配置。保留additive数据，不FLUSHDB、不清未知reservation。前端保留v2-backup并提供独立rollback；评测回退旧安全边界须显式记录，不能自动回退成答案可读来掩盖失败。

## 当前生产环境阻塞与VM路径

已只读核对sduoj-prod10.102.33.79：ARM64/64CPU/约188GiB，Ubuntu20.04.2/Linux5.4，Docker27.1/cgroupfs/**v1**。存在/sys/fs/cgroup/unified不代表Docker使用v2。Landlock version-only syscall返回ENOSYS38，新sandbox不能直接运行。

/dev/kvm可用，KVM_GET_API_VERSION只读返回12，当前账号可访问；尚未创建虚拟机。普通Docker共享宿主内核，Docker-in-Docker也不能解决；可用完整ARM64 Linux VM提供新内核，再在其中运行同一套Docker。若要求基础系统也一致，dev与生产须从同一固定guest基础盘重新验收，不能把Docker Desktop旧收据自动转给未启动VM。

详见[虚拟机环境方案](PRODUCTION_VM_ENVIRONMENT.md)。未修改生产内核/Docker/cgroup/网络/服务/数据库、未重启或创建VM，当前仅准备和只读审计。
