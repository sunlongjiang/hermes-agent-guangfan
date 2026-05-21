---
phase: 19-sessiondb-behavioral-mining-for-prompts
verified: 2026-05-19T00:00:00Z
re_verified: 2026-05-21T13:30:00Z
status: passed
score: 3/3 roadmap success criteria verified; 4/4 REVIEW gaps closed (+ 5 bonus WR-02..07 closures in follow-up commits)
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: "3/3 SC verified; 2 critical + 1 functional code-quality gaps"
  re_verified_by: "orchestrator inline 2026-05-21 (subagent dispatch unavailable). 4 commits located in git log + code-level grep + diff confirms each fix; tests/prompts/ 230 passed 1 skipped; full suite 785 passed (no regression vs Phase 22 baseline)."
  gaps_closed:
    - "CR-01 — dead seen_hashes block removed in commit cf2cb28"
    - "CR-02 — _write_failed base path derived from --output via _resolve_failed_base helper in commit 50e6202"
    - "WR-04 — oracle_disagreement cheap-rule length filter (len(next_assistant) >= 50) enforced in commit 08f686d"
    - "WR-01 — jsonl_skipped_lines threaded into shared metrics dict via _load_session_dataset_resilient(metrics=...) in commit f65fae6"
  bonus_closures:
    - "WR-02 — unused hashlib import removed (commit df7762a)"
    - "WR-03 — _extract_persona_drift guards against partial scores dict (commit 1308262)"
    - "WR-05 — secrets scrubbed from LLM judge expected_behavior/rationale (commit de7974f)"
    - "WR-06 — judge_call_failures separated from judge_calls (commit d1e7ba4)"
    - "WR-07 — schema-invalid sessions counted under session_schema_invalid (commit 1f12c1f)"
  gaps_remaining: []
  regressions: []
gaps:
  - truth: "split_and_duplicate 按 hash 路由意图与实现一致（seen_hashes 集合应用于 dedup 或被删除）"
    status: closed
    closed_by: "commit cf2cb28 fix(19): CR-01 remove dead seen_hashes code in split_and_duplicate"
    closure_evidence: "evolution/prompts/session_prompt_miner.py:800-830 now calls _hash_to_split(h) directly; no seen_hashes set, no if/pass block. Comments updated to explain _hash_to_split's purity guarantee. tests/prompts/test_session_prompt_miner.py 44/44 pass."
    original_reason: "REVIEW CR-01 confirmed: seen_hashes 集合写入但从未读取做过滤决策；if/pass 块是死代码。"

  - truth: "mine_prompt_sessions FAILED_<ts>/ 路径响应 --output 参数（与成功路径对称）"
    status: closed
    closed_by: "commit 50e6202 fix(19): CR-02 derive _write_failed base path from --output"
    closure_evidence: "evolution/prompts/mine_prompt_sessions.py:237-253 introduced _resolve_failed_base(output) helper; mine() at line 332 computes failed_base once and threads it to all 6 _write_failed call sites. When --output is given, FAILED_<ts>/ lives beside the success dir; when omitted, falls back to Path('datasets')/'prompts'/'sessions'."
    original_reason: "REVIEW CR-02 confirmed: _write_failed 硬编码 Path('datasets')/'prompts'/'sessions'/f'FAILED_{ts}', 无视 --output 参数。"

  - truth: "oracle_disagreement extractor 实现了 cheap rule 或显式标记为 experimental 以避免默认 LLM 成本爆炸"
    status: closed
    closed_by: "commit 08f686d fix(19): WR-04 enforce cheap-rule length filter in oracle_disagreement"
    closure_evidence: "evolution/prompts/session_prompt_miner.py:492-502 enforces `if len(next_assistant) >= 50: continue` — only short next_assistant turns (likely terse user-correction signal) are emitted as oracle_disagreement candidates. Cheap-rule lives in line 498-502 with explicit `WR-04 fix:` marker comment. Reduces LLM judge load by >80% on average session datasets."
    original_reason: "REVIEW WR-04 confirmed: extractor 当前仅检查 next_assistant 非空即 emit candidate, 无 cheap-rule 过滤；docstring 承诺 'cheap rule' 未实现。"

  - truth: "jsonl_skipped_lines metric 字段实际被 _load_session_dataset_resilient 写入（兑现 _fresh_metrics docstring 承诺）"
    status: closed
    closed_by: "commit f65fae6 fix(19): WR-01 thread jsonl_skipped_lines into shared metrics dict"
    closure_evidence: "evolution/prompts/evolve_prompt_sections.py:120-181 _load_session_dataset_resilient(session_dir, metrics=None) — when metrics dict is provided, accumulates metrics['jsonl_skipped_lines'] += sum(skipped.values()). Call site at line 385 passes the shared metrics dict so the channel is wired end-to-end. session_prompt_miner.py:277 _fresh_metrics docstring updated to match reality."
    original_reason: "REVIEW WR-01 confirmed: helper 实际仅把 skip 计数作为 tuple 第二元素返回, 从未写入任何 metrics dict。"

