# Phase 22: Continuous Evolution Loop - Context

**Gathered:** 2026-05-21
**Status:** Ready for planning

<domain>
## Phase Boundary

为 evolution 项目交付一条**自动化进化循环**: GitHub Actions cron 周期性调用 6 个现有 evolve_* CLI (skill / tool_descriptions / tool_params / tool_reasoning / prompt_sections / code), 串行跑出 evolved artifact, 通过每个 CLI 自带的 holdout gate, 然后用 `gh` CLI 在 hermes-agent 仓创建带 NOTICE.md 的 PR — main 分支由 GitHub branch protection + CODEOWNERS 保证 PR 必须经人审才能 merge。Phase 22 同时落地 deploy_mode gate (CONCERNS §M6 闭环 — 写回 hermes-agent 的 write_back_description / prompt write-back 路径在 production 部署下硬 raise PermissionError)。

满足 V2-LOOP-01 + ROADMAP 三条 Success Criteria:
1. Scheduler runs optimization on configurable interval — GH Actions cron weekly + workflow_dispatch
2. Results validated against regression gates before PR creation — 复用每个 evolve_* CLI 已有的 holdout gate (D-15/D-19 + 18 drift + 20 TBLite), Phase 22 不新增 loop-级 cross-artifact gate
3. Human review required before merge (no auto-merge) — GitHub branch protection rules + required reviewers + CODEOWNERS runbook 三件套机械化强制

Phase 22 **不**包含: loop-级 cross-artifact 回归门、并行 matrix 调度、多 cron 调度策略、evolution-self 镜像 audit PR、lockfile 引入、SECRET_PATTERNS 扩充 (这些进 deferred ideas)。

</domain>

<decisions>
## Implementation Decisions

### D1 Scheduler 调度底层 — GitHub Actions cron + workflow_dispatch

- **D-01:** **GitHub Actions 为 Phase 22 唯一 scheduler 底层** (cloud-native, 与 INTEGRATIONS.md §CI/CD 现状 "none detected" 互补 — Phase 22 是第一条 CI/CD 流水线)。优势: ephemeral runner + per-job secret + native `gh` CLI + branch protection 原生集成; minute quota 在公开仓免费, 私仓 2000min/月可承担 weekly 节奏。本地 cron / systemd timer / Python `schedule` lib 全部**不**采纳 — 维护成本 + 依赖 host 存活不符合 V2-LOOP-01 "automated" 期望。

- **D-02:** **调度节奏 = cron weekly + workflow_dispatch**。`.github/workflows/evolution-loop.yml` 主 trigger 是 `schedule: - cron: '<minute> <hour> * * 1'` (每周一凌晨某个 off-peak UTC 时间; planner 选 minute/hour 时避开整点 :00/:30 以分散流量), 副 trigger 是 `workflow_dispatch` 带 inputs (`cli` choice / `iterations` int / `max_cost` float / `dry_run` flag) 支持 ad-hoc 调试或单 CLI 重跑。每天调度 (cron daily 轮转 CLI) 被否决 — PR 频率会淹没 reviewer; manual-only 被否决 — 不满足 SC #1 "scheduled"。

### D2 PR 创建机制与仓库拓扑 — 单向 hermes-agent PR + gh CLI subprocess

- **D-03:** **PR target = `hermes-agent` 仓** (not evolution-self)。Phase 22 loop 在 evolution-self 仓的 GH Actions runner 上跑, 但 evolved artifact (skill / tool desc / prompt section / code) 本来就是 hermes-agent 的产物 — PR head 分支在 hermes-agent, base 是 hermes-agent main。evolution-self 仓不产生 audit PR (deferred — 见 deferred ideas)。这把 SC #3 "human review before merge" 的反应面集中到一个 reviewer 池, 避免 reviewer 分裂。

- **D-04:** **PR 创建用 `gh` CLI subprocess** (not PyGithub, not curl)。`gh pr create --repo <owner>/hermes-agent --head <branch> --base main --title "..." --body @notice.md --label auto-loop --label requires-human-review --draft` 由 Python `subprocess.run` 调用; 零新 Python 依赖, 复用 PROJECT-level "gh CLI 已隐含使用" 现状。`gh` 在 GH Actions runner 上 pre-installed, GITHUB_TOKEN 自动注入。错误处理: subprocess.CalledProcessError 落 metrics.json 后跳过该 CLI 继续 (Phase 22 不让 PR 创建失败阻塞剩余 CLI 调度)。

