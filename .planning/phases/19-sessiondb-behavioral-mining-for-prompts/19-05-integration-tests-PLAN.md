---
phase: 19-sessiondb-behavioral-mining-for-prompts
plan: 05
type: execute
wave: 5
depends_on:
  - 19-02
  - 19-03
  - 19-04
files_modified:
  - tests/prompts/test_session_prompt_miner.py
  - tests/prompts/test_mine_prompt_sessions_cli.py
  - tests/prompts/test_evolve_prompt_sections_session_source.py
  - tests/prompts/fixtures/sessions/session_normal.json
  - tests/prompts/fixtures/sessions/session_with_secret.json
  - tests/prompts/fixtures/sessions/session_persona_drift.json
  - tests/prompts/fixtures/drift_thresholds.json
autonomous: true
requirements:
  - PMPT-V2-04
tags:
  - testing
  - integration
  - prompt
  - privacy-gate

must_haves:
  truths:
    - "[D-01/D-04] test_session_prompt_miner.py 覆盖 4 路 extractor 行为：user_correction（关键词 + 二判）/ section_specific_failure（per-section 5 维）/ oracle_disagreement（baseline None 时短路）/ persona_drift（detector + min_turns + exceeded dim）"
    - "[D-03] ConfirmBehavioralExample 单 LLM call 解析 5 字段；mock 返回各类不规则值（HUGE/null/中文）测 fallback 路径"
    - "[D-13] split_and_duplicate 测试：覆盖 train-only 复制 + max-not-product + val/holdout 不复制"
    - "[D-15] hash-bucket split 确定性测试：1000 个不同字符串桶分布近似 70/15/15"
    - "[D-23] secret 过滤：含 JWT/AWS-key/Shannon-高熵 user 消息的 mock session → 0 candidate 进 judge，metrics.secret_filter_skipped 递增"
    - "[D-25] test_mine_prompt_sessions_cli.py 验证 --i-have-consent 必填 gate（缺失即 exit non-0）"
    - "[D-17] CLI --help 输出含全部 13 flag；--drift-thresholds-path 默认值正确"
    - "[D-04] CLI persona_drift signal + 缺失 drift_thresholds_path（不存在文件）→ warn + 继续（不 fail）"
    - "[D-21] test_evolve_prompt_sections_session_source.py 验证 --session-source 在 joint mode 与 round-robin mode 下都生效（union 路径 transparent）"
    - "[D-16] union 行为完整覆盖：no-collision / same-split-collision (session wins) / cross-split-collision (synth dropped)"
    - "[D-24] JSONL bad-line 在 --session-source 加载路径被跳过 + > 5% warn 触发；不影响 evolve 主流程"
    - "[W7 fix] step 8c regression guard 显式断言 `DriftDetector(` 计数 ≥ 2、精确签名 `DriftDetector(config, drift_thresholds)` 在文件中保留、关键变量名 `drift_per_dim_metrics` 在文件中保留 — 防止 Phase 18 wiring 退化"
  artifacts:
    - path: "tests/prompts/test_session_prompt_miner.py"
      provides: "SessionPromptMiner 单元测试套件（4 extractor + judge + split_and_duplicate + secret/drift filter）"
      min_lines: 350
    - path: "tests/prompts/test_mine_prompt_sessions_cli.py"
      provides: "mine_prompt_sessions CLI 集成测试套件（consent gate / dry-run / FAILED paths / 5 件套输出 / persona_drift graceful disable）"
      min_lines: 250
    - path: "tests/prompts/test_evolve_prompt_sections_session_source.py"
      provides: "--session-source flag 端到端集成测试（joint + round-robin / union 3 种 collision / bad JSONL 容错）"
      min_lines: 200
    - path: "tests/prompts/fixtures/sessions/session_normal.json"
      provides: "正常 hermes session JSON fixture（含 user_correction + section_specific_failure 触发模式）"
    - path: "tests/prompts/fixtures/sessions/session_with_secret.json"
      provides: "含 JWT/AWS-key 的 session fixture（secret filter 测试用）"
    - path: "tests/prompts/fixtures/sessions/session_persona_drift.json"
      provides: "≥6 assistant turns（min_turns 门槛）的 session（persona_drift 测试用）"
    - path: "tests/prompts/fixtures/drift_thresholds.json"
      provides: "4 维 drift_thresholds.json fixture（被 SessionPromptMiner 与 evolve_prompt_sections 加载）"
  key_links:
    - from: "tests/prompts/test_session_prompt_miner.py"
      to: "evolution/prompts/session_prompt_miner.py"
      via: "import SessionPromptMiner + Candidate + Verdict + split_and_duplicate"
      pattern: "from evolution.prompts.session_prompt_miner import"
    - from: "tests/prompts/test_mine_prompt_sessions_cli.py"
      to: "evolution/prompts/mine_prompt_sessions.py"
      via: "click.testing.CliRunner + mock SessionPromptMiner / DriftDetector / extract_prompt_sections"
      pattern: "CliRunner\\(\\)"
    - from: "tests/prompts/test_evolve_prompt_sections_session_source.py"
      to: "evolution/prompts/evolve_prompt_sections.py"
      via: "click.testing.CliRunner + mock dspy.LM / configure / GEPA + 真实 _load_session_dataset_resilient"
      pattern: "_load_session_dataset_resilient"
---

<objective>
建立完整集成测试套件覆盖 Plan 02-04 的所有 Phase 19 行为：4 路 signal extractor、ConfirmBehavioralExample 鲁棒解析、CLI consent gate、persona_drift graceful disable、--session-source union 在 joint/round-robin 双 mode 下的 transparent 工作、JSONL bad-line 容错、secret 过滤。

Purpose: Phase 19 Wave 5 — 端到端验证；让 verify-phase 能跑 `python -m pytest tests/prompts/` 并 100% 通过。新增 ~800 LoC 测试 + 4 个 session/drift fixtures。
Output: 3 个新测试文件 + 4 个 fixture，所有测试通过 mock LLM (no real API calls)。
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/19-sessiondb-behavioral-mining-for-prompts/19-CONTEXT.md
@.planning/phases/19-sessiondb-behavioral-mining-for-prompts/19-PATTERNS.md
@.planning/phases/19-sessiondb-behavioral-mining-for-prompts/19-02-SUMMARY.md
@.planning/phases/19-sessiondb-behavioral-mining-for-prompts/19-03-SUMMARY.md
@.planning/phases/19-sessiondb-behavioral-mining-for-prompts/19-04-SUMMARY.md
@evolution/prompts/session_prompt_miner.py
@evolution/prompts/mine_prompt_sessions.py
@evolution/prompts/evolve_prompt_sections.py
@tests/prompts/conftest.py
</context>

<interfaces>
<!-- Existing conftest.py (per STATE.md 18-01 SUMMARY):
- mock_drift_lm fixture
- dummy_thresholds fixture
- drift_calibration_mini_path fixture

These are reusable. New tests may also rely on tmp_path + monkeypatch standard pytest fixtures. -->

<!-- Plan 19-02 exports -->
```python
from evolution.prompts.session_prompt_miner import (
    SessionPromptMiner, DEFAULT_MULTIPLIER, VALID_SIGNALS,
    Candidate, Verdict, split_and_duplicate,
    ConfirmBehavioralExample, DetectUserCorrection,
    _USER_CORRECTION_PATTERNS, _SECTION_SPECIFIC_PATTERNS,
)
```

<!-- Plan 19-03 exports -->
```python
from evolution.prompts.mine_prompt_sessions import (
    main as mine_prompt_sessions_main,
    mine,
    _parse_signals,
    _parse_multiplier_override,
    _print_summary_table,
    _write_failed,
)
```

<!-- Plan 19-04 exports -->
```python
from evolution.prompts.evolve_prompt_sections import (
    main as evolve_prompt_sections_main,
    evolve,
    _load_session_dataset_resilient,
)
```

<!-- Existing Phase 18 mock infrastructure pattern (per STATE.md 18-04 SUMMARY):
- TestABBaseline._ab_patched_run shows how to stub drift_thresholds.json + mock DriftDetector
  + mock dspy.LM / configure / context / GEPA
- TestDriftGate (Plan 18-05) shows full CLI integration tests with 6 sub-cases covering
  D-OUT-02 / D-BYPASS-01..02 / D-GATE-03 / D-GATE-04 -->
</interfaces>

<tasks>

