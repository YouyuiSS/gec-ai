from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from dataclasses import asdict

from .models import Evidence, ExtractionBundle, FieldDefinition


class NoopLLMEnricher:
    def enrich(self, parsed, partial: ExtractionBundle) -> ExtractionBundle:
        return partial


class FieldEnrichmentUpdateModelMixin:
    @staticmethod
    def _load_langchain_dependencies():
        try:
            from langchain.chat_models import init_chat_model
            from pydantic import BaseModel, Field
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "LangChain structured enrichment requires langchain and pydantic. Install requirements.txt first."
            ) from exc
        return init_chat_model, BaseModel, Field

    @classmethod
    def build_schema(cls):
        _, BaseModel, Field = cls._load_langchain_dependencies()

        class FieldEnrichmentUpdate(BaseModel):
            field_code: str = Field(description="Field code to update, for example BT-1.")
            semantic_notes: str | None = Field(
                default=None,
                description="Short business meaning grounded in the supplied source excerpts.",
            )
            format_hint: str | None = Field(
                default=None,
                description="Formatting or lexical hint that is explicit in the excerpts, for example YYYY-MM-DD.",
            )
            sample_value: str | None = Field(
                default=None,
                description="Example value only when the excerpts contain one clearly.",
            )
            value_set_refs: list[str] = Field(
                default_factory=list,
                description="Exact code list references or explicit allowed values from the excerpts.",
            )
            confidence: float = Field(
                default=0.7,
                ge=0.0,
                le=1.0,
                description="Confidence in the proposed update.",
            )
            evidence_page_numbers: list[int] = Field(
                default_factory=list,
                description="Page numbers from the supplied excerpts that support this update.",
            )

        class FieldEnrichmentBatch(BaseModel):
            field_updates: list[FieldEnrichmentUpdate] = Field(
                default_factory=list,
                description="Field metadata updates supported by the supplied excerpts.",
            )

        return FieldEnrichmentBatch