- **D-05:** **分支命名 = `evolution/auto-loop/<YYYYMMDD_HHMMSS>/<artifact_kind>`** (`artifact_kind` ∈ {skill, tool-descriptions, tool-params, tool-reasoning, prompt-sections, code})。timestamp UTC 与 evolve_* 输出 `output/<kind>/<ts>/` 一致。content-addressed (SHA) 分支名被否决 (调试困难)。fork-based PR 被否决 (设置复杂 + token scope 膨胀)。Workflow runner 直接 `git push origin <branch>` 同仓 push, base=main。

### D3 Loop 范围与节奏 — 全 6 CLI 串行 + per-CLI 独立 max-cost

- **D-06:** **全部 6 个 evolve_* CLI 都进 loop** (skill / tool_descriptions / tool_params / tool_reasoning / prompt_sections / code)。Phase 22 提供完整 V2-LOOP-01 覆盖 — 后期再加 Phase 23+ "选择性调度" 是可逆扩展, 当前不裁剪。`evolution.yaml` 新增 `loop:` 顶层 key, 子键 `loop.cli.<name>.enabled: bool` 让人 (而非 Phase 22 代码) 控制运行时启停。

- **D-07:** **串行执行** (固定顺序 skill → tool_descriptions → tool_params → tool_reasoning → prompt_sections → code), **上一个失败不阻塞后续**。串行原因: 避免 LLM API rate-limit + 简化总成本计算 + 让 reviewer 看到 PR 时能区分各 CLI 的产物。GH Actions matrix 并行被否决 (PR ×6 同时打到 reviewer + token scope 复杂); skip-on-fail 让 loop 自愈 — 比如某次 evolve_tool_params 因 model 临时降级失败, evolve_prompt_sections 仍跑。

- **D-08:** **每个 CLI 独立 max-cost cap, 经 evolution.yaml 配置**。`evolution.yaml` 新增 `loop.cli.<name>.max_cost_usd: float` (默认 5.0)。Phase 22 loop runner 读这段配置, `subprocess.run(['python', '-m', 'evolution.<pkg>.<module>', '--max-cost', str(cap), ...])`。复用 `EvolutionConfig.max_cost_usd` (CLI flag → Config 的现有 5-param load 链); 不新加 loop-级总预算 — 用户在 evolution.yaml 通过 sum 调整。Loop runner 把每个 CLI 实际花费 (从 metrics.json 提取) 累计到 `output/loop/<ts>/run_summary.json` 仅作 audit, 不动态降级后续 CLI。

### D4 人审 gate 强制机制 — Branch Protection + CODEOWNERS + 复用上游 holdout gate

- **D-09:** **机械化 human-review gate = GitHub branch protection + required reviewers + CODEOWNERS 三件套**。Phase 22 交付一份 `setup-hermes-agent-branch-protection.md` runbook (steps 化, 用户在 hermes-agent 仓 Settings 里点开应用)。Required settings: `main` 分支 — `require pull request review (1 reviewer min)` + `dismiss stale reviews when new commits are pushed` + `require status checks to pass (Phase 21 import-boundary CI + 任何 hermes-agent 自有 CI)` + `restrict who can push to matching branches (除 reviewer 外)`。`.github/CODEOWNERS` 在 hermes-agent 仓配置: `* @<hermes-owner>` (evolution bot 账号**不**作为 codeowner, 强制必有第二人审)。仅 NOTICE.md UNREVIEWED 字面量被否决 — 纯约定不防止误操作 merge。

- **D-10:** **复用每个 evolve_* CLI 已有的 holdout gate, Phase 22 不新增 loop-级 cross-artifact 回归门**。每个 CLI 在 output/<kind>/<ts>/metrics.json 已写 `holdout_gate_passed: bool`; loop runner 仅当 `holdout_gate_passed=true` 才进 PR 创建; 否则把 `output/<kind>/FAILED_<ts>/` 路径落到 run_summary.json + 不创 PR + 不阻塞后续 CLI。SC #2 "Results validated against regression gates before PR creation" 由此满足。Cross-artifact gate (同时改 prompt + tool desc 是否互相破坏) 作为 Phase 23+ 增项 (deferred)。

