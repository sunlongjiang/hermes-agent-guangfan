"""D-18 CI lint gate — pytest 第二层防御。

验证 ``import openevolve`` 和 ``from openevolve`` 仅出现在
``evolution/code/code_evolver_adapter.py``（D-03 单点 import 面）。

设计要点
~~~~~~~~
- 不 ``import openevolve`` 本身 — 允许在 openevolve 未安装的环境中通过；
  pure pathlib + 正则扫描即可，运行时间 < 1s。
- 与 ``.pre-commit-config.yaml`` 的 ``openevolve-single-import-surface``
  hook 构成双层防御（pre-commit = 第一层；本测试 = 第二层）；
  pre-commit 仅在本地启用，CI/pytest 始终运行此测试。
- 测试通过 ``Path(__file__)`` 上溯定位仓根（独立于 pytest 调用目录）。
"""

import re
from pathlib import Path


# 仓根 = 本测试文件向上两级（tests/code/test_import_boundary.py → tests/code → tests → <repo>）。
# 使用 Path(__file__) 而非 Path.cwd()，保证 pytest 在任意工作目录调用均可定位。
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# 匹配行首的 ``import openevolve`` 或 ``from openevolve``（含 ``from openevolve.config import ...``）。
# 用 re.MULTILINE 让 ``^`` 锚定到每行起始。
_IMPORT_PATTERN = re.compile(r"^(?:import openevolve|from openevolve)", re.MULTILINE)

# D-03 唯一允许含 openevolve import 的源文件，相对仓根表示。
_ALLOWED_FILE = _REPO_ROOT / "evolution" / "code" / "code_evolver_adapter.py"


class TestImportBoundary:
    """pytest 层 D-18 防御：扫描 evolution/ 所有 .py，断言 openevolve import
    仅出现在 ``evolution/code/code_evolver_adapter.py``。"""

    def test_openevolve_import_only_in_adapter(self):
        """pathlib 扫描 evolution/ 所有 .py，正则匹配 openevolve import，
        断言仅 code_evolver_adapter.py 中出现。

        允许的违规白名单：
        - ``evolution/code/code_evolver_adapter.py`` — D-03 单点 import 面
        - ``__pycache__/`` 子目录 — 字节码缓存（运行时产物）
        """
        evolution_dir = _REPO_ROOT / "evolution"
        violations: list[str] = []

        for py_file in evolution_dir.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            if _IMPORT_PATTERN.search(content):
                if py_file.resolve() != _ALLOWED_FILE.resolve():
                    # 用相对仓根的路径让错误消息可读。
                    violations.append(str(py_file.relative_to(_REPO_ROOT)))

        assert violations == [], (
            "D-18 VIOLATION: openevolve import found outside "
            "evolution/code/code_evolver_adapter.py:\n"
            + "\n".join(f"  {v}" for v in violations)
        )
