# Phase 20: Benchmark-Gated Validation - Discussion Log

**Date:** 2026-05-19
**Phase:** 20-benchmark-gated-validation
**Areas discussed:** Regression 判定语义, TBLite 子集策略, evolved sections 注入 TBLite 的机制, Calibration + cache + cost cap 落地形式

---

## Area 1: Regression 判定语义

### Q1.1 — TBLite gate 的 baseline (比较基准) 取哪个?

| Option | Description | Selected |
|--------|-------------|----------|
| 原始 hermes-agent (untouched) | 一次性 anchor + 缓存复用 | |
| 上次 accepted 的 evolved sections | 递归梯度 baseline | |
| 两者都跑 + 两个阈值 | 双保障双 cost | |
| (用户自定义) | 自适应滑动窗口基准 + 1.96σ 置信区间 | ✓ |

**User's choice:** "自适应滑动窗口基准 (包含初始锚点与移动平均),结合统计置信区间 (3-run σ 阈值判定)。核心逻辑: 通过 = 候选分数 >= (max(初始基准分数, 移动平均分数) - 1.96 * 标准差)。设计目的: 以初始版本 (untouched) 作为防止性能滑坡的锚点,以移动平均值 (moving_avg) 作为动态性能参考,引入标准差 (σ) 来过滤因环境导致的测试噪声。"

**Notes:** 此决策同时回答了 median-of-N 问题(3-run 必跑,既算 mean 又算 σ)。moving_avg 实现需要 history ledger 持久化 last N accepted runs;首次 evolve 时 moving_avg 退化为 anchor。落地见 CONTEXT D-01。

---

### Q1.2 — Pass/fail 判定按 TBLite 的哪个粒度评估?

| Option | Description | Selected |
|--------|-------------|----------|
| 整体 pass_rate (单一指标) | 100 tasks 聚合 pass_rate 单一 1.96σ 判定 | |
| Per-tier 4 个独立判定 | 4 个 tier 各自 1.96σ,任一 fail = candidate fail | |
| 整体 + per-tier 软警 | 硬门走整体,tier 走 yellow warn | |
| (用户自定义) | 分层加权独立判定 (Tier-wise Weighted Gating) | ✓ |

**User's choice:** "分层加权独立判定 (Tier-wise Weighted Gating):Easy/Medium/Hard/Extreme 各 tier 独立置信区间校验,并引入 Tier-specific 权重系数 (Extreme 权重最高),确保关键路径退步被强制拦截。"

**Notes:** 是 per-tier 判定的加强版 — 每 tier 独立 1.96σ 检查 + tier 权重。落地见 CONTEXT D-02。

---

### Q1.3 — Extreme tier 决策规则怎么写?

| Option | Description | Selected |
|--------|-------------|----------|
| Extreme breach = 硬拒 (zero-tolerance) | extreme 单 breach 直接 reject | |
| Weighted score 超总阈 = reject | Σ(w[t] × breach) ≥ threshold | |
| Extreme + Hard 都是硬拦项 | 两个高阶 tier 任一 breach = reject | |
| (用户自定义) | 梯度加权拦截 (Gradient-Weighted Blocking) | ✓ |

**User's choice:** "梯度加权拦截 (Gradient-Weighted Blocking):以加权风险分 Risk_Score = Σ(weight[t] × breach_flag[t]) 为核心,设定 Threshold = 4.0。Extreme tier 单独 Breach 触发硬阻断,同时允许低阶 Tier 的累计 Breach 触发拦截,实现'单点致命'与'累积失效'双重防御。"

**Notes:** 默认权重 `{easy:1.0, medium:1.5, hard:2.0, extreme:4.0}`,阈值 4.0。Extreme weight=4 → 单 breach 直达阈;低阶累积(e.g. easy+medium+hard=4.5)也可达。落地见 CONTEXT D-02。

---

## Area 2: TBLite 子集策略

### Q2.1 — TBLite gate 默认跑哪些 task?

| Option | Description | Selected |
|--------|-------------|----------|
| 全量 100 tasks (4 tier 都跑) | 完整 signal,~90-120 min,~$15-40/run | |
| 默认子集 + `--benchmark-full` flag | 30 tasks per-tier 抽样 + full 命令 | |
| `--benchmark-tier` CSV 选择 | 明拆要跑哪些 tier | |
| (用户自定义) | 分层动态子集 + 触发式全量校验 | ✓ |

**User's choice:** "分层动态子集 (Stratified Fast Subset) + 触发式全量校验:默认采样每个 Tier 的核心代表性任务(共 ~30 tasks),确保覆盖 4 个 Tier 以满足 Risk_Score 计算;一旦通过 Gate,自动触发后台全量校验作为异步质量回溯。"

