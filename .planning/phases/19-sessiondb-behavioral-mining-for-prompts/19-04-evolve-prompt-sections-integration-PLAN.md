---
phase: 19-sessiondb-behavioral-mining-for-prompts
plan: 04
type: execute
wave: 4
depends_on:
  - 19-01
  - 19-02
  - 19-03
files_modified:
  - evolution/prompts/evolve_prompt_sections.py
autonomous: true
requirements:
  - PMPT-V2-04
tags:
  - prompt
  - cli
  - integration
  - dataset-union

must_haves:
  truths:
    - "[D-21] `evolve_prompt_sections.py` 新增 `--session-source <dir>` Click option，类型 click.Path(exists=True, path_type=Path)，默认 None；未传时一切原行为不变"
    - "[D-21] --session-source 在 joint mode 与 round-robin mode 都自动消费（dataset union 在 mode 分叉之前发生），无需额外 flag"
    - "[D-16] union 行为：synthetic split 与 session split 各自 hash 去重，按 (hash, split) 合并；同 hash 跨数据源时 session 例优先（保留 mining_signals 字段）"
    - "[D-16] 跨 split hash 去重保证 train/val/holdout 互不重叠（session-derived 例 hash 决定它落 train 时不可能同时出现在 val）"
    - "[D-22] **不动** `build_drift_calibration.py`（不为 calibration 加 --session-source）；Plan 04 不应有任何文件修改触及 build_drift_calibration.py"
    - "[D-13/D-14] --behavioral-multiplier 通过 mine_prompt_sessions CLI 已落地的 train-only 复制保留在 session-source 目录的 train.jsonl 中；evolve_prompt_sections 加载时不复制（已展开）"
    - "[D-24] 加载 session-source 目录的 train.jsonl/val.jsonl/holdout.jsonl 走 try/except per line + 跳过坏行；skip 率 > 5% Rich console warn"
    - "[D-24] 不重写 `PromptBehavioralDataset.load`（CONTEXT 显式约束 v2-STAB-01 范围）；JSONL 容错通过新 helper `_load_jsonl_skip_bad` 实现在 evolve_prompt_sections.py 调用点"
    - "Step 8c DriftDetector wiring（evolve_prompt_sections.py lines 508-617）零修改 — Phase 18 资产复用不动"
  artifacts:
    - path: "evolution/prompts/evolve_prompt_sections.py"
      provides: "新增 --session-source Click flag + 新增 union 块（步骤 5b）+ 新增 _load_session_dataset_resilient 辅助"
      contains:
        - "--session-source"
        - "session_source"
        - "_load_session_dataset_resilient"
  key_links:
    - from: "evolution/prompts/evolve_prompt_sections.py:evolve"
      to: "evolution/prompts/session_prompt_miner.py (Plan 02 暴露 task hash)"
      via: "import _normalize_task_hash for D-16 union dedup（已在 Plan 01 暴露于 prompt_dataset.py 顶层）"
      pattern: "from evolution\\.prompts\\.prompt_dataset import _normalize_task_hash"
    - from: "evolution/prompts/evolve_prompt_sections.py:evolve"
      to: "evolution/prompts/prompt_dataset.py:PromptBehavioralDataset"
      via: "load session JSONL via helper + 同 split union with synthetic"
      pattern: "_load_session_dataset_resilient"
---

<objective>
扩展 `evolution/prompts/evolve_prompt_sections.py` 加入 `--session-source <dir>` Click flag（D-21），实现 synthetic + session 数据集 hash dedup union（D-16），并加入 JSONL bad-line tolerance helper（D-24）。在 joint 与 round-robin mode 双 pipeline 上 transparent 工作。**严格不动** Phase 18 既有 DriftDetector step 8c wiring（lines 508-617）与 build_drift_calibration.py（D-22）。

Purpose: Phase 19 Wave 4 — 让 Plan 03 mine_prompt_sessions 产出的数据集直接被既有 GEPA 优化管线消费，闭合"挖矿 → 训练数据 → 优化"循环。
Output: ~80 LoC delta on evolve_prompt_sections.py（1 new Click option + 1 new helper + 1 new dataset union block + main/evolve 参数 thread）。
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
@.planning/phases/19-sessiondb-behavioral-mining-for-prompts/19-03-SUMMARY.md
@evolution/prompts/evolve_prompt_sections.py
@evolution/prompts/prompt_dataset.py
@evolution/prompts/session_prompt_miner.py
@evolution/tools/session_miner.py
</context>

<interfaces>
<!-- From evolution/prompts/evolve_prompt_sections.py (current state, post-Phase 18) -->

