# 07 API 清单与合同

> 这是 v2 路径唯一清单，除标“已有”外均为待实现/批准的合同，不表示现有路由已经存在。保持原 GET/POST 约束，不新增 DELETE/PATCH/PUT。数据库见 [06](06-数据库变更汇总.md)，审批见 [09](09-审计与实施门禁.md)。

## 1. 前缀、包体和通用规则

- 下表 `A` = `/api/ps/auto-task/ai`，`I` = `/api/ps/invigilate`，`T` = `/api/ps/trial`。Autolab 注册时去掉网关 `/api/ps`，不能重复拼前缀。
- Runner 的 `C=/internal/agent` 只在私有控制监听入口，不注册为公共 `/api/ps/internal/*`。Java `/internal/*` 沿原 RPC 认证与服务间路由，公共 Gateway 必须拒绝。
- 主体 ID 和 Java Long 用十进制字符串；提交 hex ID 保留。路径参数 encodeURIComponent，uid 不当作 problemCode。
- 新写请求有 operation_key 与 expected_version（创建无既有版本时只需 key）；批量操作固定清单 hash。幂等结果原样返回，输入变化 409；外部结果不确定返回操作句柄和 unknown，不静默重发。
- 最新一期是 [10](10-OpenHands与Agent组件.md) 的 AutoLab/OpenHands/组件路线。AI 配置、能力发现和任务 API 均由 AutoLab 实现；Java 优先复用既有接口，缺合同的动作先不可用，不为 AI 另建 Java 平台。
- 列表有界分页/cursor、稳定排序；files/rows/events/code 均有字节与数量上限。带版本的轮询响应标明 updated_at/last_observed_at，不能凭客户端时钟判业务已完成。

```json
{"code":0,"message":"","data":{"id":"123","version":1},"timestamp":0}
```

主字段 message；旧 msg 由 request.ts 兼容读取，不复制成新标准。HTTP 状态与业务错误都要测试。MCP 与此 REST 包体不同，见 §5。

## 2. 身份与公共入口

| 通道 | 要求 |
| --- | --- |
| 用户管理/学生业务 | 原 SESSION + Gateway 可信身份 + 服务端角色/对象检查 |
| 敏感 Agent 写操作 | 保留当前浏览器确认，或经 AUTH 批准的受限委托；owner_id 不能冒充会话 |
| MCP | audience/job/execution/lease/scope/有效期/撤销检查；不得透传内部 RPC token |
| 监考/实测 | 独立能力 Cookie + CSRF/Origin + 当前 link/资源/有效期，sid 不是凭证 |
| Runner | 私有 listener + 节点认证 + TaskJob lease fencing，用户 Cookie 不适用 |

新匿名例外仅限以下精确方法/路径，仍受 Gateway 到 Autolab 的 peer 边界保护，新增前缀也须纳入：

| 入口 | 对象边界 |
| --- | --- |
| GET A/library/problems；GET A/library/problems/{uid} | 仅公开 learner 投影，禁止 anonymous source=mine/group/all、view=author |
| POST T/links/{id}/join；GET T/session；POST T/submit；POST T/feedback | 邀请交换后限定同一 package/manifest/attempt 上限 |
| POST I/links/{id}/preview；POST I/links/{id}/join；GET I/session；GET I/rooms/{room}/status；POST I/actions | 当前 link/session 与明确 exam/room scope |

以上是**待批准白名单**，不是直接豁免建议；未放行前入口关闭。无效能力会话不触发普通 OJ 登录重定向，也不改变同浏览器的 OJ SESSION。

原 `/objective/info/edit`、`/subjective/info/edit` 的安全修复需校验 gid/type/pid 关系，不能删掉已有 group_manager。management-agent/question-bank peer 保护和 Internal RPC 拦截器已有实现，任务是核对基线/配置和补回归，不重写原权限角色。

## 3. 用户端口和作业

