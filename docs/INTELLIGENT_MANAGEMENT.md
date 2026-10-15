# 智能管理（2026-09-13）

## 入口与交互

M 端 `/v2/manage/intelligent`，菜单名“智能管理”。原程序题命题入口与旧地址转向该模块。

- 首页沿用 M 端小尺寸 Card、表格、右上角“新建”、Modal 表单。
- 新会话选择程序题命题、比赛维护或批量录题预设，并填写补充说明。说明及步骤在创建时形成快照，后续会话可继续补充要求。
- 会话展示消息、流式回复、执行计划、操作参数、审批状态及结果。会话列表只返回当前管理员的记录。
- 每次 Agent OJ 读取或写入均产生待确认操作。用户先审阅，再在独立对话框中确认具体参数；也可拒绝。
- 确认绑定操作 ID 和参数摘要，只能消费一次。取消、断开、进程重启不能自动恢复审批或重放写请求。执行结果不明时须先读回核对。

## 身份与执行

使用真实 Codex CLI App Server 的 stdio 协议，支持 initialize、thread/start/resume、turn/start、消息事件和动态工具调用。首次用户消息启动进程；会话和事件持久化到现有 AiResource，kind 为 management_session，独立于题库资源。

只有白名单 `oj_request` 工具可以访问 OJ。服务端不将管理员 Cookie、内部服务 token 或身份头交给模型；用户确认时才临时使用该 HTTP 请求携带的当前登录 Cookie，经正常 Gateway 调用业务接口，由原 OJ 权限再次校验。Cookie 不写入会话或日志。每个 API 重新检查当前管理员角色和会话所有者；通用资源接口不能修改智能管理会话、审批或历史。

Agent 使用独立的 HOME/CODEX_HOME，禁用 shell、外网搜索、桌面 apps、子 agent 和宿主技能发现；线程环境设为空。不提供数据库直写、任意 URL、用户密码或文件系统工具。非支持的工具/权限请求会拒绝。

当前预设说明位于 `sduoj-autolab/auto_task/management_guides/`。接口白名单及字段说明位于 `auto_task/management_agent.py`。新增接口必须同时定义具体字段、权限与确认展示并扩充测试。

## 运行条件与边界

- 服务端需安装 Codex CLI；可设置 AUTOLAB_CODEX_BIN。已验证本机 0.154.0-alpha.6.2 的协议。
- 使用现有“模型与额度”页面的 Codex / Responses 提供者配置。当前本地尚无模型/API key；会话管理可以体验，真实模型对话需配置后使用。
- 已设置进程并发、每用户并发、输入及执行时间限制。智能管理目前不是原有 TaskJob/Worker 队列任务，不能把旧队列的 AiRun 账务与预算核算视作已经覆盖新会话；生产上线前需独立补齐该口径。
- App Server 进程由当前 Autolab 实例维护，当前实现按单实例运行。多实例需会话粘滞或独立执行服务；不应在生产多 worker 场景直接开放。
- 本轮未部署线上、未修改线上业务数据。真实模型与生产多用户负载未验收。

## M 端统一与 IDE 移除

查重、批阅、考务改用记录表格；新建统一入口与弹窗，详情保留在相应业务页。业务组件统一 AntD small 尺寸；MLayout 去掉造成页面横向错位的固定 1200px 最小宽度。

AIOperations 现在只展示任务列表和记录。教学 IDE 的页面、工作区管理、代码编辑/运行/指导和 C 端入口已经移除。历史 IDE 任务记录、底层沙箱及旧后端兼容代码保留，不影响既有记录读取和其他任务运行。

## 验证

- 持久会话/跨用户隔离、管理员校验、拒绝不执行、参数摘要防篡改、重复确认拦截、断开审批失效、比赛题号去重均有后端测试。
- `AUTOLAB_MANAGEMENT_PROTOCOL_TEST=1 python -m pytest tests/test_management_agent.py` 使用真实 Codex App Server 与本地模拟 Responses 服务验证“工具调用→等待确认→只执行一次→回传结果”，不会调用付费模型。
- 前端测试覆盖独立确认弹窗、拒绝、IDE 入口移除以及新建/表格业务回归。
- 浏览器创建测试会话 `DEV-智能管理体验-20260913`，刷新后可以继续。截图位于工作区 `output/playwright/intelligent-management.png`。
