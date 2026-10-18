# 01 云 Agent 系统（多 harness · 沙箱 · S3 工作区）

> 目标：把「单实例进程内维护 Codex 会话」改造为**可在云端多节点并发、租户安全隔离、可升级、可用对象存储当文件系统的高性能执行层**。
>
> 本文只定义执行层。业务能力（端口、MCP、题目、查重、考务）见 02–05。

## 1. 现状与差距（事实）

### 1.1 今天是怎么跑的

| 事实 | 位置 | 影响 |
| --- | --- | --- |
| Codex 以 `subprocess` 拉起 `app-server --listen stdio://`，会话对象存进程内 `RUNTIMES` 字典 | `auto_task/management_agent.py` | **单实例**。多 worker 或多节点下会话不可达 |
| 写死 `codex` 二进制，仅可用 `AUTOLAB_CODEX_BIN` 覆盖 | 同上 | **无 harness 抽象**，加 DSH 必须改这一处 |
| `wire_api = "responses"`、`model_provider` 可指向任意 `base_url` + `env_key` | 同上（生成的 `config.toml`） | **好消息**：harness 天然支持自建端口，02 可直接复用 |
| 沙箱 = `docker run`，`--network none`、`--cap-drop ALL`、`--read-only`、`--pids-limit 64`、`--memory`、`--cpus 1`、`--user 65534`、tmpfs | `auto_task/sandbox.py` | 单次执行的隔离是合格的，但**无持久工作区、无快照、无 S3** |
| 任务队列 = MySQL 租约 + 心跳 + Redis 唤醒，三层限额（全局/每用户/通道） | `store.py`、`worker.py` | **可直接复用**为 02 的调度基础 |
| 官方文档已声明：单实例、多实例需粘滞或独立执行服务 | `sduoj-deploy/docs/INTELLIGENT_MANAGEMENT.md` | 与本设计结论一致 |

### 1.2 必须解决的五个缺口

1. **无 harness 抽象**：只有 Codex，无法接第二个。
2. **无版本管理**：harness 版本靠运维手动装；文档只记录了「已验证 0.154.0-alpha.6.2」，没有检测、灰度、回滚。
3. **无多节点会话归属**：会话绑在进程内，无法调度到空闲节点。
4. **工作区是本地目录**：`safe_path()` 落在单机磁盘，无法跨节点、无法扩缩容、无共享文件系统。
5. **沙箱无快照与预热**：每次 `docker run` 冷启动，且没有「基镜像 + 增量层」的概念。

## 2. 目标架构

```
                        ┌──────────────────────────────┐
   02 端口/作业 ───────▶│  Agent 调度器 (Scheduler)     │
                        │  · 按队列优先级取作业          │
                        │  · 选节点(负载/镜像/租户亲和)   │
                        │  · 端口并发额度检查            │
                        └──────────────┬───────────────┘
                                       │ 派发(带租约)
        ┌──────────────────────────────┼──────────────────────────────┐
        ▼                              ▼                              ▼
┌───────────────┐            ┌───────────────┐            ┌───────────────┐
│ Runner Node A │            │ Runner Node B │            │ Runner Node C │
│ ┌───────────┐ │            │               │            │               │
│ │ Harness   │ │  1 作业 =  1 沙箱容器         │            │               │
│ │ Adapter   │ │            │               │            │               │
│ │(dsh|codex)│ │            │               │            │               │
│ └─────┬─────┘ │            │               │            │               │
│       │ stdio │            │               │            │               │
│ ┌─────▼──────────────────────────────────────────────────────┐        │
│ │ 沙箱容器: /work (S3 挂载) + /tmp + 只读基镜像              │        │
│ │ seccomp / no-network / cap-drop / pids / 只读根            │        │
│ └─────┬──────────────────────────────────────────────────────┘        │
└───────┼───────────────────────────────────────────────────────────────┘
        │ MCP over stdio/HTTP（只出站到 Autolab）
        ▼
   OJ 能力网关（见 02）
```