| 方法 | 路径 | 权限 / 结果 |
| --- | --- | --- |
| GET | A/ports | 本人列表，has_key/fingerprint，无 key/cipher |
| POST | A/ports/create | 本人；创建但不隐式设默认 |
| POST | A/ports/{id}/update | 属主 + version；endpoint 改变需新 key |
| POST | A/ports/{id}/delete | 属主；运行中拒绝删除，默认标记原子清除 |
| POST | A/ports/{id}/default | 属主；稳定账户行锁 + 唯一约束 |
| GET | A/ports/{id}/test | dev 已接的本地报价，不访问模型；返回版本/价格及请求/token/费用上限，见 [26](26-受控端点探测后端dev验收.md) |
| POST | A/ports/{id}/test | 属主 + 限频；显式报价确认和原 worker 任务，dev 前端及有界真实供应商验收见 [27](27-端点探测前端与真实供应商dev验收.md) |
| GET | A/ports/{id}/test/latest | 本人最近固定探测或 null；只读历史，含冻结 port_version，停用端点仍可查，见 27 |
| GET | A/ports/{id}/test/{taskId} | dev 已接本人脱敏状态和有限观察结果，不能作为其他组件自动授权 |
| GET | A/ports/{id}/models | dev 本人本地范围：版本/1 次目录 GET/0 推理/30 秒/256KiB，不解密或访问提供商，见 [30](30-models任务与前端dev验收.md) |
| POST | A/ports/{id}/models | 同上；version/confirmed/operation_key，独立 port.models 原 worker 任务；与 test 共用限频，不自动重试 |
| GET | A/ports/{id}/models/latest | 本人最近目录任务或 null，停用/暂停后历史仍可读；不改变 Responses 能力观察 |
| GET | A/ports/{id}/models/{taskId} | 本人固定生命周期、冻结版本、UTC 时间及目录数量/观察/延迟；没有模型 ID/原始 provider 内容 |
| GET | A/ports/{id}/usage | 属主；结算/预留/未知用量和 UTC 周期；dev 已接，offset 分页/固定 20 条，见 [25](25-本人端点用量dev验收.md)；更广的聚合运营信息仍未实现 |
| GET | A/admin/ports | dev 已接原 superadmin；20 条分页、offset/owner_id/status 过滤；仅脱敏元数据，见 [28](28-端点运营与停用dev验收.md) |
| POST | A/admin/ports/{id}/disable | dev 已接同上；version/operation_key/reason，停用清默认、在途结算，保留属主原显式启用，见 28 |
| GET | A/capabilities | 已有，扩展 v2 的 policy_version、catalog_revision、组件/action 投影；保留原 admin/sandbox_enabled/task_types/resource_kinds 字段，按当前主体/作用域裁剪，不访问 provider |
| GET | A/components | 新增；原 SUPERADMIN/明确平台运营授权，读静态已安装目录、实际开关、版本与依赖，不回传用户密钥 |
| POST | A/components/{componentId}/update | 同上；policy_version CAS + operation_key/reason；只能更新已登记组件/action，不能安装代码/任意工具 |
| POST | A/components/policy/update | 同上；总开关 CAS 与同一原审计链，关闭不影响治理/历史/取消/对账 |
| POST | A/agent/runs/create | 登录主体 + 原资源权限；component_id/version、action、resource_id/version、port_id（可省略用本人默认）、operation_key、受 schema 限制的 input；新建原 TaskJob(agent.run)，返回 taskId/session_id |
| GET | A/agent/candidates/{action_id} | 新增；原源资源读取权限，读已成功 fenced 登记的候选/版本/receipt，不提供执行凭据 |
| POST | A/agent/candidates/{action_id}/decide | 新增适配；当前本人浏览器会话 + 原源写权限，expected_version/action_hash/decision/operation_key，检查冻结的三元 generation、有效期，以 CAS 执行一次；不要求原 TaskJob 仍 running，不接收 Cookie/owner 作为 payload |
| GET | A/jobs/{task_id} | 已有，扩展 port、release、queued_reason、blocked_reason、attempt |
| GET | A/jobs/{task_id}/events | 已有，保留授权/游标，扩展关联 execution/sequence |
| POST | A/jobs/{task_id}/cancel | 已有，取消新调用；在途写结果可能 unknown |
| POST | A/jobs/{task_id}/retry | 已有，按原规则；unknown 写不得通用重试 |
| GET | A/admin/queue | 扩展端口聚合，不能回传其它用户 key 或正文 |

