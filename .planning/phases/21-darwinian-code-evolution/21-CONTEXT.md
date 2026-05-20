# Phase 21: Darwinian Code Evolution - Context

**Gathered:** 2026-05-20
**Status:** Ready for planning

<domain>
## Phase Boundary

将自进化能力从文本制品 (skills / tool descriptions / prompt sections) 扩展到**代码**:为 hermes-agent 选定一个低风险的目标组件 (`tools/ansi_strip.py`),在 evolution 项目里走完整的 GEPA-style 进化循环 — LLM 生 patch → pytest 二进制门 + size + ruff 评分 → 反思 → 保留 top-K → 迭代。**至少一个 hermes-agent 代码组件可进化** (V2-CODE-01) 即满足成功标准,本期不追求多组件覆盖。

落地三件事:
1. **`evolution/code/` 新包**:`code_target_loader.py` (组件描述 + 测试发现) + `code_fitness.py` (pytest 二进制 + size penalty + ruff lint 评分,无 LLM judge) + `code_evolver_adapter.py` (**唯一** import openevolve 的文件,单点 import 面) + `evolve_code.py` (Click CLI 入口 + GEPA-style 调度) + `sandbox_runner.py` (subprocess + timeout 评估 candidate 代码,不在主进程 exec 未审 LLM 代码) + `LICENSING.md` (本期 boundary 说明)。
2. **基础设施前置**:`LICENSE` 仓根 (MIT) + `pyproject.toml` 加 `[project.optional-dependencies] code = ["openevolve>=0.2.27"]` + CI lint gate (`grep` 校 `import openevolve` 仅在 `code_evolver_adapter.py` 出现)。
3. **运行产物**:`output/code/<ts>/<component>.py` + 同目录 `NOTICE.md` (LLM 生成源 + 未经人工审核警示) + `metrics.json` + `diff.txt` + `eval_holdout.json`。**永远 output-only,不写回 hermes-agent**。

**In scope:**
- 新包 `evolution/code/{__init__.py, code_target_loader.py, code_fitness.py, code_evolver_adapter.py, evolve_code.py, sandbox_runner.py, LICENSING.md}`
- PoC 目标 = `~/.hermes/hermes-agent/tools/ansi_strip.py` (44 行,纯算法 CSI/SGR/OSC 转义序列去除,零安全敏感路径)
- 复用 hermes-agent 自带 30 个 pytest (`tests/tools/test_ansi_strip.py`):20/10 stratified split (按 CSI / SGR / OSC 三类) + 在 evolution 仓内手补 5-10 个 edge case (长输入 / Unicode 边界 / 嵌套转义) 进 holdout
- Fitness = pytest 100% 二进制硬门 (不过直接 reject) + size_penalty (>baseline ×1.2 罚 0.3 / >×1.5 reject) + ruff lint score (0-1)
- openevolve native LLM client (复用 `EvolutionConfig.optimizer_model` / `api_base` / `api_key` 三层后端配置值,不走 `dspy.LM` 路径)
- Candidate 评分沙箱:每个 candidate 代码以 `subprocess.Popen` 跑 pytest,30s timeout (单 test) / 120s 总 cap,工作目录隔离到 `~/.hermes/tmp/code_eval_<ts>/`,**不**触碰真实 hermes-agent tree
- LICENSE (MIT) 落仓根 — **本期必须前置**
- CI lint gate:pre-commit + pytest 各加一道 `grep -r "import openevolve" evolution/ --exclude-dir=__pycache__` 校验,出现在 `evolution/code/code_evolver_adapter.py` 之外时硬 fail
- `output/code/<ts>/NOTICE.md` 与 evolved 文件同目录,说明 LLM 生成、未审核、勿直接合入生产
- `metrics.json` schema 含 `pytest_passed` / `pytest_total` / `size_baseline_bytes` / `size_evolved_bytes` / `size_penalty` / `ruff_violations` / `ruff_score` / `composite_fitness` / `optimizer_used` / `holdout_passed`
- `evolve_code` CLI flags (与 v1 三个 evolve_* 风格对齐):`--component / --iterations / --eval-source / --hermes-repo / --dry-run / --max-cost / --allow-miprov2-fallback`
- 不少于 12 个单元测试,覆盖:(a) code_target_loader 找文件 + 收集 pytest;(b) code_fitness 三段计分各自 (pytest 二进制 / size / ruff);(c) code_evolver_adapter 单点 import 边界 (假突破 CI gate);(d) sandbox_runner timeout + 工作目录隔离;(e) evolve_code 端到端 dry-run 一次 (mock openevolve);(f) holdout edge case 真实回放

**Out of scope:**
- **多组件 / 模块级重构** — FEATURES "NOT broad refactoring agents",本期一个文件,后续 phase 再拓
- **安全敏感组件** (auth / sandbox / 凭证 / `agent/redact.py` / `agent/credential_*.py`) — FEATURES 硬限,即使本期沙箱成熟也不碰
- **递归自进化 evolution/ 自身** — FEATURES anti-feature,planner 在 evolve_code 入口加白名单 + 硬 reject `evolution/` 路径
- **LLM-as-judge 主导 fitness** — PITFALLS:代码二进制对错,LLM judge 在代码域 flaky。本期连 ≤0.1 权重的 nudge 也不要,纯 deterministic 评分
- **写回 hermes-agent** — 即使 pytest 全过 + ruff 全过 + holdout 全过,evolved 代码仍只落 output/code/,人工审核后手工合入 (与 v1 三个 evolve_* 同策略;Phase 22 自动 loop 才考虑 PR 流)
- **Phase 22 持续进化循环** — PROJECT.md Out-of-Scope 明确
- **多 evolver 同时切换** — 本期单 evolver = openevolve;不预留 plugin 注册中心 (与项目"先实做后抽象"风格一致)
- **AGPL 边界 / `.venv-agpl/` 隔离** — openevolve Apache-2.0 已规避,无需。darwinian-evolver 路径完全弃
- **Modal / 远程沙箱** — 本期 candidate 评分走本地 subprocess + timeout 即可
- **Test-suite 自动生成 / property-based fuzzing 进 train** — 手补 holdout edge case 即可,property-based 是未来扩展
- **PR/auto-merge** — PROJECT.md Out-of-Scope

</domain>

<decisions>
## Implementation Decisions

