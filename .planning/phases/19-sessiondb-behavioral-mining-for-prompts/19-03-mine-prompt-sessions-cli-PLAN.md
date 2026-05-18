---
phase: 19-sessiondb-behavioral-mining-for-prompts
plan: 03
type: execute
wave: 3
depends_on:
  - 19-01
  - 19-02
files_modified:
  - evolution/prompts/mine_prompt_sessions.py
autonomous: true
requirements:
  - PMPT-V2-04
tags:
  - prompt
  - cli
  - mining
  - privacy-gate

must_haves:
  truths:
    - "[D-17] 新 CLI `python -m evolution.prompts.mine_prompt_sessions` 接受 13 个 Click options（12 个 Phase 14 对称 + 1 个 NEW --drift-thresholds-path）"
    - "[D-17] 默认 sessions-dir = ~/.hermes/sessions；默认 output = datasets/prompts/sessions/<YYYYMMDD_HHMMSS>/"
    - "[D-18] CLI 包装 SessionPromptMiner.mine() + split_and_duplicate；通过 EvolutionConfig.load 加载配置"
    - "[D-20] 输出目录含 train.jsonl / val.jsonl / holdout.jsonl + metrics.json + miner_log.jsonl 五件套；CLI 末尾 Rich Table 总结 4 个信号"
    - "[D-23] 复用 _contains_secret（不再 import _shannon_entropy / SECRET_PATTERNS 直接路径）"
    - "[D-24] _load_session try/except per file + 5% bad-lines 阈值 console warn"
    - "[D-25] --i-have-consent 必填 — 缺则 click.echo error to stderr + return 1（exit code 非 0）；错误消息显式提及 ~/.hermes/sessions/"
    - "[D-14] --behavioral-multiplier 'key=value' 解析支持 4 个 signal key（user_correction/section_specific_failure/oracle_disagreement/persona_drift）"
    - "[D-04] persona_drift signal 启用时从 --drift-thresholds-path 加载 thresholds（剥离 _meta 键）；缺失时该 signal silent disabled + warn"
    - "[D-04] oracle_disagreement signal 启用时尝试加载 --baseline-module；缺失时该 signal silent disabled + warn"
    - "Dry-run 模式：跳过 LLM judge，按规则枚举 candidate 后打印分布表，不消耗 API 配额"
    - "FAILED_<ts>/ failure path 覆盖 3 种失败场景：sessions_dir_missing / no_sections_found / no_examples_post_judge"
  artifacts:
    - path: "evolution/prompts/mine_prompt_sessions.py"
      provides: "Click CLI + mine() 主流程函数 + _parse_signals/_parse_multiplier_override 辅助 + Rich Table 总结 + metrics.json 写盘"
      min_lines: 350
      exports:
        - "main"
        - "mine"
  key_links:
    - from: "evolution/prompts/mine_prompt_sessions.py:mine"
      to: "evolution/prompts/session_prompt_miner.py:SessionPromptMiner"
      via: "Plan 02 公开 import → CLI 实例化与调用"
      pattern: "SessionPromptMiner\\("
    - from: "evolution/prompts/mine_prompt_sessions.py"
      to: "evolution/prompts/drift_detector.py:DRIFT_DIMENSIONS"
      via: "D-04 thresholds JSON 剥离 _meta 时迭代 4 维"
      pattern: "DRIFT_DIMENSIONS"
    - from: "evolution/prompts/mine_prompt_sessions.py"
      to: "evolution/prompts/prompt_loader.py:extract_prompt_sections"
      via: "D-09 current_section_ids 真实来源"
      pattern: "extract_prompt_sections"
---

<objective>
新建 `evolution/prompts/mine_prompt_sessions.py` Click CLI，端到端包装 SessionPromptMiner：13 个 flag、--i-have-consent 隐私 gate、persona_drift 阈值加载、Rich Table 总结、metrics.json 写盘、FAILED_<ts>/ 失败路径。镜像 `evolution/tools/mine_tool_sessions.py`。

Purpose: Phase 19 Wave 3 用户入口；让用户一次离线挖矿即可生成可被 evolve_prompt_sections --session-source 消费的 JSONL 数据集。
Output: ~350-500 LoC Python 模块 + 可执行 `python -m evolution.prompts.mine_prompt_sessions --help` 入口。
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
@.planning/phases/19-sessiondb-behavioral-mining-for-prompts/19-01-SUMMARY.md
@.planning/phases/19-sessiondb-behavioral-mining-for-prompts/19-02-SUMMARY.md
@evolution/tools/mine_tool_sessions.py
@evolution/prompts/session_prompt_miner.py
@evolution/prompts/drift_detector.py
@evolution/prompts/prompt_loader.py
@evolution/core/config.py
</context>

<interfaces>
<!-- From Plan 19-02 (already shipped) -->
```python
from evolution.prompts.session_prompt_miner import (
    SessionPromptMiner,
    DEFAULT_MULTIPLIER,    # dict[str, int]
    VALID_SIGNALS,         # frozenset[str]
    split_and_duplicate,   # (examples, multiplier_override, metrics) -> (train, val, holdout)
)
from evolution.prompts.prompt_dataset import PromptBehavioralExample, PromptBehavioralDataset
```

<!-- From evolution/prompts/drift_detector.py -->
```python
DRIFT_DIMENSIONS: tuple[str, ...] = ("tone", "formality", "vocabulary", "persona")
```

<!-- From evolution/prompts/prompt_loader.py -->
```python
def extract_prompt_sections(prompt_builder_path: Path) -> list[PromptSection]: ...
```

<!-- From evolution/core/config.py -->
```python
class EvolutionConfig:
    @classmethod
    def load(cls, hermes_repo=None, model=None, api_base=None, **kwargs) -> "EvolutionConfig": ...
    # Has: judge_model, hermes_agent_path, get_lm_kwargs()
```

<!-- Existing prompt_builder.py path (evolve_prompt_sections.py:170) -->
config.hermes_agent_path / "agent" / "prompt_builder.py"

