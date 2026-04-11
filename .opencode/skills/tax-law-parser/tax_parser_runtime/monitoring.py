from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SCRIPT_PATH = Path(__file__).resolve()
SKILL_ROOT = SCRIPT_PATH.parents[1]
REPO_ROOT = SCRIPT_PATH.parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from tax_parser_runtime.registry import load_registry as load_profile_registry


DEFAULT_INDEX = SKILL_ROOT / "sources" / "index.yaml"
USER_AGENT = "tax-law-parser-source-monitor/1.0"


class HtmlTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.parts.append(text)

    def get_text(self) -> str:
        return "\n".join(self.parts)


@dataclass
class FetchResult:
    url: str
    ok: bool
    final_url: str | None
    status_code: int | None
    content_type: str | None
    sha256: str | None
    size_bytes: int | None
    error: str | None
    visible_text: str
    visible_text_sha256: str | None
    bytes_payload: bytes | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Monitor official tax-law source pages and attachments for changes."
    )
    parser.add_argument(
        "--index",
        default=str(DEFAULT_INDEX),
        help="Path to sources/index.yaml.",
    )
    parser.add_argument(
        "--pack-dir",
        help="Optional pack root directory. When provided, load sources and profiles from that pack.",
    )
    parser.add_argument("--outdir", required=True, help="Directory for generated monitoring reports.")
    parser.add_argument(
        "--jurisdiction",
        action="append",
        default=[],
        help="Optional jurisdiction filter. May be repeated.",
    )
    parser.add_argument(
        "--source-id",
        action="append",
        default=[],
        help="Optional source_id filter. May be repeated.",
    )
    parser.add_argument(
        "--previous-snapshot",
        help="Optional previous snapshot JSON. Defaults to <outdir>/latest_snapshot.json when present.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--no-write-latest",
        action="store_true",
        help="Do not overwrite <outdir>/latest_snapshot.json.",
    )
    parser.add_argument(
        "--fail-on-change",
        action="store_true",
        help="Exit non-zero when any source is new or changed.",
    )
    parser.add_argument(
        "--fail-on-error",
        action="store_true",
        help="Exit non-zero when any fetch error is present.",
    )
    parser.add_argument(
        "--fail-on-review",
        action="store_true",
        help="Exit non-zero when any review item is generated.",
    )
    return parser.parse_args()


