"""Opoint-grounded Nebius LLM oracle for S-4 energy candidates.

This module contains the real LLM oracle path. It fetches Opoint evidence for
one historical/live energy candidate, asks a Nebius-hosted analyst model for
the probability that the bucket resolves YES, optionally validates that output
with a critic model, and emits an auditable JSON receipt.

The oracle is evidence only. It does not score premium, call the judge, or call
any on-chain adapter.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

import requests

from templates.energy.classifier import classify_energy

DEFAULT_MASTER_FILLS = Path(__file__).resolve().parent.parent / "data" / "master_fills_v4.tsv"
DEFAULT_ANALYST_MODEL = "deepseek-ai/DeepSeek-V3.2"
DEFAULT_CRITIC_MODEL = "Qwen/Qwen3-30B-A3B-Instruct-2507"
NEBIUS_BASE_URL = "https://api.studio.nebius.ai/v1"
OPOINT_SEARCH_URL = "https://api.opoint.com/search/"

VERDICT_KEEP = "KEEP"
VERDICT_VETO = "VETO"
VERDICT_DEFER = "DEFER"


@dataclass(frozen=True, slots=True)
class EnergyOracleCandidate:
    condition_id: str
    slug: str
    event_slug: str
    energy_template_id: str
    fill_ts: str
    side: str
    outcome_type: str
    entry_price: float
    premium: float
    hours_to_res: float | None = None


@dataclass(frozen=True, slots=True)
class QuerySpec:
    label: str
    searchline: str
    core_terms: list[str]
    context_terms: list[str]


@dataclass(frozen=True, slots=True)
class ArticleSnippet:
    article_id: str
    title: str
    summary: str
    source: str
    published_at: str
    url: str = ""
    equalgroup: str | None = None
    rank_global: int | None = None


@dataclass(frozen=True, slots=True)
class ChatResult:
    content: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


@dataclass(frozen=True, slots=True)
class AnalystOutput:
    p_yes: float
    confidence: float
    verdict: str
    reason: str
    evidence_ids: list[str]


@dataclass(frozen=True, slots=True)
class CriticOutput:
    passed: bool
    reason: str


@dataclass(frozen=True, slots=True)
class OracleReceipt:
    ts: str
    condition_id: str
    slug: str
    event_slug: str
    energy_template_id: str
    verdict: str
    reason_code: str
    p_yes: float | None
    confidence: float | None
    analyst_model: str
    critic_model: str | None
    critic_passed: bool | None
    critic_reason: str | None
    article_count: int
    coverage: dict[str, int]
    query: dict[str, Any]
    evidence_hash: str
    analysis_hash: str
    cost_usd: float
    reason: str


ChatFn = Callable[..., ChatResult]
FetchArticlesFn = Callable[[EnergyOracleCandidate, QuerySpec], tuple[list[ArticleSnippet], dict[str, int]]]


ANALYST_SYSTEM = """You are an evidence-grounded prediction-market oracle for Arc S-4 energy candidates.

The desk is considering buying NO on one Polymarket bucket. Estimate the probability that this exact bucket resolves YES.

Use the Opoint articles as evidence. Do not invent facts not in the evidence. Return strict JSON:
{
  "p_yes": <float 0-1>,
  "verdict": "KEEP" | "VETO" | "DEFER",
  "confidence": <float 0-1>,
  "reason": "<short reason>",
  "evidence_ids": ["..."]
}

Rules:
- VETO if the evidence implies the bucket's YES probability is above the threshold.
- KEEP only if evidence does not contradict the NO trade and confidence is sufficient.
- DEFER when evidence is absent, stale, contradictory, or insufficient.
- This output is evidence only; it is not an execution instruction.
"""

CRITIC_SYSTEM = """You validate an energy prediction-market oracle receipt.

Return strict JSON:
{
  "passed": <true|false>,
  "reason": "<short reason>"
}

