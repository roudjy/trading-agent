from research.batch_execution import build_validation_evidence_status


def test_validation_evidence_status_no_oos_trades() -> None:
    payload = build_validation_evidence_status(
        {"oos_summary": {"totaal_trades": 0}},
        result_success=True,
    )

    assert payload == {
        "evidence_status": "no_oos_trades",
        "oos_trade_count": 0,
        "min_oos_trades": 10,
    }


def test_validation_evidence_status_insufficient_oos_trades() -> None:
    payload = build_validation_evidence_status(
        {"oos_summary": {"totaal_trades": 3}},
        result_success=True,
    )

    assert payload == {
        "evidence_status": "insufficient_oos_trades",
        "oos_trade_count": 3,
        "min_oos_trades": 10,
    }


def test_validation_evidence_status_sufficient_oos_evidence() -> None:
    payload = build_validation_evidence_status(
        {"oos_summary": {"totaal_trades": 10}},
        result_success=True,
    )

    assert payload == {
        "evidence_status": "sufficient_oos_evidence",
        "oos_trade_count": 10,
        "min_oos_trades": 10,
    }


def test_validation_evidence_status_validation_error() -> None:
    payload = build_validation_evidence_status(None, result_success=False)

    assert payload == {
        "evidence_status": "validation_error",
        "oos_trade_count": 0,
        "min_oos_trades": 10,
    }
