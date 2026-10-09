# GitHub Evidence Lens

**从公开贡献找证据，而不是给人打分。** Skill-first GitHub 调研工具：确定性 CLI 负责采集、可追溯引用和安全渲染；你现有 Agent 的模型负责挑选贡献、读代码、找反证并提出有限结论。无内置付费模型，无个人总分，无招聘资格推断。

## 快速开始

需要 Python 3.11+；真实采集另需已安装并自行登录的 GitHub CLI `gh`。不要求读取或授予任何私有仓库权限。运行时仅 Python 标准库。

```bash
git clone https://github.com/coldxiangyu163/github-evidence-lens.git
cd github-evidence-lens
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install .
github-evidence-lens --help
# 无账号、无网络的第一步：明确标记的合成演示
python examples/synthetic_demo.py --out artifacts/demo
github-evidence-lens report artifacts/demo/bundle.json --findings artifacts/demo/findings.json --out artifacts/demo/report
```

用浏览器打开 `artifacts/demo/report/report.html`；同时生成 `report.md` 与静态 `card.svg`。演示内容不是任何真实人的报告。

```bash
# 替换 USER / OWNER / REPO / N，严格保留合法标识，不接受 URL 或 @前缀
github-evidence-lens collect USER --out artifacts/collection --max-prs 100 --sample-prs 6 --max-pages 10
github-evidence-lens inspect OWNER/REPO#N --out artifacts/inspection
# 无 findings = 明确注明未经 AI 评审的证据清单
github-evidence-lens report artifacts/collection/bundle.json --out artifacts/report
# Agent 按 skill 生成 findings.json 后，校验引用再输出
github-evidence-lens report artifacts/collection/bundle.json --findings artifacts/findings.json --out artifacts/reviewed
```

`inspect` 输出独立 bundle，不隐式合并或覆盖 collect 数据；请使用不同 `--out`。对 inspected bundle 单独写 findings/report，或由调用方显式整合、保留来源后验证。相同 out 的 bundle 会原子替换。退出码 0 表示操作完成，2 表示参数/文件/引用错误或存在采集错误；**即使退出 2，也保留含错误的部分 bundle**。预算截断不是 API 错误：需阅读 completeness/coverage，退出 0 不代表全量。

## 安装 portable skill

从本仓库复制完整 `skills/github-evidence-lens/`（含 references）到宿主支持的技能目录，并单独安装 CLI；skill 本身不自动装包、不改 Agent 配置、不附带模型。先检查是否存在同名技能，避免覆盖。

```bash
# 通用 Agent Skills convention（宿主需支持）
mkdir -p .agents/skills
cp -R skills/github-evidence-lens .agents/skills/
# Claude Code 项目级技能目录（在目标项目中执行）
mkdir -p .claude/skills
cp -R skills/github-evidence-lens .claude/skills/
# Hermes 默认 profile（仅用户选择执行；命名 profile 请用该 profile 的 skills 目录）
mkdir -p ~/.hermes/skills
cp -R skills/github-evidence-lens ~/.hermes/skills/
```

目录约定参考 [Hermes skills 文档](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills/) 与 [Claude Code skills 文档](https://code.claude.com/docs/en/skills)。构建本项目不会执行这些复制操作。

给 Agent 的提示：`使用 github-evidence-lens，围绕我关心的工程领域检查 USER 的公开贡献；先说明范围和预算，挑选代表 PR，检查代码、review、CI 和反证，输出有 evidence ID 的有限结论。不要个人总分。`

## 能做与不能做

- public-only PR search + 仓库可见性二次验证；分页、去重、外部/自有 merged/open/closed-unmerged 分列。
- 有界 PR 元信息、文件 patch、reviews、review comments、discussion、head SHA check-runs。
- 可追溯 evidence ID、URL、时间、head SHA、错误、截断、分母与抽样方法。
- Agent findings 引用校验；Markdown 转义、独立 HTML、无脚本/远程图片的 SVG。
- **引用存在不等于结论正确**。没有 diff 不等于没有贡献，CI 存在不等于通过，closed 不等于被拒，自有合并不等于外部认可。
- 不推断 AI 作者身份、账号现实身份、智商、百分位、普适能力或雇佣资格。组织仓库也可能是本人控制；external 仅指命名空间不同。

文档：[PRD](docs/PRD.md) · [架构/数据契约](docs/architecture.md) · [方法](docs/methodology.md) · [限制](docs/limitations.md) · [安全](SECURITY.md) · [贡献](CONTRIBUTING.md) · [路线图](ROADMAP.md)

## 测试与打包

```bash
python -m unittest discover -s tests -v
# 离线构建需要本机预装 setuptools>=68 和 wheel；不涉及 GitHub 或凭据
python -m pip wheel --no-deps --no-build-isolation --no-index . -w dist
python -m pip install --no-deps --no-index dist/*.whl
```

CI 的测试/构建命令不访问 GitHub API、不需要 secret；checkout/setup-python 和构建工具准备阶段需要下载环境及 setuptools/wheel，后续测试和打包离线执行。

## English

A skill-first public GitHub contribution investigation toolkit, not a personal score. Python 3.11+, standard-library runtime, `gh` for bounded read-only API calls. `collect` inventories public evidence; `inspect` lets an agent choose PRs; `report` renders safe Markdown/HTML/SVG and validates optional agent-authored findings against evidence IDs. No embedded LLM. Synthetic offline demo and unittest suite are included. Public evidence cannot establish identity, AI authorship, general capability or hiring eligibility. MIT licensed.