<!-- Phase 14 mine_tool_sessions.py CLI flags (lines 327-378 — 12 flags as base template) -->
--sessions-dir, --output, --limit, --i-have-consent, --signals,
--baseline-module, --judge-model, --misselection-multiplier (RENAME to --behavioral-multiplier),
--hermes-repo, --model, --api-base, --dry-run
</interfaces>

<tasks>

<task type="auto" tdd="true">
  <name>Task 3.1: CLI 文件骨架 + 13 个 Click options + _parse_signals/_parse_multiplier_override 辅助 + consent gate</name>
  <files>evolution/prompts/mine_prompt_sessions.py</files>

  <read_first>
    - evolution/tools/mine_tool_sessions.py (整文件 — Phase 14 verbatim 模板，重点 lines 1-200 + 327-378)
    - evolution/prompts/session_prompt_miner.py (Plan 19-02 公开符号确认)
    - evolution/prompts/evolve_prompt_sections.py lines 1043-1053 (--drift-thresholds-path 既有 Click option 风格)
    - .planning/phases/19-sessiondb-behavioral-mining-for-prompts/19-PATTERNS.md §1.2.A-B (lines 348-462)
  </read_first>

  <behavior>
    - Test 1: 模块可 import；导出 `main` 函数（Click command）
    - Test 2: `python -m evolution.prompts.mine_prompt_sessions --help` 返回 exit 0；输出含全部 13 flag 名（--sessions-dir / --output / --limit / --i-have-consent / --signals / --baseline-module / --judge-model / --behavioral-multiplier / --hermes-repo / --model / --api-base / --dry-run / --drift-thresholds-path）
    - Test 3: 不传 --i-have-consent → exit code 非 0；stderr 含 "--i-have-consent" 和 "~/.hermes/sessions"
    - Test 4: `_parse_signals("user_correction,persona_drift")` 返回 `["user_correction","persona_drift"]`
    - Test 5: `_parse_signals("user_correction,unknown")` 抛 click.UsageError 含 "unknown"
    - Test 6: `_parse_signals("")` 抛 click.UsageError 含 "empty"
    - Test 7: `_parse_multiplier_override("user_correction=5,persona_drift=2")` 返回 `{"user_correction":5,"persona_drift":2}`
    - Test 8: `_parse_multiplier_override("user_correction=NaN")` 抛 click.UsageError 含 "int"
    - Test 9: `_parse_multiplier_override(None)` 返回 `{}`
    - Test 10 (W2 fix): 默认 `--drift-thresholds-path` 文件不存在时 CLI 不在 parse 阶段拒绝；仅在 mine() 内 `"persona_drift" in signals` 且文件缺失时 Rich warn + 从 signals 移除 persona_drift
  </behavior>

  <action>
    创建文件 `evolution/prompts/mine_prompt_sessions.py`：

    1. **Module docstring**（mirror `evolution/tools/mine_tool_sessions.py:1-27`）：
    ```python
    """SessionDB prompt behavioral mining CLI — Phase 19 (PMPT-V2-04).

    Reads ~/.hermes/sessions/*.json transcripts and produces
    PromptBehavioralExample JSONL files suitable for unioning with
    Phase 9 synthetic datasets via evolve_prompt_sections --session-source.

    Usage:
        python -m evolution.prompts.mine_prompt_sessions \\
            --i-have-consent \\
            --sessions-dir ~/.hermes/sessions \\
            --signals user_correction,section_specific_failure,oracle_disagreement,persona_drift \\
            --baseline-module output/prompts/<latest> \\
            --drift-thresholds-path datasets/prompts/drift_thresholds.json \\
            --output datasets/prompts/sessions/<ts>

    Output topology (D-20):
        datasets/prompts/sessions/<YYYYMMDD_HHMMSS>/
            ├── train.jsonl / val.jsonl / holdout.jsonl
            ├── metrics.json
            └── miner_log.jsonl

    Failure paths:
        FAILED_<ts>/   — sessions empty / consent missing / 0 examples post-judge

    READ-ONLY guarantee: this CLI never calls prompt_loader.write_back_section
    or any hermes-agent mutation path. It only reads session JSON + the current
    prompt surface via extract_prompt_sections.
    """
    ```

    2. **Imports**:
    ```python
    import json
    import sys
    from datetime import datetime
    from pathlib import Path
    from typing import Optional

    import click
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    from evolution.core.config import EvolutionConfig
    from evolution.prompts.drift_detector import DRIFT_DIMENSIONS
    from evolution.prompts.prompt_loader import extract_prompt_sections
    from evolution.prompts.session_prompt_miner import (
        DEFAULT_MULTIPLIER,
        SessionPromptMiner,
        VALID_SIGNALS,
        split_and_duplicate,
    )
    from evolution.prompts.prompt_dataset import PromptBehavioralDataset

    console = Console()
    ```

    3. **_parse_signals** + **_parse_multiplier_override**（mirror `mine_tool_sessions.py:52-95`，仅替换 CLI 错误消息）：
    ```python
    def _parse_signals(value: str) -> list[str]:
        """Parse '--signals' CSV into a deduped list. Unknown signals → UsageError."""
        items = [s.strip() for s in (value or "").split(",") if s.strip()]
        bad = [s for s in items if s not in VALID_SIGNALS]
        if bad:
            raise click.UsageError(
                f"--signals contains unknown signal(s): {bad}. "
                f"Valid: {sorted(VALID_SIGNALS)}"
            )
        if not items:
            raise click.UsageError("--signals is empty after parsing")
        return list(dict.fromkeys(items))


    def _parse_multiplier_override(value: Optional[str]) -> dict[str, int]:
        """Parse '--behavioral-multiplier' kv string into dict[str, int].

        Format: 'user_correction=3,section_specific_failure=3,oracle_disagreement=2,persona_drift=2'.
        Empty / None returns {}. Unknown signal keys raise UsageError.
        """
        if not value:
            return {}
        out: dict[str, int] = {}
        for part in value.split(","):
            if not part.strip():
                continue
            if "=" not in part:
                raise click.UsageError(
                    f"--behavioral-multiplier item {part!r} missing '='"
                )
            k, v = part.split("=", 1)
            k = k.strip()
            if k not in VALID_SIGNALS:
                raise click.UsageError(
                    f"--behavioral-multiplier unknown signal {k!r}; "
                    f"valid: {sorted(VALID_SIGNALS)}"
                )
            try:
                out[k] = int(v.strip())
            except ValueError:
                raise click.UsageError(
                    f"--behavioral-multiplier value for {k!r} must be int, got {v!r}"
                )
        return out
    ```

    4. **Click command with 13 options + consent gate + body placeholder**（per D-17/D-25）。

    **W2 修复（critical）**：`--drift-thresholds-path` 移除 `exists=True`（避免用户运行环境无该文件时 Click 在 consent gate 前即拒绝）。`exists=True` 的语义校验迁移到 mine() 内部 lazy 检查，且仅在 `"persona_drift" in signals_list` 时触发（与 oracle_disagreement disabled 模式对称）。

    Click options 顺序：
    ```python
    @click.command()
    @click.option(
        "--sessions-dir", default=None, type=click.Path(),
        help="Directory containing session_*.json (default ~/.hermes/sessions)",
    )
    @click.option(
        "--output", default=None, type=click.Path(),
        help="Output directory (default datasets/prompts/sessions/<YYYYMMDD_HHMMSS>/)",
    )
    @click.option("--limit", default=0, type=int, help="0 = scan all sessions")
    @click.option(
        "--i-have-consent", is_flag=True,
        help="REQUIRED — explicit consent to read session data (Layer 3 privacy gate). "
             "Refuses to proceed without it. Phase 14 D-16 + Phase 19 D-25 mirror.",
    )
    @click.option(
        "--signals",
        default="user_correction,section_specific_failure,oracle_disagreement,persona_drift",
        help="Comma-separated subset of {user_correction, section_specific_failure, "
             "oracle_disagreement, persona_drift}",
    )
    @click.option(
        "--baseline-module", default=None, type=click.Path(),
        help="Path to a Phase 10/17/18 evolve_prompt_sections output dir for "
             "oracle_disagreement signal (omit → signal disabled + warn)",
    )
    @click.option(
        "--judge-model", default=None,
        help="Override config.judge_model for ConfirmBehavioralExample LLM judge",
    )
    @click.option(
        "--behavioral-multiplier", default=None,
        help='Override D-13 defaults; e.g. "user_correction=3,section_specific_failure=3,'
             'oracle_disagreement=2,persona_drift=2"',
    )
    @click.option(
        "--hermes-repo", default=None,
        help="Path to hermes-agent repo (overrides HERMES_AGENT_REPO env)",
    )
    @click.option("--model", default=None, help="Override LLM model for non-judge calls")
    @click.option("--api-base", default=None, help="Override API base URL")
    @click.option(
        "--dry-run", is_flag=True,
        help="Skip LLM judge; enumerate candidates and print distribution table",
    )
    @click.option(
        "--drift-thresholds-path",
        type=click.Path(path_type=Path),
        default=Path("datasets/prompts/drift_thresholds.json"),
        help="Path to drift_thresholds.json (Phase 18 D-BYPASS-02 mirror) for "
             "persona_drift signal. Used only when persona_drift signal is enabled. "
             "When the file does not exist → persona_drift disabled + warn (not fatal). "
             "W2 fix: NO exists=True — file missing must not block consent gate.",
    )
    def main(
        sessions_dir, output, limit, i_have_consent, signals, baseline_module,
        judge_model, behavioral_multiplier, hermes_repo, model, api_base,
        dry_run, drift_thresholds_path,
    ):
        """SessionDB behavioral mining CLI for Phase 19 (PMPT-V2-04)."""
        sys.exit(mine(
            sessions_dir=sessions_dir, output=output, limit=limit,
            i_have_consent=i_have_consent, signals=signals,
            baseline_module=baseline_module, judge_model=judge_model,
            behavioral_multiplier=behavioral_multiplier,
            hermes_repo=hermes_repo, model=model, api_base=api_base,
            dry_run=dry_run, drift_thresholds_path=drift_thresholds_path,
        ))
    ```

    5. **mine() 函数 stub + consent gate**（per D-25 必填 — Task 3.2 填充其余主体）：
    ```python
    def mine(
        sessions_dir: Optional[str],
        output: Optional[str],
        limit: int,
        i_have_consent: bool,
        signals: str,
        baseline_module: Optional[str],
        judge_model: Optional[str],
        behavioral_multiplier: Optional[str],
        hermes_repo: Optional[str],
        model: Optional[str],
        api_base: Optional[str],
        dry_run: bool,
        drift_thresholds_path: Path,
    ) -> int:
        """Main mining orchestration. Returns int exit code (0=success, 1=fail)."""
        # D-25: --i-have-consent gate (mirror mine_tool_sessions.py:194-201)
        if not i_have_consent:
            click.echo(
                "ERROR: --i-have-consent is REQUIRED — refusing to read "
                "session data from ~/.hermes/sessions/ without explicit "
                "consent. Pass --i-have-consent to proceed.\n"
                "Session text may contain personal context; auditors should "
                "review SECRET_PATTERNS coverage before enabling.",
                err=True,
            )
            return 1

        # Body filled by Task 3.2:
        raise NotImplementedError("Task 3.2 fills this in")


    if __name__ == "__main__":
        main()
    ```

    依据 (per D-14/D-17/D-25)：
    - --behavioral-multiplier 重命名（非 --misselection-multiplier）反映 prompt 域语义
    - --signals 默认 4 路（含 persona_drift），区别于 Phase 14 的 3 路默认
    - --drift-thresholds-path 是 Phase 19 唯一新 flag（不存在 Phase 14 中）
    - **W2 修复**：`type=click.Path(path_type=Path)` 不带 `exists=True`，默认值为 `Path("datasets/prompts/drift_thresholds.json")`；文件存在性检查 lazy 化到 mine() 内（Task 3.2）
    - --output 默认 `datasets/prompts/sessions/` 而非 `datasets/tools/sessions/`
    - consent gate 走 click.echo(err=True) + return 1 而非 raise SystemExit 以便单测可 catch
  </action>

  <verify>
    <automated>cd /Users/slj/项目/hermes-agent-self-evolution &amp;&amp; python -c "