### D1 进化引擎选型 — openevolve native + 单点 import 面

- **D-01:** **openevolve (Apache-2.0, ≥0.2.27)** 作为底层 evolutionary code search 库。研究 SUMMARY §1 验证 `pip index versions darwinian-evolver` 无匹配;openevolve 是 PyPI 上唯一 actively-maintained 的 LLM-driven code evolution 库,API surface (population / mutation / archive / fitness) 直接映射 Phase 21 需求。AGPL 边界问题被本决策**永久关闭**。
- **D-02:** **`pyproject.toml` 加 `[project.optional-dependencies] code = ["openevolve>=0.2.27"]`**,**移除现存 `[darwinian]` extra**。`pip install .[code]` 显式 opt-in 安装,默认 install 不触发。LICENSE 注明 openevolve 是可选依赖。
- **D-03:** **单点 import 面架构**:**`evolution/code/code_evolver_adapter.py` 是项目内唯一**写 `import openevolve` 的文件 (除非可读的 docs/tests 字符串字面量)。adapter 暴露窄接口给 `evolve_code.py`,内部封装 openevolve 调度 / Population / Archive 等 evolver 概念。**理由**:复用 v1 单点 facade 模式 (类似 `TBLiteBenchmarkGate` 包 TBLite subprocess)、为未来可能换 evolver (e.g. self-roll DSPy+GEPA) 留收口、配合 CI lint gate 让架构边界可机械化校验。
- **D-04:** **LLM 路径走 openevolve 原生 client + 复用 EvolutionConfig 配置值**。`code_evolver_adapter` 读取 `EvolutionConfig.optimizer_model` / `api_base` / `api_key` (即现存 `evolution.yaml` / `EVOLUTION_API_*` 三层链),然后**实例化 openevolve 自己的 LLM client** (e.g. 它内置 `openai.OpenAI` 或 `litellm.completion`) 传入。**不走** `dspy.LM`,因为 openevolve 不消费 DSPy primitives;但配置**值**统一,Phase 21 与 v1 三个 evolve_* 在 evolution.yaml 看见的是同一份配置。**Risk anchor**:openevolve 可能只接受特定 LLM SDK (OpenAI-compatible chat completions / litellm 等),planner Task 1 需 spike 验证,若不直接吃 base_url override,adapter 加一层 shim。
- **D-05:** **不复用 GEPA reflection_lm 模式**。openevolve 内置自己的 LLM mutation 反思 (读取 fitness reasoning + 提 patch 建议),本期接受 openevolve 自己的反思机制,不强行套 GEPA reflection signature。**反思 feedback 写入 openevolve trajectory log + 本地 metrics.json append-only**,供人工事后审计。

### D2 目标组件选型 — ansi_strip.py + 20/10 stratified holdout

- **D-06:** **PoC 组件 = `~/.hermes/hermes-agent/tools/ansi_strip.py`**。44 行纯算法 (CSI / SGR / OSC 三类 ANSI 转义序列去除),hermes-agent 自带 30 个 pytest 覆盖 (`tests/tools/test_ansi_strip.py`),零安全敏感路径 (不碰 auth / sandbox / 凭证 / 用户文件),零 hermes-agent runtime 依赖耦合 (函数调用边界清晰,IO-free)。这是 FEATURES "ONE code component evolvable" 的最稳 PoC,不过度交付。
- **D-07:** **测试切分 = 20/10 stratified + 5-10 手补 holdout edge case**。stratify dimension = 转义类型 (CSI / SGR / OSC 三桶);seed 固定 (`code_evolution_seed = 42`);**handle case**:hermes-agent 测试可能不严格分类,planner 用 AST `pytest.mark.parametrize` 名字 + docstring 关键词 (CSI / color / cursor / OSC) 自动桶化,buckets 不均时 round-robin 补齐确保 holdout 至少每桶 1 个。**手补 5-10 个 edge case** 写在 evolution 仓内 `tests/code/test_ansi_strip_holdout.py` (项目内,**不**入 hermes-agent),覆盖:超长输入 (>10K chars)、Unicode 边界、嵌套 / 重叠转义、空字符串 / 单字符、CSI 中断、未知 OSC、混合无效字节、CRLF 处理。
- **D-08:** **测试发现走 AST + 静态扫描** (不在主 evolve_code 流程 exec 真实测试代码):`code_target_loader` 读 `~/.hermes/hermes-agent/tests/tools/test_ansi_strip.py`,用 `ast.parse` 收集所有顶层 `def test_*` 函数体 + `@pytest.mark.parametrize` 装饰器参数 (id 列表 + values),生成结构化 test_manifest.json (用于 stratify 计算 + holdout 切分)。**Risk anchor**:hermes-agent 升级测试文件结构变化,planner 在 manifest 加 schema_version + `hermes_agent_commit` 字段,加载时校验对齐。
- **D-09:** **测试运行环境**:每个 candidate 评分都建一个隔离 working dir `~/.hermes/tmp/code_eval_<ts>_<candidate_id>/`,**copy** hermes-agent 的相关测试文件 + `tools/__init__.py` shim + 该 candidate 的 evolved `ansi_strip.py`,然后 `subprocess.run([sys.executable, "-m", "pytest", str(test_dir), "-x", "--tb=line", "-q", "--json-report"], timeout=120, cwd=eval_dir)`。**关键**:**不在真实 `~/.hermes/hermes-agent/` 里跑测试** (即不污染原仓);**不复制整个 hermes-agent** (几百 MB,太重) — 只复制需要的 import 闭包文件 (即 `tools/ansi_strip.py` 本体的依赖,planner spike 验证 ansi_strip.py 的 import 闭包通常为空)。
- **D-10:** **Baseline 跑一次,缓存到磁盘**。`code_evolve --component ansi_strip.py` 启动时跑 baseline (untouched ansi_strip.py × 30 tests) → `output/code/<ts>/baseline_metrics.json`。`baseline_size_bytes` 用于 D-13 size penalty 比较;`baseline_pytest_passed = 30` 用于 holdout regression assertion。每次 evolve 时 commit hash 匹配则**命中缓存**,否则重 baseline (因为 hermes-agent 升级可能影响 baseline)。

### D3 适应度函数形状 — pytest + size + ruff (无 LLM judge)

