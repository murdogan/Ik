from __future__ import annotations

import pytest

from scripts.ops import recovery


def _identity_output(value: str):
    def output(*_args: object, **_kwargs: object) -> str:
        return value

    return output


def test_proof_database_identity_accepts_postgresql_unlimited_sentinel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        recovery,
        "_psql_output",
        _identity_output("123|456|-1|ik-recovery-proof-marker"),
    )

    assert recovery._proof_database_identity(
        "psql",
        {},
        "p10_restore_proof",
        30,
        "PROOF_DATABASE_UNAVAILABLE",
    ) == (123, 456, -1, "ik-recovery-proof-marker")


def test_proof_database_identity_rejects_invalid_negative_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        recovery,
        "_psql_output",
        _identity_output("123|456|-2|ik-recovery-proof-marker"),
    )

    with pytest.raises(recovery.RecoveryError) as error:
        recovery._proof_database_identity(
            "psql",
            {},
            "p10_restore_proof",
            30,
            "PROOF_DATABASE_UNAVAILABLE",
        )

    assert error.value.reason_code == "PROOF_DATABASE_UNAVAILABLE"
