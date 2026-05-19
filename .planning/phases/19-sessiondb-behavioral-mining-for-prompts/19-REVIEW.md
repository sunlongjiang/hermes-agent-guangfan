---
phase: 19-sessiondb-behavioral-mining-for-prompts
reviewed: 2026-05-19T00:00:00Z
depth: standard
files_reviewed: 13
files_reviewed_list:
  - evolution/prompts/prompt_dataset.py
  - evolution/prompts/session_prompt_miner.py
  - evolution/prompts/mine_prompt_sessions.py
  - evolution/prompts/evolve_prompt_sections.py
  - tests/prompts/test_prompt_dataset.py
  - tests/prompts/test_session_prompt_miner.py
  - tests/prompts/test_mine_prompt_sessions.py
  - tests/prompts/test_mine_prompt_sessions_cli.py
  - tests/prompts/test_evolve_prompt_sections_session_source.py
  - tests/prompts/fixtures/drift_thresholds.json
  - tests/prompts/fixtures/sessions/session_normal.json
  - tests/prompts/fixtures/sessions/session_with_secret.json
  - tests/prompts/fixtures/sessions/session_persona_drift.json
findings:
  critical: 2
  warning: 8
  info: 5
  total: 15
status: issues_found
---

# Phase 19: Code Review Report

**Reviewed:** 2026-05-19T00:00:00Z
**Depth:** standard
**Files Reviewed:** 13
**Status:** issues_found

## Summary

审查覆盖了 Phase 19 SessionDB 行为挖掘的全部新文件（4 个源文件 + 9 个测试/fixture）。整体结构遵循 Phase 14 `session_miner.py` 的镜像模式，配对测试覆盖度良好。

主要风险点集中在两处：
1. **`split_and_duplicate` 的 `seen_hashes` 集合存在死代码 + 逻辑漏洞**：同一 hash 出现在多个 `section_id` 时,代码声称"路由到同一 split",但实际实现并未阻止重复 append——`seen_hashes` 的值被记录后从未用于过滤,导致同 hash 多 section_id 的样本被重复路由到训练集（注释承诺与实现不一致）。
2. **`mine_prompt_sessions._write_failed` 的输出路径硬编码,忽略 `--output` 参数**：失败时 FAILED_<ts>/ 始终写到 `datasets/prompts/sessions/`,即使用户通过 `--output` 指定了别的目录。这会让 CI/外部脚本无法可靠地收集失败 artifact。
3. **`available_sections_summary` 输入字段实际只包含一行**：DSPy Signature 的 desc 承诺"newline-separated '- <section_id>: <<=200-char excerpt>' for all current sections + platform_hints.<key> list",但 `_judge_candidates` 仅对单个 candidate 调用 `_format_sections_summary(current_sections)` 拼接所有 sections,内部实现正确——这里没有 bug,只是 desc 的 "+ platform_hints.<key> list" 措辞令人误解（platform sections 已经在 current_sections 中）。归类为 Info。

另外多处 WARNING 级别问题：辅助函数引入的 `import hashlib` 等导入未使用、`mine_prompt_sessions.py:413` 在 `--dry-run` 中重复执行了 `_extract_*` 但忽略 `_load_session` 失败时的 metrics 副作用、`evolve_prompt_sections._load_session_dataset_resilient` 没有累加到 `metrics["jsonl_skipped_lines"]`（按 docstring 它应该写入但实际没有挂钩）。

## Critical Issues

### CR-01: `split_and_duplicate` 的 `seen_hashes` 是死代码,同 hash 多 section_id 会被多次路由

**File:** `evolution/prompts/session_prompt_miner.py:750-767`
**Issue:**
代码注释清晰说明意图："same hash already routed; this can happen if two examples share user_message but differ on section_id — route both to the SAME split (the first split chosen for this hash)"。但实际实现是:

```python
seen_hashes: set[str] = set()
for ex in examples:
    h = _normalize_task_hash(ex.user_message)
    if h in seen_hashes:
        # D-15: same hash already routed; this can happen if two
        # examples share user_message but differ on section_id —
        # route both to the SAME split (the first split chosen for
        # this hash). ...
        pass            # ← NO-OP: 没有任何过滤行为
    seen_hashes.add(h)
    split = _hash_to_split(h)   # ← 始终用 hash 重新计算,与 first-seen 无关
    if split == "train":
        train_raw.append(ex)
    ...
```

