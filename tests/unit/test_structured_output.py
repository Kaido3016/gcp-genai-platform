import pytest

from app.core.exceptions import StructuredOutputValidationError
from app.services.ai.service import DefaultAIService


SCHEMA = {
    "type": "object",
    "properties": {
        "label": {"type": "string", "enum": ["positive", "negative", "neutral"]},
        "confidence": {"type": "number"},
        "flagged": {"type": "boolean"},
    },
    "required": ["label", "confidence"],
}


def test_valid_structured_output_passes(ai_service):
    result = ai_service.generate_structured("classify this", response_schema=SCHEMA)
    # local backend fabricates a schema-conformant object; validation must not raise
    assert result.text


def test_rejects_non_json_output():
    with pytest.raises(StructuredOutputValidationError):
        DefaultAIService._validate_json_against_schema("not json at all", SCHEMA)


def test_rejects_missing_required_field():
    import json

    with pytest.raises(StructuredOutputValidationError):
        DefaultAIService._validate_json_against_schema(json.dumps({"confidence": 0.9}), SCHEMA)


def test_rejects_wrong_type():
    import json

    with pytest.raises(StructuredOutputValidationError):
        DefaultAIService._validate_json_against_schema(
            json.dumps({"label": "positive", "confidence": "high"}), SCHEMA
        )


def test_rejects_invalid_enum_value():
    import json

    with pytest.raises(StructuredOutputValidationError):
        DefaultAIService._validate_json_against_schema(
            json.dumps({"label": "sideways", "confidence": 0.5}), SCHEMA
        )


def test_accepts_valid_payload():
    import json

    # Should not raise
    DefaultAIService._validate_json_against_schema(
        json.dumps({"label": "positive", "confidence": 0.87, "flagged": False}), SCHEMA
    )
