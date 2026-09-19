from __future__ import annotations

import pytest

from app.security.policies import classify_action, is_destructive, requires_approval


@pytest.mark.parametrize(
    ("actions", "expected"),
    [
        ([], "READ"),
        (["Check database availability"], "RECOMMEND"),
        (["Restart the affected service"], "CHANGE"),
        (["Roll back to the previous deployment"], "CHANGE"),
        (["Delete the corrupted table"], "DELETE"),
        (["Drop the stale partition"], "DELETE"),
        (["rm -rf the temp directory"], "DELETE"),
    ],
)
def test_classify_action(actions, expected):
    assert classify_action(actions) == expected


def test_is_destructive():
    assert is_destructive("DELETE") is True
    assert is_destructive("CHANGE") is False
    assert is_destructive("READ") is False


def test_delete_always_requires_approval_even_in_dev():
    assert (
        requires_approval(
            action_class="DELETE",
            environment="development",
            severity="low",
            llm_parse_failed=False,
            security_violation=False,
        )
        is True
    )


def test_read_in_dev_never_requires_approval():
    assert (
        requires_approval(
            action_class="READ",
            environment="development",
            severity="low",
            llm_parse_failed=False,
            security_violation=False,
        )
        is False
    )


def test_change_in_production_requires_approval():
    assert (
        requires_approval(
            action_class="CHANGE",
            environment="production",
            severity="low",
            llm_parse_failed=False,
            security_violation=False,
        )
        is True
    )


def test_change_in_development_does_not_require_approval():
    assert (
        requires_approval(
            action_class="CHANGE",
            environment="development",
            severity="low",
            llm_parse_failed=False,
            security_violation=False,
        )
        is False
    )


def test_high_severity_in_production_requires_approval_even_if_recommend():
    assert (
        requires_approval(
            action_class="RECOMMEND",
            environment="production",
            severity="critical",
            llm_parse_failed=False,
            security_violation=False,
        )
        is True
    )


def test_degraded_analysis_always_requires_approval():
    assert (
        requires_approval(
            action_class="READ",
            environment="development",
            severity="low",
            llm_parse_failed=True,
            security_violation=False,
        )
        is True
    )


def test_security_violation_takes_precedence_even_over_llm_parse_failed():
    """Sugestão do code review de IA (docs/qa/code-review-fase7-security.md,
    item 1): confirma explicitamente que security_violation tem precedência
    mesmo quando a análise TAMBÉM falhou (llm_parse_failed) — ambas as
    flags 'puxariam' para True isoladamente, mas o bloqueio já aconteceu
    antes (finalize_blocked), então pedir aprovação não faz sentido."""
    assert (
        requires_approval(
            action_class="DELETE",
            environment="production",
            severity="critical",
            llm_parse_failed=True,
            security_violation=True,
        )
        is False
    )


def test_security_violation_never_requires_approval_its_already_blocked():
    # já foi bloqueado antes (finalize_blocked) — não faz sentido pedir aprovação
    assert (
        requires_approval(
            action_class="DELETE",
            environment="production",
            severity="critical",
            llm_parse_failed=False,
            security_violation=True,
        )
        is False
    )
