# 架构与数据契约

`gh GET -> GhAPI -> Collector -> bundle.json -> 宿主 Agent findings.json -> validate -> Markdown / HTML / SVG`

- `core.py`：输入/endpoint allowlist、带超时/字节预算的 gh 子进程、脱敏、公开验证、分页、抽样、原子持久化。
- `report.py`：bundle 与引用验证、安全 URL、纯数据转义渲染。
- `__main__.py`：CLI、退出码、50 MB 本地输入限制。
- `skills/`：不绑定供应商的 Agent 调查流程；不是自动运行的程序。

## bundle schema_version 0.1

顶层 `source` 区分 live 与明确 SYNTHETIC fixture；`retrieved_at` UTC；`subject`；`budget`；`coverage` 按 endpoint 记录 observed/total/pages/truncated/errors/incomplete_results；`counts` 仅观察到的公开 PR 分组；`selection` 保存方法与入选 URL；`errors` 保存 endpoint、脱敏错误、时间。

每条 evidence：

| 字段 | 契约 |
|---|---|
| id | `ev_` + SHA-256(kind、规范 URL、PR 编号、head SHA) 前 20 hex；同上下文稳定，不是内容签名 |
| kind | profile / repository / pr_inventory / pr_detail / files / reviews / review_comments / discussion / checks |
| url | https://github.com 的规范 source URL |
| retrieved_at | UTC ISO-8601；不是目标提交时间 |
| repo / pr / head_sha | 可用时写入；不适用则 null |
| content | 最小字段 allowlist + 文本脱敏；评论保留最小 user.login/type 和 author_association |
| completeness | truncated/errors；分页还含 observed/total/pages；patch_missing、patch_completeness_unknown |

repository evidence 保存 private=false、visibility=public 的确认，不保存失败或私有元数据。repo verification 同次运行缓存；公开性可能随后变化。列表无总数时 total=null，不能伪造全站分母。source URL 指向 GitHub，内容并非签名快照；URL 未来可能变化或失效。

## findings schema_version 0.1

`findings` 数组，每条有 `claim`、`status`（supported/partial/contradicted/unknown）、`rationale`、非空 `evidence_ids`、显式 `counterevidence` 字符串数组、非空 `limitations` 字符串数组；可加 `counterevidence_ids`。全部 ID 必须存在于当前 bundle。见 skill 的 schema/example；引用检查不能验证自然语言真假，也不自动判定引用是否真的支持 claim。

## 预算与故障

默认每 endpoint 最多 10 页、每页 100；max-prs 默认 100（最多 1000），sample-prs 默认 6（最多 100）；每次 gh 响应上限 2 MB，超时 45 秒，超限丢弃该页并记录错误，不存半截 JSON。最大理论请求量由仓库页数、去重仓库验证、PR 样本与详情页预算共同界定，不是一个全局 wall-clock SLA。GitHub 失败不转为成功零值；CLI 2 + errors/coverage 留下部分结果。不会盲目自动重试耗尽速率预算。

JSON 在同目录临时文件 fsync 后 os.replace；HTML/MD/SVG 为派生文件。相同目录重复运行会替换文件。无需数据库、无遥测、无 shell=True。
