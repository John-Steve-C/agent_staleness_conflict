from __future__ import annotations

import ast
import json
import subprocess
import sys

from .models import ConflictEpisode


_BEHAVIOR_HARNESS = r"""
import json
import sys

scenario = sys.argv[1]
source = sys.stdin.read()

def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name != "json" or level:
        raise ImportError(name)
    return json

safe_builtins = {
    "__import__": guarded_import,
    "dict": dict,
    "enumerate": enumerate,
    "isinstance": isinstance,
    "len": len,
    "list": list,
    "max": max,
    "PermissionError": PermissionError,
    "range": range,
    "RuntimeError": RuntimeError,
    "set": set,
    "str": str,
    "TypeError": TypeError,
}
scope = {"__builtins__": safe_builtins}
exec(compile(source, "candidate.py", "exec"), scope)

if scenario == "normalization":
    assert scope["normalize"](" Alice ") == "alice"
    try:
        scope["normalize"](3)
    except TypeError:
        pass
    else:
        raise AssertionError("normalize must reject non-text input")
elif scenario == "formatting":
    assert scope["render"](" x ", prefix=">") == ">x"
elif scenario == "cache":
    cache = scope["build_cache"](3, ttl=7)
    assert cache == {"max_size": 3, "ttl": 7, "items": {}}
elif scenario == "authorization":
    class User:
        scopes = {"read"}
    class Audit:
        def __init__(self):
            self.calls = []
        def record(self, user, scope):
            self.calls.append((user, scope))
    user = User()
    audit = Audit()
    assert scope["authorize"](user, " read ", audit=audit) is True
    assert audit.calls == [(user, "read")]
    try:
        scope["authorize"](user, "write", audit=audit)
    except PermissionError:
        pass
    else:
        raise AssertionError("authorize must enforce scope membership")
elif scenario == "transaction":
    class Store:
        def __init__(self, version):
            self.version = version
            self.values = []
        def write(self, value):
            self.values.append(value)
    class Logger:
        def __init__(self):
            self.messages = []
        def info(self, message):
            self.messages.append(message)
    store = Store(2)
    logger = Logger()
    scope["commit"](store, 2, "value", retries=2, logger=logger)
    assert store.values == ["value"] and logger.messages == ["committed"]
    stale = Store(3)
    try:
        scope["commit"](stale, 2, "value", retries=1, logger=logger)
    except RuntimeError:
        pass
    else:
        raise AssertionError("commit must reject stale versions")
    assert stale.values == []
elif scenario == "serialization":
    assert scope["dumps"]({"b": 1, "a": 2}) == '{"a": 2, "b": 1}'
    try:
        scope["dumps"](["a"])
    except TypeError:
        pass
    else:
        raise AssertionError("dumps must reject non-dictionaries")
elif scenario == "deduplication":
    assert scope["unique"](["b", "a", "b"]) == ["b", "a"]
    try:
        scope["unique"](None)
    except TypeError:
        pass
    else:
        raise AssertionError("unique must reject None")
elif scenario == "pagination":
    values = list(range(8))
    assert scope["page"](values, 3, offset=2) == [2, 3, 4]
    assert scope["page"](values, -2, offset=2) == []
else:
    raise AssertionError(f"unknown validator: {scenario}")
"""


_DEPENDENCY_HARNESS = r"""
import json
import sys

scenario = sys.argv[1]
source = sys.stdin.read()

def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name != "json" or level:
        raise ImportError(name)
    return json

safe_builtins = {
    "__import__": guarded_import,
    "dict": dict,
    "isinstance": isinstance,
    "list": list,
    "max": max,
    "PermissionError": PermissionError,
    "range": range,
    "RuntimeError": RuntimeError,
    "set": set,
    "str": str,
    "TypeError": TypeError,
}
scope = {"__builtins__": safe_builtins}
exec(compile(source, "candidate.py", "exec"), scope)

if scenario == "normalization":
    try:
        scope["normalize"](3)
    except TypeError:
        pass
    else:
        raise AssertionError("normalize must reject non-text input")
elif scenario == "formatting":
    assert scope["render"]("x", prefix=">") == ">x"
elif scenario == "cache":
    assert scope["DEFAULT_TTL"] == 60
elif scenario == "authorization":
    class User:
        scopes = {"read"}
    user = User()
    assert scope["authorize"](user, " read ") is True
    try:
        scope["authorize"](user, "write")
    except PermissionError:
        pass
    else:
        raise AssertionError("authorize must enforce scope membership")
elif scenario == "transaction":
    class Store:
        def __init__(self, version):
            self.version = version
            self.values = []
        def write(self, value):
            self.values.append(value)
    stale = Store(3)
    try:
        scope["commit"](stale, 2, "value")
    except RuntimeError:
        pass
    else:
        raise AssertionError("commit must reject stale versions")
    assert stale.values == []
elif scenario == "serialization":
    try:
        scope["dumps"](["a"])
    except TypeError:
        pass
    else:
        raise AssertionError("dumps must reject non-dictionaries")
elif scenario == "deduplication":
    try:
        scope["unique"](None)
    except TypeError:
        pass
    else:
        raise AssertionError("unique must reject None")
elif scenario == "pagination":
    values = list(range(8))
    assert scope["page"](values, 3, offset=2) == [2, 3, 4]
else:
    raise AssertionError(f"unknown validator: {scenario}")
"""


