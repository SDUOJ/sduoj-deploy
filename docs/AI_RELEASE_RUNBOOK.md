# AI-19/20 本机发布与恢复工具

`scripts/ai_release.py` 为 Web2 与 Autolab 提供可审查的本机发布单元。Java OJ 后端继续使用原有发布流程；本工具不会修改 Nginx、Nacos、Java 服务或任何远端主机，也不会自动建立 SSH/HTTP 连接。`templates/systemd/` 与 `templates/nginx/sduoj-ai.conf` 只是待审查模板，本轮没有安装、启用或 reload。

## 发布前准备

本仓库新增 `.github/workflows/ai-release.yml` 手动构建入口，要求 Web2/Autolab 的完整 40 位 commit SHA 和 release ID；checkout 使用只读 `SDUOJ_SOURCE_READ_TOKEN`，作业绑定 `ai-release-review` 环境。仓库管理员需配置此环境的 required reviewers 及只读 token。工作流只运行测试、构建并上传制品，不安装服务、不执行生产迁移或 SSH，也不会改变 Java 发布流程。本轮仅解析校验 YAML，未推送或触发 GitHub 作业。

Autolab release 模式已改为只从环境读取 OJ RPC、Redis/MySQL 及可选旧模型凭证；源码不再携带旧的明文值。`AUTOLAB_AI_SECRET_KEY` 在 release 模式为必填且必须是有效 Fernet key，空白包围的凭证也会 fail-closed。生产首次采用新制品前必须准备 `templates/systemd/autolab.env.example` 对应配置和 Fernet 主密钥。当前本机 debug 仍使用原私有 dev 配置；本轮未改运行中的生产配置。

`preflight.node_options` 记录构建使用的 `NODE_OPTIONS`。本轮普通 Node 24.20.0 在全量 Jest 中出现一次 V8 GC 原生 SIGSEGV，已按相同门禁用 `--jitless` 重跑；此参数仅作用于本次构建程序，不写入产品运行配置。不应忽略解释器崩溃后直接发布未通过测试的包。

推荐使用 `prepare-release` 从 Web2 和 Autolab 源码制作制品。它把 Web2 源码复制到临时目录，复用调用方已经安装的 `node_modules`，以 `--offline --frozen-lockfile` 依次执行 typecheck、lint、unit tests 和 production build；随后用指定 Python 运行 Autolab 全量 pytest 并校验 OpenAPI/DDL 快照。任何一项失败都不会生成制品。它不会安装或下载依赖。

`--source-date-epoch` 固定 manifest 和 tar 时间；相同源码内容、文件权限、工具版本、release ID 和 epoch 会生成字节一致的 tar。manifest 记录 Web2/Autolab 输入树哈希、Node/Yarn/Python 版本和通过的 preflight 项。成功命令的原始输出可能包含不稳定的耗时，因此不写入可复现 manifest；失败时 CLI 仍返回末尾输出。Web2 必须使用 package.json 声明的 Yarn 1.22.22 和 Node 24。

```bash
python3 scripts/ai_release.py prepare-release \
  --web2-source /absolute/path/to/sduoj-web2 \
  --autolab-source /absolute/path/to/sduoj-autolab \
  --node /absolute/path/to/node-24 \
  --yarn /absolute/path/to/yarn \
  --python /absolute/path/to/autolab-python \
  --source-date-epoch 1788534000 \
  --release-id 20260905-r1 \
  --output /absolute/path/to/artifacts/sduoj-ai-20260905-r1.tar.gz
```

`--migration-check` 另外执行 `python -m auto_task.migrate` 的只读计划。它会连接 `SDUOJ_MODE` 和环境配置指向的数据库，因此只能在明确确认是本机/预生产数据库后使用。该检查不带 `--apply`，不能创建表；正式迁移仍需单独变更窗口。

`build-release` 保留为兼容入口，只接受已经构建完成的前端目录和 Autolab 运行目录，不生成或记录上述 preflight。打包策略会排除 `.env`、`dev_config.py`、本地初始化脚本、测试夹具、`.github`、凭证、私钥、数据库数据、`node_modules`、`.git`、日志、工作区、coverage/htmlcov 和 Python 缓存；调用方仍应只传经过审查的运行目录。

```bash
python3 scripts/ai_release.py build-release \
  --web2 /absolute/path/to/web2-build \
  --autolab /absolute/path/to/sduoj-autolab-runtime \
  --release-id 20260905-r1 \
  --output /absolute/path/to/artifacts/sduoj-ai-20260905-r1.tar.gz
python3 scripts/ai_release.py verify \
  /absolute/path/to/artifacts/sduoj-ai-20260905-r1.tar.gz --kind release
```

