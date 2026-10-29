# 正式 /v2/ 现成制品发布与恢复

本入口只提升已经验收的前端制品，不安装依赖、不运行 webpack，也不重新生成 manifest。`scripts/release-v2-artifact.sh` 只操作显式目标根目录下的 `v2`、`v2-backup`、`rollback-v2.sh` 和本次 release ID 对应的暂存/恢复目录；不修改 `v2-pre`、OpenResty、hosts 或后端配置。无参数只输出帮助。`verify` 只读本机制品；`plan` 连接显式 SSH 目标但只读检查；只有 `deploy` / `rollback` 执行写入。

这份脚本准备完成不代表生产部署已获批准。先满足整栈的节点隔离、镜像身份、容量和回滚门禁，再单独决定正式切换。不能用前端静态制品演练替代 Worker/Judger 的 Linux 内核与 cgroup 合同验收。

## 输入和前置条件

- 本机与远端均使用 Node 24；两端有 rsync，远端有 GNU coreutils `timeout`。本机脚本使用随包的有界命令运行器。
- SSH host、user、root 必须显式设置；没有默认生产地址。启用非交互、禁止 Agent 转发、严格 known-host 校验。预先通过可信渠道核对 known_hosts；脚本不写入它。
- root 必须是已经存在、可写、非符号链接的物理绝对目录；其 `v2`、`v2-backup` 也必须已经存在且可写。`plan` 不创建目录。路径不接受空格、shell 元字符或 `..`。
- HTTPS URL 必须是规范的 `https://host[:port]/v2/`。制品的完整 40 位 source ref、manifest SHA、`/v2/` 前缀、生产 origin、全部文件字节都需匹配。release ID 必须显式给出，使用 1–96 个字母、数字、点、下划线、短横线，且首字符为字母或数字；不能复用保留的 ID。
- 当前线上 `/v2/` 必须已经提供可完整验证的 known-good `release-manifest.json`。发布前 HTTPS smoke 校验全部文件、响应安全头、缓存、SPA fallback、静态 404 和匿名 API 401，并记录旧 manifest SHA/ref。如果旧站点没有可信 manifest，先完成独立的旧版本取证和恢复准备；本入口会拒绝直接覆盖，不伪造旧 manifest。
- 所有写操作要求一个尚不存在的本机绝对证据目录，其父目录需已经存在；新目录权限为 0700。每条命令默认 600 秒，允许显式设置 1–3600 秒。请为当前制品大小和网络吞吐预留余量。

## 显式命令模板

下列值是占位符，不应直接执行；从审批后的发布包填写目标和身份。制品目录应保持只读/冻结直到发布完成。

```bash
export PATH="/path/to/node24/bin:$PATH"
export SDUOJ_RELEASE_URL='https://approved-host/v2/'
export SDUOJ_DEPLOY_HOST='approved-ssh-host'
export SDUOJ_DEPLOY_USER='approved-deploy-user'
export SDUOJ_DEPLOY_ROOT='/approved/existing/webroot'
export SDUOJ_DEPLOY_PORT='22'
# 如需独立密钥：export SDUOJ_DEPLOY_KEY='/private/path/to/key'
export SDUOJ_RELEASE_COMMAND_TIMEOUT_SECONDS='600'

ARTIFACT='/absolute/path/to/already-qualified/build'
SOURCE_REF='FULL_40_CHARACTER_SOURCE_REF'
RELEASE_ID='APPROVED_UNIQUE_RELEASE_ID'

bash scripts/release-v2-artifact.sh verify "$ARTIFACT" "$SOURCE_REF" "$RELEASE_ID"
bash scripts/release-v2-artifact.sh plan "$ARTIFACT" "$SOURCE_REF" "$RELEASE_ID"
```

`verify` 不需要 SSH 参数。核对审批与 plan 后，才执行写入步骤：

```bash
export SDUOJ_RELEASE_EVIDENCE_DIR='/existing/private/evidence/unique-deploy-operation'
bash scripts/release-v2-artifact.sh deploy "$ARTIFACT" "$SOURCE_REF" "$RELEASE_ID"
```

deploy 保存 `before.json`、本机制品验证结果、上传日志、应用日志和 `after.json`；HTTPS 后验失败时额外保存恢复日志和 `rollback.json`。不要将这些操作证据、SSH 凭据或运行环境文件提交到 Git。

## 发布事务与恢复

