import ast
from pathlib import Path

PACKAGE_ROOT = Path(__file__).parents[1] / "src" / "nanexus_event_intelligence"
CORE_ROOT = PACKAGE_ROOT / "core"
FORBIDDEN_CORE_PREFIXES = (
    "nanexus_event_intelligence.adapters",
    "nanexus_event_intelligence.plugins",
    "paho",
)
PRIVATE_PREFIXES = (
    "nanexus_event_intelligence.pro",
    "nanexus_event_intelligence_private",
    "nanexus_pro",
)


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_core_does_not_import_adapters_or_plugin_implementations() -> None:
    violations: list[str] = []
    for path in CORE_ROOT.rglob("*.py"):
        for module in imported_modules(path):
            if module.startswith(FORBIDDEN_CORE_PREFIXES):
                violations.append(f"{path.relative_to(PACKAGE_ROOT)} imports {module}")
    assert violations == []


def test_vendor_clients_stay_inside_adapter_boundary() -> None:
    violations: list[str] = []
    adapter_root = PACKAGE_ROOT / "adapters" / "frigate"
    for path in PACKAGE_ROOT.rglob("*.py"):
        if path == PACKAGE_ROOT / "main.py":
            continue  # composition root wires concrete adapters
        if path.is_relative_to(adapter_root):
            continue
        for module in imported_modules(path):
            if module.startswith(
                ("aiomqtt", "paho", "nanexus_event_intelligence.adapters.frigate")
            ):
                violations.append(f"{path.relative_to(PACKAGE_ROOT)} imports {module}")
    assert violations == []


def test_community_source_has_no_private_or_pro_imports() -> None:
    violations: list[str] = []
    for path in PACKAGE_ROOT.rglob("*.py"):
        for module in imported_modules(path):
            if module.startswith(PRIVATE_PREFIXES):
                violations.append(f"{path.relative_to(PACKAGE_ROOT)} imports {module}")
    assert violations == []
