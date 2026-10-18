# 02 AI 端口与 MCP

> 目标三件事：**① 平台不提供任何默认 AI 服务，全由用户自建端口；② 统一队列管理后台 agent，按端口限额；③ 通过 MCP 以用户身份操作 OJ，用提示词约束而非硬编码 workflow。**
>
> 依赖：01 的执行层。本层只负责「谁的哪个端口、跑哪个 harness、能用哪些工具、排队与限额」。

## 1. 现状与差距

| 事实 | 位置 | 结论 |
| --- | --- | --- |
| provider 是**站点级单例**：`AiSetting.id="runtime"`，只有一个 `base_url/model/key` | `auto_task/configuration.py` | 需提升为**多端口注册表** |
| 只支持 `codex` 与 `chat_completions` 两种 provider 形态 | 同上（`provider_supported`） | 需明确以 **Responses** 为一等公民 |
| 凭证 Fernet 加密、绝不回传、改端点必须换 key、版本冲突 409、SSRF/HTTPS 校验 | 同上 | **直接复用**，扩展为多行 |
| 已有按用途的 `model_overrides`（moderation/grading/authoring/tutor） | 同上 | 可保留，作为端口的可选覆盖 |
| 队列：MySQL 租约 + 心跳 + 三层限额 + `skip_locked` 防饿死 | `store.py` `claim()` | **直接复用**，增加端口维度 |
| 工具白名单 + 逐次审批 + 只读沙箱 | `management_agent.py` | 演进为 **MCP 工具规范** |
| 旧 AI 批阅走 `subjective_review.py` + `TaskJob(task_type=...)` | 后端 | **改为走 agent** |

**注意**：现有 `/settings` 保持不动（运维仍可用它配置站点兜底）。用户端口是**新增的一层**，优先级高于站点配置。

## 2. AI 端口模型

### 2.1 概念

「端口」= 一个可调用的模型服务接入点：

```
port = { 展示名, base_url, api_key(加密), model, wire_api=responses,
         并发上限, 单次成本上限, 是否默认, 可见范围 }
```

### 2.2 硬性规则（来自需求）

1. **平台不内置任何 AI**。未配置端口时，所有 AI 功能返回 `503 port_not_configured` 并给出引导，**不回退到任何内置模型**。
2. **必须支持 Responses 接口**。`wire_api` 固定为 `responses`；`chat_completions` 仅作兼容保留，默认拒绝。
3. **必须在端口上指定模型**。`model` 必填，不允许「由服务端猜」。
4. **可配多个端口，但只有一个默认**。用部分唯一索引保证全局唯一默认。
5. **所有 AI 功能都走默认端口**（除非任务显式指定端口且该用户有权限）。

### 2.3 数据模型

```sql
CREATE TABLE auto_ai_port (
  id                 VARCHAR(63) PRIMARY KEY,
  owner_id           VARCHAR(64) NOT NULL,          -- 创建者；NULL = 站点级(仅超管可建)
  scope              VARCHAR(16) NOT NULL,          -- 'user' | 'site'
  name               VARCHAR(64) NOT NULL,          -- 展示名，用户可读
  base_url           VARCHAR(2048) NOT NULL,
  api_key_cipher     TEXT NOT NULL,                 -- Fernet 密文，永不回传
  key_fingerprint    VARCHAR(16) NOT NULL,          -- sha256 前 8 字节，用于「换没换」提示
  model              VARCHAR(128) NOT NULL,
  wire_api           VARCHAR(24) NOT NULL DEFAULT 'responses',
  harness            VARCHAR(24) NOT NULL DEFAULT 'codex',
  harness_version    VARCHAR(63) NOT NULL,
  reasoning_effort   VARCHAR(16) NOT NULL DEFAULT 'medium',
  max_concurrency    INTEGER NOT NULL DEFAULT 2,    -- 端口并发上限（需求明确要求）
  max_job_cost_usd   NUMERIC(10,4) NOT NULL DEFAULT 2,
  monthly_budget_usd NUMERIC(12,2) NOT NULL DEFAULT 0,   -- 0 = 不限
  is_default         TINYINT NOT NULL DEFAULT 0,
  status             VARCHAR(16) NOT NULL DEFAULT 'active',  -- active|disabled|invalid
  version            INTEGER NOT NULL DEFAULT 1,
  created_at         DATETIME(6) NOT NULL,
  updated_at         DATETIME(6) NOT NULL,
  UNIQUE KEY uq_port_default (owner_id, is_default, status),
  INDEX ix_port_owner (owner_id, status)
);
```

