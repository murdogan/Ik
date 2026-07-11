from __future__ import annotations

from datetime import UTC, datetime
from inspect import Parameter, signature
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest
from app.modules.core.application.events import (
    FeatureFlagChangedEvent,
    PlatformEventType,
    TenantCreatedEvent,
    TenantSettingChangedEvent,
    TenantSettingField,
    TenantStatusChangedEvent,
)
from app.modules.core.domain.feature_flags import FeatureFlagKey
from app.modules.core.domain.tenant import TenantPlan, TenantRegion, TenantStatus
from app.platform.events import (
    DEFAULT_PLATFORM_EVENT_RECORDER,
    PlatformEventActorType,
    PlatformEventContract,
    RecordingPlatformEventRecorder,
)
from app.services.tenant_commands import TenantCommandHandler
from pydantic import ValidationError

EVENT_ID = UUID("10000000-0000-4000-8000-000000000001")
TENANT_ID = UUID("20000000-0000-4000-8000-000000000002")
OCCURRED_AT = datetime(2026, 7, 11, 14, 30, tzinfo=UTC)
REQUEST_ID = "req_f1d_platform_event_001"
TRACE_ID = "0123456789abcdef0123456789abcdef"
FEATURE_KEY = next(iter(FeatureFlagKey))

FIXED_METADATA = {
    "scope_type": "tenant",
    "category": "platform_operations",
    "severity": "info",
    "result": "success",
    "data_classification": "platform_metadata",
    "visibility_class": "platform_ops",
}


def _base_fields() -> dict[str, Any]:
    return {
        "id": EVENT_ID,
        "occurred_at": OCCURRED_AT,
        "tenant_id": TENANT_ID,
        "resource_id": TENANT_ID,
        "actor_type": PlatformEventActorType.PLATFORM_ADMIN,
        "request_id": REQUEST_ID,
        "trace_id": TRACE_ID,
    }


def _event_factories() -> tuple[tuple[type[Any], dict[str, Any]], ...]:
    return (
        (
            TenantCreatedEvent,
            {
                **_base_fields(),
                "plan_code": TenantPlan.CORE,
                "data_region": TenantRegion.TR_1,
            },
        ),
        (
            TenantStatusChangedEvent,
            {
                **_base_fields(),
                "before_status": TenantStatus.PROVISIONING,
                "after_status": TenantStatus.ACTIVE,
            },
        ),
        (
            TenantSettingChangedEvent,
            {
                **_base_fields(),
                "changed_fields": (
                    TenantSettingField.PLAN_CODE,
                    TenantSettingField.ACTIVE_EMPLOYEE_LIMIT,
                ),
            },
        ),
        (
            FeatureFlagChangedEvent,
            {
                **_base_fields(),
                "feature_key": FEATURE_KEY,
                "before_enabled": False,
                "after_enabled": True,
            },
        ),
    )


def test_four_event_contracts_have_fixed_redacted_audit_metadata() -> None:
    events = [event_class(**fields) for event_class, fields in _event_factories()]

    assert [event.event_type for event in events] == list(PlatformEventType)
    assert set(PlatformEventType) == {
        PlatformEventType.TENANT_CREATED,
        PlatformEventType.TENANT_STATUS_CHANGED,
        PlatformEventType.TENANT_SETTING_CHANGED,
        PlatformEventType.FEATURE_FLAG_CHANGED,
    }
    for event in events:
        dumped = event.model_dump(mode="json")
        assert {key: dumped[key] for key in FIXED_METADATA} == FIXED_METADATA
        assert dumped["id"] == str(EVENT_ID)
        assert dumped["tenant_id"] == str(TENANT_ID)
        assert dumped["resource_id"] == str(TENANT_ID)
        assert dumped["request_id"] == REQUEST_ID
        assert dumped["trace_id"] == TRACE_ID
        assert "payload" not in dumped
        assert "metadata" not in dumped
        assert "before_data" not in dumped
        assert "after_data" not in dumped