发布包内包含 `release-manifest.json`，其中记录组件、每个文件的大小、模式和 SHA-256。包旁边会生成必需的同名 `.sha256` 文件，两者必须一起传递。解包前会验证压缩包清单、路径、重复成员、展开大小、文件哈希和 sidecar 哈希。绝对路径、`..`、目录、符号链接、重复成员和私钥内容都会被拒绝。

sidecar 与制品一起传输只能发现意外损坏或只替换其中一个文件的篡改，不能证明发布者身份。正式制品必须再使用独立可信通道传递摘要或由受保护 CI 进行签名和 provenance 证明。

## 本机原子切换

目标目录必须是明确的绝对本机路径。首次使用时才传 `--create-target`；工具拒绝 `/`、用户 home、已有符号链接、非目录目标以及首次部署时的非空目录。

```bash
python3 scripts/ai_release.py deploy-local \
  /absolute/path/to/artifacts/sduoj-ai-20260905-r1.tar.gz \
  --target /absolute/path/to/local-install --create-target
python3 scripts/ai_release.py deploy-local \
  /absolute/path/to/artifacts/sduoj-ai-20260905-r1.tar.gz \
  --target /absolute/path/to/local-install --create-target --apply
```

目录结构为：

```text
local-install/
  .sduoj-ai-release-root
  current -> releases/20260905-r1
  releases/
    20260905-r1/
      web2/...
      autolab/...
      release-manifest.json
      .artifact-sha256
  release-state.json
```

`deploy-local` 默认只输出计划，不创建目录、不解包也不切换；必须显式传 `--apply`。首次实际部署会写入固定内容的 `.sduoj-ai-release-root`，后续部署、漂移和回滚都要求此 marker 存在且匹配。目标路径任何一段包含软链接时会拒绝。

制品先解到随机 staging 目录，再次核对成员路径/类型/大小并逐文件验哈希，然后通过 `os.replace` 放入 `releases/<release-id>`，最后用临时符号链接原子替换 `current`。同一 release ID 如果已存在，内容必须完全相同才允许重放。发布状态只保存最近 20 个历史 release ID。原子替换保证运行时看不到半条链接；目录未执行 `fsync`，突然断电后的持久性仍需在目标文件系统演练。

## 回滚与漂移

不带 `--to` 时回退到状态文件中最近的其他 release；带 `--to` 时必须给出已安装且完整的 release ID。回滚前会重新验证目标 release，篡改的 release 不会被切换。

```bash
python3 scripts/ai_release.py rollback-local --target /absolute/path/to/local-install
python3 scripts/ai_release.py rollback-local --target /absolute/path/to/local-install --apply
python3 scripts/ai_release.py rollback-local --target /absolute/path/to/local-install --to 20260905-r1 --apply
python3 scripts/ai_release.py drift --target /absolute/path/to/local-install
python3 scripts/ai_release.py drift --target /absolute/path/to/local-install --prefix web2
```

`rollback-local` 默认也只输出计划；目标 release 通过完整校验后，`--apply` 才切换。`drift` 是只读检查。返回 JSON 中 `missing`、`changed`、`added` 和 `unsafe` 分别表示缺失、哈希/大小变化、新文件和符号链接等不安全内容；无漂移时退出码为 0，有漂移时退出码为 2。它不会根据工作树重新生成 manifest，也不会修复文件。

Nginx/Nacos 等配置使用独立的本机导出目录和基线。工具只读取指定目录，不连接 Nacos、服务器或容器；导出方式及访问权限由现有运维流程负责。基线会排除 `.env`、凭证、私钥等文件，而漂移检查会把当前目录中额外出现的这些文件名报告为 `added`，不会输出其内容。

```bash
python3 scripts/ai_release.py config-baseline \
  --source /absolute/path/to/reviewed-config-export \
  --baseline-id prod-config-20260905 \
  --output /absolute/path/to/baselines/prod-config-20260905.json
python3 scripts/ai_release.py config-drift \
  --baseline /absolute/path/to/baselines/prod-config-20260905.json \
  --current /absolute/path/to/current-config-export
```

`config-drift` 不更新基线且不写当前目录。新增、删除或修改 Nginx/Nacos 配置必须继续走人工审查，生成一份新的基线，不允许以漂移工具自动覆盖现场配置。

