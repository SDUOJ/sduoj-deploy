# Mini 原生 ARM64 HVF 工具实际制备

这份入口使用 Mini 已存在的 Clang21/SDK27、CMake4.1.1、pkg-config3.0.7、Python3.13.5、GLib2.88.3/Pixman0.46.4 只读依赖；不运行 Homebrew，不改系统PATH，不在MBP安装包，不启动VM。现有依赖的366个headers/pkg-config/dylib输入逐字摘要、工具二进制摘要、SDK版本和Mini型号均在 `native-build.lock.json` 固定，漂移即停止，不自动安装/升级。

当前已取回并固定QEMU10.0.13源tar（141718608B，SHA256 `4a59b74dac7ead8b162a7c4595dcbbeebe989b90c89cfe6bb4dec5447342f6fa`），官方分离签名以官方fingerprint `CEACC9E15534EBABB82D3FA03353C9CEF108B584` 验证成功。缺少的Ninja1.12.1源码、libslirp4.9.1上游release源码、Meson1.8.1纯Python wheel均已取回并固定SHA；连同现有GLib/Pixman/gettext/pcre2对应官方源码归档，合计约185MB；源码hash与现有formula记录匹配并逐字下载校验，未声称重新编译这些已有库。libslirp/Ninja/wheel的来源是对应官方发布/包索引的HTTPS字节校验，没有另称已做其发布者GPG核验。QEMU签名、源码、依赖下载和Mini只读工具前置证据在独立artifact目录，源代码/工具制备不等于HVF guest启动资格。

本机构建路线使用已存在的GLib/Pixman及其固定gettext/pcre2动态依赖，避免当前内存压力下重编全部已有库。编译过程仅写新owned目录中的venv、Ninja、libslirp、QEMU和portable bundle。QEMU以 `--without-default-features` 显式开启HVF/slirp/pixman/tools，关闭TCG、GUI、GIO/modules、docs和下载；不存在自动转TCG。编译单job，进程nice+10，每阶段有PID、完整命令、日志、超时、exitcode和`/usr/bin/time -l`峰值RSS，由唯一脚本阻塞wait，不需主会话轮询。

## 运行前提与资源窗口

1. Linux manager/Docker离线闭包sole builder先终态成功。原生脚本核其真实receipt、QEMU10.0.13版本、AAVMF_CODE/VARS文件和SHA，确保Mac/Linux使用相同firmware bytes。合法复合恢复来源已有专门reader：核所有source文件SHA、原始/权限fix commit格式以及恰好匹配的保留失败parent receipt；已用本轮真实build-2离线核通过。没有硬补sourceUnchanged=true。
2. 读取Mini原生 `memory_pressure -Q`、`kern.memorystatus_vm_pressure_level` 和vm_stat；不使用Docker Linux的MemAvailable冒充Mac host。当前观察raw pressure=2、system free32–33%、free/inactive/speculative约3.9–4.2GB。没有以任意4GiB数字作为永久门禁。执行正常level1允许；warning2须sole owner在协调停止并行重负载后显式加`--allow-warning-pressure`；critical或未知level拒绝。单个编译阶段峰值还未实测，先按单job保守运行并保留time/RSS证据，不能把候选时长视为SLO。
3. 当前native依赖minos=26.0，MiniSDK27；MBP只读已确认为macOS27.0.1，满足版本下限。但只有移交后在MBP复核codesign/loader/HVF和实际guest，才可称MBP通过。

```bash
# 默认只读核源码、依赖、工具和原生内存；不编译/写出output。
python3 deployment/vm-execution/native-build.py \
  --sources /absolute/verified/native-source-prepare

# 父任务指定唯一monitor，确认Linux工件已完成和资源窗口后才执行。
# OUT必须是新目录；无VM启动或MBP安装动作。
python3 deployment/vm-execution/native-build.py \
  --sources /absolute/verified/native-source-prepare \
  --linux-artifacts /absolute/completed/linux-builder-artifacts \
  --output /absolute/private/NEW_NATIVE_OPERATION \
  --owner sduoj-native-build-UNIQUE \
  --execute-build --allow-warning-pressure
```

估计单job Ninja约3分钟、slirp3分钟、QEMU约40分钟、portable审计3分钟，实际以receipt/time为准，QEMU编译上界2小时。构建不会自动重试或改pins；失败保留原目录，按具体错误诊断，不能通过放开下载或系统安装绕过闭包。

## 输出与验收边界

portable阶段从QEMU/qemu-img实际otool递归复制所有非系统dylib；只接受既有固定Cellar或本次构建目录的依赖，拒绝未知绝对来源/同名冲突。以install_name_tool改相对加载，重新ad-hoc签名，QEMU带 `com.apple.security.hypervisor` entitlement；附上同hash AAVMF和源码许可。生成完整文件SHA inventory、native tar/lock及source/firmware绑定收据，运行本Mini `--version`、`-accel help`（必须有hvf）、qemu-img版本、codesign严格核验和otool闭包检查。构建结束重核所有输入没有漂移。

这些检查证明的是Mini原生工具可加载并编入HVF；**不创建任何VM，不证明MBP HVF或业务工作负载通过**。Linux manager的local image、Docker离线包closure也不等于prepared guest已制备。后续先由根任务 `dev-bootstrap.py` 在明确dispatch后用同一verified原盘、同一AAVMF和本工具包建立独立dev guest，再真实安装/资格；生产仍保持不创建VM、不切换。

QEMU官方依据：[官方源代码/签名与Mac安装说明](https://www.qemu.org/download/)、[ARM virt与host CPU/HVF支持](https://www.qemu.org/docs/master/system/arm/virt.html)、[QEMU离线构建与Python依赖](https://www.qemu.org/docs/master/devel/build-system.html)。正式package传递时同时保留本轮固定源码、依赖来源和许可证，不把内部portable工具包标成官方Mac二进制发行版。
