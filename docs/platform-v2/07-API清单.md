# 07 API 清单

> 全部新增与变更接口。约定：网关前缀 `/api`；Autolab 侧挂 `/api/ps/...`；包体 `{code, data, msg}`，成功 `code==0`。
>
> 图标：🆕 新增　✏️ 变更　⚠️ 需安全加固

## 1. 鉴权与身份

| 通道 | 凭证 | 适用 |
| --- | --- | --- |
| 前端 → 网关 | `SESSION` Cookie（`withCredentials`） | 所有管理端/学生端接口 |
| Autolab → Java | `sduoj-token` 内部 RPC | 现有，不变 |
| Agent → MCP → OJ | 作业令牌（绑定 `job_id + owner_id`） | 见 02 §5 |
| 监考端 → Autolab | 链接令牌 + 会话令牌 | 见 05 §4 |

**P0 安全修复**（先于所有新功能）：

| 项 | 现状 | 修复 |
| --- | --- | --- |
| ⚠️ 网关对等校验范围 | `main.py:31` 只匹配 `/auto-task`，`/management-agent` 未被覆盖 | 扩展为 `/auto-task`、`/management-agent`、`/invigilate` 的统一前缀判定 |
| ⚠️ `/ps/objective/info` | 只按 `pid` 查，**无归属校验**，可读答案 | 增加可见性判定（详见 03 §2.1） |
| ⚠️ `/ps/subjective/info` | 同构 | 同上 |
| ⚠️ 题组可引用他人私有题 | 无 `isPublic` 校验 | 入组校验 |

## 2. 01 · 云 Agent（Runner 内部控制面）

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| 🆕 `POST` | `/api/ps/internal/agent/nodes/register` | 内部令牌 | 节点注册 |
| 🆕 `POST` | `/api/ps/internal/agent/nodes/{id}/heartbeat` | 内部令牌 | 心跳 + `in_flight` |
| 🆕 `POST` | `/api/ps/internal/agent/jobs/claim` | 内部令牌 | 领取作业（含端口额度） |
| 🆕 `POST` | `/api/ps/internal/agent/jobs/{id}/complete` | 内部令牌 | 完成 |
| 🆕 `POST` | `/api/ps/internal/agent/jobs/{id}/fail` | 内部令牌 | 失败 |
| 🆕 `GET` | `/api/ps/internal/agent/versions` | 内部令牌 | 版本清单（`versions.yaml` 渲染） |

> 内部控制面**不对公网暴露**，仅 Runner 网络可达。

## 3. 02 · AI 端口

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| 🆕 `GET` | `/api/ps/auto-task/ai/ports` | USER | 我的端口（不含密钥） |
| 🆕 `POST` | `/api/ps/auto-task/ai/ports/create` | USER | 新建 |
| 🆕 `POST` | `/api/ps/auto-task/ai/ports/{id}/update` | 属主 | 更新 |
| 🆕 `POST` | `/api/ps/auto-task/ai/ports/{id}/delete` | 属主 | 软删 |
| 🆕 `POST` | `/api/ps/auto-task/ai/ports/{id}/default` | 属主 | 设为唯一默认 |
| 🆕 `POST` | `/api/ps/auto-task/ai/ports/{id}/test` | 属主 | 连通性探测（不回响应体） |
| 🆕 `GET` | `/api/ps/auto-task/ai/ports/{id}/usage` | 属主 | 近 30 天用量 |
| 🆕 `GET` | `/api/ps/auto-task/ai/admin/ports` | ADMIN | 全站总览 |
| 🆕 `POST` | `/api/ps/auto-task/ai/admin/ports/{id}/disable` | ADMIN | 禁用 |
| ✏️ `GET` | `/api/ps/auto-task/ai/jobs/{task_id}` | 属主 | 增加 `queue_position`、`port`、`harness`、`blocked_reason` |
| ✏️ `GET` | `/api/ps/auto-task/ai/admin/queue` | ADMIN | 增加按端口聚合 |

**端口请求体**见 02 §3.1；校验规则见 02 §3.2。

## 4. 02 · MCP 工具（不是 REST，列在此处便于对照）

| 工具 | 风险级 | 说明 |
| --- | --- | --- |
| `oj.user.profile` | L0 | 读当前身份与权限 |
| `oj.problem.search` / `oj.problem.get` | L0 | 检索/读题 |
| `oj.exam.list` / `oj.exam.get` | L0 | 读考试 |
| `oj.submission.list` | L0 | 读提交（按权限裁剪） |
| `oj.problem.upload_testcase` | L1 | 上传单个测试点 |
| `oj.problem.set_checkpoints` | L1 | 设置测试点分值 |
| `oj.problem.create` / `oj.problem.update_description` | L2 | 建题/写题面 |
| `oj.group.add_members` | L2 | 加组员 |
| `oj.exam.prepare` / `oj.exam.publish` | L3 | 组卷/发布（二次确认） |
| `oj.seat.assign` | L3 | 座位写回 |
| `oj.plagiarism.scan` | L3 | 发起查重 |

