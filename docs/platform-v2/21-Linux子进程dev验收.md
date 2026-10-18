# Linux SDK 子进程 dev 验收

2026-10-19，AutoLab 668681c，承接 [20](20-真实网关身份与端点dev验收.md)。不改生产或现有镜像/CI 发布链；组件安装集仍为空。

## 实际环境与锁

使用本机已有 python:3.13-slim 镜像（本地镜像 ID sha256:9d2e5553305c7c7b0097999bb17187c69b921ccd6bc9d40e4bb5ebe652c00285），运行 Linux aarch64、Python 3.13.15。在任务仓库外独立 venv 安装原 136 项 SDK 锁，pip check 和 SDK 导入成功；OpenHands SDK 1.55.1、LiteLLM 1.93.0。

安装后清点发现 Linux keyring 自动引入 jeepney 0.9.0、SecretStorage 3.5.0，原 macOS 锁未固定它们。668681c 新增 requirements-linux.lock，引用原共享锁并固定这两项。现有 Linux 环境应用平台锁后，138 项版本全部匹配，没有未锁定业务依赖；bootstrap pip 单列。该过程是共享锁安装后应用平台锁，不冒充平台锁的全新冷安装、带文件哈希的供应链证明或多架构镜像发布。

## 子进程协议

新增 agent_runner/test_protocol.py 仅需 SDK 解释器和标准库：

- 启动 loopback 合成父端，真实 SDK 子进程读取、提候选、finish；断言后续模型输入实际包含工具观察值，工具列表只有当前业务工具及 finish。
- 轮数耗尽返回固定失败结构，不能报成功；非 canonical 父端地址在发 HTTP 前拒绝。
- 临时 HOME/work、白名单环境、宿主 skill 标记不进入模型输入、token 不进入公开 IPC/模型正文。显式命令缺 SDK 时退出 2；普通测试收集可显式 skip，不能计作通过。

主测 host 3 PASS/8.046 秒，Linux 3 PASS/12.278 秒；Linux 测试禁外网、只读挂载代码及已安装 runtime。独立 exact archive 审计 accepted：host 3 PASS/8.013 秒，Linux 3 PASS/12.113 秒；缺 SDK CLI 退出 2、普通收集明确 skip、pip check、138 项版本与两个锁哈希均通过。没有重复大依赖安装。

证据在当前任务 work/platform-v2-implementation-20261018：sdk-linux-install.log、sdk-linux-install-monitor.md/json、sdk-linux-lock-inventory.json（初始未锁两项的失败记录）、sdk-linux-platform-lock-apply.log、sdk-linux-platform-lock-inventory.json、runner-portable-host-final.log、runner-portable-linux-final.log、runner-portable-missing-runtime.log，以及 audit-linux-sdk-runtime.md/json/log 和独立检查附件。

## 剩余范围

这里验证 Linux 子解释器，不运行 AutoLab Web/worker，也不覆盖父进程组清理、MySQL、Redis、Java 身份、模型预留或真实供应商。20 的网关业务链仍在 macOS 父 worker 上执行，不能拼接成完整 Linux worker 部署证明。Linux amd64、长期独立 worker、运行中取消/恢复、真实浏览器和真实供应商组合仍待验收。原 48 项任务不改 done。