- **D-11:** **deploy_mode gate 落地 = `EvolutionConfig.deploy_mode` + write_back_description / prompt write-back guard**。`evolution/core/config.py` 加 `deploy_mode: Optional[str] = None` (取值 None/`'dev'`/`'production'`, env: `EVOLUTION_DEPLOY_MODE`, CLI flag: `--deploy-mode`)。`evolution/tools/tool_loader.py:578 write_back_description()` 和 `evolution/prompts/prompt_loader.py:182` 入口加 `if config.deploy_mode == 'production': raise PermissionError("hermes-agent is read-only in production deploy_mode — use output/ only")`。Phase 22 GH Actions workflow yaml 设 `env: EVOLUTION_DEPLOY_MODE: production`。本地 dev 调用不带 deploy_mode 默认行为不变 — CONCERNS §M6 (hermes-agent Read-Only Not Enforced) 闭环。OS-层 chmod -R a-w 被否决 (超出 Python 代码范围 + Linux only)。

### Claude's Discretion

- GH Actions YAML 的具体结构 (job 命名、step 划分、cache key、Python 版本 matrix) — planner 读 GH Actions docs 后定保守 default (Ubuntu-latest, Python 3.13)
- `gh pr create` 的精确 flag 组合 (是否 `--draft`, label 名称的最终 spelling, body 是用 `--body-file` 还是 inline) — planner 读 `gh pr create --help` 选最简洁组合
- `evolution.yaml` 的 `loop:` 段 schema (是否嵌套 / 是否支持 `--config` 覆盖) — planner 与 EvolutionConfig.load 现有结构对齐
- CODEOWNERS 的具体 GitHub username (用户在 runbook 中自填占位符)
- branch protection rules 设置的精确 JSON (在 runbook 里给 `gh api` 命令而非 UI 截图)
- Loop history 持久化策略 (output/loop/<ts>/run_summary.json 字段 schema) — planner 与 Phase 20 tblite_history.json + Phase 18 calibration 持久化模式对齐
- 失败告警/通知 (GH Actions 失败时是否触发 issue 创建 / Slack webhook) — planner 给 minimal default (GH Actions 自带 email-on-failure 已足够, 不引入新依赖)

### Folded Todos

- **`.planning/todos/pending/2026-05-07-enforce-readonly-hermes-agent.md`** — fold 进 Phase 22 作为 D-11 (deploy_mode gate)。原始问题: hermes-agent 在 CLAUDE.md 声明 "read-only access" 但代码层未强制 — Phase 20 D-09 Virtual Prompt Overlay 进一步打破了此承诺, CONCERNS §M6 标记为 MEDIUM。Phase 22 是第一个真正自动化高频写回 hermes-agent 的 phase (PR 创建 = 通过 gh CLI 远程写), 必须在 production deploy_mode 下硬 raise PermissionError 阻止意外本地写回。Phase 20 CONTEXT 在 Reviewed Todos 段已经显式建议推迟到 Phase 22。

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 项目规划文档 (必读)
- `.planning/REQUIREMENTS.md` §V2-LOOP-01 line ~117 — Phase 22 需求来源 ("Continuous evolution loop — scheduled optimization with regression gates and PR creation")
- `.planning/ROADMAP.md` §"Phase 22: Continuous Evolution Loop" — goal "Automated pipeline that periodically runs optimization, validates, and creates PRs" + 3 条 Success Criteria
- `.planning/PROJECT.md` — Last updated 2026-05-20 行确认 Phase 21 已完成、Phase 22 next; 项目约束 (read-only hermes-agent / output/ 写产物 / 不引入 cloud DB) 直接影响 D-01/D-03/D-11

