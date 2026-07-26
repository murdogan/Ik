from __future__ import annotations

import argparse
from pathlib import Path

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


def _verified_object_backup(tmp_path: Path) -> recovery.VerifiedBackup:
    return recovery.VerifiedBackup(
        backup_directory=tmp_path,
        manifest={
            "object_storage": {
                "aggregate_sha256": "a" * 64,
                "object_count": 1,
                "state": "included",
                "total_bytes": 7,
            }
        },
    )


def test_object_proof_requires_explicit_synthetic_data_confirmation(
    tmp_path: Path,
) -> None:
    args = argparse.Namespace(
        confirm_synthetic_object_data=False,
        include_objects=True,
        proof_object_alias="proof",
        proof_object_bucket="proof-bucket",
    )

    with pytest.raises(recovery.RecoveryError) as error:
        recovery._proof_object_configuration(args, _verified_object_backup(tmp_path))

    assert error.value.reason_code == "RESTORE_GUARD_REJECTED"


def test_object_proof_cleans_remote_target_after_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    commands: list[tuple[str, ...]] = []
    empty_checks: list[str] = []

    monkeypatch.setattr(recovery, "_mc_environment", dict)
    monkeypatch.setattr(
        recovery,
        "_ensure_proof_bucket_empty",
        lambda _mc, _alias, bucket, _timeout: empty_checks.append(bucket),
    )
    monkeypatch.setattr(
        recovery,
        "_run_command",
        lambda command, **_kwargs: commands.append(tuple(command)),
    )
    monkeypatch.setattr(
        recovery,
        "_remote_object_aggregate",
        lambda *_args: recovery.ObjectAggregate("a" * 64, 1, 7, ()),
    )

    result = recovery._restore_and_verify_objects(
        "mc", _verified_object_backup(tmp_path), "proof", "proof-bucket", 30
    )

    assert result == {"object_count": 1, "status": "verified", "total_bytes": 7}
    assert commands[-1] == (
        "mc",
        "rm",
        "--recursive",
        "--force",
        "proof/proof-bucket",
    )
    assert empty_checks == ["proof-bucket", "proof-bucket"]


def test_object_proof_cleans_remote_target_after_mirror_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    commands: list[tuple[str, ...]] = []
    monkeypatch.setattr(recovery, "_mc_environment", dict)
    monkeypatch.setattr(recovery, "_ensure_proof_bucket_empty", lambda *_args: None)

    def run(command: tuple[str, ...], **_kwargs: object) -> None:
        commands.append(tuple(command))
        if command[1] == "mirror":
            raise recovery.RecoveryError("OBJECT_OPERATION_FAILED")

    monkeypatch.setattr(recovery, "_run_command", run)

    with pytest.raises(recovery.RecoveryError) as error:
        recovery._restore_and_verify_objects(
            "mc", _verified_object_backup(tmp_path), "proof", "proof-bucket", 30
        )

    assert error.value.reason_code == "OBJECT_OPERATION_FAILED"
    assert commands[-1][1:] == (
        "rm",
        "--recursive",
        "--force",
        "proof/proof-bucket",
    )
