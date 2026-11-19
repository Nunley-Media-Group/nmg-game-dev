"""The environment-piece geometry rule is documented where authors read it (#144).

SCN008 (AC8): docs/asset-contract.md section 3, skills/model-asset/SKILL.md, and
docs/skills/model-asset.md each state the open-sheet, winding, outward-facing closed-part, and
touching-primitive rules that geometry.normals and geometry.duplicates apply.
"""

from __future__ import annotations

import re

from tests.ship_fakes import REPO_ROOT

CONTRACT = REPO_ROOT / "docs" / "asset-contract.md"
SKILL = REPO_ROOT / "skills" / "model-asset" / "SKILL.md"
DOC = REPO_ROOT / "docs" / "skills" / "model-asset.md"
DOCUMENTS = (CONTRACT, SKILL, DOC)
OLD_NORMALS_WORDING = "faces whose normals are inconsistent or inward"


def _contract_section_3(text: str) -> str:
    start = text.index("## 3. Geometry")
    return text[start : text.index("## 4.", start)]


def _assert_rule(text: str, where: str) -> None:
    lowered = text.lower()
    assert re.search(r"open sheets?", lowered), f"{where} does not name open sheets"
    assert re.search(r"\bwound\b|\bwinding\b", lowered), f"{where} does not name winding"
    assert "outward" in lowered, f"{where} does not say closed parts face outward"
    assert "geometry.duplicates" in text, f"{where} does not name geometry.duplicates"
    assert "0.6 mm" in text, f"{where} does not give the 0.6 mm spacing"
    assert "merge" in lowered, f"{where} does not say touching primitives merge"


def test_each_document_states_the_authoring_rule() -> None:
    """SCN008: every document names the open-sheet, winding, closed-part, and touching rules."""
    for path in DOCUMENTS:
        _assert_rule(path.read_text(encoding="utf-8"), path.relative_to(REPO_ROOT).as_posix())


def test_contract_section_3_carries_the_rule_itself() -> None:
    """SCN008: section 3 of the asset contract, not just elsewhere in the file, carries the rule."""
    section = _contract_section_3(CONTRACT.read_text(encoding="utf-8"))
    _assert_rule(section, "docs/asset-contract.md section 3")


def test_consumer_doc_no_longer_describes_normals_as_a_flat_count() -> None:
    """SCN008: the model-asset doc describes geometry.normals per island, not as one flat count."""
    text = DOC.read_text(encoding="utf-8")
    assert OLD_NORMALS_WORDING not in text
    assert "connected island" in text


def test_each_document_names_the_twist_seam_rule() -> None:
    """#243 FR6: every document names geometry.twist_seam and says it is a reversed-winding seam."""
    for path in DOCUMENTS:
        text = path.read_text(encoding="utf-8")
        where = path.relative_to(REPO_ROOT).as_posix()
        assert "geometry.twist_seam" in text, f"{where} does not name geometry.twist_seam"
        assert "reversed winding" in text.lower(), f"{where} does not describe the twist seam"
    section = _contract_section_3(CONTRACT.read_text(encoding="utf-8"))
    assert "geometry.twist_seam" in section, "asset contract section 3 does not name the rule"


def test_consumer_doc_locates_twist_seam_samples_on_edges() -> None:
    """#243: a geometry.twist_seam sample is an edge index located at the edge midpoint."""
    text = " ".join(DOC.read_text(encoding="utf-8").split())
    assert "the edge index (`geometry.twist_seam`)" in text
    assert "edge midpoint for a `geometry.twist_seam` edge" in text