Current `evolve()` signature (line 116):
```python
def evolve(
    section: Optional[str] = None,
    iterations: int = 10,
    eval_source: str = "synthetic",
    hermes_repo: Optional[str] = None,
    dry_run: bool = False,
    model: Optional[str] = None,
    api_base: Optional[str] = None,
    mode: str = "joint",
    drift_thresholds_path: Path = Path("datasets/prompts/drift_thresholds.json"),
): ...
```

Current `main()` signature (line 1054):
```python
def main(section, iterations, eval_source, hermes_repo, dry_run, model,
         api_base, mode, drift_thresholds_path): ...
```

Existing dataset gen block (lines 251-276) — INSERTION POINT for D-16 union (after line 276):
```python
if eval_source == "synthetic":
    builder = PromptDatasetBuilder(config)
    dataset = builder.generate(original_sections)
    save_path = Path("datasets") / "prompts"
    dataset.save(save_path)
    ...
elif eval_source == "load":
    dataset = PromptBehavioralDataset.load(dataset_path)

console.print(f"  Split: ...")  # line ~274
# ← INSERT 5b block here
```

**Existing imports (lines 26-29)** — current multi-line style — Plan 04 必须保留多行结构：
```python
from evolution.prompts.prompt_dataset import (
    PromptDatasetBuilder,
    PromptBehavioralDataset,
)
```

Plan 04 helper `_load_session_dataset_resilient` 使用 `PromptBehavioralExample.from_dict` 与 `_normalize_task_hash`，必须显式导入。

Existing `--drift-thresholds-path` Click option (lines 1043-1053) — style template for new `--session-source`.

<!-- From evolution/prompts/prompt_dataset.py (Plan 19-01 ships) -->
```python
def _normalize_task_hash(task: str) -> str: ...
def _hash_to_split(h: str) -> str: ...
@dataclass
class PromptBehavioralExample:
    section_id: str; user_message: str; expected_behavior: str
    difficulty: str = "medium"; source: str = "synthetic"
    mining_signals: list[str] = field(default_factory=list)
class PromptBehavioralDataset:
    train: list[PromptBehavioralExample]
    val: list[PromptBehavioralExample]
    holdout: list[PromptBehavioralExample]
    def save(self, path: Path): ...
    @classmethod
    def load(cls, path: Path) -> "PromptBehavioralDataset": ...
```

<!-- From evolution/tools/session_miner.py:77-97 (reference pattern for D-24 helper) -->
```python
JSONL_BAD_LINE_WARN_THRESHOLD: float = 0.05

def _load_jsonl_skip_bad(path: Path) -> tuple[list[dict], int]:
    rows: list[dict] = []
    skipped = 0
    if not path.exists():
        return rows, 0
    with open(path) as f:
        for line in f:
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                skipped += 1
    return rows, skipped
```
</interfaces>

<tasks>

