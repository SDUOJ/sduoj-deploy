# S3-01 原 worker 生命周期与强杀回收验收

2026-10-19，AutoLab `a0945c0db854602421e1b422c8907edc26edb447`。原TaskJob/AiResource/lease/心跳和额度账本仍是唯一持久权威；不建草案node/session/execution表，不增加独立队列。

## 本次真实缺陷与修复

核对发现原run_process的finally只能在父worker存活时回收SDK。新增反例在真实SDK等待本地合成模型响应时SIGKILL父进程，SDK在2秒观察窗仍存活，1 FAIL。随后父run_agent通过私有白名单环境传入自身PID和有限期限；子main在SDK import前启动watchdog，父消失或期限到达时SIGKILL本轮独立进程组。当前Linux worker本身是容器PID1，允许该有效父PID，不能错误要求父PID大于1。任务、账务、鉴权、IPC字段和工具集合不变。

同一反例及真实SDK/IPC/后代回收26项全通过；另新增不依赖父监督的子期限测试1通过。61项原worker/heartbeat/完成边界通过，旧attempt或伪造hint不能续租、完成或覆盖继任状态，未知用量仍unsettled。61项为SQLite，不把配置了MySQL的launcher误称实库验证。实际MySQL并发claim/额度、过期lease/完成拒绝/取消和迟到结算复用45已通过证据，不重跑该出口。

## 当前 Linux 组合

由于main和父runner已改变，46此前逐字一致的Linux运行时复用条件不再满足，因此本次实际重跑原Linux完整链：**1 PASS，20.72秒，退出0**。仍使用原已安装的Python3.9 worker/Python3.13 SDK环境和原镜像，不重新安装依赖、不改镜像或CI。真实Gateway/Java身份/自有MySQL/Redis与原worker/SDK执行取消→子进程退出→未知用量阻断→显式对账→同worker新任务→人工采用。worker正常SIGTERM退出、RestartCount=0、日志无已知凭据、容器和临时私密配置清理均通过。模型为合成，Web在宿主，不能称完整Linux全站或最终制品。

首次Linux启动因/Users路径别名不满足canonical校验而setup拒绝，未进入业务；改测试配置为resolve后的已有0700卷路径后通过，原失败保留，不充当产品红灯。当前Linux运行也验证了父PID1兼容。macOS26项是在允许PID1前执行，独立deadline是在最终产品代码执行；不虚构同一SHA的全量组合。

## 出口与限制

S3-01三类证据齐全，现done；16/48完成。证据`work/platform-v2-all-20261019/s3-01-evidence.json`记录原失败、各增量、复用hash和源码hash。SDK没有文件/命令执行工具，watchdog不等于恶意代码沙箱；S3-03仍未放行。父SIGKILL可留空私有临时目录，测试finally清理自有目录；持久task/attempt工作区、快照与孤儿目录回收归S3-02。amd64、固定最终制品及其余组件仍待完成。
