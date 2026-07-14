from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from uuid import UUID

import pytest
from app.api.auth_dependencies import (
    AuthenticatedSession,
    get_authenticated_request_context,
)
from app.platform.errors import ApiError
from app.platform.identity import AccessPrincipal
from app.platform.request_context import (
    AuthenticationStrength,
    RequestContext,
    SupportSessionMetadata,
)
from app.platform.tenancy import TenantContext

REQUEST_ID = "request-opaque-001"
TRACE_ID = "0123456789abcdef0123456789abcdef"
TENANT_ID = UUID("11111111-1111-4111-8111-111111111111")
ACTOR_ID = UUID("22222222-2222-4222-8222-222222222222")
MEMBERSHIP_ID = UUID("66666666-6666-4666-8666-666666666666")
SESSION_ID = UUID("33333333-3333-4333-8333-333333333333")
SUPPORT_SESSION_ID = UUID("44444444-4444-4444-8444-444444444444")
SUPPORT_OPERATOR_ID = UUID("55555555-5555-4555-8555-555555555555")


def test_request_context_and_nested_metadata_are_deeply_immutable() -> None:
    tenant = TenantContext(tenant_id=TENANT_ID, slug="private-tenant-slug")
    support = SupportSessionMetadata(
        support_session_id=SUPPORT_SESSION_ID,
        operator_actor_id=SUPPORT_OPERATOR_ID,
    )
    context = RequestContext(
        request_id=REQUEST_ID,
        trace_id=TRACE_ID,
        tenant=tenant,
        actor_id=ACTOR_ID,
        membership_id=MEMBERSHIP_ID,
        session_id=SESSION_ID,
        authentication_strength=AuthenticationStrength.STEP_UP,
        support_session=support,
    )

    with pytest.raises(FrozenInstanceError):
        context.actor_id = None  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        context.tenant.slug = "mutated"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        context.support_session.operator_actor_id = None  # type: ignore[misc,union-attr]
    assert not hasattr(context, "__dict__")
    assert not hasattr(context.tenant, "__dict__")
    assert not hasattr(context.support_session, "__dict__")


def test_derive_returns_new_context_and_preserves_correlation_ids() -> None:
    context = RequestContext(request_id=REQUEST_ID, trace_id=TRACE_ID)
    tenant = TenantContext(tenant_id=TENANT_ID, slug="wealthy-falcon")

    enriched = context.derive(
        tenant=tenant,
        actor_id=ACTOR_ID,
        membership_id=MEMBERSHIP_ID,
        session_id=SESSION_ID,
        authentication_strength=AuthenticationStrength.MULTI_FACTOR,
    )

    assert enriched is not context
    assert context.tenant is None
    assert enriched.request_id == context.request_id
    assert enriched.trace_id == context.trace_id
    assert enriched.require_tenant() is tenant
    assert enriched.actor_id == ACTOR_ID
    assert enriched.require_membership() == MEMBERSHIP_ID
    assert enriched.authentication_strength is AuthenticationStrength.MULTI_FACTOR


def test_require_tenant_fails_closed_for_unscoped_context() -> None:
    context = RequestContext(request_id=REQUEST_ID, trace_id=TRACE_ID)

    with pytest.raises(RuntimeError, match="tenant-scoped"):
        context.require_tenant()
    with pytest.raises(RuntimeError, match="membership"):
        context.require_membership()


@pytest.mark.parametrize(
    "request_id",
    [
        " leading-space",
        "trailing-space ",
        "contains@email",
        "contains/slash",
        "contains\nnewline",
        "eyJhbGciOi.none.signature",
        "x" * 129,
    ],
)
def test_request_context_rejects_unsafe_request_ids(request_id: str) -> None:
    with pytest.raises(ValueError, match="request_id"):
        RequestContext(request_id=request_id, trace_id=TRACE_ID)


@pytest.mark.parametrize(
    "trace_id",
    [
        "0" * 32,
        "0123456789ABCDEF0123456789ABCDEF",
        "0123456789abcdef",
        "g123456789abcdef0123456789abcdef",
    ],
)
def test_request_context_rejects_noncanonical_trace_ids(trace_id: str) -> None:
    with pytest.raises(ValueError, match="trace_id"):
        RequestContext(request_id=REQUEST_ID, trace_id=trace_id)