import subprocess
# T1+T2: --help works
r = subprocess.run(['python','-m','evolution.prompts.mine_prompt_sessions','--help'], capture_output=True, text=True)
assert r.returncode == 0, r.stderr
flags = ['--sessions-dir','--output','--limit','--i-have-consent','--signals','--baseline-module','--judge-model','--behavioral-multiplier','--hermes-repo','--model','--api-base','--dry-run','--drift-thresholds-path']
for f in flags:
    assert f in r.stdout, f'missing flag {f} in --help output'

# T3: no consent → exit non-zero with stderr
r2 = subprocess.run(['python','-m','evolution.prompts.mine_prompt_sessions'], capture_output=True, text=True)
assert r2.returncode != 0
assert '--i-have-consent' in r2.stderr
assert '~/.hermes/sessions' in r2.stderr

# T10 (W2 fix): default --drift-thresholds-path missing must not block consent gate parse
# (CLI must reach 'mine() body NotImplementedError' / Task 3.2 lazy check, not click.Path exists=True rejection)
r3 = subprocess.run(['python','-m','evolution.prompts.mine_prompt_sessions',
                     '--i-have-consent','--sessions-dir','/tmp'],
                    capture_output=True, text=True)
# Either NotImplementedError stack (Task 3.1 placeholder) or FAILED_/sessions_dir_missing (Task 3.2 done)
# Critical: must NOT be 'Invalid value for --drift-thresholds-path' from Click
assert 'Invalid value' not in (r3.stderr + r3.stdout), (
    'W2 regression: Click rejected default --drift-thresholds-path before consent gate')