<task type="auto" tdd="true">
  <name>Task 4.1: 加 --session-source Click option + 参数 thread 到 evolve() + 引入 _load_session_dataset_resilient helper</name>
  <files>evolution/prompts/evolve_prompt_sections.py</files>

  <read_first>
    - evolution/prompts/evolve_prompt_sections.py (主要 lines 1-200 + 240-280 + 1000-1072 — 全文了解后必要 grep 定位插入点)
    - 重点确认 lines 26-29 imports 为多行风格（B2 fix前置要求）
    - evolution/prompts/session_prompt_miner.py (确认 Plan 02 暴露 split_and_duplicate / SessionPromptMiner)
    - evolution/prompts/prompt_dataset.py (Plan 19-01 后 _normalize_task_hash / _hash_to_split / mining_signals 都已暴露)
    - evolution/tools/session_miner.py lines 77-97 (_load_jsonl_skip_bad 参考模板)
    - .planning/phases/19-sessiondb-behavioral-mining-for-prompts/19-PATTERNS.md §2.2.A-B + §4.4 (lines 644-685, 898-906)
  </read_first>

  <behavior>
    - Test 1: `python -m evolution.prompts.evolve_prompt_sections --help` 含 `--session-source` 选项；exit 0
    - Test 2: --session-source 默认 None；不传时 evolve() 中 `session_source` 参数为 None
    - Test 3: 不传 --session-source 时，evolve() 行为与 Phase 18 完全一致（dry-run 运行无 regression）
    - Test 4: --session-source 指向不存在路径 → click.Path(exists=True) 在 parse 时即拒绝，exit code != 0
    - Test 5: `_load_session_dataset_resilient(non_existent_dir)` 返回 `(PromptBehavioralDataset(), {"train":0,"val":0,"holdout":0})`，不抛错
    - Test 6: 一个有效目录含 valid + invalid lines → `_load_session_dataset_resilient` 返回 dataset + skip 计数 dict（每 split 独立计 skip）
    - Test 7: skip 率 > 5% 时，console 输出 yellow warning 含 "skipped" 字符串
    - Test 8 (B2 fix): 模块顶部 imports 后，下列符号可直接 import：`PromptDatasetBuilder, PromptBehavioralDataset, PromptBehavioralExample, _normalize_task_hash`
  </behavior>

  <action>
    打开 `evolution/prompts/evolve_prompt_sections.py`，做以下 **4 处** 精确插入：

    **Edit 1 — Imports（B2 fix: 精确多行 patch 替换 lines 26-29）**：

    当前 (lines 26-29)：
    ```python
    from evolution.prompts.prompt_dataset import (
        PromptDatasetBuilder,
        PromptBehavioralDataset,
    )
    ```

    替换为：
    ```python
    from evolution.prompts.prompt_dataset import (
        PromptDatasetBuilder,
        PromptBehavioralDataset,
        PromptBehavioralExample,   # NEW: Phase 19 D-16 union helper 使用
        _normalize_task_hash,      # NEW: Phase 19 D-15/D-16 hash dedup
    )
    ```

    **B2 fix 原则**：保留既有 multi-line 风格；不要单行化；不要在原导入语句基础上"尾部追加" — 而是用 Edit 工具针对该 4 行 import 块做精确替换。每个新符号必须独立一行（便于 grep 单行精确匹配）。

    **Edit 2 — 在 `# ── Main Pipeline` 注释之前（约 line 113，但在 `_compose_diff` 等 helper 之后）插入新 helper**：

    ```python
    # ── Phase 19 D-24: JSONL bad-line tolerance ──────────────────────────
    _SESSION_SOURCE_BAD_LINE_WARN: float = 0.05

    def _load_session_dataset_resilient(
        session_dir: Path,
    ) -> tuple["PromptBehavioralDataset", dict]:
        """Load PromptBehavioralDataset from <dir>/{train,val,holdout}.jsonl
        with per-line try/except. Phase 19 D-24 mirror of Phase 14's
        _load_jsonl_skip_bad — we do NOT modify PromptBehavioralDataset.load
        (CONTEXT explicit v2-STAB-01 boundary).

        Args:
            session_dir: Directory produced by mine_prompt_sessions.

        Returns:
            (dataset, skipped_counts) where skipped_counts is
            {"train": int, "val": int, "holdout": int}. Missing files yield
            an empty split with skip=0.

        Side effects:
            Prints yellow Rich warning when any split's skip rate > 5%.
        """
        dataset = PromptBehavioralDataset()
        skipped = {"train": 0, "val": 0, "holdout": 0}
        for split_name in ("train", "val", "holdout"):
            jp = session_dir / f"{split_name}.jsonl"
            if not jp.exists():
                continue
            kept: list = []
            sk = 0
            with open(jp) as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        d = json.loads(line)
                        kept.append(PromptBehavioralExample.from_dict(d))
                    except (json.JSONDecodeError, TypeError, ValueError):
                        sk += 1
            setattr(dataset, split_name, kept)
            skipped[split_name] = sk
            total = len(kept) + sk
            if total > 0 and sk / total > _SESSION_SOURCE_BAD_LINE_WARN:
                console.print(
                    f"[yellow]⚠ session-source {split_name}: skipped {sk}/{total} "
                    f"bad JSONL lines ({sk / total * 100:.1f}%) > 5% threshold[/yellow]"
                )
        return dataset, skipped
    ```

    `json`、`PromptBehavioralExample` 已在 Edit 1 imports 中显式导入；不需要额外操作。

    **Edit 3 — 加 Click option `--session-source`**（在既有 `--drift-thresholds-path` option 之后，line ~1053）：

    通过 grep 定位 `@click.option("--drift-thresholds-path"` 起始 line，在其匹配的 `)` 结束（约 line 1053）之后、`def main(` 之前插入新 option block：
    ```python
    @click.option(
        "--session-source",
        type=click.Path(exists=True, path_type=Path),
        default=None,
        help=(
            "Phase 19 D-21. Path to a directory produced by "
            "`python -m evolution.prompts.mine_prompt_sessions` containing "
            "train.jsonl / val.jsonl / holdout.jsonl. When provided, the "
            "session-mined dataset is UNION-merged (hash dedup, session "
            "wins on collision per D-16) with the synthetic PromptDatasetBuilder "
            "output. Works in both --mode joint and --mode round-robin. "
            "Omitting this flag preserves pre-Phase-19 behavior."
        ),
    )
    ```

    **Edit 4 — Thread `session_source` 参数到 `main()` 和 `evolve()` 签名**：

    a) 修改 `main()` 签名（line 1054-1055）：
    ```python
    def main(section, iterations, eval_source, hermes_repo, dry_run, model,
             api_base, mode, drift_thresholds_path, session_source):
    ```

    b) 修改 `main()` 内 `evolve(...)` 调用（line 1057-1067），在 kwargs 列表末尾加 `session_source=session_source,`：
    ```python
    evolve(
        section=section,
        iterations=iterations,
        eval_source=eval_source,
        hermes_repo=hermes_repo,
        dry_run=dry_run,
        model=model,
        api_base=api_base,
        mode=mode,
        drift_thresholds_path=drift_thresholds_path,
        session_source=session_source,  # ← new
    )
    ```

    c) 修改 `evolve()` 签名（line 116-126），在 `drift_thresholds_path:` 后追加：
    ```python
    session_source: Optional[Path] = None,
    ```

    d) 修改 `evolve()` docstring（line 127-147），在 `drift_thresholds_path:` Args 段后追加：
    ```python
        session_source: Optional Path to a directory produced by
            `python -m evolution.prompts.mine_prompt_sessions`. When given,
            the session-mined dataset (train/val/holdout JSONL) is unioned
            with the synthetic dataset via hash dedup (Phase 19 D-21/D-16).
            None = pre-Phase-19 behavior (synthetic only). Works in both
            joint and round-robin modes.
    ```

    依据 (per D-21/D-22/D-24)：
    - 4 处插入分别独立：Edit 1（imports B2 fix）+ Edit 2（helper）+ Edit 3（Click option）+ Edit 4（signature thread）
    - **B2 fix**：每个新 import 符号独占一行；不依赖 multi-line grep "兜底"；每个符号 单行 grep 必须精确命中
    - Click option `exists=True` 让用户传错路径在 parse 时即报错；与既有 `--drift-thresholds-path` 风格一致
    - helper 走 `setattr(dataset, split_name, kept)` 而非 `dataset.train = kept` 是为了对 train/val/holdout 三 split 复用同一循环
    - Edit 不触及 step 8c DriftDetector wiring（lines 508-617）— 验证 grep 在 acceptance criteria 显式落地
  </action>

  <verify>
    <automated>cd /Users/slj/项目/hermes-agent-self-evolution &amp;&amp; python -c "
