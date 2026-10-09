# 限制与解释边界

- 搜索索引可能延迟、incomplete_results，最多 1000 条；采样和每 endpoint 页预算产生选择偏差。
- 列表 observed=0 配合 errors 不表示零贡献。公开列表不覆盖私有工作、线下工作、其他账号。
- self/external 是仓库命名空间，不是独立性证明；fork/stars/仓库数量不是个人作者量。
- PR 内容和 review 可变；稳定 ID 标识上下文而非内容哈希，后续采集不能视为相同快照。
- API patches 不保证完整；仅收 head check-runs，不覆盖全部 CI 类型或历史重跑。无目标代码执行。
- 脱敏是尽力而为：不可能识别自然语言中的全部个人信息、联系方式和任意格式秘密。不要自动公开原始 bundle，必须人工复核。
- gh/操作系统/受信 GitHub 服务是信任基础；固定 public 主机和 endpoint，不跟随证据内 URL。GitHub 官方迁移重定向由 gh 处理，仓库 identity mismatch 会拒绝持久化；本工具不是自定义 TLS/代理隔离器。
- 外部 supplied bundle 本身未被签名认证；本地引用验证只验证结构与存在性，不证明数据来自 GitHub或结论真实。
- Markdown 与 HTML 是不同安全渲染策略，原始文字会被转义；HTML 无脚本，SVG 无图片/链接。不替代宿主浏览器更新。
