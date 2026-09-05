"""Renderer tests.

They run against a fixture, never against data/ — the real profile is private
and absent from git (D56), so a test that read it would fail on a clean clone.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from hub import factgate, render

FIXTURE = Path(__file__).parent / "fixtures" / "master-min.yaml"


@pytest.fixture
def master() -> dict:
    return yaml.safe_load(FIXTURE.read_text())


def profile(**over) -> dict:
    base = {
        "name": "test",
        "sections": ["skills", "experience", "projects", "education", "certifications"],
        "emphasis": [],
        "drop": [],
    }
    base.update(over)
    return base


class TestEscaping:
    def test_specials_are_escaped(self):
        assert render.tex("100% & $5 #1 a_b") == r"100\% \& \$5 \#1 a\_b"

    def test_tilde_means_approximately_not_a_diacritic(self):
        # "~18%" in prose reads "about 18%". \textasciitilde renders as a
        # raised mark; $\sim$ is what the sentence actually means.
        assert render.tex("~18%") == r"$\sim$18\%"

    def test_backslash_does_not_escape_its_own_replacement(self):
        assert render.tex(r"a\b") == r"a\textbackslash{}b"

    def test_folded_yaml_newlines_collapse(self):
        assert render.tex("one\n  two\n\n three") == "one two three"


class TestDates:
    def test_month_year(self):
        assert render.month("2024-08") == "Aug 2024"

    def test_single_digit_month(self):
        assert render.month("2022-01") == "Jan 2022"

    def test_null_end_date_means_current_role(self):
        assert render.month(None) == "Present"


class TestSkills:
    def test_known_abbreviations_survive_titlecasing(self, master):
        names = render.flatten_skills(master["skills"], drop=set())
        assert "SQL" in names and "Relational DB" in names and "DuckDB" in names
        assert "Sql" not in names and "Relational Db" not in names

    def test_drop_by_bare_key_and_by_group_path(self, master):
        assert "Python" not in render.flatten_skills(master["skills"], {"python"})
        assert "SQL" not in render.flatten_skills(master["skills"], {"languages.sql"})


class TestDrop:
    def test_single_bullet_by_index(self, master):
        out = render.render(master, profile(drop=["acme.1"]))
        assert "Second bullet that a profile may drop" not in out
        assert "Cut costs by 12" in out

    def test_whole_job(self, master):
        out = render.render(master, profile(drop=["initech"]))
        assert "Initech" not in out

    def test_project_bullet_by_index(self, master):
        out = render.render(master, profile(drop=["widget.0"]))
        assert "Project bullet one" not in out
        assert "Project bullet two" in out

    def test_section_omitted_when_not_listed(self, master):
        out = render.render(master, profile(sections=["experience"]))
        assert "PROJECTS" not in out and "CERTIFICATIONS" not in out


class TestNoFabrication:
    def test_emphasis_only_reorders_never_adds(self, master):
        """Emphasis must not introduce a skill the master lacks (D44)."""
        plain = render.render(master, profile())
        moved = render.render(master, profile(emphasis=["duckdb", "kubernetes"]))
        assert "Kubernetes" not in moved

        def skills_of(doc: str) -> set[str]:
            body = doc.split(r"\begin{rSection}{SKILLS}")[1].split(r"\end{rSection}")[0]
            return {t.strip() for t in body.replace(r"\textbf{", "").replace("}", "")
                    .split(",") if t.strip()}

        assert skills_of(plain) == skills_of(moved)

    def test_every_rendered_bullet_exists_in_the_master(self, master):
        out = render.render(master, profile())
        for job in master["experience"]:
            for b in job["bullets"]:
                assert render.tex(b) in out


class TestDocumentShape:
    def test_compiles_to_a_complete_latex_document(self, master):
        out = render.render(master, profile())
        assert out.startswith(r"\documentclass{resume}")
        assert out.rstrip().endswith(r"\end{document}")
        assert out.count(r"\begin{itemize}") == out.count(r"\end{itemize}")


class TestTailoringSpec:
    def test_default_drops_nothing_and_has_no_page_limit(self):
        spec = render.default_tailoring()
        assert spec["drop"] == [] and spec["max_pages"] is None

    def test_name_comes_from_the_folder_when_the_file_omits_it(self, tmp_path):
        app = tmp_path / "2026-09-05--acme--data-engineer"
        app.mkdir()
        f = app / "tailoring.yaml"
        f.write_text("max_pages: 1\ndrop: [initech]\n")
        spec = render.load_tailoring(f)
        assert spec["name"] == "2026-09-05--acme--data-engineer"
        assert spec["max_pages"] == 1 and spec["drop"] == ["initech"]

    def test_declared_name_wins(self, tmp_path):
        f = tmp_path / "tailoring.yaml"
        f.write_text("name: custom\n")
        assert render.load_tailoring(f)["name"] == "custom"

    def test_no_file_means_the_bare_master(self):
        assert render.load_tailoring(None) == render.default_tailoring()


class TestIdentity:
    def test_link_label_is_derived_not_hardcoded(self):
        assert render.link_label("https://www.linkedin.com/in/example") == "linkedin.com/in/example"
        assert render.link_label("https://github.com/example/") == "github.com/example"

    def test_header_follows_the_profile(self, master):
        out = render.render(master, profile())
        assert "linkedin.com/in/example" in out and "github.com/example" in out
        assert "Ada Lovelace" in out


class TestGateWiring:
    """The gate composes with the renderer, in both directions."""

    def test_a_faithful_render_passes(self, master):
        doc = render.render(master, profile())
        r = factgate.verify(render.strip_tex(doc), render.source_text(master),
                            allow=render.TEMPLATE_WORDS)
        assert r.ok, r.report()

    def test_it_flags_content_the_source_lacks(self, master):
        """Proof the gate has teeth: drop a job from the source, keep it in
        the document, and its facts must be reported as invented."""
        doc = render.render(master, profile())
        thinner = {**master, "experience": [master["experience"][0]]}
        r = factgate.verify(render.strip_tex(doc), render.source_text(thinner),
                            allow=render.TEMPLATE_WORDS)
        assert not r.ok
        assert "initech" in r.invented_names

    def test_skill_display_names_come_from_keys_not_values(self, master):
        src = render.source_text(master)
        # `relational_db` is a KEY; the renderer prints "Relational DB".
        assert "Relational DB" in src and "relational_db" in src

    def test_layout_dimensions_are_not_numeric_claims(self):
        stripped = render.strip_tex(r"\usepackage[left=0.4in]{geometry} \vspace{-1.25em} text")
        assert factgate.numbers(stripped) == set()

    def test_escaped_percent_keeps_its_sign(self):
        # "12\%" left the backslash behind, so the claim read as a bare 12.
        assert factgate.numbers(render.strip_tex(r"costs by 12\% annually")) == {"12%"}