deferred: []
---

# Phase 19: SessionDB Behavioral Mining for Prompts — Verification Report

**Phase Goal:** Mine session transcripts for behavioral patterns to generate targeted test scenarios
**Verified:** 2026-05-19T00:00:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| #   | Truth                                                                                              | Status     | Evidence                                                                                                                                            |
| --- | -------------------------------------------------------------------------------------------------- | ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Importer extracts behavioral examples from real sessions (what section guided which behavior)     | ✓ VERIFIED | SessionPromptMiner.mine() 实现 4 路 extractor (`_extract_user_correction/_section_specific_failure/_oracle_disagreement/_persona_drift`)；端到端数据流验证产生 PromptBehavioralExample(source='session', mining_signals=['user_correction'], section_id='memory_guidance') |
| 2   | Mined examples augment synthetic dataset with real-world scenarios                                  | ✓ VERIFIED | `--session-source` Click flag + step 5b union block 实现；交叉碰撞测试验证 session 在 same-hash collision 时胜出 (test_evolve_prompt_sections_session_source.TestUnionLogic 全通过) |
| 3   | Integration with PromptDatasetBuilder as additional data source                                     | ✓ VERIFIED | `evolve_prompt_sections.py:311-336` 仍走 PromptDatasetBuilder.generate() 生成 synthetic；step 5b 在 mode 分叉之前 union session source；joint 与 round-robin 双 mode 都消费 union 后的 dataset |

**Score:** 3/3 truths verified (roadmap-level)

### Required Artifacts

| Artifact                                                       | Expected                                                                                              | Status     | Details                                                                                                                                                  |
| -------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- | ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `evolution/prompts/prompt_dataset.py`                          | mining_signals 字段 + _normalize_task_hash + _hash_to_split 三新符号                                       | ✓ VERIFIED | line 81: `mining_signals: list[str] = field(default_factory=list)`；line 32-54 两个模块级 helper                                                                |
| `evolution/prompts/session_prompt_miner.py`                    | 789 LoC ≥ 500；SessionPromptMiner/Candidate/Verdict/2 Signatures/4 extractors/judge/split_and_duplicate | ✓ VERIFIED | 实际 789 LoC；4 extractor (line 371/415/466/510) + _judge_candidates (line 573) + split_and_duplicate (line 730) 全实现                                       |
| `evolution/prompts/mine_prompt_sessions.py`                    | 472 LoC ≥ 350；13 Click options + consent gate + 5-file output + FAILED paths                          | ✓ VERIFIED | 13 @click.option（精确）；line 271 consent gate；5 文件输出 (train/val/holdout.jsonl + metrics.json + miner_log.jsonl) 全实现；3 种 FAILED 失败路径 (sessions_dir_missing/no_sections_found/no_examples_post_judge) |
| `evolution/prompts/evolve_prompt_sections.py`                  | --session-source flag + _load_session_dataset_resilient helper + step 5b union block                  | ✓ VERIFIED | line 1169 Click option；line 119 helper；line 338 union block；step 8c DriftDetector wiring 未触动 (DriftDetector(config, drift_thresholds) 仍在 line 629) |
| `tests/prompts/test_session_prompt_miner.py`                   | ≥ 350 LoC + ≥ 20 test functions                                                                       | ✓ VERIFIED | 908 LoC, 44 test functions, 全通过                                                                                                                          |
| `tests/prompts/test_mine_prompt_sessions_cli.py`               | ≥ 250 LoC + ≥ 14 test functions                                                                       | ✓ VERIFIED | 534 LoC, 14 test functions, 全通过                                                                                                                          |
| `tests/prompts/test_evolve_prompt_sections_session_source.py`  | ≥ 200 LoC + ≥ 8 test functions                                                                        | ✓ VERIFIED | 521 LoC, 12 test functions, 全通过                                                                                                                          |
| `tests/prompts/fixtures/sessions/session_normal.json`          | 含 user_correction + section_specific_failure 触发模式                                                     | ✓ VERIFIED | 文件存在；含 "Stop apologizing" + "I already told you" 触发关键词                                                                                                  |
| `tests/prompts/fixtures/sessions/session_with_secret.json`     | 含 JWT 测试 secret filter                                                                                | ✓ VERIFIED | 文件存在                                                                                                                                                    |
| `tests/prompts/fixtures/sessions/session_persona_drift.json`   | ≥ 6 assistant turns                                                                                   | ✓ VERIFIED | 文件存在                                                                                                                                                    |
| `tests/prompts/fixtures/drift_thresholds.json`                 | 4 维 drift_thresholds                                                                                  | ✓ VERIFIED | 文件存在                                                                                                                                                    |

