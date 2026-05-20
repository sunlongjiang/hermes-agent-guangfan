---
phase: 21
slug: darwinian-code-evolution
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-20
---

# Phase 21 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> 详细 12+ 测试清单见 `21-RESEARCH.md` §Validation Architecture (lines 768-849)。

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 (existing project test runner) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` `testpaths = ["tests"]` |
| **Quick run command** | `pytest tests/code/ -x -q` |
| **Full suite command** | `pytest tests/ -q` |
| **Estimated runtime** | < 2s（tests/code/ 全 mock，无 LLM 调用，无真实 openevolve 调用） |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/code/ -x -q`
- **After every plan wave:** Run `pytest tests/ -q`
- **Before `/gsd-verify-work`:** 全套 + `pytest tests/code/test_import_boundary.py` 必须绿（CI lint gate）
- **Max feedback latency:** < 2 秒（tests/code/ 全 mock；E2E dry-run 不调真实 openevolve）

---

## Per-Task Verification Map

> Plan IDs/Wave IDs/Task IDs 由 gsd-planner 在生成 PLAN.md 时正式分配；下表给出与 RESEARCH.md §Validation Architecture 对齐的"requirement → test name → command"骨架，planner 在 PLAN.md `<automated>` 字段直接复用。

| Test Group | Plan (TBD) | Wave (TBD) | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|-----------|------------|-----------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| test_import_boundary | TBD | 0 | V2-CODE-01 | T-21-IMPORT | openevolve import 仅限 adapter | unit | `pytest tests/code/test_import_boundary.py -x` | ❌ W0 | ⬜ pending |
| test_code_target_loader::test_find_target_by_relative_path | TBD | 1 | V2-CODE-01 | — | 正确解析 hermes-agent 目标路径 | unit | `pytest tests/code/test_code_target_loader.py::test_find_target_by_relative_path -x` | ❌ W0 | ⬜ pending |
| test_code_target_loader::test_ast_parse_discovers_30_tests | TBD | 1 | V2-CODE-01 | — | AST 收集所有 30 个原生 pytest | unit | `pytest tests/code/test_code_target_loader.py::test_ast_parse_discovers_30_tests -x` | ❌ W0 | ⬜ pending |
| test_code_target_loader::test_stratified_split_respects_buckets | TBD | 1 | V2-CODE-01 | — | CSI/SGR/OSC 分桶每桶 ≥1 | unit | `pytest tests/code/test_code_target_loader.py::test_stratified_split_respects_buckets -x` | ❌ W0 | ⬜ pending |
| test_code_target_loader::test_loader_rejects_evolution_path | TBD | 1 | V2-CODE-01 | T-21-RECURSE | 拒绝 evolution/ 路径防递归自演化 | unit | `pytest tests/code/test_code_target_loader.py::test_loader_rejects_evolution_path -x` | ❌ W0 | ⬜ pending |
| test_code_fitness::test_pytest_pass_gives_score_1 | TBD | 1 | V2-CODE-01 | — | pytest 全过 → pytest_score=1.0 | unit | `pytest tests/code/test_code_fitness.py::test_pytest_pass_gives_score_1 -x` | ❌ W0 | ⬜ pending |
| test_code_fitness::test_pytest_fail_gives_zero_and_reject | TBD | 1 | V2-CODE-01 | — | pytest 任一 fail → composite=0, decision=reject | unit | `pytest tests/code/test_code_fitness.py::test_pytest_fail_gives_zero_and_reject -x` | ❌ W0 | ⬜ pending |
| test_code_fitness::test_size_within_1_2x_gives_partial_score | TBD | 1 | V2-CODE-01 | — | size×1.15 → 0.7<component<1.0 | unit | `pytest tests/code/test_code_fitness.py::test_size_within_1_2x_gives_partial_score -x` | ❌ W0 | ⬜ pending |
| test_code_fitness::test_size_over_1_5x_rejects | TBD | 1 | V2-CODE-01 | — | size×1.6 → decision=reject | unit | `pytest tests/code/test_code_fitness.py::test_size_over_1_5x_rejects -x` | ❌ W0 | ⬜ pending |
| test_code_fitness::test_ruff_zero_violations_gives_1 | TBD | 1 | V2-CODE-01 | — | ruff clean → ruff_score=1.0 | unit | `pytest tests/code/test_code_fitness.py::test_ruff_zero_violations_gives_1 -x` | ❌ W0 | ⬜ pending |
| test_code_fitness::test_ruff_3_violations_gives_0_4 | TBD | 1 | V2-CODE-01 | — | ruff 3 条 → ruff_score=0.4 | unit | `pytest tests/code/test_code_fitness.py::test_ruff_3_violations_gives_0_4 -x` | ❌ W0 | ⬜ pending |
| test_sandbox_runner::test_restricted_env_removes_api_keys | TBD | 1 | V2-CODE-01 | T-21-SECRET | API key 不泄漏到 candidate 子进程 | unit | `pytest tests/code/test_sandbox_runner.py::test_restricted_env_removes_api_keys -x` | ❌ W0 | ⬜ pending |
| test_sandbox_runner::test_sandbox_timeout_returns_zero_fitness | TBD | 1 | V2-CODE-01 | T-21-DOS | timeout 不卡死主进程 | unit | `pytest tests/code/test_sandbox_runner.py::test_sandbox_timeout_returns_zero_fitness -x` | ❌ W0 | ⬜ pending |
| test_sandbox_runner::test_eval_dir_is_cleaned_after_run | TBD | 1 | V2-CODE-01 | T-21-LEAK | tmp 目录不残留 | unit | `pytest tests/code/test_sandbox_runner.py::test_eval_dir_is_cleaned_after_run -x` | ❌ W0 | ⬜ pending |
| test_sandbox_runner::test_candidate_with_implicit_hermes_import_fails_cleanly | TBD | 1 | V2-CODE-01 | T-21-IMPORT | 越界 import 不污染主进程 | unit | `pytest tests/code/test_sandbox_runner.py::test_candidate_with_implicit_hermes_import_fails_cleanly -x` | ❌ W0 | ⬜ pending |
| test_evolve_code_cli::test_dry_run_exits_0_without_openevolve_call | TBD | 2 | V2-CODE-01 | — | --dry-run 不真调 openevolve | E2E | `pytest tests/code/test_evolve_code_cli.py::test_dry_run_exits_0_without_openevolve_call -x` | ❌ W0 | ⬜ pending |
| test_evolve_code_cli::test_preflight_fails_without_license | TBD | 2 | V2-CODE-01 | — | LICENSE 缺失 pre-flight 即 fail | E2E | `pytest tests/code/test_evolve_code_cli.py::test_preflight_fails_without_license -x` | ❌ W0 | ⬜ pending |
| test_evolve_code_cli::test_cli_passes_model_to_evolution_config | TBD | 2 | V2-CODE-01 | — | --model 传入 EvolutionConfig | E2E | `pytest tests/code/test_evolve_code_cli.py::test_cli_passes_model_to_evolution_config -x` | ❌ W0 | ⬜ pending |
| test_ansi_strip_holdout（≥9 tests） | TBD | 2 | V2-CODE-01 | — | edge case 真实回放 | unit | `pytest tests/code/test_ansi_strip_holdout.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**覆盖统计**：19+ 个单测（满足 CONTEXT D-21 "不少于 12 个" 要求），涵盖：
- (a) code_target_loader 找文件 + 收集 pytest（4 个）
- (b) code_fitness 三段计分（6 个：pytest pass/fail × size ok/oversize × ruff clean/dirty）
- (c) code_evolver_adapter 单点 import 边界（1 个）
- (d) sandbox_runner timeout + 工作目录隔离 + import 防御（4 个）
- (e) evolve_code 端到端 dry-run（3 个）
- (f) holdout edge case 真实回放（≥9 个）

---

## Wave 0 Requirements

- [ ] `LICENSE` — MIT 文件落仓根（D-17，不可逆，executor checkpoint 确认版权人）
- [ ] `.pre-commit-config.yaml` — 含 `openevolve-single-import-surface` local hook（D-18）
- [ ] `pyproject.toml` — 删除 `[darwinian]` extra，加 `[project.optional-dependencies] code = ["openevolve>=0.2.27"]`；如 ruff 未在 `[dev]` extra，并入
- [ ] `ruff.toml`（或 `pyproject.toml [tool.ruff]`）— `select = ["E", "F", "W"]`, `line-length = 120`（D-13）
- [ ] `.gitignore` — 确认 `output/` 已纳入（CONCERNS H4）；如未，Wave 0 加入
- [ ] `tests/code/__init__.py` — 空文件
- [ ] `tests/code/test_import_boundary.py` — D-18 grep gate pytest 层
- [ ] `tests/code/test_code_target_loader.py` — 4 tests
- [ ] `tests/code/test_code_fitness.py` — 6 tests
- [ ] `tests/code/test_sandbox_runner.py` — 4 tests
- [ ] `tests/code/test_evolve_code_cli.py` — 3 tests
- [ ] `tests/code/test_ansi_strip_holdout.py` — 9-10 edge case

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| LICENSE 版权人正确性 | D-17 不可逆决策 | 法律责任不可自动化 | executor 在 commit LICENSE 前 AskUserQuestion 确认 `<COPYRIGHT_HOLDER>` 占位符替换值；与 `git config user.name` 对齐 |
| evolved `ansi_strip.py` 真实合入 hermes-agent | PROJECT.md Out-of-Scope | 自动 PR 永久排除 | output/code/<ts>/ 产物由人工 review 后手工合入 hermes-agent |
| `output/code/<ts>/NOTICE.md` 警示完整性 | D-19 | 警示语义不能 grep | 抽样人工阅读 NOTICE.md，确认 "UNREVIEWED — DO NOT MERGE WITHOUT HUMAN REVIEW" 显著存在 |
| openevolve 真实 evolve run 收敛性 | success criterion #2 | LLM 调用 + cost 实跑不在 CI | Phase 21 完成后一次性人工跑 `python -m evolution.code.evolve_code --component tools/ansi_strip.py --iterations 5 --max-cost 1.0 --dry-run=false`，验收 best_candidate 存在 |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references（LICENSE / pre-commit / ruff config / pyproject extras / tests/code/ 目录）
- [ ] No watch-mode flags
- [ ] Feedback latency < 2s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