- **D-11:** **三段评分,pytest 二进制硬门 + size + ruff**:
  ```python
  composite_fitness = (
      pytest_score * 0.80    # pytest_pass / pytest_total;pytest_pass<total 时 composite=0 直接 reject (硬门)
      + size_component * 0.10
      + ruff_score * 0.10
  )
  ```
  pytest 不全过 → `composite = 0, decision = "reject"` 直接淘汰,**不**降级到 0.x soft score,**不**给 GEPA "几乎全过" 误导。**理由**:PITFALLS "Code is binary correct/incorrect; LLM-as-judge invites flaky scoring";二进制门让 fitness landscape 清晰,GEPA 反思能定位真正 fail 的 test。
- **D-12:** **size_component 设计**:
  ```python
  ratio = evolved_size_bytes / baseline_size_bytes
  if ratio <= 1.0:
      size_component = 1.0   # 缩小或持平,满分
  elif ratio <= 1.2:
      size_component = 1.0 - (ratio - 1.0) * 1.5   # 1.0 → 0.7 线性下降
  elif ratio <= 1.5:
      size_component = 0.7 - (ratio - 1.2) * (0.7 / 0.3)   # 0.7 → 0.0 线性下降
  else:
      size_component = 0.0
      decision = "reject"   # >×1.5 直接 reject,作为第二个硬门
  ```
  **理由**:进化容易膨胀代码 (FEATURES "penalize bloat");硬上界 ×1.5 保护组件不被改成大杂烩。
