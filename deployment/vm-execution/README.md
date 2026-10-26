# ARM64 执行层 VM 部署候选包

范围固定为 **IDE Worker、Judger、RunWorker**。现有 MySQL、Redis、RabbitMQ、Nacos、Filesys、Problem、Gateway 和其他业务服务保留原部署；本包不迁移数据库/附件、不改宿主内核、不改现有 80/443、不切换流量。所有配置默认只读 plan，生成配置也不会启动 VM 或消费者。

本包是可审阅的准备结果，尚未启动任何 guest。生产只读事实：ARM64/64 CPU/约188GiB，Linux5.4/cgroup-v1；`/dev/kvm` 当前账号可访问且 KVM API=12；约537GiB根盘空闲；缺 QEMU、qemu-img、cloud-localds 和 AAVMF。管理镜像把这些依赖隔离在自己的容器中，不对旧宿主执行 apt 或 reboot。现有主机业务服务使用 host network，因此 guest 连接显式内网 host IP+原服务端口；不能复制 MacBook/Mini SSH 转发地址。

## 固定基础盘与尚未冻结的部分

`source.lock.json` 固定 Debian 官方 build `20261021-2638`，ARM64 genericcloud QCOW2 336,265,216 bytes；下载前已固定 SHA512，下载后同时固定 SHA256，检查 QCOW2v3 header 无外部 backing。官方元数据列出 `linux-image-6.12.113+deb13-cloud-arm64`、包版本 `6.12.113-1`。基础盘已本地下载验证，但未启动、未挂载文件系统，不能把元数据当作实际 guest syscall/LSM 验收。