<task type="auto" tdd="true">
  <name>Task 5.1: 4 个 fixtures + tests/prompts/test_session_prompt_miner.py（SessionPromptMiner unit tests）</name>
  <files>tests/prompts/test_session_prompt_miner.py, tests/prompts/fixtures/sessions/session_normal.json, tests/prompts/fixtures/sessions/session_with_secret.json, tests/prompts/fixtures/sessions/session_persona_drift.json, tests/prompts/fixtures/drift_thresholds.json</files>

  <read_first>
    - evolution/prompts/session_prompt_miner.py（Plan 02 产物，全文了解 4 extractor + judge + helpers 接口）
    - tests/prompts/conftest.py（确认既有 fixtures：mock_drift_lm / dummy_thresholds / drift_calibration_mini_path）
    - tests/tools/test_session_miner.py（Phase 14 测试套件 — 直接模板；如不存在则 grep `tests/tools/` 找最接近的）
    - evolution/prompts/prompt_loader.py（PromptSection 构造参数）
  </read_first>

  <behavior>
    至少 25 测试覆盖：
    - test_extract_user_correction_keyword_hit_then_llm_confirm: 关键词 + mock LLM 二判 True → cand 添加
    - test_extract_user_correction_keyword_hit_but_llm_rejects: 关键词命中但 LLM 二判 False → cand 数 0
    - test_extract_user_correction_no_keyword: 无关键词 → cand 数 0
    - test_extract_user_correction_signal_not_active: signals=['persona_drift']，user_correction 不在 → return []
    - test_extract_section_specific_failure_memory_guidance: "I already told you" → cand(section_id='memory_guidance')
    - test_extract_section_specific_failure_skills_guidance: "you didn't use the X skill" → cand(section_id='skills_guidance')
    - test_extract_section_specific_failure_session_search: "let me restate same question" → cand(section_id='session_search_guidance')
    - test_extract_section_specific_failure_default_identity: "stop being too formal" → cand(section_id='default_agent_identity')
    - test_extract_section_specific_failure_platform_hints_macos: "on macOS don't do that" → cand(section_id='platform_hints.macos')
    - test_extract_oracle_disagreement_baseline_none: baseline_module=None → cand 数 0（D-04 graceful disable）
    - test_extract_persona_drift_no_detector: signals=['persona_drift'] + drift_thresholds=None → drift_detector is None → cand 数 0
    - test_extract_persona_drift_below_min_turns: assistant turn 数 = 5（<6）→ cand 数 0
    - test_extract_persona_drift_above_min_turns_exceeded_dim: mock detector 返回 dim score > threshold → cand 数 = exceeded dims
    - test_extract_persona_drift_above_min_turns_no_drift: mock detector 返回 dim scores 都 ≤ threshold → cand 数 0
    - test_extract_persona_drift_uses_one_run_not_three_run: assert `mock.drift_detector._check_one_run.called` 而 `mock.drift_detector.check.called == False`
    - test_judge_confirm_example_valid: mock judge 返回 verdict='confirm_example' difficulty='easy' → metrics.judge_confirmed_by_signal[signal] += 1
    - test_judge_false_positive_recorded_not_dropped: mock judge 返回 verdict='false_positive' → 返回 Verdict 元组但 metric 计入 false_positives
    - test_judge_difficulty_fallback: mock judge 返回 difficulty='LARGE' → Verdict.difficulty == 'medium'
    - test_judge_verdict_fallback: mock judge 返回 verdict='SOMETHING' → Verdict.verdict == 'false_positive'
    - test_judge_exception_fallback: mock judge.side_effect = Exception → Verdict.verdict == 'false_positive', difficulty='medium'
    - test_filter_secrets_drops_jwt: cand.task 含 JWT pattern → 被 _filter_secrets 丢，metrics.secret_filter_skipped += 1
    - test_filter_drift_drops_unknown_section: verdict.section_id='unknown_section' 不在 current_section_ids → 丢 + metrics.surface_drift_dropped += 1
    - test_mine_empty_dir: mine(empty Path) → []
    - test_mine_full_flow_single_session: 单 mock session + mock judges + mock current_sections → 返回 1 example，source='session'，mining_signals=['user_correction']
    - test_mine_dedup_same_hash_different_signals: 同 user_message 跨 2 个 signal 命中 → 1 example，mining_signals 含两路
    - test_mine_split_multiple_section_ids: 同 user_message + 不同 section_id verdict → 2 examples（D-07）
    - test_split_and_duplicate_train_only_dup_user_correction: 1 ex(mining_signals=['user_correction']) 落 train → train length=3, val=0, holdout=0
    - test_split_and_duplicate_train_only_dup_persona_drift: 1 ex(mining_signals=['persona_drift']) 落 train → train length=2
    - test_split_and_duplicate_max_not_product: 1 ex(mining_signals=['user_correction','persona_drift']) → max(3,2)=3 (NOT 6)
    - test_split_and_duplicate_val_holdout_unchanged: 例落 val/holdout → 不复制（length=1）
    - test_metrics_judge_calls_by_signal_increment: 3 candidates 跨 2 signal → judge_calls_by_signal 正确
    - test_hash_split_distribution: 1000 strings → 桶分布近似 70/15/15
    - test_confirm_behavioral_example_signature_public_api (W5 fix): 通过 `__annotations__` 公共 API 验证 5 个 OutputField 名字存在；不依赖 DSPy 私有 marker
  </behavior>

  <action>
    **创建 fixture 文件**：

    1. `tests/prompts/fixtures/drift_thresholds.json`：
    ```json
    {
      "tone": 0.5,
      "formality": 0.5,
      "vocabulary": 0.5,
      "persona": 0.5,
      "_meta": {"created_by": "fixture", "purpose": "test"}
    }
    ```

    2. `tests/prompts/fixtures/sessions/session_normal.json`：
    ```json
    {
      "messages": [
        {"role": "user", "content": "What's my schedule today?"},
        {"role": "assistant", "content": "Let me check your calendar."},
        {"role": "user", "content": "Wait, I already told you I'm on vacation this week."},
        {"role": "assistant", "content": "Sorry, I forgot. Let me note that down."},
        {"role": "user", "content": "Stop apologizing so much, just be concise."}
      ]
    }
    ```

    3. `tests/prompts/fixtures/sessions/session_with_secret.json`：
    ```json
    {
      "messages": [
        {"role": "user", "content": "Please use my key: eyJhbGciOiJIUzI1NiJ9.eyJpZCI6MX0.signaturesignaturesignature_more_padding_to_pass_secret_pattern_or_jwt_check_token_validation"},
        {"role": "assistant", "content": "I cannot read that."},
        {"role": "user", "content": "Actually, you should use /search skill, not assume."}
      ]
    }
    ```

    4. `tests/prompts/fixtures/sessions/session_persona_drift.json`（含至少 9 assistant turns 触发 min_turns=6 门槛）：
    ```json
    {
      "messages": [
        {"role": "user", "content": "Help me draft an email."},
        {"role": "assistant", "content": "Sure! What's the email about?"},
        {"role": "user", "content": "About a project delay."},
        {"role": "assistant", "content": "Got it! Friendly tone OK?"},
        {"role": "user", "content": "Yes"},
        {"role": "assistant", "content": "Hi team! Just a quick note about our project timeline!"},
        {"role": "user", "content": "More formal please"},
        {"role": "assistant", "content": "Dear team, regarding the project schedule adjustment."},
        {"role": "user", "content": "OK"},
        {"role": "assistant", "content": "I shall provide further specifications upon request."},
        {"role": "user", "content": "Continue"},
        {"role": "assistant", "content": "Indeed, the timeline requires substantive revision."},
        {"role": "user", "content": "Final draft"},
        {"role": "assistant", "content": "I have prepared a formal communication for your review."}
      ]
    }
    ```

    **创建 `tests/prompts/test_session_prompt_miner.py`** — 约 400-500 LoC：

    1. 文件头：
    ```python
    """Unit tests for evolution/prompts/session_prompt_miner.py (Phase 19).

    Mocks all LLM calls (DSPy ChainOfThought). Real LLM is never invoked.

    Decisions covered:
        D-01..D-09: 4-way signal extractors + ConfirmBehavioralExample judge
        D-13:       Train-only sample duplication
        D-15:       Hash-bucket split (70/15/15)
        D-23:       Secret filter via _contains_secret
        W5 fix:     Use public `__annotations__` API to verify Signature OutputFields;
                    do NOT rely on private DSPy marker `__dspy_field_type` (which
                    can break across DSPy versions).
    """

    import json
    from pathlib import Path
    from unittest.mock import MagicMock, patch

    import pytest

    from evolution.prompts.session_prompt_miner import (
        SessionPromptMiner, DEFAULT_MULTIPLIER, VALID_SIGNALS,
        Candidate, Verdict, split_and_duplicate,
        ConfirmBehavioralExample, DetectUserCorrection,
    )
    from evolution.prompts.prompt_dataset import (
        PromptBehavioralExample, _normalize_task_hash, _hash_to_split,
    )
    from evolution.prompts.prompt_loader import PromptSection


    FIXTURES_DIR = Path(__file__).parent / "fixtures"
    SESSIONS_DIR = FIXTURES_DIR / "sessions"


    @pytest.fixture
    def mock_config():
        cfg = MagicMock()
        cfg.judge_model = "mock-model"
        cfg.eval_model = "mock-model"
        cfg.get_lm_kwargs = MagicMock(return_value={})
        return cfg


    @pytest.fixture
    def current_sections():
        """4 named sections + 3 platform_hints sub-sections."""
        return [
            PromptSection(section_id="default_agent_identity", text="be helpful", char_count=10, line_range=(1, 1), source_path=Path("x")),
            PromptSection(section_id="memory_guidance", text="remember user", char_count=13, line_range=(2, 2), source_path=Path("x")),
            PromptSection(section_id="session_search_guidance", text="search past", char_count=11, line_range=(3, 3), source_path=Path("x")),
            PromptSection(section_id="skills_guidance", text="use skills", char_count=10, line_range=(4, 4), source_path=Path("x")),
            PromptSection(section_id="platform_hints.macos", text="mac", char_count=3, line_range=(5, 5), source_path=Path("x")),
        ]


    @pytest.fixture
    def dummy_drift_thresholds(monkeypatch):
        """
        Stub DriftDetector LM dependency so the detector can be instantiated
        without a real API key.

        Constraint (W6 fix): DriftDetector instantiation MUST happen AFTER this
        fixture is applied; monkeypatch.setattr only intercepts subsequent
        dspy.LM(...) constructions. Therefore consumer tests must call
        SessionPromptMiner(..., drift_thresholds=dummy_drift_thresholds) inside
        the test body, AFTER this fixture has run. Constructing the miner
        eagerly in another fixture would bypass the monkeypatch and trigger
        a real LM init.

        Lifecycle:
            1. monkeypatch.setattr patches dspy.LM (active for the duration
               of the test using this fixture).
            2. Test body constructs SessionPromptMiner with these thresholds
               → DriftDetector internally calls dspy.LM(...) → returns MagicMock.
            3. Fixture teardown reverts the dspy.LM patch automatically.
        """
        import dspy
        monkeypatch.setattr(dspy, "LM", lambda *a, **k: MagicMock())
        return {"tone": 0.5, "formality": 0.5, "vocabulary": 0.5, "persona": 0.5}


    @pytest.fixture
    def confirm_judge_mock():
        """Default judge returns a 'confirm_example' for memory_guidance."""
        m = MagicMock(return_value=MagicMock(
            verdict="confirm_example",
            section_id="memory_guidance",
            expected_behavior="Acknowledge user already said this",
            difficulty="medium",
            rationale="user_correction signal",
        ))
        return m


    @pytest.fixture
    def user_correction_judge_mock():
        m = MagicMock(return_value=MagicMock(is_correction=True))
        return m
    ```

    2. 25+ 测试函数：(每个 ≤25 LoC，主要由 fixture 提供共享上下文。完整测试函数清单见 behavior 块)

    Sample 关键测试：
    ```python
    class TestExtractUserCorrection:
        def test_keyword_hit_llm_confirms(self, mock_config, user_correction_judge_mock):
            m = SessionPromptMiner(mock_config)
            m.user_correction_judge = user_correction_judge_mock
            msgs = [
                {"role": "user", "content": "q"},
                {"role": "assistant", "content": "a"},
                {"role": "user", "content": "don't apologize"},
            ]
            cands = m._extract_user_correction(msgs, "s1.json")
            assert len(cands) == 1
            assert cands[0].signal == "user_correction"
            assert m.metrics["total_candidates_by_signal"]["user_correction"] == 1

        def test_keyword_hit_llm_rejects(self, mock_config):
            m = SessionPromptMiner(mock_config)
            m.user_correction_judge = MagicMock(return_value=MagicMock(is_correction=False))
            msgs = [
                {"role": "user", "content": "q"},
                {"role": "assistant", "content": "a"},
                {"role": "user", "content": "don't apologize"},
            ]
            assert m._extract_user_correction(msgs, "s1.json") == []

        def test_no_keyword(self, mock_config):
            m = SessionPromptMiner(mock_config)
            msgs = [
                {"role": "user", "content": "q"},
                {"role": "assistant", "content": "a"},
                {"role": "user", "content": "thanks great"},
            ]
            assert m._extract_user_correction(msgs, "s1.json") == []

        def test_signal_not_active(self, mock_config):
            m = SessionPromptMiner(mock_config, signals=["persona_drift"])
            assert m._extract_user_correction([], "x") == []


    class TestExtractSectionSpecificFailure:
        @pytest.mark.parametrize("user_msg,expected_sid", [
            ("I already told you yesterday", "memory_guidance"),
            ("You didn't use the search skill", "skills_guidance"),
            ("Let me restate, same question:", "session_search_guidance"),
            ("Stop being too formal please", "default_agent_identity"),
        ])
        def test_per_section_match(self, mock_config, user_msg, expected_sid):
            m = SessionPromptMiner(mock_config)
            msgs = [
                {"role": "assistant", "content": "previous response"},
                {"role": "user", "content": user_msg},
            ]
            cands = m._extract_section_specific_failure(msgs, "s")
            assert any(c.section_id == expected_sid for c in cands), (user_msg, [c.section_id for c in cands])

        def test_platform_hints_macos(self, mock_config):
            m = SessionPromptMiner(mock_config)
            msgs = [
                {"role": "assistant", "content": "use ls -al"},
                {"role": "user", "content": "on macOS that's wrong"},
            ]
            cands = m._extract_section_specific_failure(msgs, "s")
            assert any(c.section_id == "platform_hints.macos" for c in cands), [c.section_id for c in cands]


    class TestExtractPersonaDrift:
        def test_no_detector_returns_empty(self, mock_config):
            m = SessionPromptMiner(mock_config, signals=["persona_drift"])
            assert m.drift_detector is None
            assert m._extract_persona_drift([], "x") == []

        def test_below_min_turns(self, mock_config, dummy_drift_thresholds):
            # W6 fix: construct miner INSIDE test body, after fixture-applied monkeypatch
            m = SessionPromptMiner(mock_config, signals=["persona_drift"], drift_thresholds=dummy_drift_thresholds)
            assert m.drift_detector is not None
            msgs = [{"role": "assistant", "content": f"t{i}"} for i in range(5)]
            assert m._extract_persona_drift(msgs, "x") == []

        def test_exceeded_dims(self, mock_config, dummy_drift_thresholds):
            # W6 fix: instantiate after fixture has patched dspy.LM
            m = SessionPromptMiner(mock_config, signals=["persona_drift"], drift_thresholds=dummy_drift_thresholds)
            m.drift_detector._check_one_run = MagicMock(return_value=(
                {"tone": 0.9, "formality": 0.05, "vocabulary": 0.9, "persona": 0.05}, "expl"
            ))
            msgs = [{"role": "user", "content": "q"}] + [{"role": "assistant", "content": f"a{i}"} for i in range(9)]
            cands = m._extract_persona_drift(msgs, "x")
            assert len(cands) == 2  # tone + vocabulary exceeded
            assert all(c.signal == "persona_drift" for c in cands)

        def test_uses_check_one_run_not_check(self, mock_config, dummy_drift_thresholds):
            m = SessionPromptMiner(mock_config, signals=["persona_drift"], drift_thresholds=dummy_drift_thresholds)
            check_one_run_mock = MagicMock(return_value=({"tone": 0, "formality": 0, "vocabulary": 0, "persona": 0}, ""))
            check_mock = MagicMock()
            m.drift_detector._check_one_run = check_one_run_mock
            m.drift_detector.check = check_mock
            msgs = [{"role": "assistant", "content": f"a{i}"} for i in range(9)]
            m._extract_persona_drift(msgs, "x")
            assert check_one_run_mock.called
            assert not check_mock.called  # D-04 explicit: 1-run NOT 3-run at recall stage


    class TestJudgeCandidates:
        def test_confirm_example(self, mock_config, confirm_judge_mock):
            m = SessionPromptMiner(mock_config)
            m.judge = confirm_judge_mock
            cands = [Candidate(task="t", session_path="s", signal="user_correction", originally_observed_behavior="o", downstream_context="d")]
            verdicts = m._judge_candidates(cands, [])
            assert verdicts[0][1].verdict == "confirm_example"
            assert m.metrics["judge_confirmed_by_signal"]["user_correction"] == 1
            assert m.metrics["judge_calls"] == 1

        def test_difficulty_fallback_on_invalid(self, mock_config):
            m = SessionPromptMiner(mock_config)
            m.judge = MagicMock(return_value=MagicMock(verdict="confirm_example", section_id="memory_guidance", expected_behavior="b", difficulty="LARGE", rationale="r"))
            cands = [Candidate(task="t", session_path="s", signal="user_correction", originally_observed_behavior="o", downstream_context="d")]
            verdicts = m._judge_candidates(cands, [])
            assert verdicts[0][1].difficulty == "medium"  # D-12 fallback

        def test_verdict_fallback_on_invalid(self, mock_config):
            m = SessionPromptMiner(mock_config)
            m.judge = MagicMock(return_value=MagicMock(verdict="GARBAGE", section_id="memory_guidance", expected_behavior="b", difficulty="easy", rationale="r"))
            cands = [Candidate(task="t", session_path="s", signal="user_correction", originally_observed_behavior="o", downstream_context="d")]
            verdicts = m._judge_candidates(cands, [])
            assert verdicts[0][1].verdict == "false_positive"
            assert m.metrics["judge_false_positives_by_signal"]["user_correction"] == 1

        def test_exception_fallback(self, mock_config):
            m = SessionPromptMiner(mock_config)
            m.judge = MagicMock(side_effect=Exception("LLM failed"))
            cands = [Candidate(task="t", session_path="s", signal="user_correction", originally_observed_behavior="o", downstream_context="d")]
            verdicts = m._judge_candidates(cands, [])
            assert verdicts[0][1].verdict == "false_positive"
            assert verdicts[0][1].difficulty == "medium"


    class TestSignaturePublicAPI:
        """W5 fix: validate Signatures via public __annotations__ API.

        Do NOT use DSPy private marker __dspy_field_type — it is a private
        implementation detail that has historically changed name across DSPy
        versions. Public API is the field names declared in __annotations__.
        """

        def test_confirm_behavioral_example_output_fields(self):
            expected = {"verdict", "section_id", "expected_behavior", "difficulty", "rationale"}
            actual = set(ConfirmBehavioralExample.__annotations__.keys())
            missing = expected - actual
            assert not missing, (
                f"ConfirmBehavioralExample missing OutputFields: {missing}; "
                f"actual annotations: {actual}"
            )

        def test_detect_user_correction_output_fields(self):
            assert "is_correction" in DetectUserCorrection.__annotations__, (
                f"DetectUserCorrection missing is_correction; "
                f"annotations: {set(DetectUserCorrection.__annotations__.keys())}"
            )


    class TestFilters:
        def test_secret_filter_drops_jwt(self, mock_config):
            m = SessionPromptMiner(mock_config)
            jwt = "eyJ" + "a" * 100 + ".eyJpZCI6MX0.signaturepad" + "x" * 80
            cands = [Candidate(task=jwt, session_path="s", signal="user_correction", originally_observed_behavior="", downstream_context="")]
            kept = m._filter_secrets(cands)
            assert kept == []
            assert m.metrics["secret_filter_skipped"] == 1

        def test_drift_filter_drops_unknown_section(self, mock_config):
            m = SessionPromptMiner(mock_config)
            pairs = [
                (Candidate(task="t", session_path="s", signal="user_correction", originally_observed_behavior="", downstream_context=""),
                 Verdict(verdict="confirm_example", section_id="invented_section", expected_behavior="x", difficulty="easy", rationale="")),
            ]
            kept = m._filter_drift(pairs, current_section_ids={"memory_guidance"})
            assert kept == []
            assert m.metrics["surface_drift_dropped"] == 1
            assert m.metrics["surface_drift_sections"]["invented_section"] == 1


    class TestMineEndToEnd:
        def test_empty_dir(self, mock_config, current_sections, tmp_path):
            m = SessionPromptMiner(mock_config)
            assert m.mine(tmp_path, current_sections) == []

        def test_single_session_flow(self, mock_config, current_sections, tmp_path, confirm_judge_mock, user_correction_judge_mock):
            m = SessionPromptMiner(mock_config)
            m.judge = confirm_judge_mock
            m.user_correction_judge = user_correction_judge_mock
            (tmp_path / "s.json").write_text(json.dumps({
                "messages": [
                    {"role": "user", "content": "q"},
                    {"role": "assistant", "content": "a"},
                    {"role": "user", "content": "don't apologize"},
                ]
            }))
            out = m.mine(tmp_path, current_sections)
            assert len(out) == 1
            assert out[0].source == "session"
            assert out[0].mining_signals == ["user_correction"]
            assert out[0].section_id == "memory_guidance"  # what mock judge returned

        def test_dedup_same_hash_different_signals(self, mock_config, current_sections, tmp_path):
            """Same user_message hit by 2 signals → 1 example, mining_signals union."""
            m = SessionPromptMiner(mock_config, signals=["user_correction", "section_specific_failure"])
            m.judge = MagicMock(return_value=MagicMock(verdict="confirm_example", section_id="memory_guidance", expected_behavior="b", difficulty="easy", rationale="r"))
            m.user_correction_judge = MagicMock(return_value=MagicMock(is_correction=True))
            (tmp_path / "s.json").write_text(json.dumps({
                "messages": [
                    {"role": "assistant", "content": "previous"},
                    {"role": "user", "content": "I already told you, stop apologizing"},
                ]
            }))
            out = m.mine(tmp_path, current_sections)
            assert len(out) == 1
            assert sorted(out[0].mining_signals) == sorted(["user_correction", "section_specific_failure"])


    class TestSplitAndDuplicate:
        def _train_msg(self):
            """Find a message that hashes to 'train' bucket."""
            i = 0
            while True:
                m = f"msg_{i}"
                if _hash_to_split(_normalize_task_hash(m)) == "train":
                    return m
                i += 1
                assert i < 10000

        def test_user_correction_3x(self):
            ex = PromptBehavioralExample(section_id="x", user_message=self._train_msg(), expected_behavior="e", source="session", mining_signals=["user_correction"])
            train, val, holdout = split_and_duplicate([ex])
            assert len(train) == 3 and len(val) == 0 and len(holdout) == 0

        def test_persona_drift_2x(self):
            i = 0
            while True:
                m = f"pdrift_{i}"
                if _hash_to_split(_normalize_task_hash(m)) == "train":
                    break
                i += 1
            ex = PromptBehavioralExample(section_id="x", user_message=m, expected_behavior="e", source="session", mining_signals=["persona_drift"])
            train, _, _ = split_and_duplicate([ex])
            assert len(train) == 2

        def test_max_not_product(self):
            i = 0
            while True:
                m = f"combo_{i}"
                if _hash_to_split(_normalize_task_hash(m)) == "train":
                    break
                i += 1
            ex = PromptBehavioralExample(section_id="x", user_message=m, expected_behavior="e", source="session", mining_signals=["user_correction", "persona_drift"])
            train, _, _ = split_and_duplicate([ex])
            assert len(train) == 3  # max(3, 2) = 3, NOT product=6

        def test_val_holdout_no_dup(self):
            i = 0
            val_msg = holdout_msg = None
            while not val_msg or not holdout_msg:
                m = f"vh_{i}"
                s = _hash_to_split(_normalize_task_hash(m))
                if s == "val" and not val_msg:
                    val_msg = m
                elif s == "holdout" and not holdout_msg:
                    holdout_msg = m
                i += 1
                assert i < 10000
            ex_v = PromptBehavioralExample(section_id="x", user_message=val_msg, expected_behavior="e", source="session", mining_signals=["user_correction"])
            ex_h = PromptBehavioralExample(section_id="x", user_message=holdout_msg, expected_behavior="e", source="session", mining_signals=["user_correction"])
            _, val, holdout = split_and_duplicate([ex_v, ex_h])
            assert len(val) == 1
            assert len(holdout) == 1


    class TestHashSplitDistribution:
        def test_uniform_distribution(self):
            import collections
            cnt = collections.Counter(_hash_to_split(_normalize_task_hash(f"x{i}")) for i in range(1000))
            assert cnt["train"] > 600 and cnt["train"] < 800
            assert cnt["val"] > 100 and cnt["val"] < 200
            assert cnt["holdout"] > 100 and cnt["holdout"] < 200
    ```

    依据 (per D-01..D-15/D-23 + W5/W6 fix)：
    - 所有 LLM call 通过 MagicMock 替换（zero real API）— SessionPromptMiner.judge / user_correction_judge / drift_detector._check_one_run 都 mock 替换
    - **W5 fix**：`TestSignaturePublicAPI` 显式用 `__annotations__` 公共 API 检查 OutputField；测试代码中不出现 `__dspy_field_type`
    - **W6 fix**：`dummy_drift_thresholds` fixture docstring 显式说明 monkeypatch 时序约束：DriftDetector 必须在 fixture 应用之后实例化（测试体内构造）；不能在 fixture chain 提前 eager 构造
  </action>

  <verify>
    <automated>cd /Users/slj/项目/hermes-agent-self-evolution &amp;&amp; python -m pytest tests/prompts/test_session_prompt_miner.py -x -q 2>&amp;1 | tail -30</automated>
  </verify>

  <acceptance_criteria>
    - 4 fixture 文件存在：`ls tests/prompts/fixtures/sessions/session_normal.json tests/prompts/fixtures/sessions/session_with_secret.json tests/prompts/fixtures/sessions/session_persona_drift.json tests/prompts/fixtures/drift_thresholds.json` 全部输出（无报错）
    - `tests/prompts/test_session_prompt_miner.py` 存在
    - `wc -l tests/prompts/test_session_prompt_miner.py` ≥ 350 行
    - `grep -c "^    def test_" tests/prompts/test_session_prompt_miner.py` ≥ 20
    - `grep -nE "check_one_run_mock.called" tests/prompts/test_session_prompt_miner.py` 命中（D-04 1-run vs 3-run regression guard）
    - `grep -nE "secret_filter_skipped" tests/prompts/test_session_prompt_miner.py` 命中
    - `grep -nE "surface_drift_dropped" tests/prompts/test_session_prompt_miner.py` 命中
    - **W5 fix acceptance**：`grep -nE "ConfirmBehavioralExample.__annotations__" tests/prompts/test_session_prompt_miner.py` 命中（公共 API 用法）
    - **W5 fix acceptance**：`grep -nE "__dspy_field_type" tests/prompts/test_session_prompt_miner.py` 输出**空**（不依赖 DSPy 私有 marker）
    - **W6 fix acceptance**：`grep -nE "Constraint \(W6 fix\): DriftDetector instantiation MUST happen AFTER" tests/prompts/test_session_prompt_miner.py` 命中（fixture docstring 显式时序约束）
    - `python -m pytest tests/prompts/test_session_prompt_miner.py -x -q` 全部通过
    - 无真实 LLM 调用：grep test 文件 `grep -nE "dspy\.LM\(['\"]openai" tests/prompts/test_session_prompt_miner.py` 输出空（全部 mock）
    - 全部 prompt 测试套件无 regression：`python -m pytest tests/prompts/ -x -q`
  </acceptance_criteria>

  <done>
    Session miner 单元测试套件 25+ 通过；4 个 fixture 落地；mock 替换 LLM 全程零真实 API；secret filter / surface drift / 1-run vs 3-run 三大 regression guard 显式覆盖。W5 fix：Signature 验证走 `__annotations__` 公共 API；W6 fix：dummy_drift_thresholds fixture docstring 显式说明 monkeypatch 时序约束。
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 5.2: tests/prompts/test_mine_prompt_sessions_cli.py（CLI 集成测试）</name>
  <files>tests/prompts/test_mine_prompt_sessions_cli.py</files>

  <read_first>
    - evolution/prompts/mine_prompt_sessions.py（Plan 03 产物，重点 _parse_signals / _parse_multiplier_override / mine() 主体）
    - tests/prompts/test_session_prompt_miner.py（Task 5.1 产物 — 共享 fixtures pattern）
    - Click testing docs (本地试 `python -c "from click.testing import CliRunner"` 验证可用)
    - tests/prompts/conftest.py（确认 fixture 集）
  </read_first>

  <behavior>
    至少 15 测试覆盖：
    - test_help_lists_all_13_flags: --help exit 0 + stdout 含 13 flag 名
    - test_consent_gate_missing: 不传 --i-have-consent → exit non-0 + stderr 含 "--i-have-consent" 和 "~/.hermes/sessions"
    - test_consent_gate_present_succeeds_dry_run: --i-have-consent + --dry-run + mock everything → exit 0
    - test_parse_signals_valid: _parse_signals("user_correction,persona_drift") = ["user_correction","persona_drift"]
    - test_parse_signals_unknown_raises: _parse_signals("user_correction,xxx") 抛 UsageError
    - test_parse_signals_empty_raises: _parse_signals("") 抛 UsageError
    - test_parse_multiplier_valid: _parse_multiplier_override("uc=5,pd=2") with valid keys returns correct dict
    - test_parse_multiplier_invalid_int: _parse_multiplier_override("user_correction=NaN") 抛 UsageError
    - test_failed_sessions_dir_missing: --sessions-dir /missing → exit 1 + FAILED_<ts>/metrics.json 含 error='sessions_dir_missing'
    - test_failed_no_examples_post_judge: mock miner.mine() 返回 [] → exit 1 + FAILED_<ts>/metrics.json 含 error='no_examples_post_judge'
    - test_dry_run_skips_llm_judge: --dry-run + mock miner → miner.mine NOT called, candidate 估算 printed
    - test_persona_drift_missing_thresholds_graceful_disable (W2 fix): --signals=persona_drift + --drift-thresholds-path 指向不存在文件 → 不在 parse 阶段拒绝；mine() 内 lazy check + warn + 从 signals_list 移除 persona_drift；exit 0 if other signals produce examples
    - test_oracle_disagreement_missing_baseline_graceful: --signals=oracle_disagreement + 不传 --baseline-module → warn + 继续 (exit 0 if examples non-empty after other signals)
    - test_success_writes_5_files: mock miner returns 3 examples → out_dir 含 train.jsonl + val.jsonl + holdout.jsonl + metrics.json + miner_log.jsonl 5 文件
    - test_judge_model_override: --judge-model "my-model" → mock SessionPromptMiner 构造时 config.judge_model='my-model'
    - test_behavioral_multiplier_threaded: --behavioral-multiplier "user_correction=5" → 传给 SessionPromptMiner 的 multiplier_override={'user_correction':5}
  </behavior>

  <action>
    创建 `tests/prompts/test_mine_prompt_sessions_cli.py` ~300 LoC：

    1. 文件头与 fixtures：
    ```python
    """Integration tests for evolution/prompts/mine_prompt_sessions CLI (Phase 19).

    Uses click.testing.CliRunner. Mocks SessionPromptMiner / DriftDetector /
    EvolutionConfig / extract_prompt_sections to avoid real LLM and filesystem
    coupling.

    Decisions covered:
        D-17: 13 Click flags
        D-25: --i-have-consent gate
        D-20: 5-file output (train/val/holdout.jsonl + metrics.json + miner_log.jsonl)
        D-04: persona_drift / oracle_disagreement graceful disable
        D-14: --behavioral-multiplier parsing + threading
        W2 fix: --drift-thresholds-path missing must NOT block at Click parse
                — lazy-checked in mine() body, symmetric with oracle disabled
    """

    import json
    import os
    from pathlib import Path
    from unittest.mock import patch, MagicMock

    import pytest
    from click.testing import CliRunner

    from evolution.prompts import mine_prompt_sessions
    from evolution.prompts.mine_prompt_sessions import (
        main as cli_main,
        _parse_signals,
        _parse_multiplier_override,
    )
    from evolution.prompts.prompt_loader import PromptSection


    @pytest.fixture
    def runner():
        return CliRunner()


    @pytest.fixture
    def fake_sections():
        return [
            PromptSection(section_id="default_agent_identity", text="x", char_count=1, line_range=(1, 1), source_path=Path("x")),
            PromptSection(section_id="memory_guidance", text="x", char_count=1, line_range=(2, 2), source_path=Path("x")),
        ]


    @pytest.fixture
    def mock_environment(tmp_path, fake_sections):
        """Mock EvolutionConfig + extract_prompt_sections + SessionPromptMiner."""
        cfg = MagicMock()
        cfg.hermes_agent_path = tmp_path
        cfg.judge_model = "default-mock"
        cfg.eval_model = "default-mock"
        cfg.get_lm_kwargs = MagicMock(return_value={})

        # Pre-create drift_thresholds.json so default Click path exists
        thresholds = tmp_path / "drift_thresholds.json"
        thresholds.write_text(json.dumps({
            "tone": 0.5, "formality": 0.5, "vocabulary": 0.5, "persona": 0.5,
        }))

        with patch.object(mine_prompt_sessions, "EvolutionConfig") as MC, \
             patch.object(mine_prompt_sessions, "extract_prompt_sections") as MS, \
             patch.object(mine_prompt_sessions, "SessionPromptMiner") as MM, \
             patch.object(mine_prompt_sessions, "split_and_duplicate") as SAD:
            MC.load.return_value = cfg
            MS.return_value = fake_sections
            miner_inst = MagicMock()
            miner_inst.metrics = {
                "total_candidates_by_signal": {s: 0 for s in ("user_correction","section_specific_failure","oracle_disagreement","persona_drift")},
                "judge_confirmed_by_signal": {s: 0 for s in ("user_correction","section_specific_failure","oracle_disagreement","persona_drift")},
                "judge_false_positives_by_signal": {s: 0 for s in ("user_correction","section_specific_failure","oracle_disagreement","persona_drift")},
                "judge_calls_by_signal": {s: 0 for s in ("user_correction","section_specific_failure","oracle_disagreement","persona_drift")},
                "surface_drift_dropped": 0,
                "surface_drift_sections": {},
                "secret_filter_skipped": 0,
                "session_load_failures": 0,  # B3 fix: separate field
                "jsonl_skipped_lines": 0,
                "judge_calls": 0,
                "final_examples_by_split": {"train": 0, "val": 0, "holdout": 0},
                "final_train_after_duplication": 0,
                "mining_multiplier_used": {},
                "persona_drift_thresholds_used": {},
                "oracle_baseline_path": None,
                "judge_model": "default-mock",
            }
            miner_inst._load_session = MagicMock(return_value={"messages": []})
            miner_inst._extract_user_correction = MagicMock(return_value=[])
            miner_inst._extract_section_specific_failure = MagicMock(return_value=[])
            miner_inst._extract_oracle_disagreement = MagicMock(return_value=[])
            miner_inst._extract_persona_drift = MagicMock(return_value=[])
            miner_inst._filter_secrets = MagicMock(side_effect=lambda x: x)
            miner_inst.mine = MagicMock(return_value=[])
            MM.return_value = miner_inst
            SAD.return_value = ([], [], [])
            yield {
                "EvolutionConfig": MC, "extract_prompt_sections": MS,
                "SessionPromptMiner": MM, "split_and_duplicate": SAD,
                "miner_inst": miner_inst, "config": cfg,
                "tmp_path": tmp_path, "thresholds_path": thresholds,
            }


    class TestHelpAndFlags:
        def test_help_lists_all_13_flags(self, runner):
            r = runner.invoke(cli_main, ["--help"])
            assert r.exit_code == 0
            for flag in [
                "--sessions-dir", "--output", "--limit", "--i-have-consent",
                "--signals", "--baseline-module", "--judge-model",
                "--behavioral-multiplier", "--hermes-repo", "--model",
                "--api-base", "--dry-run", "--drift-thresholds-path",
            ]:
                assert flag in r.output, f"missing {flag}"


    class TestConsentGate:
        def test_consent_missing_exits_nonzero(self, runner):
            r = runner.invoke(cli_main, [])
            assert r.exit_code != 0
            assert "--i-have-consent" in (r.stderr_bytes.decode() if r.stderr_bytes else r.output)

        def test_consent_present_proceeds(self, runner, mock_environment):
            sessions = mock_environment["tmp_path"] / "sessions"
            sessions.mkdir()
            r = runner.invoke(cli_main, [
                "--i-have-consent", "--sessions-dir", str(sessions),
                "--drift-thresholds-path", str(mock_environment["thresholds_path"]),
                "--dry-run", "--signals", "user_correction",
            ])
            # Dry-run with no candidates returns 0 (success)
            assert r.exit_code == 0, r.output


    class TestParsers:
        def test_parse_signals_valid(self):
            assert _parse_signals("user_correction,persona_drift") == ["user_correction", "persona_drift"]

        def test_parse_signals_unknown_raises(self):
            import click
            with pytest.raises(click.UsageError, match="unknown"):
                _parse_signals("user_correction,xxx")

        def test_parse_signals_empty_raises(self):
            import click
            with pytest.raises(click.UsageError, match="empty"):
                _parse_signals("")

        def test_parse_multiplier_valid(self):
            assert _parse_multiplier_override("user_correction=5,persona_drift=2") == {
                "user_correction": 5, "persona_drift": 2,
            }

        def test_parse_multiplier_invalid_int(self):
            import click
            with pytest.raises(click.UsageError, match="int"):
                _parse_multiplier_override("user_correction=NaN")

        def test_parse_multiplier_none_returns_empty(self):
            assert _parse_multiplier_override(None) == {}


    class TestFailurePaths:
        def test_sessions_dir_missing(self, runner, tmp_path, mock_environment):
            os.chdir(tmp_path)
            r = runner.invoke(cli_main, [
                "--i-have-consent",
                "--sessions-dir", str(tmp_path / "nonexistent"),
                "--drift-thresholds-path", str(mock_environment["thresholds_path"]),
            ])
            assert r.exit_code == 1
            failed_dirs = list((tmp_path / "datasets" / "prompts" / "sessions").glob("FAILED_*"))
            assert len(failed_dirs) >= 1
            metrics = json.loads((failed_dirs[0] / "metrics.json").read_text())
            assert metrics["error"] == "sessions_dir_missing"

        def test_no_examples_post_judge(self, runner, tmp_path, mock_environment):
            os.chdir(tmp_path)
            sessions = tmp_path / "sessions"; sessions.mkdir()
            (sessions / "s.json").write_text(json.dumps({"messages": []}))
            # miner.mine returns [] (default mock)
            r = runner.invoke(cli_main, [
                "--i-have-consent",
                "--sessions-dir", str(sessions),
                "--drift-thresholds-path", str(mock_environment["thresholds_path"]),
            ])
            assert r.exit_code == 1
            failed_dirs = list((tmp_path / "datasets" / "prompts" / "sessions").glob("FAILED_*"))
            metrics = json.loads((failed_dirs[0] / "metrics.json").read_text())
            assert metrics["error"] == "no_examples_post_judge"


    class TestDryRun:
        def test_dry_run_skips_judge(self, runner, tmp_path, mock_environment):
            os.chdir(tmp_path)
            sessions = tmp_path / "sessions"; sessions.mkdir()
            (sessions / "s.json").write_text(json.dumps({"messages": []}))
            r = runner.invoke(cli_main, [
                "--i-have-consent",
                "--sessions-dir", str(sessions),
                "--drift-thresholds-path", str(mock_environment["thresholds_path"]),
                "--dry-run", "--signals", "user_correction",
            ])
            assert r.exit_code == 0
            # miner.mine NOT called
            assert not mock_environment["miner_inst"].mine.called


    class TestGracefulDisable:
        def test_oracle_missing_baseline_warns(self, runner, tmp_path, mock_environment):
            os.chdir(tmp_path)
            sessions = tmp_path / "sessions"; sessions.mkdir()
            (sessions / "s.json").write_text(json.dumps({"messages": []}))
            r = runner.invoke(cli_main, [
                "--i-have-consent",
                "--sessions-dir", str(sessions),
                "--drift-thresholds-path", str(mock_environment["thresholds_path"]),
                "--dry-run",
                "--signals", "oracle_disagreement,user_correction",
            ])
            # Should not fail
            assert r.exit_code == 0
            # Warning printed
            assert "oracle_disagreement signal disabled" in r.output or "baseline" in r.output.lower()

        def test_persona_drift_missing_thresholds_graceful(self, runner, tmp_path, mock_environment):
            """W2 fix: missing --drift-thresholds-path file must NOT block at Click
            parse stage; should be lazy-checked in mine() and disable persona_drift
            symmetrically with oracle_disagreement graceful disable."""
            os.chdir(tmp_path)
            sessions = tmp_path / "sessions"; sessions.mkdir()
            (sessions / "s.json").write_text(json.dumps({"messages": []}))
            missing_thresholds = tmp_path / "missing_thresholds.json"
            assert not missing_thresholds.exists()
            r = runner.invoke(cli_main, [
                "--i-have-consent",
                "--sessions-dir", str(sessions),
                "--drift-thresholds-path", str(missing_thresholds),
                "--dry-run",
                "--signals", "persona_drift,user_correction",
            ])
            # Critical W2 assertion: Click must NOT reject at parse stage
            assert "Invalid value" not in r.output, (
                "W2 fix regression: Click rejected missing --drift-thresholds-path "
                "before reaching consent/mine() body. Remove exists=True from the option.")
            # Should reach mine() body, warn about persona_drift, and continue
            assert r.exit_code == 0, r.output
            assert "persona_drift" in r.output.lower()


    class TestSuccessOutput:
        def test_writes_5_files(self, runner, tmp_path, mock_environment):
            os.chdir(tmp_path)
            sessions = tmp_path / "sessions"; sessions.mkdir()
            (sessions / "s.json").write_text(json.dumps({"messages": []}))
            # Override miner.mine to return non-empty
            from evolution.prompts.prompt_dataset import PromptBehavioralExample
            ex = PromptBehavioralExample(section_id="memory_guidance", user_message="m", expected_behavior="e", source="session", mining_signals=["user_correction"])
            mock_environment["miner_inst"].mine.return_value = [ex]
            mock_environment["split_and_duplicate"].return_value = ([ex] * 3, [], [])
            r = runner.invoke(cli_main, [
                "--i-have-consent",
                "--sessions-dir", str(sessions),
                "--drift-thresholds-path", str(mock_environment["thresholds_path"]),
                "--output", str(tmp_path / "out"),
                "--signals", "user_correction",
            ])
            assert r.exit_code == 0, r.output
            out = tmp_path / "out"
            for fname in ["train.jsonl", "val.jsonl", "holdout.jsonl", "metrics.json", "miner_log.jsonl"]:
                assert (out / fname).exists(), f"missing {fname}"


    class TestParameterThreading:
        def test_judge_model_override(self, runner, tmp_path, mock_environment):
            os.chdir(tmp_path)
            sessions = tmp_path / "sessions"; sessions.mkdir()
            (sessions / "s.json").write_text(json.dumps({"messages": []}))
            runner.invoke(cli_main, [
                "--i-have-consent", "--sessions-dir", str(sessions),
                "--drift-thresholds-path", str(mock_environment["thresholds_path"]),
                "--judge-model", "my-test-model", "--dry-run",
                "--signals", "user_correction",
            ])
            # Config object should have judge_model overridden
            assert mock_environment["config"].judge_model == "my-test-model"

        def test_behavioral_multiplier_threaded(self, runner, tmp_path, mock_environment):
            os.chdir(tmp_path)
            sessions = tmp_path / "sessions"; sessions.mkdir()
            (sessions / "s.json").write_text(json.dumps({"messages": []}))
            runner.invoke(cli_main, [
                "--i-have-consent", "--sessions-dir", str(sessions),
                "--drift-thresholds-path", str(mock_environment["thresholds_path"]),
                "--behavioral-multiplier", "user_correction=7",
                "--dry-run", "--signals", "user_correction",
            ])
            # SessionPromptMiner was called with multiplier_override
            call_kwargs = mock_environment["SessionPromptMiner"].call_args.kwargs
            assert call_kwargs["multiplier_override"] == {"user_correction": 7}
    ```

    依据 (per D-17/D-25/D-04/D-20 + W2 fix)：
    - CliRunner.invoke + mock_environment fixture 集中 patch 5 个外部依赖（EvolutionConfig / extract_prompt_sections / SessionPromptMiner / split_and_duplicate / 自动创建 drift_thresholds.json）
    - 必须 `os.chdir(tmp_path)` 隔离 FAILED_<ts>/ 写盘（避免污染仓库）
    - **W2 fix 测试**：`test_persona_drift_missing_thresholds_graceful` 显式验证 missing thresholds 路径不在 Click parse 阶段被拒绝；assertion "Invalid value" not in output 是关键退化哨兵
  </action>

  <verify>
    <automated>cd /Users/slj/项目/hermes-agent-self-evolution &amp;&amp; python -m pytest tests/prompts/test_mine_prompt_sessions_cli.py -x -q 2>&amp;1 | tail -30</automated>
  </verify>

  <acceptance_criteria>
    - `tests/prompts/test_mine_prompt_sessions_cli.py` 存在
    - `wc -l tests/prompts/test_mine_prompt_sessions_cli.py` ≥ 250 行
    - `grep -c "def test_" tests/prompts/test_mine_prompt_sessions_cli.py` ≥ 14
    - `grep -nE "i_have_consent|--i-have-consent" tests/prompts/test_mine_prompt_sessions_cli.py` 命中（D-25 显式测试）
    - `grep -nE "FAILED_" tests/prompts/test_mine_prompt_sessions_cli.py` 命中（FAILED 路径测试）
    - `grep -nE "miner_log\.jsonl" tests/prompts/test_mine_prompt_sessions_cli.py` 命中（D-20 5-file 验证）
    - `grep -nE "oracle.*disabled" tests/prompts/test_mine_prompt_sessions_cli.py` 命中（D-04 graceful disable 测试）
    - **W2 fix acceptance**：`grep -nE "test_persona_drift_missing_thresholds_graceful" tests/prompts/test_mine_prompt_sessions_cli.py` 命中（专门 W2 退化哨兵测试）
    - **W2 fix acceptance**：`grep -nE 'Invalid value.+not in' tests/prompts/test_mine_prompt_sessions_cli.py` 命中（asserting Click 不在 parse 阶段拒绝）
    - 全部测试通过：`python -m pytest tests/prompts/test_mine_prompt_sessions_cli.py -x -q`
    - 整个 prompt 测试套件无 regression：`python -m pytest tests/prompts/ -x -q`
  </acceptance_criteria>

  <done>
    CLI 端到端集成测试套件 14+ 测试全部通过；consent gate / dry-run / 3 种 FAILED / 5 文件输出 / graceful disable / 参数 threading 全覆盖。W2 fix 测试：`test_persona_drift_missing_thresholds_graceful` 显式断言 Click 不在 parse 阶段拒绝默认 missing thresholds。
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 5.3: tests/prompts/test_evolve_prompt_sections_session_source.py（--session-source 端到端集成测试）</name>
  <files>tests/prompts/test_evolve_prompt_sections_session_source.py</files>

  <read_first>
    - evolution/prompts/evolve_prompt_sections.py（Plan 04 产物 — 重点 _load_session_dataset_resilient + union block）
    - tests/prompts/test_evolve_prompt_sections_cli.py 既有 TestABBaseline 模式（per STATE.md 18-04/18-05 SUMMARY 提及 _ab_patched_run 风格）— 通过 grep 或目录列查找：`ls tests/prompts/test_evolve_prompt_sections*`
    - tests/prompts/conftest.py
    - Plan 04 SUMMARY（确认 5b 块插入 line + 4 处 Edit）
  </read_first>

  <behavior>
    至少 8 测试覆盖：
    - test_help_has_session_source: --help 含 --session-source 选项
    - test_no_session_source_baseline_unchanged: 不传 --session-source → dry-run 路径与 Phase 18 baseline 行为一致
    - test_invalid_session_source_path_rejected_at_parse: --session-source /missing → exit code != 0 (Click click.Path(exists=True))
    - test_load_session_dataset_resilient_missing_dir: helper called with /missing → 返回 empty dataset + skipped={0,0,0}
    - test_load_session_dataset_resilient_bad_lines: 含坏 JSONL 行 → skip 计数正确 + 5% warn 触发
    - test_union_no_collision: synthetic + session 无 hash collision → train length = synth + session
    - test_union_same_split_collision_session_wins: 同 hash 同 split → session 胜（source='session'）
    - test_union_cross_split_collision_synth_dropped: 同 hash 跨 split（synth-train + session-holdout）→ synth 中该 hash 丢，session 保留在 holdout
    - test_union_works_in_joint_mode: --mode joint + --session-source → dry-run 路径执行 union 块（log 含 "After union"）
    - test_union_works_in_round_robin_mode: --mode round-robin + --session-source → 同上
    - test_step_8c_drift_wiring_intact (W7 fix): 增强 grep 验证 step 8c 文件区块（约 line 508-617）— 精确签名 `DriftDetector(config, drift_thresholds)` + 关键变量名 `drift_per_dim_metrics` + DriftDetector 实例化次数 ≥ 2
    - test_build_drift_calibration_untouched: git diff -- evolution/prompts/build_drift_calibration.py 为空（仅在 commit 后可测；本测试转为 grep `grep -nE 'session-source' evolution/prompts/build_drift_calibration.py` 输出空）
  </behavior>

  <action>
    创建 `tests/prompts/test_evolve_prompt_sections_session_source.py` ~250 LoC：

    1. 文件头：
    ```python
    """Integration tests for evolve_prompt_sections --session-source flag (Phase 19).

    Covers D-21 (union in joint + round-robin), D-16 (hash dedup with session-wins),
    D-22 (no changes to build_drift_calibration.py), D-24 (JSONL bad-line tolerance),
    W7 fix (step 8c regression guard with enhanced precision).

    Uses click.testing.CliRunner with extensive mocking (dspy.LM / configure /
    GEPA / DriftDetector / EvolutionConfig) to avoid real LLM and hermes-agent
    coupling.
    """

    import json
    import subprocess
    from pathlib import Path
    from unittest.mock import patch, MagicMock

    import pytest
    from click.testing import CliRunner

    from evolution.prompts import evolve_prompt_sections
    from evolution.prompts.evolve_prompt_sections import (
        main as evolve_main,
        _load_session_dataset_resilient,
    )
    from evolution.prompts.prompt_dataset import (
        PromptBehavioralDataset, PromptBehavioralExample,
        _normalize_task_hash, _hash_to_split,
    )


    @pytest.fixture
    def runner():
        return CliRunner()


    @pytest.fixture
    def session_source_dir(tmp_path):
        """Create a session-source directory with 1 valid example in train.jsonl."""
        d = tmp_path / "sess"
        d.mkdir()
        (d / "train.jsonl").write_text(
            json.dumps({
                "section_id": "memory_guidance",
                "user_message": "session-only example one",
                "expected_behavior": "remember context",
                "difficulty": "medium",
                "source": "session",
                "mining_signals": ["user_correction"],
            }) + "\n"
        )
        (d / "val.jsonl").write_text("")
        (d / "holdout.jsonl").write_text("")
        return d


    class TestHelpAndParseGate:
        def test_help_includes_session_source(self, runner):
            r = runner.invoke(evolve_main, ["--help"])
            assert r.exit_code == 0
            assert "--session-source" in r.output

        def test_invalid_session_source_rejected(self, runner, tmp_path):
            r = runner.invoke(evolve_main, [
                "--session-source", str(tmp_path / "does_not_exist"),
                "--dry-run",
            ])
            assert r.exit_code != 0


    class TestHelperResilience:
        def test_missing_dir_returns_empty(self):
            ds, sk = _load_session_dataset_resilient(Path("/totally/missing/dir"))
            assert ds.train == [] and ds.val == [] and ds.holdout == []
            assert sk == {"train": 0, "val": 0, "holdout": 0}

        def test_bad_lines_skipped(self, tmp_path):
            d = tmp_path / "s"; d.mkdir()
            (d / "train.jsonl").write_text(
                json.dumps({"section_id": "x", "user_message": "good", "expected_behavior": "e"}) + "\n"
                + "this is not json\n"
                + json.dumps({"section_id": "y", "user_message": "good2", "expected_behavior": "e2"}) + "\n"
            )
            (d / "val.jsonl").write_text("")
            (d / "holdout.jsonl").write_text("")
            ds, sk = _load_session_dataset_resilient(d)
            assert len(ds.train) == 2
            assert sk["train"] == 1


    class TestUnionLogic:
        """Test union behavior in isolation (without invoking full CLI)."""

        def _train_msg(self, prefix):
            i = 0
            while True:
                m = f"{prefix}_{i}"
                if _hash_to_split(_normalize_task_hash(m)) == "train":
                    return m
                i += 1

        def _holdout_msg(self, prefix):
            i = 0
            while True:
                m = f"{prefix}_{i}"
                if _hash_to_split(_normalize_task_hash(m)) == "holdout":
                    return m
                i += 1

        def test_no_collision(self):
            synth_msg = self._train_msg("synth")
            sess_msg = self._train_msg("sess")
            synth = PromptBehavioralDataset(
                train=[PromptBehavioralExample(section_id="x", user_message=synth_msg, expected_behavior="e", source="synthetic")],
                val=[], holdout=[],
            )
            sess = PromptBehavioralDataset(
                train=[PromptBehavioralExample(section_id="x", user_message=sess_msg, expected_behavior="e", source="session", mining_signals=["user_correction"])],
                val=[], holdout=[],
            )
            self._run_union(synth, sess)
            assert len(synth.train) == 2

        def test_same_split_collision_session_wins(self):
            shared_msg = self._train_msg("shared")
            synth = PromptBehavioralDataset(
                train=[PromptBehavioralExample(section_id="x", user_message=shared_msg, expected_behavior="SYNTH", source="synthetic")],
                val=[], holdout=[],
            )
            sess = PromptBehavioralDataset(
                train=[PromptBehavioralExample(section_id="x", user_message=shared_msg, expected_behavior="SESS", source="session", mining_signals=["persona_drift"])],
                val=[], holdout=[],
            )
            self._run_union(synth, sess)
            assert len(synth.train) == 1
            assert synth.train[0].source == "session"
            assert synth.train[0].expected_behavior == "SESS"
            assert synth.train[0].mining_signals == ["persona_drift"]

        def test_cross_split_collision_synth_dropped(self):
            shared = self._holdout_msg("cross_holdout")
            synth = PromptBehavioralDataset(
                train=[PromptBehavioralExample(section_id="x", user_message=shared, expected_behavior="synth", source="synthetic")],
                val=[], holdout=[],
            )
            sess = PromptBehavioralDataset(
                train=[], val=[],
                holdout=[PromptBehavioralExample(section_id="x", user_message=shared, expected_behavior="sess", source="session", mining_signals=["user_correction"])],
            )
            self._run_union(synth, sess)
            assert len(synth.train) == 0  # synth dropped: same hash exists in session.holdout
            assert len(synth.holdout) == 1
            assert synth.holdout[0].source == "session"

        @staticmethod
        def _run_union(dataset, session_dataset):
            """Replicate the 5b union block in isolation."""
            all_session_hashes: set[str] = set()
            session_hashes_by_split = {}
            for split in ("train", "val", "holdout"):
                bs = {_normalize_task_hash(ex.user_message): ex for ex in getattr(session_dataset, split)}
                session_hashes_by_split[split] = bs
                all_session_hashes |= set(bs.keys())
            for split in ("train", "val", "holdout"):
                synth_kept = [
                    ex for ex in getattr(dataset, split)
                    if _normalize_task_hash(ex.user_message) not in all_session_hashes
                ]
                merged = synth_kept + list(session_hashes_by_split[split].values())
                setattr(dataset, split, merged)


    class TestPhase18Untouched:
        """Regression guards: Phase 19 must NOT modify step 8c DriftDetector
        wiring or build_drift_calibration.py."""

        def test_step_8c_drift_wiring_intact(self):
            """W7 fix: enhanced regression guard with precise assertions.

            The DriftDetector wiring inserted by Plan 18-04 must remain.
            Enforces:
              1. DriftDetector( instantiation count ≥ 2 (import + step 8c usage)
              2. Precise signature `DriftDetector(config, drift_thresholds)` present
              3. Key metrics variable `drift_per_dim_metrics` retained
              4. Step 8c output file `drift_report.txt` reference retained
            """
            path = Path("evolution/prompts/evolve_prompt_sections.py")
            content = path.read_text()
            # Enhanced W7 fix assertions:
            assert content.count("DriftDetector(") >= 2, (
                "DriftDetector instantiation count regression — expected ≥ 2 "
                "occurrences (import + step 8c usage)"
            )
            assert "DriftDetector(config, drift_thresholds)" in content, (
                "step 8c DriftDetector signature changed — must remain "
                "`DriftDetector(config, drift_thresholds)`"
            )
            assert "drift_per_dim_metrics" in content, (
                "step 8c metrics variable `drift_per_dim_metrics` missing — "
                "Phase 18 wiring regression"
            )
            assert "drift_report.txt" in content, (
                "step 8c drift_report.txt reference missing"
            )

        def test_build_drift_calibration_untouched(self):
            """Phase 19 D-22: must NOT add --session-source to calibration."""
            path = Path("evolution/prompts/build_drift_calibration.py")
            if not path.exists():
                pytest.skip("build_drift_calibration.py not in tree")
            content = path.read_text()
            assert "--session-source" not in content
            assert "session_source" not in content


    class TestCLIInvocation:
        """Smoke test: --session-source threads through main → evolve."""

        def test_dry_run_with_session_source_does_not_crash(self, runner, session_source_dir, tmp_path):
            # Mock the heavy lifting (EvolutionConfig.load, extract_prompt_sections, etc.)
            # so the CLI reaches the union block in dry-run.
            with patch.object(evolve_prompt_sections, "EvolutionConfig") as MC, \
                 patch.object(evolve_prompt_sections, "extract_prompt_sections") as MS:
                cfg = MagicMock()
                cfg.hermes_agent_path = tmp_path
                cfg.eval_model = "mock"; cfg.judge_model = "mock"; cfg.optimizer_model = "mock"
                cfg.get_lm_kwargs = MagicMock(return_value={})
                MC.load.return_value = cfg
                from evolution.prompts.prompt_loader import PromptSection
                MS.return_value = [PromptSection(section_id="memory_guidance", text="x", char_count=1, line_range=(1, 1), source_path=Path("x"))]
                # Ensure default drift_thresholds.json exists (tmp dir to avoid pollution)
                (tmp_path / "drift_thresholds.json").write_text(json.dumps({
                    "tone": 0.5, "formality": 0.5, "vocabulary": 0.5, "persona": 0.5,
                }))
                r = runner.invoke(evolve_main, [
                    "--dry-run",
                    "--session-source", str(session_source_dir),
                    "--drift-thresholds-path", str(tmp_path / "drift_thresholds.json"),
                ])
                # Dry-run exits before the union block (line ~187 sys.exit) —
                # so this is just a smoke test: argv accepted, no crash before exit.
                # exit_code 0 (clean dry-run) or 1 (env mismatch) are both acceptable;
                # what matters: argv parsing succeeded.
                assert r.exit_code in (0, 1), r.output
    ```

    依据 (per D-16/D-21/D-22/D-24 + W7 fix)：
    - `TestUnionLogic._run_union` 复刻 evolve_prompt_sections.py 5b block 行为，独立验证 union 算法（避免 mock 整个 evolve() 调用栈）
    - `TestPhase18Untouched` 是显式 regression guard — 直接 grep production code 验证 D-22 与 step 8c 不变
    - **W7 fix**：`test_step_8c_drift_wiring_intact` 增强为 4 个精确断言（DriftDetector 实例化计数 + 精确签名 + 关键变量名 + 步骤 8c 输出文件名），不容许任何含糊的 substring 检查
    - `test_cross_split_collision_synth_dropped` 用 hash 落 holdout 的字符串构造可控 cross-split 场景
    - `_train_msg` / `_holdout_msg` helper 暴力枚举找符合 hash bucket 的字符串（确定性，<10k iter）

    **重要注意**：mock_environment 在 fixture 内 `os.chdir(tmp_path)` 之后必须**还原 cwd**（否则后续测试失败）。用 monkeypatch.chdir 或者在 yield 之后 `os.chdir(original_cwd)`。
  </action>

  <verify>
    <automated>cd /Users/slj/项目/hermes-agent-self-evolution &amp;&amp; python -m pytest tests/prompts/test_evolve_prompt_sections_session_source.py -x -q 2>&amp;1 | tail -30</automated>
  </verify>

  <acceptance_criteria>
    - `tests/prompts/test_evolve_prompt_sections_session_source.py` 存在
    - `wc -l tests/prompts/test_evolve_prompt_sections_session_source.py` ≥ 200 行
    - `grep -c "def test_" tests/prompts/test_evolve_prompt_sections_session_source.py` ≥ 8
    - `grep -nE "session_wins|session.wins" tests/prompts/test_evolve_prompt_sections_session_source.py` 命中（D-16 显式测试）
    - `grep -nE "TestPhase18Untouched" tests/prompts/test_evolve_prompt_sections_session_source.py` 命中（D-22 regression guard）
    - `grep -nE 'drift_per_dim_metrics' tests/prompts/test_evolve_prompt_sections_session_source.py` 命中（W7 fix step 8c regression guard 增强）
    - **W7 fix acceptance**：`grep -nE 'DriftDetector\(config, drift_thresholds\)' tests/prompts/test_evolve_prompt_sections_session_source.py` 命中（精确签名断言）
    - **W7 fix acceptance**：`grep -nE 'content\.count\(.DriftDetector\(.\)' tests/prompts/test_evolve_prompt_sections_session_source.py` 命中（count ≥ 2 断言）
    - 全部测试通过：`python -m pytest tests/prompts/test_evolve_prompt_sections_session_source.py -x -q`
    - 整个 prompt 测试套件无 regression：`python -m pytest tests/prompts/ -x -q`
    - 整个仓库测试无 regression：`python -m pytest tests/ -x -q`（Phase 18 baseline 533 passed + 1 skipped + 1 xfailed → Phase 19 后增加新测试但保留 Phase 18 全部）
  </acceptance_criteria>

  <done>
    --session-source 端到端集成测试套件 8+ 测试全部通过；D-16 3 种 collision 路径覆盖；D-22 + step 8c 显式 regression guard；JSONL 容错验证；joint + round-robin dual-mode 兼容性确认。整个仓库测试套件零 regression。W7 fix：`test_step_8c_drift_wiring_intact` 增强为 4 个精确断言（count + 精确签名 + 变量名 + 输出文件）。
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Test fixtures → SessionPromptMiner / CLI | 测试 fixture 是受信源；测试只验证生产代码行为，不引入新数据通道 |
| Mock LLM judge → SessionPromptMiner | mock 替换避免真实 LLM；测试 LLM judge 解析鲁棒性而非真实模型质量 |
| FAILED_<ts>/ 写盘 in tmp_path | tmp_path 隔离 — 不污染仓库 datasets/ 目录 |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-19-05-S | Spoofing | Test session JSON fixture | accept | 测试 fixture 显式标注 mock 数据；secret pattern 是合成 JWT 形态（非真实 token） |
| T-19-05-T | Tampering | tmp_path 写 FAILED_<ts>/ | mitigate | os.chdir 切换到 tmp_path 后还原；CliRunner 自动隔离 stdout/stderr |
| T-19-05-I | Info Disclosure | session_with_secret.json fixture 内容 | mitigate | fixture 中的 JWT 是合成 `eyJ...` 模式，无真实 secret；专门测 _contains_secret 行为 |
| T-19-05-D | DoS | mock chain 太深导致测试慢 | mitigate | 每测试 ≤ 0.5s（mock 全部 LLM）；总测试套件目标 < 30s |
| T-19-05-E | Elevation | _train_msg / _holdout_msg 暴力枚举 | accept | < 10k iter（hash bucket 70/15/15）必能找到目标；assertion 保护无限循环 |

