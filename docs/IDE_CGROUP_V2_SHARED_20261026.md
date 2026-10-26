# ARM64 cgroup-v2 统一权限配置

> 下文“已完成验收”是 R7 历史节点记录。当前集成候选为 R8，外部 guardian CPU 计量已修正；R7 资格锁不能用于 R8。当前状态、源提交和最终完整整栈收据统一以 [集成发布入口](COMBINED_RELEASE_20261026.md) 为准。

用户确认 dev 与生产采用同一权限配置；连接地址、私有凭据、Nacos/Redis 命名空间和每实例身份分别提供。本轮仅操作隔离工作树与自有 dev，不修改生产。

## 运行合同

- ARM64、Linux cgroup-v2、Docker **cgroupfs** driver；systemd driver 当前拒绝，不能直接复用路径语义。
- 统一入口：compose.ide-worker.cgroup-v2.yaml。R6 新权限失败已保留；最终镜像使用本轮实际验收身份。
- Worker 从启动即 UID/GID10001，不使用 privileged、SYS_ADMIN、宿主PID/network或Docker socket。bounding capabilities仅SETUID/SETGID，Worker CapEff=0。
- 外层seccomp/AppArmor与systempaths放宽用于嵌套user/mount/PID/network namespace。这不是外层syscall最小白名单。用户代码仍由固定NsJail和内层seccomp限制，adapter/target降为namespace UID65534、capabilities0、NoNewPrivs1。
- 外层NoNewPrivs=0是filecap helper要求；不改变用户程序NoNewPrivs1。Compose早期注释setuid为历史措辞，实际R7两个helper均为精确filecap。
- SDUOJ_IDE_DEV_DEBUG_LAB=0；外部只读qualification manifest，不用开发开关自动放行。

## CPU/内存总额

    root-owned aggregate：4CPU / 6GiB / 1024PIDs / swap0
      Docker CID 子组：Worker + LSP
      debug 兄弟组：1CPU / 1.5GiB / 512PIDs
        guardian-sid 与 sid

LSP文档48/48/32/32，clangd-j2，JDTLS2处理器/384MiB，concurrency2/2/1/2。Debug预算、产品编译和运行时限不变。

总量只读取aggregate memory.current/events/cpu.stat/pids.current。Docker stats只覆盖管理CID，不作为整体内存证明。Debug仍受同一6GiB总额限制。

容器使用host cgroup namespace，但只bind自身aggregate子树，不暴露宿主整棵cgroup树。aggregate根目录和总limits由root持有，Worker不可写；只委派共同祖先cgroup.procs及debug子树必要文件。每Worker独占aggregate，禁止Compose scale共享父组。

## 真实失败与修复

新权限R6首轮四语言LSP通过，Debug均失败。private stderr为newgidmap open gid_map EACCES，并非编译器、内存或时限问题。

有界AB：仅SETUID/SETGID的原setuidhelper为EACCES；加DAC_OVERRIDE变为write EPERM，仍失败。原helper相同字节去setuid，分别设置cap_setuid=ep/cap_setgid=ep，保留EUID10001 namespaceowner后真实映射成功。随后原NsJail在nested proc挂载失败；systempaths=unconfined后固定innerpolicy中的id成功。

R7从R6派生，仅修改cgroups.py helper前置检查及两个原helper mode/xattr，编译器、Judger rootfs/native sandbox、业务修复、资源不变。检查拒绝非rootowned、组/全局可写、symlink、混合setuid+filecap、额外cap及inheritablebits。锁同时记录内容SHA、mode、ownership和完整xattr。

## 部署顺序与边界

1. 管理员确认ARM64、cgroup-v2、cgroupfs、祖先控制器。setup默认只读；审核后为全新独占sduoj-ide实例执行apply，不修改其他服务/全局控制器。cgroup目录重启后需重新配置。
2. 提供环境独立0600连接env、唯一身份、网络和rootowned只读qualification目录。
3. 同一Compose启动1Worker；runtime_check核对镜像、driver、UID、权限、parent、挂载及独占性。
4. 实际子进程迁组→两轮四语言API→browser→隔离→容量/混合→恢复。candidate manifest明确notaccepted；不只改verified冒充验收。
5. release脚本在原始收据全部通过后生成hash绑定的不可变节点qualification；不自动激活生产。生产新节点仍需本地资格检查，不能仅复制dev路径或收据。