_CUSTOM_HARNESS = r"""
import json
import sys

payload = json.load(sys.stdin)
safe_builtins = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "bytes": bytes,
    "dict": dict,
    "enumerate": enumerate,
    "float": float,
    "int": int,
    "IndexError": IndexError,
    "isinstance": isinstance,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "range": range,
    "reversed": reversed,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
    "AssertionError": AssertionError,
    "KeyError": KeyError,
    "PermissionError": PermissionError,
    "RuntimeError": RuntimeError,
    "TypeError": TypeError,
    "ValueError": ValueError,
}
scope = {"__builtins__": safe_builtins}
exec(compile(payload["source"], "candidate.py", "exec"), scope)
exec(compile(payload["check"], "check.py", "exec"), scope)
"""


def _safe_syntax(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name != "json" for alias in node.names):
                return False
        elif isinstance(node, ast.ImportFrom):
            return False
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            return False
        elif isinstance(node, ast.Name) and node.id in {
            "breakpoint",
            "compile",
            "eval",
            "exec",
            "globals",
            "help",
            "input",
            "locals",
            "open",
        }:
            return False
    return True


def _assignments(tree: ast.AST) -> dict[str, object]:
    assignments: dict[str, object] = {}
    for node in getattr(tree, "body", []):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        try:
            assignments[target.id] = ast.literal_eval(node.value)
        except (ValueError, TypeError):
            continue
    return assignments


def _run_custom_check(content: str, check: str) -> bool:
    try:
        completed = subprocess.run(
            [sys.executable, "-I", "-c", _CUSTOM_HARNESS],
            input=json.dumps({"source": content, "check": check}),
            text=True,
            capture_output=True,
            timeout=1.0,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False
    return completed.returncode == 0


def validate_revision(episode: ConflictEpisode, content: str) -> bool:
    """Validate behavior without exposing evaluator rules to the recovery model."""
    if not content.strip():
        return False
    try:
        tree = ast.parse(content, filename=episode.file_path)
    except SyntaxError:
        return False
    if not _safe_syntax(tree):
        return False

    validator = str(episode.metadata.get("validator", ""))
    if not validator:
        required = episode.metadata.get("required_substrings", [])
        forbidden = episode.metadata.get("forbidden_substrings", [])
        code_without_comments = ast.unparse(tree)
        return all(item in code_without_comments for item in required) and not any(
            item in code_without_comments for item in forbidden
        )

    expected_assignments = episode.metadata.get("protected_assignments", {})
    actual_assignments = _assignments(tree)
    if any(actual_assignments.get(key) != value for key, value in expected_assignments.items()):
        return False

    custom_check = str(episode.metadata.get("behavior_check", ""))
    if custom_check:
        return _run_custom_check(content, custom_check)

    try:
        completed = subprocess.run(
            [sys.executable, "-I", "-c", _BEHAVIOR_HARNESS, validator],
            input=content,
            text=True,
            capture_output=True,
            timeout=1.0,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False
    return completed.returncode == 0


def validate_dependencies(episode: ConflictEpisode, content: str) -> bool:
    """Run only the pre-existing behavior on which the losing task depends."""
    if not content.strip():
        return False
    try:
        tree = ast.parse(content, filename=episode.file_path)
    except SyntaxError:
        return False
    if not _safe_syntax(tree):
        return False
    validator = str(episode.metadata.get("validator", ""))
    if not validator:
        return True
    custom_check = str(episode.metadata.get("dependency_check", ""))
    if custom_check:
        return _run_custom_check(content, custom_check)
    try:
        completed = subprocess.run(
            [sys.executable, "-I", "-c", _DEPENDENCY_HARNESS, validator],
            input=content,
            text=True,
            capture_output=True,
            timeout=1.0,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False
    return completed.returncode == 0
