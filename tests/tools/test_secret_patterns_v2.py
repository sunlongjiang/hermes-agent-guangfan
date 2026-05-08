"""Phase 14 Wave 0 stub — secret patterns v2 tests.

Target: 14-VALIDATION.md rows 13-15 (test_layer1_positives / test_v1_regression /
test_low_entropy_negatives). Wave 1+ 实现见 14-03-PLAN.md.

B4 belt-and-suspenders: 文件顶部 **禁止** 导入 `_shannon_entropy` — 该符号在
Wave 1 (Plan 03 Task 3.2) 落地前不存在，collect-time ImportError 会让 RED
grep mis-match 为 ERROR 而非 FAILED。本 stub 仅保留实现后真正需要的 import。
"""

import pytest


def test_layer1_positives():
    """JWT / AWS-secret 邻近 / 高熵 ≥32-char base64 token 必须被 _contains_secret 检出。"""
    pytest.skip("Wave 1+ 实现 — 见 14-03-PLAN.md Task 3.1")


def test_v1_regression():
    """Phase 1 SECRET_PATTERNS 现有命中行为必须保留（D-15 不破坏 v1）。"""
    pytest.skip("Wave 1+ 实现 — 见 14-03-PLAN.md Task 3.1")


def test_low_entropy_negatives():
    """中文散文 / 短英文 / 真实 SHA256 hex 不应被熵分支误判。"""
    pytest.skip("Wave 1+ 实现 — 见 14-03-PLAN.md Task 3.1")