来源与配置依据均为官方资料：[Debian13 ARM64/6.12 release notes](https://www.debian.org/releases/trixie/release-notes/whats-new.en.html)、[固定 cloud build](https://cloud.debian.org/images/cloud/trixie/20261021-2638/)、[同目录 SHA512SUMS](https://cloud.debian.org/images/cloud/trixie/20261021-2638/SHA512SUMS)、[QEMU ARM virt/versioned machine](https://www.qemu.org/docs/master/system/arm/virt.html)、[QEMU user-network/hostfwd](https://www.qemu.org/docs/master/system/invocation.html)、[Docker Debian13 ARM64 安装与指定版本](https://docs.docker.com/engine/install/debian/)、[Docker cgroup-v2 默认 driver 差异](https://docs.docker.com/engine/containers/runmetrics/)。checksum 从官方 HTTPS 取得；没有宣称已核验独立发布者签名。

```bash
# 默认不联网、不写盘；verify 只读既有下载文件。
python3 deployment/vm-execution/fetch-source.py
python3 deployment/vm-execution/fetch-source.py verify --file /absolute/path/to/frozen-source.qcow2
# 只有明确 download 才下载；目标必须不存在，部分文件保留，不自动覆盖/继续。
python3 deployment/vm-execution/fetch-source.py download --file /existing/private/directory/frozen-source.qcow2
```

以下 pins 刻意留空，**renderer/start 会拒绝未填写的模板**，不把 `latest` 或未启动的原盘伪称正式环境：管理镜像 registry digest、实际QEMU10.0 patch核验、AAVMF_CODE/VARS hashes、准备后的独立 guest 盘 hash、准备收据 hash、Docker 离线包及依赖闭包 hash、两个执行镜像 registry digests、审批后的内网端点/身份。`manager-build.lock.json` 另列官方Debian ARM64 index查到的QEMU10.0.13及固件/工具包精确候选；该index未在本轮做apt签名和snapshot闭包实证，仍不是已构建锁。Docker Engine `29.2.1` 是当前 dev Engine 的候选对齐值；其 Debian ARM64 包及依赖的可得性和完整离线安装仍待实证。缺包时停在准备阶段，不能擅自升级版本后沿用旧收据。

## 资源与权限合同

| 层            | CPU     | 内存    | 其他                                                  |
| ------------- | ------- | ------- | ----------------------------------------------------- |
| guest 候选    | 16 vCPU | 24GiB   | 120GiB overlay，单独冻结基础盘                        |
| 管理容器上限  | 16 CPU  | 26GiB   | guest24GiB加QEMU开销；PIDs256                         |
| IDE aggregate | 4 CPU   | 6GiB    | PIDs1024；guest CPU0–3；Debug也在同一父限额与cpuset内 |
| Judger        | 2 CPU   | 2560MiB | PIDs1024；guest CPU4–5                                |
| RunWorker     | 2 CPU   | 2560MiB | PIDs1024；guest CPU6–7                                |

执行配额合计8 CPU/11GiB，其余 guest CPU/内存留给内核、Docker、文件缓存及管理进程。16/24/120 是待验候选，不代表已证明500在线/100活跃；必须在同 guest 盘和跨VM真实网络下重新测量。guest vCPU 分区不是物理宿主专核承诺，宿主调度/争用必须纳入容量证据。

IDE保留UID/GID10001、cap_drop ALL、SETUID/SETGID、host cgroup namespace、只绑定自己aggregate、read-only rootfs、原NsJail/Landlock合同和原tmpfs；不启用dev root bootstrap。Judger/Run保留root父进程、tini→固定entrypoint、SYS_ADMIN、private cgroup、AppArmor unconfined及真实sandbox权限；不能把父进程root误写成sandbox内root。VM边界不代替这些内部合同，模板/权限/镜像改变都须重新资格验证。

管理容器则非root、cap_drop ALL、no-new-privileges、read-only rootfs，仅映射 `/dev/kvm` 和自身一个0700磁盘目录；不挂宿主根目录、Docker socket、业务数据或 `/dev/net/tun`，不使用 privileged。host network 只承载QEMU显式hostfwd；没有NET_ADMIN，不创建桥/TAP，不修改宿主路由。

## 网络分两阶段，禁止错误 discovery

`networkPhase=bootstrap` 是默认值：SSH固定绑定 `127.0.0.1:<显式端口>`；health只绑定loopback。生成的 executor Compose 是空服务 stub，无法误启动执行消费者。适合guest启动/基础环境检查，不是生产可用数据面。

`networkPhase=integrated` 必须另行填写并审批健康端口私网绑定：`healthBindAddress` 与 `execution.advertiseAddress` 必须是同一个真实 host 内网 IPv4，端口使用同一显式 healthPort。QEMU 把该地址/端口转发到guest同端口；guest IDE使用host network，在同端口监听，`NACOS_IP`注册host私网地址。SSH始终loopback。禁止0.0.0.0、公网bind或登记guest NAT的10.0.2.15；guest→host的10.0.2.2 alias也不能充当已审批服务地址。Judger/Run使用不同的显式server/discovery port，并把Java Nacos discovery.ip注册为同一个审批host私网IP；QEMU也分别转发这两个端口，防止guest host-network下两个Java服务默认8080冲突。示例39086/39087/39088只是候选，不是已获批生产端口。新端口不开放公网，需由网络审批确认仅Nacos/Gateway/运维来源可达，本工具不修改firewall。

guest→既有Nacos/Redis(DB2)/Rabbit/Filesys/Problem/Run RPC使用明确内网IP与端口。Nacos返回的Filesys/Problem等discovery地址还要逐个核对可达；仅TCP探针通过不代表RPC认证正确。Nacos/Java SDK可能使用附加RPC端口，应按部署版本收集实际连接并单独确认可达。Redis的host/port/DB2/prefix必须与Gateway完全一致；先执行既有 `scripts/ide_connection_preflight.py`，再验证真实鉴权与transport。队列初验只使用本任务owned vhost/fixture与独立账号，并在Rabbit端只授予该vhost权限；Java命令行也显式绑定已配置host/port/vhost。启动前核Nacos有效配置，不能让bootstrap远端覆盖引回正式队列；不能启动消费者去抢原生产队列。示例Snowflake26/27必须与保留业务的全局节点登记核对，不能仅核Judger/Run彼此不同。

反向验收必须从原host上的Nacos/Gateway网络位置请求 `http://审批内网IP:healthPort/ready`，再核对注册/heartbeat中的精确ip+port+workerId，并执行真实Gateway→Redis→Worker及Judger/Run→队列→RPC闭环。Nacos仅控制面、业务走Redis也不能豁免错误健康地址。

## 分阶段构建、冻结与启动

1. **离线制备原料。** 在独立dev制备工作区，核源盘checksum；从官方apt签名元数据固定Docker29.2.1、containerd/runc、Compose/Buildx及完整依赖deb字节，填写 `guest-packages.example.json` 的新私有副本，状态改为 `OFFICIAL_APT_DEPENDENCY_CLOSURE_FROZEN`。保留apt Release/InRelease/key fingerprint和包hash；不能用浮动安装脚本。管理镜像用 `manager.Dockerfile`，提供带digest的Debian基础镜像、明确snapshot时间及4个非空包版本buildargs（覆盖5个包），在隔离构建机生成ARM64镜像，导出dpkg清单/QEMU版本/两份AAVMF hashes，并固定registry digest。此包未构建管理镜像。
2. **只在独立dev guest制备Docker盘。** 从已校验原盘创建临时overlay，使用上述固定QEMU/firmware和同版本virt machine引导；这一步也必须显式批准/记录，未包含在本次只读准备中。通过只含公钥的cloud-init建立独立身份，写 `/etc/sduoj-execution-vm` 标记。原cloud盘无Docker，所以不能直接充当preparedGuest。`guest-install.py`在dev guest内默认只核离线包；只有 `--apply --confirm-instance 精确名称`、root、ARM64及匹配标记才安装，禁止生产staging guest临时安装。配置 `/etc/docker/daemon.json` 为本包的cgroupfs driver；不改旧物理host。按固定kernel config启动并验证Landlock激活；若官方cloud内核未启所需LSM/功能，停止并选择另一个经过批准且同样固定的guest盘，不能只降级探针。
3. **冻结prepared盘。** 禁止在镜像内保留私钥、生产secret、持久cloud-init instance identity或旧SSH host keys；清理前先保留dev身份取证，执行guest干净关机。用固定 `qemu-img convert -O qcow2` 将制备overlay转成无外部backing的独立新盘。核查无backing，设为0400并计算SHA256。完成 `preparation-receipt.example.json`，绑定上游SHA512、磁盘SHA256、实际内核/Docker版本、`dpkg-query -W`、kernel config和daemon config hashes；状态只能是PREPARED_NOT_GUEST_QUALIFIED。计算该收据自身SHA256，填写配置的空pins。制作的新盘需Macdev与LinuxKVM共用同一字节，不从两个环境各自apt安装后宣称一致。
4. **生成受控bundle。** 复制 `deployment.example.json` 到Git外私有文件，chmod0600；填pins、精确身份和审批内网地址，选择新的不存在的stateDirectory。`render`生成目录0700、文件0600，包含compose、无secret的cloud-init公钥/metadata和文件hash receipt。把冻结prepared盘复制到该目录的 `prepared-guest.qcow2`(0400)、收据复制为 `preparation-receipt.json`(0600)。state所属UID/GID需与managerUid/Gid及当前执行账号一致；KVM GID必须来自实际 `/dev/kvm`，不可照抄示例0。

```bash
python3 deployment/vm-execution/vmctl.py plan --config /private/config.json
python3 deployment/vm-execution/vmctl.py render --config /private/config.json --output /private/new-owned-vm-state
python3 deployment/vm-execution/vmctl.py verify-assets --config /private/config.json
# 以下会创建overlay/seed或启动VM；本轮未执行。必须另行明确dispatch。
python3 deployment/vm-execution/vmctl.py prepare --config /private/config.json --execute --confirm-instance sduoj-execution-EXACT_NAME
python3 deployment/vm-execution/vmctl.py start --config /private/config.json --execute --confirm-instance sduoj-execution-EXACT_NAME
```

生产staging额外要求0600的 `--authorization /private/authorization.json`，内容为 operation=`VM_STAGING_APPROVED`、精确instance、配置规范JSON的SHA256（`vmctl.config_hash`）。这是最终dispatch绑定，默认模板不包含此授权。该guard是本地操作防误触，不是用户身份签名或不可绕过的安全边界。

5. **guest内执行前置验证。** 将本目录工具和已审阅的完整deploy脚本包复制进guest专属目录，保留各commit/hash。guest config及env均0600、private目录0700；secret通过已核SSH host key的加密连接独立注入，不在cloud-init、Git、命令日志或console中。`guest-preflight.py --config ... --network`只读核ARM64、精确kernel/Docker、cgroup2/cgroupfs、Landlock ABI≥3/LSM、close_range/pidfd及明确端点TCP；它不证明认证。`guest-cgroup.py --config ...`默认只读，显式 `--apply --confirm-instance ...`才在匹配的专用guest建立一次性4CPU/6GiB aggregate，并把父/Debug cpuset都限制0–3。该工具只对专用guest root启用控制器，不可在旧host执行。
6. **guest业务资格。** integrated网络审批通过后，使用专属候选profile与owned Redis前缀/DB2、Rabbit vhost/fixture部署3执行服务；Compose全部受 `explicit-executor-start` profile约束，默认up不会启动。此目录不提供绕过node qualification的生产流量切换入口。两轮四语言LSP/Debug API、4浏览器、6业务、Run/formal/答案隔离全矩阵、500/20/50/100容量、混合Debug、长稳、故障/恢复都要在新guest重跑；按现有release gate脚本生成**绑定新guest基础盘+kernel/config+Docker+权限compose+镜像**的资格，不引用DockerDesktop/R7/R8旧锁抵扣。资格期间生产消费者保持原流量，任何正式队列/入口切换单独审批。

## Mac dev 路径与当前事实

本机只读：ARM64、`kern.hv_support=1`；未安装qemu-system-aarch64、qemu-img或cloud-localds；无 `/dev/kvm`。现DockerDesktop29.2.1运行LinuxKit6.12.69/cgroup2，不是固定Debian guest；未证实其nested KVM可用，不把容器内TCG模拟作为容量验收。需要独立原生HVF dev VM，或另一个具备KVM的专用dev节点。此次没有安装Mac宿主依赖。

`manager.py plan --state /private/owned-state --backend hvf --firmware-code /absolute/frozen-code.fd --firmware-vars /absolute/frozen-vars.fd`默认只读；原生HVF的prepare/start同样要求`--execute --confirm-instance`，只允许stage=dev，完整核同一prepared盘/firmware hashes和QEMU patch。HVF用virt-10.0/GICv3，KVM用同版本machine/GIC host；两种加速后端分别记录CPU特性及资格。Mac必须有足够的可分配资源，不能在12核/不足内存的节点上把16vCPU候选的性能结果直接归为生产容量。这里没有TCG自动fallback。

### 首次从上游原盘制备 guest

`manager.py`和`vmctl.py`只接受已有preparedGuest盘；首次安装Docker使用独立的`dev-bootstrap.py`，不需要伪造尚不存在的制备收据。复制`dev-bootstrap.example.json`到Git外0600文件，填写已验原盘、冻结native lock/bundle、仅公钥的身份和新的短0700状态路径。默认plan不读工具、不联网、不写盘。prepare只创建新私有overlay和public-key cloud-init seed，不启动guest；start仅允许ARM64 Mac/HVF及完整16vCPU/24GiB候选，不支持生产stage或TCG。只暴露loopback SSH，不启动任何执行消费者，不含业务端点和secret。

```bash
python3 deployment/vm-execution/dev-bootstrap.py plan --config /private/bootstrap.json
# 唯一运行责任方确认旧性能任务已结束及当前可用资源后，再显式执行；本轮尚未启动。
python3 deployment/vm-execution/dev-bootstrap.py prepare --config /private/bootstrap.json --execute --confirm-instance sduoj-execution-dev-bootstrap-EXACT_NAME
python3 deployment/vm-execution/dev-bootstrap.py start --config /private/bootstrap.json --execute --confirm-instance sduoj-execution-dev-bootstrap-EXACT_NAME
```

prepare核官方上游SHA256/SHA512、完整便携bundle及HVF签名，保留只读源盘副本和初始文件hash；start再核同一身份、overlay backing、seed和firmware，拒绝已有runtime/QMP记录。guest SSH host key必须从本实例串口/console核验后单独写入本任务known_hosts，不能使用关闭host-key校验的连接。进入guest后，以本实例name生成`stage=dev`的安装配置，按第2步用`guest-install.py`验证并安装冻结离线deb；不在cloud-init浮动apt安装。保留真实guest探针/包清单，再关机、清理身份并按第3步freeze独立prepared盘。bootstrap的退出和静态测试均不是guest资格；新prepared盘仍须Mac/HVF和Linux/KVM各自验收。

## Mini 可执行的唯一工件构建入口（不启动VM）

`build-artifacts.py` 默认只打印plan，不调用Docker/网络。已固定官方Debian ARM64 manifest `docker.io/library/debian@sha256:0daf3052d9359adaa0de63035b87949cc6c7966bfd6d60746d318ee1999f5edb`，来源为日期tag trixie-20261020的官方registry index；固定Debian snapshot=20261026T000000Z、QEMU10.0.13/对应固件工具包版本，Docker Engine29.2.1/CLI29.2.1/containerd2.2.1/Buildx0.31.1/Compose5.0.2。执行时apt核Debian签名及Docker官方key fingerprint并保留InRelease/index；Docker仓库为签名在线index，只有本次取回后生成的完整deb hashes锁可用于离线guest安装，不把当前候选版本表冒充完整依赖闭包。

```bash
python3 deployment/vm-execution/build-artifacts.py
# 仅父任务指定的sole monitor运行；新output子目录必须不存在，保留PID/log/exitcode。
python3 deployment/vm-execution/build-artifacts.py --execute-build --output /absolute/private/artifacts/NEW_OPERATION --owner sduoj-vm-build-UNIQUE --memory-mib 768
```

该命令仅允许ARM64本机Mac+local Unix DockerDesktop context；拒绝DOCKER_HOST/DOCKER_CONTEXT覆盖。Docker构建容器1CPU、memory=memory-swap=768MiB（允许512–2048MiB）、PIDs256，仅挂只读源码副本和自己的output，不映射KVM/宿主root/Docker socket，不启Docker daemon或VM。apt仅在该可丢弃root builder内运行。最终本地manager镜像默认USER10001:10001，运行时再按vmctl的UID/GID+cap_dropALL合同启动；保留停止builder、local image、docker-save tar、真实QEMU版本、AAVMF hashes、签名取证及完整离线deb闭包。没有registry push，因此结果是local image ID，不是可填写正式renderer的registry digest；后续push是单独授权步骤。Mini内存紧张，sole owner采用768MiB并保留失败，不停其他会话服务。

准备后的guest盘**不能通过仅下载deb或docker commit生成**：还须后续空闲时在独立MBPHVF dev guest真实安装、probe、关机、转独立qcow2后freeze。这次builder显式输出guestImagePrepared=false。原盘已可从现有verified路径只读复制，不重复下载。不在R10稳定性/性能阶段并行启动HVF。

## MBP 独立 HVF 工具包（待构建，不安装宿主包管理器）

只读证据显示MBP有48GiB/18CPU、HVF支持，但没有QEMU/qemu-img/Homebrew；Mini只有24GiB/12CPU且当前Docker实验负载密集，因此同盘dev资格优先安排MBP独立HVF，必须在当前实验结束后由sole运行方启动。本包没有启动任何MBP负载。

[QEMU官方下载页](https://www.qemu.org/download/)为Mac列出Homebrew/MacPorts和源代码构建路径，没有提供本包可直接宣称已冻结的官方便携Mac二进制。采用独立ARM64 macOS构建机提供**内部便携bundle**，不在MBP安装Homebrew、不修改系统PATH/LaunchDaemon。`native-bundle.example.json`明确为NOT_BUILT_NOT_AVAILABLE：候选QEMU10.0.13需核官方tar签名（官方fingerprint已列）、固定tar SHA256、编译器/SDK/依赖来源和配置；用与Linux管理镜像相同的AAVMF字节。所有非系统dylib须收进bundle并改为相对加载，系统绝对依赖只允许/usr/lib和/System/Library，不能依赖构建机/opt/homebrew。QEMU需ARM64并保留Hypervisor entitlement；签名/来源与完整archive hash都须冻结后才能stage。此刻该bundle尚不存在，不能宣称HVF路径ready。

```bash
python3 deployment/vm-execution/native-bundle.py plan
# 输入必须为另行冻结的真实bundle/archive；stage只写新私有目录，不运行二进制。
python3 deployment/vm-execution/native-bundle.py stage --lock /private/native.lock.json --archive /private/frozen-native.tar --directory /private/new-native-bundle
python3 deployment/vm-execution/native-bundle.py verify --lock /private/native.lock.json --directory /private/new-native-bundle --runtime-checks
# 后续sole dev方才把已验证bundle的bin放入本次进程PATH；不改系统安装。
# 使用manager.py --backend hvf --state ...及同hash firmware，显式prepare/start确认；不自动fallback。
```

隔离构建handoff：在另一台可用的ARM64 Mac构建机先下载固定 `https://download.qemu.org/qemu-10.0.13.tar.xz` 和 `.sig`，由可信官方fingerprint核签并记录source SHA256，再解包到本任务新目录。用该版本支持的SDK/Clang和完整冻结的GLib/pixman/libslirp等依赖闭包（可从官方上游源或固定Homebrew bottle取字节，须记录每个hash/许可），stage到本任务prefix而非系统路径；通过该prefix的PKG_CONFIG_PATH/DYLD相对rpath构建 `--target-list=aarch64-softmmu --enable-hvf --enable-slirp --disable-cocoa --disable-sdl --disable-gtk --disable-vnc --disable-docs --disable-download`。先用该固定版本 `configure --help` 核参数，不承诺未试过的flags；configure缺依赖即停止，禁止在线浮动补包。导出完整configure/meson日志、编译器版本、SDK版本、依赖hash和build目录摘要。复制qemu-system-aarch64/qemu-img到bundle/bin，非系统dylib到bundle/lib，用install_name_tool修成@loader_path相对引用并核otool，带Hypervisor entitlement重新codesign；AAVMF从上面的同一Linux工件输出复制，不能换另一份固件。签名会改变MachO hash，所以最后再生成files/archive SHA，填写native lock并运行runtime-checks。这条路线技术上可行但尚未实构，缺任何工具链/可迁移dylib/签名条件时报告具体阻塞，不能把Linux交叉编译产物当作已通过Mac HVF加载。MBP无Brew时优先转移已完成的便携bundle，允许的本地可逆依赖staging也必须在新owned prefix中单独记录。

runtime-checks只读核codesign/Hypervisor entitlement和otool依赖闭包，不启动VM；所需Mac系统检查工具不可用时停下，不触发自动安装。Mac seed使用系统已有hdiutil生成cidata，不需要移植Linux cloud-localds或额外安装genisoimage。原生HVF manager只允许stage=dev；生产路径仍为显式ARM64 KVM管理容器。

## 停止、回滚与证据

新VM未接生产流量前，回滚只停新消费者/VM，旧业务和数据不动。接入执行队列后需先准入关闭、排队/活跃任务排空、取消/终态/文件一致性核对，再停新消费者，恢复审批包记录的旧不可变镜像/配置/消费端；不可让新旧未经设计的消费者同时抢正式队列。回滚旧Judger会重引入答案读取风险，必须保留明确决策记录。停止VM优先在guest内干净shutdown；管理容器TERM通过私有QMP socket发送system_powerdown，120秒超时仍未退出时Docker可能强制终止，须保留overlay并做磁盘一致性检查。不要在运行时复制qcow2当一致性备份。

固定基础盘只读保留。不同候选使用新0700目录/新overlay；脚本拒绝已有overlay、seed、QMP socket或runtime记录，不自动删锁/磁盘/其他目录。停止或异常恢复后人工核对进程/实例再归档旧状态，不能盲删记录重启。没有任何自动down/prune/rm生产数据操作。

每次记录：配置/hash、上游/ prepared盘/hash、管理镜像digest、QEMU/firmware、guest uname/config/LSM/syscall、Docker/containerd/runc/cgroup、镜像OCI digest↔本地ID映射、Nacos/Gateway↔Worker的DB2/prefix/地址、服务quota/cpuset、准确样本与收据、停止/恢复状态。所有此前DockerDesktop测试仍保留为功能基线，不提升为VM资格。生产正式dispatch、端点凭据和新health私网端口尚待审批。

## 本地静态检查

```bash
python3 -m unittest discover -s deployment/vm-execution -p 'test_*.py' -v
python3 deployment/vm-execution/fetch-source.py verify --file /absolute/path/to/already-downloaded-source.qcow2
```

测试仅验证配置/权限/路径/来源/渲染/默认只读guard，不启动VM或容器；缺pins模板必须被拒绝。它们不能替代guest启动、离线安装、QEMU/KVM兼容性或新业务资格验收。