本轮证据：work/artifacts/ide-cgroup-v2-shared-20261026。本轮结果见下节；历史R6/R5范围不变。

## 已完成验收结果

- R7 image ID：sha256:8d1fc4807aea8fde1e761dab68c24fb2fb5bd4848206e5841275214e6cd3b83c；父R6：sha256:aed4d073a034464126a18b21c2c6c88d3af974bc63654efddbe21d81759fb4bf。
- 原native SHA仍为5e349e70d163c365ce81001cbf8ff931c57ad5982420e448c852440001086015；helpers二进制内容SHA保持原值，仅mode/xattr变更。Worker全套154passed/51 inherited warnings；deploy定向30passed，另有既有asyncio fixture deprecation。
- 两轮完整四语言API通过；真实四语言browser4passed/0skip/0retry；8项API边界通过。
- 同一配置500online，20/50/100active分别600/1500/3000有效样本，均100%；overall validp95为0.509/0.485/0.618s，各语言都达当前参考。500/500sessions清理。aggregate采样峰值2,020,409,344bytes，无max/OOM。
- 真实PythonDebug目标12项隔离检查通过：UID65534、capabilities0、NNP1、seccomp2、不能恢复root、只读rootfs、禁外网、私有PIDnamespace、supervisorroot不可访问、隐藏Docker/cgroup。
- 混合：500online/100active+恰好1JavaDebug，实际steady overlap25.898s、暂停20.000s、step去重/stdin/ECHO47及cleanup成功。总体2988/3000=99.6%有效，validp95 0.794s。Java288/300=96%，9degraded+3null；Java validp95 0.943s，all-outcome p95 1.206s。C/C++/Python均100%。aggregate峰值2,784,317,440bytes，无max/OOM。
- 上述混合结果通过的是原工程参考validRate>=95%、validp95<=1s，不能称100%无降级或“所有请求p95<1s”。不外推active2/resident8任意组合，也不把当前工程参考改称正式生产SLO。
- 一次受控SIGTERM/exit0/同CIDstart，五组件epoch和reservation incarnation更新；旧现场clean、旧命令410fenced、旧step ledger不变；新现场step/watch/stdin/ECHO47和cleanup通过。不是SIGKILL/crash/Redis中断验收。
- qualified-node-bundle已由原始收据验证生成，status=NODE_QUALIFIED_NOT_PRODUCTION_ACTIVATED。自有dev已安装root-owned0444qualifiedmanifest并关闭developer自动放行；权限probe实child迁移通过，总limits不可写。最终安装后四语言API复测另存r7-qualified-final-1，四语言LSP/Debug全部通过；最终ready/running、四语言documents0、Debug全部资源0。

### 保留的非通过记录

- 原R6新权限全部Debug失败是真实helper权限失败。
- R7 isolation attempt1的目标访问/proc/1/root被EACCES拒绝，测试未捕获PermissionError而崩溃；修复仅测试异常处理，attempt2通过，产品不变。
- R7 recovery attempt1旧现场清理、epoch、fence通过，随后rawHTTP replay没有更新Client.last，紧接创建触发Gateway100ms限流quietnull；测试恢复正常360ms节奏后attempt2通过，没有create重试、产品限流或时限修改。
- 早期Compose flow-sequence引用未加引号、resume变量缺失和规范化false被省略为schema/setup失败，均发生在停旧Worker前；不计入产品运行通过。BuildKit将本地imageID误作registry标签；改用无网络legacybuilder固定本地ID成功，不拉取新依赖。

### 上线范围

统一配置已在当前ARM64/cgroup-v2/cgroupfs节点资格化，生产连接/凭据/namespace不复制dev SSH拓扑。生产节点需同一driver/权限资源树及本地资格检查。长稳、SIGKILL/控制面故障、生产灰度和多Worker扩容仍未执行，且没有提交、registry发布或生产开关修改。每个新副本须独立aggregate和身份，不得scale共享父组。