**Notes:** 落地分布 `{easy:12, medium:8, hard:7, extreme:3}` = 30 tasks 白名单,git 跟踪 `datasets/prompts/tblite_stratified_subset.json`。落地见 CONTEXT D-05/D-07。

---

### Q2.2 — Gate 过了 + write-back 发生后,后台全量验证发现 regression 怎么处理?

| Option | Description | Selected |
|--------|-------------|----------|
| 告警但不 rollback | 写 metrics + stdout warn,人工反转 | |
| 自动 rollback 到上次 accepted | 自动 restore + 写 ROLLBACK_<ts>/ | |
| 不做 async full verify | 仅 stratified subset 为唯一 signal | |
| (用户自定义) | 软性自动回溯 (Soft-Rollback) + 状态隔离存储 | ✓ |

**User's choice:** "软性自动回溯 (Soft-Rollback) + 状态隔离存储:发现 Async Regression 时,系统自动在 ~/.hermes/backups/ 下保存当前版本副本,将生产环境 Prompt 状态回退至 last_known_good;同时在 logs/regression.jsonl 中挂起该次 Commit ID,待人工核验后确认是否恢复。"

**Notes:** 直接关联 Area 3 注入机制选项。需要 `evolve_prompt_sections --restore <ts>` / `--confirm-rollback <ts>` 子命令配合。落地见 CONTEXT D-08。

---

## Area 3: evolved sections 注入 TBLite 的机制

### Q3.1 — Phase 20 gate 跑 TBLite 时, evolved sections 怎么让 hermes-agent agent 加载到?

| Option | Description | Selected |
|--------|-------------|----------|
| Temp-dir 复制 hermes-agent (隔离) | 完整复制几百 MB 仓 | |
| 直接写回 hermes-agent + rollback | snapshot + 写回 + restore | |
| tblite_env `--env.system_prompt` flag 覆盖 | CLI override 路径 | |
| (用户自定义) | 虚拟 Prompt 层挂载 (Symlink Overwrite) | ✓ |

**User's choice:** "虚拟 Prompt 层挂载 (Virtual Prompt Overlay/Symlink Overwrite):通过符号链接 (Symlink) 替换 prompt_builder.py 所在的 sections/ 子目录,将候选 Prompt 注入到临时目录并挂载至测试环境,实现零复制、原子级切换,且完全物理隔离 hermes-agent 原仓。"

**Notes:** hermes-agent 当前实际结构是 `prompt_builder.py` 单文件而非 sections/ 子目录。Claude 已记录此差异,planner 实现 file-level 变体(snapshot + atomic `os.replace` 或 file-level symlink),保留"zero-copy + atomic + isolated"语义。落地见 CONTEXT D-09/D-10。

---

### Q3.2 — TBLite subprocess 马拉松 (60-120 分钟),如何管 timeout / 进度 / 中断?

| Option | Description | Selected |
|--------|-------------|----------|
| fail-fast 硬超时 | subprocess.run(timeout=N) 一刀切 | |
| Popen + 流式 tail samples.jsonl | Live Table 实时进度 | |
| 推 TBLite 到后台 + checkpoint-resume | detached + check_benchmark 查询 | |
| (用户自定义) | 异步流式管道 (Async Stream Pipe) + 状态监控器 (State Monitor) | ✓ |

**User's choice:** "异步流式管道 (Asynchronous Stream Pipe) + 状态监控器 (State Monitor):通过 subprocess.Popen 调用 tblite_env.py,并将 stdout/stderr 重定向至管道,在 evolve_prompt_sections 进程中利用非阻塞读取实现实时进度解析与 heartbeat 心跳检测;支持 --wait 阻塞式等待或 --detach 后台查询。"

**Notes:** option 2 + option 3 的合并。`--wait` / `--detach` 两 CLI mode 共享 same gate 算法,heartbeat 60s 阈值。落地见 CONTEXT D-11/D-12。

---

## Area 4: Calibration + cache + cost cap 落地形式

### Q4.1 — Anchor baseline × σ_baseline 从哪里来?

| Option | Description | Selected |
|--------|-------------|----------|
| 独立 build_tblite_calibration 子命令 (mirror Phase 18) | 独立 CLI + .gitignore exception | |
| 首次 evolve --benchmark 自动启动 calibration (lazy) | inline 启动,UX 顺畅 | |
| 每次 gate 同机跑 untouched (no calibration) | 6 runs/gate,cost 翻倍 | |
| (用户自定义) | 显式锚点校准 + 启动前校验 | ✓ |