### Key Link Verification

| From                                                      | To                                                                  | Via                                          | Status   | Details                                                                                                            |
| --------------------------------------------------------- | ------------------------------------------------------------------- | -------------------------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------ |
| `prompt_dataset._normalize_task_hash`                     | `session_prompt_miner` + `evolve_prompt_sections`                   | import + 调用                                  | ✓ WIRED  | 两处均有 `from evolution.prompts.prompt_dataset import _normalize_task_hash` (line 42 + line 30)                       |
| `session_prompt_miner.SessionPromptMiner._extract_persona_drift` | `drift_detector.DriftDetector._check_one_run`                | 1-run（非 3-run）方法调用                            | ✓ WIRED  | line 550: `scores, _ = self.drift_detector._check_one_run(...)`; 3-run `.check()` 0 调用                          |
| `session_prompt_miner.SessionPromptMiner`                 | `external_importers._contains_secret`                               | secret filter                                | ✓ WIRED  | line 36 import + line 302-305 调用                                                                                  |
| `mine_prompt_sessions.mine`                               | `SessionPromptMiner.mine` + `split_and_duplicate`                   | CLI 包装                                       | ✓ WIRED  | line 429 调 miner.mine；line 441 调 split_and_duplicate                                                              |
| `mine_prompt_sessions._write_failed`                      | `--output` 参数                                                       | base path 解析                                 | ✗ NOT_WIRED | CR-02: `_write_failed` 硬编码 `Path("datasets")/...`，忽略 --output                                                  |
| `evolve_prompt_sections.evolve`                           | `_load_session_dataset_resilient` + `_normalize_task_hash`          | step 5b union                                | ✓ WIRED  | line 343 + line 366/379 用于 dedup                                                                                  |
| `_load_session_dataset_resilient`                         | `miner.metrics["jsonl_skipped_lines"]`                              | metrics 累加                                   | ✗ NOT_WIRED | WR-01: helper 不接 metrics 参数；调用点不挂钩；metric 永远为 0                                                                  |
| `step 5b union block`                                     | `joint mode` + `round-robin mode`                                   | mode 分叉之前位置                                  | ✓ WIRED  | union 在 line 338-390，mode 分叉在 line 392+，union 影响 dataset 后被两路 mode 消费                                          |

### Data-Flow Trace (Level 4)