- **D-13:** **ruff_score 设计**:`subprocess.run(["ruff", "check", "--output-format=json", str(evolved_file)], timeout=10)`,解析 violations count。映射:0 violations → 1.0;1-2 → 0.7;3-5 → 0.4;6-10 → 0.1;>10 → 0.0。**理由**:Phase 21 不要求代码"漂亮",但严重 lint smell (e.g. `bare except`、`unused imports`) 是 GEPA 的可纠正信号。**实现细节**:evolution 仓自带 ruff config (默认 `--select E,F,W` 即可,不要 plugin 大全;ruff 已经是常见 Python 工程依赖,planner 加到 `[dev]` extra 或检查是否已存在)。
- **D-14:** **无 LLM-as-judge 评分**。PITFALLS 7 / 12 + FEATURES anti-feature 表 "LLM-graded fitness on code evolution → Pytest pass rate as primary gate; LLM only for code-quality nudges" — **本期连 nudge 也不开**。理由:Phase 21 是 PoC,先验证"二进制 pytest 门 + 结构化指标"是否够用;LLM judge 留待未来 phase 视情况引入 (deferred,见 deferred 区)。
- **D-15:** **Holdout gate**:evolve 循环结束选出 best candidate 后,**单独**跑一遍 holdout (10 + 5-10 edge case = 15-20 tests),holdout pytest 必须 100% 过 + size_component ≥ 0.7 + ruff_score ≥ 0.4,**全过才进 output/code/<ts>/**;任一不过则该 evolve 失败,写 `output/code/FAILED_<ts>/` (与 v1 三个 evolve_* 同 FAILED 路径),metrics.json 写 reason。
- **D-16:** **GEPA-like reflection feedback 内容**:每个 candidate 评分时 feedback 字典字段 = `{"pytest_failures": [test_name + assertion_error_msg ×N], "size_ratio": float, "ruff_violations": [rule_id + message ×N], "composite_fitness": float, "decision": "accept|reject", "reject_reason": str}`。openevolve 拿到这个 feedback 作为下一轮 mutation prompt 的 context,引导 LLM 优先修真正 fail 的 test。

### D4 许可证 & 安全脚手架范围 — 本期一次性全做

- **D-17:** **`LICENSE` 文件落仓根 (MIT)**,**本期内、Phase 21 第一个 plan 之前完成**。PITFALLS "Phase 21 darwinian: Often missing → LICENSE.md at repo root. Verify: LICENSE file present BEFORE Phase 21 work begins" — 这是不可逆决策,不能拖。MIT 文本含项目名 `hermes-agent-self-evolution`、版权人 (用户自填,planner 留 `<COPYRIGHT_HOLDER>` placeholder)、年份 2026。
- **D-18:** **CI lint gate 校验单点 import 边界**:
  - **pre-commit hook** (`.pre-commit-config.yaml` 加 `local` hook) + **pytest 测试** (`tests/code/test_import_boundary.py`) 双层防御。
  - 实现:`grep -rn "^import openevolve\|^from openevolve" evolution/ --include="*.py" --exclude-dir=__pycache__ | grep -v "evolution/code/code_evolver_adapter.py"` 若有输出则 fail。
  - pytest 测试用 `pathlib.Path` 直读源文件正则匹配,不 import openevolve 本身 (允许在 openevolve 未安装的纯 dev 环境通过)。
  - **理由**:这个 phase 营造"单点 import 面"架构习惯,未来 phase 引入别的 evolver / 大库都按此 pattern 走,机械化护栏好过文档约定。
- **D-19:** **`output/code/<ts>/NOTICE.md`**(每次 evolve 都生成):
  ```markdown
  # NOTICE — LLM-generated code
  This code was generated by openevolve via Phase 21 darwinian-code-evolution pipeline.
  
  - Source library: openevolve >=0.2.27 (Apache-2.0)
  - Target: hermes-agent/<component_path>
  - Generated: <timestamp>
  - Status: UNREVIEWED — DO NOT MERGE WITHOUT HUMAN REVIEW
  - Fitness: pytest <P>/<T>, size_component <S>, ruff_score <R>, composite <C>
  - Holdout: pytest <HP>/<HT> (status: <pass|fail>)
  
  Per project policy (PROJECT.md), evolved artifacts are output-only.
  Auto-merge is explicitly out of scope.
  ```
  落盘时机:evolve 成功时 (gate 全过) 写到 `output/code/<ts>/NOTICE.md`;gate 不过时写到 `output/code/FAILED_<ts>/NOTICE.md` 含 reject_reason。
- **D-20:** **Candidate 评分沙箱**:每个 candidate 跑 pytest 时走 subprocess + timeout (D-09 已定),**关键加固**:
  - `subprocess.run([sys.executable, "-m", "pytest", ...], cwd=eval_dir, env=restricted_env, timeout=120)`
  - `restricted_env` = 父进程 env minus `OPENAI_API_KEY` / `OPENROUTER_API_KEY` / `DASHSCOPE_KEY` / `EVOLUTION_API_KEY` 等所有 API 凭证 + `HERMES_AGENT_REPO=<isolated>` (即指向 eval_dir 而不是真实 hermes-agent)
  - eval_dir 在 `~/.hermes/tmp/code_eval_<run_ts>_<candidate_id>/`,evolve 结束统一清理 (失败也清理,只保留 `output/code/<ts>/` 永久产物)
  - timeout 触发 → SIGTERM → SIGKILL fallback;timeout-killed candidate 视为 fitness=0,decision="reject",reason="timeout"
  - **不**用 docker / firejail 等更强 sandbox (PoC 阶段,subprocess + env 削减 + timeout 已够;若未来 Phase 22 自动 loop 需更强隔离再升级)
- **D-21:** **`evolution/code/LICENSING.md`** 文档说明 phase 内 boundary:openevolve Apache-2.0 是单点 import 唯一引入,本目录其他文件无 AGPL 风险,output/code/ 产物按本项目 MIT 出。planner 直接照写这一段。

### Claude's Discretion

- openevolve 具体的 evolutionary loop 参数 (population_size / archive_size / mutation_temperature / max_generations) — planner 读 openevolve docs 后给一个保守 PoC 默认 (例:pop=10, archive=5, gens=20, max_metric_calls=300),允许 CLI flag 覆盖
- `code_target_loader.find_target_tests` 的 AST 解析具体实现 (`ast.walk` 还是 `ast.NodeVisitor` 子类) — planner 自决
- `ruff_score` 三段映射的精确分位 (1-2 → 0.7 vs 0.8;3-5 → 0.4 vs 0.5) — 允许 ±0.1 调,记 `EvolutionConfig.ruff_score_buckets` 字段
- `size_component` 的 ratio 阈值 (×1.2 / ×1.5) — D-12 给的是研究启发值,允许 planner 在 baseline 跑后实测调 (e.g. 若 baseline 44 行 ×1.2 = 53 行已经偏紧,planner 可松到 ×1.3)
- `eval_dir` 命名与清理时机 (用 `tempfile.TemporaryDirectory` context manager 还是手动 `shutil.rmtree`)
- openevolve native client 的具体 SDK (`openai.OpenAI` vs `litellm.completion` vs openevolve 内置 wrapper) — planner spike Task 1 验证后定
- holdout 5-10 edge case 测试的具体内容 (planner 读 ansi_strip.py 源码 + 30 个现有测试后,补真实 gap 而非凭空想)
- `metrics.json` 字段命名是否走"openevolve_*" 前缀 (与 Phase 16 dashboard "benchmark_*" 前缀风格对齐) — planner 决,推荐 `code_*` 前缀避免误锁定 evolver 选型
- `LICENSE` 版权人 (项目用户名 / 组织名) — planner 用 git config user.name 默认填,提交时人工 review

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 项目规划文档 (必读)
- `.planning/REQUIREMENTS.md` §V2-CODE-01 line 91 — Phase 21 需求来源 ("Darwinian code evolution — at least one hermes-agent code component evolvable")
- `.planning/ROADMAP.md` §Phase 21 lines 392-400 — 三条成功标准 (darwinian-evolver integrated and tested / at least one component evolvable / fitness combines tests + quality)。**注意**:goal 仍写 "Integrate darwinian-evolver",研究 SUMMARY §1 已替换为 openevolve,planner 在 PLAN 第一段说明这一替换,但**不**改 ROADMAP.md (treat ROADMAP as historical intent, CONTEXT as live decision)
- `.planning/PROJECT.md` §Constraints / §Out of Scope / §Active line 47 — V2-CODE-01 pending;约束 (hermes-agent 只读 / Size / Architecture / Dependency 复用)
- `.planning/STATE.md` — Phase 20 deferred status;Phase 21 next

### 研究与约束 (载荷决策的根源)
- `.planning/research/SUMMARY.md` §1 (lines 14-23) — **本期最高杠杆发现**:darwinian-evolver 不存在 → openevolve 替换 → AGPL 边界彻底消解。Action 列表中"Phase 21 substrate = openevolve" 已是 Key Decision
- `.planning/research/SUMMARY.md` §"Cross-Cutting Decisions" #1 line 80 — Phase 21 substrate 决策点
- `.planning/research/SUMMARY.md` §"Phase 21 substrate" line 149 — openevolve API surface 验证 in first plan iteration
- `.planning/research/PITFALLS.md` §Pitfall 3 (lines 87-121) — AGPL contamination;openevolve 选择已 defuse,但 PITFALLS 列的 5 条 prevention 中 "single import surface" "CI grep gate" "LICENSE.md prerequisite" 仍逐条对应本期 D-03 / D-18 / D-17
- `.planning/research/PITFALLS.md` §"Looks Done But Isn't" lines 492-493 — Phase 21 两大经典遗漏 (CI lint gate + LICENSE.md);本期 D-17 / D-18 直接闭环
- `.planning/research/PITFALLS.md` §Anti-Feature §"LLM-graded fitness on code evolution" line 427 — 直接对应 D-14 (no LLM judge)
- `.planning/research/PITFALLS.md` §Anti-Feature §"Recursive self-evolution" line 424 — Phase 21 必须硬 exclude `evolution/`
- `.planning/research/FEATURES.md` §V2-CODE-01 (lines 330-372) — Phase 21 完整 feature spec:behavior table、value proposition、scope boundary、reference implementations、anti-feature risks
- `.planning/research/FEATURES.md` §"Anti-Features hidden inside other features" lines 424-427 — recursive / security-critical / LLM-graded 三大坑
- `.planning/research/FEATURES.md` line 466 — Phase 21 → all gating phases (16, 18, 20) 依赖路径已成立 (16/18/20 均已 ship 至少 code-level)
- `.planning/research/STACK.md` §"Phase 21 BLOCKER" lines 81-105 — 本期最关键的 stack 决策来源 (替换 darwinian-evolver → openevolve, drop `[darwinian]` extra → add `[code]` extra)
- `.planning/research/STACK.md` §"AGPL Boundary Concerns" lines 107-119 — 一般指南,Phase 21 选 openevolve 后多数条款不触发
- `.planning/research/ARCHITECTURE.md` §3.9 Phase 21 (lines 159-173) — 包结构定义 (`evolution/code/{__init__.py, code_target_loader.py, code_fitness.py, evolve_code.py, code_evolver_adapter.py, LICENSING.md}`)。本期 D-01..D-21 完全沿用 + 新增 `sandbox_runner.py`
- `.planning/research/ARCHITECTURE.md` §6 "AGPL/License Isolation" lines 260-275 — 6 层 isolation 模型 (本期 #4 subprocess 弃用 / #1-3+5-6 全用)

### 直接前置 CONTEXT (强相关 — 模式直接复用)
- `.planning/phases/20-benchmark-gated-validation/20-CONTEXT.md` §D-09/D-10/D-11/D-12 — Virtual Prompt Overlay + subprocess + Async Stream Pipe + heartbeat。**Phase 21 sandbox_runner 是 Phase 20 TBLiteRunner 的精神同构**:subprocess + timeout + isolated env + 状态 monitor。planner 把 TBLiteRunner 当结构模板
- `.planning/phases/20-benchmark-gated-validation/20-CONTEXT.md` §D-04 FAILED_<ts>/ + 决策落 report json — Phase 21 评分失败路径同构
- `.planning/phases/18-personality-drift-detection/18-CONTEXT.md` §D-CAL-01/D-BYPASS-01..02 — Phase 21 不复用其 calibration 模板,但 "无 bypass flag" "fail-closed" "结构化 metrics.json" 思路相同
- `.planning/phases/13-per-parameter-description-optimization/13-CONTEXT.md` — `CostTracker` / `max_cost_usd` / `--allow-miprov2-fallback` 模式;Phase 21 CLI flags 沿用 (虽然 21 不走 MIPROv2,但保留 `--allow-fallback` 以备 openevolve 不可用时降级到 self-rolled DSPy loop 的未来扩展)

### Phase 21 实现锚点 (planner / executor 必读)
- **evolution 项目侧**:
  - `evolution/skills/skill_module.py` — DSPy Module wrapper 模板 (虽然 21 不走 DSPy,但 "把外部资产包成可优化对象" 思路同)
  - `evolution/skills/evolve_skill.py` (CLI shell) — Click + Rich + EvolutionConfig.load 三件套模板,**注意 H1/H3 (CONCERNS.md)**:skill CLI 仍用 OLD GEPA API 且未走多模型后端,Phase 21 evolve_code.py **必须**用 `EvolutionConfig.load(...)` + 5-param signature 模式 (虽然 21 不直接调 GEPA,LLM 调用配置仍走完整链)
  - `evolution/tools/evolve_tool_descriptions.py` (lines 1-100) — 多模型后端 (`config.get_lm_kwargs()`) 与 CLI flag 设计的 canonical pattern;Phase 21 沿用
  - `evolution/prompts/evolve_prompt_sections.py` §step 10/11 (lines ~1000-1100) — output 目录拓扑、metrics.json 写、FAILED_<ts>/ 路径
  - `evolution/benchmarks/tblite_runner.py` — **sandbox_runner.py 的直接结构模板** (subprocess.Popen + 流式 stdout/stderr + state monitor + heartbeat;Phase 21 简化版即可,不需 heartbeat)
  - `evolution/benchmarks/benchmark_gate.py` — `TBLiteBenchmarkGate.check` 接口 → Phase 21 `code_fitness.score_candidate` 同构 (输入 candidate, 输出 dataclass + decision)
  - `evolution/core/config.py` (lines 30-65) — `EvolutionConfig.load` 多层级配置链;Phase 21 新增 `code_target_*` 字段 (sandbox_timeout_sec, ruff_score_buckets 等),沿用同模式
  - `evolution/core/constraints.py` — `ConstraintResult` dataclass + ConstraintValidator;Phase 21 size_constraint / ruff_constraint 沿用
  - `evolution/core/cost_tracker.py` — `CostTracker`;openevolve LLM 调用累加 cost,**Phase 21 默认 max_cost_usd = 5.0** (PoC 阶段控制成本,planner 在 EvolutionConfig 暴露字段)
  - `pyproject.toml` (existing `[project.optional-dependencies]`) — 现存 `darwinian = ["darwinian-evolver"]` 必须**删除并替换**为 `code = ["openevolve>=0.2.27"]`
  - `.gitignore` — 检查 `output/` 是否已纳入 (CONCERNS H4),Phase 21 写 output/code/ 前确认;若未纳入,planner 加 `output/` + `!output/.gitkeep` 一并落
- **hermes-agent 侧**:
  - `~/.hermes/hermes-agent/tools/ansi_strip.py` — PoC 目标文件 (44 行,纯算法)。planner Task 1 spike:读源码确认 import 闭包 (应为空) + 验证 D-08 AST 测试发现可行
  - `~/.hermes/hermes-agent/tests/tools/test_ansi_strip.py` — 30 pytest (168 行)。planner Task 1 spike:跑一次,确认无外部 fixture 依赖、可在 isolated dir 独立运行
  - `~/.hermes/hermes-agent/conftest.py` (若存在) — 检查 root conftest 是否注入 fixtures,若有,Phase 21 sandbox 需要 copy 必要 conftest 进 eval_dir
- **新建文件锚点 (本期 deliver)**:
  - `evolution/code/__init__.py` — lazy ImportError guard (openevolve 未安装时 `import evolution.code` 不 crash,只在 `evolve_code` 入口 fail)
  - `evolution/code/code_target_loader.py` — `CodeTarget` dataclass + `find_target_tests` (AST 解析 hermes-agent tests/)
  - `evolution/code/code_fitness.py` — `CodeFitness` dataclass + `score_candidate(target, evolved_path, eval_dir) -> CodeFitness` (D-11..D-15)
  - `evolution/code/code_evolver_adapter.py` — **唯一** `import openevolve` 的文件 (D-03)
  - `evolution/code/sandbox_runner.py` — subprocess + timeout + restricted_env + eval_dir 隔离 (D-09 / D-20)
  - `evolution/code/evolve_code.py` — Click CLI 入口 (D-21 整合 + EvolutionConfig.load)
  - `evolution/code/LICENSING.md` — phase 内 boundary 文档 (D-21)
  - `LICENSE` 在仓根 — MIT (D-17)
  - `.pre-commit-config.yaml` — local hook 校验 D-18 grep gate;若仓里没有 `.pre-commit-config.yaml`,planner 新建 + 仅这一个 hook
  - `tests/code/__init__.py`
  - `tests/code/test_import_boundary.py` (D-18 pytest 双层防御)
  - `tests/code/test_code_target_loader.py`
  - `tests/code/test_code_fitness.py`
  - `tests/code/test_sandbox_runner.py`
  - `tests/code/test_evolve_code_cli.py`
  - `tests/code/test_ansi_strip_holdout.py` — 5-10 edge case (D-07,**在 evolution 仓内**,不入 hermes-agent)
  - `output/code/.gitkeep` (若 output/ 未 gitignored 则需此目录占位 stub)

### 外部依赖
- `openevolve >= 0.2.27` (Apache-2.0) — 唯一新 runtime dep,放 `[project.optional-dependencies] code`
- `ruff` (已是 dev 工具链 / 项目可能已隐式存在;planner 检查后决定显式加 `[dev]` 还是允许 `pip install ruff` 隐式) — D-13 ruff_score 计算需要
- `subprocess` / `tempfile` / `shutil` / `ast` / `json` (全部 stdlib) — sandbox_runner / target_loader / fitness 核心

### 安全/合规参考
- `.planning/codebase/CONCERNS.md` §M6 — hermes-agent Read-Only Not Enforced。Phase 21 是项目里**首个**完全 output-only 不碰 hermes-agent 的 phase (TBLite Phase 20 有 Virtual Prompt Overlay,Phase 21 没有),反而是 §M6 的良好遵循样板
- `.planning/codebase/CONCERNS.md` §H4 — `output/` not in `.gitignore`。Phase 21 写 output/code/ 之前必须确认 .gitignore 已纳 `output/` (若 Phase 20 已修复则跳过;若未修,planner Wave 0 加进去)
- `.planning/codebase/CONCERNS.md` §H1 — `evolve_skill.py` Old GEPA API + 3-param metric → silent MIPROv2 fallback。Phase 21 evolve_code.py **不**复用 evolve_skill.py 模板,改用 evolve_tool_descriptions.py (line 184-190) + evolve_prompt_sections.py 的 5-param signature 模式

### openevolve 上游参考 (planner Task 1 spike 验证后写入 PLAN.md)
- https://pypi.org/project/openevolve/ — PyPI 主页,版本 / docs URL
- openevolve 的 LLM client 接口 (是否接受 base_url override / 是否自带 OpenAI-compatible / 是否需要 anthropic-style)
- openevolve 的 fitness function 接入接口 (callable + return type)
- openevolve 的 population / archive / diversity 默认参数与可调点
- openevolve 的输出格式 (best candidate 怎么取 / trajectory log 怎么读 / 反思 feedback 怎么传)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `evolution/benchmarks/tblite_runner.py` `TBLiteRunner` 类 — `sandbox_runner.py` 直接结构模板 (subprocess + Popen + state monitor;Phase 21 简化:无 heartbeat 因 candidate eval 是短任务)
- `evolution/benchmarks/benchmark_gate.py` `TBLiteBenchmarkGate.check` 接口 — `code_fitness.score_candidate` 同构 (输入 candidate, 输出 dataclass)
- `evolution/core/cost_tracker.py` `CostTracker` context manager — openevolve LLM 调用累加 cost
- `evolution/core/config.py` `EvolutionConfig.load` 多层级配置链 — Phase 21 新增字段沿用同链路
- `evolution/core/constraints.py` `ConstraintResult` dataclass — size_constraint / ruff_constraint 沿用
- `evolution/tools/evolve_tool_descriptions.py` Click CLI 三件套 (Click + Rich + EvolutionConfig.load + 5-param signature) — evolve_code.py 直接模板
- `evolution/prompts/evolve_prompt_sections.py` step 10/11 FAILED_<ts>/ + Rich Table summary — evolve_code 失败路径 + 终端报告同模式
- `evolution/core/external_importers.py` `_contains_secret` — 写 output/code/<ts>/NOTICE.md 前过滤 LLM mutation 反馈中可能泄漏的 token

### Established Patterns
- 单点 facade pattern (Phase 20 `TBLiteBenchmarkGate` 包 TBLite subprocess) — Phase 21 `code_evolver_adapter` 包 openevolve
- 5-param GEPA signature + reflection_lm 走多模型后端 (Phase 13/14/17/18/19/20 已立) — Phase 21 LLM 调用配置值复用 EvolutionConfig.optimizer_model / api_base / api_key (D-04)
- FAILED_<ts>/ + ABORTED_<ts>/ + 成功 <ts>/ 三套输出拓扑 (Phase 13/14/17/18/19/20 同) — Phase 21 沿用,新增 NOTICE.md 同目录
- 数据集/校准产物落 `datasets/<domain>/*.json` + .gitignore 例外 (Phase 18 D-CAL-02 / Phase 20 D-13) — Phase 21 holdout edge case test 走 `tests/code/test_ansi_strip_holdout.py` (代码非数据,直接 git 跟踪,不走 .gitignore 例外路径)
- Pre-flight validation hard fail (Phase 18 D-CAL-05 / Phase 20 D-10/D-14) — Phase 21 evolve_code 启动时 pre-flight 检查:openevolve 已安装 / hermes-agent 路径有效 / 目标文件存在 / 测试文件可解析 / output/ 在 .gitignore (任一 fail 即 SystemExit(1))

### Integration Points
- `evolve_code --component=ansi_strip.py --iterations=20 --hermes-repo=~/.hermes/hermes-agent` →
  1. pre-flight (openevolve 装好 / 目标文件存在 / .gitignore 含 output/ / LICENSE 存在 / CI lint hook 装好) →
  2. EvolutionConfig.load(...) →
  3. CodeTarget = load_target("ansi_strip.py") →
  4. test_manifest = find_target_tests(target) + stratify 切 20/10 + 合并 holdout edge case →
  5. baseline_metrics = score_candidate(target.original_path, target.train_tests + target.holdout_tests) →
  6. code_evolver_adapter.evolve(target, train_tests, fitness_fn=score_candidate, max_iterations, max_cost) → best_candidate
  7. holdout_metrics = score_candidate(best_candidate.evolved_path, target.holdout_tests + edge_case_tests)
  8. accept (holdout pass + size + ruff 全过) → output/code/<ts>/ + NOTICE.md + metrics.json
  9. reject (任一 fail) → output/code/FAILED_<ts>/ + NOTICE.md + metrics.json (含 reject_reason)
- `pre-commit run` + `pytest tests/code/test_import_boundary.py` → grep gate 校验 `import openevolve` 边界
- `pip install .[code]` → 安装 openevolve;默认 `pip install -e .` 不触发

### Risk Anchors (Pre-execution)
- **openevolve LLM client 接口与 evolution.yaml 配置的 shim 复杂度**:planner Task 1 spike 必须验证 — 若 openevolve 不接受 base_url override (e.g. 硬编码 `openai.OpenAI()`),adapter 需 monkey-patch 或包一层 fake OpenAI client。最坏情形:openevolve 上游不支持自定义 endpoint,Phase 21 退化到只用 OpenAI 官方 API (此时 D-04 标注"短期退化:仅 OPENAI_API_KEY",改 EvolutionConfig 文档)
- **hermes-agent pytest 在 isolated dir 跑通的可行性**:planner Task 1 spike — 复制 ansi_strip.py + test_ansi_strip.py 到 tmp dir,运行 `pytest test_ansi_strip.py` 看 conftest 依赖是否爆。若爆,需扩展 D-09 (copy 更多文件) 或换组件 (binary_extensions.py 备选,虽然测试更少)
- **size_penalty 阈值在 44-行小文件上是否合理**:×1.2 = 53 行已经偏紧 (一两个 docstring 修复都可能越界)。planner 在 Task 1 baseline 跑后实测调,允许 D-12 阈值放宽 (×1.3 / ×1.6)
- **ruff config 缺失时的退化**:若 evolution 仓没有 ruff config,`ruff check` 用全默认规则可能过严。planner 在 evolution 仓加最小 `ruff.toml`:`select = ["E", "F", "W"]` + `line-length = 120`,避免本期被无关规则干扰
- **openevolve 默认 LLM model**:openevolve 若不读 EvolutionConfig.optimizer_model 而自带默认 (e.g. gpt-4),用户配置的 qwen/dashscope 会被绕过 → cost 失控。adapter 必须把 model 名注入 openevolve config 调用,planner 在 PLAN 第一段写明 verify
- **candidate 评分进程的隐式 hermes-agent import**:若 evolved ansi_strip.py 意外 `from hermes.agent import ...`,subprocess 会拉一长串依赖。planner 在 sandbox_runner 加 `PYTHONPATH` 限制 (只允许 eval_dir + stdlib),禁止跨界 import
- **CONCERNS.md M6 (read-only) 重新评估**:Phase 21 是项目里第一个**纯 output-only** 不碰 hermes-agent 真实文件的 phase (与 Phase 20 D-09 Virtual Prompt Overlay 不同),反而是 §M6 修复的样板;planner 可在 PLAN 提及"Phase 21 不引入新的 hermes-agent 写路径"
- **LICENSE.md 版权人占位符的运营约束**:planner 用 git config user.name 默认填,但 PR 时**人工** review 必须确认 (这是不可逆决策)。executor checkpoint:LICENSE 提交前一定 AskUserQuestion 确认版权人

</code_context>

<specifics>
## Specific Ideas

### Fitness Composition (D-11..D-15 精确公式)
```python
@dataclass
class CodeFitness:
    pytest_passed: int
    pytest_total: int
    size_baseline_bytes: int
    size_evolved_bytes: int
    ruff_violations: int
    pytest_score: float       # 0/1 hard binary
    size_component: float     # 0..1 (D-12 三段映射)
    ruff_score: float         # 0..1 (D-13 三段映射)
    composite: float          # 0..1
    decision: str             # "accept" | "reject"
    reject_reason: str        # "pytest_fail:test_x" | "size_oversize:1.57x" | "ruff_oversize" | ""
    pytest_failures: list[dict]   # [{test_name, assertion_msg, traceback_one_line}, ...] for feedback to GEPA
    ruff_findings: list[dict]     # [{rule_id, message, line}, ...]

def score_candidate(target, evolved_path, eval_dir, baseline_size) -> CodeFitness:
    pytest_passed, pytest_total, failures = _run_pytest_in_sandbox(evolved_path, eval_dir)
    if pytest_passed < pytest_total:
        return CodeFitness(..., pytest_score=0.0, composite=0.0, decision="reject", reject_reason=f"pytest_fail:{failures[0]['test_name']}")
    size_evolved = evolved_path.stat().st_size
    ratio = size_evolved / baseline_size
    if ratio > 1.5:
        return CodeFitness(..., decision="reject", reject_reason=f"size_oversize:{ratio:.2f}x")
    size_component = _size_to_component(ratio)
    ruff_violations, ruff_findings = _run_ruff(evolved_path)
    ruff_score = _ruff_to_score(ruff_violations)
    composite = 0.80 * 1.0 + 0.10 * size_component + 0.10 * ruff_score
    return CodeFitness(..., composite=composite, decision="accept", ...)
```

### Stratified holdout split (D-07)
```python
STRATIFY_BUCKETS = ["csi", "sgr", "osc", "other"]
HOLDOUT_PER_BUCKET = {"csi": 4, "sgr": 3, "osc": 2, "other": 1}   # 总 10
EDGE_CASE_HOLDOUT_TESTS = [
    "test_extreme_long_input_10k_chars",
    "test_unicode_boundary_in_escape",
    "test_nested_escape_sequences",
    "test_overlapping_escapes",
    "test_empty_string",
    "test_single_char",
    "test_truncated_csi_at_eof",
    "test_unknown_osc_command",
    "test_mixed_invalid_bytes",
    "test_crlf_inside_escape",
]  # 共 10 个手补 holdout
```

### NOTICE.md template (D-19)
见上方 D-19 决策中的代码块。planner 用 Python f-string + dataclass 渲染。

### CI lint gate 实现 (D-18)
```bash
# .pre-commit-config.yaml local hook
- id: openevolve-single-import-surface
  name: Block openevolve import outside code_evolver_adapter
  entry: bash -c 'grep -rn "^import openevolve\|^from openevolve" evolution/ --include="*.py" --exclude-dir=__pycache__ | grep -v "evolution/code/code_evolver_adapter.py" && exit 1 || exit 0'
  language: system
  pass_filenames: false
  always_run: true
```
+ 等价的 pytest 测试 (`tests/code/test_import_boundary.py`),不依赖 openevolve 安装。

### CLI signature (D-21 + D-04)
```bash
python -m evolution.code.evolve_code \
  --component tools/ansi_strip.py \
  --iterations 20 \
  --max-cost 5.0 \
  --hermes-repo ~/.hermes/hermes-agent \
  --model qwen-plus \
  --api-base https://dashscope.aliyuncs.com/compatible-mode/v1 \
  --dry-run                       # 只 pre-flight + baseline,不跑 evolve
  --allow-fallback                # 未来若 openevolve 不可用降级到 self-rolled DSPy loop (本期仅占位,不实做 fallback path)
```

### Pre-flight check 顺序 (D-22 同 D-10 思路)
1. `evolution/code/code_evolver_adapter.py` `import openevolve` 成功
2. `~/.hermes/hermes-agent/tools/ansi_strip.py` 存在 & 可读
3. `~/.hermes/hermes-agent/tests/tools/test_ansi_strip.py` 存在 & AST 解析成功
4. `.gitignore` 含 `output/` (失败 → 引导用户运行修复命令)
5. `LICENSE` 在 repo root 存在 & 非空 (失败 → SystemExit(1) 说明 Phase 21 prerequisite)
6. `.pre-commit-config.yaml` 包含 `openevolve-single-import-surface` hook (失败 → warn,不阻塞)
7. EvolutionConfig.load 三层后端 (yaml / env / CLI) 解析成功 + api_key 非空

任一失败 → `raise SystemExit(1)` + 明确错误信息。

### Test fixture 设计 (mock openevolve)
sandbox_runner / code_fitness / code_target_loader 单测都不需要真 openevolve;evolve_code CLI 端到端测试用 `unittest.mock.patch("evolution.code.code_evolver_adapter.evolve")` 替换为返回 deterministic candidate。这样 CI 跑 tests/code/ 不需要 openevolve 已安装。

</specifics>

<deferred>
## Deferred Ideas

- **多组件批量进化** — 本期 PoC 单文件;未来可拓 `evolve_code --component tool_registry --recursive` 或 `--components a.py,b.py,c.py`,加 cross-component fitness。Phase 23+ 候选。
- **LLM-as-judge code quality nudge (0.1 权重)** — FEATURES anti-feature 表已警告,本期不引入;若未来发现 ruff + pytest 不足以拉出可读性优化方向,可在新 phase 加 ≤0.1 权重的 LLM nudge,带 dedicated calibration set (类似 Phase 18 D-CAL-01 calibration 模式)
- **Property-based / fuzzing holdout** (Hypothesis / atheris) — 本期手补 10 个 edge case 即可,property-based 留到组件复杂度升级后引入
- **Modal / firejail / docker sandbox** — subprocess + restricted_env + timeout 在 PoC 足够;若 Phase 22 自动 loop 需更强隔离 (e.g. evolved 代码可能误删文件),再升级到 docker
- **CodeMetric 抽象 + 多 evolver plugin 注册中心** — 与项目"先实做后抽象"风格违和;若有第二个 evolver 候选 (e.g. AlphaEvolve / self-rolled DSPy loop) 出现,再抽象
- **evolved 代码自动 PR / 自动 merge** — PROJECT.md Out-of-Scope 永久排除;Phase 22 持续 loop 做 PR 生成,但仍需人工 review
- **Recursive self-evolution (evolve evolution/ 自己)** — FEATURES anti-feature,**永久** out-of-scope
- **安全敏感组件演化** (agent/redact.py / auth / sandbox / 凭证) — FEATURES 硬限,**不在任何 phase 内** evolve;若未来真要碰,先独立 phase 设计审计 / approval / rollback 全套
- **darwinian-evolver / AGPL 隔离基础设施** (`.venv-agpl/` / 进程边界 / subprocess shim) — openevolve 决策已 defuse,**永久** 不需要建。若未来真有 AGPL 包不可避免,新 phase 设计
- **cross-run 历史 metrics 持久化 (历次 evolve 趋势)** — 与 Phase 16 dashboard 相关,Phase 21 metrics.json 一次性产物,不入 dashboard;若 Phase 22 需要趋势,在 Phase 16 dashboard 加 code_* 前缀分桶
- **`--allow-fallback` 真实降级路径** (self-rolled DSPy+GEPA code loop) — 本期 CLI flag 占位但不实做,留 openevolve 出大问题时再启用
- **多语言代码进化** (TypeScript / Rust / Go) — 本期 Python only;hermes-agent 主要是 Python,需求触发再开 phase
- **ROADMAP.md goal text 与 CONTEXT.md 替换说明同步** — 本期 CONTEXT 已明确 openevolve 替换,ROADMAP "Integrate darwinian-evolver" 字面表述保留为历史 intent;若未来 PROJECT.md 全面 review,统一改 (Phase 22 prep / milestone cleanup 候选)

### Reviewed Todos (not folded)

- **`.planning/todos/pending/2026-05-07-enforce-readonly-hermes-agent.md`** — Phase 21 与 §M6 反向:本 phase 不写 hermes-agent (output/ only),不加剧 §M6;deploy_mode 全局化仍属 Phase 22 / 独立 hygiene phase scope。
- **`.planning/todos/pending/2026-05-07-add-lockfile-dspy-pin.md`** — Phase 21 引入 openevolve 后,lockfile 缺失风险上升一阶。但完整 lockfile (uv/poetry) 是独立工程任务,留独立 hygiene phase。
- **`.planning/todos/pending/2026-05-07-centralize-lm-retry-handling.md`** — openevolve 内置自己的 LLM 调用 retry (大概率),不复用 evolution 仓的 retry helper;此 todo 与 Phase 21 弱相关。
- **`.planning/todos/pending/2026-05-07-expand-secret-patterns.md`** — Phase 21 NOTICE.md 写出前用 _contains_secret 过滤,即复用 Phase 14/19 已落的 SECRET_PATTERNS,**implicit 复用**,无新落地。
- **`.planning/todos/pending/2026-05-07-harden-llm-output-parsing.md`** — Phase 21 不新增 DSPy LLM-as-judge Signature (no LLM judge per D-14),不适用。
- **`.planning/todos/pending/2026-05-07-jsonl-skip-bad-lines.md`** — Phase 21 不读 jsonl,不适用。

</deferred>

---

*Phase: 21-darwinian-code-evolution*
*Context gathered: 2026-05-20*