### 强相关前置 CONTEXT (模式直接复用)
- `.planning/phases/21-darwinian-code-evolution/21-CONTEXT.md` §D-15 + §D-19 — holdout gate (pytest 100% + size + ruff) + NOTICE.md UNREVIEWED 字面量 (Phase 22 复用此 NOTICE 模式写入 PR body)
- `.planning/phases/21-darwinian-code-evolution/21-CONTEXT.md` §D-18 双层 import boundary (pre-commit + pytest) — Phase 22 在 hermes-agent 仓的 branch protection required status checks 必须包含此类 CI
- `.planning/phases/20-benchmark-gated-validation/20-CONTEXT.md` §"Reviewed Todos" — 显式建议 enforce-readonly todo 留 Phase 22, 本 phase 兑现
- `.planning/phases/20-benchmark-gated-validation/20-CONTEXT.md` §D-13 — `build_tblite_calibration` 独立 CLI 模式 + history.json 持久化, Phase 22 loop runner 同构 (per-CLI history 累积)

### 实现锚点 (planner / executor 必读)
- **evolution 项目侧 (现有 6 CLI 入口)**:
  - `evolution/skills/evolve_skill.py` — skill evolution CLI 入口
  - `evolution/tools/evolve_tool_descriptions.py:467-490` — Click 三件套模板 (Phase 22 loop runner 用同样的 Click 风格)
  - `evolution/tools/evolve_tool_params.py` — Phase 13 V2-TOOL-PARAMS CLI
  - `evolution/tools/evolve_tool_reasoning.py` — Phase 14/15 think-augmented CLI
  - `evolution/prompts/evolve_prompt_sections.py` — prompt 段进化 CLI (含 Phase 20 `--benchmark=tblite` 步)
  - `evolution/code/evolve_code.py` — Phase 21 code 进化 CLI
- **配置层**:
  - `evolution/core/config.py:30-65` — `EvolutionConfig` 字段定义 (D-11 在此加 `deploy_mode`)
  - `evolution/core/config.py:109-300+` — `EvolutionConfig.load(**overrides)` 5-param + env + yaml 三层链 (Phase 22 复用; D-08 `loop.cli.<name>.max_cost_usd` 通过 yaml 层落)
  - `evolution.yaml` 当前 schema (Phase 12+) — Phase 22 新增 `loop:` 顶层 key 不破坏现有 `models:` / `api_base` / `api_key`
- **D-11 write-back guard 落地点**:
  - `evolution/tools/tool_loader.py:578` `write_back_description()` — 加 deploy_mode guard
  - `evolution/prompts/prompt_loader.py:182` — 同样加 guard

### 外部工具
- `gh` CLI v2.x — GitHub Actions runner 自带; `gh pr create --help` / `gh api repos/<owner>/<repo>/branches/main/protection` 文档
- GitHub Actions `schedule` + `workflow_dispatch` triggers — `https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows#schedule`
- GitHub branch protection API — `https://docs.github.com/en/rest/branches/branch-protection`
- GitHub CODEOWNERS — `https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners`

### 安全/合规参考
- `.planning/codebase/CONCERNS.md` §M6 — hermes-agent Read-Only Not Enforced — Phase 22 D-11 闭环
- `.planning/codebase/CONCERNS.md` §H4 — `output/` not in `.gitignore` (Phase 20 已修复, Phase 22 不再需关注)
- `.planning/codebase/INTEGRATIONS.md` §"CI/CD" — "None detected" 现状基线, Phase 22 是第一条 CI/CD pipeline
- `.planning/codebase/INTEGRATIONS.md` §"External Repository" — `hermes-agent` discovery chain (`HERMES_AGENT_REPO` env / `~/.hermes/hermes-agent` / `../hermes-agent`), Phase 22 GH Actions workflow 需 `actions/checkout@v4` 单独 checkout hermes-agent 到 runner

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`EvolutionConfig.load(**overrides)`** (`evolution/core/config.py:109`) — Phase 22 loop runner 读 `evolution.yaml` 不重写解析逻辑; `loop.cli.<name>.max_cost_usd` 通过 yaml 层自动 cascade 到 CLI 子进程的 `--max-cost` flag
- **Click 三件套模式** (PATTERNS.md §evolve_tool_descriptions lines 392-464) — Phase 22 loop runner 自身也是一个 Click CLI (`evolution/loop/run_loop.py` 或类似), 调用其他 CLI 复用 `subprocess.run(['python', '-m', 'evolution.<pkg>.<module>', ...])` 模式
- **`output/<kind>/<ts>/` 目录约定** — Phase 22 loop 拼装新分支 commit 时只需 `cp -r output/<kind>/<ts>/* <hermes-checkout>/<artifact_path>` (具体路径 plan 时定)
- **NOTICE.md template** (Phase 21 D-19, in `evolution/code/evolve_code.py NOTICE_TEMPLATE`) — Phase 22 PR body 直接 cat output/<kind>/<ts>/NOTICE.md (对于 evolve_code) 或基于 metrics.json + holdout_gate_passed 重新组装 (对于其他 5 个 CLI)
- **`gh` CLI 习惯用法** — PROJECT-level CLAUDE.md "Use gh CLI for all GitHub-related tasks" 已隐含; Phase 22 沿用此模式

