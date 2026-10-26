# 使用虚拟机统一 dev 与生产环境

当前结论：普通 Docker 容器不能替换宿主机内核。可以由专用 ARM64 Linux 虚拟机提供内核，再在虚拟机内运行同一套 Docker 制品和配置；如果需要统一管理入口，可以让一个仅管理该虚拟机的容器运行 QEMU/KVM。这依然是虚拟机方案，不是 Docker-in-Docker 补齐内核能力。

官方边界：[Docker containers share the host kernel](https://www.docker.com/resources/what-container/)，[Docker Desktop Engine runs inside a Linux VM](https://docs.docker.com/desktop/features/networking/)，[Docker cgroup version follows host configuration](https://docs.docker.com/engine/containers/runmetrics/)。

## 已核实的现有生产条件

2026-10-26只读检查sduoj-prod：ARM64、64CPU、约188GiB；当前Ubuntu20.04/Linux5.4、Docker27.1/cgroup-v1。Landlock version-only syscall返回ENOSYS38。本次未创建ruleset、未改变权限或任何宿主机配置。

/dev/kvm存在，当前SSH账号可读写，KVM_GET_API_VERSION只读ioctl返回12，说明有可用虚拟化接口；尚未创建VM或验证完整guest启动。约537GiB根文件系统空闲。当前未安装QEMU、qemu-img、cloud-localds或AAVMF固件，也无Node。若采用容器管理VM，需要把这些依赖装入固定的管理镜像，而非直接修改线上宿主机包。

## 固定启动方式

正式候选改为 `bootMode=direct-kernel`：HVF/dev与KVM/生产均使用同盘实际kernel.Image/initrd.img、精确root PARTUUID和命令行 `root=PARTUUID=194f4bfc-04a8-48a7-868d-ebe69b12df74 ro console=ttyAMA0`；16vCPU/24GiB/120GiB、virt-10.0/GICv3不降格。两个backend均显式单值accelerator，不允许TCG自动fallback。启动不依赖pflash/NVRAM或PXE ROM；保留AAVMF制品不代表UEFI已通过。

MBP的原UEFI16CPU引导停在固件WFI，失败收据保留。相同官方QEMU10.0.13、同kernel/盘、16CPU/GICv3直接引导诊断已实际进入固定Linux并干净关机；它不是生产KVM资格。初始kernel/initrd来自精确上游盘，最终prepared锁必须重新取安装/清理后实际/boot字节及hash、kernel包/config，不能假设initrd未被dpkg重建。缺boot pins/任意额外kernelargs时启动拒绝。源码包见 `../deployment/vm-execution/README.md`。

## 一致性合同

镜像/依赖、权限、安全内核能力和资源设置都要固定。仅固定业务镜像digest不足以称环境一致；需要同时记录guest基础盘SHA、guest kernel/config、Docker版本和cgroup-v2/cgroupfs driver、AppArmor/LSM/usernamespace、CPU架构、父cgroup控制器和各服务资源限额。

Mac Docker Desktop的LinuxKit与生产拟采用的普通Linux发行版不是同一个基础盘。若要求基础系统本身也完全一致，dev与生产应改为从同一个固定guest基础盘启动；Mac与生产的硬件加速后端可以不同，但必须各自完成同一资格测试。不能把已有Docker Desktop测试直接当作尚未启动的生产VM通过。

首次虚拟机建议配置可先评审16vCPU/32GiB内存/120GiB独立磁盘，运行本轮完整单Worker stack；这是待验证的容器外层容量建议，不是新的性能承诺。IDE仍保持单实例4CPU/6GiB/1024PIDs，Judger与Run各2CPU/2560MiB，并保留彼此独立执行核。实际guest配置须用同一个业务负载验收后再冻结，不从生产宿主空闲内存直接推导性能。

## 分阶段准备与切换

1. 固定一个ARM64 guest基础盘及kernel/config（具备实际必需的Landlock/close_range/pidfd等能力），安装固定Docker并明确cgroup-v2/cgroupfs。先生成可校验、可备份的只读基础盘，不在生产临时apt升级。
2. 准备专属可写overlay磁盘、只读cloud-init身份材料和管理配置。管理容器仅访问/dev/kvm与自己的磁盘目录，不挂宿主根目录、Docker socket或现有业务数据；新VM初期端口只bind loopback，绝不占用当前80/443。
3. 在dev从同一基础盘启动guest，导入这次已测镜像、私有独立Nacos/Redis/Rabbit/数据库配置，完整重新验收。当前Docker Desktop测试作为功能基线保留。
4. 生产仅新建独立VM与专属网络/磁盘，先只读环境探针及隔离fixture，完成同一权限/功能/容量/恢复资格。现有服务保持原流量，生产数据库迁移/同步与维护窗口另作明确计划。
5. 仅在目标VM、具体制品digest、备份与回滚演练全部通过后切换入口；回滚只恢复旧入口与对应服务版本，不修改旧宿主机内核。

## 尚未执行

未创建生产VM、未下载/固定guest基础盘、未安装QEMU、未改生产Docker配置、未迁移数据库、未更改80/443或OpenResty。当前KVM接口可用不等于guest和本业务已验收。具体guest基础盘、网络、持久化与切换窗口需在最终部署前确认；本轮先把完整隔离dev问题与回归闭环。

## 可选迁移范围

如果近期目标是避免搬动已有生产数据库和附件，可先把需要新内核的执行层（IDE Worker、Judger、RunWorker）放进新VM；Gateway/业务Java服务及MySQL/Redis/Rabbit/Nacos保留既有部署位置，使用明确的内网地址连接。这样需要验证跨VM网络延迟、队列/文件RPC和精确权限，不能直接沿用本机全同网容量数字。

如果目标是整个stack的基础环境也一致，则在VM部署完整stack，并单独设计生产数据迁移、增量同步、入口切换与回滚。用户已选择第一条：先统一执行层，保留现有数据库与业务服务。完整stack迁移不在本次生产VM范围；本轮不会复制生产数据库或改变现有数据服务位置。

## 已确定的生产范围

用户确认先统一执行层：IDE Worker、Judger、RunWorker。当前正准备固定guest基础盘、私有连接配置与资源合同；VM尚未启动，跨VM真实RPC/队列/性能验收尚未执行。执行层VM应明确连现有Nacos、Redis、Rabbit、Problem与Filesys的内网端点；生产业务Java服务的兼容版本发布仍按联合发布顺序进行，但不搬迁这些服务的宿主位置。
