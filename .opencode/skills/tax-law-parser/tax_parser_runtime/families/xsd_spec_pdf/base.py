from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re


@dataclass
class XsdSpecPdfConfig:
    profile_name: str
    start_element_name: str = "Comprobante"
    root_path: str = "/Comprobante"
    element_path_overrides: dict[str, str] = field(default_factory=dict)
    element_heading_pattern: re.Pattern[str] = field(
        default_factory=lambda: re.compile(r"^Elemento:\s*(.+)$", re.IGNORECASE)
    )
    attribute_heading_pattern: re.Pattern[str] = field(
        default_factory=lambda: re.compile(r"^Atributos?:?$", re.IGNORECASE)
    )
    description_heading_pattern: re.Pattern[str] = field(
        default_factory=lambda: re.compile(r"^Descripción(?:\s+(.*))?$", re.IGNORECASE)
    )
    child_elements_heading_pattern: re.Pattern[str] = field(
        default_factory=lambda: re.compile(r"^Elementos Hijo \(min,max\)$", re.IGNORECASE)
    )
    attribute_name_pattern: re.Pattern[str] = field(
        default_factory=lambda: re.compile(r"^[A-Za-zÁÉÍÓÚÑáéíóúñ][A-Za-zÁÉÍÓÚÑáéíóúñ0-9]+$")
    )
    usage_pattern: re.Pattern[str] = field(
        default_factory=lambda: re.compile(r"^Uso\s+(.+)$", re.IGNORECASE)
    )
    type_pattern: re.Pattern[str] = field(
        default_factory=lambda: re.compile(r"^Tipo\s+(?:Base|Especial)\s+(.+)$", re.IGNORECASE)
    )
    prefixed_value_pattern: re.Pattern[str] = field(
        default_factory=lambda: re.compile(r"^Valor Prefijado\s+(.+)$", re.IGNORECASE)
    )
    value_set_pattern: re.Pattern[str] = field(
        default_factory=lambda: re.compile(r"^Valores Permitidos\s+(.+)$", re.IGNORECASE)
    )
    fixed_length_pattern: re.Pattern[str] = field(
        default_factory=lambda: re.compile(r"^Longitud\s+(.+)$", re.IGNORECASE)
    )
    min_length_pattern: re.Pattern[str] = field(
        default_factory=lambda: re.compile(r"^Longitud Mínima\s+(.+)$", re.IGNORECASE)
    )
    max_length_pattern: re.Pattern[str] = field(
        default_factory=lambda: re.compile(r"^Longitud Máxima\s+(.+)$", re.IGNORECASE)
    )
    decimal_pattern: re.Pattern[str] = field(
        default_factory=lambda: re.compile(r"^Posiciones Decimales\s+(.+)$", re.IGNORECASE)
    )
    rule_patterns: tuple[re.Pattern[str], ...] = field(
        default_factory=lambda: (
            re.compile(r"^Valor Mínimo Incluyente\s+(.+)$", re.IGNORECASE),
            re.compile(r"^Valor Máximo Incluyente\s+(.+)$", re.IGNORECASE),
            re.compile(r"^Espacio en Blanco\s+(.+)$", re.IGNORECASE),
            re.compile(r"^Patrón\s+(.+)$", re.IGNORECASE),
        )
    )
    stop_patterns: tuple[re.Pattern[str], ...] = field(
        default_factory=lambda: (
            re.compile(r"^Secuencia de Formación:$", re.IGNORECASE),
            re.compile(r"^Generación del Sello Digital$", re.IGNORECASE),
            re.compile(r"^[A-Z]\.\s+Estándar del servicio de cancelación\.$", re.IGNORECASE),
            re.compile(r"^[A-Z]\.\s+Especificación técnica del código de barras", re.IGNORECASE),
            re.compile(r"^[A-Z]\.\s+Secuencia de formación", re.IGNORECASE),
            re.compile(r"^[A-Z]\.\s+Validaciones adicionales", re.IGNORECASE),
        )
    )
    ignore_line_patterns: tuple[re.Pattern[str], ...] = field(
        default_factory=lambda: (
            re.compile(r"^DIARIO OFICIAL\b", re.IGNORECASE),
            re.compile(r"^[A-Za-zÁÉÍÓÚÑáéíóúñ]+\s+\d{1,2}\s+de\s+[A-Za-zÁÉÍÓÚÑáéíóúñ]+\s+de\s+\d{4}\s+DIARIO OFICIAL$", re.IGNORECASE),
            re.compile(r"^Estructura$", re.IGNORECASE),
            re.compile(r"^Elementos$", re.IGNORECASE),
            re.compile(r"^Diagrama$", re.IGNORECASE),
            re.compile(r"^Código Fuente$", re.IGNORECASE),
            re.compile(r"^Secuencia\s*\(.*\).*$", re.IGNORECASE),
        )
    )


@dataclass
class _LineEntry:
    page_number: int
    text: str