### Established Patterns
- **subprocess + timeout + restricted env**: Phase 20 TBLiteRunner + Phase 21 sandbox_runner 都是这个模式 — Phase 22 loop runner 调用 evolve_* CLI 时同构 (subprocess.run + 600s timeout per CLI / 2hr 总 workflow timeout)
- **FAILED_<ts>/ rename + 不阻塞**: Phase 20 D-04 + Phase 21 D-15 模式 — Phase 22 loop 处理 holdout_gate_passed=false 时同构: 记录 FAILED 路径到 run_summary.json + skip PR + continue 下一个 CLI
- **history.json 持久化** (Phase 20 D-13 tblite_history.json): Phase 22 在 `output/loop/<ts>/run_summary.json` 累积每次 loop 各 CLI 的 success/fail/cost/PR-URL, 同 Phase 20 模式; history.json **不** git track (.gitignore 已盖 output/)
- **EVOLUTION_API_KEY / EVOLUTION_API_BASE env-driven secrets** (`evolution/core/config.py:209-228`): Phase 22 GH Actions workflow 用 repo secrets `EVOLUTION_API_KEY` + `EVOLUTION_API_BASE` 映射到 env, 然后 EvolutionConfig.load 自动 pick up
- **`_contains_secret` + `SECRET_PATTERNS`** (`evolution/core/external_importers.py`): Phase 21 D-19 已经把 NOTICE.md 失败字段都过了 _contains_secret; Phase 22 不重复此过滤, 仅在 loop runner 拼 PR title / commit message 时再过一遍以防 metrics.json 中模型名 / api_base 域名被 leaked (defense in depth)

### Integration Points
- **`.github/workflows/evolution-loop.yml`** (新建): GH Actions 主入口, 含 cron + workflow_dispatch + job(`run_loop`) + steps(checkout self / checkout hermes-agent / setup python / pip install / run loop / upload artifacts)
- **`evolution/loop/`** (新建子包, 与 evolution/code / evolution/tools / evolution/prompts 同级): 含 `run_loop.py` (Click CLI) + `pr_creator.py` (gh subprocess wrapper) + `__init__.py` (lazy guard)
- **`evolution.yaml` 顶层新增 `loop:` 段**: 不破坏 Phase 12 现有 backend 配置; planner 决定 yaml schema 精确形状
- **`evolution/core/config.py:30-65` `EvolutionConfig`**: 加 `deploy_mode: Optional[str] = None` 字段, load() 加 env + override 链
- **`evolution/tools/tool_loader.py:578` + `evolution/prompts/prompt_loader.py:182`**: 加 deploy_mode == 'production' guard, raise PermissionError
- **hermes-agent 仓 (~/.hermes/hermes-agent)**: Phase 22 workflow 通过 `gh api repos/<owner>/hermes-agent/branches/main/protection` 应用 branch protection — 但**不** Phase 22 自动执行; 仅交付 `setup-hermes-agent-branch-protection.md` runbook (用户手动跑 `gh api -X PUT ...`)
- **`setup-hermes-agent-branch-protection.md`** (新建, 仓根 docs/ 或类似): step-by-step runbook + `gh api` 命令模板 + CODEOWNERS 模板 + verification 步骤

</code_context>

<specifics>
## Specific Ideas