API key 只出现在受控 HTTPS 写入请求，不能放 URL/审计参数/错误回显。显式端口失败不回退默认；没有默认返回 503。并发满返回已创建任务 pending，不当成 429。

agent.run 的接口 202/任务句柄不表示执行成功。创建、旧 API 映射/串联/批量/重试、claim、每次模型/工具准入和最终写入均重新检查同一组件/action；任务、候选固定 global/component/action 三元 generation；关闭再开启也不能复活。客户端提交的 policy_version 仅用于诊断，不能作为权限。disabled 用 409 component_disabled、实现/依赖不可用（含 sandbox_tools 的原 AUTOLAB_SANDBOX_ENABLED 部署许可关闭）用 503 component_unavailable；源权限不足仍 403。错误不回传私有配置。

GET capabilities 的 scope 可指定 course/ps/resource，但必须先验证当前主体能访问该 scope。缺上下文用 requires_context，未配端点用 port_not_configured，引导配置；组件/总开关关闭时不运行模型。历史和取消继续沿原权限读取，不因业务开关关闭形成无法清理的任务。

普通文档 dev 适配的 capabilities 可启动提示已接当前来源的原管理/write ACL、普通文本合同与本人可选端点，见 [22](22-独立worker与真实浏览器dev验收.md)。至少一个 active、has_key、明确价格的本人端点只表示可以显式选择；没有默认时仍不能以默认选项新建，接口不自动改用其他端点。提示不探测供应商、不代表预算已经预留，typed admission 继续独立复验。

### 3.1 原生主观批阅：dev 已接合同

以下只属于已批准的纯文本批阅适配，见 [33](33-主观批阅历史与前端合同dev验收.md)、[34](34-主观批阅工作台dev验收.md)。组件仍未 installed，不能据接口存在推断可创建或采用。来源读取/历史与新模型准入分开；所有原生材料读取均校验当前题单教师及父子关联，任务/资源还须属于本人。

| 方法 | 路径 | 权限 / 结果 |
| --- | --- | --- |
| POST | A/native/grading/preview | 原生 psid/gid/pid/username + grade 或 feedback；当前题目、答卷、rubric、source_hash、has_manual_grade，不调用模型 |
| POST | A/native/grading/create | 当前教师、来源 hash、本人端点、组件/action/依赖；operation_key 精确重放返回原 taskId/resource_id，不自动重新入队 |
| POST | A/resources/list | kind=grading，pageNow=页码，pageSize=20；原当前教师读取，旧记录只读；争用整页 409，不返回半页 |
| GET | A/resources/{resource_id} | 原 grading 来源快照或旧历史；持有旧快照不授予撤权后的读取权限 |
| GET | A/native/grading/resources/{resource_id}/tasks?page=1 | 当前来源及本人历史；每页 20，按 created_at/id 稳定排序 |
| GET | A/native/grading/tasks/{task_id} | 仅固定 component/action、状态、attempt、UTC 时间、has_error 和成功候选引用，无 payload/原日志/provider 错误 |
| GET | A/native/grading/candidates/{candidate_id} | 当前教师、本人的来源/任务/attempt/hash/version 绑定；历史读取不代表允许采用 |
| POST | A/native/grading/candidates/{candidate_id}/adopt | 当前教师独立确认，version/candidate_hash/operation_key/reason/严格布尔 overwrite_manual；CAS 回执重放；feedback 只改评语 |
| POST | A/jobs/{task_id}/cancel | 原任务取消；调用后重读，完成与取消争用不能自动创建替代任务 |