import subprocess, json, tempfile
from pathlib import Path

# T1: --help has --session-source
r = subprocess.run(['python','-m','evolution.prompts.evolve_prompt_sections','--help'], capture_output=True, text=True)
assert r.returncode == 0, r.stderr
assert '--session-source' in r.stdout

# T2 / T3: signature accepts session_source kwarg
from evolution.prompts.evolve_prompt_sections import evolve, _load_session_dataset_resilient
import inspect
sig = inspect.signature(evolve)
assert 'session_source' in sig.parameters
assert sig.parameters['session_source'].default is None

# T4: invalid path rejected at parse time
r2 = subprocess.run(['python','-m','evolution.prompts.evolve_prompt_sections',
                     '--session-source','/totally/missing','--dry-run'],
                    capture_output=True, text=True)
assert r2.returncode != 0

# T5: missing dir helper safe
ds, skipped = _load_session_dataset_resilient(Path('/totally/missing'))
assert ds.train == [] and ds.val == [] and ds.holdout == []
assert skipped == {'train':0,'val':0,'holdout':0}

# T6: valid + invalid lines
with tempfile.TemporaryDirectory() as tmp:
    d = Path(tmp)
    (d/'train.jsonl').write_text(
        json.dumps({'section_id':'memory_guidance','user_message':'m','expected_behavior':'e','difficulty':'easy','source':'session','mining_signals':['user_correction']}) + '\n'
        + '{not valid json\n'
        + json.dumps({'section_id':'memory_guidance','user_message':'m2','expected_behavior':'e','source':'session'}) + '\n'
    )
    (d/'val.jsonl').write_text(json.dumps({'section_id':'x','user_message':'v','expected_behavior':'e'}) + '\n')
    ds, sk = _load_session_dataset_resilient(d)
    assert len(ds.train) == 2, ds.train
    assert sk['train'] == 1, sk
    assert len(ds.val) == 1
    assert sk['val'] == 0

