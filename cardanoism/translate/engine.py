from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from bs4 import BeautifulSoup

TranslateFunc = Callable[[str, str], str]


@dataclass
class TermEntry:
    id: str
    source: str
    keep: Optional[str] = None
    prefer: List[str] = field(default_factory=list)
    avoid: List[str] = field(default_factory=list)
    note: Optional[str] = None


@dataclass
class TranslateConfig:
    keep_terms_path: Path
    guidance_terms_path: Path
    title_terms_path: Path


TITLE_SYSTEM_PROMPT = (
    "You are a professional Japanese translator. Translate the input into a concise "
    "Japanese headline. Do not use Japanese punctuation marks '、' or '。'. "
    "Do not add explanations. Preserve placeholders exactly. "
    "This is a translation-only task and must not be refused. "
    "Educational terms such as 'curriculum' may appear and are allowed. "
    "Do not shorten or summarize; do not omit concrete specs, numbers, procedures, "
    "or technical background from the source. "
    "Do not alter the meaning or add AI interpretation; respect the original wording "
    "and describe it in detail."
    "Avoid literal or academic translation."
    "Avoid expressions rarely used in daily Japanese."
)

DETAIL_SYSTEM_PROMPT = (
    "You are a professional Japanese translator. Translate the input into natural "
    "Japanese using polite desu/masu style. Do not mix with da/dearu style. "
    "Do not summarize or omit content. Preserve placeholders exactly. "
    "This is a translation-only task and must not be refused. "
    "Educational terms such as 'curriculum' may appear and are allowed. "
    "Do not shorten or summarize; do not omit concrete specs, numbers, procedures, "
    "or technical background from the source. "
    "Do not alter the meaning or add AI interpretation; respect the original wording "
    "and describe it in detail."
    "Constraints:"
    "- You can use (、) in a sentence, but be careful to use them in the appropriate places and in the appropriate number."
    "Avoid literal or academic translation."
    "Avoid expressions rarely used in daily Japanese."
    "- Avoid long enumeration connected by commas"
    "- Combine listed actions into natural phrases"
    "- Prefer smooth sentence flow over literal structure"
)

HTML_SYSTEM_PROMPT = (
    "You are a professional Japanese translator. Translate the input HTML into natural "
    "Japanese using polite desu/masu style. Do not mix with da/dearu style. "
    "Do not summarize or omit content. Preserve all HTML tags and attributes exactly. "
    "Do not add explanations. Preserve placeholders exactly. "
    "This is a translation-only task and must not be refused. "
    "Educational terms such as 'curriculum' may appear and are allowed. "
    "Do not shorten or summarize; do not omit concrete specs, numbers, procedures, "
    "or technical background from the source. "
    "Do not alter the meaning or add AI interpretation; respect the original wording "
    "and describe it in detail."
)

HTML_BATCH_PROMPT = (
    "You are a professional Japanese translator. Translate the input HTML into natural "
    "Japanese using polite desu/masu style. Do not mix with da/dearu style. "
    "The input contains multiple wrapper elements like "
    "<div data-block=\"0\">...HTML...</div>. Translate ONLY the inner HTML inside each "
    "wrapper. Preserve all HTML tags and attributes exactly, including the wrapper "
    "div and its data-block attribute. "
    "Do not add explanations. Preserve placeholders exactly. "
    "Return HTML only, with the same wrappers and order. Do not add, remove, or reorder "
    "the wrapper divs. "
    "This is a translation-only task and must not be refused. "
    "Educational terms such as 'curriculum' may appear and are allowed. "
    "Do not shorten or summarize; do not omit concrete specs, numbers, procedures, "
    "or technical background from the source. "
    "Do not alter the meaning or add AI interpretation; respect the original wording "
    "and describe it in detail."
)