原教师列表 `getJudgeList`的原 `gid/pid` 继续表示显示位置；dev 新增 `rows[].native_ref={psid,gid,pid,username}`，其中 gid/pid 为原生主键。辅助批阅只使用严格解析且匹配当前题单/学生的 native_ref，缺失或非法时隐藏行内按钮；原手工批阅继续用旧位置，不改接口含义。

沿用原生整数主键合同，前端拒绝不安全 JS 整数、学生显示位置和未知字段，不为此改 Java Long API。取消和未知结果的重试不是通用任务重跑。纯文本无法表示的附件/OCR/视觉材料显式拒绝；真实空白答卷保留，不能用空文本替代解析失败。来源 hash 也包含当前手工成绩状态。

## 4. Runner 私有控制面

**延期评审对象，不是一期要实现的 API。** 一期原 Task worker 直接调起 OpenHands SDK，不新建节点注册/claim 控制平面。若以后确有多节点执行服务需求，下表仅作待重新审查的历史合同；不得随本轮组件能力自动开放。

| 方法 | 私有路径 | 验收 |
| --- | --- | --- |
| POST | C/nodes/register | 节点预登记身份，endpoint 不能指向任意内网 URL |
| POST | C/nodes/{id}/heartbeat | 同节点，容量为已批准配置，不信任任意 in_flight |
| POST | C/jobs/claim | 原权威锁/队列分配，不能由 caller 指定他人 owner/端口 |
| POST | C/jobs/{id}/heartbeat | 当前 execution/attempt/lease |
| POST | C/jobs/{id}/complete | fencing + 输入/产物 hash + 幂等完成 |
| POST | C/jobs/{id}/fail | fencing + 错误分类 + 用量结算/未知状态 |
| GET | C/releases | 已批准版本/digest/能力，无密钥 |

控制面认证凭证轮换、日志脱敏和网络白名单需 SECRETS/AUTH 批准，不能用“路径里有 internal”代替验证。

## 5. MCP 工具合同

协议握手、tools/list、tools/call 与 CallToolResult 按 [MCP tools 规范快照](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)。业务结构放 structuredContent，错误 isError=true；JSON-RPC 错误仅用于协议/未知方法等。自动工具授权未完成前，保留当前人工确认 Broker。

| 工具 | 风险 | 约束 |
| --- | --- | --- |
| oj.user.profile | L0 | 本人最小权限视图 |
| oj.problem.search/get | L0 | source ACL + learner/author 投影，include_tests 不能提升权限 |
| oj.exam.list/get、oj.submission.list | L0 敏感读 | 先授权场次/题项，代码/个人信息裁剪 |
| oj.problem.create/update_description/upload_testcase/set_checkpoints | L2 | 源编辑权限、逐次确认、版本/清单/幂等 |
| oj.group.add_members | L3 | 会改变可见范围，审核人员和目标组 |
| oj.exam.prepare/publish、oj.seat.assign | L3 | 原 TEST/FORMAL、hash/版本与二次确认 |
| oj.plagiarism.scan | L2 | 固定范围/预算，只扫描，不隐含写回或发布 |
| oj.plagiarism.writeback | L3 | 复查齐备、目标版本和 receipt；contest 写成绩不在 v1 |

任何工具都不接受任意 method/path/SQL/文件路径。readOnlyHint、description 与模型提示不是授权证据。以已批准工具注册表为唯一 schema，02 的风险级别与此相同。

## 6. 题库、出题和实测

统一索引由 Autolab 聚合，Java 原数据仍走原服务；不再同时提议 Java 新 /api/problem/unified 与 Autolab 新同功能接口。