## 5. 03 · 出题平台

### 5.1 统一题目

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| 🆕 `GET` | `/api/problem/unified/list` | USER | `source=public\|group\|mine\|all`、`kind`、`tag`、`keyword`、分页 |
| 🆕 `GET` | `/api/problem/unified/{uid}` | 按可见性 | 统一详情 |
| 🆕 `POST` | `/api/problem/unified/{uid}/visibility` | 属主/超管 | 改可见性 |
| 🆕 `POST` | `/api/problem/unified/{uid}/report` | USER | 举报（可选） |

### 5.2 出题工作台

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| 🆕 `POST` | `/api/ps/auto-task/ai/authoring/packages` | 新建出题包 |
| 🆕 `GET` | `/api/ps/auto-task/ai/authoring/packages` | 我的出题包 |
| 🆕 `GET` | `/api/ps/auto-task/ai/authoring/packages/{id}` | 详情 |
| 🆕 `POST` | `/api/ps/auto-task/ai/authoring/packages/{id}/stage` | 推进/回退 |
| 🆕 `POST` | `/api/ps/auto-task/ai/authoring/packages/{id}/generate` | `kind=statement\|programs\|data` |
| 🆕 `POST` | `/api/ps/auto-task/ai/authoring/packages/{id}/audit` | 七项终检 |
| 🆕 `GET` | `/api/ps/auto-task/ai/authoring/packages/{id}/audit` | 终检报告 |
| 🆕 `POST` | `/api/ps/auto-task/ai/authoring/packages/{id}/publish` | 发布（高危） |
| 🆕 `POST` | `/api/ps/auto-task/ai/authoring/packages/{id}/trials` | 生成实测链接 |
| 🆕 `POST` | `/api/ps/auto-task/ai/trials/{token}/submit` | 实测提交（令牌） |
| 🆕 `POST` | `/api/ps/auto-task/ai/trials/{token}/feedback` | 实测意见（令牌） |

### 5.3 文档解析与翻译

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| ✅ `POST` | `/api/ps/auto-task/ai/files/upload` | 已存在（≤50MiB，白名单后缀） |
| ✅ `POST` | `/api/ps/auto-task/ai/documents/{id}/parse` | 解析为块与题目（扩展） |
| 🆕 `GET` | `/api/ps/auto-task/ai/documents/{id}/blocks` | 块列表（页码/坐标） |
| 🆕 `POST` | `/api/ps/auto-task/ai/documents/{id}/translate` | 翻译 |
| 🆕 `POST` | `/api/ps/auto-task/ai/documents/{id}/import` | 导入出题包/题组 |

## 6. 04 · 查重

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| 🆕 `POST` | `/api/ps/auto-task/ai/plagiarism/scans` | 题单/比赛管理 | 建扫描 |
| 🆕 `GET` | `/api/ps/auto-task/ai/plagiarism/scans` | 同上 | 历史扫描 |
| 🆕 `GET` | `/api/ps/auto-task/ai/plagiarism/scans/{id}` | 同上 | 详情+进度 |
| 🆕 `POST` | `/api/ps/auto-task/ai/plagiarism/scans/{id}/cancel` | 同上 | 取消 |
| 🆕 `POST` | `/api/ps/auto-task/ai/plagiarism/scans/{id}/threshold` | 同上 | 后期调阈值重筛 |
| 🆕 `POST` | `/api/ps/auto-task/ai/plagiarism/scans/{id}/rescan` | 同上 | 新快照重扫 |
| 🆕 `GET` | `/api/ps/auto-task/ai/plagiarism/scans/{id}/pairs` | 同上 | 配对列表 |
| 🆕 `GET` | `/api/ps/auto-task/ai/plagiarism/scans/{id}/pairs/{pairId}` | 同上 | 单对详情 |
| ✅ `POST` | `/api/ps/auto-task/ai/plagiarism/{rid}/pairs/review` | 同上 | 已存在，语义沿用 |
| ✅ `POST` | `/api/ps/auto-task/ai/plagiarism/{rid}/writeback` | 同上 | 已存在 |
| ✅ `GET` | `/api/ps/auto-task/ai/plagiarism/{rid}/report` | 同上 | 已存在 |
| 🆕 `GET` | `/api/ps/auto-task/ai/plagiarism/scans/{id}/export` | 同上 | CSV/Excel |
| 🆕 `POST` | `/api/ps/auto-task/ai/plagiarism/bindings` | 同上 | 绑定 |
| 🆕 `DELETE` | `/api/ps/auto-task/ai/plagiarism/bindings/{id}` | 同上 | 解绑 |
| 🆕 `GET` | `/api/ps/plagiarism/self/{kind}/{refId}` | USER | **学生自查** |