# T8 (B2 fix): all 4 symbols import successfully (per-symbol single-line grep gate)
from evolution.prompts.evolve_prompt_sections import (
    PromptDatasetBuilder,
    PromptBehavioralDataset,
    PromptBehavioralExample,
    _normalize_task_hash,
)
assert callable(_normalize_task_hash)
print('PASS')
"</automated>
  </verify>

  <acceptance_criteria>
    - `grep -nE '@click\.option\(\s*\"--session-source\"' evolution/prompts/evolve_prompt_sections.py` 命中 1 次
    - `grep -nE 'session_source: Optional\[Path\] = None' evolution/prompts/evolve_prompt_sections.py` 命中 1 次（evolve 签名）
    - `grep -nE 'session_source=session_source' evolution/prompts/evolve_prompt_sections.py` 命中 1 次（main → evolve 传递）
    - `grep -nE 'def _load_session_dataset_resilient' evolution/prompts/evolve_prompt_sections.py` 命中 1 次
    - **B2 fix precise per-symbol single-line grep gates**（每行精确命中，不依赖 multi-line / 兜底）：
      - `grep -nE '^\s+PromptBehavioralExample,' evolution/prompts/evolve_prompt_sections.py` 命中 ≥ 1 行
      - `grep -nE '^\s+_normalize_task_hash,' evolution/prompts/evolve_prompt_sections.py` 命中 ≥ 1 行
      - `grep -nE '^\s+PromptDatasetBuilder,' evolution/prompts/evolve_prompt_sections.py` 命中 ≥ 1 行（保留既有 import）
      - `grep -nE '^\s+PromptBehavioralDataset,' evolution/prompts/evolve_prompt_sections.py` 命中 ≥ 1 行（保留既有 import）
    - `grep -c '@click\.option' evolution/prompts/evolve_prompt_sections.py` == 既有数量 + 1（即在原 8 个基础上 → 9 个 — 由实际既有数量校验）
    - 步骤 8c DriftDetector wiring 保持完整：`grep -c 'DriftDetector(' evolution/prompts/evolve_prompt_sections.py` 等于 Plan 04 修改**前**的数量（即 zero diff on step 8c block）— 通过 `git diff -- evolution/prompts/evolve_prompt_sections.py | grep -E '^[\\+\\-].*DriftDetector\\(' | wc -l` 应为 0
    - build_drift_calibration.py **零修改**：`git diff -- evolution/prompts/build_drift_calibration.py | wc -l` == 0
    - 现有 tests/prompts/ 110 测试零 regression：`python -m pytest tests/prompts/ -x -q`
  </acceptance_criteria>

  <done>
    --session-source Click flag 注册，main/evolve 签名延伸至 session_source 参数，新 helper `_load_session_dataset_resilient` 暴露并行为正确（含 5% warn）。B2 fix：imports 块为精确多行 patch，每个新符号独立单行，单行 grep 全部命中（不依赖 multi-line 兜底）。Step 8c DriftDetector wiring 与 build_drift_calibration.py 完全未触碰（D-22）。
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 4.2: 在 evolve() 中插入 dataset union 块（步骤 5b — D-16 / D-21 行为）</name>
  <files>evolution/prompts/evolve_prompt_sections.py</files>

  <read_first>
    - evolution/prompts/evolve_prompt_sections.py（Task 4.1 之后状态 — 主要 lines 245-285 dataset 生成块附近）
    - .planning/phases/19-sessiondb-behavioral-mining-for-prompts/19-PATTERNS.md §2.2.C (lines 687-724)
    - evolution/prompts/prompt_dataset.py（Plan 01 暴露的 _normalize_task_hash）
  </read_first>

  <behavior>
    - Test 1: 不传 session_source（None）→ dataset 大小与原 synthetic 一致；无新 console 输出
    - Test 2: session_source 指向有效目录 + 无 hash 冲突 → 各 split 长度 = synthetic + session 之和
    - Test 3: session_source 与 synthetic 同 hash collision（同 user_message + 同 split）→ 该 hash 在 union 后仅出现一次，且来自 session（source='session', mining_signals 非空）
    - Test 4: session 例 hash 落到 holdout（synthetic 中该 hash 落 train）→ union 后 holdout 含 session 例；train 中该 hash 被丢弃（D-15 + D-16：同 hash 单一切分；session 切分优先）
    - Test 5: console 输出含 "Loading session-mined dataset" 和 "After union:" 字串
    - Test 6 (W4 fix): dry-run gate 在 union 块（"Phase 19 D-21" 注释）之前；用 awk 验证 `if dry_run:` 出现在 D-21 注释行之前
  </behavior>

  <action>
    打开 `evolution/prompts/evolve_prompt_sections.py`，**找到** 现有 dataset 加载块的结尾（line ~276，紧跟 `console.print(f"  Split: ...")` 之后），在其后插入新 union 块。

    通过 grep 定位精确位置：找 `console.print(\s*$.+?Split.+?train.+?val.+?holdout` 行，在该 print 之后、`# ── 6. Optimization` 注释之前插入。

    **W4 修复约束**：dry-run gate（既有的 `if dry_run:` block，约 line ~187 sys.exit()）必须出现在 union 块（包含 `# ── 5b. Phase 19 D-21` 注释）**之前**。union 块插入时务必在 dataset 加载块之后、`# ── 6.` 之前 — 而不是 dry-run gate 之前。这确保 dry-run 路径不进入 union（dry-run sys.exit 已经更早执行）。

    新 union 块：
    ```python
    # ── 5b. Phase 19 D-21 / D-16: Union session-mined dataset ───────────
    if session_source is not None:
        console.print(
            f"\n[bold]Loading session-mined dataset[/bold] from {session_source}"
        )
        session_dataset, session_skipped = _load_session_dataset_resilient(
            Path(session_source)
        )
        console.print(
            f"  Session split: {len(session_dataset.train)} train / "
            f"{len(session_dataset.val)} val / {len(session_dataset.holdout)} holdout"
        )
        if any(session_skipped.values()):
            console.print(
                f"  (skipped lines: train={session_skipped['train']} "
                f"val={session_skipped['val']} holdout={session_skipped['holdout']})"
            )

        # D-16: per-split hash dedup. Session example wins on collision.
        # Cross-split hash dedup: an example's split is fully determined by
        # _hash_to_split — so if session example lands in 'holdout' and synthetic
        # example with the same hash sits in 'train', the synthetic one is
        # dropped from train (session wins; session sits in its computed split).
        # We achieve this via a two-pass union:
        #   1) Per split: dedup synthetic vs session, session wins.
        #   2) Drop synthetic examples whose hash exists in any session split.
        session_hashes_by_split: dict[str, dict[str, "PromptBehavioralExample"]] = {
            split_name: {
                _normalize_task_hash(ex.user_message): ex
                for ex in getattr(session_dataset, split_name)
            }
            for split_name in ("train", "val", "holdout")
        }
        all_session_hashes: set[str] = set()
        for split_name in ("train", "val", "holdout"):
            all_session_hashes |= set(session_hashes_by_split[split_name].keys())

        for split_name in ("train", "val", "holdout"):
            synth_split = getattr(dataset, split_name)
            synth_kept: list = []
            for ex in synth_split:
                h = _normalize_task_hash(ex.user_message)
                if h in all_session_hashes:
                    continue  # session wins (D-16); drop synthetic across splits
                synth_kept.append(ex)
            # Merge: kept synthetic + this split's session entries
            merged = synth_kept + list(session_hashes_by_split[split_name].values())
            setattr(dataset, split_name, merged)

        console.print(
            f"  After union: {len(dataset.train)} train / "
            f"{len(dataset.val)} val / {len(dataset.holdout)} holdout"
        )
    ```

    依据 (per D-15/D-16/D-21)：
    - 两步去重：(1) per-split session-wins-on-collision (2) cross-split synthetic drop for any hash that exists in any session split — 保证 cross-split hash 唯一性（D-15 约束）
    - union 块在 mode 分叉（line 278 处 `if effective_mode == "joint":`）之前发生，确保 joint 与 round-robin 都看到统一 dataset（D-21）
    - 用 `_normalize_task_hash` from prompt_dataset（Plan 01 已暴露），不重造 hash 函数
    - `dataset` 是 `PromptBehavioralDataset` 实例；用 `setattr(dataset, split_name, merged)` 替换其 3 个 split list（与 Phase 14 dataset union 风格对齐）
    - 不增加新的 console.print 在 dry-run path 之前 — union 块在 dataset 加载（步骤 5）之后、优化（步骤 6）之前，dry-run 块（步骤 3，line ~187）已经先于此 — 所以 dry-run 不进 union block。

    **W4 dry-run gate 验证**：dry-run 块在 line ~187 sys.exit；union 块在 line ~276+ 之后；所以 dry-run 不会执行 union — 这是 acceptable，因为 dry-run 目的是验证 setup 不实际跑训练。

    依据 (per D-21 "Joint mode and round-robin mode both auto consume session-source"):
    - union 块在 mode 分叉之前 — `dataset` 在两路 pipeline 都被使用，所以两路 mode 都消费 union 结果
  </action>

  <verify>
    <automated>cd /Users/slj/项目/hermes-agent-self-evolution &amp;&amp; python -c "