| 方法 | 路径 | 权限 / 行为 |
| --- | --- | --- |
| GET | A/library/problems | source=public/group/mine/all，kind、tags、difficulty、keyword；all 仅超管 |
| GET | A/library/problems/{uid} | learner/author 投影逐字段校验，陈旧索引回源 |
| POST | A/library/problems/{uid}/visibility | 属主/原有可改 ACL 者，不改变角色语义；多组、版本与影响清单 |
| POST | A/authoring/packages | 创建绑定原 AiResource 的阶段壳，固定类型 |
| GET | A/authoring/packages | 本人/获授权协作包，有界分页 |
| GET | A/authoring/packages/{id} | 当前版本及阶段产物/失效检查 |
| POST | A/authoring/packages/{id}/stage | 服务端准入，不允许跳过终检/实测 |
| POST | A/authoring/packages/{id}/generate | kind=statement/programs/data；AI 和确定性路径区分 |
| POST | A/authoring/packages/{id}/audit | 对固定 manifest 运行七项检查，返回任务句柄 |
| GET | A/authoring/packages/{id}/audit | 按版本读结果，不显示旧版本绿勾 |
| POST | A/authoring/packages/{id}/publish | 人工确认、manifest/version、原 native-plan/finalize、partial/unknown 对账 |
| POST | A/authoring/packages/{id}/trials | 生成限定版本邀请；v1 每人一邀请、一次兑换，多人生成多份；secret 只显示一次 |
| GET | A/authoring/packages/{id}/trials | 原包管理者；邀请元数据/状态及受权结果投影，不返回 secret/hash/会话凭据 |
| POST | A/authoring/packages/{id}/trials/{trialId}/revoke | 原包管理者，校验 package/trial 关联、邀请自身 expected_version（非 package_version）、operation_key；重复撤销幂等，立即拒绝该邀请已兑换会话 |
| POST | T/links/{id}/join | secret 在 body，交换受限会话，不能获取完整 author 详情 |
| GET | T/session | 当前试做快照、次数与状态，无隐藏答案 |
| POST | T/submit | 限次隔离执行/作答，记录完整 attempt，不写正式成绩 |
| POST | T/feedback | 当前 invitation，意见与结果版本关联 |

| 方法 | 文档路径 | 状态 |
| --- | --- | --- |
| POST | A/files/upload | 已有；复用属主/大小/类型校验 |
| POST | A/documents/{id}/parse | 新增包装现有解析任务，不宣称此 REST 已存在 |
| GET | A/documents/{id}/blocks | 新增，源文件/页/bbox/版本 |
| POST | A/documents/{id}/translate | 新增，所选端口、费用确认，保留原文 |
| POST | A/documents/{id}/import | 新增，人工修订版本显式导入草稿 |

## 7. 查重

| 方法 | 路径 | 行为 |
| --- | --- | --- |
| POST | A/plagiarism/scans | 源场次管理权限，固定 scope、selection、languages、capture_metric/floor、review_metric/threshold、预算；当前 MAX 复查用 AVG floor=0 |
| GET | A/plagiarism/scans | 授权历史，不把 operation_key 当历史查询 |
| GET | A/plagiarism/scans/{id} | 进度/完整性/失败分片/版本 |
| POST | A/plagiarism/scans/{id}/cancel | 当前权威任务取消 |
| POST | A/plagiarism/scans/{id}/threshold | expected_version；指标不暗改，阈值十进制字符串最多四位；超出指标覆盖/低于同指标 floor 返回 requires_rescan |
| POST | A/plagiarism/scans/{id}/rescan | 新 operation_key/new snapshot，不覆盖旧 scan |
| GET | A/plagiarism/scans/{id}/pairs | 分片/语言/阈值/decision 分页 |
| GET | A/plagiarism/scans/{id}/pairs/{pairId} | 关联校验及双方代码，仅授权管理者 |
| POST | A/plagiarism/scans/{id}/pairs/{pairId}/review | CAS+追加决策日志，绑定原 resource 复查语义 |
| POST | A/plagiarism/scans/{id}/writeback | 复用原原生题单写回门禁；未知结果先对账 |
| GET | A/plagiarism/scans/{id}/export | revision+filter 固定，CSV/Excel 防注入 |
| POST | A/plagiarism/bindings | 冻结发布，默认 visible=false/show_code=false |
| POST | A/plagiarism/bindings/{id}/unbind | 失效新读取，保留旧发布审计/manifest |
| GET | /api/ps/plagiarism/self/{kind}/{refId} | 本人+场次资格+已发布 revision，默认无 other_code/对方身份 |