实际上：
- `seen_hashes` 写入了但**从未被读取**用于决策；
- `_hash_to_split(h)` 是 hash 的纯函数,所以"first-seen split"与"this-seen split"对于同 hash 永远相同——这部分注释的语义本身是被算法保证的,不需要 `seen_hashes`。
- 但当同一个 user_message 因为不同 section_id 产生两个 example 时（D-07: "Same task_hash + different section_id → multiple ex"）,这两个 ex 都会**被 append 到同一个 split**——这与注释的承诺一致,但跟用户的预期（按 hash dedup）相反:同一段用户文本在数据集里会出现 N 份, train-only duplication 还会进一步乘 multiplier。

如果意图就是允许这种"同 task 多 section"的多份样本同 split 共存,那么 `seen_hashes` 集合及其周围的 `if`/`pass` 注释完全是死代码,应删除以避免误导。如果意图是按 hash dedup,则必须改为:

```python
seen_hashes: set[str] = set()
for ex in examples:
    h = _normalize_task_hash(ex.user_message)
    if h in seen_hashes:
        continue                       # 真正的 dedup
    seen_hashes.add(h)
    split = _hash_to_split(h)
    ...
```

**Fix:**
明确意图后两选一。基于 `mine()` 中 `by_key[(task_hash, section_id)]` 的 dedup 已经保证了 (hash, section) 唯一性,大概率意图是"允许同 hash 多 section_id 共存,但保证所有都进同一 split"——此情况下 `seen_hashes`/`if`/`pass` 块应整段删除:

```python
for ex in examples:
    h = _normalize_task_hash(ex.user_message)
    split = _hash_to_split(h)  # 同 hash 永远同 split,无需额外簿记
    if split == "train":
        train_raw.append(ex)
    elif split == "val":
        val_raw.append(ex)
    else:
        holdout_raw.append(ex)
```

### CR-02: `_write_failed` 硬编码失败路径,忽略 `--output` 参数

**File:** `evolution/prompts/mine_prompt_sessions.py:244`
**Issue:**
```python
def _write_failed(timestamp: str, error_key: str, extra: Optional[dict] = None) -> Path:
    failed = Path("datasets") / "prompts" / "sessions" / f"FAILED_{timestamp}"
```

无论用户是否传入 `--output <path>`,失败 marker 始终写到 cwd-relative `datasets/prompts/sessions/FAILED_<ts>/`。然而成功路径 (`mine()` 末尾,line 299-302) 会响应 `--output`:
```python
out_dir = (
    Path(output) if output
    else Path("datasets") / "prompts" / "sessions" / timestamp
)
```

后果:
1. 在 CI/scripted 场景里,用户给了显式 `--output /tmp/run_abc/out` 时,失败 artifact 会泄露到 `cwd/datasets/...`,导致清理/收集失败结果的脚本找不到。
2. 在测试 `test_sessions_dir_missing_writes_failed_marker` (test_mine_prompt_sessions.py:208) 中,fixture 通过 `monkeypatch.chdir(tmp_path)` 隔离了 cwd 才让测试通过——一旦 CI 不 chdir,失败目录将污染 repo root。
3. 在 `_write_failed` 内部:`Path("datasets") / "prompts" / "sessions" / f"FAILED_{timestamp}"` 与`mine()` 同样位置的字符串重复了三次（line 244, 300, 305, 437）——任何修改其中一处都会产生不一致。

**Fix:**
让 `_write_failed` 接受 base path 或共享 timestamp/out_dir 计算:

```python
def _write_failed(
    timestamp: str,
    error_key: str,
    base_dir: Path,
    extra: Optional[dict] = None,
) -> Path:
    failed = base_dir / f"FAILED_{timestamp}"
    failed.mkdir(parents=True, exist_ok=True)
    ...

# In mine(), compute once:
base = Path(output).parent if output else Path("datasets") / "prompts" / "sessions"
# ... then pass base to every _write_failed call.
```

