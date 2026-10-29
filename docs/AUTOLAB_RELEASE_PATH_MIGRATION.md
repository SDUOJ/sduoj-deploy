# AutoLab 代码路径迁移

本工具只准备冻结源码和迁移现有两个 systemd release drop-in 的代码路径。目的地为 root 管理的 `/opt/sduoj/releases/<release-id>` 实目录；所有祖先不得由服务身份写入。代码目录使用 root:服务组、0550，普通文件 0440、可执行文件 0550。它不使用 `current` 软链接，也不覆盖正在运行的源码。

`scripts/autolab_release_path.py` 不连接远端、数据库或 HTTP，不输出 Environment/ExecStart/环境文件正文，不调用服务 stop/start/restart，不改变数据库、配置、解释器、日志或持久文件。`prepare` 写入新代码目录；`apply`/`rollback` 只替换已有 drop-in 中的两个精确路径指令并执行 `daemon-reload`。生产切换仍需原正式窗口的排空、停止、启动、业务验证与回退责任方。

## 已确认的现场合同

2026-10-29 的受限元数据审计发现：当前代码自身归 root，但某个 home 祖先由服务身份控制。代码自身只读不足以防止祖先重命名替换。现场路径、UID/GID、drop-in 摘要及运行环境保留在本轮受限发布单，不在公开仓库记录。

既有 `sduoj-autolab-web.service`、`sduoj-autolab-worker.service` 都经 `grade-review-release.conf` 指向版本目录，实际启动脚本是同级的 `run-web.sh`、`run-worker.sh`。准备包应为：

```text
reviewed-input/
  autolab/        # 本次冻结的完整运行源码
  run-web.sh     # 现有启动脚本，逐字核对
  run-worker.sh  # 现有启动脚本，逐字核对
```

工具只把启动脚本中 `旧版本/autolab` 替换为 `新版本/autolab`；解释器、环境文件、PID、日志及其它绝对路径逐字保留。drop-in 只允许替换 `WorkingDirectory=旧版本/autolab` 和对应的 `ExecStart=/bin/bash 旧版本/run-ROLE.sh`。其它字段、注释和换行保持原字节。基础 unit 及全部已加载 drop-in 的内容只记录 SHA256、模式、所有者，拒绝 plan 后漂移；不读取配置指令值用于日志展示。

不能把环境、数据、日志、运行目录、软链接、硬链接、缓存或私钥放进代码包。工具拒绝已知私有/运行目录名、特殊文件及两类私钥标记；这属于有限检查，不能证明任意源码中没有凭据。正式准备仍需对完整冻结输入单独审查。源码树摘要没有签名能力，必须由独立可信发布单或原受保护制品记录提供，不能仅在可写源旁放一个新摘要就当成可信。

## 准备配置

先在隔离 Linux staging 主机演练。以下路径均为占位符，不能直接粘贴为生产命令。部署配置、plan、gates、state 全部放在 root 管理且组/其它身份不可写的祖先下；state 私有 0700，完整 unit 备份 0600。

1. 用已有发布流程建立受审 source 输入目录，不从 live Python 进程收集临时文件。记录源码 40 位 SHA、输入树、旧 launchers 与两个实际 drop-in 摘要。
2. 由运维核验并创建 `/opt/sduoj/releases` 的 root-owned 0755 祖先；工具不会自动修正已有不安全祖先。
3. 生成 inventory 并与可信来源核对，输出仅为文件名、大小、执行标志和 SHA256：

```bash
python3 scripts/autolab_release_path.py inventory --source /reviewed/immutable-input
```

配置 schema 示例（保存为 root-owned 0600 JSON）：

```json
{
  "schemaVersion": 1,
  "releaseId": "autolab-path-APPROVED-ID",
  "sourceRef": "FULL_40_HEX_SOURCE_REF",
  "source": "/reviewed/immutable-input",
  "sourceTreeSha256": "REVIEWED_64_HEX_INVENTORY_SHA256",
  "oldRelease": "/reviewed/existing-release-parent",
  "releaseRoot": "/opt/sduoj/releases",
  "serviceUser": "existing-service-user",
  "serviceGroup": "existing-service-group",
  "serviceGid": 1234,
  "dropins": {
    "sduoj-autolab-web.service": {
      "path": "/etc/systemd/system/sduoj-autolab-web.service.d/grade-review-release.conf",
      "sha256": "REVIEWED_64_HEX_CURRENT_DROPIN_SHA256"
    },
    "sduoj-autolab-worker.service": {
      "path": "/etc/systemd/system/sduoj-autolab-worker.service.d/grade-review-release.conf",
      "sha256": "REVIEWED_64_HEX_CURRENT_DROPIN_SHA256"
    }
  }
}
```

## Preflight、准备和只读 plan

```bash
python3 scripts/autolab_release_path.py preflight --config /private/path-migration/config.json
sudo python3 scripts/autolab_release_path.py prepare --config /private/path-migration/config.json
python3 scripts/autolab_release_path.py plan --config /private/path-migration/config.json \
  > /private/path-migration/plan.json
```

`preflight`/`plan` 不创建或修改文件。`prepare` 要求 root，拒绝复用已有 release ID；逐文件验源摘要再复制，在同文件系统临时目录中生成安装 manifest、设 owner/mode，再 rename 到新版本。代码源和安装源的摘要分别记录，因为两个 launcher 的代码路径被有意替换。文件清单、大小、模式含义和内容都需在 staging 验证。新代码不能写入自身。

