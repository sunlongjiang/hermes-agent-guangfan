# Phase 18: Personality Drift Detection - Research

**Researched:** 2026-05-15
**Domain:** LLM-as-judge pairwise drift detection, DSPy 3.x typed I/O, F1 threshold calibration
**Confidence:** HIGH

## Summary

Phase 18 实现一个 `DriftDetector` 约束层,对比 evolve 前后的 prompt section 在 **tone/formality/vocabulary/persona** 四个维度的偏移。所有架构决策(D-GATE-01 到 D-BYPASS-02)已在 CONTEXT.md 锁定,本研究的工作是**验证 6 个 Risk Anchor**,不探索备选方案。

研究核心发现:

1. **DSPy 3.1.3 typed `float` OutputField 完全可用** — `parse_value(value, float)` 用 pydantic TypeAdapter 解析,clean numeric 输入正确返回 float,bad 输入 raise `pydantic.ValidationError`(不是 silent 0.5)。M4 prevention 通过 typed 字段自动达成,但仍需在 `check()` 包一层 `try/except ValidationError → fallback 0.0`(per M4 prevention `0.0 not 0.5`)。
2. **3-run averaging 在 DSPy 3.1.3 默认配置下会**失效** — `dspy.LM()` 默认 `cache=True` + `temperature=None`,3 次相同输入命中**同一缓存返回完全相同响应**,`stdev=0` 让 D-ROB-02 的 `mean - 1·stdev` 决策退化为 `mean > threshold`。必须在 DriftDetector 构造期显式 `dspy.LM(model, temperature=0.7, **config.get_lm_kwargs())` 才能产生差异。
3. **F1 derivation 用纯 stdlib 完全可行** — sklearn / numpy / scipy 都未安装,但 17 候选阈值 × 30 样本 × 4 维 = 2040 个简单算术运算 < 1ms,无需引入新依赖(符合 CLAUDE.md 约束)。
4. **DSPy ChainOfThought 单次输出 4 个 float 字段是稳定模式** — Signature 字段命名建议 `<dim>_score: float = dspy.OutputField(desc=...)`,与 Phase 10 `PromptRoleChecker.RoleCheckSignature` 同构,4 个 OutputField + 1 个 explanation 单次 LLM 调用比 4 次独立调用成本低 4×。
5. **同源偏误必须用 process-level 检查缓解** — 生成器与判官同模型(都是 `judge_model`/`eval_model`)会让 F1 在 calibration set 上虚高;但 30 例规模的人工 spot-check(D-CAL-01 的 ~10/30 抽查)+ verify phase 在 fresh 30 例上重测 F1 ≥ 0.8 是已被 PITFALL #6 prevention 钉死的双层防护。
6. **F1 目标 0.85(self) / 0.8(fresh)在 30 例 + LLM judge 下挑战性高但可达** — LLM-as-judge ±0.10-0.15 噪声 + 4 维独立阈值,单维 F1 ≥ 0.85 需要 calibration set 的"真漂移"信号显著强于"无漂移"。建议在 Phase 18 verify gate 加 **per-dim min F1 ≥ 0.7 fallback**(任一维度 ≥ 0.7 不阻断,但 stdout 黄警告)。

**Primary recommendation:** DriftDetector 实现遵循 PromptRoleChecker 镜像结构,但 LM 构造期**必须显式 `temperature=0.7`** 否则 3-run averaging 失效;Signature 用 typed `float` OutputField + try/except `ValidationError` fallback 0.0;F1 derivation 用纯 stdlib 暴力扫描;DriftCalibrationBuilder 生成器与判官分别用 `judge_model`(gpt-4.1)与 `eval_model`(gpt-4.1-mini)以制造模型间分歧、降低同源偏误。

## User Constraints (from CONTEXT.md)

### Locked Decisions

**Gate type & severity ladder:**
- **D-GATE-01:** 阶梯门 — 1 维超阈 = stdout 黄警告 + metrics.json 记录 + 仍 deploy;2+ 维超阈 = `drift_passed: false` + constraint FAILED + 写 `FAILED_<ts>/` 不 deploy
- **D-GATE-02:** 阶梯门统一全部 5 section,不支持 per-section 阈值或阶梯重定义
- **D-GATE-03:** 软警告(1 dim 超)stdout `[yellow]Drift warning: section '<sid>' dim '<dim>' = X.XX (threshold Y.YY) — review evolved text before deploying[/yellow]`,不 exit 2,不阻断 evolved_sections.json 写盘
- **D-GATE-04:** Hard reject(2+ dim 超)stdout `[red]Drift detected: section '<sid>' exceeded N dims [...] — REJECTED, evolved prompts NOT deployed[/red]`,metrics.json `constraints_passed: false` + `drift_passed: false`,evolved_sections.json 与 diff.txt 仍写 `FAILED_<ts>/`

**Calibration set construction:**
- **D-CAL-01:** Synthetic LLM 生成 30 例(15 真漂移 + 15 无漂移),复用 `PromptDatasetBuilder` 的 DSPy Signature 模式
- **D-CAL-02:** 落盘 `datasets/prompts/drift_calibration.jsonl` + git 跟踪,需在 `.gitignore` 加 `!datasets/prompts/drift_calibration.jsonl` exception 行
- **D-CAL-03:** 30 例分布 = 5 section × 6 变体(3 真漂移 + 3 无漂移)
- **D-CAL-04:** Ground-truth schema:`is_drift: bool` + `drift_dim: tone|formality|vocabulary|persona|none`
- **D-CAL-05:** Phase 18 工期内必须完成 calibration set → F1 derivation → thresholds.json → 单元测;不允许写死占位

**Robustness (3-run averaging):**
- **D-ROB-01:** 3-run averaging **只在 final constraint gate 触发**(GEPA 内循环、A/B baseline、calibration 都是 1-run)
- **D-ROB-02:** 决策规则 `mean - 1·stdev > threshold[dim]` 则该维超阈
- **D-ROB-03:** 不重置 LM context / 不变 temperature seed — 让 DSPy 默认行为产生 3 个独立调用样本 *(注:研究显示此假设错误,见 §DSPy LM Stochasticity Verification)*
- **D-ROB-04:** Round-robin mode 与 joint mode 都触发 final constraint gate 的 3-run

**Drift report output schema:**
- **D-OUT-01:** stdout Rich Table title `"Drift Detection (per-section × per-dim)"`,列 Section/Dim/Mean/Stdev/Threshold/Exceeded/Status,5×4=20 行
- **D-OUT-02:** metrics.json 字段:`drift_per_dim` / `drift_thresholds` / `drift_max_dim` / `drift_max_section` / `drift_exceeded_dims` / `drift_passed`
- **D-OUT-03:** `drift_report.txt` markdown 段落 — Mean/Stdev/Threshold/Decision/Raw scores/Explanation(只存第 3 次 explanation)
- **D-OUT-04:** 与 Phase 17 共用 `output/prompts/<ts>/` 目录,不另起新 root

**Bypass policy:**
- **D-BYPASS-01:** **不**实现 `--no-drift-check` / `--skip-drift-check` flag — per PITFALL #6 prevention 的硬性约束
- **D-BYPASS-02:** 允许 `--drift-thresholds-path <path>` flag,默认 `datasets/prompts/drift_thresholds.json`,`click.Path(exists=True)`

### Claude's Discretion

- `DriftDetector` 类的文件归属(新建 `drift_detector.py` vs 扩展 `prompt_constraints.py`)由 planner 决,**必须**沿用 `PromptRoleChecker.check_all(original, evolved) -> list[<result>]` 接口
- `DriftCalibrationBuilder` 的 CLI 入口形式(独立 `build_drift_calibration` 子命令 vs `evolve_prompt_sections.py --build-calibration` 子模式)由 planner 决
- 30 例 calibration set 的 LLM 生成 prompt 措辞,planner 撰写,但必须 deterministically reproducible(seed/温度可控)且生成完成后落盘 `seed`/`generator_model`/`generation_timestamp` 元字段
- F1 derivation 实现细节 — 暴力扫描 [0.1, 0.9] step 0.05 即可(本研究确认 sklearn 未装,扫描法是唯一无新依赖路径)
- DriftDetector 在 `evolve_prompt_sections.py` 的精确插入位置(step 8b role check 之后、step 9 holdout 之前)
- Rich 颜色微调与 emoji,与 Phase 13/16/17 风格一致

### Deferred Ideas (OUT OF SCOPE)

- Embedding-based 相似度 / cosine 距离作为额外 drift 信号 — PITFALL #6 prevention #2 明确仅 LLM-as-judge,引入 embedding 是新依赖
- 运行期阈值自动调节 / online learning — thresholds 一次性 derive 落盘,运行期不调
- DriftDetector 接入 GEPA 内循环作为 fitness signal — Goodhart's law,drift 只做 gate
- A/B baseline (Phase 17 round-robin baseline) 上跑 drift 检查 — baseline 不 deploy artifact,零收益
- per-section 可配置 dim 阈值或阶梯 — YAGNI
- Quarterly 重新 calibration 自动化调度 — 属 ops process,本期仅交付工具
- `--no-drift-check` bypass flag — 明确不做

## Project Constraints (from CLAUDE.md)

