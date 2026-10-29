> 本文为历史v1八副本/privileged开发配置记录。当前用户已确认采用ARM64+cgroup-v2，正式入口见[集成发布](COMBINED_RELEASE_20261026.md)及[统一权限报告](IDE_CGROUP_V2_SHARED_20261026.md)，禁止直接复制本页旧资源/权限默认值。

# Online IDE 统一 Worker：开发与发布

## 边界

Gateway 保留 HTTP 接口、WebSession 鉴权、用户限流和 Redis session；AutoLab 不执行 LSP/Debug。每个容器向 Nacos 注册一个 `ide-worker` 实例，内部同时运行 C、C++、Java、Python 四个有界 LSP 池与一个 Debug runtime。进程池是上限固定、按需启动并复用，不能把进程上限理解为已预热容量。

LSP 初始任务进入语言共享 list，后续请求优先访问持有文档的角色队列。Debug 创建时分配 Worker，后续事件和控制请求固定访问该 Worker 的 `workerId + workerEpoch` 队列。Redis 仅保存元数据、任务和有界事件；真实调试现场保留在原容器内存中。Worker 丢失时明确终止/报告现场丢失，不能在另一 Worker 重放 continue/step。

Nacos 使用 Judger 相同的地址、namespace 与 DEFAULT_GROUP 约定；dataId 为 `ide-worker.yml`。内容采用 `schemaVersion=1, environment={...}` JSON，与现有 dev Nacos 的 JSON 发布方式一致。只接受显式白名单字段，`${NAME}` 在容器内展开，Redis 密码和 RPC token 不写入注册 metadata。首次配置不可达/非法时拒绝启动；组件初始化完成后注册服务，5 秒心跳、30 秒配置检查。短暂控制面网络失败重试，连续三次失败停止 Worker。配置变化关闭并清理现有现场，再由容器重启读取新配置；这是维护操作，不承诺现场迁移。

## 独立分支与本机 dev

三个仓库均使用 `ide-worker-nacos-debug-20261025` 分支，工作树位于 `worktrees/`。只从原工作区按文件清单导入 IDE Redis Worker、Gateway IDE 包及必要部署文件；没有切换或提交原工作区其他 session 的文件。

完整镜像构建仍使用 `sduoj-judger/ide-worker/Dockerfile` 中冻结的 Judger、工具和调试器镜像。已有冻结镜像可使用 `Dockerfile.overlay` 更新控制代码；构建前必须检查基础 tag 的 imageId 与 release lock 一致。不能把裸本地 `sha256:imageId` 当成 BuildKit 可解析的 registry digest。更新后的 debugger overlay 同步复制到 judge rootfs，并重新生成文件清单及工具链 stamp。

在独立 deploy 工作树执行：

```bash
python3 scripts/ide_unified_dev.py up --dev-env /原工作区/sduoj-deploy/data/dev/compose.env
python3 scripts/ide_unified_dev.py check --dev-env /原工作区/sduoj-deploy/data/dev/compose.env
```

本机 Gateway 为 `127.0.0.1:18086`，原 `8080` 和 Web2 不被替换。连接现有 AutoLab Redis 的 DB14，使用独立 `sduoj:ide:unified:20261025:` 前缀。dev Nacos 配置是独立 dataId，避免修改原 Judger 配置。脚本显式设置 Compose project，避免继承其他 session 的 COMPOSE_PROJECT_NAME。

验收使用 `scripts/ide_redis_dev_acceptance.py --base http://127.0.0.1:18086 --users ... --other-user ... --output ...`。检查真实登录、四语言补全/定义/参数提示/诊断、revision 重试、跨账号隔离，以及断点、单步、变量监视、实时输入输出、重复命令不重复执行、编译错误和运行超时。另运行 `ide_redis_dev_boundaries.py --base ... --user ... --output ...` 验证恢复、替换与路由边界。脚本只允许本机地址，不产生压力负载。

dev 的 privileged bootstrap 只作用于一次性容器私有 cgroup，降到 UID10001 后才消费任务。它用于本机内核正确性验证，**不能用于生产**；dev 的自动标记 profile 只具有 `local-dev-correctness-only` 范围。

## ARM 八副本初始配置

候选文件：`compose.ide-worker.arm64.candidate.yaml`、`templates/ide-worker.nacos.arm64.json`。它们是待 ARM 容器验收的部署候选，不等于生产已开启。

| 项目 | 单 Worker | 八副本合计 |
|---|---:|---:|
| Docker 管理/LSP CPU 上限 | 1 核 | 8 核 |
| Debug cgroup CPU 上限 | 1 核 | 8 核 |
| Docker 管理/LSP 内存硬上限 | 2 GiB | 16 GiB |
| Debug 内存硬上限 | 8 GiB | 64 GiB |
| Debug 正常许可预算 | 7 GiB | 56 GiB |
| Debug 许可内保留 | 256 MiB | 2 GiB |
| Debug 活跃运行上限 | 4 | 32 |
| Debug 驻留数量上限 | 128 | 1024 |
| 每语言 LSP 进程上限 | 1 | 8 |
| 单 LSP 进程文档上限 | 32 | 256 |

