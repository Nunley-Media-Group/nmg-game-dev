"""AC10 (T006): docs/rigging-and-animation.md documents the estimate, review, and rig flow.

The guard reads the doc as it is checked in. It fails when the agent flow stops calling
estimate_landmarks before rig_humanoid, when the estimate's contract (fields, confidence values,
A-pose limit, failure codes) goes undocumented, or when the retired "never detects anatomy" line
returns.
"""

from __future__ import annotations

import pathlib
import re

import pytest

_DOC = "docs/rigging-and-animation.md"
_CONTRACT_TERMS = (
    "estimate_landmarks",
    "confidence",
    "warnings",
    "rig.arms_not_found",
    "rig.crotch_not_found",
)
_ESTIMATE_CODES = ("rig.asset_not_found", "rig.arms_not_found", "rig.crotch_not_found")
_RETIRED_SENTENCE = "never detects anatomy itself"


def _doc(repo_root: pathlib.Path) -> str:
    return (repo_root / _DOC).read_text(encoding="utf-8")


def _section(text: str, heading: str) -> str:
    """Return the text from heading up to the next level-two heading."""
    start = text.index(heading)
    following = re.search(r"\n## ", text[start + len(heading) :])
    end = start + len(heading) + following.start() if following else len(text)
    return text[start:end]


@pytest.mark.parametrize("term", _CONTRACT_TERMS)
def test_doc_names_the_estimate_contract(repo_root: pathlib.Path, term: str) -> None:
    assert term in _doc(repo_root)


def test_agent_flow_estimates_landmarks_before_it_rigs(repo_root: pathlib.Path) -> None:
    flow = _section(_doc(repo_root), "## Agent flow")
    assert "estimate_landmarks" in flow
    assert "rig_humanoid" in flow
    assert flow.index("estimate_landmarks") < flow.index("rig_humanoid")


def test_agent_flow_requires_review_when_confidence_is_low(repo_root: pathlib.Path) -> None:
    flow = _section(_doc(repo_root), "## Agent flow")
    assert "review" in flow.lower()
    assert "`low`" in flow


def test_retired_sentence_is_gone(repo_root: pathlib.Path) -> None:
    assert _RETIRED_SENTENCE not in _doc(repo_root)


def test_result_statuses_list_the_estimate_failure_codes(repo_root: pathlib.Path) -> None:
    statuses = _section(_doc(repo_root), "## Result statuses")
    for code in _ESTIMATE_CODES:
        assert f"`{code}`" in statuses, code


def test_a_pose_limit_is_documented(repo_root: pathlib.Path) -> None:
    text = _doc(repo_root)
    assert "T-pose" in text
    assert "A-pose" in text
    assert "legs apart" in text