@pytest.mark.parametrize(
    "forbidden_field",
    [
        "password",
        "password_hash",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "cookie",
        "secret",
        "otp",
        "employee",
        "employee_id",
        "employee_payload",
        "hr_payload",
        "sensitive_hr_data",
        "salary",
        "tckn",
        "iban",
        "health_data",
        "leave_payload",
        "document_body",
        "metadata",
        "payload",
        "before_data",
        "after_data",
    ],
)
def test_every_contract_structurally_rejects_secret_and_hr_fields(
    forbidden_field: str,
) -> None:
    for event_class, valid_fields in _event_factories():
        with pytest.raises(ValidationError):
            event_class(**valid_fields, **{forbidden_field: "must-not-enter-event"})


def test_event_contracts_are_frozen_and_deep_values_are_closed_types() -> None:
    event = TenantSettingChangedEvent(
        **_base_fields(),
        changed_fields=(TenantSettingField.LOCALE,),
    )

    with pytest.raises(ValidationError):
        event.changed_fields = (TenantSettingField.TIMEZONE,)

    assert isinstance(event.changed_fields, tuple)
    assert all(isinstance(field, TenantSettingField) for field in event.changed_fields)
    assert not any(
        field.annotation in {dict, object}
        for event_class, _ in _event_factories()
        for field in event_class.model_fields.values()
    )


@pytest.mark.parametrize("uuid_field", ["id", "tenant_id", "resource_id"])
def test_event_identifiers_must_be_nonzero_uuids(uuid_field: str) -> None:
    fields = {
        **_base_fields(),
        uuid_field: UUID(int=0),
        "plan_code": TenantPlan.CORE,
        "data_region": TenantRegion.TR_1,
    }

    with pytest.raises(ValidationError, match="non-zero UUID"):
        TenantCreatedEvent(**fields)


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("occurred_at", datetime(2026, 7, 11, 14, 30)),
        ("request_id", "person@example.test"),
        ("request_id", "header.payload.signature"),
        ("trace_id", "0" * 32),
        ("trace_id", "ABCDEF0123456789ABCDEF0123456789"),
        ("actor_type", "support-session-with-free-text"),
        ("scope_type", "platform"),
        ("category", "hr_operations"),
        ("result", "failed"),
        ("data_classification", "sensitive_hr"),
        ("visibility_class", "hr_operations"),
        ("resource_id", UUID("30000000-0000-4000-8000-000000000003")),
        ("actor_user_id", UUID(int=0)),
        ("session_id", UUID(int=0)),
        ("support_session_id", UUID(int=0)),
        ("resource_type", "employee"),
        ("action", "export_hr_data"),
    ],
)
def test_event_metadata_rejects_unsafe_or_nonfixed_values(
    field_name: str,
    invalid_value: object,
) -> None:
    fields = {
        **_base_fields(),
        field_name: invalid_value,
        "plan_code": TenantPlan.CORE,
        "data_region": TenantRegion.TR_1,
    }

    with pytest.raises(ValidationError):
        TenantCreatedEvent(**fields)


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("event_type", "tenant.deleted"),
        ("status", TenantStatus.ACTIVE),
        ("plan_code", "unlimited"),
        ("data_region", "customer-specific-region"),
    ],
)
def test_tenant_created_uses_typed_provisioning_plan_and_region(
    field_name: str,
    invalid_value: object,
) -> None:
    fields = {
        **_base_fields(),
        "plan_code": TenantPlan.PROFESSIONAL,
        "data_region": TenantRegion.EU_1,
        field_name: invalid_value,
    }

    with pytest.raises(ValidationError):
        TenantCreatedEvent(**fields)