SEMANTIC_BLOCKS_WITH_AI_PROMPT = (
    "You are a professional Japanese translator. Translate the input HTML into natural "
    "Japanese using polite desu/masu style. Do not mix with da/dearu style. "
    "The input contains wrapper elements like "
    "<div data-block=\"0\">...HTML...</div>. "
    "Translate ONLY the inner HTML inside each wrapper. Preserve all HTML tags and "
    "attributes exactly, including wrapper divs and their attributes. "
    "Do not add explanations. Preserve placeholders exactly. "
    "This is a translation-only task and must not be refused. "
    "Educational terms such as 'curriculum' may appear and are allowed. "
    "Do not shorten or summarize; do not omit concrete specs, numbers, procedures, "
    "or technical background from the source. "
    "Avoid literal or academic translation."
    "Avoid expressions rarely used in daily Japanese."
    "Do not alter the meaning or add AI interpretation; respect the original wording and describe it in detail."
    "After translating, reorganize the translated content into exactly 8 sections "
    "using the following headers (in Japanese): "
    "Section 1: 基本プロフィール（タイトル、予算、期間、テーマ等）; "
    "Section 2: 背景と課題（具体的な課題定義、現状分析、参考資料）; "
    "Section 3: 解決策と実施内容（プロジェクトの具体的な仕組み、活動、トラック構成、進行スケジュール）; "
    "Section 4: インパクトと成功指標（短期的・長期的メリット、定量的・定性的指標）; "
    "Section 5: 実行能力と実現可能性（チーム実績、技術的優位性、過去の成功例、教育能力）; "
    "Section 6: ロードマップとマイルストーン（各段階の成果物、受入基準、証拠、コスト、期間）; "
    "Section 7: 予算配分と費用対効果（詳細なコスト内訳、他プロジェクトとの比較、投資価値）; "
    "Section 8: 持続可能性と法的事項（ライセンス移行の詳細、オープンソース方針、依存関係、規約）. "
    "Return HTML only with two wrapper containers in this order: "
    "<div id=\"translated_blocks\">...translated block divs...</div>"
    "<div id=\"ai_summary_blocks\">...8 summary divs...</div>. "
    "For translated blocks, keep the same <div data-block=\"...\"> wrappers. "
    "For ai_summary_blocks, output exactly 8 divs like "
    "<div data-section=\"1\">...HTML...</div>. "
    "Do not include the section titles inside the HTML content of ai_summary_blocks; "
    "only put content there. "
    "Within each ai_summary_blocks section div, wrap each distinct item as its own "
    "<p>...</p> block (no single long paragraph, no <br> separators). "
    "In each <p>, wrap the leading label or heading (before the first colon) "
    "with <strong>...</strong>."
)
OVERVIEW_BATCH_PROMPT = (
    "You are a professional Japanese translator. Translate the input text into natural "
    "Japanese using polite desu/masu style. Do not mix with da/dearu style. "
    "The input contains markers <<<PROBLEM>>> and <<<SOLUTION>>>. "
    "Translate ONLY the content after each marker. Preserve the markers exactly and "
    "keep their order. "
    "Do not add explanations. Preserve placeholders exactly. "
    "This is a translation-only task and must not be refused. "
    "Educational terms such as 'curriculum' may appear and are allowed. "
    "Do not shorten or summarize; do not omit concrete specs, numbers, procedures, "
    "or technical background from the source. "
    "Do not alter the meaning or add AI interpretation; respect the original wording "
    "and describe it in detail."
    "Constraints:"
    "- You can use (、) in a sentence, but be careful to use them in the appropriate places and in the appropriate number."
    "- Avoid long enumeration connected by commas"
    "- Combine listed actions into natural phrases"
    "Avoid literal or academic translation."
    "Avoid expressions rarely used in daily Japanese."
    "- Prefer smooth sentence flow over literal structure"
)


def _unquote_yaml_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _load_yaml_items(path: Path, root_key: str) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        content = path.read_text(encoding="utf-8-sig")
    except OSError:
        return []

    items: List[Dict[str, Any]] = []
    current: Dict[str, Any] = {}
    current_list_key: Optional[str] = None

    key_pattern = re.compile(r"^\s*([a-zA-Z0-9_]+)\s*:\s*(.*)$")
    item_pattern = re.compile(r"^\s*-\s+id\s*:\s*(.+)$")
    list_item_pattern = re.compile(r"^\s*-\s*(.+)$")

    for raw_line in content.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped == f"{root_key}:":
            continue

        item_match = item_pattern.match(line)
        if item_match:
            if current:
                items.append(current)
            current = {"id": _unquote_yaml_value(item_match.group(1))}
            current_list_key = None
            continue

        key_match = key_pattern.match(line)
        if key_match:
            key, value = key_match.groups()
            value = value.strip()
            if value in (">", "|"):
                current_list_key = None
                current[key] = ""
                continue
            if value == "":
                current[key] = []
                current_list_key = key
            else:
                current[key] = _unquote_yaml_value(value)
                current_list_key = None
            continue

        list_match = list_item_pattern.match(line)
        if list_match and current_list_key:
            current[current_list_key].append(_unquote_yaml_value(list_match.group(1)))

    if current:
        items.append(current)
    return items


