from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parent
PROFILES_REGISTRY_PATH = SKILL_ROOT / "profiles" / "registry.json"
LEGACY_REGISTRY_PATH = SKILL_ROOT / "extractors" / "registry.json"
BASELINES_DIR = SKILL_ROOT / "baselines"


def _load_registry_file(path: Path, *, source: str) -> list[dict[str, Any]]:
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
        entries.append(entry)
    return entries


def load_registry() -> list[dict[str, Any]]:
    combined: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    for path, source in [
        (PROFILES_REGISTRY_PATH, "profiles"),
        (LEGACY_REGISTRY_PATH, "legacy"),
    ]:
        for entry in _load_registry_file(path, source=source):
            name = str(entry.get("name", "")).strip()
            if not name or name in seen_names:
                continue
            combined.append(entry)
            seen_names.add(name)

    return combined


def find_registry_entry(name: str) -> dict[str, Any] | None:
    for entry in load_registry():
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


def import_extractor_module(module_name: str):
    import_name = normalize_module_name(module_name)
    try:
        return importlib.import_module(import_name)
    except ModuleNotFoundError as exc:
        raise RuntimeError(f"Extractor module '{import_name}' could not be imported.") from exc


def resolve_module_path(module_name: str) -> Path:
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
            candidate = (SKILL_ROOT / candidate).resolve()
        return candidate

    name = str(entry.get("name", "")).strip()
    jurisdiction = str(entry.get("jurisdiction", "")).strip().lower()
    if not name or not jurisdiction:
        return None

    return BASELINES_DIR / jurisdiction / name / "field_catalog.json"
