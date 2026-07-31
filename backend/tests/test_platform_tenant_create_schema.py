import pytest
from app.schemas.tenant import TenantInitialAdminCorrection, TenantPlatformCreate
from pydantic import ValidationError


def test_platform_tenant_create_requires_initial_admin() -> None:
    with pytest.raises(ValidationError) as exc_info:
        TenantPlatformCreate(
            slug="acme-turkiye",
            name="Acme Türkiye",
        )

    assert exc_info.value.errors(include_url=False) == [
        {
            "type": "missing",
            "loc": ("initial_admin",),
            "msg": "Field required",
            "input": {
                "slug": "acme-turkiye",
                "name": "Acme Türkiye",
            },
        }
    ]


def test_platform_tenant_create_normalizes_only_allowlisted_initial_admin_fields() -> None:
    payload = TenantPlatformCreate(
        slug="acme-turkiye",
        name="Acme Türkiye",
        initial_admin={
            "full_name": "  Ada Yönetici  ",
            "email": "  ADA.YONETICI@EXAMPLE.TEST  ",
        },
    )

    assert payload.initial_admin.model_dump() == {
        "full_name": "Ada Yönetici",
        "email": "ada.yonetici@example.test",
    }


@pytest.mark.parametrize(
    "forbidden_field",
    [
        "role",
        "identity_id",
        "membership_id",
        "password_hash",
        "status",
        "tenant_id",
    ],
)
def test_platform_tenant_create_rejects_server_owned_initial_admin_fields(
    forbidden_field: str,
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        TenantPlatformCreate(
            slug="acme-turkiye",
            name="Acme Türkiye",
            initial_admin={
                "full_name": "Ada Yönetici",
                "email": "ada.yonetici@example.test",
                forbidden_field: "client-controlled",
            },
        )

    assert exc_info.value.errors(include_url=False)[0]["loc"] == (
        "initial_admin",
        forbidden_field,
    )
    assert exc_info.value.errors(include_url=False)[0]["type"] == "extra_forbidden"


def test_initial_admin_correction_normalizes_only_name_and_email() -> None:
    payload = TenantInitialAdminCorrection(
        full_name="  Düzeltilmiş Yönetici  ",
        email="  CORRECTED.ADMIN@EXAMPLE.TEST  ",
    )

    assert payload.model_dump() == {
        "full_name": "Düzeltilmiş Yönetici",
        "email": "corrected.admin@example.test",
    }


@pytest.mark.parametrize(
    "forbidden_field",
    [
        "activation_id",
        "identity_id",
        "membership_id",
        "password_hash",
        "role",
        "status",
        "tenant_id",
        "token",
        "user_id",
    ],
)
def test_initial_admin_correction_rejects_server_owned_fields(
    forbidden_field: str,
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        TenantInitialAdminCorrection.model_validate(
            {
                "full_name": "Corrected Admin",
                "email": "corrected.admin@example.test",
                forbidden_field: "client-controlled",
            }
        )

    assert exc_info.value.errors(include_url=False)[0]["loc"] == (forbidden_field,)
    assert exc_info.value.errors(include_url=False)[0]["type"] == "extra_forbidden"