或更稳健:统一使用 `out_dir` 即将-成为的 parent。当前形式下,任何用户传了 `--output ./customdir/run123` 的失败都会把 marker 写到 `datasets/prompts/sessions/`,这是一个明显的契约/最小惊讶违反。

## Warnings

### WR-01: `_load_session_dataset_resilient` 与 docstring/metrics 不一致——skip 计数未挂钩

**File:** `evolution/prompts/evolve_prompt_sections.py:119-163`
**Issue:**
`session_prompt_miner.py:262-267` 的 `_fresh_metrics` docstring 显式承诺:

> jsonl_skipped_lines: int — Line-level — JSONL bad-line skip counter from D-24,
> maintained by Plan 04 evolve_prompt_sections.py's `_load_session_dataset_resilient` helper.

但 `_load_session_dataset_resilient` 实际实现 (line 119-163) 只把 skip count 返回成 second tuple element,**从未** 写入任何 `metrics` 字典。调用方 (line 343-354) 也仅打印 `session_skipped`,未将其传给 miner 的 metrics。结果:
- `jsonl_skipped_lines` metric 字段永远是 0;
- B3 fix 注释里所谓"两个 metric channel 独立写入"的承诺只兑现了一半——B3 fix 的设计在落地时被截短了。

**Fix:**
方案 A——做实承诺：
```python
def _load_session_dataset_resilient(
    session_dir: Path,
    metrics: Optional[dict] = None,
) -> tuple["PromptBehavioralDataset", dict]:
    ...
    if metrics is not None:
        metrics["jsonl_skipped_lines"] = (
            metrics.get("jsonl_skipped_lines", 0) + sum(skipped.values())
        )
```
然后调用点（`evolve` 中 step 5b）传入一个 metrics dict 并随 evolve metrics.json 一起持久化。

方案 B——降低承诺：把 `session_prompt_miner._fresh_metrics` docstring 改成"该字段保留以供未来 helper 使用,当前不会被任何代码写入",并删除 `_print_summary_table` 里 "JSONL skipped lines" 一行（line 222-225）。

当前状态是承诺-实现不一致,审计员/工具看到 metrics.jsonl_skipped_lines=0 会误以为没有坏行,即使 helper 真的跳过了行。

### WR-02: `mine_prompt_sessions.py` 模块顶部 `Optional` 双 import 风险及未使用 import

**File:** `evolution/prompts/session_prompt_miner.py:25`
**Issue:**
`session_prompt_miner.py` 顶部 import `hashlib`（line 25）但模块内未直接使用——hash 计算全部通过 `_normalize_task_hash` 委托给 `prompt_dataset` 完成。同样 import 了 `Optional`、`field`、`dataclass`、`re`、`json` 等,其中 `hashlib` 是死 import。

**Fix:**
```python
# Remove:
import hashlib
```

### WR-03: `_extract_persona_drift` 假设 `drift_detector.thresholds[dim]` 存在,无验证

**File:** `evolution/prompts/session_prompt_miner.py:558-560`
**Issue:**
```python
for dim in DRIFT_DIMENSIONS:
    score = scores.get(dim, 0.0)
    if score > self.drift_detector.thresholds[dim]:   # ← KeyError if user passes incomplete dict
```

`__init__` 接受 `drift_thresholds: Optional[dict]` 而**没有验证 4 个 dim key 都存在**。如果调用方（如 CLI 解析坏 JSON 但部分字段成功)只给了 `{"tone": 0.5, "formality": 0.5}`, `DriftDetector` 的构造函数在 line 103 会 raise `ValueError`,然后 `SessionPromptMiner.__init__` 会让这个异常冒出（构造方法没 try/except）——这至少不会 silent-fail。但 `mine_prompt_sessions.py:347-348` 解析 drift_thresholds 时:

```python
raw = json.loads(Path(drift_thresholds_path).read_text())
drift_thresholds = {d: float(raw[d]) for d in DRIFT_DIMENSIONS}  # ← KeyError if any dim missing
```

会 `KeyError` → 走 `except Exception` (line 349) → silent disable persona_drift。这是设计内的优雅降级,所以正常路径下 OK。但**测试 `test_persona_drift_multi_dim_candidates`（line 345-362）显式构造了 `SessionPromptMiner(... drift_thresholds={...4 dims...})`,并 mock 了 `_check_one_run`,然后访问 `self.drift_detector.thresholds[dim]`**——这里依赖了 `DriftDetector.__init__` 完成的 thresholds 验证。如果未来重构里 `DriftDetector.__init__` 提前 return 或改成 lazy 初始化, line 560 会 KeyError。

