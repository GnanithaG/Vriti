from app.classify import classify_employment


def test_full_time_from_schema_org_type():
    assert classify_employment("Engineer", "Join our team", "FULL_TIME") == ("full_time", None)


def test_contractor_schema_org_type_with_no_subtype_text():
    assert classify_employment("Engineer", "Join our team", "CONTRACTOR") == ("contract", None)


def test_c2c_detected_in_description():
    result = classify_employment("Java Developer", "6 month contract, C2C only.", None)
    assert result == ("contract", "c2c")


def test_c2h_detected_via_full_phrase():
    result = classify_employment("Data Engineer", "This is a contract-to-hire position.", None)
    assert result == ("contract", "c2h")


def test_w2_detected():
    result = classify_employment("QA Analyst", "W2 contract position, benefits included.", None)
    assert result == ("contract", "w2")


def test_c2h_wins_over_w2_when_both_mentioned():
    result = classify_employment("Analyst", "Open to W2 or contract-to-hire.", None)
    assert result == ("contract", "c2h")


def test_full_time_from_text_heuristic():
    result = classify_employment("Engineer", "This is a full-time role.", None)
    assert result == ("full_time", None)


def test_internship_from_text():
    result = classify_employment("Summer Intern", "A 12-week internship.", None)
    assert result == ("internship", None)


def test_no_signal_returns_none():
    assert classify_employment("Engineer", "We build things.", None) == (None, None)


def test_contract_without_subtype_stays_unspecified():
    result = classify_employment("Engineer", "This is a contract position.", None)
    assert result == ("contract", None)
