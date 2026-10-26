# ARM64 执行层 VM 候选合同

范围只含 IDE Worker、Judger、RunWorker。MySQL、Redis、RabbitMQ、Nacos、Filesys、Problem、Gateway 和附件保留现部署。此包没有生产流量切换入口；所有命令默认 plan，消费者仍受显式 profile 约束。生产未启动 VM。

## 固定直接内核引导

当前正式候选是 `bootMode=direct-kernel`。两个 backend 都固定：

- Debian13 ARM64 genericcloud build `20261021-2638`，原盘336265216 bytes；`source.lock.json` 记录官方 HTTPS 来源、SHA256/SHA512和无 backing QCOW2v3。没有独立发布者签名声明。
- kernel `6.12.113+deb13-cloud-arm64`，包版本 `6.12.113-1`；QEMU `10.0.13`，machine `virt-10.0,gic-version=3`。
- 16 vCPU / 24576 MiB / 120GiB overlay。dev 仅 `-accel hvf`，生产候选仅 `-accel kvm`；无自动 TCG fallback。
- 精确命令行 `root=PARTUUID=194f4bfc-04a8-48a7-868d-ebe69b12df74 ro console=ttyAMA0`。不接受任意额外 kernel arguments。
- `kernel.Image`、`initrd.img` 必须位于 owned state，真实普通文件、只读并逐字节 SHA 匹配；ARM64 Image magic 也检查。启动不使用 pflash、NVRAM 或网卡 PXE ROM。

初次 bootstrap 的 kernel/initrd 从该精确上游盘只读提取，锁在 `source.lock.json.directBoot`。它们不自动成为 prepared 盘的 boot pins：离线安装可能重建 initrd，最终必须读取安装/清理后实际 `/boot/vmlinuz-<release>` 与 `/boot/initrd.img-<release>`，保存原字节和哈希。`preparation-receipt.example.json` 的 boot 字段必须与最终配置一致。缺 disk/receipt/kernel/initrd/image pins 时 render/start 拒绝。

历史边界：HVF-only 自定义构建最初漏编 GICv3；显式 Kconfig 补丁构建以及官方未 patch 的 TCG+HVF 编译，在16CPU/GICv3的 AAVMF UEFI 路径均停在固件 WFI。失败收据保留。官方未 patch build6 仅编译包含 TCG，运行仍强制 HVF；同16CPU/GICv3直接 kernel 诊断已实际启动固定 Linux 并干净关机。这证明直接引导可用，不是原 UEFI 合同通过，也不是 prepared 盘/生产资格。

## 制品与权限

Mini 的 Linux manager build2 是冻结 Debian base/snapshot 与签名依赖原料：QEMU10.0.13、Docker Engine/CLI29.2.1、containerd2.2.1、Buildx0.31.1、Compose5.0.2，147 manager deb 与29 guest deb 各有 package/version/architecture/SHA 锁和 signed-index 取证。不能把依赖闭包校验当作 guest 实际安装成功。后续 runtime manager/vmctl 代码变化需要以该精确本地 image 为父层做离线 overlay，再保存新 image/code hashes；旧 image 不自动拥有新启动合同。registry digest 在实际另行发布前留空，不拿本地 image ID 代替。

管理容器 UID/GID 显式非root、cap_drop ALL、no-new-privileges、只读rootfs，仅 `/dev/kvm` 与自身0700 state 单一 bind；不挂宿主根目录、Docker socket、TAP 或业务数据。16CPU/26GiB管理上限容纳24GiB guest和QEMU开销，PIDs256、memory-swap等于memory。Mac 便携 bundle 在新 owned 目录核 archive/file lock、Hypervisor entitlement、codesign/otool loader 闭包；不安装宿主包管理器、不改系统 PATH。

| 执行层 | CPU | 内存 | guest cpuset / 权限 |
| --- | --- | --- | --- |
| IDE aggregate | 4 | 6GiB | 0–3，含Debug；UID10001、SETUID/SETGID、原NsJail/Landlock、own cgroup、read-only |
| Judger | 2 | 2560MiB | 4–5；root父进程、tini/固定entrypoint、SYS_ADMIN、private cgroup |
| RunWorker | 2 | 2560MiB | 6–7；同Judger，独立节点号/端口 |

所有执行服务禁额外 swap。VM边界不替代内部 sandbox；上述额度未证明500在线/100活跃，须在最终 guest/image/network 全profile下重新验收。

## 网络阶段

`networkPhase=bootstrap`：QEMU user-net 显式 `restrict=on`，阻止guest到host/外部IP路由，保留显式loopback hostfwd。初次dev-bootstrap仅SSH，manager另有loopback health；默认 executor compose 为空服务，无法误启动。`package_update=false` 不能替代整体出网隔离；进入guest记录并停用专用guest的apt自动更新timer，避免制备漂移。

`networkPhase=integrated`：不加restrict，但必须另行填写并审批真实host内网IPv4、healthBindAddress=advertiseAddress、独立Judger/Run端口和各服务端点。禁止0.0.0.0、公网、guest NAT10.0.2.15或host alias10.0.2.2作为discovery身份。SSH始终loopback；现有80/443不动。配置显式绑定 Redis DB2/prefix、独立Rabbit vhost/fixture、Nacos namespace/dataId及无冲突Snowflake节点。Java命令也绑定host/port/vhost和discovery.ip/port。不能让远端Nacos覆盖回正式队列。