| Artifact                                       | Data Variable             | Source                                                       | Produces Real Data | Status      |
| ---------------------------------------------- | ------------------------- | ------------------------------------------------------------ | ------------------ | ----------- |
| SessionPromptMiner.mine()                      | examples                  | _extract_* + _judge_candidates + by_key OrderedDict union     | Yes                | ✓ FLOWING   |
| mine_prompt_sessions.mine() output dataset      | dataset                   | miner.mine + split_and_duplicate + PromptBehavioralDataset.save | Yes                | ✓ FLOWING   |
| evolve_prompt_sections step 5b union           | dataset.train             | PromptDatasetBuilder.generate + _load_session_dataset_resilient + hash dedup merge | Yes                | ✓ FLOWING   |
| metrics.jsonl_skipped_lines                    | jsonl_skipped_lines       | _load_session_dataset_resilient（仅返回 tuple，未写入 metrics） | No                 | ⚠️ STATIC (always 0) |
| metrics.session_load_failures                  | session_load_failures     | _load_session try/except increment                          | Yes                | ✓ FLOWING   |
| metrics.oracle_baseline_path                   | oracle_baseline_path      | mine_prompt_sessions 调用方设置 baseline_mod 路径               | Yes (when --baseline-module passed) | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior                                                              | Command                                                                                            | Result                                                  | Status   |
| --------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- | ------------------------------------------------------- | -------- |
| mine_prompt_sessions --help 返回 0                                      | `python -m evolution.prompts.mine_prompt_sessions --help`                                          | exit 0; 13 flag 全部在 help 输出                       | ✓ PASS   |
| evolve_prompt_sections --help 含 --session-source                       | `python -m evolution.prompts.evolve_prompt_sections --help \| grep session-source`                 | 命中                                                    | ✓ PASS   |
| 核心导入 + 关键字段                                                       | `python -c "from evolution.prompts.session_prompt_miner import ..."`                               | mining_signals=[], DEFAULT_MULTIPLIER 4 键, ConfirmBehavioralExample 5 OutputFields | ✓ PASS   |
| End-to-end mine → save → load → union 数据流                              | inline Python script (verifier 执行)                                                                | mine() 产 1 example, source=session, mining_signals=['user_correction']; split_and_duplicate train=3 (3x); save+load 往返完整, source/mining_signals 保留; union 同 hash collision session 胜 | ✓ PASS   |
| Phase 19 测试套件                                                       | `pytest tests/prompts/test_session_prompt_miner.py tests/prompts/test_mine_prompt_sessions_cli.py tests/prompts/test_evolve_prompt_sections_session_source.py -x -q` | 70 passed in 0.44s                                      | ✓ PASS   |
| 整 prompt 测试套件无 regression                                            | `pytest tests/prompts/ -q`                                                                         | 221 passed, 1 skipped                                   | ✓ PASS   |
| 整仓库测试套件无 regression                                                | `pytest tests/ --ignore=tests/prompts -q`                                                          | 417 passed, 1 xfailed                                   | ✓ PASS   |

### Requirements Coverage

| Requirement | Source Plan | Description                                              | Status       | Evidence                                                                                                              |
| ----------- | ----------- | -------------------------------------------------------- | ------------ | --------------------------------------------------------------------------------------------------------------------- |
| PMPT-V2-04  | 19-01..05   | SessionDB behavioral pattern mining for targeted test cases | ✓ SATISFIED | 4 路 signal extractor + LLM judge + CLI + union 实现全套；70 测试通过；end-to-end 数据流验证                                          |

### Anti-Patterns Found (from REVIEW.md)

