"""Does a posting's title match what a Scout search is looking for?

Job sites match loosely: a search for "IT Analyst" also returns sales
executives and business analysts. A title is kept when it carries every
distinctive word of one of the search's job titles, or of a related title
Luna suggested for them ("SOC Analyst" -> "Threat Intelligence Analyst",
"Incident Response Analyst", ...). Seniority words (senior, lead, L2, intern)
never count, and a word matches its common equivalents ("security" in
"cybersecurity", "IT" as "ICT" or "information technology", "SOC" as
"security operations").
"""

from __future__ import annotations

import re

from api.job_os import llm

_WORD = re.compile(r"[a-z0-9+#]+")
# Words that say how senior or what kind of contract, not what the job is.
GENERIC = frozenset("""
senior sr junior jr lead leader principal staff chief head associate assistant intern internship trainee graduate
fresh entry level mid i ii iii iv v l1 l2 l3 l4 1 2 3 4 tier the and of for in to a an with at
contract permanent temporary temp part full time remote hybrid onsite urgent immediate hiring
""".split())
# A word in a search title and what else counts as it in a posting's title.
ALIASES = {
    "it": ("it", "ict", "information technology", "technology"),
    "soc": ("soc", "security operations", "security operation", "cyber defense", "cyber defence", "cdc"),
    "security": ("security", "cybersecurity", "cyber", "infosec", "secops"),
    "cyber": ("cyber", "cybersecurity", "security", "infosec"),
    "cybersecurity": ("cybersecurity", "cyber", "security", "infosec"),
    "network": ("network", "networks", "networking", "noc"),
    "developer": ("developer", "dev", "programmer"),
    "engineer": ("engineer", "engineering"),
    "data": ("data", "analytics"),
}
MAX_RELATED = 15


def words(text: str) -> list[str]:
    return _WORD.findall(str(text or "").lower())


def distinctive(phrase: str) -> list[str]:
    """The words of a title that say what the job is (all of them if none are left)."""
    all_words = words(phrase)
    return [w for w in all_words if w not in GENERIC] or all_words


def _has(word: str, title_words: set[str], title_text: str) -> bool:
    for alias in ALIASES.get(word, (word,)):
        if " " in alias:
            if f" {alias} " in title_text:
                return True
        elif alias in title_words:
            return True
        # Compounds and plurals: "security" in "cybersecurity", "analyst" in "analysts".
        elif len(alias) >= 5 and any(t.endswith(alias) or t.startswith(alias) for t in title_words):
            return True
    return False


def title_relevant(title: str, phrases: list[str]) -> bool:
    """True when the title has every distinctive word of one phrase; no phrases keeps everything."""
    phrases = [p for p in phrases if words(p)]
    if not phrases:
        return True
    title_words = set(words(title))
    title_text = f" {' '.join(words(title))} "
    return any(all(_has(w, title_words, title_text) for w in distinctive(p)) for p in phrases)


def clean_titles(values, *, limit: int = MAX_RELATED) -> list[str]:
    out: list[str] = []
    for value in values if isinstance(values, list) else []:
        text = re.sub(r"\s+", " ", str(value or "")).strip()[:60]
        if text and words(text) and text.lower() not in (o.lower() for o in out):
            out.append(text)
    return out[:limit]


SUGGEST_SYSTEM = (
    "You help a job seeker search job sites. Given the job titles they search for, list other job titles that are "
    "the same kind of work: what employers commonly call these roles, close specialisations and near-equivalents a "
    "person doing this job would also apply for. Do not include broader or different fields (for a security analyst: "
    "no business analyst, data analyst, financial analyst or sales roles). No seniority words. Return ONLY JSON: "
    "{\"titles\": [\"...\"]} with 8-15 titles."
)


def suggest_related(keywords: str) -> list[str]:
    """Luna's related titles for a search's job titles (one model call)."""
    data, _model = llm.ask_json(SUGGEST_SYSTEM, f"Job titles searched: {str(keywords)[:200]}", max_tokens=600)
    titles = data.get("titles") if isinstance(data, dict) else None
    searched = {t.strip().lower() for t in str(keywords).split(",")}
    return [t for t in clean_titles(titles) if t.lower() not in searched]