从真实Nacos/Gateway网络位置请求新health/ready并核注册、heartbeat与地址；TCP可达不等于RPC认证。详细联网门禁见 `../../docs/VM_DEV_NETWORK_QUALIFICATION.md`。本轮仅guest制备，不接这些业务网络或消费者。

## 首次独立 dev 制备

复制 `dev-bootstrap.example.json` 到Git外0600文件，填固定源盘、native bundle/lock、初始bootDirectory、公钥与新的短0700 state。公钥可进cloud-init，私钥仅放host专属0600文件，不进guest/cloud-init/Git/log。config精确限制fields及初始上游boot pins。

```bash
python3 deployment/vm-execution/dev-bootstrap.py plan --config /private/bootstrap.json
python3 deployment/vm-execution/dev-bootstrap.py prepare --config /private/bootstrap.json --execute --confirm-instance sduoj-execution-dev-bootstrap-EXACT_NAME
python3 deployment/vm-execution/dev-bootstrap.py start --config /private/bootstrap.json --execute --confirm-instance sduoj-execution-dev-bootstrap-EXACT_NAME
```

prepare/start核源盘双hash、native bundle、boot assets、seed和overlay身份；拒绝已有runtime/QMP记录，不重启失败目录。实际argv/launcherSHA/PID/退出码留档。唯一运行方须先核实际可用CPU/内存与其他任务窗口；Mac critical压力拒绝。不同失败/候选使用新instance/state。

首次SSH必须先从本实例serial/console拿Ed25519 host fingerprint，再与ssh-keyscan对应key精确匹配，写独立0600 known_hosts。随后仅StrictHostKeyChecking=yes、禁password/agent forwarding；不得accept-new或关闭校验。

在guest内建root-owned0600、stage=dev、匹配marker/name的私有安装配置；配置boot字段先绑定实际启动的上游字节。校29个离线deb及metadata：

```bash
sudo python3 guest-install.py --config /private/install.json --package-lock /private/guest-packages.lock.json --deb-directory /private/debs --apply --confirm-instance sduoj-execution-dev-bootstrap-EXACT_NAME
sudo python3 guest-preflight.py --config /private/install.json --preparation
```

安装保留 `--no-download --no-remove --no-install-recommends`，不在线补依赖。Docker daemon 使用本包cgroupfs配置。preparation探针仅dev、禁止`--network`，核实际kernel/config、Landlock ABI≥3且active、pidfd/close_range、Docker29.2.1/cgroup2/cgroupfs和控制器，并记录实际/boot字节hash、kernel包版本与CPU。它不要求伪造尚未生成的prepared盘/registry pins，不给workload资格。

收cloud-init、dpkg清单、daemon config、package lock、实际kernel/initrd/config bytes；通过guest安全poweroff并记录QEMU退出。下一步先审身份清理清单，再清cloud-init/host keys/私有制备材料，干净关机，将overlay转成无backing的新独立QCOW2并0400/hash。不得在运行时复制盘，不得提前把下载/诊断叫prepared盘。

## 从冻结 prepared 盘生成候选

最终配置 `deployment.example.json` 的boot字段只能引用安装/清理后实际kernel/initrd；state下同时提供只读 `prepared-guest.qcow2`、`kernel.Image`、`initrd.img` 与0600 preparation收据。收据绑定同boot字节/命令行、disk/upstream/kernel包/config/Docker/包锁hash，状态只能PREPARED_NOT_GUEST_QUALIFIED。

```bash
python3 deployment/vm-execution/vmctl.py plan --config /private/config.json
python3 deployment/vm-execution/vmctl.py render --config /private/config.json --output /private/new-owned-state
python3 deployment/vm-execution/vmctl.py verify-assets --config /private/config.json
# 显式独立dispatch才可执行：
python3 deployment/vm-execution/vmctl.py prepare --config /private/config.json --execute --confirm-instance sduoj-execution-EXACT_NAME
python3 deployment/vm-execution/vmctl.py start --config /private/config.json --execute --confirm-instance sduoj-execution-EXACT_NAME
```

生产stage额外要求0600 `--authorization`，绑定operation=VM_STAGING_APPROVED、精确instance和规范配置SHA。该guard防误触，不是用户签名安全边界。生产KVM未启动、guest内核/CPU/GIC资格仍需实际验收；dev HVF通过不能代替它。

最终guest还需完整四语言LSP/Debug API/browser/隔离、业务六场景、Run/formal/答案隔离、容量/混合/900秒稳定/恢复/crash门禁，绑定同盘/kernel/initrd/config/Docker/镜像/端点。此前DockerDesktop/R8结果仅历史功能基线。启动消费者、队列切换、registry发布、生产上线均为独立明确动作。

## 制品构建及停止

`build-artifacts.py` 默认plan，显式 `--execute-build --output NEW --owner OWNED --memory-mib 768` 才在Mini的独立1CPU/768MiB builder解析固定签名依赖。`native-build.py` 默认plan；显式单job nice10只构建工具，不启动VM；官方QEMU source signature、编译器/SDK/依赖与bundle hashes全部记录。`native-bundle.py stage/verify --runtime-checks` 验相对dylib闭包和签名；仅编译包含TCG不等于运行允许fallback。

停止先guest安全shutdown；TERM经私有QMP请求system_powerdown，未确认则保留overlay并检查。固件尚未进入guest的QMP quit只能记录为受控诊断退出，不能叫guest clean shutdown。旧失败、runtime、source与receipt不删除、不改写；不自动prune/down或清其他会话资源。

```bash
python3 -m unittest discover -s deployment/vm-execution -p 'test_*.py' -v
```

静态guard测试不启动VM，不替代真实安装/引导/业务验收。