**学生自查返回**：

```json
{"bound": true, "scan_title": "...", "show_similarity": true,
 "items": [{"problem_uid":"prog:123","problem_title":"...","similarity":0.92,
            "decision":"CONFIRMED","counterpart_display":"匿名 A",
            "matches":[{"left_lines":[12,18],"right_lines":[45,52]}],
            "my_code":"...","other_code":"..."}]}
```

未绑定时返回 `{"bound": false, "items": []}`，前端显示为空。

## 7. 05 · 考务

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| 🆕 `POST` | `/api/ps/auto-task/ai/exams/{id}/accounts/generate` | 管理组 | 生成账号（幂等） |
| 🆕 `GET` | `/api/ps/auto-task/ai/exams/{id}/accounts` | 管理组 | 列表（脱敏） |
| 🆕 `GET` | `/api/ps/auto-task/ai/exams/{id}/accounts/export` | 管理组 | 导出（审计） |
| 🆕 `POST` | `/api/ps/auto-task/ai/exams/{id}/accounts/import` | 管理组 | 导入 OJ |
| 🆕 `POST` | `/api/ps/auto-task/ai/exams/{id}/materials/render` | 管理组 | 生成材料 |
| 🆕 `GET` | `/api/ps/auto-task/ai/exams/{id}/materials/{kind}` | 管理组 | 下载 |
| 🆕 `POST` | `/api/ps/auto-task/ai/exams/{id}/invigilator-links` | 管理组 | 生成链接 |
| 🆕 `GET` | `/api/ps/auto-task/ai/exams/{id}/invigilator-links` | 管理组 | 链接列表 |
| 🆕 `POST` | `/api/ps/auto-task/ai/exams/{id}/invigilator-links/{lid}/revoke` | 管理组 | 吊销 |
| 🆕 `GET` | `/api/ps/auto-task/ai/exams/{id}/rooms/{room}/status` | 管理组 | 考场实时状态（含在线） |
| 🆕 `GET` | `/api/ps/invigilate/links/{token}` | 令牌 | 校验链接 |
| 🆕 `POST` | `/api/ps/invigilate/links/{token}/join` | 令牌 | `{name}` → 会话 |
| 🆕 `GET` | `/api/ps/invigilate/sessions/{sid}/rooms/{room}/status` | 会话 | 实时状态 |
| 🆕 `POST` | `/api/ps/invigilate/sessions/{sid}/actions` | 会话 | 记录动作 |

**监考端状态返回**：

```json
{"rows":[{"seat":3,"name":"张三","username":"ytm27abc...","online":true,
          "submission":"SUBMITTED","last_active_at":"2026-10-18T14:05:12+08:00",
          "actions":[{"action":"present","at":"..."}]}],
 "summary":{"total":216,"online":213,"submitted":180,"exceptions":2}}
```

## 8. Java 侧需要的新增/改造

| 项 | 类型 | 说明 |
| --- | --- | --- |
| 🆕 `GET /api/problem/unified/list` | 新 | 三题型统一检索，权限在服务层判定 |
| ✏️ `GET /api/manage/user/getOnlineSessions` | 改 | 增加批量 `usernames` 参数（供监考端一次查询 216 人） |
| 🆕 `GET /api/internal/user/onlineSessions` | 新 | 内部 RPC 批量版，供 Autolab 调用 |
| ✏️ `ProblemManageDTO` | 改 | 增加 `difficulty`、`visibility`（若采纳统一模型） |
| ⚠️ `ProblemInternalController.listJudgerCheckpoints` | 加固 | 现无 `@Auth`，依赖网络边界 |
| ✏️ `ProblemCommonService` | 改 | `managerGroups` 变更后**显式清除** Redis 缓存（现未找到清理点） |

## 9. 错误码约定

| 码 | 含义 | 场景 |
| --- | --- | --- |
| `400` | 参数非法 | 校验失败 |
| `401` | 未登录 | 会话失效 |
| `403` | 无权限 | 越权、令牌无效 |
| `404` | 不存在 | — |
| `409` | 冲突 | 版本冲突、已有默认端口、重复绑定 |
| `413` | 过大 | 文件/批量超限 |
| `429` | 限额 | 端口并发满、队列满 |
| `502` | 上游失败 | 模型/评测服务异常 |
| `503` | 未配置 | 未配置 AI 端口（**必须给出引导，不回退内置模型**） |
