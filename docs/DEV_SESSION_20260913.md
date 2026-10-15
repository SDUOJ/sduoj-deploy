# 2026-09-13 开发环境恢复与历史进展

## 历史进展

已查看项目历史任务「继续推进当前任务」（01a0722f-aa4f-78a3-805b-2e6f575919bc，后端与 AI 工作台）和「继续推进当前任务」（01a07229-625b-7242-a83d-3d08f8abb82c，前端审计修复），并与当前工作树及共享进度核对。

- AI 平台已合入 Autolab 的 FastAPI / MySQL / Redis 和持久 Worker，沿用 OJ 身份及权限。历史记录包含队列恢复、任务输入快照、账务、资源版本、身份与撤权、文件审计等实现。
- Web2 有 9 个 AI 工作台入口：任务/IDE、题库、命题、批阅、考务、课程资料、查重、实验验收、账户与管理；另有验收详情路由。后端契约记录为 91 条 AI 路径、13 张扩展表。页面存在不等于真实模型业务验收。
- 原生编程/主观/客观题导入发布、批阅候选采用、考务 TEST/FORMAL 门禁、课程问答引用、JPlag、实验验收媒体等均有实现与局部验证；真实模型、摄录硬件、完整多角色和生产迁移仍未验收。
- 前端历史修复包括 React 18 / AntD 5、表单契约、上传失败/取消、过期响应保护、WebSocket、移动管理、权限边界、依赖替换和 ARM 构建。最新前端文档记录 77 suites / 367 tests、45 个 mock Playwright 通过；这些是历史结果，本轮没有重跑全量。
- 大量新增功能仍为工作树改动，不能用 HEAD 代表实现。未提交、推送或修改生产。

## 本轮实际验证

- 原有 13 个 Docker 容器运行：主库/Redis/RabbitMQ/Nacos、Autolab MySQL/Redis、6 个 Java 服务及 judger。`./dev check` 验证 6 个 Java 服务健康、judger 已连接本地队列。
- 补启动 Web2 3000、Autolab 5005、独立 Worker，全部后台运行，日志在 `data/dev/runtime`。
- 本地数据库缺失表/列检查通过。前端和经 Gateway 的 Autolab OpenAPI HTTP 200。
- 使用既有本地测试账号，经真实 OJ 登录逐页检查 9 个 AI 工作台，标题与页面加载完成。
- 真实 Worker 首次运行暴露 Java RPC 的 Long ID 字符串与严格身份校验不匹配。仅在内部 RPC 适配处转换规范十进制 userId/groups，浏览器身份头校验保持严格。身份专项 38 passed。
- 真实 Gateway 入队 → Worker → Docker 沙箱：Python、C、C++、Java 均得到 exit_code=0、输出 5。Java 默认镜像本地缺失导致第一次超时，启动配置改用此前验证过的本地 Java 沙箱镜像后通过。保留诊断任务及成功任务，便于检查历史/重试。
- Python 成功任务：a7fb5b39d6a14439b0d6349edae62b23。其他任务及输出见 `data/dev/runtime/language-smoke.json`。
- 新增可重复启动工具 `scripts/dev_apps.py`，支持 up/down/status；启停与幂等 up 已实测。

## 访问与体验

当日晚间已按反馈整合进 C/M 原有页面并改为原生题组直接保存；以下 `ai-*` 表格保留为早期恢复验收记录，旧地址现作兼容跳转。最新结构与验证见 [共享进度顶部更新](AI_PLATFORM_PROGRESS.md)。测试批次为 `DEV-原生题组体验-20260913`（组 #201 / #202）。

当前浏览器入口：`http://127.0.0.1:3000/v2/manage/problemSet/problem_group`。原 OJ 首页：`http://127.0.0.1:3000/v2/home`。
登录凭证使用本地私有 `data/dev/ai-integration/test-user.json`，不在本文复制密码。

| 入口 | 可体验内容 | 本轮边界 |
| --- | --- | --- |
| ai-workbench | 任务详情/历史、教学 IDE 四语言运行 | 四语言真实消费通过；AI 指导需模型 |
| ai-bank | 检索、题集、编辑与原生题导入入口 | OCR、生成解答、验证需模型 |
| ai-authoring | 命题草案、复核、导出和发布入口 | 真实模型生成/发布全链未验收 |
| ai-grading | 主观题候选对照、编辑和采用入口 | 需答题卡数据；AI 批阅需模型 |
| ai-exams | 名单、考场、TEST/FORMAL、监控与导出入口 | 无完整真实考试验收 |
| ai-course | 资料、检索/索引、问答引用入口 | 问答需模型与资料 |
| ai-plagiarism | 原生快照、候选对、JPlag 与复核入口 | 本轮仅页面加载，AI 分析需模型 |
| ai-interviews | 邀请、会话、媒体、教师复核入口 | 真实媒体和模型交互未验收 |
| ai-admin | 模型、资格、预算、账务、队列与存储管理 | 当前 has_api_key=false |

尚未配置 provider/model/API key，真实模型功能不能作为已可用交付。可在账户与管理的模型页配置自己的开发提供者；本轮未调用付费模型。
旧 standalone exam 后端不在当前 Java checkout，无法启动；不影响原生 OJ 基础服务和 Autolab 题单考试模块。
首页保留 React key 等开发告警，本轮没有做全站 UI 修复。

启停说明见 ../DEV.md。关闭环境不会删除数据库卷。
