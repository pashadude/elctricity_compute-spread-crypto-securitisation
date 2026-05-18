import json

from agent import energy_llm_oracle as oracle


def _candidate(**overrides):
    data = {
        "condition_id": "0xabc",
        "slug": "will-80-or-more-ships-transit-the-strait-of-hormuz-between-april-13-april-19",
        "event_slug": "how-many-ships-transit-the-strait-of-hormuz-this-week-apr-13-19",
        "energy_template_id": "energy_geopolitics",
        "fill_ts": "2026-04-14 18:00:04",
        "side": "BUY",
        "outcome_type": "No",
        "entry_price": 0.91,
        "premium": -0.09,
        "hours_to_res": 102.0,
    }
    data.update(overrides)
    return oracle.EnergyOracleCandidate(**data)


def test_query_spec_maps_hormuz_to_core_context_terms():
    spec = oracle.query_spec_for_candidate(_candidate())

    assert spec.label == "hormuz_transit"
    assert "Strait of Hormuz" in spec.core_terms
    assert "tankers" in spec.context_terms
    assert "header:" in spec.searchline


def test_article_relevance_requires_core_and_context_terms():
    relevant = oracle.ArticleSnippet(
        article_id="1",
        title="Strait of Hormuz tanker transit rises",
        summary="Shipping data shows more oil tankers moving through the chokepoint.",
        source="wire",
        published_at="2026-04-14",
        rank_global=1,
    )
    noisy = oracle.ArticleSnippet(
        article_id="2",
        title="Hormuz local festival opens",
        summary="Tourism officials expect many visitors.",
        source="local",
        published_at="2026-04-14",
        rank_global=1,
    )

    assert oracle.is_relevant_article(
        relevant,
        core_terms=["Strait of Hormuz", "Hormuz"],
        context_terms=["tankers", "shipping", "oil"],
    )
    assert not oracle.is_relevant_article(
        noisy,
        core_terms=["Strait of Hormuz", "Hormuz"],
        context_terms=["tankers", "shipping", "oil"],
    )


def test_parse_analyst_output_derives_verdict_from_probability():
    parsed = oracle.parse_analyst_output(
        json.dumps({
            "p_yes": 0.22,
            "confidence": 0.7,
            "reason": "Evidence says high transit count is plausible.",
            "evidence_ids": ["1"],
        }),
        veto_threshold=0.10,
    )

    assert parsed.verdict == oracle.VERDICT_VETO
    assert parsed.p_yes == 0.22
    assert parsed.confidence == 0.7


def test_parse_analyst_output_rejects_invalid_probability():
    try:
        oracle.parse_analyst_output('{"p_yes": 1.4}', veto_threshold=0.10)
    except ValueError as exc:
        assert "p_yes" in str(exc)
    else:
        raise AssertionError("expected malformed p_yes to fail")


def test_analyze_candidate_uses_mocked_opoint_and_nebius_without_network():
    candidate = _candidate()

    def fake_fetch(_candidate, _query):
        return [
            oracle.ArticleSnippet(
                article_id="a1",
                title="Strait of Hormuz tanker traffic elevated",
                summary="Shipping and oil tanker counts point to elevated transit.",
                source="wire",
                published_at="2026-04-14",
            )
        ], {"raw": 1, "after_dedup": 1, "after_filter": 1, "pages": 1}

    calls = []

    def fake_chat(**kwargs):
        calls.append(kwargs["model"])
        if kwargs["model"].startswith("Qwen/"):
            return oracle.ChatResult(
                content=json.dumps({"passed": True, "reason": "Evidence-backed."}),
                model=kwargs["model"],
            )
        return oracle.ChatResult(
            content=json.dumps({
                "p_yes": 0.35,
                "verdict": "VETO",
                "confidence": 0.8,
                "reason": "Opoint evidence supports a high transit bucket.",
                "evidence_ids": ["a1"],
            }),
            model=kwargs["model"],
        )

    receipt = oracle.analyze_candidate(
        candidate,
        fetch_articles=fake_fetch,
        chat_completion=fake_chat,
    )

    assert calls == [oracle.DEFAULT_ANALYST_MODEL, oracle.DEFAULT_CRITIC_MODEL]
    assert receipt.verdict == oracle.VERDICT_VETO
    assert receipt.p_yes == 0.35
    assert receipt.article_count == 1
    assert receipt.evidence_hash.startswith("0x")
    assert receipt.analysis_hash.startswith("0x")


def test_critic_rejection_prevents_keep_as_positive_evidence():
    candidate = _candidate(
        slug="will-openai-release-gpt-5",
        event_slug="gpt-5-released-by",
        energy_template_id="energy_ai_infra",
        premium=0.03,
    )

    def fake_fetch(_candidate, _query):
        return [
            oracle.ArticleSnippet(
                article_id="a1",
                title="OpenAI model release uncertain",
                summary="Executives did not confirm a GPT-5 launch timeline.",
                source="wire",
                published_at="2026-04-14",
            )
        ], {"raw": 1, "after_dedup": 1, "after_filter": 1, "pages": 1}

    def fake_chat(**kwargs):
        if kwargs["model"].startswith("Qwen/"):
            return oracle.ChatResult(
                content=json.dumps({"passed": False, "reason": "KEEP not supported."}),
                model=kwargs["model"],
            )
        return oracle.ChatResult(
            content=json.dumps({
                "p_yes": 0.04,
                "verdict": "KEEP",
                "confidence": 0.5,
                "reason": "Weak evidence.",
                "evidence_ids": ["a1"],
            }),
            model=kwargs["model"],
        )

    receipt = oracle.analyze_candidate(
        candidate,
        fetch_articles=fake_fetch,
        chat_completion=fake_chat,
    )

    assert receipt.verdict == oracle.VERDICT_DEFER
    assert receipt.reason_code == "critic_reject_keep"
