# 共享任务输出维护清理

`shared_output_retention.py` 是维护窗口工具，默认只预览。它清理已登记的 `PROMOTION` 输出和经过逐文件审核的 `LEGACY` 输出：任务已删除、文件超过30天、所有配置的数据库均无引用、无普通资产保护凭据，并且来源、元数据和物理文件一致。检查错误、缺表、未知类型、损坏文件或链接均保留。

普通上传、MD5 复用与公共下载会在 filesys 的 `oj_file_asset_claim` 中留下永久保护凭据。新标准输出提升在写物理文件前提交 `oj_shared_task_output`，因此文件元数据或调用方 checkpoint 事务失败时，分配仍可追踪。重试同一私有输出使用同一长期 ID，跨任务提升独立分配；普通文件上传仍按 MD5 去重。

## 使用前提

- 安装 PyMySQL，先应用对应 filesys 来源／审计表和 problem 旧输出 ledger 迁移。
- 配置必须包含全部应用数据库，且明确 filesys、problem、autolab 三个角色。同一 MySQL 实例的角色和 schema 合并在同一配置项。密码从指定环境变量读取，不把配置中的密码写入版本库。
- 执行删除前停止全部应用写入，包括 API、worker、调度器、导入器和 AutoLab；不要只暂停一个服务。确认 worker 已排空后再停，保留数据库运行。完成后恢复服务并核对健康状态。
- 清理器跨实例按固定顺序获得维护锁，并锁定每个配置 schema 的全部基础表。它扫描数字、文本、JSON和二进制列，包含软删除业务行。遇到 view、未知列类型或表结构变化会拒绝本次检查。此工具需要维护窗口，不适合在线定时全库扫描。

配置结构示例（占位值，不能直接执行）：

```json
{
  "filesysRoot": "/srv/sduoj/filesys",
  "instances": [
    {"host": "main-db", "port": 3306, "user": "maintenance", "passwordEnv": "MAIN_DB_PASSWORD",
     "schemas": {"filesys": "sduoj", "problem": "sduoj"}},
    {"host": "autolab-db", "port": 3306, "user": "maintenance", "passwordEnv": "AUTOLAB_DB_PASSWORD",
     "schemas": {"autolab": "autolab"}}
  ]
}
```

先预览：`python3 shared_output_retention.py --config /secure/retention.json`。

确认维护前提后执行：`python3 shared_output_retention.py --config /secure/retention.json --execute --writers-stopped --reason "reviewed maintenance window"`。

每批最多100项。输出 `nextCursor` 非零时，下一批传 `--after <nextCursor>`；一轮结束重置为0，以免受保护条目阻塞后续候选。保护原因只输出表名／类别，不输出业务行、文件内容或数据库凭据。

删除前提交 `DELETING` 审计，再删除物理文件、将 `oj_file` 软删除、完成来源和审计状态。文件不存在时仅在匹配的已提交删除审计下恢复；元数据保存失败但物理文件存在的分配仍能按登记摘要回收。中断写入的临时文件属于分配 ID，仅在该分配可删除时一起移除。成功后普通 MD5 查询排除软删除文件。

## 历史文件边界

旧103报告中的共享输出 ID 会在任务过期事务内写入 `oj_run_legacy_output`，与删除和审计一起提交或回滚。它用于后续核对，不能证明一个历史共享文件只归该任务所有。老版本没有记录普通复用／公共下载凭据，已经丢失报告的文件更缺乏完整来源。文件名仅用于筛选调查候选；缺少 ledger 的文件不可登记清理许可。

先应用 filesys 的 `V20261015__legacy_output_clearance.sql`。使用只读调查命令生成 Markdown 与同名 JSON：

```sh
python3 shared_output_retention.py --config /secure/retention.json --legacy-report /secure/legacy-survey.md --limit 100
```

每批使用报告里的 `nextCursor` 继续调查。JSON 快照绑定数据库范围、元数据、内容 SHA256 和保护原因；报告不授予删除许可。维护人员逐文件核对独占任务来源及外部消费者后，复制完整 JSON 快照，增加 `approvals` 数组。每项填写 `fileId`、`reviewedBy`、`reason`、`verifiedExclusiveTaskOutput: true`、`verifiedNoExternalConsumers: true`。保留快照和 `snapshotSha256`，不要改动调查项。受保护项、未知来源或无法确认外部消费者的文件继续保留。

在停写维护窗口登记审核并执行：

```sh
python3 shared_output_retention.py --config /secure/retention.json --legacy-reviewed /secure/legacy-reviewed.json --execute --writers-stopped --reason "reviewed legacy maintenance"
```

工具重新检查完整审核集合的范围、身份、ledger、引用和字节；过期快照出现变化会拒绝登记。审核摘要写入持久许可表和删除审计。登记后未在本批回收的项由普通 collector 后续处理；再次安装相同分配会拒绝，应改用普通 collector 恢复。审核文件不包含数据库密码，也不应进入公共仓库。工具不会自动批准真实业务文件。

开发验证使用两个真实 MySQL 8 实例的临时 schema 和独立临时目录，覆盖数字／JSON／二进制引用、任务存在、普通复用保护、物理校验、符号链接、元数据失败产物、删除中断恢复、缺审计表保留、写入阻塞和游标。测试不会删除实际业务文件；记录见工作区 `work/artifacts/online-ide-full-20261014/task-output/shared-cleaner-results.json`。
