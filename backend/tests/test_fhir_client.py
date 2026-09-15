from app.fhir_client import _extract_text


def test_extracts_code_text():
    resource = {"code": {"text": "Chronic low back pain"}}
    assert _extract_text(resource) == "Chronic low back pain"


def test_extracts_coding_display_when_no_text():
    resource = {"code": {"coding": [{"display": "Injury of knee"}]}}
    assert "Injury of knee" in _extract_text(resource)


def test_extracts_notes_and_conclusion():
    resource = {
        "code": {"text": "Physical therapy"},
        "note": [{"text": "6-week course completed"}],
        "conclusion": "Meniscal tear confirmed",
    }
    text = _extract_text(resource)
    assert "Physical therapy" in text
    assert "6-week course completed" in text
    assert "Meniscal tear confirmed" in text


def test_returns_empty_string_when_nothing_found():
    assert _extract_text({"resourceType": "Encounter"}) == ""