def test_status_event_requires_two_distinct_typed_statuses() -> None:
    with pytest.raises(ValidationError, match="actual status change"):
        TenantStatusChangedEvent(
            **_base_fields(),
            before_status=TenantStatus.ACTIVE,
            after_status=TenantStatus.ACTIVE,
        )
    with pytest.raises(ValidationError):
        TenantStatusChangedEvent(
            **_base_fields(),
            before_status="customer-specific-status",
            after_status=TenantStatus.ACTIVE,
        )


@pytest.mark.parametrize(
    "changed_fields",
    [
        (),
        (TenantSettingField.LOCALE, TenantSettingField.LOCALE),
        ("password",),
        ("employee_payload",),
        ("arbitrary_customer_setting",),
    ],
)
def test_setting_event_accepts_only_nonempty_unique_allowlisted_field_tuple(
    changed_fields: tuple[object, ...],
) -> None:
    with pytest.raises(ValidationError):
        TenantSettingChangedEvent(
            **_base_fields(),
            changed_fields=changed_fields,
        )


@pytest.mark.parametrize(
    "invalid_fields",
    [
        {"feature_key": "customer_specific_fork"},
        {"before_enabled": 0},
        {"after_enabled": 1},
        {"before_enabled": "false"},
        {"after_enabled": "true"},
    ],
)
def test_feature_event_accepts_only_typed_key_and_strict_booleans(
    invalid_fields: dict[str, object],
) -> None:
    fields = {
        **_base_fields(),
        "feature_key": FEATURE_KEY,
        "before_enabled": False,
        "after_enabled": True,
        **invalid_fields,
    }

    with pytest.raises(ValidationError):
        FeatureFlagChangedEvent(**fields)


def test_feature_event_requires_an_actual_boolean_transition() -> None:
    with pytest.raises(ValidationError, match="actual enabled-state change"):
        FeatureFlagChangedEvent(
            **_base_fields(),
            feature_key=FEATURE_KEY,
            before_enabled=True,
            after_enabled=True,
        )


async def test_recorders_are_async_replaceable_and_test_fake_exposes_tuple() -> None:
    event = FeatureFlagChangedEvent(
        **_base_fields(),
        feature_key=FEATURE_KEY,
        before_enabled=False,
        after_enabled=True,
    )
    recorder = RecordingPlatformEventRecorder()

    await recorder.record(event)
    await DEFAULT_PLATFORM_EVENT_RECORDER.record(event)

    assert recorder.events == (event,)
    assert isinstance(recorder.events, tuple)
    with pytest.raises(TypeError, match="approved closed platform event contract"):
        await recorder.record(cast(Any, object()))
    malicious_structural_event = SimpleNamespace(
        **event.model_dump(),
        password="must-not-cross-recorder-boundary",
    )
    with pytest.raises(TypeError, match="approved closed platform event contract"):
        await recorder.record(cast(Any, malicious_structural_event))


async def test_recorders_reject_marker_and_sensitive_field_event_subclasses() -> None:
    class CredentialBearingTenantCreatedEvent(TenantCreatedEvent):
        password: str

    sensitive_event = CredentialBearingTenantCreatedEvent(
        **_base_fields(),
        plan_code=TenantPlan.CORE,
        data_region=TenantRegion.TR_1,
        password="must-not-cross-recorder-boundary",
    )

    for recorder in (RecordingPlatformEventRecorder(), DEFAULT_PLATFORM_EVENT_RECORDER):
        with pytest.raises(TypeError, match="approved closed platform event contract"):
            await recorder.record(cast(Any, PlatformEventContract()))
        with pytest.raises(TypeError, match="approved closed platform event contract"):
            await recorder.record(cast(Any, sensitive_event))


def test_every_tenant_command_requires_an_explicit_safe_request_context() -> None:
    for method_name in (
        "create_tenant",
        "update_tenant",
        "update_tenant_settings",
        "update_tenant_features",
    ):
        parameter = signature(getattr(TenantCommandHandler, method_name)).parameters[
            "request_context"
        ]
        assert parameter.kind is Parameter.KEYWORD_ONLY
        assert parameter.default is Parameter.empty