Fail if JSON fields are inconsistent, evidence is not used, or a KEEP verdict is unsupported by the articles.
"""


def _as_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(out) or math.isinf(out):
        return None
    return out


def _strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", "", value or "")
    return re.sub(r"\s+", " ", text).strip()


def _build_searchline(core_terms: list[str]) -> str:
    quoted: list[str] = []
    for term in core_terms:
        term = term.strip()
        if not term:
            continue
        if " " in term and not (term.startswith('"') and term.endswith('"')):
            term = f'"{term}"'
        quoted.append(term)
    body = " OR ".join(quoted)
    return f"(header:({body}) OR summary:({body}) OR text:({body}))"


def _dedupe_articles(articles: Iterable[ArticleSnippet]) -> list[ArticleSnippet]:
    seen: set[str] = set()
    out: list[ArticleSnippet] = []
    for article in articles:
        key = article.equalgroup or hashlib.sha256(
            f"{article.title}|{article.summary}".encode("utf-8")
        ).hexdigest()
        if key in seen:
            continue
        seen.add(key)
        out.append(article)
    return out


def _contains_any(blob: str, terms: Iterable[str]) -> bool:
    lower = blob.lower()
    return any(term.lower() in lower for term in terms if term)


def is_relevant_article(
    article: ArticleSnippet,
    *,
    core_terms: list[str],
    context_terms: list[str],
    max_rank: int = 10,
) -> bool:
    if article.rank_global is not None and article.rank_global > max_rank:
        return False
    blob = f"{article.title} {article.summary}"
    return _contains_any(blob, core_terms) and _contains_any(blob, context_terms)


def query_spec_for_candidate(candidate: EnergyOracleCandidate) -> QuerySpec:
    slug_blob = f"{candidate.slug} {candidate.event_slug}".lower()
    template = candidate.energy_template_id

    if template == "energy_geopolitics" or "hormuz" in slug_blob:
        core = ["Strait of Hormuz", "Hormuz transit"]
        context = ["ships", "tankers", "transit", "Iran", "shipping", "oil"]
        return QuerySpec("hormuz_transit", _build_searchline(core), core, context)

    if "gpt-5" in slug_blob or "gpt-5pt5" in slug_blob:
        core = ["GPT-5", "GPT-5.5", "OpenAI"]
        context = ["release", "launched", "available", "model", "Sam Altman"]
        return QuerySpec("gpt_release", _build_searchline(core), core, context)

    if "best-math-ai" in slug_blob or "best-coding-ai" in slug_blob or "best-ai-model" in slug_blob:
        core = ["OpenAI", "Anthropic", "Claude", "GPT", "Gemini", "DeepSeek"]
        context = ["benchmark", "Chatbot Arena", "coding", "math", "model", "release"]
        return QuerySpec("ai_leaderboard", _build_searchline(core), core, context)

    if "nvda" in slug_blob or "nvidia" in slug_blob:
        core = ["NVIDIA", "NVDA"]
        context = ["AI chip", "GPU", "earnings", "data center", "Blackwell", "stock"]
        return QuerySpec("nvidia_ai_infra", _build_searchline(core), core, context)

    if "app-store" in slug_blob or "free-app" in slug_blob:
        core = ["ChatGPT", "OpenAI", "Apple App Store"]
        context = ["app", "ranking", "download", "AI", "iOS"]
        return QuerySpec("ai_app_store", _build_searchline(core), core, context)

    if template == "energy_ai_infra":
        core = ["OpenAI", "Anthropic", "NVIDIA", "data center", "AI compute"]
        context = ["power", "GPU", "capacity", "benchmark", "release", "infrastructure"]
        return QuerySpec("ai_infra", _build_searchline(core), core, context)

    core = ["energy", "power", "oil", "gas"]
    context = ["price", "supply", "demand", "outage", "policy"]
    return QuerySpec(template or "energy", _build_searchline(core), core, context)


def _parse_opoint_article(raw: dict[str, Any]) -> ArticleSnippet:
    article_id = str(raw.get("id_article") or raw.get("id") or "")
    title = _strip_html((raw.get("header") or {}).get("text", "") if isinstance(raw.get("header"), dict) else raw.get("title", ""))
    summary = _strip_html((raw.get("summary") or {}).get("text", "") if isinstance(raw.get("summary"), dict) else raw.get("summary", ""))
    source = ((raw.get("first_source") or {}).get("name") if isinstance(raw.get("first_source"), dict) else None) or raw.get("source") or "unknown"
    date_text = (raw.get("local_time") or {}).get("text", "") if isinstance(raw.get("local_time"), dict) else raw.get("published_at", "")
    rank = None
    site_rank = raw.get("site_rank")
    if isinstance(site_rank, dict):
        maybe_rank = _as_float(site_rank.get("rank_global"))
        rank = int(maybe_rank) if maybe_rank is not None else None
    equalgroup = raw.get("equalgroup")
    if isinstance(equalgroup, dict):
        equalgroup = equalgroup.get("id")
    return ArticleSnippet(
        article_id=article_id,
        title=title,
        summary=summary[:800],
        source=str(source),
        published_at=str(date_text),
        url=str(raw.get("orig_url") or raw.get("url") or ""),
        equalgroup=str(equalgroup) if equalgroup is not None else None,
        rank_global=rank,
    )


def fetch_opoint_articles(
    candidate: EnergyOracleCandidate,
    query: QuerySpec,
    *,
    api_key: str | None = None,
    days_back: int = 7,
    n_articles: int = 6,
    max_pages: int = 2,
    timeout: float = 30.0,
) -> tuple[list[ArticleSnippet], dict[str, int]]:
    key = api_key or os.getenv("OPOINT_API_KEY")
    if not key:
        raise RuntimeError("OPOINT_API_KEY is not set")
    newest = _fill_timestamp(candidate.fill_ts) or int(time.time())
    oldest = newest - days_back * 86400
    payload: dict[str, Any] = {
        "expressions": [{
            "linemode": "R",
            "searchline": {
                "searchterm": query.searchline,
                "filters": [{"type": "lang", "id": "en"}],
            },
        }],
        "params": {
            "requestedarticles": 25,
            "oldest": oldest,
            "newest": newest,
            "main": {
                "header": 1,
                "summary": 1,
                "first_source": 1,
                "site_rank": 1,
                "equalgroup": 1,
            },
        },
    }
    headers = {
        "Authorization": f"Token {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    raw_articles: list[ArticleSnippet] = []
    prev_context: str | None = None
    pages = 0
    for _ in range(max_pages):
        resp = requests.post(OPOINT_SEARCH_URL, headers=headers, json=payload, timeout=timeout)
        resp.raise_for_status()
        body = resp.json()
        result = body.get("searchresult") or {}
        docs = result.get("document") or []
        pages += 1
        for raw in docs:
            if isinstance(raw, dict):
                raw_articles.append(_parse_opoint_article(raw))
        context = result.get("context")
        if not context or context == prev_context:
            break
        payload["params"]["context"] = context
        prev_context = context

    deduped = _dedupe_articles(raw_articles)
    filtered = [
        article for article in deduped
        if is_relevant_article(article, core_terms=query.core_terms, context_terms=query.context_terms)
    ][:n_articles]
    return filtered, {
        "raw": len(raw_articles),
        "after_dedup": len(deduped),
        "after_filter": len(filtered),
        "pages": pages,
    }


def _fill_timestamp(fill_ts: str) -> int | None:
    if not fill_ts:
        return None
    try:
        dt = datetime.fromisoformat(fill_ts.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = datetime.strptime(fill_ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def build_analyst_prompt(
    candidate: EnergyOracleCandidate,
    query: QuerySpec,
    articles: list[ArticleSnippet],
    *,
    veto_threshold: float,
) -> str:
    lines = [
        f"Candidate market slug: {candidate.slug}",
        f"Parent event slug: {candidate.event_slug}",
        f"Energy template: {candidate.energy_template_id}",
        f"Desk action being tested: buy NO on this bucket",
        f"Entry NO price: {candidate.entry_price:.4f}",
        f"Historical premium: {candidate.premium:.4f}",
        f"Veto threshold: p_yes > {veto_threshold:.4f}",
        f"Query label: {query.label}",
        "",
        "Opoint evidence available before entry:",
    ]
    if not articles:
        lines.append("- none")
    for idx, article in enumerate(articles, 1):
        aid = article.article_id or f"a{idx}"
        lines.append(
            f"- [{aid}] {article.published_at} {article.source}: "
            f"{article.title} -- {article.summary}"
        )
    lines.extend([
        "",
        "Estimate p_yes for the exact candidate bucket. Return JSON only.",
    ])
    return "\n".join(lines)


def parse_analyst_output(content: str, *, veto_threshold: float) -> AnalystOutput:
    data = _parse_json_object(content)
    p_yes = _as_float(data.get("p_yes"))
    if p_yes is None or not 0.0 <= p_yes <= 1.0:
        raise ValueError("analyst output missing valid p_yes")
    confidence = _as_float(data.get("confidence"))
    if confidence is None:
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    verdict = str(data.get("verdict") or "").upper()
    if verdict not in {VERDICT_KEEP, VERDICT_VETO, VERDICT_DEFER}:
        verdict = VERDICT_VETO if p_yes > veto_threshold else VERDICT_KEEP
    evidence = data.get("evidence_ids") or []
    if not isinstance(evidence, list):
        evidence = []
    return AnalystOutput(
        p_yes=p_yes,
        confidence=confidence,
        verdict=verdict,
        reason=str(data.get("reason") or "")[:1000],
        evidence_ids=[str(x) for x in evidence],
    )


def parse_critic_output(content: str) -> CriticOutput:
    data = _parse_json_object(content)
    return CriticOutput(
        passed=bool(data.get("passed", False)),
        reason=str(data.get("reason") or "")[:500],
    )


def _parse_json_object(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("expected JSON object")
    return data


def nebius_chat_completion(
    *,
    model: str,
    system: str,
    user: str,
    api_key: str | None = None,
    base_url: str = NEBIUS_BASE_URL,
    temperature: float = 0.0,
    max_tokens: int = 700,
    timeout: float = 60.0,
) -> ChatResult:
    key = api_key or os.getenv("NEBIUS_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("NEBIUS_API_KEY is not set")
    resp = requests.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"].get("content") or ""
    usage = data.get("usage") or {}
    return ChatResult(
        content=content,
        model=model,
        input_tokens=int(usage.get("prompt_tokens") or 0),
        output_tokens=int(usage.get("completion_tokens") or 0),
        cost_usd=0.0,
    )


def analyze_candidate(
    candidate: EnergyOracleCandidate,
    *,
    fetch_articles: FetchArticlesFn | None = None,
    chat_completion: ChatFn = nebius_chat_completion,
    analyst_model: str = DEFAULT_ANALYST_MODEL,
    critic_model: str | None = DEFAULT_CRITIC_MODEL,
    veto_threshold: float = 0.10,
) -> OracleReceipt:
    query = query_spec_for_candidate(candidate)
    fetcher = fetch_articles or (lambda c, q: fetch_opoint_articles(c, q))
    articles, coverage = fetcher(candidate, query)

    if not articles:
        return _receipt(
            candidate,
            query=query,
            articles=articles,
            coverage=coverage,
            verdict=VERDICT_DEFER,
            reason_code="no_opoint_evidence",
            p_yes=None,
            confidence=None,
            analyst_model=analyst_model,
            critic_model=critic_model,
            critic_passed=None,
            critic_reason=None,
            cost_usd=0.0,
            reason="No relevant Opoint articles passed the core/context evidence gate.",
        )

    prompt = build_analyst_prompt(candidate, query, articles, veto_threshold=veto_threshold)
    analyst_raw = chat_completion(
        model=analyst_model,
        system=ANALYST_SYSTEM,
        user=prompt,
        temperature=0.1,
        max_tokens=700,
    )
    analyst = parse_analyst_output(analyst_raw.content, veto_threshold=veto_threshold)

    critic_passed: bool | None = None
    critic_reason: str | None = None
    total_cost = analyst_raw.cost_usd
    final_verdict = analyst.verdict
    reason_code = f"analyst_{analyst.verdict.lower()}"
    if critic_model:
        critic_user = json.dumps({
            "candidate": asdict(candidate),
            "articles": [asdict(a) for a in articles],
            "analyst": asdict(analyst),
        }, sort_keys=True)
        critic_raw = chat_completion(
            model=critic_model,
            system=CRITIC_SYSTEM,
            user=critic_user,
            temperature=0.0,
            max_tokens=300,
        )
        total_cost += critic_raw.cost_usd
        critic = parse_critic_output(critic_raw.content)
        critic_passed = critic.passed
        critic_reason = critic.reason
        if not critic.passed and final_verdict == VERDICT_KEEP:
            final_verdict = VERDICT_DEFER
            reason_code = "critic_reject_keep"

    return _receipt(
        candidate,
        query=query,
        articles=articles,
        coverage=coverage,
        verdict=final_verdict,
        reason_code=reason_code,
        p_yes=analyst.p_yes,
        confidence=analyst.confidence,
        analyst_model=analyst_model,
        critic_model=critic_model,
        critic_passed=critic_passed,
        critic_reason=critic_reason,
        cost_usd=total_cost,
        reason=analyst.reason,
    )


def _receipt(
    candidate: EnergyOracleCandidate,
    *,
    query: QuerySpec,
    articles: list[ArticleSnippet],
    coverage: dict[str, int],
    verdict: str,
    reason_code: str,
    p_yes: float | None,
    confidence: float | None,
    analyst_model: str,
    critic_model: str | None,
    critic_passed: bool | None,
    critic_reason: str | None,
    cost_usd: float,
    reason: str,
) -> OracleReceipt:
    query_blob = {
        "label": query.label,
        "searchline": query.searchline,
        "core_terms": query.core_terms,
        "context_terms": query.context_terms,
    }
    evidence_blob = [asdict(a) for a in articles]
    analysis_blob = {
        "condition_id": candidate.condition_id,
        "verdict": verdict,
        "reason_code": reason_code,
        "p_yes": p_yes,
        "confidence": confidence,
        "analyst_model": analyst_model,
        "critic_model": critic_model,
        "critic_passed": critic_passed,
        "critic_reason": critic_reason,
        "reason": reason,
    }
    return OracleReceipt(
        ts=datetime.now(timezone.utc).isoformat(),
        condition_id=candidate.condition_id,
        slug=candidate.slug,
        event_slug=candidate.event_slug,
        energy_template_id=candidate.energy_template_id,
        verdict=verdict,
        reason_code=reason_code,
        p_yes=p_yes,
        confidence=confidence,
        analyst_model=analyst_model,
        critic_model=critic_model,
        critic_passed=critic_passed,
        critic_reason=critic_reason,
        article_count=len(articles),
        coverage=coverage,
        query=query_blob,
        evidence_hash=_hash_json(evidence_blob),
        analysis_hash=_hash_json(analysis_blob),
        cost_usd=cost_usd,
        reason=reason,
    )


def _hash_json(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return "0x" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def candidates_from_master_fills(path: Path) -> list[EnergyOracleCandidate]:
    out: list[EnergyOracleCandidate] = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            template = classify_energy(
                title=f"{row.get('slug') or ''} {row.get('event_slug') or ''}",
                description="",
                upstream_category=row.get("category"),
            )
            if template is None:
                continue
            out.append(EnergyOracleCandidate(
                condition_id=row.get("condition_id") or "",
                slug=row.get("slug") or "",
                event_slug=row.get("event_slug") or "",
                energy_template_id=template,
                fill_ts=row.get("fill_ts") or "",
                side=row.get("side") or "",
                outcome_type=row.get("outcome_type") or "",
                entry_price=_as_float(row.get("entry_price")) or 0.0,
                premium=_as_float(row.get("premium")) or 0.0,
                hours_to_res=_as_float(row.get("hours_to_res")),
            ))
    return out


def write_receipts(path: Path, receipts: Iterable[OracleReceipt]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for receipt in receipts:
            fh.write(json.dumps(asdict(receipt), sort_keys=True) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run live Opoint+Nebius oracle on historical energy fills")
    parser.add_argument("--master-fills-tsv", type=Path, default=DEFAULT_MASTER_FILLS)
    parser.add_argument("--receipts-out", type=Path, default=Path("logs/energy_llm_oracle.jsonl"))
    parser.add_argument("--max-cases", type=int, default=5)
    parser.add_argument("--only-losses", action="store_true")
    parser.add_argument("--model", default=DEFAULT_ANALYST_MODEL)
    parser.add_argument("--critic-model", default=DEFAULT_CRITIC_MODEL)
    parser.add_argument("--no-critic", action="store_true")
    args = parser.parse_args(argv)

    candidates = candidates_from_master_fills(args.master_fills_tsv)
    if args.only_losses:
        losses: set[str] = set()
        with args.master_fills_tsv.open("r", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh, delimiter="\t"):
                if row.get("resolution_outcome") == "LOSS":
                    losses.add(row.get("condition_id") or "")
        candidates = [c for c in candidates if c.condition_id in losses]
    # Avoid repeated LLM calls for duplicate condition ids.
    deduped: list[EnergyOracleCandidate] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = candidate.condition_id or candidate.slug
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    if args.max_cases > 0:
        deduped = deduped[:args.max_cases]

    receipts: list[OracleReceipt] = []
    for candidate in deduped:
        receipts.append(
            analyze_candidate(
                candidate,
                analyst_model=args.model,
                critic_model=None if args.no_critic else args.critic_model,
            )
        )
    write_receipts(args.receipts_out, receipts)
    print(f"wrote {len(receipts)} oracle receipts to {args.receipts_out}")
    for receipt in receipts:
        print(f"{receipt.verdict}\t{receipt.condition_id}\tp_yes={receipt.p_yes}\t{receipt.reason_code}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