1. 本机制品完整校验、远端只读 plan、当前 HTTPS known-good 校验，再次校验冻结制品。
2. 创建全新的 `.v2-release-ID` 和 `.v2-release-meta-ID`，通过带 checksum 的 `rsync -rlptDc` 上传制品和固定 verifier/transaction helper；校验 helper SHA。
3. 获取 `.v2-release-lock`。在锁内重验当前旧 manifest 和候选全部字节，拒绝覆盖 plan/smoke 之后发生的站点变化。
4. 将当前版本完整复制并验证到 `.v2-backup-new-ID`。把原 `v2-backup` 保留为 `.v2-backup-old-ID`，将新快照提升为 `v2-backup`。先安装已绑定 helper SHA、旧 ref/SHA 的 `rollback-v2.sh`，再写入当前 `v2`。
5. 应用同步失败、应用验证失败或远端 Bash 收到 INT/TERM 时，EXIT 处理器尝试从已验证的 `v2-backup` 恢复。应用成功后做完整 HTTPS 后验；后验失败则只在当前 manifest 仍为本次候选时自动恢复，避免覆盖另一笔已经完成的发布。无论自动恢复是否成功，本次发布均返回失败。

独立恢复入口无需候选制品目录：

```bash
export SDUOJ_RELEASE_EVIDENCE_DIR='/existing/private/evidence/unique-rollback-operation'
bash scripts/release-v2-artifact.sh rollback 'EXPECTED_64_CHARACTER_BACKUP_MANIFEST_SHA256' 'UNIQUE_ROLLBACK_OPERATION_ID'
```

应从本次部署的 `before.json` 取预期旧 manifest SHA，并和审批包核对。脚本在远端检查 `v2-backup` 摘要后才执行 `rollback-v2.sh`，并把预期摘要带入锁内再次核对，拒绝检查之后被另一笔发布替换的回滚入口，随后通过 HTTPS 校验恢复后的精确摘要。摘要不匹配时拒绝写入。恢复 plan 允许当前 `v2` 内容损坏，以便恢复半次同步；仍要求固定目录真实存在。

若本机连接丢失，可在已核对目标的受控 SSH 会话里执行现成 `bash /approved/existing/webroot/rollback-v2.sh`，该入口重验绑定的 transaction/verifier SHA 与备份全量字节；随后必须补跑上述带预期摘要的 CLI 恢复/HTTPS 后验并保存证据。直接入口不执行 HTTPS 验证，不能据其退出码单独关闭恢复验收。

脚本不递归删除任何暂存或恢复副本。`.v2-release-ID`、metadata、`.v2-backup-old-ID` 和失败快照均保留，后续清理须另行审计并批准。SIGKILL、主机断电、存储故障无法保证自动执行 trap；若发现遗留锁或中断记录，先确认没有活跃发布，核对当前/备份/helper 摘要和权限，再决定受控恢复，不盲删锁或重用 ID。`v2` 使用 rsync 原地同步，存在文件切换窗口，应在批准的维护窗执行；这不是原子目录切换。

## verifier 来源和本地回归

三个 `.cjs` helper 逐字复制自已验收的 Web2 HEAD `e0608b2d8bdc071f9052b92bea949098c4f07c7a`：

| 文件                   | SHA256                                                             |
| ---------------------- | ------------------------------------------------------------------ |
| `release-artifact.cjs` | `974d251980a589944c80b0b38590bd4f2fc225d3774caec0d06f341c325d5196` |
| `deployment-smoke.cjs` | `00c11144f0d3539f4859d0afbcf369a3418886bd3365fd9614035578d5932f96` |
| `timed-command.cjs`    | `99c5305751aa4eb0a538e616f3a9ebfd470f14262293c0abf7ceca66287e63f6` |

沿用 Web2 `release-v2-pre.sh` 的 checksum rsync、前后 smoke、快照轮换与恢复思路，新增正式固定路径、显式输入、已验收制品提升、锁、完整来源验证和可独立恢复的 helper。原 `release-v2-pre.sh` 未改动。

```bash
bash -n scripts/release-v2-artifact.sh scripts/frontend-release/remote-v2-transaction.sh
shellcheck scripts/release-v2-artifact.sh scripts/frontend-release/remote-v2-transaction.sh
node --test tests/test_release_v2_artifact.cjs
```

测试必须使用 Node 24、真实 rsync 和支持 `-addext` 的 OpenSSL，缺少工具明确失败，不 skip。测试仅伪造 SSH 传输端点和 GNU timeout 外壳；文件复制调用真实系统 rsync，HTTP 校验使用本机临时 HTTPS 服务器及单次生成的受信自签证书。覆盖只读 plan、显式参数防护、精确应用、独立回滚、同步失败、候选/当前漂移、快照失败、TERM 中断、恢复再次失败后重试、HTTPS 后验失败、错误备份摘要、修改 helper、ID/证据目录重用及活动锁。每例都断言 `v2-pre` 和 OpenResty 哨兵未变。该测试不连接任何真实 SSH 或生产站点，不等同于生产演练。