- **PR 标题模板**: `auto-loop: <artifact_kind> evolved at <ts>` (例: `auto-loop: prompt-sections evolved at 20260601_030000`) — 让 reviewer 一眼区分 evolution loop PR vs 人写 PR
- **PR 默认带两个 label**: `auto-loop` + `requires-human-review` (后者配合可选的 PR-label-bot 做额外 gate, Phase 22 不引入此 bot 仅打 label)
- **Phase 22 自身的 cron 时刻**: 每周一 UTC 08:57 (planner 自由选具体非整点 minute, 避开 :00/:30) — 周一保证全周修复时间充足
- **GH Actions runner OS**: `ubuntu-latest` (gh CLI 自带 + 与 sandbox_runner pytest subprocess 行为一致, macOS-latest 不必要也更贵)
- **Workflow 整体 timeout**: 2 hours (single-job, 6 CLI 串行每个 ~15min 计 + buffer); per-step timeout 单独设
- **`evolution/loop/` 命名**: 不取 `evolution/scheduler/` 因为 scheduler 仅是 invocation 角度; loop 更贴近 "continuous evolution loop" V2-LOOP-01 命名

</specifics>

<deferred>
## Deferred Ideas

- **Loop-级 cross-artifact regression gate** — 多个 evolve_* CLI 同时改 hermes-agent 时是否相互冲突 (例: prompt 改了 "use tools sparingly" 但 tool descs 改得更冗长). Phase 22 仅复用上游 holdout gate, Phase 23+ 可加 `loop_regression_check.py` 在 PR merge 前跑 hermes-agent 全集 test。
- **GH Actions matrix 并行** — 6 个 CLI 用 matrix 并行而非串行, 总时间从 ~90min 降到 ~20min。需先解决: PR 数量 ×6 + token scope 复杂 + reviewer 负担。Phase 23+ 候选。
- **evolution-self audit PR 镜像** — Phase 22 仅 PR 到 hermes-agent。可以在 evolution-self 也开一个 audit PR 总结 metrics + run_summary.json + diff 链接 — 提供历史索引 + 让 evolution 项目侧 reviewer 也看到产物。Phase 22 不做避免双 PR 复杂度。
- **每 CLI 调度独立 cron / 不同节奏** — evolve_code 可能比 evolve_skill 需要更高频率 (Phase 21 新交付, 风险更高需更快迭代检测)。Phase 22 统一 weekly 后, Phase 23+ 可拆解。
- **失败告警 (Slack / issue 创建)** — Phase 22 仅依赖 GH Actions 原生 email-on-failure。增加 Slack webhook / 自动 issue 创建是 ops hygiene 的独立工作。
- **Per-CLI 子集开关** — `evolution.yaml.loop.cli.<name>.enabled: bool` 已在 D-06 中提及作为 schema 一部分, Phase 22 实现该字段; 但 "动态根据上次 history 自动启停" (例: 连续 4 次同一 CLI fail 后自停) 是 future smartness。

### Reviewed Todos (not folded)
- **`.planning/todos/pending/2026-05-07-add-lockfile-dspy-pin.md`** — Lockfile + DSPy pin 提高可重现性, 但 GH Actions runner 上 `pip install .` 每次新装的 transient 差异在 Phase 22 weekly cadence 下可接受; 留作独立 hygiene phase 处理。
- **`.planning/todos/pending/2026-05-07-expand-secret-patterns.md`** — Phase 22 PR 边界确实是 secret leak 风险点 (NOTICE.md / commit message / branch name), 但当前 SECRET_PATTERNS (Phase 14 D-15) 已覆盖 JWT + AWS + Shannon entropy + 邻近模式; Phase 22 用 defense-in-depth 在 PR 拼装时再过一遍 _contains_secret 即可, 模式集本身扩充作为独立任务 (例: GitHub PAT / OpenAI key prefix / DashScope key 格式) 留作 hygiene phase。
- **其他 4 个 0.6 score todos** (centralize-lm-retry / harden-llm-output-parsing / make-jsonl-loaders-skip-bad-lines / untitled) — 均为通用代码质量项, 与 V2-LOOP-01 scope 无直接关系, 不 fold。

</deferred>

---

*Phase: 22-continuous-evolution-loop*
*Context gathered: 2026-05-21*