**四条设计原则**

1. **一个作业一个沙箱**，不共享文件系统。跨作业共享只发生在 S3 上的版本化产物。
2. **harness 是可替换的运行时**，不是系统的中心。它只负责「读提示词 + 调工具 + 产出结果」。
3. **状态全部外置**：会话、事件、工作区、产物都落在数据库或 S3，节点可随时销毁。
4. **默认拒绝**：没显式授予的能力（网络、文件、工具）一律不可用。

## 3. Harness 抽象

### 3.1 接口

```python
# auto_task/harness/base.py（新增）
class HarnessSpec(BaseModel):
    name: Literal["dsh", "codex"]
    version: str                      # 语义化版本，见 §7
    binary_env: str                   # 定位可执行文件的 env 名
    wire_api: Literal["responses", "chat_completions"]
    supports_dynamic_tools: bool
    supports_resume: bool
    max_prompt_bytes: int

class HarnessSession(Protocol):
    async def start(self, *, spec, workdir, system_prompt, tools, env, model) -> str:
        """启动 harness，返回外部会话 id（可持久化）。"""

    async def send(self, session_id: str, text: str) -> None:
        """追加一轮用户输入。"""

    async def resume(self, session_id: str) -> None:
        """从持久化状态恢复（节点漂移时使用）。"""

    def events(self) -> AsyncIterator[HarnessEvent]:
        """统一事件流：delta / tool_call / plan / turn_done / error。"""

    async def close(self) -> None: ...
```

`HarnessEvent` 统一为：

```python
@dataclass
class HarnessEvent:
    kind: Literal["text_delta", "message", "tool_call", "plan", "turn_done", "error"]
    data: dict            # tool_call: {call_id, tool, arguments}
```

**关键约定**：`tool_call` 事件由**适配器**统一翻译。Codex 用 `item/tool/call`，DSH 用其自有事件，但上层（审批、审计、执行）只认 `HarnessEvent`。

### 3.2 Codex 适配器（首个实现）

直接迁移现有 `management_agent.py` 的协议部分，保持已验收行为不变：

| 项 | 值 |
| --- | --- |
| 启动 | `<bin> app-server --listen stdio://` |
| 握手 | `initialize`（`experimentalApi: true`）→ `initialized` |
| 建会话 | `thread/start`（`dynamicTools`）或 `thread/resume`（`threadId`） |
| 输入 | `turn/start`（`input: [{type:"text"}]`） |
| 工具回调 | 收 `item/tool/call`，回 `{id, result:{success, contentItems}}` |
| 配置 | 写入 `config.toml`：`approval_policy="on-request"`、`sandbox_mode="read-only"`、禁用 shell/apps/multi_agent/goal/web_search，`[model_providers.oj]` 指向用户端口 |
| 已验证版本 | `0.154.0-alpha.6.2` |

### 3.3 DSH 适配器（第二实现）

**已核实的事实**：

- DSH CLI 位于 `runtime/cli/bin/dsh`，版本 `0.2.1-rc.2`（本机安装）。
- 提供 `dsh headless "<task>"` —— 一次任务、打印结果、退出，正是无头执行所需形态。
- 通过 `$DSH_HOME/profiles` 组织插件层，支持 `--patch` 叠加配置。

**未验证的部分（必须实测）**：`headless` 的
① 是否支持**多轮会话**与**会话恢复**；
② 是否支持**动态工具/外部 MCP**；
③ 事件流是否为结构化 JSON（还是纯文本）。

→ 因此任务清单把「DSH 能力探测」列为 01 的第一个任务，**探测未通过则不得切换**。

**适配策略**：若 DSH 支持 MCP，则把 OJ 工具以 **MCP server** 形式挂载（与 02 的 MCP 网关共用一份规范），使两套 harness 走同一条工具通道；若不支持，则退化为「headless 单轮 + 由调度器串多轮」，并在文档中显著标注能力差异。

## 4. 沙箱

### 4.1 现有隔离机制的评估

