from __future__ import annotations

from packages.qre_research import autonomous_opportunity_loop as aol


def test_loop_output_input_classes_are_never_material_triggers() -> None:
    for input_class in (
        "QRE_LOOP_OUTPUT",
        "QRE_GENERATED_HYPOTHESIS_OUTPUT",
        "QRE_CAPABILITY_REQUEST_OUTPUT",
        "QRE_REPORTING_OUTPUT",
        "REPLAY_OR_STATUS_OUTPUT",
    ):
        assert input_class in aol.NON_MATERIAL_INPUT_CLASSES


def test_bootstrap_does_not_emit_material_triggers() -> None:
    payload = aol.build_precheck(None, {"watermark_id": "bootstrap", "content_identity": "bootstrap"})

    assert payload["precheck_status"] == "NO_MATERIAL_CHANGE"
    assert payload["bootstrap_state"] == aol.BOOTSTRAP_BASELINE
    assert payload["triggers"] == []


def test_step5_boundary_constants_remain_disabled() -> None:
    assert aol.LOOP_OUTPUT_NOT_AUTHORIZED_REASON == "LOOP_OUTPUT_NOT_AUTHORIZED_AS_CAPABILITY_TRIGGER"
    assert aol.SELF_TRIGGER_FALSE_POSITIVE_REASON == "SELF_TRIGGER_FALSE_POSITIVE"
