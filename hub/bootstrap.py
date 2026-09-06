"""The questions almost every application form asks.

Thirty-odd, because that is what a person will actually sit and fill in once.
A hundred gets abandoned halfway, and the two learning channels pick up the
rest as it comes.

`reuse` matters more than it looks. `never` is not an optimisation: without
it, a paragraph written about one company eventually goes to another.
"""
from __future__ import annotations

STANDARD = [
    # legal and eligibility — asked by nearly every form, and knockouts
    ("work_authorization", "Are you legally authorised to work in the UK?", "enum", "always"),
    ("sponsorship", "Will you now or in the future require visa sponsorship?", "enum", "always"),
    ("right_to_work_doc", "What document evidences your right to work?", "text", "always"),
    ("criminal_record", "Do you have any unspent criminal convictions?", "enum", "always"),

    # logistics
    ("notice_period", "What is your notice period?", "text", "always"),
    ("earliest_start", "What is your earliest start date?", "text", "always"),
    ("location", "Where are you currently located?", "text", "always"),
    ("relocate", "Are you willing to relocate?", "enum", "always"),
    ("work_format", "Are you able to work in the office as required?", "enum", "per_archetype"),
    ("travel", "Are you willing to travel for work?", "enum", "always"),

    # compensation
    ("salary_expectation", "What are your salary expectations?", "text", "per_archetype"),
    ("current_salary", "What is your current salary?", "text", "never"),

    # education
    ("degree", "What is your highest level of education?", "enum", "always"),
    ("degree_subject", "What did you study?", "text", "always"),
    ("university", "Which institution did you attend?", "text", "always"),
    ("graduation_year", "What year did you graduate?", "number", "always"),

    # experience, the years questions that recur per technology
    ("total_years", "How many years of professional experience do you have?", "number", "always"),
    ("python_years", "Years of experience with Python", "number", "always"),
    ("sql_years", "Years of experience with SQL", "number", "always"),
    ("spark_years", "Years of experience with Apache Spark", "number", "always"),
    ("cloud_years", "Years of experience with AWS", "number", "always"),
    ("current_title", "What is your current job title?", "text", "always"),
    ("current_employer", "Who is your current employer?", "text", "always"),
    ("management_experience", "Do you have experience managing people?", "enum", "always"),

    # sourcing and process
    ("referral", "How did you hear about this role?", "text", "never"),
    ("applied_before", "Have you applied to this company before?", "enum", "never"),
    ("worked_before", "Have you ever been employed by this company?", "enum", "always"),
    ("related_employees", "Do you know anyone who works here?", "enum", "never"),
    ("portfolio", "Link to your portfolio or GitHub", "text", "always"),
    ("linkedin", "Link to your LinkedIn profile", "text", "always"),

    # free text — company-specific by nature, so never reused
    ("why_company", "Why do you want to work here?", "text", "never"),
    ("why_role", "Why are you interested in this role?", "text", "never"),
    ("cover_note", "Anything else you would like us to know?", "text", "never"),

    # demographic, where asked
    ("gender", "Gender", "enum", "always"),
    ("ethnicity", "Ethnicity", "enum", "always"),
    ("disability", "Do you consider yourself to have a disability?", "enum", "always"),
    ("veteran", "Veteran status", "enum", "always"),
]

HEADER = """# answer-bank.yaml — answers to the questions forms ask.
#
# Fill `value` for anything you will be asked. For a "years of X" question say
# it plainly, e.g. `stated: "6 years"`, and `jam answers --fill` converts it to
# a `since` date so the answer stays true next year without maintenance.
#
# reuse:
#   always          the same answer every time
#   per_archetype   may differ by the kind of role
#   never           written fresh for each application. NOT an optimisation:
#                   without it a paragraph about one company reaches another.
#
# Empty entries are simply unanswered. The agent asks about them once and
# records what you say.
"""


def starter() -> list[dict]:
    return [{"slot": slot, "question": question, "type": kind,
             "reuse": reuse, "value": None}
            for slot, question, kind, reuse in STANDARD]


# Where a question is already answered by the master profile. Prefilling these
# is the difference between a form the human fills and one they abandon: what
# is left is only what the master genuinely does not know.
FROM_MASTER = {
    "location":         ("identity", "location"),
    "linkedin":         ("identity", "linkedin"),
    "portfolio":        ("identity", "github"),
}

SKILL_YEARS = {
    "python_years": "python", "sql_years": "sql",
    "spark_years": "pyspark", "cloud_years": "aws",
}


def _find_skill(master: dict, key: str) -> dict | None:
    for group in (master.get("skills") or {}).values():
        if key in group:
            return group[key] or {}
    return None


def prefill(entries: list[dict], master: dict) -> int:
    """Answer what the master already holds. Returns how many were filled."""
    filled = 0
    current = next((e for e in master.get("experience") or []
                    if e.get("to") is None), None)
    education = (master.get("education") or [None])[0]

    direct = {}
    for slot, (section, field) in FROM_MASTER.items():
        value = (master.get(section) or {}).get(field)
        if value:
            direct[slot] = value
    if current:
        direct["current_title"] = current.get("title")
        direct["current_employer"] = current.get("company")
    if education:
        direct["university"] = education.get("institution")
        direct["degree"] = education.get("degree")

    for entry in entries:
        slot = entry["slot"]
        if slot in direct and direct[slot]:
            entry["value"] = direct[slot]
            filled += 1
        elif slot in SKILL_YEARS:
            skill = _find_skill(master, SKILL_YEARS[slot])
            if skill and skill.get("since"):
                entry["since"] = str(skill["since"])
                entry["granularity"] = 0.5
                entry.pop("value", None)
                filled += 1
        elif slot == "total_years" and master.get("career_start"):
            entry["since"] = str(master["career_start"])
            entry["granularity"] = 0.5
            entry.pop("value", None)
            filled += 1
    return filled