def test_request_context_rejects_untyped_auth_and_zero_uuid_placeholders() -> None:
    with pytest.raises(TypeError, match="AuthenticationStrength"):
        RequestContext(
            request_id=REQUEST_ID,
            trace_id=TRACE_ID,
            authentication_strength="step_up",  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="actor_id"):
        RequestContext(request_id=REQUEST_ID, trace_id=TRACE_ID, actor_id=UUID(int=0))
    with pytest.raises(ValueError, match="membership_id"):
        RequestContext(request_id=REQUEST_ID, trace_id=TRACE_ID, membership_id=UUID(int=0))
    with pytest.raises(ValueError, match="support_session_id"):
        SupportSessionMetadata(support_session_id=UUID(int=0))


def test_safe_metadata_is_frozen_and_excludes_slug_sources_and_free_text() -> None:
    context = RequestContext(
        request_id=REQUEST_ID,
        trace_id=TRACE_ID,
        tenant=TenantContext(tenant_id=TENANT_ID, slug="ada@example.test"),
        actor_id=ACTOR_ID,
        session_id=SESSION_ID,
        authentication_strength=AuthenticationStrength.STEP_UP,
        support_session=SupportSessionMetadata(
            support_session_id=SUPPORT_SESSION_ID,
            operator_actor_id=SUPPORT_OPERATOR_ID,
        ),
    )

    assert dict(context.safe_error_metadata()) == {
        "request_id": REQUEST_ID,
        "trace_id": TRACE_ID,
    }
    assert dict(context.safe_log_metadata()) == {
        "request_id": REQUEST_ID,
        "trace_id": TRACE_ID,
        "authentication_strength": "step_up",
        "tenant_id": str(TENANT_ID),
        "support_session_id": str(SUPPORT_SESSION_ID),
    }
    with pytest.raises(TypeError):
        context.safe_log_metadata()["authorization"] = "Bearer secret"  # type: ignore[index]
    assert "ada@example.test" not in repr(context.safe_log_metadata())


def test_worker_serialization_is_tenant_required_and_strictly_allowlisted() -> None:
    unscoped = RequestContext(request_id=REQUEST_ID, trace_id=TRACE_ID)
    with pytest.raises(RuntimeError, match="tenant-scoped"):
        unscoped.serialize_for_worker()

    scoped = unscoped.derive(
        tenant=TenantContext(tenant_id=TENANT_ID, slug="never-serialized"),
        actor_id=ACTOR_ID,
        membership_id=MEMBERSHIP_ID,
        session_id=SESSION_ID,
        authentication_strength=AuthenticationStrength.SINGLE_FACTOR,
        support_session=SupportSessionMetadata(
            support_session_id=SUPPORT_SESSION_ID,
            operator_actor_id=SUPPORT_OPERATOR_ID,
        ),
    )

    assert scoped.serialize_for_worker() == scoped.to_worker_context() == {
        "request_id": REQUEST_ID,
        "trace_id": TRACE_ID,
        "tenant_id": str(TENANT_ID),
        "actor_id": str(ACTOR_ID),
        "membership_id": str(MEMBERSHIP_ID),
        "session_id": str(SESSION_ID),
        "authentication_strength": "single_factor",
        "support_session_id": str(SUPPORT_SESSION_ID),
        "support_operator_actor_id": str(SUPPORT_OPERATOR_ID),
    }
    assert "never-serialized" not in repr(scoped.serialize_for_worker())


def test_authenticated_context_rejects_a_membership_mismatch_even_when_actor_matches() -> None:
    principal = AccessPrincipal(
        user_id=ACTOR_ID,
        tenant_id=TENANT_ID,
        membership_id=MEMBERSHIP_ID,
        tenant_slug="wealthy-falcon",
        session_family_id=SESSION_ID,
    )
    authenticated = AuthenticatedSession(
        principal=principal,
        user=SimpleNamespace(),  # type: ignore[arg-type]
    )
    valid = RequestContext(
        request_id=REQUEST_ID,
        trace_id=TRACE_ID,
        tenant=TenantContext(tenant_id=TENANT_ID, slug="wealthy-falcon"),
        actor_id=ACTOR_ID,
        membership_id=MEMBERSHIP_ID,
        session_id=SESSION_ID,
        authentication_strength=AuthenticationStrength.SINGLE_FACTOR,
    )
    request = SimpleNamespace(state=SimpleNamespace(request_context=valid))
    assert (
        get_authenticated_request_context(request, authenticated)  # type: ignore[arg-type]
        is valid
    )

    mismatched = valid.derive(membership_id=UUID("77777777-7777-4777-8777-777777777777"))
    request.state.request_context = mismatched
    with pytest.raises(ApiError) as denied:
        get_authenticated_request_context(request, authenticated)  # type: ignore[arg-type]
    assert denied.value.code == "authentication_required"
