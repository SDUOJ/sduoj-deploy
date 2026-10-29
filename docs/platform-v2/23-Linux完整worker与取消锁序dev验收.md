# Linux 完整 worker 与取消锁序 dev 验收

2026-10-19，承接 [21](21-Linux子进程dev验收.md) 的子解释器和 [22](22-独立worker与真实浏览器dev验收.md) 的 macOS 独立 worker。这里实际运行 Linux 的原 Task worker，不把两份独立证据拼接为完整 Linux 全站部署。仅 dev，不 push、不改生产、Java、镜像或 CI 发布链；本页当时安装集仍为空，后续首批源码登记及真实供应商浏览器组合见 [24](24-首批组件与真实模型浏览器dev验收.md)。

## 双解释器环境

使用本机已有官方 `python:3.9-slim-bullseye` 镜像，镜像 ID `sha256:b9e06687fbfc57f6fe563e94e4c8751e39513dde89afc120dc6f56afe5ffc761`，Linux arm64。仓库外新建 worker venv，按原 `requirements.txt` 安装，未改依赖文件；Python 3.9.23、Pydantic 1.10.2，61 项 distribution 清点含 bootstrap 包。原 requirements 有未固定版本的依赖，本次实际版本清单保存在证据中，不宣称已获得完整依赖锁或带 wheel 哈希的供应链证明。

随后按现有 runner README 的 uv 流程新建独立 Python 3.13 SDK 环境：uv 0.11.2、Python 3.13.12、OpenHands SDK 1.55.1、LiteLLM 1.93.0。使用原 `requirements-linux.lock`，138 项版本全部匹配、无未锁定业务依赖。两环境依赖检查及实际导入均通过；没有向原 Web/worker 的 Python 3.9 环境安装 Pydantic 2 或 SDK 依赖。

这次独立 venv 安装与 21 的 Python 3.13.15 子运行时不同，不改写旧环境版本或旧测试结果，也不是生产镜像发布。

## 完整 worker 路径

`9c22b51` 为既有验收函数增加可替换的 worker factory/子进程观察 fixture；宿主版本保持原实现，Linux 版本复用同一个测试函数，检查范围一致：

- 主机现有真实 Gateway、Java 登录和临时 AutoLab Web，随机自有 MySQL 与实际 Redis。
- Linux 容器以非 root UID/GID 执行原 `worker.run()`；代码和两解释器目录只读，根文件系统只读，本轮文件写入使用任务自有 workspace 与有界 `/tmp`。未修改 seccomp 规则或增加可执行模型工具。
- 只共享现有 dev user-service 容器的网络命名空间，使原 debug 身份 RPC 继续走 loopback；MySQL/Redis 和合成 broker 走 Docker Desktop host bridge 的既有自有端口。没有重配或重启现有 dev 服务。
- 每次使用随机自有容器、私有临时 JSON 配置和有界 stdin；凭据不进入 Docker 命令参数或容器环境元数据。测试 bootstrap 只允许明确 opt-in、已知 dev 地址、自有随机库和规范合成出口；不改变产品出口或鉴权规则。
- 观察 Linux `/proc` 中实际 SDK 子进程，HTTP 取消后在 fixture 清理前确认它退出，同一 worker 仍运行。未知用量阻断新任务，按本合成暂停确实未产出的零 token 对账；显式新任务执行六次模型步骤，人工采用后核对文档版本 2、六条 success AiRun 和一条 reconciled AiRun。
- 退出时原 worker 正常处理 SIGTERM，容器退出 0、RestartCount=0，Redis 订阅恢复；删除的只有本次随机容器和临时凭据。

模型出口、安装投影仍是合成替身。SDK、worker、claim/租约/权限/账务/候选不是替身；Web 控制器仍在 macOS。没有运行完整 Linux Web 站点、amd64 或真实提供商浏览器组合。

## 审计修复与真实失败

首轮 Linux 1 项通过，21.40 秒；随后宿主版本 1 项通过，14.54 秒。复跑 Linux 出现真实取消失败：Gateway 返回 500，MySQL 1213，后续清理未满足正常退出断言（退出 137）。失败日志保留，不把首轮通过当作稳定性证明，也不凭退出码推断 OOM 或其他系统原因。