更直接的隐患是 `scores.get(dim, 0.0)`（line 559）：如果 `_check_one_run` 出现 partial dict（如 LLM 部分字段失败）, `scores.get(dim, 0.0)` 会安静地用 0.0 替代——这与 Phase 18 `DriftDetector._check_one_run` 的 fallback 语义（全 0.0 fallback）不冲突,但在 partial-LLM-output 场景下,某些 dim 会被静默置 0,可能掩盖检测信号。

**Fix:**
低成本：在 SessionPromptMiner.__init__ DriftDetector 实例化处加一行注释,或者改为:
```python
missing = set(DRIFT_DIMENSIONS) - set(scores.keys())
if missing:
    console.print(f"[yellow]⚠ drift scores missing dims {missing}; skipping[/yellow]")
    return cands
```
作为对 `_check_one_run` partial-output 的防御。

### WR-04: `_extract_oracle_disagreement` 是占位实现——任何 user→assistant 对都会被 emit 为 candidate

**File:** `evolution/prompts/session_prompt_miner.py:466-508`
**Issue:**
注释承认:

> Simplified: produce a candidate when (cheap rule) the actual assistant message is very short / fails a length-style sanity check vs the user message length — the LLM judge will decide whether this constitutes a disagreement worth keeping. Real oracle invocation is left to baseline_module.forward when the integration test mocks it; per D-04 the LLM judge is the source of truth, the proposer just nominates.

但实际代码 (line 489-507) 并没有任何长度比较,仅仅检查 `next_assistant`（被截断到 500 chars）是否非空,然后**无条件 emit**:

```python
if not next_assistant:
    continue
# Oracle prediction: ... Real oracle invocation is left to baseline_module.forward ...
cands.append(Candidate(...))
self.metrics["total_candidates_by_signal"]["oracle_disagreement"] += 1
```

后果：
- 启用 oracle_disagreement 信号后,所有非空 user→assistant pairs 会全部被打成候选,然后 100% 进入 LLM judge——LLM 成本会爆炸。
- 注释承诺的"cheap rule (长度 sanity check)"被丢弃了,实际是 0 过滤。
- 即使 `baseline_module` 已经提供（line 472),代码也从未调用它的 `forward` 方法——只是把 `Path` 对象作为 truthy 检查。这违反了变量名暗示的 oracle 比较语义,该信号其实退化为"任何 user-assistant pair"。

**Fix:**
方案 A：实现一个最小可用的 cheap rule（如 len(next_assistant) < 50 时才 emit）作为初始版本:
```python
if not next_assistant or len(next_assistant) >= 50:
    continue
```
方案 B：抛出 `NotImplementedError`/在 CLI 里把 oracle_disagreement 标为 experimental, 禁止默认启用,直到真正的 oracle 比较接入。

当前 CLI 的默认 signals 包含 `oracle_disagreement`（mine_prompt_sessions.py:120）,意味着任何运行成熟数据集都会承受 100% LLM judge 成本。这是 prod 风险。

### WR-05: `_filter_secrets` 不过滤 LLM judge 输出 / `expected_behavior`

**File:** `evolution/prompts/session_prompt_miner.py:298-310, 711-727`
**Issue:**
`_filter_secrets` 在 judge 之前过滤 `c.task` / `c.downstream_context` / `c.originally_observed_behavior`——这是好做法。但 LLM judge 输出的 `v.expected_behavior` 可能包含从 task/context 中复述过来的敏感片段（即使原片段过了 SECRET_PATTERNS,LLM 仍可能"创造性地"复读到 rubric 里）。`miner_log.jsonl` 写入的 `user_message_excerpt` (mine_prompt_sessions.py:463) 截断到 200 chars,但 `expected_behavior` 全文落到 `train.jsonl`/`val.jsonl`/`holdout.jsonl` 里没有任何过滤。