class LangChainStructuredEnricher(FieldEnrichmentUpdateModelMixin):
    def __init__(
        self,
        model: str | None = None,
        model_provider: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        max_fields_per_batch: int = 8,
        max_candidate_fields: int = 24,
    ) -> None:
        env_model = model or os.getenv("TAX_PIPELINE_LLM_MODEL") or os.getenv("OPENAI_MODEL")
        inferred_provider, normalized_model = self._resolve_provider_and_model(env_model)
        self.model = normalized_model
        self.model_provider = model_provider or inferred_provider
        self.base_url = base_url or (os.getenv("OPENAI_BASE_URL") if self.model_provider == "openai" else None)
        self.api_key = api_key or (os.getenv("OPENAI_API_KEY") if self.model_provider == "openai" else None)
        self.prefer_raw_json = bool(
            self.model_provider == "openai"
            and self.base_url
            and any(host in self.base_url for host in ("127.0.0.1", "localhost"))
        )
        self.max_fields_per_batch = 1 if self.prefer_raw_json else max(1, max_fields_per_batch)
        self.max_candidate_fields = max(1, max_candidate_fields)
        self._schema = self.build_schema()

    def enrich(self, parsed, partial: ExtractionBundle) -> ExtractionBundle:
        if not self.model:
            raise RuntimeError(
                "LangChain enrichment is enabled but no model was provided. "
                "Set --llm-model, TAX_PIPELINE_LLM_MODEL, or OPENAI_MODEL."
            )

        candidates = self._select_candidates(partial.fields)
        if not candidates:
            return partial

        bundle = deepcopy(partial)
        field_map = {field.field_code: field for field in bundle.fields}
        raw_model, structured_model = self._build_models()

        for batch in self._batched(candidates):
            prompt = self._build_prompt(parsed=parsed, bundle=bundle, fields=batch)
            response = self._invoke_batch(
                raw_model=raw_model,
                structured_model=structured_model,
                prompt=prompt,
            )
            for update in response.field_updates:
                field = field_map.get(update.field_code)
                if field is None:
                    continue
                self._apply_update(field=field, update=update, parsed=parsed)

        return bundle

    def _build_models(self):
        init_chat_model, _, _ = self._load_langchain_dependencies()
        try:
            kwargs = {
                "model": self.model,
                "temperature": 0,
                "max_tokens": 400,
            }
            if self.model_provider:
                kwargs["model_provider"] = self.model_provider
            if self.model_provider == "openai":
                kwargs["reasoning_effort"] = "minimal"
                kwargs["timeout"] = 90
                if self.base_url:
                    kwargs["base_url"] = self.base_url
                if self.api_key:
                    kwargs["api_key"] = self.api_key
            model = init_chat_model(**kwargs)
            return model, model.with_structured_output(self._schema)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "Failed to initialize the LangChain chat model. "
                "Check --llm-model / TAX_PIPELINE_LLM_MODEL / OPENAI_MODEL and the provider integration package."
            ) from exc

    def _invoke_batch(self, raw_model, structured_model, prompt: str):
        if self.prefer_raw_json:
            return self._invoke_with_json_fallback(raw_model=raw_model, prompt=prompt)
        try:
            return structured_model.invoke(prompt)
        except Exception:  # noqa: BLE001
            return self._invoke_with_json_fallback(raw_model=raw_model, prompt=prompt)

    def _invoke_with_json_fallback(self, raw_model, prompt: str):
        repair_prompt = (
            prompt
            + "\n\nReturn JSON only. Do not use markdown fences. "
            + "The top-level object must be {\"field_updates\": [...]}."
            + " If a current value is clearly a placeholder or low-confidence extraction artifact, replace it."
            + " Prefer at least one update when the supplied evidence supports a better value."
        )
        response = raw_model.invoke(repair_prompt)
        content = getattr(response, "content", response)
        payload = self._parse_json_payload(content)
        return self._schema.model_validate(payload)

    def _parse_json_payload(self, content) -> dict[str, object]:
        text = self._coerce_response_text(content)
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
            text = text.strip()

        payload = json.loads(text)
        if isinstance(payload, dict) and "updates" in payload and "field_updates" not in payload:
            payload["field_updates"] = payload.pop("updates")
        return payload

    def _coerce_response_text(self, content) -> str:
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            fragments: list[str] = []
            for item in content:
                if isinstance(item, str):
                    fragments.append(item)
                    continue
                if isinstance(item, dict):
                    if isinstance(item.get("text"), str):
                        fragments.append(item["text"])
                        continue
                    if item.get("type") == "text" and isinstance(item.get("content"), str):
                        fragments.append(item["content"])
                        continue
            return "\n".join(fragment for fragment in fragments if fragment)

        return str(content)

    @staticmethod
    def _resolve_provider_and_model(model: str | None) -> tuple[str | None, str | None]:
        if not model:
            return ("openai", os.getenv("OPENAI_MODEL")) if os.getenv("OPENAI_MODEL") else (None, None)

        if ":" in model:
            provider, bare_model = model.split(":", 1)
            if provider and bare_model:
                return provider, bare_model

        if os.getenv("OPENAI_MODEL") == model or os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_KEY"):
            return "openai", model

        return None, model

    def _select_candidates(self, fields: list[FieldDefinition]) -> list[FieldDefinition]:
        prioritized = sorted(
            (
                field
                for field in fields
                if field.field_kind == "atomic"
                and (
                    field.origin == "inferred"
                    or self._semantic_notes_missing(field)
                    or self._sample_value_suspicious(field)
                    or (
                        not field.constraints.format_hint
                        and (field.data_type or "").lower() in {
                            "identifier",
                            "date",
                            "datetime",
                            "time",
                            "code",
                            "amount",
                            "quantity",
                            "percentage",
                            "boolean",
                        }
                    )
                )
            ),
            key=lambda field: (
                0 if self._semantic_notes_missing(field) else 1,
                0 if field.origin == "explicit" else 1,
                0 if self._sample_value_suspicious(field) else 1,
                field.confidence,
                field.field_code,
            ),
        )
        return prioritized[: self.max_candidate_fields]

    def _batched(self, fields: list[FieldDefinition]):
        for index in range(0, len(fields), self.max_fields_per_batch):
            yield fields[index : index + self.max_fields_per_batch]

    def _build_prompt(self, parsed, bundle: ExtractionBundle, fields: list[FieldDefinition]) -> str:
        blocks = []
        for field in fields:
            blocks.append(
                {
                    "field": self._field_payload(field),
                    "source_excerpts": self._source_excerpts(parsed=parsed, field=field),
                }
            )

        prompt_payload = {
            "document": {
                "jurisdiction": bundle.document.jurisdiction,
                "tax_domain": bundle.document.tax_domain,
                "language_code": bundle.document.language_code,
                "version_label": bundle.document.version_label,
            },
            "instructions": [
                "Use only the supplied source excerpts.",
                "Return updates only when the excerpts support them directly.",
                "Do not invent code lists, examples, or formatting hints.",
                "Keep semantic_notes concise and business-facing.",
                "Preserve existing values by returning null or an empty list when no improvement is justified.",
            ],
            "fields": blocks,
        }
        return json.dumps(prompt_payload, ensure_ascii=False, indent=2)

    def _field_payload(self, field: FieldDefinition) -> dict[str, object]:
        payload = asdict(field)
        payload = {
            "field_code": payload["field_code"],
            "field_name": payload["field_name"],
            "field_description": payload["field_description"],
            "data_type": payload["data_type"],
            "sample_value": payload["sample_value"],
            "value_set_refs": payload["value_set_refs"],
            "semantic_notes": payload["semantic_notes"],
            "paths": payload["paths"],
            "origin": payload["origin"],
            "confidence": payload["confidence"],
        }
        if self._semantic_notes_missing(field):
            payload["semantic_notes"] = None
        if self._sample_value_suspicious(field):
            payload["sample_value"] = None
        payload["evidence"] = [
            {
                "page_number": item.page_number,
                "source_kind": item.source_kind,
                "section_title": item.section_title,
                "quote_text": item.quote_text[:280],
            }
            for item in field.evidence[:3]
        ]
        return payload

    def _source_excerpts(self, parsed, field: FieldDefinition) -> list[dict[str, object]]:
        page_numbers = self._field_page_numbers(parsed=parsed, field=field)
        excerpts: list[dict[str, object]] = []
        for page_number in page_numbers:
            page = next((page for page in parsed.pages if page.page_number == page_number), None)
            if page is None:
                continue
            excerpts.append(
                {
                    "page_number": page_number,
                    "excerpt": self._extract_relevant_excerpt(page.text, field.field_code),
                }
            )
        return excerpts

    def _field_page_numbers(self, parsed, field: FieldDefinition) -> list[int]:
        page_numbers = []
        for evidence in field.evidence:
            if evidence.page_number not in page_numbers:
                page_numbers.append(evidence.page_number)

        if not page_numbers:
            for page in parsed.pages:
                if field.field_code in page.text and page.page_number not in page_numbers:
                    page_numbers.append(page.page_number)

        return page_numbers[:3] or [1]

    def _extract_relevant_excerpt(self, text: str, anchor: str) -> str:
        normalized = re.sub(r"\s+", " ", text).strip()
        if not normalized:
            return ""

        match = re.search(re.escape(anchor), normalized)
        if not match:
            return normalized[:700]

        start = max(0, match.start() - 240)
        end = min(len(normalized), match.end() + 620)
        return normalized[start:end]

    def _apply_update(self, field: FieldDefinition, update, parsed) -> None:
        if update.semantic_notes and (self._semantic_notes_missing(field) or field.origin == "inferred"):
            field.semantic_notes = update.semantic_notes.strip()

        if update.format_hint and not field.constraints.format_hint:
            field.constraints.format_hint = update.format_hint.strip()

        if update.sample_value and (not field.sample_value or self._sample_value_suspicious(field)):
            field.sample_value = update.sample_value.strip()

        if update.value_set_refs:
            merged_refs = list(field.value_set_refs)
            for value in update.value_set_refs:
                normalized = value.strip()
                if normalized and normalized not in merged_refs:
                    merged_refs.append(normalized)
            field.value_set_refs = merged_refs

        if update.confidence is not None:
            field.confidence = max(field.confidence, float(update.confidence))

        if update.evidence_page_numbers:
            self._append_llm_evidence(
                field=field,
                parsed=parsed,
                page_numbers=update.evidence_page_numbers,
            )

    def _append_llm_evidence(self, field: FieldDefinition, parsed, page_numbers: list[int]) -> None:
        existing_keys = {(item.page_number, item.source_kind, item.quote_text) for item in field.evidence}
        for page_number in page_numbers[:2]:
            page = next((item for item in parsed.pages if item.page_number == page_number), None)
            if page is None:
                continue
            quote_text = self._extract_relevant_excerpt(page.text, field.field_code)[:280]
            evidence = Evidence(
                page_number=page_number,
                source_kind="llm_page_excerpt",
                quote_text=quote_text,
                section_title=None,
            )
            key = (evidence.page_number, evidence.source_kind, evidence.quote_text)
            if key not in existing_keys:
                field.evidence.append(evidence)
                existing_keys.add(key)

    @staticmethod
    def _semantic_notes_missing(field: FieldDefinition) -> bool:
        notes = (field.semantic_notes or "").strip()
        return not notes or notes == "Recovered from rule reference fallback."

    @staticmethod
    def _sample_value_suspicious(field: FieldDefinition) -> bool:
        sample = (field.sample_value or "").strip()
        if not sample:
            return False
        if field.origin == "inferred" and sample.lower() in {"true", "false"}:
            return True
        if field.field_name.lower().endswith("code on invoice item") and sample.lower() in {"true", "false"}:
            return True
        return False
