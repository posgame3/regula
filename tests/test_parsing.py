import pytest
from app import extract_json


def test_extract_json_plain():
    assert extract_json('{"applies": true}')["applies"] == True


def test_extract_json_with_intro():
    assert extract_json('Here is the result:\n{"applies": true}')["applies"] == True


def test_extract_json_markdown_fence():
    assert extract_json('```json\n{"applies": true}\n```')["applies"] == True


def test_interview_complete_detection():
    text = 'Dziękuję za rozmowę.\n[INTERVIEW_COMPLETE]\n{"company_name": "Test"}'
    assert "[INTERVIEW_COMPLETE]" in text
    json_part = text.split("[INTERVIEW_COMPLETE]")[1].strip()
    result = extract_json(json_part)
    assert result["company_name"] == "Test"


def test_extract_json_nested():
    data = extract_json('{"gaps": [{"risk": "high"}, {"risk": "low"}]}')
    assert len(data["gaps"]) == 2
    assert data["gaps"][0]["risk"] == "high"


def test_extract_json_trailing_text():
    data = extract_json('{"applies": false}\n\nSome trailing explanation.')
    assert data["applies"] == False


def test_extract_json_raises_on_no_json():
    with pytest.raises(ValueError):
        extract_json("No JSON here at all.")