@dataclass
class _AttributeState:
    name: str
    element_name: str
    element_path: str
    element_description: str
    source_pages: set[int]
    description_lines: list[str] = field(default_factory=list)
    usage_text: str = ""
    data_type: str = ""
    sample_value: str = ""
    value_set_lines: list[str] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    min_char_length: str = ""
    max_char_length: str = ""
    min_decimal_precision: str = ""
    max_decimal_precision: str = ""
    active_slot: str = ""


class XsdSpecPdfParser:
    def __init__(self, config: XsdSpecPdfConfig) -> None:
        self.config = config

    def extract(self, pdf_path: Path) -> list[dict[str, object]]:
        entries = self.read_line_entries(pdf_path)
        records: list[dict[str, object]] = []
        seen_field_ids: dict[str, int] = {}
        started = False
        occurrence_counts: dict[str, int] = {}
        current_element_name = ""
        current_element_path = ""
        current_element_description: list[str] = []
        in_attribute_section = False
        current_attribute: _AttributeState | None = None

        for entry in entries:
            line = entry.text

            if not started:
                match = self.config.element_heading_pattern.match(line)
                if not match:
                    continue
                name = match.group(1).strip()
                if name != self.config.start_element_name:
                    continue
                started = True
                occurrence = occurrence_counts.get(name, 0) + 1
                occurrence_counts[name] = occurrence
                current_element_name = name
                current_element_path = self._resolve_element_path(name, occurrence)
                current_element_description = []
                in_attribute_section = False
                continue

            if self._matches_any(self.config.stop_patterns, line):
                break
            if self._matches_any(self.config.ignore_line_patterns, line):
                continue

            match = self.config.element_heading_pattern.match(line)
            if match:
                current_attribute = self._flush_attribute(records, seen_field_ids, current_attribute)
                name = match.group(1).strip()
                occurrence = occurrence_counts.get(name, 0) + 1
                occurrence_counts[name] = occurrence
                current_element_name = name
                current_element_path = self._resolve_element_path(name, occurrence)
                current_element_description = []
                in_attribute_section = False
                continue

            if self.config.child_elements_heading_pattern.match(line):
                current_attribute = self._flush_attribute(records, seen_field_ids, current_attribute)
                in_attribute_section = False
                continue

            if self.config.attribute_heading_pattern.match(line):
                current_attribute = self._flush_attribute(records, seen_field_ids, current_attribute)
                in_attribute_section = True
                continue

            description_match = self.config.description_heading_pattern.match(line)
            if description_match:
                content = (description_match.group(1) or "").strip()
                if current_attribute is not None:
                    current_attribute.active_slot = "description"
                    current_attribute.source_pages.add(entry.page_number)
                    if content:
                        current_attribute.description_lines.append(content)
                else:
                    in_attribute_section = False
                    if content:
                        current_element_description.append(content)
                continue

            if current_attribute is not None and self._apply_attribute_property(current_attribute, line, entry.page_number):
                continue

            if in_attribute_section:
                if self.config.attribute_name_pattern.fullmatch(line):
                    current_attribute = self._flush_attribute(records, seen_field_ids, current_attribute)
                    current_attribute = _AttributeState(
                        name=line,
                        element_name=current_element_name,
                        element_path=current_element_path,
                        element_description=self._collapse_lines(current_element_description),
                        source_pages={entry.page_number},
                    )
                    continue

                if current_attribute is not None:
                    self._append_attribute_continuation(current_attribute, line, entry.page_number)
                    continue

            if current_attribute is None and current_element_name:
                current_element_description.append(line)

        self._flush_attribute(records, seen_field_ids, current_attribute)
        return records

    def read_line_entries(self, pdf_path: Path) -> list[_LineEntry]:
        import pdfplumber

        entries: list[_LineEntry] = []
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                for raw_line in text.splitlines():
                    line = raw_line.replace("\xa0", " ").strip()
                    if line:
                        entries.append(_LineEntry(page_number=int(page.page_number), text=line))
        return entries

    def read_text_lines(self, pdf_path: Path) -> list[str]:
        return [entry.text for entry in self.read_line_entries(pdf_path)]

    def looks_like_xsd_spec_pdf(self, pdf_path: Path, *, max_lines: int = 400) -> bool:
        lines = self.read_text_lines(pdf_path)[:max_lines]
        hits = 0
        for line in lines:
            if self.config.element_heading_pattern.search(line):
                hits += 2
            if self.config.attribute_heading_pattern.search(line):
                hits += 1
            if self.config.description_heading_pattern.search(line):
                hits += 1
            if self.config.usage_pattern.search(line):
                hits += 1
            if self.config.type_pattern.search(line):
                hits += 1
        return hits >= 6

    def _resolve_element_path(self, name: str, occurrence: int) -> str:
        key = f"{name}#{occurrence}"
        if key in self.config.element_path_overrides:
            return self.config.element_path_overrides[key]
        if name in self.config.element_path_overrides:
            return self.config.element_path_overrides[name]
        if occurrence == 1 and name == self.config.start_element_name:
            return self.config.root_path
        return f"{self.config.root_path}/{name}"

    def _apply_attribute_property(self, state: _AttributeState, line: str, page_number: int) -> bool:
        usage_match = self.config.usage_pattern.match(line)
        if usage_match:
            state.usage_text = usage_match.group(1).strip()
            state.active_slot = "usage"
            state.source_pages.add(page_number)
            return True

        type_match = self.config.type_pattern.match(line)
        if type_match:
            state.data_type = type_match.group(1).strip()
            state.active_slot = "data_type"
            state.source_pages.add(page_number)
            return True

        prefixed_match = self.config.prefixed_value_pattern.match(line)
        if prefixed_match:
            state.sample_value = prefixed_match.group(1).strip()
            state.active_slot = "sample_value"
            state.source_pages.add(page_number)
            return True

        value_set_match = self.config.value_set_pattern.match(line)
        if value_set_match:
            state.value_set_lines = [value_set_match.group(1).strip()]
            state.active_slot = "value_set"
            state.source_pages.add(page_number)
            return True

        min_length_match = self.config.min_length_pattern.match(line)
        if min_length_match:
            state.min_char_length = min_length_match.group(1).strip()
            state.active_slot = ""
            state.source_pages.add(page_number)
            return True

        max_length_match = self.config.max_length_pattern.match(line)
        if max_length_match:
            state.max_char_length = max_length_match.group(1).strip()
            state.active_slot = ""
            state.source_pages.add(page_number)
            return True

        fixed_length_match = self.config.fixed_length_pattern.match(line)
        if fixed_length_match:
            length = fixed_length_match.group(1).strip()
            state.min_char_length = length
            state.max_char_length = length
            state.active_slot = ""
            state.source_pages.add(page_number)
            return True

        decimal_match = self.config.decimal_pattern.match(line)
        if decimal_match:
            precision = decimal_match.group(1).strip()
            state.max_decimal_precision = precision
            state.active_slot = ""
            state.source_pages.add(page_number)
            return True

        for pattern in self.config.rule_patterns:
            rule_match = pattern.match(line)
            if rule_match:
                self._append_unique(state.rules, line.strip())
                state.active_slot = "rule"
                state.source_pages.add(page_number)
                return True

        return False

    def _append_attribute_continuation(self, state: _AttributeState, line: str, page_number: int) -> None:
        state.source_pages.add(page_number)
        if state.active_slot == "description":
            state.description_lines.append(line)
            return
        if state.active_slot == "usage":
            state.usage_text = self._join_text(state.usage_text, line)
            return
        if state.active_slot == "sample_value":
            state.sample_value = self._join_text(state.sample_value, line)
            return
        if state.active_slot == "value_set":
            state.value_set_lines.append(line)
            return
        if state.active_slot == "rule" and state.rules:
            state.rules[-1] = self._join_text(state.rules[-1], line)
            return

    def _flush_attribute(
        self,
        records: list[dict[str, object]],
        seen_field_ids: dict[str, int],
        state: _AttributeState | None,
    ) -> _AttributeState | None:
        if state is None:
            return None

        base_field_id = f"{state.element_path}/@{state.name}"
        field_id = base_field_id
        duplicate_index = seen_field_ids.get(base_field_id, 0)
        if duplicate_index:
            field_id = f"{base_field_id}#{duplicate_index + 1}"
        seen_field_ids[base_field_id] = duplicate_index + 1

        value_set = self._collapse_lines(state.value_set_lines)
        note_on_use = state.usage_text.strip()
        record = {
            "field_id": field_id,
            "field_name": state.name.strip(),
            "field_description": self._collapse_lines(state.description_lines),
            "note_on_use": note_on_use,
            "data_type": state.data_type.strip(),
            "cardinality": self._usage_to_cardinality(note_on_use),
            "invoice_path": base_field_id,
            "credit_note_path": "",
            "report_path": base_field_id,
            "sample_value": state.sample_value.strip(),
            "value_set": value_set,
            "interpretation": state.element_description.strip(),
            "rules": list(state.rules),
            "source_pages": sorted(state.source_pages),
            "min_char_length": state.min_char_length.strip(),
            "max_char_length": state.max_char_length.strip(),
            "min_decimal_precision": state.min_decimal_precision.strip(),
            "max_decimal_precision": state.max_decimal_precision.strip(),
            "extractor_name": self.config.profile_name,
        }
        records.append(record)
        return None

    def _usage_to_cardinality(self, usage_text: str) -> str:
        normalized = usage_text.lower()
        if "requerido" in normalized:
            return "1..1"
        if "opcional" in normalized or "condicional" in normalized:
            return "0..1"
        return ""

    def _matches_any(self, patterns: tuple[re.Pattern[str], ...], value: str) -> bool:
        return any(pattern.search(value) for pattern in patterns)

    def _collapse_lines(self, lines: list[str]) -> str:
        return " ".join(part.strip() for part in lines if part.strip()).strip()

    def _append_unique(self, items: list[str], value: str) -> None:
        if value not in items:
            items.append(value)

    def _join_text(self, current: str, extra: str) -> str:
        current = current.strip()
        extra = extra.strip()
        if not current:
            return extra
        if not extra:
            return current
        return f"{current} {extra}"