`sduoj-sandbox/`（评测量）用 `setrlimit` + `seccomp` + `setuid`，**没有 namespace / chroot / pivot_root**（已核查 `src/container/container.c` 中只有 `setrlimit`、`seccomp`、`setgid/setgroup`）。它适合「跑一段不可信但结构固定的选手代码」，**不适合**承载一个能执行任意 shell 的 agent。

`auto_task/sandbox.py` 的 Docker 方案才是正确方向：
```
--network none  --cap-drop ALL  --read-only  --security-opt no-new-privileges
--pids-limit 64 --memory 256m   --cpus 1     --user 65534:65534
--tmpfs /tmp:rw,noexec,nosuid,size=64m       bind-mount /workspace
```

### 4.2 面向 agent 的强化要求

| 维度 | 现状 | 目标 |
| --- | --- | --- |
| 网络 | `--network none` | 保持；仅允许**显式出站**到 MCP 网关（用独立 `--network` + 白名单网关） |
| 文件系统 | 单目录 bind mount | `/work` = S3 挂载，`/tmp` tmpfs，其余只读 |
| 进程 | `--pids-limit 64` | 保持 |
| 内核攻击面 | runc 共享内核 | 可选 **gVisor（`runsc`）** 或 **Firecracker**，按租户等级选择 |
| 生命周期 | 一次性 | 支持**暂停/恢复**（checkpoint）以加速冷启动 |
| 资源计量 | 容器限额 | cgroup v2 计量 + 作业后汇总记账 |

> 说明：gVisor / Firecracker 属于**运行时隔离**（缩小内核攻击面），与「沙箱」不是同一层次的概念。建议默认用 runc + 强化 seccomp，对**多租户公开场景**再升到 gVisor。

### 4.3 镜像策略

- **基镜像固定**：`sduoj-agent-base:<digest>`（含 node/python/git/常用 CLI），digest 锁定，不使用 `:latest`。
- **语言镜像复用**现有 `AUTOLAB_SANDBOX_<LANG>_IMAGE` 约定（`gcc:14-bookworm`、`python:3.13-slim`、`eclipse-temurin:21-jdk`）。
- **预热**：节点常驻 `docker pull` + 定期 `docker run true` 校验可启动。

## 5. S3 工作区（挂载为标准文件系统）

### 5.1 为什么不是「把本地目录换成 S3 SDK」

agent 与 harness 期望的是**普通 POSIX 路径**（`README.md`、`src/main.py`、`git status`）。用 SDK 改造所有工具不现实，必须提供**真实挂载点**。

### 5.2 方案对比

| 方案 | 原理 | 优点 | 缺点 | 结论 |
| --- | --- | --- | --- | --- |
| **s3fs-fuse** | FUSE 把 S3 映射为目录 | 成熟、支持 POSIX 大部分语义、可本地缓存 | 元数据操作慢；不适合高并发小文件 | **推荐**（配合本地缓存） |
| **JuiceFS** | 元数据引擎(Redis/MySQL) + S3 数据层 | 元数据极快、多节点共享一致、支持快照 | 需额外组件 | **多节点共享首选** |
| rclone mount | 轮询同步 | 简单 | 最终一致、延迟高 | 仅归档场景 |
| goofys | FUSE，弱一致性 | 简单 | 弱语义 | 不推荐 |

### 5.3 推荐配置

```yaml
# 挂载进沙箱
- /work        → JuiceFS volume  tenants/<tenant>/agent/<job_id>   (读写，本地缓存 2G)
- /work/.inputs → S3 前缀      tenants/<tenant>/jobs/<job_id>/inputs  (只读)
- /tmp          → tmpfs 64m
- 其余根目录     → 只读基镜像
```

**目录约定**（与 00 总纲一致）：

```
tenants/<tenant>/
  agent/<job_id>/              作业工作区（可写，保留 7 天）
    README.md, src/, notes/
  jobs/<job_id>/inputs/        输入快照（只读，哈希固定）
  jobs/<job_id>/artifacts/     产物（结果、补丁、报告、日志）
  problems/<problemId>/        题目资源（图/文档/数据包）
  exam-material/<examId>/      考务材料（密码条/签到表）
  plagiarism/<scanId>/         查重报告
```