**唯一默认的实现**：MySQL 部分索引受限，改为：

```sql
-- 在事务内，设置默认前先清掉同 owner 的其他默认
UPDATE auto_ai_port SET is_default = 0 WHERE owner_id = ? AND is_default = 1;
UPDATE auto_ai_port SET is_default = 1 WHERE id = ? AND owner_id = ?;
```

并用行级锁 `SELECT ... FOR UPDATE` 保证并发下仍只有一个默认。

### 2.4 与站点配置的关系

```
解析优先级：任务指定 port_id（需有权限）
          → 用户默认端口
          → 站点默认端口（超管建的 scope='site'）
          → 503 未配置
```

站点配置 `/settings` 保留为「兜底端口」，在 UI 上标注为「全站兜底」。

## 3. 接口

> 全部挂在 `/api/ps/auto-task/ai` 下，沿用现有 `api_response()` 包体与 `{code:0, data, msg}` 约定。

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| `GET` | `/ports` | USER | 列出我的端口（**永不返回密钥**，只返回 `has_key` 与 `key_fingerprint`） |
| `POST` | `/ports/create` | USER | 新建端口 |
| `POST` | `/ports/{id}/update` | 属主 | 更新；改 `base_url/model` 必须重新提供 `api_key` |
| `POST` | `/ports/{id}/delete` | 属主 | 软删；若有运行中作业拒绝 `409` |
| `POST` | `/ports/{id}/default` | 属主 | 设为唯一默认 |
| `POST` | `/ports/{id}/test` | 属主 | 连通性探测（只回 `{ok, latency_ms, status, model_present}`，**不回响应体**） |
| `GET` | `/ports/{id}/usage` | 属主 | 近 30 天调用数、token、成本、失败率 |
| `GET` | `/admin/ports` | ADMIN | 全站端口总览（用于配额与滥用排查） |
| `POST` | `/admin/ports/{id}/disable` | ADMIN | 禁用违规端口 |

### 3.1 创建请求

```json
{
  "name": "我的 DeepSeek",
  "base_url": "https://api.example.com/v1",
  "api_key": "sk-...",
  "model": "deepseek-v4.1-flash",
  "wire_api": "responses",
  "harness": "codex",
  "harness_version": "0.154.0-alpha.6.2",
  "reasoning_effort": "medium",
  "max_concurrency": 2,
  "max_job_cost_usd": 2,
  "monthly_budget_usd": 20,
  "is_default": true
}
```

### 3.2 校验规则（服务端强制）

| 规则 | 错误 |
| --- | --- |
| `base_url` 必须 https（回环调试除外）、无 userinfo/query/fragment | `400` |
| 禁止内网地址（RFC1918、链路本地、元数据 `169.254.169.254`） | `400 ssrf_blocked` |
| `wire_api != "responses"` 且未显式开启兼容 | `400 responses_required` |
| `model` 为空 | `400 model_required` |
| `max_concurrency` ∈ [1, 32] | `400` |
| 改端点未带新 key | `409 endpoint_change_requires_key` |
| 版本冲突 | `409` |
| 同用户已有默认且未指定替换 | `409`（由前端二次确认） |

### 3.3 探测实现