## 备份与空目标恢复

备份是标准 gzip tar，使用相同的逐文件清单和 sidecar 校验；`--source` 可以是本机持久化目录。备份不会包含发布目录的排除规则，调用方应只指定需要备份的本机数据目录。

```bash
python3 scripts/ai_release.py build-backup \
  --source /absolute/path/to/autolab-persistent-data \
  --backup-id 20260905-db1 \
  --output /absolute/path/to/artifacts/autolab-20260905-db1.tar.gz
python3 scripts/ai_release.py restore-backup \
  /absolute/path/to/artifacts/autolab-20260905-db1.tar.gz \
  --target /absolute/path/to/empty-restore --create-target
python3 scripts/ai_release.py restore-backup \
  /absolute/path/to/artifacts/autolab-20260905-db1.tar.gz \
  --target /absolute/path/to/empty-restore --create-target --apply
```

恢复默认只输出计划。带 `--apply` 时只接受空的、明确的本机目录。数据先解到目标旁边的 staging 目录并完成完整性检查，再以同文件系统目录重命名原子替换空目标；目标非空、包被篡改或包含不安全路径都会失败。真正的 MySQL `mysqldump`/恢复、对象存储、跨主机复制和生产备份策略仍需由运维流程单独执行，不能把此目录演练当成生产恢复证明。

## 服务与同域入口模板

`templates/systemd/sduoj-autolab-web.service` 使用专用非 root 用户，从 `current/autolab` 启动仅监听 `127.0.0.1:5005` 的 Gunicorn/Uvicorn；`sduoj-autolab-worker.service` 独立运行 `python -m auto_task.worker`。两个 unit 启动前都执行只读 `drift --prefix autolab`，并将代码目录设为只读，只开放外部数据/日志目录。Worker 模板不授予 Docker socket；代码执行应使用隔离 runner 或经过审查的最小权限代理。

`templates/nginx/sduoj-ai.conf` 在同一 origin 提供 `current/web2` 下的 `/v2/` 静态文件，并把 `/api/`、`/ws/` 交给 SDUOJ Gateway。Autolab 5005 不能直接对公网开放，Gateway 必须清理浏览器伪造的身份 header 后按 OJ session 重新注入。模板域名、Gateway 地址、TLS、证书、HSTS、限流和日志策略均是待部署环境确认的占位内容。

## 验证证据与限制

临时目录测试覆盖：排除密钥/依赖/日志/工作区、私钥内容拒绝、绝对路径与符号链接拒绝、恶意 `..` tar、文件/sidecar/安装清单篡改、原子切换、默认 dry-run、root marker、配置只读漂移、篡改 release 回滚拒绝、备份恢复、非空目标拒绝，以及固定 epoch 的离线 preflight 可复现制品。

```bash
python3 -m pytest -q tests/test_ai_release.py
```

2026-09-06 本机发布工具专项结果为 13 passed；新增用例证明本地 `dev_config.py`、初始化脚本、测试夹具和工作流元数据不会进入运行制品。此前一次真实 `prepare-release` 使用 Node 24.19.0、Yarn 1.22.22 和 Autolab Python 3.9.23，Web2 typecheck/lint/unit/build 均通过；当时直接检查 Autolab 工作树准确阻止了 stale `docs/auto-task-ai-openapi.json`，在临时副本刷新为 68 paths/13 extension tables 后才完成制品。后端续推后，权威工作树已刷新并再次验证为 91 paths/13 extension tables；本轮没有重跑完整 Web2 `prepare-release`，不能把契约复核当成新制品已生成。最近一次本机数据库的独立只读 `python -m auto_task.migrate` 返回 `missing_tables=[]`、`missing_indexes=[]`、`apply_required=false`。正式构建仍必须先提交最新 OpenAPI/DDL 快照并重跑完整 preflight。

该工具提供本机制品完整性和可回滚基础，不代表生产高可用、灰度、负载、ARM64 隔离、备份异地保管或 Nginx/Nacos 变更已验收。生产使用前仍需要：受保护 CI 生成并签名制品；在目标 ARM64/发行版验证依赖与沙箱；在同构预生产验证 Gateway session/header、SSE、上传和 WebSocket；完成数据库备份恢复演练及前后版本兼容证明；定义队列 drain/lease、服务重启顺序、观察指标、停止条件和批准记录。软链接切换不会让已经运行的 Python 进程自动加载新代码，多机切换也需要外部编排器。
