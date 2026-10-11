"""Excerpt-bound explanations shared by maps and paragraph lenses.

No generation occurs during segment projection. Valid references are merely
locatable evidence; all local and model interpretations remain unreviewed.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Callable

from fields_study_flow import explanation_provider as transport

__all__ = ["prepare_explanations", "explain_segment"]

MAX_FILES = 16
MAX_CHUNKS = 64
MAX_CLAIMS = 64
MAX_CHUNK_BYTES = 4096
MAX_INPUT_BYTES = 48_000
_NUMBERS = re.compile(r"(?<![\d.])[+\-\u2212]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)"
                     r"(?:[eE][+-]?\d+)?(?:[ \t]*[%\u2030\uff05])?")
_UNSAFE = re.compile(r"(?i)(?:<[!/]?[a-z]|javascript\s*:|file://|https?://|"
                     r"[a-z]:[\\/]|\\\\[^\s]+|(?:^|\s)/(?:[^\s/]+/)+[^\s]*)")
_SECRET_FIELD = re.compile(r"(?i)^(?:api[_-]?key|access[_-]?token|refresh[_-]?token|token|password|secret|authorization)$")
_SECRET_TEXT = re.compile(r"(?i)\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|token|password|secret|authorization)"
                          r"[\"']?\s*[:=]\s*\S+|\bBearer\s+\S+|\bsk-[a-z0-9_-]{12,}\b")
_LOCATOR_KEYS = {"page", "section", "symbol", "line_start", "line_end", "cell_id", "json_pointer", "row", "column"}
_TERMS = (
    (r"\bself[- ]attention\b", "Self-attention", "自注意力：同一序列内的元素彼此比较。", "Self-attention compares elements within the same sequence."),
    (r"\bdiffusion\b", "Diffusion", "扩散：此处出现了 diffusion 一词；具体过程与条件仍以摘录为准。", "Diffusion is the named process here; its specific process and conditions remain excerpt-dependent."),
    (r"\bdropout\b", "Dropout", "Dropout：训练时随机停用部分单元的术语。", "Dropout names random unit disabling during training."),
    (r"\bgradient descent\b", "Gradient descent", "梯度下降：沿梯度的反方向更新参数。", "Gradient descent updates parameters opposite the gradient."),
    (r"\bcross[- ]entropy\b", "Cross-entropy", "交叉熵：比较预测分布与目标分布的损失术语。", "Cross-entropy names a loss comparing predicted and target distributions."),
    (r"\bPDDL\b", "PDDL", "PDDL：描述规划问题的领域与实例的语言。", "PDDL names a language for planning domains and problem instances."),
)
_ROLE = {
    "background": ("背景", "background"), "motivation": ("动机", "motivation"),
    "problem": ("问题", "problem"), "methodology": ("方法", "method"),
    "experiment": ("实验条件", "experimental conditions"), "result": ("结果", "result"),
    "contribution": ("贡献", "contribution"), "limitation": ("限制", "limitation"),
}


def _language(language: str) -> str:
    if language in {"zh-CN", "zh", "zh-cn"}:
        return "zh-CN"
    if language in {"en", "en-US", "en-GB"}:
        return "en"
    if language == "bilingual":
        return language
    raise ValueError("language must be zh-CN, en, or bilingual")


def _safe_text(value: str) -> bool:
    key = os.environ.get("FIELDS_STUDY_FLOW_LLM_API_KEY", "").strip()
    return (not _UNSAFE.search(value) and not _SECRET_TEXT.search(value) and (not key or key not in value)
            and not any((ord(c) < 32 and c not in "\n\r\t") or 0xD800 <= ord(c) <= 0xDFFF for c in value))


def _identifier(value) -> bool:
    return isinstance(value, str) and bool(value) and len(value) <= 160 and bool(re.fullmatch(r"[\w.:-]+", value)) and _safe_text(value)


def _index(rows, name: str) -> dict:
    if not isinstance(rows, list):
        raise ValueError("research context " + name + " must be a list")
    result = {}
    for row in rows:
        if not isinstance(row, dict) or not _identifier(row.get("id")) or row["id"] in result:
            raise ValueError("research context " + name + " require unique safe IDs")
        result[row["id"]] = row
    return result


def _valid_locator(locator) -> bool:
    if not isinstance(locator, dict) or not locator or set(locator) - _LOCATOR_KEYS:
        return False
    for name, value in locator.items():
        if name in {"page", "line_start", "line_end", "row"}:
            if type(value) is not int or value < 1:
                return False
        elif not isinstance(value, str) or not value.strip():
            return False
        elif name != "json_pointer" and not _safe_text(value):
            return False
    if "line_end" in locator and ("line_start" not in locator or locator["line_end"] < locator["line_start"]):
        return False
    if "json_pointer" in locator:
        pointer = locator["json_pointer"]
        if not pointer.startswith("/") or re.search(r"~(?![01])", pointer):
            return False
        key = os.environ.get("FIELDS_STUDY_FLOW_LLM_API_KEY", "").strip()
        if (key and key in pointer) or re.search(r"(?i)<|[a-z]:[\\/]|file:|javascript:", pointer):
            return False
        if any(_SECRET_FIELD.fullmatch(part.replace("~1", "/").replace("~0", "~")) for part in pointer.split("/")):
            return False
    return True


def _context(context: dict) -> tuple[dict, dict, dict]:
    if not isinstance(context, dict) or type(context.get("schema_version")) is not int or context["schema_version"] != 1:
        raise ValueError("research context schema_version must be 1")
    sources = _index(context.get("sources"), "sources")
    anchors = _index(context.get("anchors"), "anchors")
    claims = _index(context.get("claims"), "claims")
    for claim in claims.values():
        ids = claim.get("anchor_ids")
        if not isinstance(ids, list) or any(not _identifier(a) for a in ids) or len(set(ids)) != len(ids):
            raise ValueError("research claim anchor_ids must be unique IDs")
        if not isinstance(claim.get("kind"), str) or claim["kind"] not in _ROLE:
            raise ValueError("research claim kind is invalid")
    valid = {aid: a for aid, a in anchors.items()
             if isinstance(a.get("source_id"), str) and a["source_id"] in sources
             and sources[a["source_id"]].get("availability") != "missing" and a.get("locator_status") == "valid"
             and _valid_locator(a.get("locator")) and isinstance(a.get("snippet"), str)
             and a["snippet"].strip() and _safe_text(a["snippet"])}
    return sources, valid, claims


def _reference(anchor: dict) -> dict:
    return {"anchor_id": anchor["id"], "source_id": anchor["source_id"],
            "locator": copy.deepcopy(anchor["locator"]), "snippet": anchor["snippet"]}


def _orientation(text: str, kind: str, language: str) -> dict:
    zh = language == "zh-CN"
    if not text or not _safe_text(text):
        return {"plain_meaning": "缺少可定位摘录，尚不能解释此论点。" if zh else "No locatable excerpt is available to explain this claim.",
                "why_it_matters": "需要原文后才能判断其作用。" if zh else "The original excerpt is needed to assess its role.", "method_note": None}
    # Quote the actual fragment; terminology is orientation, not translation.
    role = _ROLE.get(kind, ("段落", "paragraph"))[0 if zh else 1]
    terms = [entry for entry in _TERMS if re.search(entry[0], text, re.IGNORECASE)]
    focus = "; ".join(entry[2 if zh else 3] for entry in terms) or None
    cue = text.splitlines()[0][:280]
    return {
        "plain_meaning": ("摘录导读（不是可靠的全文翻译）：\n" if zh else "Excerpt orientation (not a full translation):\n") + text,
        "why_it_matters": (f"此{role}摘录的具体线索是“{cue}”；其适用范围应以该原文为准。" if zh else
                           f'The concrete cue in this {role} excerpt is "{cue}"; interpret its scope using this original text.'),
        "method_note": focus,
    }


def _local_item(claim: dict, anchors: dict, language: str) -> dict:
    ids = [aid for aid in claim["anchor_ids"] if aid in anchors]
    text = "\n".join(anchors[aid]["snippet"] for aid in ids)
    return {"claim_id": claim["id"], "kind": claim["kind"], **_orientation(text, claim["kind"], language),
            "anchor_ids": ids, "evidence_refs": [_reference(anchors[aid]) for aid in ids],
            "review_status": "unreviewed"}


def _payload(claims: dict, anchors: dict, language: str) -> tuple[dict, bool]:
    payload = {"language": language, "claims": [], "anchors": []}
    selected = set()
    sources = set()
    limited = False
    for claim in claims.values():
        usable = [aid for aid in claim["anchor_ids"] if aid in anchors]
        if not usable:
            continue
        if len(payload["claims"]) >= MAX_CLAIMS:
            limited = True
            continue
        candidate = copy.deepcopy(payload)
        new = [aid for aid in usable if aid not in selected]
        new_sources = sources | {anchors[aid]["source_id"] for aid in new}
        if (len(selected) + len(new) > MAX_CHUNKS or len(new_sources) > MAX_FILES
                or any(len(anchors[aid]["snippet"].encode("utf-8")) > MAX_CHUNK_BYTES for aid in usable)):
            limited = True
            continue
        candidate["claims"].append({"id": claim["id"], "kind": claim["kind"], "anchor_ids": usable})
        candidate["anchors"].extend({"id": aid, **{k: v for k, v in _reference(anchors[aid]).items() if k != "anchor_id"}} for aid in new)
        if len(json.dumps(candidate, ensure_ascii=False).encode("utf-8")) > MAX_INPUT_BYTES:
            limited = True
            continue
        payload = candidate
        selected.update(new)
        sources = new_sources
    return payload, limited


def _validate_response(raw: str | dict, payload: dict, anchors: dict, claims: dict) -> list[dict]:
    data = transport.parse_response(raw)
    if set(data) != {"items"} or not isinstance(data["items"], list):
        raise transport.ProviderError("provider_response_rejected")
    allowed = {c["id"]: set(c["anchor_ids"]) for c in payload["claims"]}
    seen = set()
    result = []
    for item in data["items"]:
        if not isinstance(item, dict) or set(item) - {"claim_id", "plain_meaning", "why_it_matters", "method_note", "example", "anchor_ids", "evidence_refs"}:
            raise transport.ProviderError("provider_response_rejected")
        cid = item.get("claim_id")
        if not isinstance(cid, str) or cid not in allowed or cid in seen:
            raise transport.ProviderError("provider_response_rejected")
        ids = item.get("anchor_ids")
        if (not isinstance(ids, list) or not ids or any(not isinstance(a, str) for a in ids)
                or len(set(ids)) != len(ids) or set(ids) - allowed[cid]):
            raise transport.ProviderError("provider_response_rejected")
        texts = []
        for name in ("plain_meaning", "why_it_matters", "method_note"):
            value = item.get(name)
            if name == "method_note" and value is None:
                continue
            if not isinstance(value, str) or not value.strip() or not _safe_text(value):
                raise transport.ProviderError("provider_response_rejected")
            texts.append(value)
        grounded = set(_NUMBERS.findall("\n".join(anchors[aid]["snippet"] for aid in ids)))
        if any(set(_NUMBERS.findall(text)) - grounded for text in texts):
            raise transport.ProviderError("provider_response_rejected")
        refs = [_reference(anchors[aid]) for aid in ids]
        if "evidence_refs" in item and json.dumps(item["evidence_refs"], sort_keys=True) != json.dumps(refs, sort_keys=True):
            raise transport.ProviderError("provider_response_rejected")
        normalized = {"claim_id": cid, "kind": claims[cid]["kind"],
                      "plain_meaning": item["plain_meaning"], "why_it_matters": item["why_it_matters"],
                      "method_note": item.get("method_note"), "anchor_ids": list(ids),
                      "evidence_refs": refs, "review_status": "unreviewed"}
        if "example" in item:
            example = item["example"]
            if (not isinstance(example, dict) or set(example) != {"kind", "text"}
                    or example["kind"] != "educational" or not isinstance(example["text"], str)
                    or not example["text"].strip() or not _safe_text(example["text"])):
                raise transport.ProviderError("provider_response_rejected")
            normalized["example"] = copy.deepcopy(example)
        seen.add(cid)
        result.append(normalized)
    if seen != set(allowed):
        raise transport.ProviderError("provider_response_rejected")
    return result


def _raw_items(items: list[dict]) -> dict:
    return {"items": [{k: v for k, v in item.items() if k not in {"kind", "review_status", "segment_id", "language", "translations"}} for item in items]}


def _bilingual_item(primary: dict, secondary: dict) -> dict:
    return {**copy.deepcopy(primary), "language": "zh-CN",
            "translations": {"en": {**copy.deepcopy(secondary), "language": "en"}}}


def _language_items(items: dict | None, language: str) -> dict | None:
    if not isinstance(items, dict):
        return None
    rows = items.get("items") if "items" in items else list(items.values())
    if not isinstance(rows, list):
        return None
    selected = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("language", language) == language:
            selected.append(row)
        elif isinstance(row.get("translations"), dict):
            translated = row["translations"].get(language)
            if isinstance(translated, dict) and translated.get("language") == language:
                selected.append(translated)
    return {"items": selected}


def _cache_key(context: dict, language: str, config: transport.ProviderConfig, provider) -> str:
    identity = "http" if provider is None else getattr(provider, "__module__", "") + ":" + getattr(provider, "__qualname__", type(provider).__name__)
    value = {"context": context, "language": language, "model": config.model,
             "endpoint": config.endpoint, "provider": identity, "prompt_version": transport.PROMPT_VERSION}
    try:
        raw = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, RecursionError):
        raise ValueError("research context must be JSON serializable") from None
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _read_cache(path: Path, payload: dict, anchors: dict, claims: dict) -> list[dict] | None:
    try:
        if path.stat().st_size > transport.MAX_RESPONSE_BYTES:
            return None
        return _validate_response(path.read_text(encoding="utf-8"), payload, anchors, claims)
    except (OSError, UnicodeError, transport.ProviderError):
        return None


def _write_cache(path: Path, items: list[dict]) -> bool:
    temporary = None
    try:
        raw = json.dumps(_raw_items(items), ensure_ascii=False, allow_nan=False)
        if len(raw.encode("utf-8")) > transport.MAX_RESPONSE_BYTES:
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
        temporary.replace(path)
        return True
    except OSError:
        return False
    finally:
        if temporary is not None and temporary.exists():
            try:
                temporary.unlink()
            except OSError:
                pass


def prepare_explanations(context: dict, *, language: str = "zh-CN", provider_mode: str = "auto",
                         offline: bool = False, cache_dir: Path | None = None,
                         provider: Callable[[dict], dict | str] | None = None) -> dict:
    """Generate once, then reuse items keyed by claim_id (also includes kind).

    The injected provider receives one bounded dict: language, claims containing
    id/kind/anchor_ids, and anchors containing id/source_id/locator/snippet. It
    returns {items: [...]} or that object's strict JSON. Injection does not bypass
    explicit environment enable/config checks. No source files are opened.

    mode is local or llm; status is ready or fallback. Warnings are fixed codes.
    Cache is opt-in, private, and stores only validated items; keep its directory
    out of public exports. No cache/model lookup occurs in local/offline modes.
    Bilingual generation prepares zh-CN and en separately (two bounded provider
    calls before cache hits). Chinese is primary; item.translations.en contains
    the full English item. language_modes preserves each side's actual provider
    mode; mixed indicates that only one language used the model successfully.
    """
    config = transport.resolve_config(provider_mode, offline=offline)
    language = _language(language)
    if language == "bilingual":
        options = {"provider_mode": provider_mode, "offline": offline,
                   "cache_dir": cache_dir, "provider": provider}
        primary = prepare_explanations(context, language="zh-CN", **options)
        secondary = prepare_explanations(context, language="en", **options)
        english = {item["claim_id"]: item for item in secondary["items"]}
        return {"mode": primary["mode"] if primary["mode"] == secondary["mode"] else "mixed",
                "status": "fallback" if "fallback" in {primary["status"], secondary["status"]} else "ready",
                "warnings": list(dict.fromkeys(primary["warnings"] + secondary["warnings"])),
                "language": "bilingual", "language_modes": {"zh-CN": primary["mode"], "en": secondary["mode"]},
                "items": [_bilingual_item(item, english[item["claim_id"]]) for item in primary["items"]]}
    _sources, anchors, claims = _context(context)
    local = [_local_item(claim, anchors, language) for claim in claims.values()]
    warnings = ["evidence_unavailable"] if any(not item["anchor_ids"] or len(item["anchor_ids"]) != len(claims[item["claim_id"]]["anchor_ids"]) for item in local) else []
    result = {"mode": "local", "status": "ready", "warnings": warnings, "items": local}
    if config is None:
        return result
    payload, limited = _payload(claims, anchors, language)
    if limited:
        warnings.append("provider_input_limited")
    if not payload["claims"]:
        return result
    cache = Path(cache_dir) / (_cache_key(context, language, config, provider) + ".json") if cache_dir is not None else None
    generated = _read_cache(cache, payload, anchors, claims) if cache is not None else None
    if generated is None:
        try:
            raw = provider(copy.deepcopy(payload)) if provider is not None else transport.request_explanations(payload, config)
            generated = _validate_response(raw, payload, anchors, claims)
        except transport.ProviderError as error:
            warnings.append(error.code if error.code in {"provider_request_failed", "provider_response_rejected"} else "provider_request_failed")
            result["status"] = "fallback"
            return result
        except Exception:
            warnings.append("provider_request_failed")
            result["status"] = "fallback"
            return result
        if cache is not None and not _write_cache(cache, generated):
            warnings.append("cache_write_failed")
    lookup = {item["claim_id"]: item for item in generated}
    result.update(mode="llm", items=[lookup.get(item["claim_id"], item) for item in local])
    return result


def explain_segment(segment: dict, context: dict, language: str, items: dict | None = None) -> dict:
    """Pure lens projection: exact excerpt matches only, never HTTP or files.

    items accepts prepare_explanations' envelope or a claim-ID keyed item dict.
    Only a claim whose complete cited text equals this paragraph can be reused;
    a subparagraph gets its own local orientation, not a whole-claim summary.
    """
    language = _language(language)
    if language == "bilingual":
        primary = explain_segment(segment, context, "zh-CN", items=items)
        secondary = explain_segment(segment, context, "en", items=items)
        return _bilingual_item(primary, secondary)
    _sources, anchors, claims = _context(context)
    if not isinstance(segment, dict):
        raise ValueError("segment must be a dict")
    text = segment.get("original_text", segment.get("text", segment.get("snippet", "")))
    if not isinstance(text, str):
        raise ValueError("segment text must be a string")
    requested = segment.get("anchor_ids")
    locator = segment.get("locator", {key: segment[key] for key in _LOCATOR_KEYS if key in segment})
    if not isinstance(locator, dict):
        locator = {"invalid": True}
    ids = [aid for aid, anchor in anchors.items() if anchor["snippet"].strip() == text.strip()
           and (requested is None or isinstance(requested, list) and aid in requested)
           and ("source_id" not in segment or segment["source_id"] == anchor["source_id"])
           and all(key in anchor["locator"] and type(value) is type(anchor["locator"][key])
                   and value == anchor["locator"][key] for key, value in locator.items())] if text.strip() else []
    if len(ids) > 1 and requested is None and not locator and "source_id" not in segment:
        ids = []
    candidates = [claim for claim in claims.values() if claim["anchor_ids"]
                  and set(claim["anchor_ids"]) <= set(ids)]
    kind = candidates[0]["kind"] if candidates else segment.get("section_kind", "paragraph")
    if not isinstance(kind, str):
        kind = "paragraph"
    sid = segment.get("id", segment.get("segment_id"))
    output = {"segment_id": sid if _identifier(sid) else None,
              **_orientation(text, kind, language), "anchor_ids": ids,
              "evidence_refs": [_reference(anchors[aid]) for aid in ids], "review_status": "unreviewed"}
    items = _language_items(items, language)
    if items is None:
        return output
    rows = items["items"]
    for claim in candidates:
        for row in rows:
            if not isinstance(row, dict) or row.get("claim_id") != claim["id"]:
                continue
            if (not isinstance(row.get("anchor_ids"), list) or not row["anchor_ids"]
                    or any(not isinstance(a, str) for a in row["anchor_ids"]) or set(row["anchor_ids"]) - set(ids)):
                continue
            payload = {"claims": [{"id": claim["id"], "anchor_ids": ids}]}
            try:
                checked = _validate_response(_raw_items([row]), payload, anchors, claims)[0]
            except (transport.ProviderError, TypeError):
                continue
            output.update({k: copy.deepcopy(v) for k, v in checked.items() if k not in {"claim_id", "kind"}})
            output["claim_id"] = claim["id"]
            return output
    return output