```python
# 与现有 provider_health 同构，但按端口
r = requests.get(base_url + "/models", headers={"Authorization": "Bearer " + key},
                 timeout=(5, 15), allow_redirects=False)
# 只暴露：可达性、HTTP 状态、model 是否在列表内（不暴露任何正文）
```

**安全要点**：探测请求必须走**出口白名单代理**或显式禁用重定向（`allow_redirects=False`），防止借 SSRF 打内网。

## 4. 统一队列与端口限额

### 4.1 作业字段扩展

```sql
ALTER TABLE auto_task_job
  ADD COLUMN port_id VARCHAR(63) NULL,
  ADD COLUMN harness VARCHAR(24) NULL,
  ADD CONSTRAINT fk_job_port FOREIGN KEY (port_id) REFERENCES auto_ai_port(id);
```

### 4.2 领取时的四层检查

在现有 `claim()` 中，`lane()` 判定旁增加：

```python
# 端口维度：同一 port 的在跑作业数 ≤ port.max_concurrency
port_load = {}
for a in active:
    if a.port_id:
        port_load[a.port_id] = port_load.get(a.port_id, 0) + 1
if job.port_id:
    port = ports.get(job.port_id)
    if port is None or port.status != "active":
        # 端口被禁用：作业转入 blocked，等待用户修复
        job.status, job.error = "blocked", "AI port unavailable"
        continue
    if port_load.get(job.port_id, 0) >= port.max_concurrency:
        continue
```

**排序**：`created_at` 升序（FIFO），但**跨端口不互相阻塞**——A 端口打满时，B 端口的作业仍可领取（`skip_locked` + 继续扫描已保证这一点）。

### 4.3 超出限额时的行为

| 情形 | 行为 |
| --- | --- |
| 端口并发已满 | 作业保持 `pending`，前端显示「排队中：等待端口空闲」 |
| 每用户并发已满 | 同上，显示「排队中：你的并发已满」 |
| 月度预算耗尽 | 作业 `blocked`，`error=budget_exhausted`，**不自动重试** |
| 端口被禁用/密钥失效 | 作业 `blocked`，通知用户修复后手动重试 |
| 队列超长（`max_queued_per_user`） | 拒绝创建，`429 queue_full` |

### 4.4 可见性

新增 `GET /jobs/{task_id}` 已存在；补充返回字段：

```json
{ "queue_position": 3, "port": {"id":"...","name":"我的 DeepSeek"}, "harness":"codex", "blocked_reason": null }
```

`/admin/queue` 增加按端口聚合的视图。

## 5. MCP：让 agent 以用户身份操作 OJ

### 5.1 设计取舍：为什么用 MCP

- **提示词驱动、非硬编码 workflow**：工具是**能力**，不是步骤。模型自行决定先读后写、查错重试。
- **跨 harness 通用**：Codex 与 DSH 都能挂 MCP server，一套规范两处复用。
- **权限天然等价**：MCP server 运行在 Autolab 侧，调用时按「发起作业的用户」重新施加权限校验。

### 5.2 身份模型（关键）

```
用户浏览器 ──Cookie──▶ 网关 ──SDUOJUserInfo──▶ Autolab (创建作业，记录 owner_id)
                                                      │
                                                      ▼ 派发作业(owner_id, port_id, tools)
                                              Runner / harness
                                                      │ MCP tool call（不带任何用户凭证）
                                                      ▼
                                            Autolab MCP 网关
                                                      │ 以 owner_id 重新构造 SDUOJUserInfo
                                                      ▼
                                              OJ 各服务（按该用户原始权限判定）
```

**三条铁律**：

1. **harness 侧不持有任何用户凭证**。MCP 请求只带 `job_token`（作业级、短期、绑定 `job_id + owner_id`）。
2. **每次工具调用都重新鉴权**。用户权限在调用时实时判定，**会话期间被撤销的权限立即失效**。
3. **越权即失败**。工具返回 `403`，并记录审计；模型收到错误后应停止而非绕过。

### 5.3 工具清单（v1）