# T4-T9: helpers
from evolution.prompts.mine_prompt_sessions import _parse_signals, _parse_multiplier_override
import click
assert _parse_signals('user_correction,persona_drift') == ['user_correction','persona_drift']
try: _parse_signals('user_correction,unknown'); assert False
except click.UsageError as e: assert 'unknown' in str(e)
try: _parse_signals(''); assert False
except click.UsageError as e: assert 'empty' in str(e)
assert _parse_multiplier_override('user_correction=5,persona_drift=2') == {'user_correction':5,'persona_drift':2}
try: _parse_multiplier_override('user_correction=NaN'); assert False
except click.UsageError as e: assert 'int' in str(e)
assert _parse_multiplier_override(None) == {}
print('PASS')
"</automated>
  </verify>

  <acceptance_criteria>
    - 文件存在：`ls evolution/prompts/mine_prompt_sessions.py`
    - `grep -c '@click.option' evolution/prompts/mine_prompt_sessions.py` ≥ 13
    - `grep -nE "@click\.option\(\s*\"--drift-thresholds-path\"" evolution/prompts/mine_prompt_sessions.py` 命中
    - `grep -nE "@click\.option\(\s*\"--behavioral-multiplier\"" evolution/prompts/mine_prompt_sessions.py` 命中
    - `grep -nE 'ERROR: --i-have-consent is REQUIRED' evolution/prompts/mine_prompt_sessions.py` 命中
    - `grep -nE "if not i_have_consent" evolution/prompts/mine_prompt_sessions.py` 命中
    - `grep -nE "default=\"user_correction,section_specific_failure,oracle_disagreement,persona_drift\"" evolution/prompts/mine_prompt_sessions.py` 命中（默认 4 信号）
    - **W2 修复 grep 不变量**：`grep -nE "exists=True" evolution/prompts/mine_prompt_sessions.py` 输出**空**（即 0 行命中 — 任何 `exists=True` 都视为 W2 回归）
    - `grep -c 'NotImplementedError' evolution/prompts/mine_prompt_sessions.py` == 1（Task 3.2 占位符）
    - Import + --help 不抛错
  </acceptance_criteria>

  <done>
    CLI 骨架就绪：可 `--help`，consent gate 工作，所有 13 个 flag 注册，2 个解析器（_parse_signals / _parse_multiplier_override）行为正确，mine() 主体留待 Task 3.2 实现。--drift-thresholds-path 不带 exists=True，文件缺失不阻塞 consent gate（W2 fix）。
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3.2: mine() 主流程 + 输出目录写盘 + Rich Table 总结 + FAILED_<ts>/ 失败路径</name>
  <files>evolution/prompts/mine_prompt_sessions.py</files>

  <read_first>
    - evolution/tools/mine_tool_sessions.py lines 100-323 (Phase 14 mine() 主体 + Rich Table + metrics.json 写盘 + FAILED 路径)
    - evolution/prompts/session_prompt_miner.py (Plan 02 公开 API — SessionPromptMiner.mine / split_and_duplicate / DEFAULT_MULTIPLIER)
    - evolution/prompts/prompt_dataset.py (PromptBehavioralDataset.save 接口确认)
    - 现 mine_prompt_sessions.py (Task 3.1 产物 — 确认 Click 骨架 + 解析器 + consent gate 就位)
    - .planning/phases/19-sessiondb-behavioral-mining-for-prompts/19-PATTERNS.md §1.2.C-D + §4.1-4.3 (lines 464-545, 867-906)
  </read_first>

  <behavior>
    - Test 1: mine() with consent + non-existent sessions_dir → 返回 1，FAILED_<ts>/ 目录创建含 metrics.json 写入 `{"error":"sessions_dir_missing"}`
    - Test 2: mine() with consent + empty sessions_dir → 返回 1，FAILED_<ts>/ 目录创建含 `{"error":"sessions_dir_empty"}` 或 `no_sessions`
    - Test 3: mine() with consent + sessions_dir 含 mock session 但 mock prompt_builder.py 不可达 → 返回 1，FAILED_<ts>/ 含 `no_sections_found`
    - Test 4: dry-run 路径不调 LLM judge：mock `SessionPromptMiner.mine`，但 dry-run 应该跳过 mine() 调用，直接打印 candidate 分布表
    - Test 5: 完整成功路径 — mock miner 返回 examples + current_sections 含正确 ids → 输出目录写 train.jsonl/val.jsonl/holdout.jsonl + metrics.json + miner_log.jsonl 五件套，exit 0
    - Test 6: Rich Table 含 4 个 signal 行（per 单元测试可 capture stdout 含 'user_correction'、'persona_drift' 等字串）
    - Test 7: persona_drift signal 启用 + drift_thresholds_path 不存在 → silent disable + warn + 从 signals_list 移除 + 继续其他三路（不 fail）；metrics.persona_drift_thresholds_used == {}
    - Test 8: --judge-model 覆盖 config.judge_model（mock + 断言传给 SessionPromptMiner 的 config.judge_model 已被覆盖）
    - Test 9 (B3 fix): metrics 含 `session_load_failures` 字段（与 `jsonl_skipped_lines` 区分）；Rich summary 同时打印两者
  </behavior>

  <action>
    打开 `evolution/prompts/mine_prompt_sessions.py`，**替换** Task 3.1 末尾 mine() body 的 `raise NotImplementedError` 为完整实现。

    1. **Rich Table 总结辅助**（mirror `mine_tool_sessions.py:143-175`，加 persona_drift 行 + B3 fix session_load_failures 行）：
    ```python
    def _print_summary_table(metrics: dict, total_examples: int, out_dir: Path) -> None:
        """Print Rich Table summary of mining run. Phase 19 has 4 signal rows."""
        t = Table(title="SessionDB Behavioral Mining Summary", show_header=True,
                  header_style="bold cyan")
        t.add_column("Signal", style="bold")
        t.add_column("Candidates", justify="right")
        t.add_column("Confirmed", justify="right")
        t.add_column("False Positives", justify="right")
        t.add_column("Judge Calls", justify="right")
        signals_order = ("user_correction", "section_specific_failure",
                         "oracle_disagreement", "persona_drift")
        for s in signals_order:
            t.add_row(s,
                str(metrics["total_candidates_by_signal"].get(s, 0)),
                str(metrics["judge_confirmed_by_signal"].get(s, 0)),
                str(metrics["judge_false_positives_by_signal"].get(s, 0)),
                str(metrics["judge_calls_by_signal"].get(s, 0)),
            )
        # TOTAL row
        t.add_row("TOTAL",
            str(sum(metrics["total_candidates_by_signal"].values())),
            str(sum(metrics["judge_confirmed_by_signal"].values())),
            str(sum(metrics["judge_false_positives_by_signal"].values())),
            str(metrics["judge_calls"]),
        )
        console.print(t)
        console.print(
            f"  Surface drift dropped: {metrics['surface_drift_dropped']} "
            f"(sections: {metrics.get('surface_drift_sections', {})})"
        )
        console.print(f"  Secret filter skipped: {metrics['secret_filter_skipped']}")
        # B3 fix: print BOTH session-level + line-level skip counters with clear labels.
        console.print(
            f"  Session load failures (file-level, mine_prompt_sessions scope): "
            f"{metrics.get('session_load_failures', 0)}"
        )
        console.print(
            f"  JSONL skipped lines (line-level, evolve_prompt_sections session-source scope): "
            f"{metrics['jsonl_skipped_lines']}"
        )
        console.print(
            f"  Final examples: train={metrics['final_examples_by_split']['train']} "
            f"({metrics['final_train_after_duplication']} after duplication) "
            f"/ val={metrics['final_examples_by_split']['val']} "
            f"/ holdout={metrics['final_examples_by_split']['holdout']} "
            f"/ flat total = {total_examples}"
        )
        console.print(f"  Output: {out_dir}")
    ```

    2. **FAILED_<ts>/ 辅助**（mirror `mine_tool_sessions.py:239-247`）：
    ```python
    def _write_failed(timestamp: str, error_key: str, extra: Optional[dict] = None) -> Path:
        """Write FAILED_<ts>/ failure marker directory. Returns its Path."""
        failed = Path("datasets") / "prompts" / "sessions" / f"FAILED_{timestamp}"
        failed.mkdir(parents=True, exist_ok=True)
        payload = {"error": error_key}
        if extra:
            payload.update(extra)
        (failed / "metrics.json").write_text(json.dumps(payload, indent=2))
        console.print(f"[red]✗ FAILED: {error_key} → {failed}[/red]")
        return failed
    ```

    3. **mine() body**（替换 Task 3.1 placeholder）：
    ```python
    def mine(
        sessions_dir, output, limit, i_have_consent, signals, baseline_module,
        judge_model, behavioral_multiplier, hermes_repo, model, api_base,
        dry_run, drift_thresholds_path,
    ) -> int:
        # D-25 consent gate (kept from Task 3.1)
        if not i_have_consent:
            click.echo(
                "ERROR: --i-have-consent is REQUIRED — refusing to read "
                "session data from ~/.hermes/sessions/ without explicit "
                "consent. Pass --i-have-consent to proceed.\n"
                "Session text may contain personal context; auditors should "
                "review SECRET_PATTERNS coverage before enabling.",
                err=True,
            )
            return 1

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        console.print(Panel.fit(
            f"[bold cyan]SessionDB Behavioral Mining[/bold cyan]\n"
            f"  Timestamp: {timestamp}\n"
            f"  Signals:   {signals}\n"
            f"  Dry-run:   {dry_run}",
        ))

        # Parse signals + multiplier (early — Click UsageError surfaces before any I/O)
        signals_list = _parse_signals(signals)
        multiplier_override = _parse_multiplier_override(behavioral_multiplier)

        # Resolve paths
        sessions_path = (
            Path(sessions_dir).expanduser() if sessions_dir
            else (Path.home() / ".hermes" / "sessions")
        )
        out_dir = (
            Path(output) if output
            else Path("datasets") / "prompts" / "sessions" / timestamp
        )

        if not sessions_path.exists():
            return 1 if _write_failed(timestamp, "sessions_dir_missing",
                                       {"sessions_dir": str(sessions_path)}) else 1

        # Load config + sections
        try:
            config = EvolutionConfig.load(
                hermes_repo=hermes_repo, model=model, api_base=api_base,
            )
        except Exception as e:
            _write_failed(timestamp, "config_load_failed", {"detail": str(e)})
            return 1
        if judge_model:
            config.judge_model = judge_model

        prompt_builder_path = config.hermes_agent_path / "agent" / "prompt_builder.py"
        try:
            current_sections = extract_prompt_sections(prompt_builder_path)
        except Exception as e:
            _write_failed(timestamp, "prompt_extraction_failed", {"detail": str(e)})
            return 1
        if not current_sections:
            _write_failed(timestamp, "no_sections_found",
                          {"prompt_builder_path": str(prompt_builder_path)})
            return 1

        # Load drift thresholds (D-04) — only when persona_drift active.
        # W2 fix: file existence checked LAZILY here (not at Click parse time).
        # Missing thresholds is NOT fatal (graceful disable + remove from signals_list).
        drift_thresholds: Optional[dict] = None
        if "persona_drift" in signals_list:
            if not Path(drift_thresholds_path).exists():
                console.print(
                    f"[yellow]⚠ drift_thresholds_path {drift_thresholds_path} does "
                    f"not exist. persona_drift signal will be disabled "
                    f"(symmetric with oracle_disagreement disabled mode).[/yellow]"
                )
                signals_list = [s for s in signals_list if s != "persona_drift"]
            else:
                try:
                    raw = json.loads(Path(drift_thresholds_path).read_text())
                    drift_thresholds = {d: float(raw[d]) for d in DRIFT_DIMENSIONS}
                except Exception as e:
                    console.print(
                        f"[yellow]⚠ Cannot parse drift thresholds from "
                        f"{drift_thresholds_path}: {type(e).__name__}: {e}. "
                        f"persona_drift signal will be disabled.[/yellow]"
                    )
                    drift_thresholds = None
                    signals_list = [s for s in signals_list if s != "persona_drift"]

        # Load baseline module (D-04) — only when oracle_disagreement active.
        # Missing baseline_module is NOT fatal.
        baseline_mod = None
        oracle_baseline_path_str: Optional[str] = None
        if "oracle_disagreement" in signals_list:
            if baseline_module:
                try:
                    # Sanity check: baseline dir must contain evolved_sections.json
                    bp = Path(baseline_module)
                    if (bp / "evolved_sections.json").exists():
                        # Defer actual PromptModule reconstruction; SessionPromptMiner
                        # treats baseline_module=None as "signal disabled". Pass the
                        # path object so the miner can later wire it lazily.
                        baseline_mod = bp
                        oracle_baseline_path_str = str(bp)
                    else:
                        console.print(
                            f"[yellow]⚠ baseline_module {bp} has no "
                            f"evolved_sections.json; oracle_disagreement disabled[/yellow]"
                        )
                except Exception as e:
                    console.print(
                        f"[yellow]⚠ Cannot load baseline module: {e}; "
                        f"oracle_disagreement disabled[/yellow]"
                    )
            else:
                console.print(
                    "[yellow]⚠ --baseline-module not given; "
                    "oracle_disagreement signal disabled[/yellow]"
                )

        # Build miner
        miner = SessionPromptMiner(
            config=config,
            signals=signals_list,
            multiplier_override=multiplier_override,
            baseline_module=baseline_mod,
            drift_thresholds=drift_thresholds,
        )
        if oracle_baseline_path_str:
            miner.metrics["oracle_baseline_path"] = oracle_baseline_path_str

        # ── Dry-run branch — skip LLM judge, enumerate candidates only ──
        if dry_run:
            console.print("[bold yellow]DRY RUN — skipping LLM judge[/bold yellow]")
            # Walk candidates without calling judge (to estimate LLM budget)
            session_paths = sorted(sessions_path.glob("*.json"))
            if limit > 0:
                session_paths = session_paths[:limit]
            total_cands = 0
            for sp in session_paths:
                sess = miner._load_session(sp)
                if not sess: continue
                msgs = sess.get("messages") or []
                if not isinstance(msgs, list): continue
                cands = []
                cands.extend(miner._extract_user_correction(msgs, str(sp)))
                cands.extend(miner._extract_section_specific_failure(msgs, str(sp)))
                cands.extend(miner._extract_oracle_disagreement(msgs, str(sp)))
                cands.extend(miner._extract_persona_drift(msgs, str(sp)))
                cands = miner._filter_secrets(cands)
                total_cands += len(cands)
            console.print(f"  Sessions scanned: {len(session_paths)}")
            console.print(f"  Candidates before LLM judge: {total_cands}")
            console.print(f"  Estimated LLM judge calls (no dry-run): {total_cands}")
            return 0

        # ── Real mine path ─────────────────────────────────────────────
        try:
            examples = miner.mine(sessions_path, current_sections, limit=limit)
        except Exception as e:
            _write_failed(timestamp, "mine_exception", {"detail": str(e)})
            return 1

        if not examples:
            _write_failed(timestamp, "no_examples_post_judge",
                          {"metrics": miner.metrics})
            return 1

        # Bucket-split + train-only duplication (D-13/D-15)
        train, val, holdout = split_and_duplicate(
            examples,
            multiplier_override=multiplier_override,
            metrics=miner.metrics,
        )

        # Persist 5-file output topology (D-20)
        out_dir.mkdir(parents=True, exist_ok=True)
        dataset = PromptBehavioralDataset(train=train, val=val, holdout=holdout)
        dataset.save(out_dir)

        # metrics.json
        (out_dir / "metrics.json").write_text(json.dumps(miner.metrics, indent=2))

        # miner_log.jsonl (audit row per example)
        with open(out_dir / "miner_log.jsonl", "w") as f:
            for ex in examples:
                f.write(json.dumps({
                    "section_id": ex.section_id,
                    "mining_signals": ex.mining_signals,
                    "difficulty": ex.difficulty,
                    "user_message_excerpt": (ex.user_message or "")[:200],
                }) + "\n")

        _print_summary_table(miner.metrics, len(examples), out_dir)
        return 0
    ```

    依据 (per D-04/D-17/D-20/D-25)：
    - **W2 修复**：drift_thresholds_path 文件存在性检查迁移到 mine() 内（`if "persona_drift" in signals_list and not Path(drift_thresholds_path).exists()`），符合"与 oracle_disagreement disabled 模式对称"
    - **B3 修复**：summary table 显式区分 `session_load_failures`（file-level，mine scope）与 `jsonl_skipped_lines`（line-level，evolve_prompt_sections session-source scope）；命名清晰避免语义混合
    - oracle_disagreement / persona_drift 缺源时 silent disable (warn + 继续其他信号) 是 CONTEXT 显式要求
    - dry-run 跳过 judge 与 split_and_duplicate（仅 candidate 枚举）以便估算 LLM 预算
    - FAILED_<ts>/ 用 helper 统一 3 种失败场景：sessions_dir_missing / no_sections_found / no_examples_post_judge
    - 5 文件输出：train.jsonl / val.jsonl / holdout.jsonl + metrics.json + miner_log.jsonl
    - baseline_module 仅做存在性检查（real PromptModule 重建留给 Plan 04 实际 oracle 调用方）— 本 plan 只需 path 存在传给 miner
  </action>

  <verify>
    <automated>cd /Users/slj/项目/hermes-agent-self-evolution &amp;&amp; python -c "