**User's choice:** "显式锚点校准 (Explicit Anchor Calibration) + 启动前校验 (Pre-flight Validation):采用独立子命令 build_tblite_calibration 构建基准文件,且在进化流程中通过预检机制 (check_anchor_existence) 强制执行校准,确保所有 Risk_Score 计算基于确定的、持久化的 statistical floor。"

**Notes:** option 1 + 显式 pre-flight。Mirror Phase 18 D-CAL-05 mandatory calibration。落地见 CONTEXT D-13/D-14。

---

### Q4.2 — Artifact-hash cache (同一 evolved 不重复跑) 怎么作?

| Option | Description | Selected |
|--------|-------------|----------|
| 默认开 + content-addressed | sha256(evolved + tblite_version + seed) | |
| 默认开 + TTL 30 天 | 含上游 dataset 更新缓解 | |
| 默认关 + `--cache` opt-in | 保守设计 | |
| (用户自定义) | 默认内容寻址缓存 + 数据集版本绑定 | ✓ |

**User's choice:** "默认内容寻址缓存 (Default Content-Addressed Cache) + 数据集版本绑定 (Dataset Fingerprinting):默认开启基于 Artifact-Hash 的缓存机制,Hash 键值引入 TBLite 数据集的 Git Commit ID/MD5 校验和,确保上游更新时缓存自动失效,实现'零维护、零过期误报、按需精准重跑'。"

**Notes:** 比 option 1 升级 — 不用 string version,直接用 HuggingFace `HfApi().dataset_info(...).sha` 实时拿 dataset commit。落地见 CONTEXT D-15。

---

### Q4.3 — Cost cap 与现有 CostTracker 怎么集成?

| Option | Description | Selected |
|--------|-------------|----------|
| 复用 max_cost_usd 同一预算 | 统一不加新字段 | |
| 独立 benchmark_max_cost_usd 字段 + 独立 CostTracker | 默认 50.0,解耦 | |
| 双报表: 主路 + benchmark 加总 | 双独立 cap + 综合 accounting | |
| (用户自定义) | 双轨解耦预算配置 + 启动前水位预检 | ✓ |

**User's choice:** "双轨解耦预算配置 (Dual-Track Decoupled Budget) + 启动前水位预检 (Pre-flight Watermark Check):保留 max_cost_usd 控制优化主路,新增 benchmark_max_cost_usd(默认 50.0)专属 TBLite。在 metrics.json 输出双轨账单,并在 Subprocess 启动前执行 水位 = 预估单次成本 × 3 的硬性余额预检。"

**Notes:** option 3 + watermark pre-flight。`tblite_estimated_cost_per_task_usd` 字段首次 calibration 实测回写。落地见 CONTEXT D-16/D-17。

---

## Claude's Discretion (planner 决策)

- `evolution/benchmarks/__init__.py` lazy import 风格
- Virtual Prompt Overlay 具体实现:file-level symlink 还是 `os.replace` atomic mv
- TBLite subprocess 命令行精确构造:`bash run_eval.sh` vs `python tblite_env.py evaluate`
- TBLite output 解析方式:tail samples.jsonl per-line vs evaluate 退出后 batch read
- Stratified subset 30 tasks 白名单的具体 task 选择(planner 从 TBLite README + 实际 dataset 抽样)
- Tier weights 与 reject threshold 的精确数字(允许 ±10% 调参,暴露 `EvolutionConfig` 字段)
- `logs/regression.jsonl` 与 `~/.hermes/backups/<ts>/` 的精确 schema
- `--check-benchmark / --restore / --confirm-rollback` 是 Click subcommand 还是 flag 形式
- HuggingFace API 调用方式(`HfApi().dataset_info` vs `snapshot_download`)
- `last_known_good` 是否要求 async full verify 也通过
- `tblite_estimated_cost_per_task_usd` 实测回写策略
- Rich Live Table 列设计 + ETA 算法
- `--detach` mode 下 staging 区位置
- Test fixture 设计(deterministic mock,不调外部 API)

## Deferred Ideas

参见 CONTEXT.md `<deferred>` 节,共 11 项:
- evolve_tool_descriptions / evolve_skill 接 --benchmark
- HuggingFace dataset revision pin
- YC-Bench / 完整 TB2 集成
- per-iteration benchmark in GEPA loop (永不开启)
- Quarterly auto recalibration
- 三档 --benchmark={tblite-fast, tblite-full, tblite-tier <tier>}
- Risk_Score 阈值/权重运行期自适应
- Per-section attribution of benchmark regression
- Cache 内容主动失效 (--clear-benchmark-cache)
- Dataset 本地镜像 (huggingface_hub snapshot)
- Modal backend 替代 (本地 Docker)
- Phase 16 dashboard 接入 benchmark_* 字段