工具名用 `oj.<域>.<动作>`，避免模型猜测。

| 工具 | 作用 | 权限 |
| --- | --- | --- |
| `oj.problem.search` | 按关键字/标签/可见性检索题目 | USER |
| `oj.problem.get` | 读题目详情与题面 | 按题目可见性 |
| `oj.problem.create` | 建题 | USER（限本人） |
| `oj.problem.update_description` | 写/改题面 | 属主或管理组 |
| `oj.problem.upload_testcase` | 上传单个测试点（小数据） | 属主或管理组 |
| `oj.problem.set_checkpoints` | 设置测试点与分值 | 同上 |
| `oj.exam.list` / `oj.exam.get` | 读考试 | 管理组/ADMIN |
| `oj.exam.prepare` / `oj.exam.publish` | 组卷与发布 | 管理组/ADMIN（**高危，需二次确认**） |
| `oj.seat.assign` | 座位分配写回 | 管理组/ADMIN |
| `oj.group.add_members` | 组员导入 | 管理组/ADMIN |
| `oj.plagiarism.scan` | 发起查重 | 管理组/ADMIN |
| `oj.submission.list` | 读提交（不含他人隐私字段） | 按题目权限 |
| `oj.user.profile` | 读当前身份与权限（用于自检） | 本人 |

**不提供的工具**：任意 SQL、任意 HTTP、文件系统、删除用户、改密码、读他人密钥。

### 5.4 工具定义格式

```json
{
  "name": "oj.problem.get",
  "description": "读取一道题目的元数据与题面。返回题面 markdown 与测试点配置。",
  "inputSchema": {
    "type": "object",
    "properties": {
      "problem_code": {"type": "string", "description": "形如 SDUOJ-123"},
      "include_tests": {"type": "boolean", "default": false}
    },
    "required": ["problem_code"],
    "additionalProperties": false
  }
}
```

**返回约定**：统一 `{ok: bool, data?: any, error?: {code, message}}`；错误信息面向模型可读，**不泄露内部栈**。

### 5.5 审批策略（保留，但分层）

现有「每次工具调用都要 UI 确认」对只读操作过重。v2 采用**按风险分级**：

| 级别 | 动作 | 策略 |
| --- | --- | --- |
| L0 只读 | search/get/list/profile | **自动放行**，记录审计 |
| L1 低危写 | 上传测试点、改组名 | 首次确认，同一作业内同参数可记住 |
| L2 中危写 | 建题、写题面、加组员 | **逐次确认**（现状） |
| L3 高危 | publish、座位写回、查重写回、删资源 | 逐次确认 + **二次确认弹窗**（输入确认短语） |

**这不是弱化安全**：L0 只读在权限体系内天然安全；L3 反而比现状更严。策略可由管理员在站点设置里收紧为「全部逐次确认」。

### 5.6 审计

复用 `AiLedger`/新增审计表：

```sql
CREATE TABLE auto_agent_tool_audit (
  id             VARCHAR(63) PRIMARY KEY,
  job_id         VARCHAR(63) NOT NULL,
  owner_id       VARCHAR(64) NOT NULL,
  tool           VARCHAR(64) NOT NULL,
  arguments_hash VARCHAR(64) NOT NULL,
  risk_level     TINYINT NOT NULL,
  decision       VARCHAR(16) NOT NULL,   -- auto|approved|denied|failed
  result_code    INTEGER NULL,
  duration_ms    INTEGER NULL,
  created_at     DATETIME(6) NOT NULL,
  INDEX ix_tool_audit_job (job_id, created_at)
);
```

## 6. 替代旧 AI 主观题批阅

### 6.1 现状

`auto_task/subjective_review.py` + `TaskJob(task_type="subjective_review")`：固定提示词、固定输出 schema、固定评分流程。

### 6.2 改造