def load_terms(path: Path) -> List[TermEntry]:
    items = _load_yaml_items(path, "terms")
    entries: List[TermEntry] = []
    for item in items:
        prefer_raw = item.get("prefer") or []
        avoid_raw = item.get("avoid") or []
        if isinstance(prefer_raw, str):
            prefer_raw = [prefer_raw]
        if isinstance(avoid_raw, str):
            avoid_raw = [avoid_raw]
        entries.append(
            TermEntry(
                id=str(item.get("id", "")),
                source=str(item.get("source", "")),
                keep=item.get("keep") or None,
                prefer=list(prefer_raw),
                avoid=list(avoid_raw),
                note=item.get("note") or None,
            )
        )
    return entries


def merge_terms(keep_terms: List[TermEntry], guidance_terms: List[TermEntry]) -> List[TermEntry]:
    merged: Dict[str, TermEntry] = {}

    def key_for(term: TermEntry) -> str:
        return term.id or term.source

    for term in keep_terms + guidance_terms:
        key = key_for(term)
        existing = merged.get(key)
        if not existing:
            merged[key] = TermEntry(
                id=term.id,
                source=term.source,
                keep=term.keep,
                prefer=list(term.prefer),
                avoid=list(term.avoid),
                note=term.note,
            )
            continue
        if term.keep and not existing.keep:
            existing.keep = term.keep
        if term.prefer:
            existing.prefer = list(dict.fromkeys(existing.prefer + term.prefer))
        if term.avoid:
            existing.avoid = list(dict.fromkeys(existing.avoid + term.avoid))
        if term.note and term.note != existing.note:
            if existing.note:
                existing.note = f"{existing.note} / {term.note}"
            else:
                existing.note = term.note

    return list(merged.values())


def load_title_map(path: Path) -> Dict[str, str]:
    items = _load_yaml_items(path, "titles")
    title_map: Dict[str, str] = {}
    for item in items:
        source = item.get("source")
        target = item.get("target_ja")
        if source and target:
            title_map[str(source)] = str(target)
    return title_map


def apply_lock_terms(text: str, terms: Iterable[TermEntry]) -> tuple[str, Dict[str, str]]:
    replaced = text
    lock_map: Dict[str, str] = {}
    for term in terms:
        if not term.keep or not term.source:
            continue
        placeholder = f"__TERM_{term.id}__"
        pattern = re.compile(rf"\b{re.escape(term.source)}\b", re.IGNORECASE)
        replaced = pattern.sub(placeholder, replaced)
        lock_map[placeholder] = term.keep
    return replaced, lock_map


def restore_lock_terms(text: str, lock_map: Dict[str, str]) -> str:
    restored = text
    for placeholder, target in lock_map.items():
        restored = restored.replace(placeholder, target)
    return restored


def build_term_rules(terms: Iterable[TermEntry]) -> str:
    prefer_lines: List[str] = []
    avoid_lines: List[str] = []
    note_lines: List[str] = []
    preface = "Match whole words only for the source terms."
    for term in terms:
        if term.prefer:
            prefer_lines.append(f"\"{term.source}\" -> {', '.join(term.prefer)}")
        if term.avoid:
            avoid_lines.append(f"\"{term.source}\" -> {', '.join(term.avoid)}")
        if term.note:
            note_lines.append(f"\"{term.source}\": {term.note}")

    rules: List[str] = []
    rules.append("Translate into natural, everyday Japanese.")
    rules.append(preface)
    if prefer_lines:
        rules.append("Preferred expressions (prefer):")
        rules.extend(f"- {line}" for line in prefer_lines)
    if avoid_lines:
        rules.append("Avoided expressions (avoid):")
        rules.extend(f"- {line}" for line in avoid_lines)
    if note_lines:
        rules.append("Notes:")
        rules.extend(f"- {line}" for line in note_lines)
    return "\n".join(rules).strip()