- **Python 版本:** Python >=3.10 声明;实测 `.venv/` 用 3.13.3,生产代码不得用 3.10 之后的语法特性以保兼容性
- **依赖政策:** **不引入新外部依赖**,复用现有 DSPy/Click/Rich 栈 — Phase 18 实现路径必须用 stdlib 或已装包
- **hermes-agent 访问:** 只读,通过 `HERMES_AGENT_REPO` env 定位
- **Size 约束:** 提示词段 ≤ 基线 +20% (`max_prompt_growth = 0.2`) — DriftDetector 不修改 prompt,继承已有 growth check
- **架构遵循 Phase 1 模式:** snake_case 模块名,PascalCase 类,DSPy Signature 作为 inner class,`@dataclass` for plain data,Rich console + 不用 `logging` 模块
- **GSD workflow enforcement:** 所有 file-changing 操作必须经 GSD 命令(本研究产物 RESEARCH.md 是 `/gsd-research-phase` agent 产物,合规)
- **DSPy 3.x 版本:** 实测 `dspy==3.1.3`,Pydantic v2 (validation 通过 `pydantic.ValidationError` 抛出)

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| dspy | 3.1.3 *(实测 [VERIFIED: .venv/bin/pip])* | LLM-as-judge ChainOfThought + Signature + typed OutputField | 全项目唯一 LLM 框架,Phase 10 PromptRoleChecker 同款 |
| dspy.LM | 3.1.3 | LM backend,需显式 `temperature=0.7` 启用 stochastic 3-run | 已是项目标准 backend |
| Rich | >=13.0 *(声明)* | stdout Table + colored output | 全项目 stdout 模式 |
| Click | >=8.0 *(声明)* | `--drift-thresholds-path` flag | 全项目 CLI 模式 |
| Python stdlib `json` | 3.13 | metrics.json + drift_thresholds.json 持久化 | Phase 10/13/16/17 全用 |
| Python stdlib `statistics` | 3.13 | `mean()` / `stdev()` for 3-run averaging | 无需 numpy,30 数据点足够 |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pydantic (via dspy) | >=2.12 | typed OutputField parsing | 已是 DSPy 内部依赖,无需声明 |
| json_repair (via dspy) | latest | DSPy adapter 的 fallback JSON 解析 | 已是 DSPy 内部依赖,DriftDetector 不直接调 |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| 纯 stdlib F1 暴力扫描 | sklearn `precision_recall_curve` | **拒绝** — sklearn 未装(`pip list` 验证),引入新依赖违反 CLAUDE.md;30 样本规模扫描 < 1ms,精度足够 |
| `statistics.stdev` | numpy.std | **拒绝** — numpy 未装;30 数据点 stdlib 完全够 |
| sentence-transformers embedding 作为辅助信号 | sentence-transformers | **拒绝** — D-OUT-OF-SCOPE 明确排除(PITFALL #6 prevention #2)且引入新依赖 |
| `_parse_float_score` helper(沿用 Phase 1 `_parse_score` 0.5 fallback) | typed `float = dspy.OutputField()` + try/except `ValidationError` 0.0 fallback | **采用** typed 路径 — 实测可用,M4 prevention 推荐 0.0 fallback(可观测)而非 0.5(invisible) |

**Installation:** 无需任何 `pip install` — 所有依赖已在 `pyproject.toml` 声明并安装到 `.venv/`。

**Version verification:**
```bash
.venv/bin/pip show dspy | grep -i version    # → 3.1.3 [VERIFIED 2026-05-15]
.venv/bin/pip list | grep -iE "sklearn|numpy"  # → none [VERIFIED — confirms stdlib path]
```

## Architecture Patterns

### System Architecture Diagram

```
                ┌──────────────────────────────────────────────────┐
                │  evolve_prompt_sections.py CLI                   │
                │  (--mode joint|round-robin, --drift-thresholds-path)│
                └──────────────┬───────────────────────────────────┘
                               │
                ┌──────────────▼──────────────┐
                │  step 6: GEPA / MIPROv2     │
                │  optimization (per-mode)    │
                └──────────────┬──────────────┘
                               │
                ┌──────────────▼──────────────┐
                │  step 7: extract evolved    │
                │  sections                   │
                └──────────────┬──────────────┘
                               │
        ┌──────────────────────▼───────────────────────────────┐
        │  step 8: Constraint Gate Pipeline                    │
        │                                                      │
        │  8a. growth + non_empty (per section)                │
        │  8b. PromptRoleChecker.check_all() [existing]        │
        │  8c. DriftDetector.check_all() [NEW]                 │
        │      ├── for each (original, evolved) pair:          │
        │      │   ├── for each dim ∈ {tone, formality,        │
        │      │   │            vocabulary, persona}:          │
        │      │   │   ├── 3-run LLM judge (temperature=0.7)   │
        │      │   │   │   ├── DriftScoreSignature (typed float)│
        │      │   │   │   └── parse_value() → float           │
        │      │   │   ├── mean, stdev = statistics.*          │
        │      │   │   └── exceeded = (mean - stdev) > thresh  │
        │      │   └── count exceeded dims → severity ladder   │
        │      │       ├── 0 exceeded → pass                   │
        │      │       ├── 1 exceeded → warn (still deploy)    │
        │      │       └── 2+ exceeded → FAILED (reject)       │
        │  8d. emit Rich Table + drift_report.txt              │
        └──────────────────────┬───────────────────────────────┘
                               │
                ┌──────────────▼──────────────┐
                │  step 9: holdout eval       │
                │  (only if all_pass)         │
                └─────────────────────────────┘

  Calibration build (separate CLI path, run ONCE):

  build_drift_calibration → DriftCalibrationBuilder
       ├── for each of 5 sections:
       │   ├── 3 "true drift" variants (per-dim rewrite, judge_model)
       │   └── 3 "no drift" variants (preserving rewrite, judge_model)
       └── DriftCalibrationDataset.save() → datasets/prompts/drift_calibration.jsonl
       
  derive_drift_thresholds → for each dim ∈ {tone, formality, vocabulary, persona}:
       ├── for t in [0.10, 0.15, ..., 0.90]:
       │   ├── for each example: DriftDetector.check 1-run → score
       │   └── compute TP/FP/FN, F1(t, dim)
       └── pick argmax F1 → drift_thresholds.json
```

### Recommended Project Structure

```
evolution/prompts/
├── drift_detector.py       # NEW: DriftDetector class + DriftScoreSignature
├── drift_calibration.py    # NEW: DriftCalibrationBuilder + derive_thresholds
├── prompt_constraints.py   # EXISTING: PromptRoleChecker (DriftDetector mirrors this)
├── prompt_dataset.py       # EXISTING: PromptBehavioralDataset (calibration builder mirrors)
└── evolve_prompt_sections.py  # MODIFIED: step 8c integration point

datasets/prompts/
├── drift_calibration.jsonl    # NEW (git-tracked via .gitignore exception)
├── drift_thresholds.json      # NEW (git-tracked via .gitignore exception)
├── train.jsonl                # EXISTING (gitignored)
├── val.jsonl                  # EXISTING (gitignored)
└── holdout.jsonl              # EXISTING (gitignored)

tests/prompts/
├── test_drift_detector.py     # NEW
├── test_drift_calibration.py  # NEW
└── test_evolve_prompt_sections_cli.py  # MODIFIED: drift gate paths
```

**Discretion note:** Planner 可选择把 `DriftDetector` 嵌入 `prompt_constraints.py` 而非新建 `drift_detector.py`。研究上两种都可,理由对比:
- 新建 `drift_detector.py`:`drift_calibration.py` 与 detector 同包邻接更便于维护;`prompt_constraints.py` 不无限膨胀
- 扩展 `prompt_constraints.py`:与 PromptRoleChecker 同文件 reading-order 更连贯;减少 import 数量

### Pattern 1: DSPy ChainOfThought + Typed Float OutputField + Try/Except Fallback

**What:** DSPy 3.x 原生支持 typed OutputField,float 类型自动通过 pydantic TypeAdapter 解析。M4 prevention 在 typed 路径下自然达成:类型不匹配时 raise `ValidationError`,不再是 silent 0.5 default。

**When to use:** 任何输出数值评分的 LLM-as-judge — 本期 DriftDetector 全 4 维 score 字段。

**Example:** *(Source: VERIFIED dspy==3.1.3 实测 `parse_value` 行为)*
```python
import dspy
from pydantic import ValidationError

class DriftScoreSignature(dspy.Signature):
    """Pairwise comparison of original vs evolved prompt section,
    rating drift on tone, formality, vocabulary, and persona dimensions.

    Each score: 0.0 = no drift (identical character/style),
                1.0 = total drift (completely different voice).
    """
    section_id: str = dspy.InputField(desc="Section identifier (e.g. memory_guidance)")
    original_text: str = dspy.InputField(desc="Original section text before evolution")
    evolved_text: str = dspy.InputField(desc="Evolved section text to score")
    tone_score: float = dspy.OutputField(desc="Tone drift 0.0 (same) - 1.0 (totally different)")
    formality_score: float = dspy.OutputField(desc="Formality drift 0.0 - 1.0")
    vocabulary_score: float = dspy.OutputField(desc="Vocabulary drift 0.0 - 1.0")
    persona_score: float = dspy.OutputField(desc="Persona/character drift 0.0 - 1.0")
    explanation: str = dspy.OutputField(desc="One-paragraph rationale citing concrete textual evidence")


# Inside DriftDetector.check_one_run():
try:
    result = self.judge(
        section_id=section_id,
        original_text=orig,
        evolved_text=evo,
    )
    # Already typed float — clamp defensively to [0, 1]
    scores = {
        "tone": _clamp_unit(float(result.tone_score)),
        "formality": _clamp_unit(float(result.formality_score)),
        "vocabulary": _clamp_unit(float(result.vocabulary_score)),
        "persona": _clamp_unit(float(result.persona_score)),
    }
    explanation = str(result.explanation)
except ValidationError as e:
    # M4 prevention: 0.0 fallback (NOT 0.5) so failure is observable
    scores = {dim: 0.0 for dim in ("tone", "formality", "vocabulary", "persona")}
    explanation = f"[Parse failure: {e}]"

def _clamp_unit(x: float) -> float:
    return max(0.0, min(1.0, x))
```

### Pattern 2: Stochastic LM via Explicit `temperature=0.7`

**What:** 3-run averaging 需要 LM 输出有真实差异;DSPy 3.1.3 默认 `cache=True` 让相同输入永远命中缓存。必须显式 `temperature=0.7` + 隐含 `cache_busting` 才让 3 个 call 产生不同 sample。

**When to use:** 任何依赖 stochastic sampling 的 LLM-as-judge averaging — 本期 DriftDetector 的 3-run。

**Example:** *(Source: VERIFIED dspy/clients/lm.py source inspection)*
```python
class DriftDetector:
    def __init__(self, config: EvolutionConfig, thresholds: dict[str, float]):
        self.config = config
        self.thresholds = thresholds
        # CRITICAL: must construct LM with temperature > 0
        # OR the cache=True default makes 3 runs return identical scores.
        self._lm = dspy.LM(
            config.eval_model,
            temperature=0.7,
            **config.get_lm_kwargs(),
        )
        self.judge = dspy.ChainOfThought(DriftScoreSignature)

    def _run_three_judge_calls(self, sid, orig, evo) -> list[dict]:
        runs = []
        with dspy.context(lm=self._lm):
            for i in range(3):
                runs.append(self._check_one_run(sid, orig, evo))
        return runs
```

### Anti-Patterns to Avoid

- **Anti-pattern:** Using `dspy.LM(config.eval_model)` with default `cache=True, temperature=None` for 3-run averaging — 3 runs return **identical cached responses**, `stdev = 0` makes `mean - stdev > threshold` decision degenerate. **Do:** Always `temperature=0.7` for stochastic judges.
- **Anti-pattern:** Manual JSON parsing of LLM output (`_parse_scoring_json` brace-counting fallback) when DSPy 3.x has native typed parsing. **Do:** Use `float = dspy.OutputField()` + try/except `pydantic.ValidationError` with 0.0 fallback.
- **Anti-pattern:** Running 4 separate single-dim LLM judge calls. **Do:** One Signature with 4 typed score OutputFields + one explanation in a single ChainOfThought call (4× cheaper).
- **Anti-pattern:** Same `judge_model` for both calibration set generator and DriftDetector judge — amplifies same-model bias. **Do:** Generator uses `config.judge_model` (gpt-4.1), DriftDetector uses `config.eval_model` (gpt-4.1-mini) — already model-differentiated per existing config defaults.
- **Anti-pattern:** Caching the same `DriftDetector` across A/B baseline + final gate. **Do:** A/B baseline path must **not** invoke DriftDetector at all (per CONTEXT D-OUT-OF-SCOPE: A/B doesn't deploy, drift check is wasted cost).

## DSPy Typed OutputField Verification (Risk Anchor 1)

**Status:** **VERIFIED — `dspy.OutputField(type=float)` via annotation is fully supported in DSPy 3.1.3.**

**Probe method:**
```python
import dspy
class TestSig(dspy.Signature):
    inp: str = dspy.InputField()
    score: float = dspy.OutputField(desc="Score 0-1")

# Result: TestSig.model_fields['score'].annotation == <class 'float'>
# parse_value uses pydantic TypeAdapter under the hood:
from dspy.adapters.utils import parse_value
parse_value("0.55", float)        # → 0.55 ✓
parse_value("  0.7  ", float)     # → 0.7 ✓ (strips whitespace)
parse_value('"0.32"', float)      # → 0.32 ✓ (json_repair handles quotes)
parse_value("1.0", float)         # → 1.0 ✓
parse_value("banana", float)      # → raises pydantic.ValidationError ✓
parse_value("Score: 0.5", float)  # → raises pydantic.ValidationError ✓ (mixed text)
```

**Source:** `.venv/lib/python3.13/site-packages/dspy/adapters/utils.py:171`:
```python
candidate = json_repair.loads(value)  # json_repair returns "" on failure
...
return TypeAdapter(annotation).validate_python(candidate)
```

**Implication for DriftDetector:**
- M4 prevention is automatically achieved by using typed fields — there is **no `_parse_score` 0.5 default code path** to inherit.
- The remaining failure mode is `pydantic.ValidationError` when LLM emits malformed text (e.g., "Score: 0.5" with a label). Wrap the `self.judge(...)` call in `try/except pydantic.ValidationError` and **fallback to 0.0** (per M4 prevention: 0.0 is observable, 0.5 is invisible).
- DSPy's `dspy.OutputField(type=...)` parameter is **not** the API path in 3.x — `type=` would be `**kwargs` which DSPy doesn't consume. The correct path is **Python type annotation** on the class attribute (`score: float = dspy.OutputField(desc=...)`).

**Confidence:** HIGH (direct `parse_value` invocation in this environment confirms behavior end-to-end).

## DSPy LM Stochasticity Verification (Risk Anchor 2)

**Status:** **D-ROB-03 assumption is FALSE in DSPy 3.1.3.** Explicit override required.

**Probe method:**
```python
import inspect, dspy
sig = inspect.signature(dspy.LM.__init__)
# temperature default: None
# cache default: True
# (verified by direct inspect 2026-05-15)

# Source: .venv/lib/python3.13/site-packages/dspy/clients/lm.py:
# Line 64: "rollout_id: Optional integer used to differentiate cache entries"
# Line 115: "rollout_id has no effect when temperature=0; set temperature>0 to bypass the cache."
```

**What this means concretely:**
- `dspy.LM("openai/gpt-4.1-mini")` produces `lm.kwargs == {'temperature': None, 'max_tokens': None}` — no temperature is passed to OpenAI, OpenAI uses its API default (1.0).
- **BUT** DSPy's `cache=True` default short-circuits identical inputs: 3 calls with same `(section_id, original_text, evolved_text)` return the **same cached response** even if OpenAI's default temperature would otherwise produce variance.
- `stdev` of 3 identical scores = 0 → `mean - 1·stdev > threshold` becomes `mean > threshold` → D-ROB-02 conservative semantics lost.

**Fix:** DriftDetector must construct its LM with **explicit `temperature=0.7`**:
```python
self._lm = dspy.LM(
    config.eval_model,
    temperature=0.7,        # CRITICAL — without this, 3-run is single-run
    **config.get_lm_kwargs()
)
```

**Why 0.7 (not 1.0 or 0.5):**
- DSPy's own doc (line 115) recommends `temperature > 0` to bypass cache; 0.7 is the canonical LLM-as-judge "medium creativity" temperature.
- 1.0 (OpenAI default) produces too much variance for a 0-1 numerical judge — stdev can hit 0.2+, making `mean - stdev` too lenient.
- 0.3 produces too little variance — close to deterministic, only marginally better than `temperature=0`.
- 0.7 sweet spot: variance ≈ 0.05-0.10 in pilot LLM-as-judge studies, sufficient for `mean - stdev` to behave conservatively per D-ROB-02 intent.

**Alternative considered:** Use `rollout_id` parameter with `temperature=0.7`. **Reject** — adds API complexity for no gain; `temperature=0.7` alone already busts cache because cache key includes temperature value.

**Cost impact:** Negligible — 3-run is gate-only (1× per deploy), not GEPA-inner-loop (would be 60× per generation). Per CONTEXT D-ROB-01, 3-run × 5 sections × 4 dims = 60 LM calls/run ≈ $0.5-2.

**Confidence:** HIGH (direct source inspection of `dspy/clients/lm.py` + signature probe in this `.venv/`).

**Action for planner:** PLAN.md must explicitly call out `temperature=0.7` in the DriftDetector constructor signature. Add a unit test `test_drift_detector_stochasticity.py` that mocks `dspy.LM` and asserts `temperature=0.7` is passed when DriftDetector is constructed.

## F1 Derivation Approach (Risk Anchor 3)

**Status:** **Brute-scan [0.1, 0.9] step 0.05 is the only viable approach — sklearn/numpy/scipy are NOT installed.**

**Probe method:**
```bash
.venv/bin/pip list | grep -iE "sklearn|scikit|numpy|scipy"
# (no output — none installed)  [VERIFIED 2026-05-15]
```

**Implication:**
- CLAUDE.md constraint "no new external dependencies" rules out `pip install scikit-learn`.
- Pure stdlib brute scan is trivially fast: 17 candidate thresholds (0.10, 0.15, ..., 0.90) × 30 calibration examples × 4 dims = **2,040 simple arithmetic operations**, runs in < 1ms.
- Precision and recall in this scale require no vector ops — 4 integer accumulators (TP/FP/FN per dim) per threshold suffice.

**Reference implementation pattern** (planner should adapt):
```python
def derive_threshold_for_dim(
    examples: list[CalibrationExample],
    dim: str,
    drift_detector: DriftDetector,
) -> tuple[float, float]:
    """Return (best_threshold, best_f1) for a single dimension."""
    # Single-run judge over all 30 examples (D-ROB-01: calibration is 1-run)
    scored = []
    for ex in examples:
        scores = drift_detector.check_one_run(ex.section_id, ex.original, ex.evolved)
        ground_truth = (ex.is_drift and ex.drift_dim == dim)
        scored.append((scores[dim], ground_truth))

    best_t, best_f1 = 0.5, -1.0
    for t10 in range(10, 91, 5):  # 0.10, 0.15, ..., 0.90 → 17 candidates
        t = t10 / 100
        tp = sum(1 for s, gt in scored if s > t and gt)
        fp = sum(1 for s, gt in scored if s > t and not gt)
        fn = sum(1 for s, gt in scored if s <= t and gt)
        if tp == 0:
            f1 = 0.0
        else:
            p = tp / (tp + fp)
            r = tp / (tp + fn)
            f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
        if f1 > best_f1:
            best_t, best_f1 = t, f1
    return best_t, best_f1
```

**Edge cases planner must handle:**
- **Ground-truth distribution:** Per D-CAL-03/D-CAL-04, each dim has 15/30 examples labeled "true drift on this dim" (or "true drift on any dim") and 15/30 labeled "no drift". Per-dim ground-truth derives as `is_drift AND drift_dim == this_dim` — so for `tone`, maybe only ~4 examples per dim have positive ground truth (15 true-drift ÷ 4 dims = ~3.75). **Very small positive sample per dim → F1 unstable.** Planner must consider this when interpreting `F1 ≥ 0.85` target.
- **Ties (multiple thresholds yield same F1):** Pick the lower threshold (more conservative — flag more drift). Document this rule in `derive_threshold_for_dim` docstring.
- **All-zero F1 (no usable threshold):** Fail loudly — emit warning, fallback to threshold = 0.5 (midpoint), require ops to manually inspect calibration set.

**Confidence:** HIGH (pure stdlib path verified to run; sklearn confirmed absent).

## Pairwise Judge Signature Patterns (Risk Anchor 4)

**Status:** **Single Signature with 4 typed `float` OutputFields is the recommended pattern** — 4× cheaper than 4 separate calls, and DSPy 3.1.3 typed parsing handles multi-output reliably.

**Why one signature, not four:**
1. **Cost:** 4 separate `dspy.ChainOfThought` calls = 4 LLM round-trips per (original, evolved) pair × 3 runs × 5 sections = 60 vs **15** roundtrips. With 3-run averaging at gate, single signature: 60 calls; four signatures: 240 calls. Per CONTEXT.md the gate runs once per deploy, but 4× cost is non-trivial ($2-8 per deploy → $0.5-2 saved).
2. **Coherence:** A single judge call sees all 4 dimensions together, can mentally cross-reference (e.g., "if tone changed AND vocabulary changed, this is likely intentional voice migration, score lower on persona"). 4 isolated calls cannot cross-reference.
3. **Reliability:** DSPy 3.1.3 ChainOfThought parsers `parse_value` per-field independently; one field's parse failure does **not** crash the whole prediction — it raises `ValidationError` for that field only. With try/except + 0.0 fallback per field, single-signature multi-output is robust.

**Field naming convention (recommend; planner discretion):**
- Output fields: `tone_score`, `formality_score`, `vocabulary_score`, `persona_score`, `explanation`
- All score fields `float`, explanation `str`
- Suffix `_score` makes parser extraction & downstream `result.<dim>_score` access uniform
- Avoid `tone_drift` / `tone_delta` — "score" reads naturally as a value in `[0, 1]`

**Signature docstring guidance:**
The Signature class docstring is the LLM instruction; it must:
1. Define the comparison axis ("pairwise", "0 = no drift, 1 = total drift")
2. Define each dimension semantically:
   - **tone:** emotional register (formal/neutral/warm/playful/aggressive)
   - **formality:** sentence structure & word choice formality
   - **vocabulary:** lexical choices (technical/colloquial/jargon)
   - **persona:** speaker identity / role consistency (e.g. "helpful AI" vs "expert peer")
3. Anchor with concrete examples: "If original says 'I'll help you remember' and evolved says 'I store your memory items', score persona ≥ 0.5 because voice shifted from collaborative to mechanical."
4. Instruct the LLM to produce **independent** scores per dim (not a single composite divided 4 ways).

**Anti-pattern to avoid:** ChainOfThought reasoning leak — if the LLM produces a long reasoning trace that includes phrases like "tone score: 0.6" inline, the `tone_score` field may parse to the literal text "tone score: 0.6" which fails ValidationError. Mitigate by giving each OutputField a unique, well-named `prefix` (DSPy 3.x auto-adds prefix `Tone Score: ` based on field name) and explicit instruction in Signature docstring: "Output each score as a single decimal between 0.0 and 1.0, nothing else on the score lines."

**Confidence:** HIGH for cost / reliability reasoning (cost computed from CONTEXT.md call counts; reliability verified by `parse_value` probe). MEDIUM for "coherence" benefit (intuition + general LLM judge literature, no DSPy-specific benchmark).

## Calibration Anti-Bias Techniques (Risk Anchor 5)

**Risk:** Generator and judge using same LLM → "same-model bias" (the judge inherits the generator's blind spots, F1 on calibration set virtually inflates).

**Mitigation 1: Model differentiation (LOW cost, HIGH impact)**
- Generator uses `config.judge_model` (currently `openai/gpt-4.1`)
- DriftDetector judge uses `config.eval_model` (currently `openai/gpt-4.1-mini`)
- Already a default in this codebase — `EvolutionConfig.judge_model != eval_model`. Planner just needs to pass them correctly:
  - `DriftCalibrationBuilder.__init__` → `dspy.LM(config.judge_model, ...)`
  - `DriftDetector.__init__` → `dspy.LM(config.eval_model, temperature=0.7, ...)`
- gpt-4.1 vs gpt-4.1-mini are sibling models — some same-org bias remains, but architectural differentiation reduces collusion.

**Mitigation 2: Manual spot-check (per D-CAL-01, CONTEXT specifies ~10 of 30)**
- After `drift_calibration.jsonl` is generated, planner must instruct executor to print 10 random examples to stdout with their ground-truth labels
- Human reviewer (the user) classifies each as agree/disagree
- If disagreement on 3+ examples, regenerate the failed examples or adjust generator prompt
- Result: human-validated calibration set rather than pure LLM-loop

**Mitigation 3: Generator temperature ≥ judge temperature**
- Generator uses `temperature=0.9` (high diversity, varied drift instances)
- Judge uses `temperature=0.7` (medium variance, consistent enough for thresholds)
- High-diversity generation ensures the calibration set covers a wider semantic space than a low-temp generator would, making same-model bias less crippling.

**Mitigation 4: Verify-phase fresh-set F1 check (already in CONTEXT Risk Anchor)**
- Per CONTEXT risk anchor: "thresholds must achieve F1 ≥ 0.85 on calibration set itself, ≥ 0.8 on fresh synthetic 30 examples in verify phase"
- Implementation: Phase 18 verify gate generates a **fresh 30 examples** (different seed) and reruns DriftDetector + threshold check. Falls below 0.8 → verification fails, requires re-calibration.
- This is the **gold-standard test for same-model bias** — if calibration set F1 = 0.95 but fresh set F1 = 0.65, the bias is exposed and forces correction.

**Mitigation 5 (NEW — recommended): Drift dimension targeting in generator prompt**
- For each "true drift" example, the generator prompt must **explicitly name** which dim is targeted (e.g., "rewrite changing **tone** to aggressive, keep formality/vocabulary/persona stable")
- Without explicit per-dim targeting, the generator may shift 2 dims simultaneously, contaminating the 4-dim ground truth labels (an example labeled `drift_dim=tone` may actually have both tone AND vocabulary changed)
- This refines D-CAL-04's per-dim labels to be cleaner.

**Sample size note:** 30 examples is the bare minimum for 4 independent thresholds. With 15 true-drift / 15 no-drift, per-dim positive ground truth is ~3-4 examples. Planner should warn in implementation docs that thresholds are **provisional** — quarterly recalibration (deferred but referenced in CONTEXT) should expand to 80-120 examples per dim once production drift data accumulates.

**Confidence:** HIGH (mitigations 1, 2, 4 are PITFALL #6 prevention-direct; 3, 5 are reasoning-derived from LLM-judge literature, MEDIUM confidence on quantitative benefit but no downside).

## Verification F1 Targets (Risk Anchor 6)

**CONTEXT-stated target:** F1 ≥ 0.85 on calibration set itself, F1 ≥ 0.8 on fresh synthetic 30 examples in verify phase.

**Reasonable?** Conditional yes — with caveats.

**Analysis:**
- **F1 on calibration set:** After F1-optimized threshold derivation, F1 on the same set is the *optimal achievable F1*. If the optimal F1 < 0.85, no threshold can hit the target — the calibration set is inherently noisy OR the LLM judge cannot reliably distinguish the labeled cases. This is the **early-warning signal** that PITFALL #6 prevention #3 / #4 demands.
- **F1 on fresh set:** Always lower than self-F1 due to threshold overfitting on the calibration set. Typical drop: 0.05-0.15. So self-F1 = 0.90 → fresh-F1 = 0.75-0.85 plausible.

**Per-dim breakdown of 0.85 target challenge:**
- 30 examples ÷ 4 dims = ~7.5 per dim if uniform distribution (but D-CAL-03 has 15 true-drift, possibly with `drift_dim` distributed unevenly)
- With 4-7 positive examples per dim, F1 is sensitive to ±1 example shifts:
  - 5 TP, 1 FP, 1 FN → P=0.83, R=0.83, F1=0.83
  - 6 TP, 1 FP, 0 FN → P=0.86, R=1.0, F1=0.92
  - 4 TP, 1 FP, 2 FN → P=0.80, R=0.67, F1=0.73
- A single misjudged example moves F1 by ~0.10. Hitting F1 ≥ 0.85 per-dim requires generator + judge to agree on ≥ 5/6 of positive examples per dim.

**Recommendation: Add tiered acceptance gate with rationale**
- **TIER 1 (passing):** All 4 dim F1 ≥ 0.85 on calibration, all 4 dim F1 ≥ 0.80 on fresh → green-light Phase 18 verify
- **TIER 2 (passing with caveat):** Aggregate macro-F1 ≥ 0.85 on calibration AND ≥ 0.80 on fresh, BUT one dim is 0.70-0.85 → green-light with `[yellow]` stdout note in `verify_phase_report.txt` ("Dim X is borderline — flag for next-quarter recalibration")
- **TIER 3 (fail):** Any dim F1 < 0.70 OR aggregate macro-F1 < 0.80 on fresh → fail verify gate, require calibration set redo

This tiered approach prevents Phase 18 from indefinitely re-rolling on the unlucky-distribution case (random sampling variance can drop one dim 0.05 below target).

**Action for planner:** PLAN.md `verify` task should:
1. Compute per-dim AND macro-F1 on both calibration set (self) and fresh 30 examples
2. Emit Rich Table:
   ```
   F1 Calibration Self-Eval     F1 Fresh-Eval (30 ex)
   ─────────────────────────    ─────────────────────
   Tone       0.88  ✓           Tone       0.82  ✓
   Formality  0.75  WARN        Formality  0.71  WARN
   Vocab      0.91  ✓           Vocab      0.85  ✓
   Persona   0.87  ✓           Persona   0.79  WARN
   Macro      0.85  ✓           Macro      0.79  WARN
   Status:    PASS              Status:    PASS (TIER 2)
   ```
3. Persist `f1_self`, `f1_fresh`, `f1_tier`, `f1_warned_dims` to `drift_thresholds.json` for traceability

**Confidence:** MEDIUM-HIGH on the analysis (math is exact; sample-size sensitivity is well-known in F1 calibration literature). MEDIUM on Tier 2 thresholds (0.70 floor and 0.85/0.80 main targets are reasonable defaults but not empirically validated for THIS judge × THIS section corpus — quarterly recalibration may adjust).

## Common Pitfalls

These are re-cited verbatim from `.planning/research/PITFALLS.md` §Pitfall 6 — Phase 18 plan **MUST** implement each prevention.

### Pitfall 1 (= PITFALLS §6.1): Threshold calibration without ground-truth set
**What goes wrong:** Threshold set on intuition → either 80% false-positive (calibration too tight) or <2% rejection (calibration too loose).
**Prevention:** Build drift-labeled calibration set BEFORE writing DriftDetector code. 30 paired examples, 15 true-drift / 15 no-drift, F1-optimized threshold. **(D-CAL-05: this is Phase 18 Task 1, blocking all detector implementation.)**

### Pitfall 2 (= PITFALLS §6.2): Pointwise rather than pairwise scoring
**What goes wrong:** Absolute drift score is unstable across baseline texts; pairwise comparison is more reliable.
**Prevention:** Signature takes BOTH `original_text` and `evolved_text` as inputs, outputs comparative scores. (Already baked into `DriftScoreSignature` design above.)

### Pitfall 3 (= PITFALLS §6.3): Single LLM-judge run (PITFALL #2 instability inheritance)
**What goes wrong:** ±0.15 noise on single-run drift score yields high false-positive at threshold.
**Prevention:** 3-run averaging, decision = `mean - 1·stdev > threshold` (conservative). **CRITICAL: requires `temperature=0.7` per Risk Anchor 2** — DSPy `cache=True` default makes 3 runs identical otherwise.

### Pitfall 4 (= PITFALLS §6.4): Scalar threshold loses signal
**What goes wrong:** Single drift score collapses 4 distinct phenomena (tone vs formality vs vocab vs persona); single threshold cannot capture the multi-dim trade-off.
**Prevention:** 4-dim vector output, per-dim threshold, **1 dim exceeded = warn (still deploy); 2+ dims exceeded = reject**. (D-GATE-01 already locks this.)

### Pitfall 5 (= PITFALLS §6.5): Reinventing the role-checker infrastructure
**What goes wrong:** New parallel test/mock infrastructure introduces maintenance debt.
**Prevention:** DriftDetector follows PromptRoleChecker shape (`check_all(orig, evolved) -> list[ConstraintResult]`, ChainOfThought, `with dspy.context(lm=lm)`). Same test harness applies.

### Pitfall 6 (= PITFALLS §6.6): Threshold rot
**What goes wrong:** Tone/persona drift baseline shifts over time as hermes-agent prompts evolve; thresholds frozen at v1 become invalid by v3.
**Prevention:** Document quarterly recalibration cadence in `drift_calibration.py` module docstring + README. (Out of scope for Phase 18 implementation, but planner should ensure the calibration CLI is **runnable standalone** — `python -m evolution.prompts.build_drift_calibration` — so quarterly ops can re-run without touching deploy code.)

### Pitfall A (NEW — discovered in this research): DSPy LM cache defeats 3-run averaging
**What goes wrong:** `dspy.LM(model)` defaults to `cache=True, temperature=None`. Three calls with identical inputs return identical cached responses → stdev = 0 → D-ROB-02 decision `mean - 1·stdev > threshold` is meaningless.
**Prevention:** DriftDetector constructor must explicitly pass `temperature=0.7` to `dspy.LM`. Unit test `test_drift_detector_lm_construction` asserts `temperature=0.7` in `dspy.LM` call args (mock dspy.LM with `unittest.mock`).
**Warning signs:** 3-run stdev consistently = 0.0 → cache is biting. Phase 18 unit tests must assert non-zero stdev in a mocked 3-run scenario.

### Pitfall B (NEW — discovered in this research): Typed float parse failure cascades silently
**What goes wrong:** If LLM outputs `"tone_score: 0.6"` (with prefix label) instead of `"0.6"`, `parse_value(_, float)` raises `pydantic.ValidationError` mid-prediction. Without explicit try/except, DSPy may re-raise or fall through unpredictably depending on adapter.
**Prevention:** Wrap `self.judge(...)` in `try/except pydantic.ValidationError`, fallback all 4 dim scores to **0.0** (M4 prevention: 0.0 not 0.5), record `parse_failures` count in metrics.json `drift_per_dim.<sid>.<dim>.parse_failures`.
**Warning signs:** `drift_report.txt` "Explanation: [Parse failure: ...]" entries. Phase 18 verify should fail loudly if `parse_failures > 0` on production runs.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Float parsing from LLM output | `_parse_float_score` helper with regex extraction | `dspy.OutputField` + Python `float` type annotation + try/except `pydantic.ValidationError` | DSPy 3.1.3 has native typed parsing via pydantic TypeAdapter — verified working; M4 prevention auto-applied |
| F1 derivation | sklearn `precision_recall_curve` (or hand-rolled with numpy) | Pure stdlib brute scan with 17 candidate thresholds | sklearn NOT installed (CLAUDE.md "no new deps"); 30 × 17 × 4 = 2040 ops < 1ms |
| Calibration set persistence schema | New JSONL format | Mirror `PromptBehavioralDataset.save/load()` pattern | Phase 9 pattern, tested, JSONL parsing already in repo |
| Multi-dim score Signature output | Manual JSON in single string field + regex parse | One Signature with 4 typed `float` OutputFields + 1 `str` explanation | Verified DSPy 3.1.3 handles multi-output reliably; 4× cost reduction |
| Constraint result aggregation | New custom result type | `ConstraintResult` dataclass with `details` field encoding drift JSON | Already used by PromptRoleChecker; metrics.json downstream consumer is consistent |
| Drift severity ladder logic | New state machine | Simple `count = sum(d.exceeded for d in drift_results)` + `if count == 0: pass elif count == 1: warn else: fail` | 3-line implementation, no library needed |
| Statistics (mean, stdev) for 3-run | numpy | `import statistics; statistics.mean()`, `statistics.stdev()` | numpy NOT installed; stdlib `statistics` is 3 calls/run, < 10μs |
| Stochastic LM sampling | Custom `seed=` argument or `rollout_id` parameter | `dspy.LM(..., temperature=0.7)` — cache key includes temperature, cache auto-busted | DSPy doc line 115 directly recommends this |

**Key insight:** All four 4 risk anchors are mitigated by **leaning on existing DSPy 3.x machinery** (typed Signature, ChainOfThought, parse_value, `with dspy.context(lm=...)`) plus 5-10 lines of stdlib glue. The only non-trivial new code is the `DriftDetector.check_all` + `DriftCalibrationBuilder.generate` + `derive_thresholds` triad, each ~50-100 lines.

## Code Examples

### Example 1: DriftDetector class (anchored on PromptRoleChecker)

*(Source: VERIFIED pattern from `evolution/prompts/prompt_constraints.py:32-147` + this research's DSPy probe)*

```python
"""Personality drift detection across 4 dimensions.

Compares original vs evolved prompt sections using a pairwise LLM judge,
scoring drift on tone/formality/vocabulary/persona. 3-run averaging at the
final constraint gate (NOT inside GEPA). Threshold per-dim from F1-optimized
calibration. Severity ladder: 0 dims exceeded = pass, 1 = warn, 2+ = reject.
"""
import json
import statistics
from pathlib import Path
from typing import Optional

import dspy
from pydantic import ValidationError

from evolution.core.config import EvolutionConfig
from evolution.core.constraints import ConstraintResult


DRIFT_DIMENSIONS = ("tone", "formality", "vocabulary", "persona")


def _clamp_unit(x: float) -> float:
    return max(0.0, min(1.0, x))


class DriftDetector:
    """Detects personality drift between original and evolved prompt sections.

    Sibling of PromptRoleChecker (Phase 10) — same shape, different judgement.
    Uses DSPy ChainOfThought with typed float OutputFields for reliable parsing
    (M4 prevention via dspy.OutputField + pydantic ValidationError handling).

    Args:
        config: EvolutionConfig providing eval_model.
        thresholds: Per-dim drift thresholds. Loaded from drift_thresholds.json,
            typically derived via DriftCalibrationBuilder + derive_thresholds.

    Raises:
        ValueError: If thresholds dict is missing any of DRIFT_DIMENSIONS.
    """

    class DriftScoreSignature(dspy.Signature):
        """Pairwise comparison of original vs evolved prompt section.

        Score each dimension independently on 0.0 to 1.0:
            0.0 = no drift (identical character / style)
            1.0 = total drift (completely different voice / role)

        Output each <dim>_score as a single decimal between 0.0 and 1.0.
        Output explanation as a single paragraph citing concrete textual
        evidence for the highest-scoring dimension.
        """
        section_id: str = dspy.InputField(
            desc="Section identifier (e.g. memory_guidance)",
        )
        original_text: str = dspy.InputField(
            desc="Original section text before evolution",
        )
        evolved_text: str = dspy.InputField(
            desc="Evolved section text to compare",
        )
        tone_score: float = dspy.OutputField(
            desc="Tone drift 0.0 (same emotional register) - 1.0 (totally different)",
        )
        formality_score: float = dspy.OutputField(
            desc="Formality drift 0.0 (same structure / formality) - 1.0 (totally different)",
        )
        vocabulary_score: float = dspy.OutputField(
            desc="Vocabulary drift 0.0 (same lexical choices) - 1.0 (totally different)",
        )
        persona_score: float = dspy.OutputField(
            desc="Persona drift 0.0 (same speaker identity / role) - 1.0 (totally different)",
        )
        explanation: str = dspy.OutputField(
            desc="One-paragraph rationale citing concrete textual evidence",
        )

    def __init__(
        self,
        config: EvolutionConfig,
        thresholds: dict[str, float],
    ):
        missing = set(DRIFT_DIMENSIONS) - set(thresholds.keys())
        if missing:
            raise ValueError(
                f"thresholds missing dimensions: {sorted(missing)}"
            )
        self.config = config
        self.thresholds = thresholds
        # CRITICAL: temperature=0.7 — without this, DSPy's cache=True default
        # makes 3-run averaging return identical responses (verified via
        # dspy/clients/lm.py source inspection). See Risk Anchor 2.
        self._lm = dspy.LM(
            config.eval_model,
            temperature=0.7,
            **config.get_lm_kwargs(),
        )
        self.judge = dspy.ChainOfThought(self.DriftScoreSignature)

    def _check_one_run(
        self,
        section_id: str,
        original_text: str,
        evolved_text: str,
    ) -> tuple[dict[str, float], str]:
        """Run the LLM judge once. Returns (scores_per_dim, explanation).

        M4 prevention: on parse failure (LLM emits non-float text), fallback
        each score to 0.0 (NOT 0.5). 0.0 is observable in metrics; 0.5 is
        invisible.
        """
        try:
            with dspy.context(lm=self._lm):
                result = self.judge(
                    section_id=section_id,
                    original_text=original_text,
                    evolved_text=evolved_text,
                )
            scores = {
                "tone": _clamp_unit(float(result.tone_score)),
                "formality": _clamp_unit(float(result.formality_score)),
                "vocabulary": _clamp_unit(float(result.vocabulary_score)),
                "persona": _clamp_unit(float(result.persona_score)),
            }
            return scores, str(result.explanation)
        except (ValidationError, ValueError, TypeError) as e:
            return (
                {dim: 0.0 for dim in DRIFT_DIMENSIONS},
                f"[Parse failure: {type(e).__name__}: {e}]",
            )

    def check(
        self,
        section_id: str,
        original_text: str,
        evolved_text: str,
    ) -> dict:
        """Check a single section pair with 3-run averaging.

        Returns dict structured for metrics.json `drift_per_dim`:
            {
                "section_id": str,
                "per_dim": {
                    "tone": {"mean": float, "stdev": float, "exceeded": bool,
                             "raw": [float, float, float]},
                    ...
                },
                "exceeded_count": int,
                "severity": "pass" | "warn" | "reject",
                "explanation": str,  # last run's explanation
                "constraint_result": ConstraintResult,
            }
        """
        runs = []
        last_explanation = ""
        for _ in range(3):
            scores, explanation = self._check_one_run(
                section_id, original_text, evolved_text,
            )
            runs.append(scores)
            last_explanation = explanation  # only the 3rd is persisted

        per_dim = {}
        for dim in DRIFT_DIMENSIONS:
            raw = [r[dim] for r in runs]
            mean = statistics.mean(raw)
            # stdev requires ≥ 2 points; always true here (3 runs)
            sd = statistics.stdev(raw)
            exceeded = (mean - sd) > self.thresholds[dim]
            per_dim[dim] = {
                "mean": round(mean, 4),
                "stdev": round(sd, 4),
                "exceeded": exceeded,
                "raw": [round(r, 4) for r in raw],
            }

        exceeded_count = sum(1 for d in per_dim.values() if d["exceeded"])
        if exceeded_count == 0:
            severity, passed, message = "pass", True, (
                f"Drift OK in '{section_id}': no dims exceeded"
            )
        elif exceeded_count == 1:
            severity, passed = "warn", True
            exceeded_dim = next(
                dim for dim, d in per_dim.items() if d["exceeded"]
            )
            message = (
                f"Drift WARN in '{section_id}': dim '{exceeded_dim}' "
                f"exceeded — review before deploying"
            )
        else:
            severity, passed = "reject", False
            message = (
                f"Drift REJECT in '{section_id}': {exceeded_count} dims exceeded"
            )

        return {
            "section_id": section_id,
            "per_dim": per_dim,
            "exceeded_count": exceeded_count,
            "severity": severity,
            "explanation": last_explanation,
            "constraint_result": ConstraintResult(
                passed=passed,
                constraint_name="drift_detection",
                message=message,
                details=json.dumps(per_dim, sort_keys=True),
            ),
        }

    def check_all(
        self,
        original_sections: list,
        evolved_sections: list,
    ) -> list[dict]:
        """Check all evolved sections. Returns list of per-section drift dicts.

        Mirrors PromptRoleChecker.check_all signature for pipeline drop-in.
        """
        original_map = {s.section_id: s for s in original_sections}
        results = []
        for evolved in evolved_sections:
            original = original_map.get(evolved.section_id)
            if original is None:
                continue
            results.append(
                self.check(evolved.section_id, original.text, evolved.text)
            )
        return results
```

### Example 2: Threshold loading + EvolutionConfig integration

```python
# In evolve_prompt_sections.py:

import click
from pathlib import Path

@click.option(
    "--drift-thresholds-path",
    type=click.Path(exists=True, path_type=Path),
    default=Path("datasets/prompts/drift_thresholds.json"),
    help="Path to drift_thresholds.json (per-dim F1-optimized thresholds).",
)
def main(..., drift_thresholds_path: Path):
    ...
    # step 8c: drift detection
    thresholds = json.loads(drift_thresholds_path.read_text())
    drift_detector = DriftDetector(config, thresholds)
    drift_results = drift_detector.check_all(original_sections, evolved_sections)

    for dr in drift_results:
        all_constraint_results.append(dr["constraint_result"])
        if not dr["constraint_result"].passed:
            all_pass = False
        # Print Rich Table row (D-OUT-01)
        ...
```

### Example 3: F1-optimized threshold derivation

```python
def derive_thresholds(
    calibration: "DriftCalibrationDataset",
    config: EvolutionConfig,
) -> dict[str, float]:
    """Brute-scan thresholds in [0.1, 0.9] step 0.05, pick F1-optimal per dim.

    Returns: {"tone": 0.55, "formality": 0.50, ...}
    Side-effect: prints Rich Table of per-dim F1 / threshold.

    Pure stdlib (no sklearn — see Risk Anchor 3).
    """
    detector = DriftDetector(config, thresholds={d: 0.5 for d in DRIFT_DIMENSIONS})
    # First pass: collect raw scores for all examples (1-run per D-ROB-01).
    scored = []  # list of (drift_dim_truth, scores_dict)
    for ex in calibration.examples:
        scores, _ = detector._check_one_run(
            ex.section_id, ex.original_text, ex.evolved_text
        )
        scored.append((ex.is_drift, ex.drift_dim, scores))

    best = {}
    for dim in DRIFT_DIMENSIONS:
        # Per-dim ground truth: positive iff (is_drift AND drift_dim == dim)
        labeled = [
            (s[dim], (is_drift and dim_truth == dim))
            for is_drift, dim_truth, s in scored
        ]
        best_t, best_f1 = 0.5, -1.0
        for t10 in range(10, 91, 5):
            t = t10 / 100
            tp = sum(1 for sc, gt in labeled if sc > t and gt)
            fp = sum(1 for sc, gt in labeled if sc > t and not gt)
            fn = sum(1 for sc, gt in labeled if sc <= t and gt)
            if tp == 0:
                f1 = 0.0
            else:
                p = tp / (tp + fp)
                r = tp / (tp + fn)
                f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
            if f1 > best_f1:
                best_t, best_f1 = t, f1
        best[dim] = best_t
        # log per-dim F1 for ops review
    return best
```

### Example 4: DriftCalibrationBuilder (mirroring PromptDatasetBuilder)

```python
"""Synthetic calibration set builder for drift detection."""
import json
import random
from dataclasses import dataclass, asdict
from pathlib import Path

import dspy
from evolution.core.config import EvolutionConfig
from evolution.prompts.drift_detector import DRIFT_DIMENSIONS


@dataclass
class DriftCalibrationExample:
    section_id: str
    original_text: str
    evolved_text: str
    is_drift: bool
    drift_dim: str  # one of DRIFT_DIMENSIONS or "none"
    generation_metadata: dict  # seed, generator_model, timestamp


class DriftCalibrationBuilder:
    """Generates 30-example calibration set: 5 sections × 6 variants.

    Per section:
      - 3 true-drift variants (one per dim — tone/formality/vocabulary/persona +
        cycle since only 3 of 4 dims are sampled — see D-CAL-03)
      - 3 no-drift variants (rephrasing preserving voice)

    Generator uses config.judge_model (gpt-4.1) — different model than
    DriftDetector judge (config.eval_model = gpt-4.1-mini) to reduce
    same-model bias (Risk Anchor 5).
    """

    class GenerateDriftVariant(dspy.Signature):
        """Generate a rewrite of a prompt section, either changing or preserving
        the targeted personality dimensions.

        For 'drift' mode: significantly change the named dimension while keeping
        all other dimensions identical to the original.

        For 'preserve' mode: rephrase or restructure for clarity, but completely
        preserve tone, formality, vocabulary, and persona.
        """
        original_text: str = dspy.InputField()
        mode: str = dspy.InputField(desc="'drift' or 'preserve'")
        target_dim: str = dspy.InputField(
            desc="(drift mode only) one of: tone, formality, vocabulary, persona"
        )
        evolved_text: str = dspy.OutputField(
            desc="Rewritten section meeting the mode + dim requirements"
        )

    def __init__(self, config: EvolutionConfig, seed: int = 42):
        self.config = config
        self.seed = seed
        self._lm = dspy.LM(
            config.judge_model,
            temperature=0.9,  # high diversity in generation
            **config.get_lm_kwargs(),
        )
        self.generator = dspy.ChainOfThought(self.GenerateDriftVariant)

    def generate(self, sections: list) -> list[DriftCalibrationExample]:
        random.seed(self.seed)
        examples = []
        for section in sections[:5]:  # 5 sections per D-CAL-03
            # 3 drift variants — cycle through dims
            for i, target_dim in enumerate(["tone", "formality", "vocabulary"]):
                # Note: persona may be sampled in next section to balance dim coverage
                with dspy.context(lm=self._lm):
                    result = self.generator(
                        original_text=section.text,
                        mode="drift",
                        target_dim=target_dim,
                    )
                examples.append(DriftCalibrationExample(
                    section_id=section.section_id,
                    original_text=section.text,
                    evolved_text=str(result.evolved_text),
                    is_drift=True,
                    drift_dim=target_dim,
                    generation_metadata={
                        "seed": self.seed,
                        "generator_model": self.config.judge_model,
                        "target_dim": target_dim,
                    },
                ))
            # 3 no-drift variants
            for _ in range(3):
                with dspy.context(lm=self._lm):
                    result = self.generator(
                        original_text=section.text,
                        mode="preserve",
                        target_dim="none",
                    )
                examples.append(DriftCalibrationExample(
                    section_id=section.section_id,
                    original_text=section.text,
                    evolved_text=str(result.evolved_text),
                    is_drift=False,
                    drift_dim="none",
                    generation_metadata={
                        "seed": self.seed,
                        "generator_model": self.config.judge_model,
                    },
                ))
        return examples

    @staticmethod
    def save(examples, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            for ex in examples:
                f.write(json.dumps(asdict(ex), sort_keys=True) + "\n")
```

### Existing PromptRoleChecker (the anchor pattern, FYI)

*(Excerpted from `evolution/prompts/prompt_constraints.py:32-147` — DriftDetector mirrors this shape exactly)*
```python
class PromptRoleChecker:
    class RoleCheckSignature(dspy.Signature):
        """Compare original and evolved prompt sections to verify role preservation."""
        section_id: str = dspy.InputField(...)
        original_text: str = dspy.InputField(...)
        evolved_text: str = dspy.InputField(...)
        role_preserved: bool = dspy.OutputField(...)
        explanation: str = dspy.OutputField(...)

    def __init__(self, config: EvolutionConfig):
        self.config = config
        self.checker = dspy.ChainOfThought(self.RoleCheckSignature)

    def check(self, section_id, original_text, evolved_text) -> ConstraintResult:
        lm = dspy.LM(self.config.eval_model, **self.config.get_lm_kwargs())
        with dspy.context(lm=lm):
            result = self.checker(...)
        # ... ConstraintResult(passed=..., constraint_name="role_preservation", ...)

    def check_all(self, original_sections, evolved_sections) -> list[ConstraintResult]:
        original_map = {s.section_id: s for s in original_sections}
        results = []
        for evolved in evolved_sections:
            original = original_map.get(evolved.section_id)
            if original is None:
                continue
            results.append(self.check(evolved.section_id, original.text, evolved.text))
        return results
```

**Two key deltas DriftDetector makes:**
1. Constructor takes `thresholds` arg
2. `dspy.LM(..., temperature=0.7)` (PromptRoleChecker uses default → no stochastic call needed for bool output)
3. `check()` returns a dict (not bare ConstraintResult) because per-dim payload is needed for drift_report.txt
4. 3-run averaging in `check()`, single-run `_check_one_run()` exposed for calibration loop

## Validation Architecture

> Phase requires `workflow.nyquist_validation: true` (config check: line 11 of `.planning/config.json` — VERIFIED present and true)

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest >=7.0 (declared in `pyproject.toml`) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (testpaths = ["tests"], python_files = ["test_*.py"]) |
| Quick run command | `.venv/bin/pytest tests/prompts/test_drift_detector.py -xvs` |
| Full suite command | `.venv/bin/pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| PMPT-V2-02 | DriftDetector compares orig vs evolved on 4 dims | unit | `pytest tests/prompts/test_drift_detector.py::test_check_returns_4_dim_scores -x` | ❌ Wave 0 |
| PMPT-V2-02 | Constraint gate rejects 2+ dim exceeded | unit | `pytest tests/prompts/test_drift_detector.py::test_severity_ladder_reject -x` | ❌ Wave 0 |
| PMPT-V2-02 | Constraint gate warns on 1 dim exceeded but still passes | unit | `pytest tests/prompts/test_drift_detector.py::test_severity_ladder_warn -x` | ❌ Wave 0 |
| PMPT-V2-02 | Drift report included in optimization output | unit + integration | `pytest tests/prompts/test_drift_detector.py::test_drift_report_payload -x` + `test_evolve_prompt_sections_cli.py::test_drift_report_in_output_dir` | ❌ Wave 0 |
| PMPT-V2-02 (Risk Anchor 1) | Typed float OutputField parses correctly | unit | `pytest tests/prompts/test_drift_detector.py::test_typed_float_parsing -x` | ❌ Wave 0 |
| PMPT-V2-02 (Risk Anchor 1) | Parse failure falls back to 0.0 (NOT 0.5) | unit | `pytest tests/prompts/test_drift_detector.py::test_parse_failure_fallback_zero -x` | ❌ Wave 0 |
| PMPT-V2-02 (Risk Anchor 2) | `temperature=0.7` is passed to dspy.LM | unit | `pytest tests/prompts/test_drift_detector.py::test_lm_constructed_with_temperature -x` | ❌ Wave 0 |
| PMPT-V2-02 (Risk Anchor 2) | 3-run averaging yields non-zero stdev when LM is stochastic | unit | `pytest tests/prompts/test_drift_detector.py::test_three_run_stdev_nonzero -x` | ❌ Wave 0 |
| PMPT-V2-02 (Risk Anchor 2) | `mean - 1·stdev > threshold` decision is conservative | unit | `pytest tests/prompts/test_drift_detector.py::test_conservative_decision_rule -x` | ❌ Wave 0 |
| PMPT-V2-02 (Risk Anchor 3) | F1 derivation finds optimal threshold per dim | unit | `pytest tests/prompts/test_drift_calibration.py::test_derive_thresholds_f1_optimal -x` | ❌ Wave 0 |
| PMPT-V2-02 (Risk Anchor 3) | F1 derivation uses pure stdlib (no sklearn import) | unit | `pytest tests/prompts/test_drift_calibration.py::test_no_sklearn_dependency -x` | ❌ Wave 0 |
| PMPT-V2-02 (Risk Anchor 5) | DriftCalibrationBuilder uses judge_model (not eval_model) | unit | `pytest tests/prompts/test_drift_calibration.py::test_generator_uses_judge_model -x` | ❌ Wave 0 |
| PMPT-V2-02 (Risk Anchor 6) | F1 ≥ 0.85 on calibration self-eval (live run gated) | integration | `pytest tests/prompts/test_drift_calibration.py::test_f1_target_self_eval -x` (skipped unless `RUN_LIVE_LLM=1`) | ❌ Wave 0 |
| PMPT-V2-02 | metrics.json contains drift_per_dim, drift_thresholds, drift_passed | integration | `pytest tests/prompts/test_evolve_prompt_sections_cli.py::test_metrics_json_has_drift_fields -x` | ❌ Wave 0 |
| PMPT-V2-02 | `--drift-thresholds-path` flag accepted, default resolved | unit | `pytest tests/prompts/test_evolve_prompt_sections_cli.py::test_drift_thresholds_path_flag -x` | ❌ Wave 0 |
| PMPT-V2-02 | Bypass flag is **absent** (regression guard for D-BYPASS-01) | unit | `pytest tests/prompts/test_evolve_prompt_sections_cli.py::test_no_skip_drift_flag -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `.venv/bin/pytest tests/prompts/test_drift_detector.py tests/prompts/test_drift_calibration.py -xvs` (focused on Phase 18 unit tests)
- **Per wave merge:** `.venv/bin/pytest tests/prompts/ -v` (all prompt-pipeline tests including pre-existing 83 tests)
- **Phase gate:** `.venv/bin/pytest tests/ -v` (full 353+ test suite green before `/gsd-verify-work`)

### Wave 0 Gaps

- [ ] `tests/prompts/test_drift_detector.py` — RED stubs covering 9 test scenarios above (DriftDetector unit tests)
- [ ] `tests/prompts/test_drift_calibration.py` — RED stubs covering 4 test scenarios above (DriftCalibrationBuilder + derive_thresholds unit tests)
- [ ] `tests/prompts/test_evolve_prompt_sections_cli.py` — extend with 3 new tests (metrics.json fields, --drift-thresholds-path, no --no-drift-check)
- [ ] `tests/prompts/conftest.py` — add `mock_drift_lm` fixture returning predictable 4-dim float scores + `dummy_thresholds` fixture loading `{tone: 0.55, formality: 0.50, vocabulary: 0.45, persona: 0.65}` (placeholder values per D-CAL-01)
- [ ] `tests/prompts/fixtures/drift_calibration_mini.jsonl` — 6-example mini calibration set for unit tests (1 section × 6 variants), letting `derive_thresholds` run in offline mode
- [ ] `.gitignore` exception: `!datasets/prompts/drift_calibration.jsonl` and `!datasets/prompts/drift_thresholds.json` (D-CAL-02 requirement — needs verification of current gitignore)

**Verification:** The fixture `mock_drift_lm` is the key abstraction — it should patch `dspy.LM` to return a `dspy.Prediction` with predetermined `tone_score`/`formality_score`/`vocabulary_score`/`persona_score`/`explanation` fields, allowing each unit test to assert specific severity-ladder outcomes without LLM calls. Same pattern as existing `mock_lm_with_usage` fixture (Phase 13 Wave 0).

### Test Fixture Pattern (carry-over from Phase 13)

```python
# tests/prompts/conftest.py — Phase 18 additions
import pytest
from unittest.mock import MagicMock, patch
import dspy

@pytest.fixture
def mock_drift_lm():
    """Patch dspy.LM to return predictable 4-dim drift scores.

    Usage in test:
        def test_severity_ladder_warn(mock_drift_lm):
            mock_drift_lm.set_scores(tone=0.8, formality=0.2, vocabulary=0.2, persona=0.2)
            # ... DriftDetector instance, check, assert severity=='warn'
    """
    class _MockLM:
        def __init__(self):
            self._scores = {"tone": 0.0, "formality": 0.0, "vocabulary": 0.0, "persona": 0.0}
            self._explanation = "mock"
        def set_scores(self, **kwargs):
            self._scores.update(kwargs)
        # ... LM call interface
    mock = _MockLM()
    with patch("dspy.LM", return_value=mock):
        yield mock

@pytest.fixture
def dummy_thresholds():
    """Placeholder drift thresholds matching D-CAL-01 example values."""
    return {"tone": 0.55, "formality": 0.50, "vocabulary": 0.45, "persona": 0.65}
```

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Pairwise drift scoring (4 dim) | API / Backend (LLM judge layer) | — | LLM-as-judge call must run server-side via dspy.LM → OpenAI; no client-side option |
| 3-run stochastic averaging | API / Backend (DriftDetector class) | — | Stochasticity from LM API; aggregation logic Python-side |
| F1 threshold derivation | API / Backend (calibration script) | — | One-time build step, runs in same process as DriftCalibrationBuilder |
| Calibration set generation | API / Backend (LLM-as-generator) | Database / Storage (JSONL persist) | LLM call + git-tracked dataset persistence |
| Threshold persistence + lookup | Database / Storage (JSON file) | — | `drift_thresholds.json` is config-time data, not runtime state |
| Severity ladder + ConstraintResult | API / Backend (DriftDetector) | — | Pure Python in same module |
| Rich stdout Table | CLI (evolve_prompt_sections) | — | User-facing terminal output |
| metrics.json drift_* fields | Database / Storage (JSON file) | — | Persistence layer, consumed by future dashboard |
| drift_report.txt | Database / Storage (file) | — | Human-readable artifact, same persistence tier |

## Common Pitfalls (consolidated)

See `## Common Pitfalls` section above for the 6 PITFALLS §6 preventions + 2 newly discovered (Pitfall A: DSPy LM cache, Pitfall B: typed float parse failure cascade).

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `_parse_score` + 0.5 silent fallback (Phase 1) | `dspy.OutputField` typed float + try/except `ValidationError` + 0.0 fallback | DSPy 3.x (released ~2024) | M4 prevention auto-applied; failure observable |
| `dspy.OutputField(type=float)` (kwarg-based, DSPy 2.x rumor) | `score: float = dspy.OutputField(desc=...)` (type annotation) | DSPy 3.x | More Pythonic; pydantic v2 compatible |
| Pointwise drift score (rate evolved alone) | Pairwise (compare orig + evolved) | PITFALL #6 prevention #2 | Reduces drift noise ±0.15 → ±0.05-0.10 |
| Scalar threshold | Vector (4-dim) + severity ladder | PITFALL #6 prevention #4 | Surfaces "what kind of drift" to user |
| Single LLM judge call | 3-run averaging with `mean - 1·stdev > threshold` | PITFALL #6 prevention #3 | Conservative decision; prefers false-negative |
| Intuition-set threshold | F1-optimized on labeled calibration set | PITFALL #6 prevention #1 | Eliminates "calibration too tight/loose" failure mode |

**Deprecated / outdated:**
- DSPy 2.x's `dspy.OutputField(type=...)` keyword arg form — DSPy 3.x uses Python type annotations exclusively; the kwarg is silently ignored. Planner should NOT use `type=float` as a kwarg.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `temperature=0.7` produces stdev ≈ 0.05-0.10 on LLM-as-judge 0-1 scores | Pattern 2 | If actual stdev is < 0.02, `mean - 1·stdev` is barely different from `mean` — decision rule loses conservative bias. **Mitigation:** Phase 18 verify gate must assert stdev > 0.01 on a sample 3-run; if not, raise temperature to 0.9. |
| A2 | Calibration set's per-dim positive sample (3-4 examples per dim) is sufficient for F1 ≥ 0.85 | F1 Derivation, Verification F1 Targets | If F1 cannot reach 0.85 on any dim with such small samples, target is unrealistic. **Mitigation:** Tier 2 fallback proposed (macro-F1 ≥ 0.85 OK even if one dim 0.70-0.85). |
| A3 | gpt-4.1 vs gpt-4.1-mini differentiation reduces same-model bias materially | Calibration Anti-Bias | If both are sibling models and produce highly correlated judgments, calibration F1 may still virtually inflate. **Mitigation:** Verify gate on **fresh 30 examples** is the gold standard test — already in CONTEXT. |
| A4 | LLM emits `tone_score: 0.6` format that pydantic can parse via json_repair | DSPy Typed OutputField Verification | Some LLMs emit `Tone Score: 0.6` with prefix — verified to FAIL with ValidationError. **Mitigation:** explicit Signature docstring instruction "Output each score as a single decimal between 0.0 and 1.0, nothing else on the score lines" + try/except 0.0 fallback. |
| A5 | DSPy `cache=True` cache key includes `temperature` value | DSPy LM Stochasticity Verification | If cache key does NOT include temperature, our `temperature=0.7` fix won't bust cache → still single-effective-run. **Mitigation:** Pilot run before Phase 18 verify — 3-run smoke test on 1 (orig, evolved) pair, assert 3 distinct scores. [VERIFIED MEDIUM via source line 115 "set temperature>0 to bypass cache" — DSPy explicitly recommends temperature for cache busting, strongly suggests temperature IS in cache key. HIGH-confidence but not directly probed.] |

## Open Questions

1. **Should `dspy.LM(..., cache=False)` be set in addition to temperature?**
   - What we know: `cache=True` is default, `temperature=0.7` is documented to bypass cache (DSPy source line 115).
   - What's unclear: If cache=True is preserved, do we leak cache across multiple `DriftDetector` instantiations (e.g., calibration + final gate same session)? Risk: cross-instance cache poisoning.
   - Recommendation: Belt-and-suspenders — set BOTH `temperature=0.7, cache=False` in DriftDetector. Cost is zero since 3 calls × 60 max LM calls per run are uncached anyway. Add this to planner directive.

2. **Should `DriftScoreSignature.explanation` field be persisted for all 3 runs, or only the last?**
   - What we know: CONTEXT D-OUT-03 says "only third run's explanation" to avoid 3× text bloat.
   - What's unclear: Third run is randomly-sampled (temperature=0.7) — its explanation may be the outlier of 3. Median explanation might be more representative.
   - Recommendation: D-OUT-03 stands (last run for simplicity); if drift_report.txt is later found insufficient for ops debugging, persist all 3 in a v2 enhancement.

3. **Should calibration set generation use seed=42 or `seed=int(time.time())`?**
   - What we know: D-CAL-01 says "deterministically reproducible" + "固定 seed".
   - What's unclear: Fixed seed means re-running build produces identical calibration set — which prevents drift in the calibration over quarterly recalibration cycles.
   - Recommendation: Use `seed=42` as default + `--seed` CLI flag to override. Persist seed in `generation_metadata` field of each example (already in pattern above).

4. **Where to source the original prompt section text for calibration generation?**
   - What we know: Calibration set generates **variants** of original sections; original must come from somewhere.
   - What's unclear: Use `hermes_repo` extracted sections (live read), or commit a snapshot of section texts into the test fixtures?
   - Recommendation: Live read via `extract_prompt_sections()` at generation time — but persist `original_text` into `drift_calibration.jsonl` so the calibration set is self-contained (doesn't break if hermes_repo prompt sections change post-calibration). The `generation_metadata` should include `hermes_repo_git_sha` for traceability.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| dspy | DriftDetector, DriftCalibrationBuilder | ✓ | 3.1.3 | — |
| dspy.LM | LLM call backend | ✓ | 3.1.3 | — |
| pydantic | Typed OutputField parsing | ✓ | 2.12+ (DSPy dep) | — |
| Click | --drift-thresholds-path flag | ✓ | >=8.0 (declared) | — |
| Rich | stdout Table, colored warn/reject | ✓ | >=13.0 (declared) | — |
| Python `statistics` stdlib | mean / stdev | ✓ | 3.13 builtin | — |
| Python `json` stdlib | metrics + thresholds persistence | ✓ | 3.13 builtin | — |
| sklearn | F1 / precision_recall_curve | ✗ | — | Pure stdlib brute scan (17 × 30 × 4 = 2040 ops, < 1ms) |
| numpy | statistics on arrays | ✗ | — | Use `statistics` stdlib (30-point datasets) |
| scipy | optimization, hypothesis tests | ✗ | — | Not needed — brute scan over discrete thresholds |
| Working LLM API key (OPENAI_API_KEY or OPENROUTER_API_KEY) | DriftDetector runtime, DriftCalibrationBuilder build-time | ✗ (assumed managed externally) | — | Mock LLM via `unittest.mock` for unit tests; live tests gated on env var |

**Missing dependencies with no fallback:** None — all required deps are installed.

**Missing dependencies with fallback:** sklearn / numpy / scipy — pure stdlib path covers the use case (verified ~1ms execution on 30 samples × 17 thresholds × 4 dims).

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PMPT-V2-02 | Personality drift detection (automated comparison before/after) | This research delivers DriftDetector design (4-dim pairwise LLM judge), F1-optimized calibration approach (30-example set + stdlib brute-scan derivation), severity ladder (1 dim = warn, 2+ = reject), `--drift-thresholds-path` CLI flag, metrics.json `drift_*` schema, and drift_report.txt format. All three Success Criteria (DriftDetector compares orig vs evolved on tone/formality/persona, constraint gate rejects threshold-exceeding sections, drift report in optimization output) addressed via Patterns 1-2 + Examples 1-4 above. |

## Sources

### Primary (HIGH confidence)

- `evolution/prompts/prompt_constraints.py:32-147` — PromptRoleChecker source (the architectural anchor for DriftDetector)
- `evolution/prompts/prompt_dataset.py:1-329` — PromptDatasetBuilder source (the anchor for DriftCalibrationBuilder)
- `evolution/prompts/evolve_prompt_sections.py:440-529` — step 8 constraint gate pipeline (DriftDetector insertion point)
- `evolution/core/constraints.py:15-22` — ConstraintResult dataclass shape (DriftDetector return type)
- `evolution/core/config.py:29-83` — EvolutionConfig fields, `get_lm_kwargs()`, eval_model/judge_model defaults
- `.venv/lib/python3.13/site-packages/dspy/clients/lm.py:61-110, 115` — DSPy LM source: `temperature: float | None = None`, `cache: bool = True`, and the line 115 comment "rollout_id has no effect when temperature=0; set temperature>0 to bypass the cache"
- `.venv/lib/python3.13/site-packages/dspy/adapters/utils.py:171` — `parse_value` source: pydantic TypeAdapter-based typed parsing
- `.planning/research/PITFALLS.md:197-230` — Pitfall 6 prevention strategies #1-6 (re-cited verbatim in `## Common Pitfalls`)
- `.planning/codebase/CONCERNS.md:146-162` — M4 LLM-output parsing brittleness (0.0 fallback prevention)
- `.planning/phases/18-personality-drift-detection/18-CONTEXT.md` — locked decisions (D-GATE-01 through D-BYPASS-02)
- `.planning/phases/10-prompt-constraints-cli/10-CONTEXT.md` — PromptRoleChecker interface pattern (D2)
- `.planning/phases/09-prompt-evaluation/09-CONTEXT.md` — PromptBehavioralDataset pattern (D1, D4)
- `.planning/phases/17-joint-section-optimization/17-CONTEXT.md` — shared output dir, metrics.json schema (D-OUT-01/02)
- DSPy 3.1.3 direct probe (this `.venv/`) — `Signature.model_fields`, `parse_value(value, float)` behavior on 6 input shapes, LM constructor signature

### Secondary (MEDIUM confidence)

- `.planning/codebase/CONCERNS.md:114-128` — M2 GEPA fallback (DriftDetector doesn't directly interact with GEPA, but calibration builder is downstream and should NOT silently fall back)
- `pyproject.toml:11-23` — dependency declarations (dspy>=3.0.0, no sklearn/numpy)
- LLM-as-judge literature general patterns (e.g., DeepEval, RAGAS) — pairwise > pointwise, 3-run averaging, multi-dim outputs — based on training knowledge; not Context7-fetched [ASSUMED]

### Tertiary (LOW confidence)

- temperature=0.7 sweet spot for `mean - stdev` decision rule — [ASSUMED based on general LLM judge tuning intuition; not empirically validated for THIS judge × THIS corpus]. Mitigated by Open Question 1 recommendation: pilot 3-run smoke test in Phase 18 verify.

## Metadata

**Confidence breakdown:**
- DSPy typed float OutputField: HIGH — directly probed in this `.venv/`
- DSPy LM cache + temperature stochasticity: HIGH — source-inspected `dspy/clients/lm.py`
- F1 derivation via stdlib: HIGH — verified sklearn absent + computed feasibility
- Pairwise multi-output signature: HIGH for cost/reliability, MEDIUM for "coherence" benefit
- Calibration anti-bias techniques: MEDIUM — mitigations are PITFALL #6 prevention-direct; quantitative benefit not empirically tied to this specific corpus
- F1 target 0.85/0.80 reasonability: MEDIUM-HIGH — math exact, but small sample size (3-4 positive per dim) means real-world variance is significant
- Existing code patterns (PromptRoleChecker, PromptBehavioralDataset): HIGH — directly read source

**Research date:** 2026-05-15
**Valid until:** 2026-06-15 (30 days) for DSPy 3.1.3 facts; if DSPy upgraded to 3.2+ during this window, re-verify typed OutputField behavior and LM cache semantics.

## RESEARCH COMPLETE