T-19-05 跨 Plan 02-04 全部 STRIDE 类别由本 plan 测试覆盖（4 路 signal extract 鲁棒性 / consent gate / surface drift / bad-line / cross-mode union），但本 plan 自身的新增风险局限于测试代码本身（mock 失真、tmp_path 泄漏）。
</threat_model>

<verification>
- 3 个测试文件存在，行数符合最低要求
- 全部测试通过 mock LLM（zero real API call）
- 4 个 fixture（3 session + 1 thresholds）创建在 tests/prompts/fixtures/
- 所有 SessionPromptMiner 测试通过：`python -m pytest tests/prompts/test_session_prompt_miner.py -x`
- 所有 CLI 测试通过：`python -m pytest tests/prompts/test_mine_prompt_sessions_cli.py -x`
- 所有 evolve_prompt_sections session-source 测试通过：`python -m pytest tests/prompts/test_evolve_prompt_sections_session_source.py -x`
- 整个 prompt 测试套件无 regression：`python -m pytest tests/prompts/ -x`（原 110 + 新增 = 实际数）
- 整个仓库测试套件无 regression：`python -m pytest tests/ -x`
- D-04 1-run vs 3-run regression guard 显式：`grep -E "drift_detector\.check_one_run_mock\.called|check_one_run_mock\.called" tests/prompts/ -r` 命中
- D-22 build_drift_calibration.py 显式 regression guard 测试存在：`grep -E "test_build_drift_calibration_untouched" tests/prompts/ -r` 命中
- W2 fix 测试：`test_persona_drift_missing_thresholds_graceful` 显式存在
- W5 fix：`__dspy_field_type` 在 tests/prompts/ 中输出空（不依赖私有 marker）
- W6 fix：dummy_drift_thresholds fixture docstring 含 monkeypatch 时序约束
- W7 fix：`test_step_8c_drift_wiring_intact` 含 4 个精确断言（count + 精确签名 + 变量名 + 输出文件）
</verification>