import json, tempfile, subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock
from evolution.prompts import mine_prompt_sessions
from click.testing import CliRunner

runner = CliRunner()

# T1: missing sessions_dir → FAILED_/
with tempfile.TemporaryDirectory() as tmp:
    # Change to tmp dir so FAILED_ writes under tmp
    import os; os.chdir(tmp)
    r = runner.invoke(mine_prompt_sessions.main, [
        '--i-have-consent', '--sessions-dir', '/definitely/not/here',
    ])
    assert r.exit_code == 1, r.output
    failed_dirs = list((Path(tmp)/'datasets/prompts/sessions').glob('FAILED_*'))
    assert len(failed_dirs) == 1, failed_dirs
    metrics = json.loads((failed_dirs[0]/'metrics.json').read_text())
    assert metrics['error'] == 'sessions_dir_missing'

# T3 (no consent — verified Task 3.1; re-verify in subprocess)
r2 = runner.invoke(mine_prompt_sessions.main, [])
assert r2.exit_code != 0

# T4: dry-run skips LLM judge (mock everything)
with tempfile.TemporaryDirectory() as tmp:
    sessions = Path(tmp)/'sessions'; sessions.mkdir()
    (sessions/'s1.json').write_text(json.dumps({'messages':[{'role':'user','content':'q'},{'role':'assistant','content':'a'},{'role':'user','content':'don\\'t apologize'}]}))
    with patch.object(mine_prompt_sessions, 'EvolutionConfig') as MC, \\
         patch.object(mine_prompt_sessions, 'extract_prompt_sections') as MS, \\
         patch.object(mine_prompt_sessions, 'SessionPromptMiner') as MM:
        cfg = MagicMock(); cfg.hermes_agent_path = Path(tmp); cfg.judge_model='mock'; cfg.eval_model='mock'; cfg.get_lm_kwargs=MagicMock(return_value={})
        MC.load.return_value = cfg
        from evolution.prompts.prompt_loader import PromptSection
        MS.return_value = [PromptSection(section_id='memory_guidance', text='x', char_count=1, line_range=(1,1), source_path=Path('x'))]
        # Simulate miner instance
        miner_inst = MagicMock()
        miner_inst._load_session.return_value = {'messages':[]}
        miner_inst._extract_user_correction.return_value = []
        miner_inst._extract_section_specific_failure.return_value = []
        miner_inst._extract_oracle_disagreement.return_value = []
        miner_inst._extract_persona_drift.return_value = []
        miner_inst._filter_secrets.side_effect = lambda x: x
        miner_inst.metrics = {}
        MM.return_value = miner_inst
        r3 = runner.invoke(mine_prompt_sessions.main, [
            '--i-have-consent', '--sessions-dir', str(sessions),
            '--dry-run', '--signals', 'user_correction',
        ])
        assert r3.exit_code == 0, r3.output
        # miner.mine should NOT have been called in dry-run
        miner_inst.mine.assert_not_called()
print('PASS')
"</automated>
  </verify>

  <acceptance_criteria>
    - `grep -c 'NotImplementedError' evolution/prompts/mine_prompt_sessions.py` == 0（占位符全部填充）
    - `grep -nE "FAILED_\{timestamp\}" evolution/prompts/mine_prompt_sessions.py` 命中
    - `grep -c "_write_failed" evolution/prompts/mine_prompt_sessions.py` ≥ 4（定义 + 3 种失败场景调用）
    - `grep -nE "miner_log\.jsonl" evolution/prompts/mine_prompt_sessions.py` 命中
    - `grep -nE "metrics\.json" evolution/prompts/mine_prompt_sessions.py` 命中
    - `grep -nE "dataset\.save\(out_dir\)" evolution/prompts/mine_prompt_sessions.py` 命中
    - `grep -nE "_print_summary_table" evolution/prompts/mine_prompt_sessions.py` ≥ 2（定义 + 调用）
    - `grep -nE 'persona_drift signal will be disabled' evolution/prompts/mine_prompt_sessions.py` 命中（D-04 graceful disable）
    - `grep -nE 'oracle_disagreement signal disabled' evolution/prompts/mine_prompt_sessions.py` 命中（D-04 graceful disable）
    - **W2 修复**：`grep -nE "if .persona_drift. in signals_list" evolution/prompts/mine_prompt_sessions.py` 命中（lazy check 替代 click exists=True）
    - **W2 修复**：`grep -nE "signals_list = \[s for s in signals_list if s != .persona_drift.\]" evolution/prompts/mine_prompt_sessions.py` 命中（从 signals_list 移除）
    - **B3 修复**：`grep -nE "session_load_failures" evolution/prompts/mine_prompt_sessions.py` ≥ 1（summary table 引用）
    - `grep -nE "JSONL skipped lines.+evolve_prompt_sections" evolution/prompts/mine_prompt_sessions.py` 命中（B3：labels 区分两个语义）
    - `grep -c '@click\.option' evolution/prompts/mine_prompt_sessions.py` == 13 (精确不超不少)
    - `wc -l evolution/prompts/mine_prompt_sessions.py` 输出 ≥ 350 行
    - 现有测试无 regression：`python -m pytest tests/prompts/ -x -q`
  </acceptance_criteria>

  <done>
    mine() 主流程端到端可用：3 种失败路径走 FAILED_<ts>/、dry-run 仅枚举 candidate、persona_drift / oracle 缺源 graceful disable（W2 fix：lazy 检查 drift_thresholds_path 而非 Click exists=True）、成功路径产出 5 文件输出 + Rich Table 总结（B3 fix：session_load_failures 与 jsonl_skipped_lines 显式 labels 区分）。`python -m evolution.prompts.mine_prompt_sessions --i-have-consent --sessions-dir <dir> --dry-run` 可在不调 LLM 的情况下产出 candidate 估算。
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| CLI argv → mine() 参数 | 用户输入；--i-have-consent 必填（D-25）；signals/multiplier 经 _parse_* 校验 |
| ~/.hermes/sessions/*.json → 内存 dict | 未受信源；session JSON 含真实用户对话 |
| LLM API 调用预算 | 默认 ~$20-30；用户可 --dry-run 预估调用量 |
| drift_thresholds.json → drift_detector 参数 | 文件可能缺失或格式错；graceful disable 而非 fatal |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-19-03-S | Spoofing | --i-have-consent | mitigate | D-25 是 CLI argv 唯一阻塞；缺则 stderr + return 1，错误消息含 ~/.hermes/sessions/ 数据来源说明 |
| T-19-03-T | Tampering | _parse_signals / _parse_multiplier_override | mitigate | 白名单校验：unknown signal/key 抛 click.UsageError；非 int multiplier 抛 click.UsageError；empty signal 抛 click.UsageError |
| T-19-03-I | Info Disclosure | metrics.json 落盘内容 | mitigate | metrics 只含计数 + section_id 名（无原始用户文本）；miner_log.jsonl 含 200 char user_message 摘要，未经 redact—审计期望已在 --i-have-consent 错误消息中告知用户 |
| T-19-03-I | Info Disclosure | FAILED_<ts>/metrics.json detail 字段 | mitigate | _write_failed 的 extra dict 内仅放路径/异常 type+str(e)，不含 session 原文 |
| T-19-03-D | DoS | --limit / unbounded sessions_dir | mitigate | limit 参数 + dry-run 模式 + 5% bad-lines 阈值 warn |
| T-19-03-E | Elevation | --hermes-repo / HERMES_AGENT_REPO | accept | 复用 Phase 14 已有 EvolutionConfig.load 路径；只读访问 prompt_builder.py |
</threat_model>

<verification>
- CLI --help 含全部 13 个 flag 名（exact count = 13）
- 无 --i-have-consent → exit code 非 0 + stderr 含 `--i-have-consent` 与 `~/.hermes/sessions`
- 3 种失败场景（sessions_dir_missing / no_sections_found / no_examples_post_judge）正确写 FAILED_<ts>/metrics.json
- dry-run 跳过 miner.mine 调用（不消耗 LLM 配额）
- persona_drift signal + 缺失 drift_thresholds_path → warn + 从 signals_list 移除 + 继续其他信号（W2 fix）
- oracle_disagreement signal + 缺 --baseline-module → warn + 继续其他信号（不 fail）
- 现有 tests/prompts/ 110 测试无 regression
- `grep` 不变量全部命中（13 options / FAILED 路径 / graceful disable 消息 / W2 fix lazy check / B3 fix session_load_failures label）
</verification>

<success_criteria>
- `python -m evolution.prompts.mine_prompt_sessions --help` exit 0 含 13 个 flag
- 无 --i-have-consent → exit 非 0 stderr 含正确消息
- dry-run + mock miner → exit 0 不调 miner.mine
- 成功路径 → out_dir 含 5 个文件（train/val/holdout.jsonl + metrics.json + miner_log.jsonl）
- 失败路径 → FAILED_<ts>/metrics.json 含正确 error key
- Rich Table 含 4 个 signal 行 + TOTAL 行 + B3 fix 显式 session_load_failures / jsonl_skipped_lines 双行
- persona_drift / oracle 缺源 graceful disable（warn + 继续）
- W2 修复：drift_thresholds_path 不带 exists=True；lazy check 在 mine() 内
- 现有 prompt 测试 zero regression
</success_criteria>

<output>
After completion, create `.planning/phases/19-sessiondb-behavioral-mining-for-prompts/19-03-SUMMARY.md` 记录：
- CLI 13 flag 列表与 default 值
- 3 种失败场景实际写盘内容样例
- dry-run 模式的 candidate 估算输出样例
- Plan 04 evolve_prompt_sections 集成入口（output dir 路径）
- W2 修复证据：grep `exists=True` 在 mine_prompt_sessions.py 中输出空
- B3 修复证据：summary 输出含 `session_load_failures` 与 `JSONL skipped lines` 两行 + Rich labels
</output>
</output>