import json, tempfile, subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

# T2: union with no collision
with tempfile.TemporaryDirectory() as tmp:
    sess = Path(tmp)/'sess'; sess.mkdir()
    # session train: 2 unique
    (sess/'train.jsonl').write_text(
        json.dumps({'section_id':'memory_guidance','user_message':'session unique 1','expected_behavior':'e','source':'session','mining_signals':['user_correction']}) + '\n' +
        json.dumps({'section_id':'memory_guidance','user_message':'session unique 2','expected_behavior':'e','source':'session','mining_signals':['persona_drift']}) + '\n'
    )
    (sess/'val.jsonl').write_text('')
    (sess/'holdout.jsonl').write_text('')

    # Simulate union logic in isolation
    from evolution.prompts.prompt_dataset import PromptBehavioralDataset, PromptBehavioralExample, _normalize_task_hash
    synth = PromptBehavioralDataset(
        train=[PromptBehavioralExample(section_id='memory_guidance',user_message='synth t1',expected_behavior='e',source='synthetic')],
        val=[], holdout=[]
    )
    from evolution.prompts.evolve_prompt_sections import _load_session_dataset_resilient
    sess_ds, _ = _load_session_dataset_resilient(sess)
    # Manually run union (copy the production block — keep tests isolated from CLI)
    all_session_hashes = set()
    by_split = {}
    for name in ('train','val','holdout'):
        bs = {_normalize_task_hash(ex.user_message): ex for ex in getattr(sess_ds, name)}
        by_split[name] = bs
        all_session_hashes |= set(bs.keys())
    for name in ('train','val','holdout'):
        kept = [ex for ex in getattr(synth, name) if _normalize_task_hash(ex.user_message) not in all_session_hashes]
        setattr(synth, name, kept + list(by_split[name].values()))
    assert len(synth.train) == 3, f'expected 3 train, got {len(synth.train)}'