### 5.4 一致性要求

- **输入快照不可变**：派发前把输入写入 `jobs/<id>/inputs/` 并记录 `sha256`，作业只读它。这与现有 `TaskInput` 表（`content` + `sha256`）语义一致。
- **产物提交是显式动作**：作业结束由 Runner 扫描 `artifacts/` 上传并登记，**不依赖 FUSE 的最终一致性**。
- **失败清理**：作业终态后保留 `N` 天再回收；`credentials` 之类敏感文件禁止写入工作区（由 seccomp/路径白名单拦截）。

## 6. 并发与多节点

### 6.1 调度模型

沿用现有「MySQL 租约」作为权威，增加**节点维度**：

```sql
-- 新表：执行节点注册
CREATE TABLE auto_agent_node (
  node_id      VARCHAR(63) PRIMARY KEY,
  endpoint     VARCHAR(255) NOT NULL,
  labels       JSON NOT NULL,            -- {"runtimes":["docker","runsc"],"harnesses":["codex","dsh"]}
  capacity     INTEGER NOT NULL,         -- 最大并发作业数
  in_flight    INTEGER NOT NULL DEFAULT 0,
  heartbeat_at DATETIME(6) NOT NULL,
  version      VARCHAR(63) NOT NULL,
  status       VARCHAR(24) NOT NULL DEFAULT 'healthy'
);
```

- Runner 每 5s 上报心跳与 `in_flight`，超 30s 未上报标记 `unhealthy`，其上作业租约到期后由别的节点接管。
- **作业亲和**：优先派发到已缓存该镜像与租户工作区的节点（`labels.cached`），减少冷启动。
- **租户隔离**：同一租户的作业可共享节点缓存，但**不同租户不得共享可写卷**。

### 6.2 并发额度（四层）

| 层 | 来源 | 说明 |
| --- | --- | --- |
| 全局 | `auto_task_setting.runtime.max_concurrency` | 已存在 |
| 每用户 | `per_user_concurrency` | 已存在 |
| 通道 | `agent/sandbox/document_concurrency` | 已存在（`claim()` 中的 `lane()`） |
| **每端口** | **`auto_ai_port.max_concurrency`** | **新增，见 02** |

四层都必须满足才能领取作业。实现上只需在 `claim()` 的候选过滤里增加一条端口维度的在跑计数（现有 `active` 列表已经在手）。

### 6.3 节点漂移

会话可能从 A 节点漂到 B 节点。要求 harness 满足其一：

1. **可恢复**：`resume(session_id)` 从 S3/DB 重建上下文（Codex 支持 `thread/resume`）；
2. **不可恢复但可归档**：则作业绑定节点，节点失联时作业失败并**明确告知用户**「会话已中断」，禁止静默重跑已执行的写操作。

## 7. 版本管理

### 7.1 版本清单

```yaml
# auto_task/harness/versions.yaml（随代码发布）
harnesses:
  codex:
    pinned: "0.154.0-alpha.6.2"       # 已验证
    allowed: [">=0.150.0 <0.160.0"]
    check: ["codex --version"]        # 启动时探测
    protocol: "app-server/1.0"
  dsh:
    pinned: "0.2.1-rc.2"
    allowed: [">=0.2.0 <0.3.0"]
    check: ["dsh --version"]
    protocol: "headless/1.0"
sandbox:
  image: "sduoj-agent-base@sha256:<digest>"
  docker_min: "24.0"
```

### 7.2 检测与灰度

