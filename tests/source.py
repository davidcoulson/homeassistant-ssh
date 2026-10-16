"""Load production definitions with explicit fakes instead of importing HA.

HA 2026.10 needs a newer Python than this test environment. These tests execute
unaltered source definitions and the real pinned manager, with no HA runtime.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def definitions(filename, names, namespace=None):
    tree = ast.parse((ROOT / "custom_components/ssh" / filename).read_text())
    nodes = [node for node in tree.body if getattr(node, "name", None) in names]
    assert len(nodes) == len(names)
    module = ast.Module(
        body=[
            ast.ImportFrom(
                module="__future__", names=[ast.alias("annotations")], level=0
            ),
            *nodes,
        ],
        type_ignores=[],
    )
    ast.fix_missing_locations(module)
    namespace = dict(namespace or {})
    exec(compile(module, filename, "exec"), namespace)  # noqa: S102 - execute repository definitions with explicit fakes
    return namespace