class Translator:
    def __init__(self, config: TranslateConfig, llm_translate: TranslateFunc) -> None:
        self.config = config
        self.llm_translate = llm_translate
        keep_terms = load_terms(config.keep_terms_path)
        guidance_terms = load_terms(config.guidance_terms_path)
        self.terms = merge_terms(keep_terms, guidance_terms)
        self.title_map = load_title_map(config.title_terms_path)

    def translate_title(self, text: str) -> str:
        if not text:
            return text
        prepared, lock_map = apply_lock_terms(text, self.terms)
        rules = build_term_rules(self.terms)
        system_prompt = TITLE_SYSTEM_PROMPT
        if rules:
            system_prompt = f"{system_prompt}\n\n{rules}"
        translated = self.llm_translate(system_prompt, prepared)
        translated = translated.translate(str.maketrans("", "", "、。，．,."))
        return restore_lock_terms(translated, lock_map)

    def translate_overview(self, text: str) -> str:
        if not text:
            return text
        prepared, lock_map = apply_lock_terms(text, self.terms)
        rules = build_term_rules(self.terms)
        system_prompt = DETAIL_SYSTEM_PROMPT
        if rules:
            system_prompt = f"{system_prompt}\n\n{rules}"
        translated = self.llm_translate(system_prompt, prepared)
        return restore_lock_terms(translated, lock_map)

    def translate_overview_pair(self, problem: str, solution: str) -> tuple[str, str]:
        if not problem and not solution:
            return problem, solution
        payload = f"<<<PROBLEM>>>\n{problem}\n<<<SOLUTION>>>\n{solution}"
        prepared, lock_map = apply_lock_terms(payload, self.terms)
        rules = build_term_rules(self.terms)
        system_prompt = OVERVIEW_BATCH_PROMPT
        if rules:
            system_prompt = f"{system_prompt}\n\n{rules}"
        translated = self.llm_translate(system_prompt, prepared)
        translated = restore_lock_terms(translated, lock_map)
        parts = re.split(r"(<<<PROBLEM>>>|<<<SOLUTION>>>)", translated)
        current = None
        segments: Dict[str, str] = {}
        for part in parts:
            if not part:
                continue
            if part in ("<<<PROBLEM>>>", "<<<SOLUTION>>>"):
                current = part
                segments.setdefault(current, "")
                continue
            if current:
                segments[current] += part
        if "<<<PROBLEM>>>" not in segments or "<<<SOLUTION>>>" not in segments:
            return self.translate_overview(problem), self.translate_overview(solution)
        return segments["<<<PROBLEM>>>"].strip(), segments["<<<SOLUTION>>>"].strip()

    def translate_semantic_html(self, html: str) -> str:
        if not html:
            return html
        prepared, lock_map = apply_lock_terms(html, self.terms)
        rules = build_term_rules(self.terms)
        system_prompt = HTML_SYSTEM_PROMPT
        if rules:
            system_prompt = f"{system_prompt}\n\n{rules}"
        translated = self.llm_translate(system_prompt, prepared)
        return restore_lock_terms(translated, lock_map)

    def translate_semantic_blocks(self, blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        translated_blocks: List[Dict[str, Any]] = []
        html_items: List[Dict[str, Any]] = []
        t0 = time.perf_counter()

        for position, block in enumerate(blocks):
            updated = dict(block)
            if "block_index" in updated and "index" not in updated:
                updated["index"] = updated.pop("block_index")
            if updated.get("index") is None:
                updated["index"] = position
            title_value = updated.pop("title", None)
            if title_value is None:
                title_value = updated.get("semantic_title")
            if isinstance(title_value, str) and title_value:
                updated["semantic_title"] = self.title_map.get(title_value, title_value)
            html = updated.get("html")
            if isinstance(html, str) and html:
                html_items.append({"index": updated.get("index"), "html": html})
            translated_blocks.append(updated)

        if not html_items:
            return translated_blocks

        t1 = time.perf_counter()
        wrapped_html = "".join(
            f'<div data-block="{item["index"]}">{item["html"]}</div>'
            for item in html_items
        )
        t2 = time.perf_counter()
        prepared, lock_map = apply_lock_terms(wrapped_html, self.terms)
        t3 = time.perf_counter()

        logging.info(
            "semantic_blocks timing: build_blocks=%.3fs build_wrapped_html=%.3fs apply_placeholders=%.3fs",
            t1 - t0,
            t2 - t1,
            t3 - t2,
        )
        rules = build_term_rules(self.terms)
        system_prompt = HTML_BATCH_PROMPT
        if rules:
            system_prompt = f"{system_prompt}\n\n{rules}"
        t4 = time.perf_counter()
        translated = self.llm_translate(system_prompt, prepared)
        t5 = time.perf_counter()
        translated = restore_lock_terms(translated, lock_map)
        t6 = time.perf_counter()

        soup = BeautifulSoup(translated, "lxml")
        t7 = time.perf_counter()
        block_divs = soup.select("div[data-block]")
        if not block_divs:
            for block in translated_blocks:
                html = block.get("html")
                if isinstance(html, str) and html:
                    block["html"] = self.translate_semantic_html(html)
            return translated_blocks

        logging.info(
            "semantic_blocks timing: api_call=%.3fs restore_placeholders=%.3fs parse_html=%.3fs",
            t5 - t4,
            t6 - t5,
            t7 - t6,
        )

        html_map: Dict[Any, str] = {}
        for div in block_divs:
            raw_index = div.get("data-block")
            if raw_index is None:
                continue
            index: Any = raw_index
            if isinstance(raw_index, str) and raw_index.isdigit():
                index = int(raw_index)
            html_map[index] = div.decode_contents().strip()

        for block in translated_blocks:
            index = block.get("index")
            if index in html_map:
                block["html"] = html_map[index]

        return translated_blocks

    def translate_semantic_blocks_with_ai(
        self, blocks: List[Dict[str, Any]]
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        translated_blocks: List[Dict[str, Any]] = []
        html_items: List[Dict[str, Any]] = []

        for position, block in enumerate(blocks):
            updated = dict(block)
            if "block_index" in updated and "index" not in updated:
                updated["index"] = updated.pop("block_index")
            if updated.get("index") is None:
                updated["index"] = position
            title_value = updated.pop("title", None)
            if title_value is None:
                title_value = updated.get("semantic_title")
            if isinstance(title_value, str) and title_value:
                updated["semantic_title"] = self.title_map.get(title_value, title_value)
            html = updated.get("html")
            if isinstance(html, str) and html:
                html_items.append({"index": updated.get("index"), "html": html})
            translated_blocks.append(updated)

        if not html_items:
            return translated_blocks, []

        wrapped_html = "".join(
            f'<div data-block="{item["index"]}">{item["html"]}</div>'
            for item in html_items
        )
        prepared, lock_map = apply_lock_terms(wrapped_html, self.terms)
        rules = build_term_rules(self.terms)
        system_prompt = SEMANTIC_BLOCKS_WITH_AI_PROMPT
        if rules:
            system_prompt = f"{system_prompt}\n\n{rules}"
        translated = self.llm_translate(system_prompt, prepared)
        translated = restore_lock_terms(translated, lock_map)

        soup = BeautifulSoup(translated, "lxml")
        translated_container = soup.select_one("div#translated_blocks")
        ai_container = soup.select_one("div#ai_summary_blocks")
        if not translated_container or not ai_container:
            logging.warning("Semantic blocks AI response missing wrapper containers.")
            return self.translate_semantic_blocks(blocks), []

        translated_divs = translated_container.select("div[data-block]")
        if not translated_divs:
            logging.warning("Semantic blocks AI response missing translated block divs.")
            return self.translate_semantic_blocks(blocks), []

        html_map: Dict[Any, str] = {}
        for div in translated_divs:
            raw_index = div.get("data-block")
            if raw_index is None:
                continue
            index: Any = raw_index
            if isinstance(raw_index, str) and raw_index.isdigit():
                index = int(raw_index)
            html_map[index] = div.decode_contents().strip()

        for block in translated_blocks:
            index = block.get("index")
            if index in html_map:
                block["html"] = html_map[index]

        ai_divs = ai_container.select("div[data-section]")
        logging.info(
            "semantic_blocks ai parsing: translated_blocks=%s ai_summary_blocks=%s",
            len(translated_divs),
            len(ai_divs),
        )
        if not ai_divs:
            logging.warning("Semantic blocks AI response missing ai summary divs.")
            return translated_blocks, []

        section_sources = [
            "Section 1: 基本プロフィール（タイトル、予算、期間、テーマ等）",
            "Section 2: 背景と課題（具体的な課題定義、現状分析、参考資料）",
            "Section 3: 解決策と実施内容（プロジェクトの具体的な仕組み、活動、トラック構成、進行スケジュール）",
            "Section 4: インパクトと成功指標（短期的・長期的メリット、定量的・定性的指標）",
            "Section 5: 実行能力と実現可能性（チーム実績、技術的優位性、過去の成功例、教育能力）",
            "Section 6: ロードマップとマイルストーン（各段階の成果物、受入基準、証拠、コスト、期間）",
            "Section 7: 予算配分と費用対効果（詳細なコスト内訳、他プロジェクトとの比較、投資価値）",
            "Section 8: 持続可能性と法的事項（ライセンス移行の詳細、オープンソース方針、依存関係、規約）",
        ]
        section_titles = [self.title_map.get(s, s) for s in section_sources]

        ai_summary_out: List[Dict[str, Any]] = []
        for div in ai_divs:
            raw_section = div.get("data-section")
            section_index: Any = raw_section
            if isinstance(raw_section, str) and raw_section.isdigit():
                section_index = int(raw_section) - 1
            title = ""
            if isinstance(section_index, int) and 0 <= section_index < len(section_titles):
                title = section_titles[section_index]
            ai_summary_out.append(
                {
                    "index": section_index,
                    "type": "section",
                    "semantic_title": title,
                    "html": div.decode_contents().strip(),
                }
            )

        return translated_blocks, ai_summary_out