| 项 | 旧 | 新 |
| --- | --- | --- |
| 触发 | 后端任务 | 后端创建 agent 作业（保留同一入口，前端无感） |
| 提示词 | 硬编码在 Python | `auto_task/agent_prompts/grading/<subject>.md`，可被课程管理组覆盖 |
| 执行 | 直接调 LLM | harness + MCP 工具（读提交、读评分标准、写评语） |
| 输出 | 固定 schema | 仍然强制 schema（**批阅是高风险动作，不能放开**） |
| 审核 | 无 | 教师复核队列（`AiReview` 已存在） |

**关键约束**：批阅结果**先入草稿**，必须教师确认后才回写成绩。这一点不因引入 agent 而放松。

### 6.3 兼容期

- 保留 `task_type="subjective_review"` 的旧实现一个版本；
- 通过站点开关 `grading_engine = legacy | agent` 切换；
- 新实现上线后跑双跑对比（同一批提交，两条链路结果差异率），差异 > 阈值则回退。

## 7. 提示词与「不再走严格 workflow」

### 7.1 结构

```
auto_task/agent_prompts/
  base/system.md              # 通用：身份、诚实、禁止猜测、工具使用礼仪
  task/authoring.md           # 出题
  task/grading.md             # 批阅
  task/exam_prep.md           # 考务（来自 exam-prep/management_guides/exam_prep.md）
  task/plagiarism.md          # 查重解释
```

每次作业组装：`base/system.md` + `task/<kind>.md` + 本次输入摘要 + 可用工具清单。

### 7.2 从「workflow」到「提示词 + 检查清单」的边界

| 保留硬约束 | 放弃硬约束 |
| --- | --- |
| 输出 schema（批阅、结构化结果） | 「必须先调 A 再调 B」的固定顺序 |
| 高危动作审批 | 「每步必须返回固定 JSON」的中间态 |
| 权限与配额 | 用代码模拟的「思考步骤」 |
| 失败不自动重试写操作 | 固定的重试次数与分支 |

**理由**：模型在自由决策下表现更好，但**副作用类**操作必须可审计、可中断、可人工兜底。

## 8. 前端（详见 08）

- 新增「AI 端口」页：列表（名称/模型/默认标记/并发/近 7 天用量/状态）+ 新建/编辑弹窗 + 「测试连接」按钮。
- 端口密钥输入后**永不回显**，只显示 `sk-****abcd`（`key_fingerprint`）。
- 作业列表显示端口名、排队位置、harness 版本。
- 未配置端口时，所有 AI 入口显示统一引导卡片（不是空白或报错）。

## 9. 实施顺序

| 步 | 内容 | 验收 |
| --- | --- | --- |
| 1 | `auto_ai_port` 表 + CRUD + 唯一默认 | 并发设默认只成功一个 |
| 2 | 端口解析优先级 + 未配置 503 | 未配端口时 AI 入口给出引导 |
| 3 | `auto_task_job.port_id` + `claim()` 端口限额 | 端口 1 并发时第二个作业排队 |
| 4 | MCP server v1（L0/L1 工具）+ 作业令牌 | 模型能读题、不能越权 |
| 5 | 审批分级 + 审计表 | L3 动作必须二次确认 |
| 6 | 批阅迁移到 agent + 双跑对比 | 差异率 < 阈值 |
| 7 | DSH 复用同一 MCP | 同一工具在 DSH 下可用 |

## 10. 风险

| 风险 | 缓解 |
| --- | --- |
| 用户端口打满全站资源 | 站点级总并发 + 每用户端口数上限 + 管理员禁用 |
| 恶意 base_url（SSRF） | HTTPS 强制、内网拒绝、禁止重定向、出口代理 |
| 提示词注入（题面里藏指令） | 工具返回标记为「不可信数据」；高危动作必须人工确认 |
| 模型自由度过高导致乱改 | 分级审批 + 审计 + 资源版本(乐观锁)已存在 |
| 端口密钥泄露 | Fernet 加密、永不回传、日志脱敏 |
