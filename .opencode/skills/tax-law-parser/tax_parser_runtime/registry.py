from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
PROFILES_REGISTRY_PATH = SKILL_ROOT / "profiles" / "registry.json"
LEGACY_REGISTRY_PATH = SKILL_ROOT / "extractors" / "registry.json"
BASELINES_DIR = SKILL_ROOT / "baselines"


def resolve_pack_dir(pack_dir: str | Path | None) -> Path | None:
    if pack_dir is None:
        return None
    return Path(pack_dir).expanduser().resolve()


def _load_registry_file(path: Path, *, source: str, entry_root: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        entry = dict(item)
        entry.setdefault("registry_source", source)
        entry.setdefault("registry_path", str(path))
        entry.setdefault("_entry_root", str(entry_root))
        entries.append(entry)
    return entries


def _iter_registry_targets(pack_dir: Path | None) -> list[tuple[Path, str, Path]]:
    if pack_dir is not None:
        return [
            (pack_dir / "profiles" / "registry.json", "pack_profiles", pack_dir),
            (pack_dir / "extractors" / "registry.json", "pack_legacy", pack_dir),
        ]
    return [
        (PROFILES_REGISTRY_PATH, "profiles", SKILL_ROOT),
        (LEGACY_REGISTRY_PATH, "legacy", SKILL_ROOT),
    ]


def load_registry(pack_dir: str | Path | None = None) -> list[dict[str, Any]]:
    resolved_pack_dir = resolve_pack_dir(pack_dir)
    combined: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    for path, source, entry_root in _iter_registry_targets(resolved_pack_dir):
        for entry in _load_registry_file(path, source=source, entry_root=entry_root):
            name = str(entry.get("name", "")).strip()
            if not name or name in seen_names:
                continue
            combined.append(entry)
            seen_names.add(name)

    return combined


def find_registry_entry(name: str, pack_dir: str | Path | None = None) -> dict[str, Any] | None:
    for entry in load_registry(pack_dir=pack_dir):
        if entry.get("name") == name:
            return entry
    return None


def normalize_module_name(module_name: str) -> str:
    cleaned = str(module_name).strip()
    if not cleaned:
        raise RuntimeError("Extractor module name is empty.")
    if cleaned.startswith("extractors.") or "." in cleaned:
        return cleaned
    return f"extractors.{cleaned}"


def _resolve_entry_root(entry: dict[str, Any]) -> Path:
    explicit = str(entry.get("_entry_root", "")).strip()
    return Path(explicit).expanduser().resolve() if explicit else SKILL_ROOT


def describe_registry_module(entry: dict[str, Any]) -> str:
    module_path = str(entry.get("module_path", "")).strip()
    if module_path:
        return f"file:{resolve_module_path(entry)}"
    return normalize_module_name(str(entry.get("module", "")).strip())


def _resolve_entry_module_path(entry: dict[str, Any]) -> Path | None:
    module_path = str(entry.get("module_path", "")).strip()
    if not module_path:
        return None
    candidate = Path(module_path).expanduser()
    if not candidate.is_absolute():
        candidate = (_resolve_entry_root(entry) / candidate).resolve()
    return candidate


def _import_extractor_file(module_path: Path):
    resolved = module_path.expanduser().resolve()
    module_name = f"tax_parser_runtime.dynamic_{hashlib.sha1(str(resolved).encode('utf-8')).hexdigest()}"
    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached

    spec = importlib.util.spec_from_file_location(module_name, str(resolved))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Extractor module file '{resolved}' could not be loaded.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def import_extractor_module(module_name_or_entry: str | dict[str, Any]):
    if isinstance(module_name_or_entry, dict):
        module_path = _resolve_entry_module_path(module_name_or_entry)
        if module_path is not None:
            return _import_extractor_file(module_path)
        module_name = str(module_name_or_entry.get("module", "")).strip()
    else:
        module_name = str(module_name_or_entry).strip()

    import_name = normalize_module_name(module_name)
    try:
        return importlib.import_module(import_name)
    except ModuleNotFoundError as exc:
        raise RuntimeError(f"Extractor module '{import_name}' could not be imported.") from exc


def resolve_module_path(module_name_or_entry: str | dict[str, Any]) -> Path:
    if isinstance(module_name_or_entry, dict):
        module_path = _resolve_entry_module_path(module_name_or_entry)
        if module_path is not None:
            return module_path
        module_name = str(module_name_or_entry.get("module", "")).strip()
    else:
        module_name = str(module_name_or_entry).strip()

    module = import_extractor_module(module_name)
    module_file = getattr(module, "__file__", None)
    if not module_file:
        raise RuntimeError(f"Extractor module '{normalize_module_name(module_name)}' has no __file__.")
    return Path(module_file).resolve()


def resolve_baseline_path(entry: dict[str, Any] | None) -> Path | None:
    if not entry:
        return None

    explicit = str(entry.get("baseline_path", "")).strip()
    if explicit:
        candidate = Path(explicit).expanduser()
        if not candidate.is_absolute():
            candidate = (_resolve_entry_root(entry) / candidate).resolve()
        return candidate

    name = str(entry.get("name", "")).strip()
    if not name:
        return None

    entry_root = _resolve_entry_root(entry)
    if entry_root != SKILL_ROOT:
        return entry_root / "baselines" / name / "field_catalog.json"

    jurisdiction = str(entry.get("jurisdiction", "")).strip().lower()
    if not jurisdiction:
        return None
    return BASELINES_DIR / jurisdiction / name / "field_catalog.json"