1. **启动自检**：Runner 启动时执行 `check`，版本不在 `allowed` 区间则**拒绝启动**（fail-closed），而不是降级运行。
2. **灰度**：`auto_ai_port` 可指定 `harness` 与 `harness_version`，按用户/端口逐个切换（见 02）。
3. **回滚**：版本清单是代码，回滚 = 回滚代码 + 重启 Runner；作业级无残留状态（会话在 S3/DB），天然可回滚。
4. **契约测试**：升级前跑 `tests/harness_contract.py`（握手、工具回调、取消、超时、恢复），通过才允许改 `pinned`。

### 7.3 与现有文档的关系

`INTELLIGENT_MANAGEMENT.md` 中「已验证本机 0.154.0-alpha.6.2 的协议」这一事实**保留**，并把 `versions.yaml` 作为唯一权威来源，避免文档与代码各说各话。

## 8. 数据模型变更

```sql
-- 会话归属外部化（取代进程内 RUNTIMES）
CREATE TABLE auto_agent_session (
  id              VARCHAR(63) PRIMARY KEY,
  resource_id     VARCHAR(63) NULL,           -- ai_resource.id (kind=agent_session)
  owner_id        VARCHAR(64) NOT NULL,
  harness         VARCHAR(24) NOT NULL,
  harness_version VARCHAR(63) NOT NULL,
  port_id         VARCHAR(63) NOT NULL,       -- 见 02
  node_id         VARCHAR(63) NULL,
  external_id     VARCHAR(128) NULL,          -- thread_id / session 句柄
  work_uri        VARCHAR(255) NOT NULL,      -- s3://.../agent/<job_id>/
  state           VARCHAR(24) NOT NULL,       -- idle/running/closed/failed
  created_at      DATETIME(6) NOT NULL,
  updated_at      DATETIME(6) NOT NULL,
  INDEX ix_agent_session_owner (owner_id, state)
);

-- 作业→节点/沙箱的执行记录
CREATE TABLE auto_agent_execution (
  id           VARCHAR(63) PRIMARY KEY,
  job_id       VARCHAR(63) NOT NULL,          -- auto_task_job.id
  node_id      VARCHAR(63) NOT NULL,
  container_id VARCHAR(128) NULL,
  harness      VARCHAR(24) NOT NULL,
  started_at   DATETIME(6) NOT NULL,
  ended_at     DATETIME(6) NULL,
  exit_code    INTEGER NULL,
  cpu_ms       BIGINT NULL,
  mem_peak_mb  INTEGER NULL,
  disk_bytes   BIGINT NULL,
  INDEX ix_exec_job (job_id)
);
```

## 9. 实施顺序

| 步 | 内容 | 验收 |
| --- | --- | --- |
| 1 | DSH 能力探测（多轮 / MCP / 事件结构） | 结论写入文档，未通过则不推进 |
| 2 | 抽出 `Harness` 接口，Codex 适配器行为不变 | 现有智能管理测试全绿 |
| 3 | 会话外部化 + 节点注册 + 心跳 | 杀掉节点后作业能被他节点接管或明确失败 |
| 4 | S3 工作区（JuiceFS）挂载 + 输入快照 | 两节点读同一作业输入结果一致 |
| 5 | 沙箱强化（seccomp、出站白名单、可选 gVisor） | 逃逸测试用例全部失败 |
| 6 | 版本管理 + 灰度开关 | 版本不符时 Runner 拒绝启动 |
| 7 | DSH 适配器上线（灰度） | 同一作业在两套 harness 产出可比结果 |

## 10. 风险

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| DSH headless 不支持多轮/MCP | 第二 harness 价值下降 | 先探测；必要时用「单轮 + 调度器串接」，并如实标注 |
| FUSE 性能不足 | 编译/大文件操作慢 | 本地缓存 + 产物显式上传；避免大量小文件元数据操作 |
| 多节点一致性 | 同一作业被两节点执行 | 租约 + `fenced()` 已有 fencing token，直接复用 |
| 沙箱逃逸 | 多租户数据泄露 | 默认 runc 强化；公开场景上 gVisor；seccomp 白名单 |
| 会话恢复不完整 | 用户感到「记忆丢失」 | 明确 UI 提示；关键上下文写入 `notes/` 而非依赖会话 |
