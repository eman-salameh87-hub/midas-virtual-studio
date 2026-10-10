from app.contracts.client_brief import ProposedJobContract
from app.contracts.uimidas_execution import (
    PRODUCT_APPEARANCE_LOCK,
    derive_change_bounds,
    derive_package_members,
    derive_product_role,
    derive_source_condition,
    inclusion_from_brief,
)
from tests.test_brief_to_job import _slice_payload


def test_derivation_rules_are_explicit() -> None:
    contract = ProposedJobContract.model_validate(_slice_payload())
    item = contract.brief.items[0]
    assert derive_product_role() == "hero"
    assert derive_source_condition(item).input_condition == "clean pack shot"
    assert derive_package_members("Lifestyle", "Wide view") == ["lifestyle"]
    assert derive_package_members("White BK", "Detail") == ["catalogue", "detail"]
    assert inclusion_from_brief(None) is False
    assert inclusion_from_brief("suggest") is True
    changes = derive_change_bounds(item, ["Lifestyle"])
    assert changes.policy_mode == "creative-room"
    assert changes.protected_identity == [PRODUCT_APPEARANCE_LOCK]
    assert changes.allowed_changes == []