InnoDB 死锁记录确认锁序相反：worker `fenced()` 已持有任务行、等待账户；取消接口的原来源 ACL 已持有账户、等待任务更新。`be19084` 只在原 `authorized_job` 之前取得任务行锁，统一为任务 → 账户，不增加 runtime 配置依赖、不变更 owner/课程/题单权限、角色或终态规则。

新增真实 MySQL 双线程调度回归通过实际 ORM SQL 事件控制两个事务；任务使用明确的 lease-shaped 历史 fixture，只证明锁顺序，不冒充准入或身份验收。旧产品上稳定得到 1213（1 项失败，0.69 秒），修复后通过，并检查 lease 撤销和重复取消。测试初稿误将异步响应 wrapper 当同步调用而失败，10.66 秒；纠正调用后才得到上述 1213 反例，两份记录均保留。

独立审计另发现测试配置存在可写别名：虽然单文件挂载标为 readonly，它也位于整体可写的 workspace 内。`ce07563` 将私有文件移至 workspace 外的 0700 sibling 目录，只通过只读单文件挂载可见，结束后删除。该问题属于测试 fixture，保留 `9c22b51` 的 needs_fix，不改生产凭据或产品权限。

独立 fixture 审计中，9c22b51 为 needs_fix，13 项启动/配置拒绝检查通过；ce07563 修复后 accepted，另有 14 项拒绝/挂载拓扑/清理检查通过。这些使用假的 process 验证 fixture 边界，不冒充 Linux 运行结果。审计曾用整体替换 gateway_dev 的探针推定 showlocals 问题，因该探针连已有 guard 也删掉而无效，已撤回；实际原 guard 在私有 JSON 读取前拒绝。

be19084 产品锁序修复独立审计 accepted：exact commit 的真实 MySQL 回归 1 项通过、0.71 秒；换回父提交产品代码，同测试 1 项失败、0.73 秒、1213。另 8 项真实 MySQL 边界通过、2.56 秒，覆盖终态不覆写、幂等回放、原非本人/暂停/删除/不存在拒绝，以及拒绝后锁释放。未用这些直接调用的 SQL 测试冒充 HTTP 身份链。

锁序和测试挂载修复后，Linux 完整链重新通过 1 项，21.10 秒，父进程退出 0；原 worker、真实 SDK、数据库核对、正常退出与清理断言均生效。`1fbff21` 仅同步 AutoLab runner README 的验收边界，已逐 hunk 独立 accepted。

另一位审计者在 be19084 exact 归档中独立重跑实际 Gateway/Java/SQLRedis 与 Linux worker/SDK 的组合验收：1 项通过、19.25 秒，正常退出/RestartCount=0 与实际子进程取消均检查；另跑稳定 MySQL 锁调度 1 项通过、0.70 秒，并在精确旧代码复现 1213。验收结束后确认 5005 可重新绑定，私有副本已删除。未重装依赖或调用真实模型。

## 当前后端组合回归

`be19084` 完整 `pytest tests`：995 通过、22 跳过、0 失败，86.67 秒，父进程退出 0。随机自有 MySQL 和宿主实际 SDK 解释器已启用；跳过为真实提供商 2、authoring 专用集成 1、固定 MySQL 锁 1、容器 9、专用 schema 数据库 3、显式 Gateway 验收 5、显式 Linux worker 1。Linux worker 是本页另行 opt-in 的定向验收，不把跳过算作全量通过。随后 1fbff21 仅修改 README，未冒称该 SHA 重跑全量。

## 证据与后续

本机仓库外 `platform-v2-implementation-20261018` 保存：`linux-worker-runtime-install.log` 与监控记录、`linux-worker-{parent,sdk}-inventory.json`、首轮 `gateway-linux-worker.log`、宿主复跑 `gateway-linux-worker-host-regression.log`、失败 `gateway-linux-worker-final.log`、修复后 `gateway-linux-worker-lock-fixed.log`、`task-cancel-lock-{before,reproduce,fixed}.log` 及 `audit-linux-worker-{fixture,private-mount,readme}.*`、`audit-task-cancel-lock.*`、`audit-linux-cancel-lock-integration.log` 等独立审计记录。原 InnoDB 片段按 0600 保存，文档只记录锁关系，不复制原 SQL 参数。

继续真实提供商与浏览器组合、其余组件迁移、原生题目锁竞争、Linux amd64 和原发布流程的最终制品验收；没有组件因本页变为 installed，没有将原 48 项任务改 done。
