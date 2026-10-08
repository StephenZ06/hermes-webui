"""Scout's on-target title match."""

from __future__ import annotations

from api.job_os import relevance

SEARCH = ["SOC Analyst", "IT Analyst", "Security Analyst"]


def test_titles_must_carry_every_distinctive_word_of_one_search_title():
    keep = ["Junior Cyber Security Analyst", "Information Security Analyst", "SOC L2 Analyst", "Lead IT Business Analyst",
            "ICT Analyst - SAP MDG", "Cybersecurity & Infrastructure Analyst", "Security Operations Analyst"]
    drop = ["Sales Executive", "Business Analyst", "Fraud Analyst (1 Year Contract)", "IT Solutions Consultant",
            "Senior Manager, STPG PE NAND", "Security Guard", "Data Analyst"]
    assert [t for t in keep if not relevance.title_relevant(t, SEARCH)] == []
    assert [t for t in drop if relevance.title_relevant(t, SEARCH)] == []


def test_related_titles_widen_the_match_and_no_titles_keeps_everything():
    assert not relevance.title_relevant("Staff Analyst Threat Intelligence", SEARCH)
    assert relevance.title_relevant("Staff Analyst Threat Intelligence", SEARCH + ["Threat Intelligence Analyst"])
    assert relevance.title_relevant("Anything at all", [])
    # A title of only seniority words still has to match as written.
    assert relevance.distinctive("Senior Lead") == ["senior", "lead"]


def test_luna_suggestions_are_cleaned(monkeypatch):
    monkeypatch.setattr(relevance.llm, "ask_json", lambda *a, **k: ({"titles": [
        "Threat Intelligence Analyst", "threat intelligence analyst", "SOC Analyst", "  Incident   Responder ", "", 7, "x" * 90]}, "m"))
    assert relevance.suggest_related("SOC Analyst, IT Analyst") == ["Threat Intelligence Analyst", "Incident Responder", "7", "x" * 60]
