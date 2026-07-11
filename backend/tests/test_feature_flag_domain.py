import pytest
from app.modules.core.domain import (
    FEATURE_FLAG_DEFAULTS,
    FEATURE_FLAG_KEYS,
    FeatureFlagKey,
    default_feature_flag_enabled,
    is_feature_flag_override,
)

EXPECTED_DEFAULTS = {
    FeatureFlagKey.ORGANIZATION: False,
    FeatureFlagKey.EMPLOYEES: True,
    FeatureFlagKey.DOCUMENTS: False,
    FeatureFlagKey.LEAVE: True,
    FeatureFlagKey.SELF_SERVICE: False,
    FeatureFlagKey.REPORTING: True,
    FeatureFlagKey.NOTIFICATIONS: False,
}


def test_feature_flag_catalog_is_closed_ordered_and_matches_deployed_modules() -> None:
    assert [key.value for key in FeatureFlagKey] == [
        "organization",
        "employees",
        "documents",
        "leave",
        "self_service",
        "reporting",
        "notifications",
    ]
    assert FEATURE_FLAG_KEYS == tuple(FeatureFlagKey)
    assert dict(FEATURE_FLAG_DEFAULTS) == EXPECTED_DEFAULTS
    assert tuple(FEATURE_FLAG_DEFAULTS) == FEATURE_FLAG_KEYS


def test_feature_flag_defaults_are_immutable_and_unknown_keys_fail_closed() -> None:
    with pytest.raises(TypeError):
        FEATURE_FLAG_DEFAULTS[FeatureFlagKey.ORGANIZATION] = True  # type: ignore[index]

    with pytest.raises(ValueError):
        default_feature_flag_enabled("payroll")


@pytest.mark.parametrize("key", FeatureFlagKey)
def test_feature_override_is_derived_from_the_typed_default(key: FeatureFlagKey) -> None:
    default = default_feature_flag_enabled(key)

    assert is_feature_flag_override(key, default) is False
    assert is_feature_flag_override(key, not default) is True


@pytest.mark.parametrize("enabled", [0, 1, "true", None])
def test_feature_override_comparison_requires_a_strict_boolean(enabled: object) -> None:
    with pytest.raises(TypeError, match="enabled must be a boolean"):
        is_feature_flag_override(FeatureFlagKey.EMPLOYEES, enabled)  # type: ignore[arg-type]