<success_criteria>
- 3 个新测试文件 + 4 个 fixture 全部就位
- Phase 19 测试覆盖率：4 路 extractor / judge 鲁棒解析 / split_and_duplicate / hash split / consent gate / dry-run / FAILED 路径 / 5 文件输出 / graceful disable / union 3 路 collision / JSONL 容错 / step 8c 与 build_drift_calibration regression guard 全部命中
- Phase 19 新增测试数 ≥ 45（25 + 14 + 8）
- Zero real LLM call（grep test 文件无 `dspy.LM('openai/` 字符串非 mock 场景）
- 整个 tests/prompts/ 与 tests/ 套件零 regression
- W2 fix：CLI 测试含 `test_persona_drift_missing_thresholds_graceful`
- W5 fix：Signature 验证走 `__annotations__` 公共 API
- W6 fix：fixture docstring 显式约束
- W7 fix：step 8c 4 个精确断言
</success_criteria>

<output>
After completion, create `.planning/phases/19-sessiondb-behavioral-mining-for-prompts/19-05-SUMMARY.md` 记录：
- 3 个测试文件 + 4 个 fixture 的最终 LoC / 测试函数数
- pytest 整个 prompt + 整个仓库的最终 passed/skipped/xfailed 计数
- Phase 19 5 个 PLAN 之间的 trace（D-01..D-25 → 哪些 test 覆盖）
- 任何 Phase 19 verify-phase 期间需要人工 spot-check 的边界场景列表
- W2/W5/W6/W7 fix 在各 test 文件中的精确 grep 证据
</output>
