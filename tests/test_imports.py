"""The plugin's modules must import against the ovos-utils it declares.

A dead import is not a cosmetic problem here: `arduino.py` owns the serial
port, so a module that cannot be imported is a Mark 1 with no eyes and no
mouth at all. This caught exactly that -- an unused
`from ovos_utils.signal import check_for_signal` left behind after
`ovos_utils.signal` was removed upstream.
"""
import importlib

import pytest


@pytest.mark.parametrize("name", [
    "ovos_PHAL_plugin_mk1",
    "ovos_PHAL_plugin_mk1.arduino",
])
def test_the_module_imports(name):
    assert importlib.import_module(name) is not None


def test_no_module_imports_a_name_it_never_uses():
    """The dead import that broke this was also an unused one.

    An import that nothing references cannot be justified by behaviour, so it
    is pure risk: it can only ever break the module.
    """
    import ast
    import pathlib

    package = pathlib.Path(__file__).resolve().parent.parent / "ovos_PHAL_plugin_mk1"
    unused = []
    for path in package.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    bound = alias.asname or alias.name.split(".")[0]
                    imported[bound] = node.lineno
        used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        used |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        source = path.read_text(encoding="utf-8")
        for name, line in imported.items():
            if name in used:
                continue
            # a name used only inside a string annotation still counts
            if f"'{name}'" in source or f'"{name}"' in source:
                continue
            unused.append(f"{path.name}:{line} {name}")
    assert not unused, f"imported but never used: {unused}"