最坏情况:用户文本 `"my password is hunter2"` 命中 SECRET_PATTERNS 被过滤 —— OK。但如果用户文本写 `"my password is X"` 没命中,LLM judge 写 `expected_behavior = "Agent should not echo password X"`——这条会原样持久化到训练集。

**Fix:**
在 `_judge_candidates`（line 627-633）落 `Verdict` 之前对 `expected` 也做一次 `_contains_secret` 检查:
```python
if _contains_secret(expected):
    self.metrics["secret_filter_skipped"] += 1
    continue
```
配合在 mine() 阶段 union 之后也对 final PromptBehavioralExample 做一次扫描。当前 threat register T-19-05-I 文档里如果只覆盖了用户输入的 JWT, expected_behavior 这条路径是漏洞。

### WR-06: `_judge_candidates` 在 exception path 上仍计数到 confirmed/false_positive,但 raw_verdict 会被强制设为 false_positive

**File:** `evolution/prompts/session_prompt_miner.py:605-624`
**Issue:**
parse failure path（line 605-611）：
```python
except Exception as exc:
    raw_verdict = "false_positive"
    ...
```
然后 line 613 `self.metrics["judge_calls"] += 1` 会增加调用计数——但是**LLM 调用其实失败了**。这会让 `judge_calls` 包含未成功的尝试,造成 cost report 高估。建议引入 `judge_call_failures` 计数器并将失败的 try 排除在 judge_calls 之外,或者至少分开统计:

```python
try:
    pred = self.judge(...)
    self.metrics["judge_calls"] += 1
    self.metrics["judge_calls_by_signal"][c.signal] += 1
    ...
except Exception as exc:
    self.metrics.setdefault("judge_call_failures", 0)
    self.metrics["judge_call_failures"] += 1
    raw_verdict = "false_positive"
    ...
```

**Fix:**
按上述差错分离 judge_calls 与 judge_call_failures。

### WR-07: `mine` 的 `if not isinstance(messages, list)` 后没有为 unloadable session 增加 metric

**File:** `evolution/prompts/session_prompt_miner.py:673-678`
**Issue:**
```python
session = self._load_session(sp)
if not session:
    continue                    # session_load_failures 已计
messages = session.get("messages") or []
if not isinstance(messages, list):
    continue                    # ← 没有计入任何 metric
```

如果 session JSON parses fine 但 `messages` 字段不是 list（比如有人手工产了畸形数据,messages 写成了 dict),代码静默跳过,**没有任何 metric 记录这种污染**。在 `_print_summary_table` 里也看不到这种文件数,审计员无法 tell"为什么 sessions=50 但 total_candidates=0"——是 session 内容空,还是 schema 错。

**Fix:**
新增 `metrics["session_schema_invalid"]` 字段或合并到 `session_load_failures`:
```python
if not isinstance(messages, list):
    self.metrics["session_load_failures"] += 1
    continue
```
（这违反了 B3 fix 的"file-level vs line-level"语义,所以更建议新增独立 key。）

### WR-08: `evolve_prompt_sections.py` 中 `drift_thresholds_raw = json.loads(...).read_text()` 没有 try/except

**File:** `evolution/prompts/evolve_prompt_sections.py:624`
**Issue:**
```python
drift_thresholds_raw = json.loads(drift_thresholds_path.read_text())
drift_thresholds = {
    d: drift_thresholds_raw[d] for d in DRIFT_DIMENSIONS
}
```

如果 `drift_thresholds_path` 文件存在（Click 的 `exists=True` 已检查）但内容是无效 JSON 或缺 dim key, 上面两行会 raise `JSONDecodeError`/`KeyError`,直接把整个 `evolve()` 拖死——而此时 GEPA 已经跑过 N 小时,数据集已经生成（synthetic 路径可能花了几美元 LLM budget),没有保存任何 partial output。

对比 `mine_prompt_sessions.py:346-356` 同一文件的 graceful disable 模式,这里应该至少:
- 抛出更清晰的错误信息（指出该文件应当通过 `build_drift_calibration` 产生)
- 或捕获并将 evolved sections 保存到 FAILED_/ 目录后再 exit。

