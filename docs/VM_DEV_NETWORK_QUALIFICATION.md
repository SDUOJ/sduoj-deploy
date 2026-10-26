# 执行层 VM 的独立 dev 联网验收

本页是后续执行的 handoff，不是已经完成的 VM 验收。唯一运行责任方必须先结束当前 IDE 性能/恢复序列，再部署新 guest。生产不适用下面的 Mac 地址或端口，也不复制 SSH 转发。

## 已核实的输入

只读证据 `work/artifacts/ide-judger-release-prep-20261026/macbook-vm-business-network-plan-input.json` 来自本任务的 `compose.yaml`，不是其他会话的部署：

- Gateway 8080→loopback38080、Problem8080→loopback38082、Nacos8848→loopback38848、Redis6379→loopback36379。
- Filesys/User/Contest/Websocket 没有宿主 published port。原业务服务使用本任务 Docker network，没有 discovery IP/port 显式覆盖。
- Mac 的 bridge0 为192.168.0.10、en0为192.168.1.100，en5为169.254.68.46；这些是采集时事实，不是永不变化的地址。
- Judger 的 Filesys/Problem/Submission/Run 等 Feign client 只指定服务名，由 discovery 返回地址。仅把 Nacos TCP 端口打通，不能使 Docker 内网地址自动成为新 HVF guest 可达地址。

## 在唯一运行方 dispatch 时落实

1. 重新核本任务 owner、精确镜像、队列/任务/session 排空；保留所有原 compose/config/container IDs 和镜像作为可恢复基线。不停止其他会话服务。
2. 从仍存在的真实 Mac 私网接口选择 dev 专属地址。优先核 bridge0 的192.168.0.10是否仍是当前独立有线接口；验证 guest→Mac和Docker业务→Mac两向路由。不能把尚未验证的接口直接记为可达，也不能使用0.0.0.0或把guest NAT地址登记成Worker地址。
3. 从本任务实际私有配置生成 `docker compose -p sduoj-combined-release-20261026 config --format json`，保存为0600文件；用 `deployment/vm-execution/dev-network.py --resolved-compose /absolute/private/resolved.json --host-address 本次已核验IP --output /absolute/private/network-candidate.json` 生成新候选。该工具不启动服务、不验证接口和端口可达性、不覆盖原配置。候选保留原loopback入口，只给本任务服务增加私网published port：Gateway38080、Problem38082、Filesys38083、Contest38084、User38085、Websocket38089；Nacos38848/39848、Redis36379、Rabbit35672。Rabbit服务名rabbit、容器5672和专属vhost /sduoj来自现有dev模板；执行时仍须核实际私有配置一致。全部端口先检查冲突。
4. 候选给六Java业务服务明确设置 `spring.cloud.nacos.discovery.ip=本次真实私网IP` 与各自 published discovery port；内部server.port保留原值。显式参数必须在实际Nacos实例/Feign调用中核验确已生效。所有消费者看到同一组可达地址，不能让guest仍读取原Docker bridge地址。当前server源码固定nacos-client2.3.2，外部38848对应客户端gRPC39848→容器9848；必须保持main+1000关系，不能只测HTTP主端口。参考[Nacos 2.x端口兼容说明](https://nacos-group.github.io/en/docs/v2/upgrading/200-compatibility/)。实际连接成功和注册仍须实测。
5. 按执行层模板填相同私网IP的 Nacos/Redis/Rabbit/RPC origins、独立namespace/RedisDB2+prefix、owned Rabbit vhost。健康端口39086以及Judger39087/Run39088通过QEMU hostfwd绑定该私网地址；Nacos中登记精确hostIP+port。该地址只属于dev网络配置，不进入生产模板默认值。所有凭据经私有0600文件注入，不放cloud-init、命令行或公开证据。
6. 从 guest 实测服务TCP和鉴权、Nacos实际返回的每个RPC地址；从原业务容器网络位置反向请求Worker `/ready` 并确认登记与heartbeat。最后跑实际Gateway→Redis→Worker、Rabbit→Judger/Run→Filesys/Problem闭环。任一注册地址/DB/prefix/队列不符时停止，不自动回退到原Worker来制造通过。

如果新 guest 无法经所选接口访问原业务地址，保留首次失败和路由证据，先修网络配置。不能在guest安装SSH隧道、复用旧Worker收据，或把仅TCP通当作业务验收完成。

## 资格与恢复

新网络配置、guest内核/Docker、执行镜像/权限/资源必须一起冻结。两轮四语言API、四浏览器、完整业务与评测/Run/隔离、500在线及20/50/100活跃、mixed Debug、900秒稳态、graceful/crash均在新guest实跑；文档关闭后项目/文档/进程回收也计入成功条件。DockerDesktop已有结果保留为修复基线，不转记成VM资格。

回退先停止新准入、排空任务并关闭新消费者/VM，再恢复本任务原dev overlay与discovery地址；核队列唯一消费端、旧业务投影和进程/cgroup清理。不对生产做该dev回退，不清数据库或未知Redis key。