def load_yaml(path: Path) -> Any:
    try:
        yaml = importlib.import_module("yaml")
    except ModuleNotFoundError:
        return load_yaml_with_ruby(path)
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_yaml_with_ruby(path: Path) -> Any:
    ruby_script = """
require "yaml"
require "json"
path = ARGV[0]
payload = YAML.load_file(path)
puts JSON.generate(payload)
"""
    result = subprocess.run(
        ["ruby", "-e", ruby_script, str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() or "unknown ruby yaml loader error"
        raise RuntimeError(f"Failed to load YAML via ruby for {path}: {stderr}")
    return json.loads(result.stdout)


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip())
    return cleaned.strip("-._") or "artifact"


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def html_to_text(payload: bytes) -> str:
    parser = HtmlTextExtractor()
    parser.feed(payload.decode("utf-8", errors="ignore"))
    return parser.get_text()


def fetch_url(url: str, timeout: int) -> FetchResult:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read()
            content_type = response.headers.get_content_type()
            visible_text = ""
            if content_type in {"text/html", "application/xhtml+xml"}:
                visible_text = html_to_text(payload)
            elif content_type.startswith("text/"):
                visible_text = payload.decode("utf-8", errors="ignore")
            visible_text_sha256 = (
                hashlib.sha256(normalize_whitespace(visible_text).encode("utf-8")).hexdigest()
                if visible_text
                else None
            )
            return FetchResult(
                url=url,
                ok=True,
                final_url=response.geturl(),
                status_code=getattr(response, "status", None),
                content_type=content_type,
                sha256=hashlib.sha256(payload).hexdigest(),
                size_bytes=len(payload),
                error=None,
                visible_text=visible_text,
                visible_text_sha256=visible_text_sha256,
                bytes_payload=payload,
            )
    except HTTPError as exc:
        return FetchResult(
            url=url,
            ok=False,
            final_url=exc.geturl(),
            status_code=exc.code,
            content_type=None,
            sha256=None,
            size_bytes=None,
            error=f"HTTPError: {exc.code}",
            visible_text="",
            visible_text_sha256=None,
            bytes_payload=None,
        )
    except URLError as exc:
        return FetchResult(
            url=url,
            ok=False,
            final_url=None,
            status_code=None,
            content_type=None,
            sha256=None,
            size_bytes=None,
            error=f"URLError: {exc.reason}",
            visible_text="",
            visible_text_sha256=None,
            bytes_payload=None,
        )


def attachment_best_effort_text(fetch: FetchResult) -> str:
    if not fetch.ok or fetch.bytes_payload is None:
        return ""

    content_type = fetch.content_type or ""
    if content_type.startswith("text/"):
        return fetch.bytes_payload.decode("utf-8", errors="ignore")

    candidates: list[str] = [fetch.bytes_payload.decode("latin1", errors="ignore")]
    extracted = extract_strings_from_bytes(fetch.bytes_payload)
    if extracted:
        candidates.append(extracted)
    return "\n".join(part for part in candidates if part)


def extract_strings_from_bytes(payload: bytes) -> str:
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as handle:
            handle.write(payload)
            temp_path = Path(handle.name)
        result = subprocess.run(
            ["strings", str(temp_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        return result.stdout if result.returncode == 0 else ""
    except FileNotFoundError:
        return ""
    finally:
        try:
            if temp_path is not None:
                temp_path.unlink()
        except Exception:
            pass


def choose_signal_text(source: dict[str, Any], landing: FetchResult, attachment: FetchResult | None) -> str:
    signal = source.get("version_signal", {}) or {}
    location = str(signal.get("location", "")).strip()
    if location == "landing_page":
        return landing.visible_text
    if location == "pdf_first_page":
        return attachment_best_effort_text(attachment) if attachment else ""
    if location == "attachment":
        return attachment_best_effort_text(attachment) if attachment else ""
    return landing.visible_text


def extract_signal_value(source: dict[str, Any], landing: FetchResult, attachment: FetchResult | None) -> dict[str, Any]:
    signal = source.get("version_signal", {}) or {}
    source_text = choose_signal_text(source, landing, attachment)
    extraction_mode = str(signal.get("extraction_mode", "")).strip()
    regex = str(signal.get("regex", "")).strip()

    value = ""
    status = "unavailable" if not source_text else "not_found"

    if regex and source_text:
        match = re.search(regex, source_text, re.MULTILINE)
        if match:
            value = normalize_whitespace(match.group(0))
            status = "ok"
    elif extraction_mode == "official_gazette_citation" and source_text:
        match = re.search(r'Official Gazette[^\n<]+', source_text, re.IGNORECASE)
        if match:
            value = normalize_whitespace(match.group(0).strip().strip('"'))
            status = "ok"
    elif extraction_mode == "published_date_text" and source_text:
        match = re.search(
            r"\b\d{1,2}\.\s*\d{1,2}\.\s*\d{4}\.|\b[A-Z][a-z]+ \d{1,2}, \d{4}\b",
            source_text,
        )
        if match:
            value = normalize_whitespace(match.group(0))
            status = "ok"
    elif extraction_mode == "listed_acts_snapshot" and source_text:
        lines = [normalize_whitespace(line) for line in source_text.splitlines()]
        filtered = [line for line in lines if line and any(token in line for token in ("Zakon", "HRN EN", "PDV"))]
        if filtered:
            value = " | ".join(filtered[:5])
            status = "ok"

    if not value and extraction_mode == "official_gazette_citation" and landing.visible_text:
        fallback_match = re.search(r'Official Gazette[^\n<]+', landing.visible_text, re.IGNORECASE)
        if fallback_match:
            value = normalize_whitespace(fallback_match.group(0).strip().strip('"'))
            status = "fallback_landing_page"

    if not value and str(signal.get("location", "")).strip() == "pdf_first_page" and attachment:
        metadata_match = re.search(
            r"xmp:CreateDate>(\d{4}-\d{2}-\d{2})|/CreationDate\(D:(\d{4})(\d{2})(\d{2})",
            attachment_best_effort_text(attachment),
        )
        if metadata_match:
            if metadata_match.group(1):
                value = metadata_match.group(1)
            else:
                value = f"{metadata_match.group(2)}-{metadata_match.group(3)}-{metadata_match.group(4)}"
            status = "fallback_pdf_metadata_date"

    return {
        "location": signal.get("location", ""),
        "extraction_mode": extraction_mode,
        "regex": regex,
        "status": status,
        "value": value,
        "observed_value_hint": signal.get("observed_value", ""),
    }


def evaluate_text_contains(source: dict[str, Any], landing: FetchResult) -> dict[str, Any]:
    needles = [str(item).strip() for item in source.get("landing_page_text_contains", []) if str(item).strip()]
    haystack = landing.visible_text or ""
    matches = [needle for needle in needles if needle in haystack]
    return {
        "expected": needles,
        "matched": matches,
        "missing": [needle for needle in needles if needle not in matches],
        "all_matched": len(matches) == len(needles),
    }


def load_registry_entries(index_path: Path) -> list[dict[str, Any]]:
    index_payload = load_yaml(index_path)
    jurisdictions = index_payload.get("jurisdictions", [])
    entries: list[dict[str, Any]] = []
    for item in jurisdictions:
        if not isinstance(item, dict):
            continue
        registry_path = item.get("registry_path")
        if not registry_path:
            continue
        registry_full_path = (index_path.parent / str(registry_path)).resolve()
        registry_payload = load_yaml(registry_full_path)
        for source in registry_payload.get("sources", []):
            if not isinstance(source, dict):
                continue
            merged = dict(source)
            merged.setdefault("jurisdiction", registry_payload.get("jurisdiction", item.get("jurisdiction", "")))
            merged.setdefault("tax_domain", registry_payload.get("tax_domain", item.get("tax_domain", "")))
            merged["_registry_path"] = str(registry_full_path)
            entries.append(merged)
    return entries


def load_pack_source_entries(pack_dir: Path) -> list[dict[str, Any]]:
    registry_full_path = (pack_dir / "sources" / "official_sources.yaml").resolve()
    registry_payload = load_yaml(registry_full_path)
    entries: list[dict[str, Any]] = []
    for source in registry_payload.get("sources", []):
        if not isinstance(source, dict):
            continue
        merged = dict(source)
        merged.setdefault("jurisdiction", registry_payload.get("jurisdiction", ""))
        merged.setdefault("tax_domain", registry_payload.get("tax_domain", ""))
        merged["_registry_path"] = str(registry_full_path)
        merged["_pack_dir"] = str(pack_dir)
        entries.append(merged)
    return entries


def filter_sources(entries: list[dict[str, Any]], jurisdictions: set[str], source_ids: set[str]) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for item in entries:
        jurisdiction = str(item.get("jurisdiction", "")).upper()
        source_id = str(item.get("source_id", "")).strip()
        if jurisdictions and jurisdiction not in jurisdictions:
            continue
        if source_ids and source_id not in source_ids:
            continue
        filtered.append(item)
    return filtered


def load_previous_snapshot(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    return payload


def compare_entry(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    if previous is None:
        return {"change_status": "new", "changed_fields": ["first_seen"]}

    previous_landing = previous.get("landing") or {}
    current_landing = current.get("landing") or {}
    previous_attachment = previous.get("attachment") or {}
    current_attachment = current.get("attachment") or {}
    previous_signal = previous.get("version_signal") or {}
    current_signal = current.get("version_signal") or {}
    previous_text_contains = previous.get("text_contains") or {}
    current_text_contains = current.get("text_contains") or {}

    changed_fields: list[str] = []
    paths = [
        (
            "landing.visible_text_sha256",
            previous_landing.get("visible_text_sha256"),
            current_landing.get("visible_text_sha256"),
        ),
        ("landing.final_url", previous_landing.get("final_url"), current_landing.get("final_url")),
        (
            "attachment.sha256",
            previous_attachment.get("sha256"),
            current_attachment.get("sha256"),
        ),
        (
            "attachment.final_url",
            previous_attachment.get("final_url"),
            current_attachment.get("final_url"),
        ),
        (
            "version_signal.value",
            previous_signal.get("value"),
            current_signal.get("value"),
        ),
        (
            "version_signal.status",
            previous_signal.get("status"),
            current_signal.get("status"),
        ),
        (
            "text_contains.missing",
            previous_text_contains.get("missing"),
            current_text_contains.get("missing"),
        ),
    ]
    for name, before, after in paths:
        if before != after:
            changed_fields.append(name)

    if current.get("landing", {}).get("ok") is False or (
        current.get("attachment") and current.get("attachment", {}).get("ok") is False
    ):
        changed_fields.append("fetch_error")

    return {
        "change_status": "changed" if changed_fields else "unchanged",
        "changed_fields": changed_fields,
    }


def serialize_fetch(result: FetchResult | None) -> dict[str, Any] | None:
    if result is None:
        return None
    return {
        "url": result.url,
        "ok": result.ok,
        "final_url": result.final_url,
        "status_code": result.status_code,
        "content_type": result.content_type,
        "sha256": result.sha256,
        "visible_text_sha256": result.visible_text_sha256,
        "size_bytes": result.size_bytes,
        "error": result.error,
    }


def build_current_entry(source: dict[str, Any], landing: FetchResult, attachment: FetchResult | None) -> dict[str, Any]:
    return {
        "source_id": source.get("source_id", ""),
        "source_name": source.get("source_name", ""),
        "pack_dir": source.get("_pack_dir", ""),
        "jurisdiction": source.get("jurisdiction", ""),
        "tax_domain": source.get("tax_domain", ""),
        "source_kind": source.get("source_kind", ""),
        "document_family": source.get("document_family", ""),
        "registry_path": source.get("_registry_path", ""),
        "landing": serialize_fetch(landing),
        "attachment": serialize_fetch(attachment),
        "text_contains": evaluate_text_contains(source, landing),
        "version_signal": extract_signal_value(source, landing, attachment),
        "monitor_strategy": source.get("monitor_strategy", {}),
    }


def summarize_results(entries: list[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "total_sources": len(entries),
        "new_sources": 0,
        "changed_sources": 0,
        "unchanged_sources": 0,
        "error_sources": 0,
    }
    for item in entries:
        status = item.get("change", {}).get("change_status")
        if status == "new":
            summary["new_sources"] += 1
        elif status == "changed":
            summary["changed_sources"] += 1
        elif status == "unchanged":
            summary["unchanged_sources"] += 1
        landing_error = item.get("current", {}).get("landing", {}).get("ok") is False
        attachment = item.get("current", {}).get("attachment")
        attachment_error = isinstance(attachment, dict) and attachment.get("ok") is False
        if landing_error or attachment_error:
            summary["error_sources"] += 1
    return summary


def build_review_items(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    review_items: list[dict[str, Any]] = []
    for item in entries:
        current = item.get("current", {})
        change = item.get("change", {})
        source_id = str(current.get("source_id", "")).strip()
        if not source_id:
            continue

        landing = current.get("landing") or {}
        attachment = current.get("attachment") or {}
        signal = current.get("version_signal") or {}
        changed_fields = list(change.get("changed_fields", []))

        if landing.get("ok") is False:
            review_items.append(
                {
                    "source_id": source_id,
                    "severity": "high",
                    "issue_type": "landing_fetch_error",
                    "summary": f"Landing page fetch failed for {source_id}.",
                    "details": landing.get("error") or landing.get("status_code"),
                    "landing_url": current.get("landing", {}).get("url", ""),
                }
            )

        if attachment and attachment.get("ok") is False:
            review_items.append(
                {
                    "source_id": source_id,
                    "severity": "high",
                    "issue_type": "attachment_fetch_error",
                    "summary": f"Attachment fetch failed for {source_id}.",
                    "details": attachment.get("error") or attachment.get("status_code"),
                    "landing_url": current.get("landing", {}).get("url", ""),
                    "attachment_url": attachment.get("url", ""),
                }
            )

        if change.get("change_status") == "new":
            review_items.append(
                {
                    "source_id": source_id,
                    "severity": "medium",
                    "issue_type": "new_source",
                    "summary": f"Source {source_id} was observed for the first time.",
                    "details": current.get("source_name", ""),
                    "landing_url": current.get("landing", {}).get("url", ""),
                }
            )

        if "attachment.sha256" in changed_fields:
            review_items.append(
                {
                    "source_id": source_id,
                    "severity": "high",
                    "issue_type": "attachment_changed",
                    "summary": f"Attachment checksum changed for {source_id}.",
                    "details": signal.get("value") or signal.get("status", ""),
                    "landing_url": current.get("landing", {}).get("url", ""),
                    "attachment_url": attachment.get("url", ""),
                }
            )

        if "version_signal.value" in changed_fields:
            review_items.append(
                {
                    "source_id": source_id,
                    "severity": "high",
                    "issue_type": "version_signal_changed",
                    "summary": f"Version signal changed for {source_id}.",
                    "details": signal.get("value") or signal.get("status", ""),
                    "landing_url": current.get("landing", {}).get("url", ""),
                    "attachment_url": attachment.get("url", ""),
                }
            )

        if "landing.visible_text_sha256" in changed_fields:
            review_items.append(
                {
                    "source_id": source_id,
                    "severity": "medium",
                    "issue_type": "landing_text_changed",
                    "summary": f"Landing page visible text changed for {source_id}.",
                    "details": ", ".join(changed_fields),
                    "landing_url": current.get("landing", {}).get("url", ""),
                }
            )

        if "text_contains.missing" in changed_fields or current.get("text_contains", {}).get("missing"):
            review_items.append(
                {
                    "source_id": source_id,
                    "severity": "medium",
                    "issue_type": "expected_text_missing",
                    "summary": f"Expected landing-page text is missing for {source_id}.",
                    "details": ", ".join(current.get("text_contains", {}).get("missing", [])),
                    "landing_url": current.get("landing", {}).get("url", ""),
                }
            )

    return review_items


def build_review_markdown(review_items: list[dict[str, Any]]) -> str:
    lines = [
        "# Official Source Review Items",
        "",
    ]
    if not review_items:
        lines.extend(["- None", ""])
        return "\n".join(lines)

    for item in review_items:
        lines.extend(
            [
                f"## {item['source_id']} / {item['issue_type']}",
                "",
                f"- Severity: {item['severity']}",
                f"- Summary: {item['summary']}",
                f"- Details: {item.get('details', '') or 'n/a'}",
            ]
        )
        if item.get("landing_url"):
            lines.append(f"- Landing URL: {item['landing_url']}")
        if item.get("attachment_url"):
            lines.append(f"- Attachment URL: {item['attachment_url']}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def guess_file_extension(fetch: FetchResult) -> str:
    content_type = fetch.content_type or ""
    if content_type == "application/pdf":
        return ".pdf"
    if content_type in {"text/html", "application/xhtml+xml"}:
        return ".html"
    if content_type.startswith("text/"):
        return ".txt"

    parsed = urlparse(fetch.final_url or fetch.url)
    suffix = Path(parsed.path).suffix
    return suffix if suffix else ".bin"


def persist_attention_artifacts(
    *,
    outdir: Path,
    fetched_by_source_id: dict[str, tuple[FetchResult, FetchResult | None]],
    results: list[dict[str, Any]],
) -> dict[str, dict[str, str]]:
    artifact_root = outdir / "source_artifacts"
    saved: dict[str, dict[str, str]] = {}

    for item in results:
        current = item.get("current", {})
        change = item.get("change", {})
        source_id = str(current.get("source_id", "")).strip()
        if not source_id:
            continue

        has_attention = change.get("change_status") in {"new", "changed"}
        landing = current.get("landing") or {}
        attachment = current.get("attachment") or {}
        has_error = landing.get("ok") is False or (attachment and attachment.get("ok") is False)
        if not has_attention and not has_error:
            continue

        landing_fetch, attachment_fetch = fetched_by_source_id.get(source_id, (None, None))
        if landing_fetch is None:
            continue

        source_dir = artifact_root / slugify(source_id)
        source_dir.mkdir(parents=True, exist_ok=True)
        paths: dict[str, str] = {}

        if landing_fetch.bytes_payload is not None:
            landing_suffix = guess_file_extension(landing_fetch)
            landing_path = source_dir / f"landing{landing_suffix}"
            landing_path.write_bytes(landing_fetch.bytes_payload)
            paths["landing_path"] = str(landing_path)

        if attachment_fetch is not None and attachment_fetch.bytes_payload is not None:
            attachment_suffix = guess_file_extension(attachment_fetch)
            attachment_path = source_dir / f"attachment{attachment_suffix}"
            attachment_path.write_bytes(attachment_fetch.bytes_payload)
            paths["attachment_path"] = str(attachment_path)

        metadata_path = source_dir / "artifact_meta.json"
        metadata_path.write_text(
            json.dumps(
                {
                    "source_id": source_id,
                    "saved_at_utc": datetime.now(timezone.utc).isoformat(),
                    "landing_url": current.get("landing", {}).get("url", ""),
                    "attachment_url": current.get("attachment", {}).get("url", "") if current.get("attachment") else "",
                    **paths,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        paths["metadata_path"] = str(metadata_path)
        saved[source_id] = paths

    return saved


def candidate_profiles_for_source(source: dict[str, Any], profile_registry: list[dict[str, Any]]) -> list[dict[str, Any]]:
    jurisdiction = str(source.get("jurisdiction", "")).strip().upper()
    tax_domain = str(source.get("tax_domain", "")).strip()
    document_family = str(source.get("document_family", "")).strip()

    candidates = [
        entry
        for entry in profile_registry
        if str(entry.get("jurisdiction", "")).strip().upper() == jurisdiction
        and str(entry.get("tax_domain", "")).strip() == tax_domain
    ]
    if document_family:
        family_matches = [entry for entry in candidates if str(entry.get("family", "")).strip() == document_family]
        if family_matches:
            candidates = family_matches

    def sort_key(entry: dict[str, Any]) -> tuple[int, str]:
        stability = str(entry.get("stability", "")).strip()
        return (0 if stability == "stable" else 1, str(entry.get("name", "")))

    return sorted(candidates, key=sort_key)


def build_followups(
    *,
    results: list[dict[str, Any]],
    review_items: list[dict[str, Any]],
    artifact_paths_by_source: dict[str, dict[str, str]],
    profile_registry: list[dict[str, Any]],
    pack_dir: Path | None,
) -> list[dict[str, Any]]:
    followups: list[dict[str, Any]] = []
    review_map: dict[str, list[dict[str, Any]]] = {}
    for item in review_items:
        review_map.setdefault(str(item.get("source_id", "")).strip(), []).append(item)

    for item in results:
        current = item.get("current", {})
        change = item.get("change", {})
        source_id = str(current.get("source_id", "")).strip()
        if not source_id:
            continue

        if change.get("change_status") == "unchanged" and not review_map.get(source_id):
            continue

        artifact_paths = artifact_paths_by_source.get(source_id, {})
        source_kind = str(current.get("source_kind", "")).strip()
        profile_candidates = candidate_profiles_for_source(current, profile_registry) if source_kind == "specification" else []
        recommended_profile = profile_candidates[0] if profile_candidates else None
        attachment_path = artifact_paths.get("attachment_path", "")
        suggested_action = "manual_review_source"
        suggested_command = ""

        if recommended_profile and attachment_path and source_kind == "specification":
            suggested_action = "rerun_profile_against_downloaded_attachment"
            extractor_name = str(recommended_profile.get("name", "")).strip()
            suggested_command = (
                "python .opencode/skills/tax-law-parser/scripts/test_extractor.py "
                + (f"--pack-dir {pack_dir} " if pack_dir else "")
                + f"--pdf {attachment_path} "
                + f"--extractor {extractor_name} "
                + f"--outdir artifacts/tax-rerun/{source_id}"
            )
        elif attachment_path:
            suggested_action = "review_downloaded_attachment"
        elif artifact_paths.get("landing_path"):
            suggested_action = "review_landing_page"

        followups.append(
            {
                "source_id": source_id,
                "jurisdiction": current.get("jurisdiction", ""),
                "tax_domain": current.get("tax_domain", ""),
                "source_kind": current.get("source_kind", ""),
                "change_status": change.get("change_status", ""),
                "review_item_count": len(review_map.get(source_id, [])),
                "review_issue_types": [entry.get("issue_type", "") for entry in review_map.get(source_id, [])],
                "artifact_paths": artifact_paths,
                "profile_candidates": [
                    {
                        "name": candidate.get("name", ""),
                        "family": candidate.get("family", ""),
                        "stability": candidate.get("stability", ""),
                    }
                    for candidate in profile_candidates
                ],
                "recommended_profile": None
                if recommended_profile is None
                else {
                    "name": recommended_profile.get("name", ""),
                    "family": recommended_profile.get("family", ""),
                    "stability": recommended_profile.get("stability", ""),
                },
                "suggested_action": suggested_action,
                "suggested_command": suggested_command,
            }
        )

    return followups


def build_followup_markdown(followups: list[dict[str, Any]]) -> str:
    lines = [
        "# Source Monitor Follow-ups",
        "",
    ]
    if not followups:
        lines.extend(["- None", ""])
        return "\n".join(lines)

    for item in followups:
        lines.extend(
            [
                f"## {item['source_id']}",
                "",
                f"- Change status: {item['change_status']}",
                f"- Suggested action: {item['suggested_action']}",
                f"- Review item count: {item['review_item_count']}",
                f"- Review issue types: {', '.join(item['review_issue_types']) if item['review_issue_types'] else 'none'}",
            ]
        )
        if item.get("recommended_profile"):
            lines.append(f"- Recommended profile: {item['recommended_profile']['name']}")
        if item.get("artifact_paths", {}).get("attachment_path"):
            lines.append(f"- Downloaded attachment: {item['artifact_paths']['attachment_path']}")
        if item.get("artifact_paths", {}).get("landing_path"):
            lines.append(f"- Saved landing page: {item['artifact_paths']['landing_path']}")
        if item.get("suggested_command"):
            lines.append(f"- Suggested command: `{item['suggested_command']}`")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def build_markdown_report(snapshot: dict[str, Any], summary: dict[str, int]) -> str:
    lines = [
        "# Official Source Monitor Report",
        "",
        "## Summary",
        "",
        f"- Checked: {summary['total_sources']}",
        f"- New: {summary['new_sources']}",
        f"- Changed: {summary['changed_sources']}",
        f"- Unchanged: {summary['unchanged_sources']}",
        f"- With fetch errors: {summary['error_sources']}",
        "",
    ]

    for item in snapshot["results"]:
        current = item["current"]
        change = item["change"]
        lines.extend(
            [
                f"## {current['source_id']}",
                "",
                f"- Name: {current['source_name']}",
                f"- Jurisdiction: {current['jurisdiction']}",
                f"- Kind: {current['source_kind']}",
                f"- Change status: {change['change_status']}",
                f"- Changed fields: {', '.join(change['changed_fields']) if change['changed_fields'] else 'none'}",
                f"- Landing URL: {current['landing']['url']}",
                f"- Landing status: {current['landing']['status_code'] if current['landing']['status_code'] is not None else current['landing']['error']}",
                f"- Landing checksum: {current['landing']['sha256'] or 'n/a'}",
            ]
        )

        attachment = current.get("attachment")
        if attachment:
            lines.append(f"- Attachment URL: {attachment['url']}")
            lines.append(
                f"- Attachment status: {attachment['status_code'] if attachment['status_code'] is not None else attachment['error']}"
            )
            lines.append(f"- Attachment checksum: {attachment['sha256'] or 'n/a'}")

        signal = current.get("version_signal", {})
        lines.append(f"- Version signal: {signal.get('value') or signal.get('status', 'unknown')}")
        missing = current.get("text_contains", {}).get("missing", [])
        lines.append(f"- Missing expected landing text: {', '.join(missing) if missing else 'none'}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    args = parse_args()
    outdir = Path(args.outdir).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    pack_dir = Path(args.pack_dir).expanduser().resolve() if args.pack_dir else None

    index_path = Path(args.index).expanduser().resolve()
    entries = load_pack_source_entries(pack_dir) if pack_dir else load_registry_entries(index_path)
    filtered = filter_sources(
        entries,
        jurisdictions={item.upper() for item in args.jurisdiction},
        source_ids=set(args.source_id),
    )
    if not filtered:
        raise SystemExit("No source entries matched the requested filters.")

    previous_snapshot_path = (
        Path(args.previous_snapshot).expanduser().resolve()
        if args.previous_snapshot
        else (outdir / "latest_snapshot.json" if (outdir / "latest_snapshot.json").exists() else None)
    )
    previous_snapshot = load_previous_snapshot(previous_snapshot_path)
    previous_map = {
        item.get("current", {}).get("source_id"): item.get("current")
        for item in previous_snapshot.get("results", [])
        if isinstance(item, dict)
    }

    results: list[dict[str, Any]] = []
    fetched_by_source_id: dict[str, tuple[FetchResult, FetchResult | None]] = {}
    for source in filtered:
        landing = fetch_url(str(source.get("landing_url", "")).strip(), timeout=args.timeout)
        attachment_url = str(source.get("attachment_url", "")).strip()
        attachment = fetch_url(attachment_url, timeout=args.timeout) if attachment_url else None
        current = build_current_entry(source, landing, attachment)
        change = compare_entry(previous_map.get(current["source_id"]), current)
        results.append({"current": current, "change": change})
        fetched_by_source_id[str(current["source_id"])] = (landing, attachment)

    summary = summarize_results(results)
    review_items = build_review_items(results)
    artifact_paths_by_source = persist_attention_artifacts(
        outdir=outdir,
        fetched_by_source_id=fetched_by_source_id,
        results=results,
    )
    followups = build_followups(
        results=results,
        review_items=review_items,
        artifact_paths_by_source=artifact_paths_by_source,
        profile_registry=load_profile_registry(pack_dir=pack_dir),
        pack_dir=pack_dir,
    )
    snapshot_payload = {
        "schema_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "pack_dir": str(pack_dir) if pack_dir else "",
        "index_path": str(index_path),
        "previous_snapshot_path": str(previous_snapshot_path) if previous_snapshot_path else "",
        "summary": summary,
        "review_item_count": len(review_items),
        "followup_count": len(followups),
        "results": results,
    }

    snapshot_path = outdir / "current_snapshot.json"
    latest_path = outdir / "latest_snapshot.json"
    report_json_path = outdir / "change_report.json"
    report_md_path = outdir / "change_report.md"
    review_json_path = outdir / "review_items.json"
    review_md_path = outdir / "review_items.md"
    followup_json_path = outdir / "followups.json"
    followup_md_path = outdir / "followups.md"

    snapshot_path.write_text(json.dumps(snapshot_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    report_json_path.write_text(json.dumps(snapshot_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    report_md_path.write_text(build_markdown_report(snapshot_payload, summary), encoding="utf-8")
    review_json_path.write_text(json.dumps(review_items, ensure_ascii=False, indent=2), encoding="utf-8")
    review_md_path.write_text(build_review_markdown(review_items), encoding="utf-8")
    followup_json_path.write_text(json.dumps(followups, ensure_ascii=False, indent=2), encoding="utf-8")
    followup_md_path.write_text(build_followup_markdown(followups), encoding="utf-8")
    if not args.no_write_latest:
        latest_path.write_text(json.dumps(snapshot_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"checked: {summary['total_sources']}")
    print(f"new: {summary['new_sources']}")
    print(f"changed: {summary['changed_sources']}")
    print(f"unchanged: {summary['unchanged_sources']}")
    print(f"errors: {summary['error_sources']}")
    print(f"review_items: {len(review_items)}")
    print(f"followups: {len(followups)}")
    print(f"snapshot: {snapshot_path}")
    print(f"report_json: {report_json_path}")
    print(f"report_markdown: {report_md_path}")
    print(f"review_json: {review_json_path}")
    print(f"review_markdown: {review_md_path}")
    print(f"followup_json: {followup_json_path}")
    print(f"followup_markdown: {followup_md_path}")
    if not args.no_write_latest:
        print(f"latest: {latest_path}")

    should_fail = False
    if args.fail_on_change and (summary["new_sources"] or summary["changed_sources"]):
        should_fail = True
    if args.fail_on_error and summary["error_sources"]:
        should_fail = True
    if args.fail_on_review and review_items:
        should_fail = True
    return 2 if should_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