**Fix:**
```python
try:
    drift_thresholds_raw = json.loads(drift_thresholds_path.read_text())
    drift_thresholds = {d: drift_thresholds_raw[d] for d in DRIFT_DIMENSIONS}
except (json.JSONDecodeError, KeyError) as e:
    console.print(
        f"[red]Cannot parse drift_thresholds {drift_thresholds_path}: "
        f"{type(e).__name__}: {e}\n  Run "
        f"`python -m evolution.prompts.build_drift_calibration` to regenerate.[/red]"
    )
    sys.exit(1)
```
应该在 GEPA 调用之前 fail-fast。

## Info

### IN-01: `available_sections_summary` 的 Signature desc 与实际实现的措辞不一致

**File:** `evolution/prompts/session_prompt_miner.py:170-172, 635-645`
**Issue:**
DSPy Signature `ConfirmBehavioralExample.available_sections_summary` desc:

> Newline-separated '- <section_id>: <<=200-char excerpt>' for all current sections + platform_hints.<key> list

实际 `_format_sections_summary` 把 `current_sections` 里的每个 section 一行拼出, platform_hints.<key> 子段已经是 current_sections 的元素之一。所以 "+ platform_hints.<key> list" 暗示"额外有一段平台 token 列表"——但实际没有这样的额外段。LLM judge 解读这段 desc 可能会以为还要看一个独立的 list,降低 prompt 清晰度。

**Fix:**
改为:
```
"Newline-separated '- <section_id>: <<=200-char excerpt>' for all current sections including platform_hints.<key> sub-sections."
```

### IN-02: 装饰器/常量重复造成大文件:`evolve_prompt_sections.py` 已突破 1200 行

**File:** `evolution/prompts/evolve_prompt_sections.py:1-1201`
**Issue:**
单文件 1200+ 行,包含 evolve()、_generate_diff、_load_session_dataset_resilient、_resolve_effective_mode、Click main——一个函数 `evolve()` 自己就占 800+ 行,内嵌 11 个步骤。可维护性差,review 工具难以聚焦。

**Fix:**
独立拆分子模块（保持 Phase 1 conventions）:
- `_session_union.py` 持有 `_load_session_dataset_resilient` + step 5b 的 union 算法
- `_holdout_eval.py` 持有 step 9（baseline vs evolved）
- `_constraints_step.py` 持有 step 8

这是 v2/重构议题, 不阻挡 Phase 19 但应纳入 backlog。

### IN-03: Test fixture `session_with_secret.json` 的 JWT 字符串容易让 SECRET_PATTERNS 失效

**File:** `tests/prompts/fixtures/sessions/session_with_secret.json:5`
**Issue:**
fixture 的 JWT 是 `eyJhbGciOiJIUzI1NiJ9.eyJpZCI6MX0.signature...` 加了 padding——这是为了"确保命中 SECRET_PATTERNS"。问题是：如果未来 `_contains_secret` 改阈值或者 JWT 模式正则收紧, fixture 还可能继续过测试,造成测试稳健度下降。

**Fix:**
在测试中显式断言 `assert _contains_secret(content) is True` for 该 user message,作为 fixture 的健康检查。

### IN-04: `mine_prompt_sessions._parse_signals` 接受空白前后但不接受 `--signals ""`(空字符串）的失败信息可改进

**File:** `evolution/prompts/mine_prompt_sessions.py:65-66`
**Issue:**
```python
if not items:
    raise click.UsageError("--signals is empty after parsing")
```
这条 message 在 `--signals ""` / `--signals ","` 时都触发, 但用户面对"empty after parsing"会困惑——"我没传 empty 啊"。

**Fix:**
```python
raise click.UsageError(
    "--signals contained no valid signal names. "
    f"Pass one or more of {sorted(VALID_SIGNALS)} comma-separated."
)
```

### IN-05: 注释 `# i must follow an assistant turn (correction implies prior assistant action)` 错误地讲述变量名

**File:** `evolution/prompts/session_prompt_miner.py:382`
**Issue:**
注释说 "i must follow an assistant turn",但 `i` 是用户消息的 index, 要求 `i-1` 是 assistant。注释应是 "user turn at i must follow an assistant turn at i-1"。小问题,但可读性。

**Fix:**
```python
# Stage 0: user message at i must follow an assistant turn at i-1
```

---

_Reviewed: 2026-05-19T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
