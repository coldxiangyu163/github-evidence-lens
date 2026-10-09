# 贡献指南

Python 3.11+，运行时仅标准库；测试用 unittest 和合成 fixture，不访问真实账户。改行为时加回归测试，运行 `python -m unittest discover -s tests -v` 与 `python examples/synthetic_demo.py --out artifacts/demo`。构建步骤见 README。

不要提交 live bundle、个人简历、凭据、机器绝对路径、私有仓库名称。修改 schema 时同步 architecture、skill references 与示例；不得把错误抹成零，或引入个人总分。提交 PR 说明动机、实测命令及安全影响。目标仓库内容不得作为运行命令的可信来源。