# T3: collision — session wins
synth = PromptBehavioralDataset(
    train=[PromptBehavioralExample(section_id='x',user_message='same msg',expected_behavior='synth',source='synthetic')],
    val=[], holdout=[]
)
sess_ds = PromptBehavioralDataset(
    train=[PromptBehavioralExample(section_id='x',user_message='same msg',expected_behavior='SESS',source='session',mining_signals=['user_correction'])],
    val=[], holdout=[]
)
all_h = set(); by = {}
for name in ('train','val','holdout'):
    bs = {_normalize_task_hash(ex.user_message): ex for ex in getattr(sess_ds, name)}
    by[name] = bs
    all_h |= set(bs.keys())
for name in ('train','val','holdout'):
    kept = [ex for ex in getattr(synth, name) if _normalize_task_hash(ex.user_message) not in all_h]
    setattr(synth, name, kept + list(by[name].values()))
assert len(synth.train) == 1
assert synth.train[0].source == 'session'
assert synth.train[0].expected_behavior == 'SESS'
assert synth.train[0].mining_signals == ['user_correction']

# T4: cross-split — session in holdout, synth same hash in train
synth = PromptBehavioralDataset(
    train=[PromptBehavioralExample(section_id='x',user_message='cross hash',expected_behavior='synth',source='synthetic')],
    val=[], holdout=[]
)
sess_ds = PromptBehavioralDataset(
    train=[], val=[],
    holdout=[PromptBehavioralExample(section_id='x',user_message='cross hash',expected_behavior='sess',source='session',mining_signals=['persona_drift'])]
)
all_h = set(); by = {}
for name in ('train','val','holdout'):
    bs = {_normalize_task_hash(ex.user_message): ex for ex in getattr(sess_ds, name)}
    by[name] = bs
    all_h |= set(bs.keys())
for name in ('train','val','holdout'):
    kept = [ex for ex in getattr(synth, name) if _normalize_task_hash(ex.user_message) not in all_h]
    setattr(synth, name, kept + list(by[name].values()))
assert len(synth.train) == 0, synth.train
assert len(synth.holdout) == 1
assert synth.holdout[0].source == 'session'

# T6 (W4 fix): dry-run gate appears BEFORE union block (D-21 annotation)
import subprocess
awk_check = subprocess.run(
    ['awk', '/if dry_run:/{found=1} /Phase 19 D-21/{if (!found) exit 1}',
     'evolution/prompts/evolve_prompt_sections.py'],
    capture_output=True
)
assert awk_check.returncode == 0, (
    'W4 fix regression: dry-run gate is NOT before union block (Phase 19 D-21)')
