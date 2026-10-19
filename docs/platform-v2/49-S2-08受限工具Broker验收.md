# S2-08 受限工具 Broker 验收

2026-10-19。AutoLab `61f3af4`，本批只补验证，产品Broker实现未改。沿第一阶段已批准的worker-owned business_tools合同；Java自动委托、通用HTTP/SQL/MCP和未安装工具继续unavailable。

## 已实现边界

每个SDK turn对应原父worker创建的独占loopback HTTP代理，随机bearer token只匹配该代理。audience由该端口与固定Responses/tools路径确定，job/attempt/lease/subject/action工具白名单/resource及组件依赖generation绑定在父侧不可由SDK替换的上下文；不是可任意携带声明的跨服务JWT。runner总期限、步数、原lease、取消及finally close共同限制其生命周期。每次模型/工具前后仍重查原当前权限和冻结绑定，收尾等待已准入事务排空。

SDK只请求父侧当前输入和提候选，不选择其他资源。原生鉴权与数据处理留在AutoLab；Java只使用原fresh身份HTTP合同，没有Java读写工具或直接数据库适配。当前不需要MCP服务，因此未启用MCP，也不宣称完成MCP握手/list/call/CallToolResult；将来确需此协议时须另验收，不能把普通JSON冒称MCP。

## 隔离验证

新增原typed任务+真实随机MySQL+原HTTP代理验证 **1 PASS**：合法读取固定teacher-doc；SDK注入owner、attempt、resource_id、userId以及其他组件/Java工具全部400；query中的伪资源选择仍只返回原受权来源。取消旧任务后旧代理403；显式新任务创建独立token，旧token向新代理401，新token合法读取。AiRun和candidate为0，源version仍1。

本例手工组合只读dispatcher，明确使用原authorize_job/_read；完整原proposal dispatcher与真实SDK回调另复用本批S2-07的 **2 PASS**：两个真实SDK阶段、六次合成Responses、工具观察值、原worker/MySQL用量及持久候选/人工采用链。身份和模型数据为隔离替身，不等同真实Java/提供商授权。

原代理/工作流 **36 PASS**，覆盖工具/请求上限、未知工具、hosted MCP/图像/外部上下文拒绝、取消/审核后撤权、缺失用量、写账失败、drain与关闭后请求拒绝；不会把未知用量变成成功或继续SDK重试。

当前浏览器确认合同沿[22](22-独立worker与真实浏览器dev验收.md)/[24](24-首批组件与真实模型浏览器dev验收.md)已通过证据，原result.json状态和哈希复核；这是历史真实浏览器/Gateway/Java/Linux组合，不冒称在当前SHA重新跑完整站点，也不再次调用真实模型。代码没有增加Java自动委托或Cookie持久化，剩余组件的工具适配归S2-10。

初次核对后发现浏览器候选入口仍信任旧角色，曾暂缓S2-08闭合；随后6edd990按7项反例修复，当前真实Gateway撤权/恢复与receipt重放均通过，见[50](50-S2-09持久候选与当前身份确认验收.md)。三类verification现已闭合，S2-08标done。日志/XML、源码hash、历史浏览器证据hash及限制见 `work/platform-v2-all-20261019/s2-08-evidence.json`。S2-09同批完成原AiResource持久候选/CAS/幂等与未知结果验证；不再重跑Broker已通过出口。