`plan` 可在旧服务仍 active 时生成。实际 apply 前原责任方必须先停止受影响入口并确认所有旧消费者/子进程排空，再停止这两个 unit；工具只接受同时 `inactive/dead`。它不替代对脱离父进程消费者、任务租约、队列及数据库状态的检查。plan 比较忽略上述运行状态转换，其余元数据、全部 unit 文件哈希及精确输入都必须相同。

## 隔离 staging apply

首次 staging 不要求已有 staging pass，以免形成循环。受审 gates 中必须明确隔离目标、授权窗口、排空和 plan 的精确两个摘要：

```json
{
  "environment": "staging",
  "isolatedTarget": true,
  "drained": true,
  "windowAuthorized": true,
  "configSha256": "FROM_REVIEWED_PLAN",
  "targetMachineSha256": "FROM_REVIEWED_PLAN",
  "installedTreeSha256": "FROM_REVIEWED_PLAN"
}
```

```bash
sudo python3 scripts/autolab_release_path.py apply \
  --config /private/path-migration/config.json \
  --plan /private/path-migration/plan.json \
  --gates /private/path-migration/staging-gates.json \
  --state /private/path-migration/NEW-operation-state
```

此命令不启动服务。原 staging 责任方按既有顺序启动 Web 与 worker，并核对：真实 PID/cwd/executable、只有预期消费者、原日志及环境/数据路径未变、无源码内新文件、服务身份不能写代码及任何祖先、原全部路由/真实 Gateway 认证、成绩复查和原 AutoLab 任务。不能把有写入副作用的成绩详情查看当成只读测试。使用专属 fixture，避免修改正式成绩或任务。

保留启动前后源码 hash、所有者与模式、单独业务 smoke、停止/恢复和回滚结果。工具始终返回 `productionQualified=false`；systemd 元数据模拟和临时文件测试不构成 staging 或生产通过。

## 正式窗口与回滚

生产 gates 使用 `environment=production`、`stagingStatus=passed`，并绑定本次批准 config/installedTree 摘要、实际 `/etc/machine-id` 的 SHA256，以及 `drained=true`、`windowAuthorized=true`。plan 与 gate 必须属于当前主机，不能把 staging 的 plan 直接用于生产。这些 JSON 是运维责任方的显式声明，不是自动检查或加密证明。跨 staging/prod 目标若路径导致 launcher 摘要不同，先审查确定的路径替换差异并在目标重新 plan，不伪造相同 bytes。

全部门禁、独立备份/恢复与 staging 验收完成后，原窗口责任方执行相同 apply，再按既有顺序启动和验证。不要只凭 daemon-reload 成功宣称服务或生产恢复。原 rootfs、数据库迁移、运行环境更新及功能开关均不属于本脚本。

回滚先由原责任方阻止新任务、排空并停止两个新 unit，再执行：

```bash
sudo python3 scripts/autolab_release_path.py rollback \
  --state /private/path-migration/EXISTING-operation-state
```

工具先核验两份当前 drop-in、全部其它 unit 文件与私有备份，全部检查通过后才写任一文件；只接受当前摘要为本次 before/after。恢复原字节与 owner/mode，daemon-reload 后核对原有效元数据。然后由原责任方启动旧服务并做业务验收。恢复旧配置也恢复旧代码路径祖先的已知风险，是否启动须由窗口责任方明确决定。它不恢复数据库或数据目录，也不删除新旧源码、备份、状态或证据。

apply 写入或 reload 失败会尝试恢复两份 drop-in，并始终返回失败。失败时 state 标明 `rolled-back` 或 `rollback-required`；不要据自动恢复字样直接放流量。prepared 状态也可用于进程中断后的显式恢复。SIGKILL/断电无法保证执行自动恢复，先核对私有 state 与两份实际 unit，不重新运行 apply 或删除残留来绕过漂移。文件分别原子替换且 fsync；两 unit 并非单文件事务，所以必须始终在 inactive 状态操作。

## 本地测试边界

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests \
  -p test_autolab_release_path.py -v
```

测试在真实临时文件系统复制/设权限/换文件并模拟 systemd metadata 与 daemon-reload。非 root 开发机只在库调用中注入当前 UID 和临时 trust anchor，CLI 没有绕过 root 身份/固定 `/opt` 根目录的参数。测试覆盖：只读 plan、源/代码/hash 漂移、祖先与链接风险、旧数据/日志/Python/env 路径逐字保留、其它 unit 字段哈希、inactive 门禁、staging/prod 门禁差异、部分写入/reload 失败、原字节回滚、备份篡改和崩溃 prepared 状态恢复。

2026-10-29 另在本机固定 Python 3.13 ARM64 Linux 镜像验证真实 DAC 权限：network none、只读 rootfs 和源码挂载、仅 tmpfs 写入，CPU 1、512 MiB、swap 0、PID 64；无 privileged/SYS_ADMIN。root UID 0 建立受保护的 `/opt/sduoj/releases` 后，UID/GID 10777、零有效 capability 的子进程实际执行 13 项检查：11 项代码写入/chmod/创建/重命名及祖先替换被 EACCES、EPERM 或 EROFS 拒绝，原声明日志与数据目录的两项读写通过。相同容器的 20 项 unittest 全通过、零 skip。首跑夹具在 chown 后 chmod 被最小 capability 集合拒绝，调整夹具的权限设置顺序后通过；两次记录均保留在受限发布单。

这些结果证明本机隔离 Linux 夹具的权限边界，不是 AutoLab 业务或真实 systemd 验收。生产源码、真实 runtime、目标服务身份与 staging 主机仍须按前文实际验证；没有操作生产或启动服务。