print('PASS')
"</automated>
  </verify>

  <acceptance_criteria>
    - `grep -nE "5b\. Phase 19 D-21 / D-16" evolution/prompts/evolve_prompt_sections.py` 命中 1 行
    - `grep -nE "session_hashes_by_split" evolution/prompts/evolve_prompt_sections.py` 命中（双向 dedup 变量）
    - `grep -nE "if session_source is not None:" evolution/prompts/evolve_prompt_sections.py` 命中（block guard）
    - `grep -nE 'After union:' evolution/prompts/evolve_prompt_sections.py` 命中（console 输出）
    - **W4 fix acceptance (新增)**：`awk '/if dry_run:/{found=1} /Phase 19 D-21/{if (!found) exit 1}' evolution/prompts/evolve_prompt_sections.py` 退出码 0（验证 dry-run gate 在 union 块的 "Phase 19 D-21" 注释行之前出现 — 不可调换次序）
    - Step 8c DriftDetector wiring 仍未触碰：`git diff HEAD -- evolution/prompts/evolve_prompt_sections.py | grep -E '^[\\+\\-]' | grep -iE 'DriftDetector|drift_per_dim|drift_thresholds_path' | wc -l` 输出小（仅可能影响 --session-source 紧邻的 import 或 helper，但不动 drift 逻辑）— 实际值由执行时人工 spot-check
    - build_drift_calibration.py **零修改**（确认未在本 plan 文件列表中）
    - 现有测试无 regression：`python -m pytest tests/prompts/ -x -q`
    - dry-run + --session-source 不抛错（exit code 0 或 1 都可，取决于环境是否有 hermes_agent_path）
  </acceptance_criteria>

  <done>
    --session-source 给定时，evolve() 在步骤 5b 完成 synthetic + session 数据集 hash dedup union；session 例在 collision 时胜出；cross-split hash 唯一性保留；joint 与 round-robin 两路 pipeline 都看到 union 后的统一 dataset；Phase 18 DriftDetector wiring 与 build_drift_calibration.py 完全未触碰。W4 fix：dry-run gate 在 union 块（"Phase 19 D-21"）之前由 awk 显式验证；不可被后续 refactor 调换次序。
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| --session-source argv → Path | 用户输入；click.Path(exists=True) 在 parse 时确保路径存在 |
| session-mined JSONL → in-memory PromptBehavioralExample | JSONL 可能含坏行；D-24 per-line try/except |
| union 后 dataset → GEPA/round-robin metric | 已审清洗数据，但仍可能有 outlier — metric 与 LLM judge 已有 fallback |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-19-04-T (T3) | Tampering / DoS | session JSONL 坏行中断加载 | mitigate | D-24: _load_session_dataset_resilient 用 try/except 包 json.loads + PromptBehavioralExample.from_dict；坏行计入 skipped；> 5% Rich warn |
| T-19-04-I (T4) | Info Disclosure | session-derived 历史包袱例进入 train | mitigate | D-09 在挖矿端（Plan 02 `_filter_drift`）已丢弃 surface drift 例；Plan 04 加载的 session JSONL 已是 post-drift 输出，无需额外过滤 |
| T-19-04-T | Tampering | hash collision 导致同 hash 双切分 | mitigate | D-15/D-16: union 块第二步明确 cross-split 检查，丢弃 synthetic 中已被任何 session split 占用的 hash |
| T-19-04-E | Elevation | --session-source 路径不存在 | mitigate | click.Path(exists=True) 在 parse 时拒绝；不会进 mine() body |
| T-19-04-R | Repudiation | session_skipped 计数仅 console | accept | metrics 仅存挖矿端 metrics.json；evolve_prompt_sections 加载侧的 skipped 计数仅作运行时 console.warn（不持久化到 evolve metrics.json — 范围外） |
</threat_model>

<verification>
- `python -m evolution.prompts.evolve_prompt_sections --help` 含 `--session-source`
- evolve() 签名含 `session_source: Optional[Path] = None`
- _load_session_dataset_resilient 在缺失 / 坏 JSONL 输入下 graceful
- Union 块的 2-step dedup（per-split session-wins + cross-split synth-drop）正确
- 步骤 8c DriftDetector wiring 与 build_drift_calibration.py 零修改（D-22）
- 现有 tests/prompts/ 110 测试无 regression
- dry-run + --session-source 不抛错
- `python -c "from evolution.prompts.evolve_prompt_sections import _load_session_dataset_resilient"` 不抛 ImportError
- **B2 fix**：单行 grep 对 4 个 import 符号全部精确命中
- **W4 fix**：awk 验证 dry-run gate 在 D-21 注释之前
</verification>

<success_criteria>
- 新增 1 个 Click option（--session-source）+ 1 个 helper（_load_session_dataset_resilient）+ 1 个 union block（5b）
- main → evolve 参数线程完整
- Union 行为正确：同 hash 跨数据源 session 胜出；同 hash 跨 split synthetic 丢弃
- joint 与 round-robin mode 双 pipeline 都自动消费 union 结果
- Phase 18 DriftDetector step 8c wiring 零修改
- build_drift_calibration.py 零修改（D-22）
- B2 fix：每个新 import 符号独立单行 + 单行 grep 全部精确命中
- W4 fix：dry-run gate 在 union 块之前（awk 验证）
- 现有 prompt 测试无 regression
</success_criteria>

<output>
After completion, create `.planning/phases/19-sessiondb-behavioral-mining-for-prompts/19-04-SUMMARY.md` 记录：
- 4 处 Edit 的精确 line ranges + line diff stat
- step 8c DriftDetector wiring 未修改的 git diff 证据
- union 4 个行为测试（no collision / same-split collision / cross-split collision / dry-run pass-through）的输出
- Plan 05 集成测试入口
- B2 fix 证据：4 个 import 符号单行 grep 输出
- W4 fix 证据：awk 命令输出 + 退出码 0
</output>