原 A/plagiarism/{resource_id}/pairs/review、writeback、report 已存在。新 scan 包装必须保存 resource_id 映射并调用原规则，不能让 scanId 冒充 resourceId。自查返回格式以 04 为准；无绑定 bound=false，不完整扫描禁止以“无异常”发布。

相似度响应标明 metric，原始值以字符串返回；最终筛选/总数/分页/导出/发布均按原始 Decimal 比较，不按九位展示值比较。非零 AVG 采集结果不能仅因 MAX 阈值更高而认作完整，需重扫或明确 legacy 不完整状态。

## 8. 考务与监考

| 方法 | 路径 | 权限 / 行为 |
| --- | --- | --- |
| POST | A/exams/{id}/accounts/generate | 考试管理者，冻结名单、幂等生成、不得重新随机 |
| GET | A/exams/{id}/accounts | 同上，密码/密文都不回传 |
| GET | A/exams/{id}/accounts/export | 额外保密材料权限/确认、审计、私有下载 |
| POST | A/exams/{id}/accounts/import | 幂等编排、不覆盖原账号，unknown 先核查 |
| POST | A/exams/{id}/materials/render | 台账/seat/roster revision 一致，反向校验全批 |
| GET | A/exams/{id}/materials/{kind} | 授权短期下载、no-store，监考会话不可用 |
| POST | A/exams/{id}/invigilator-links | 明确 room/actions/expiry/uses，仅一次返回 secret |
| GET | A/exams/{id}/invigilator-links | 元数据/撤销状态，不返回 secret |
| POST | A/exams/{id}/invigilator-links/{linkId}/revoke | 当前资源/版本，子会话立即失效 |
| GET | A/exams/{id}/rooms/{room}/status | 管理者，最小化聚合；unknown/stale 与断网区分 |
| POST | I/links/{id}/preview | body secret，有效才返回最小考试/考场信息，不消耗次数 |
| POST | I/links/{id}/join | 原子兑换受限 Cookie + CSRF token |
| GET | I/session | 验证独立会话，返回作用域及过期时间 |
| GET | I/rooms/{room}/status | Cookie+当前 link+room 范围，不靠 sid/path 授权 |
| POST | I/actions | request_id/version/CSRF/Origin，补时只是 extension_request |

Java 保留原 SUPERADMIN getOnlineSessions。若新增内部考试在线聚合，只返回经 Autolab 认证的场次名单所需布尔/采样时间，不提供任意 usernames 的广域代理；认证合同另经 AUTH 批准。占位邮箱、是否覆盖已有账号及导入原子性不能只凭 DTO 注解断言。

## 9. 错误与负向合同

| HTTP/业务码 | 子码示例 | 语义 |
| --- | --- | --- |
| 400 / 422 | invalid_parameters、unsupported_kind | 保留原校验错误兼容，拒绝多余字段/非法 ID |
| 401 | session_expired、capability_expired | 普通会话与能力会话分别引导，不交叉登录 |
| 402 | account_admission_denied | 保留原账户计费准入，不新改角色 |
| 403 / 必要时404 | permission_denied、scope_mismatch | 防止私有对象枚举，响应策略按源业务冻结 |
| 409 | version_conflict、operation_changed、requires_rescan、outcome_unknown | 不自动覆盖或重放 |
| 413 | payload_too_large | 文件/代码/展开/批量上限 |
| 429 | queue_full、rate_limited | 创建拒绝或请求限频；并发排队不是此码 |
| 502 | upstream_failed | 脱敏，不暴露响应体/栈/凭据 |
| 503 | port_not_configured、service_unavailable | 未配置与暂时不可用分别引导，不隐式回退 |

每条写接口至少覆盖：未登录、本人/异人、合法父对象+非法子对象、撤权、stale version、重复 key、参数变化、超时后结果未知。内部入口测伪造节点/过期 lease；能力入口测无 Cookie、sid 猜测、跨房间和跨 package。07 中未列的通用任意 HTTP/SQL 工具不进入 v1。