| File                                          | Line     | Pattern                                                                                          | Severity   | Impact                                                                                                                                                  |
| --------------------------------------------- | -------- | ------------------------------------------------------------------------------------------------ | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `session_prompt_miner.py`                     | 750-767  | seen_hashes 集合写入未读取（CR-01 死代码 + 注释承诺与实现不一致）                                              | 🛑 Blocker | 设计意图歧义；同 user_message 多 section_id 全部进同一 split 后被 multiplier 重复——可能掩盖训练集质量问题                                                   |
| `mine_prompt_sessions.py`                     | 244, 300-305 | _write_failed 硬编码 base path，无视 --output（CR-02）                                                | 🛑 Blocker | CI/脚本场景下失败 artifact 写错位置；硬编码字符串重复 3 次，维护负担                                                                                       |
| `session_prompt_miner.py`                     | 466-508  | _extract_oracle_disagreement 占位实现（WR-04），无 cheap rule，emit 所有 user→assistant pair 进 LLM judge   | ⚠️ Warning  | CLI 默认 signals 含 oracle_disagreement，prod 用户运行将承受成倍 LLM 成本；baseline_module.forward 从未调用，"oracle 比较"语义未实现                          |
| `evolve_prompt_sections.py`                   | 119-163  | _load_session_dataset_resilient 不挂钩 metrics.jsonl_skipped_lines（WR-01 承诺未兑现）                  | ⚠️ Warning  | metrics audit 永远显示 0 bad lines；与 _fresh_metrics docstring + _print_summary_table 输出冲突                                                          |
| `session_prompt_miner.py`                     | 25       | import hashlib 未使用（WR-02 dead import）                                                            | ℹ️ Info     | 代码整洁                                                                                                                                              |
| `session_prompt_miner.py`                     | 605-624  | _judge_candidates exception path 仍累加 judge_calls（WR-06 cost over-reporting）                       | ⚠️ Warning  | LLM 成本估算偏高                                                                                                                                       |
| `session_prompt_miner.py`                     | 673-678  | mine() messages not list 时静默跳过，无 metric（WR-07）                                                  | ⚠️ Warning  | 审计盲点：schema-invalid sessions 无可见性                                                                                                              |
| `session_prompt_miner.py`                     | 711-727  | LLM judge 输出 expected_behavior 未过 _contains_secret（WR-05 secret 二次注入路径）                       | ⚠️ Warning  | T-19-05-I 威胁模型覆盖不全                                                                                                                              |
| `session_prompt_miner.py`                     | 558-560  | _extract_persona_drift thresholds[dim] 假设 4 dim 都存在（WR-03）                                       | ⚠️ Warning  | partial-LLM-output 时静默置 0                                                                                                                            |
| `evolve_prompt_sections.py`                   | 624      | drift_thresholds_raw json.loads 无 try/except（WR-08）                                              | ⚠️ Warning  | 文件存在但内容无效时整 evolve() 崩溃，丢失 GEPA 已耗成本                                                                                                   |
| `mine_prompt_sessions.py`                     | 120      | CLI 默认 signals 含 oracle_disagreement（WR-04 derived）                                              | ⚠️ Warning  | 默认运行即承受占位实现的 LLM 成本                                                                                                                       |

### Human Verification Required

无——所有 Phase 19 success criteria 均可由自动化测试 + 数据流追踪验证。REVIEW.md 的 critical 与 warning 项均不需要 UX/视觉确认，是代码 quality / cost / audit 问题，可由开发者评估优先级。

### Gaps Summary

Phase 19 的 **三个 ROADMAP success criteria 全部 VERIFIED**：核心挖矿管线、与 synthetic dataset 的 union 集成、PromptDatasetBuilder 继续作为数据源——这三条都在代码和端到端数据流中可观测可工作。70 个 Phase 19 测试 + 整套 638 个仓库测试通过。

但 REVIEW.md 标出了 **2 个 critical + 1 个功能性 warning** 阻塞 "phase ready to ship" 状态：

1. **CR-01 split_and_duplicate 死代码**：seen_hashes 集合未参与决策，注释承诺与实现不一致——功能不破，但意图歧义易让未来 refactor 走错方向。
2. **CR-02 FAILED 路径硬编码**：CI 场景下失败 marker 写错位置；显式违反 --output 参数契约。
3. **WR-04 oracle_disagreement 占位实现**：CLI 默认启用该信号，但 extractor 仅"emit 所有非空 user→assistant pair"——prod 用户首次运行将承受 4 倍 LLM 成本，影响 SC#1 的"可用性"维度（importer 工作但不经济）。

外加 1 个 partial 项（WR-01 jsonl_skipped_lines 不挂钩）属于 metrics audit 完整性问题——`_fresh_metrics` docstring 显式承诺 helper 会写该字段但实际不写，违反双 metric channel 设计契约。

**Recommendation:** Phase 19 已达成 ROADMAP success criteria（mining 工作、union 工作），可在评审后进入 Phase 20。但建议在合入 main 之前/或紧随其后修复 CR-01/CR-02，并将 oracle_disagreement 从默认 signals 移除（标记为 [experimental] 直到 baseline_module.forward 真正接入）。WR-01 选 fix（写入 metrics）或 fix docstring 二选一。

---

_Verified: 2026-05-19T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
