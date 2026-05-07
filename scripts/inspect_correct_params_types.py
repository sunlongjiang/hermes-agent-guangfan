"""One-shot: count value types across correct_params in all three splits.

Resolves RESEARCH Open Question #2: is param normalization rule 'strip-only'
sufficient, or must it coerce int/bool/list/etc.? Dominance of str -> strip-only;
diversity -> strip + numeric/type coerce.

Usage:
    /Users/slj/项目/hermes-agent-self-evolution/.venv/bin/python scripts/inspect_correct_params_types.py
"""
import json
from collections import Counter
from pathlib import Path

DATASET_DIR = Path("datasets/tools")
SPLITS = ["train", "val", "holdout"]


def main():
    total = Counter()
    per_split = {}
    per_type_examples: dict[str, list] = {}
    empty_dict_count = 0
    nested_dict_count = 0
    total_examples = 0
    examples_with_any_params = 0

    for split in SPLITS:
        c = Counter()
        p = DATASET_DIR / f"{split}.jsonl"
        if not p.exists():
            continue
        with p.open() as f:
            for line in f:
                row = json.loads(line)
                total_examples += 1
                params = row.get("correct_params") or {}
                if not params:
                    empty_dict_count += 1
                    continue
                examples_with_any_params += 1
                for k, v in params.items():
                    tname = type(v).__name__
                    c[tname] += 1
                    total[tname] += 1
                    if tname == "dict":
                        nested_dict_count += 1
                    per_type_examples.setdefault(tname, [])
                    if len(per_type_examples[tname]) < 3:
                        per_type_examples[tname].append({"k": k, "v": v, "split": split})
        per_split[split] = c

    print("=== correct_params value-type distribution ===")
    print(f"total_examples={total_examples}")
    print(f"empty_dict_count={empty_dict_count}")
    print(f"examples_with_any_params={examples_with_any_params}")
    print(f"nested_dict_count={nested_dict_count}")
    print()
    for split, c in per_split.items():
        print(f"[{split}] {dict(c)}")
    print()
    print("=== overall by type ===")
    for tname, n in total.most_common():
        print(f"{tname}_count={n}")
    print()
    print("=== sample values per type ===")
    for tname, samples in sorted(per_type_examples.items()):
        print(f"-- {tname} --")
        for s in samples:
            print(f"  [{s['split']}] {s['k']!r} = {s['v']!r}")

    # Recommendation
    dominant = total.most_common(1)[0][0] if total else "none"
    diversity = len(total)
    print()
    print("=== recommendation ===")
    if dominant == "str" and diversity <= 2:
        print("NORMALIZATION_RULE=strip_only")
        print("# str-dominant; strip both sides + lowercase comparison is sufficient")
    else:
        print("NORMALIZATION_RULE=strip_plus_coerce")
        print(f"# multi-type (types seen: {sorted(total.keys())}); apply strip + try int/float/bool coerce")


if __name__ == "__main__":
    main()