在 cgroup-v1 下，NsJail 进程会迁移到容器外显式委派的 Debug cgroup，仍留在容器 PID/文件系统隔离中，但不能假设它继续计入 Docker 的内存限制。两组控制分别限制：LSP/管理共16 GiB，加 Debug 硬上限64 GiB，总资源包络80 GiB；CPU两组各8核，总16核。必须在 ARM 实测确认迁移与父组限制，不能仅看 docker stats。

驻留数量是第二道数量上限，不能保证 1024 个实际现场同时放得下。内存、PID、宿主机余量任一不足都必须停止扩容，优先保存已有现场。Java 冷启动仍按语言限制为 1。各语言 profile 的启动/暂停实际内存决定最终驻留数量，不以单个 C++ Worker 的历史压测替代四语言混合容量验收。

浏览器最小间隔仍为 300ms；Gateway Redis 用户限流仍为 100ms 间隔、每秒5次、每分钟100次，LSP 超限返回空结果。Gateway 推荐初始 `maxQueue=16`、`maxPending=128`，超期补全和过时位置直接丢弃；这些是保护阈值，不是吞吐承诺。

Debug 每账号一个现场；5 分钟空闲、30 分钟绝对驻留、最多120秒排队；每次继续至下一停点按题目对应语言时限的2倍计时。停止/暂停走独立优先控制队列。源码、输入、程序输出按已有字节上限限制。编译使用冻结 Judger 的原 sandbox，保留模板版本、参数、PATH 与标准库；只追加调试信息、关闭优化。

## ARM 上线门槛与启动顺序

1. 核对实际 Judger 镜像、sandbox SHA、各模板版本及编译器/解释器版本；冻结新的统一 Worker image digest。dev 验收 stamp 不可复制为 ARM 正式验收证明。
2. 管理员为 UID10001 新建八组独立的 cgroup-v1 父组 `sduoj-ide-debug-01` 到 `08`。使用 `scripts/debug_cgroup_setup.py --uid 10001 --version 1 --parent sduoj-ide-debug-01 --hard-gib 8 --cpus 1 --pids 8192` 先只读检查，再对新空组使用 `--apply`；逐组执行，禁止修改现有业务父组。检查父组无残留、控制器确实挂载、层级内存限制有效。Docker userns-remap 若开启，必须按实际映射 UID 重新委派，不能照抄10001。
3. ARM 候选容器以非 root UID10001 运行，只绑定自身四个已委派 cgroup 子树，拒绝自动创建宿主机绑定目录。没有 Docker socket、host PID/network、privileged 或 SYS_ADMIN。为 newuidmap/newgidmap 保留 SETUID/SETGID；NoNewPrivileges 必须为0。外层 seccomp/AppArmor 暂采用 unconfined 以允许根less NsJail；内层仍强制 namespace、rootfs 只读、禁网、降权、seccomp 与 cgroup。该外层权限组合必须在 ARM 验证，不能以本机 privileged 测试替代。
4. 在独立前缀和受限验收组验证 ARM 容器四语言 Debug、编译错误/超时、运行超时、内存/PID/目录/网络隔离、进程树清理、Redis中断和 Worker 重启。通过后才生成与 image、overlay digest 和模板匹配的 accepted profiles，放入 root-owned 的 `IDE_ACCEPTED_CONFIG_DIR`。候选镜像内 profile 默认为未验收，缺少有效 profile 时启动失败。
5. 将 Nacos JSON 发布到正式 namespace 的 `ide-worker.yml`，在私有 env 文件设置 Nacos、AutoLab Redis URL、RPC token、Problem RPC地址、现有 Docker网络名、accepted config目录和不可变镜像digest。网关与 Worker 的 Redis prefix 必须一致。
6. 先单副本正确性冒烟，再按 2/4/8 个 Worker 分批启动。检查 Nacos 实例数、Redis角色注册、总预算、debug活跃/驻留/排队和宿主机业务指标。只有验收通过后启用正式 Gateway 的 IDE/Debug 开关；不重启 Judger 业务来发布 IDE。

## 停机、回滚与异常恢复

停止 Gateway 新建调试入口，再按 Worker 逐个停止，至少保留60秒优雅退出。停止时取消消费、关闭实际沙箱树、发布最后终止事件、释放许可，并注销 Nacos/Redis incarnation。运行中的程序另有 guardian 截止，不能依赖前端保活实现资源回收。

回滚使用上一版 Gateway jar/镜像及部署配置，不修改现有 Problem/Judger。停止新 Worker 后需验证所有委派子组空，再决定是否回收专用 Redis 元数据。禁止 FLUSHDB、删除 AutoLab 键或自动清除无法证明已释放的预算 reservation。异常退出留下的 reservation 需要核验容器/PID命名空间与 cgroup 均为空后，由管理员按对应 incarnation 精确清理；不能以 TTL 到期作为现场消失的证据。
