import json
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from app.ai import agenda_lambda
from app.ai.agenda import (
    AgendaItem,
    AgendaParseError,
    ParsedAgenda,
    cost_usd,
    parse_agenda,
)


def test_cost_usd_calculation():
    usage = {"input_tokens": 1000, "output_tokens": 500}

    # Haiku pricing: $0.80/1M in, $4.00/1M out -> (1000*0.80 + 500*4.00) / 1M = 0.0028
    assert cost_usd("us.anthropic.claude-haiku-4-5-20251001-v1:0", usage) == 0.0028

    # Sonnet pricing: $3.00/1M in, $15.00/1M out -> (1000*3.00 + 500*15.00) / 1M = 0.0105
    assert cost_usd("anthropic.claude-sonnet-4-6", usage) == 0.0105

    # Opus pricing: $15.00/1M in, $75.00/1M out -> (1000*15.00 + 500*75.00) / 1M = 0.0525
    assert cost_usd("anthropic.claude-opus-5-5", usage) == 0.0525


def test_parsed_agenda_schema_validation():
    # Valid model
    data = {
        "title": "Weekly Sync",
        "starts_at": "2026-10-28T10:00:00+02:00",
        "duration_minutes": 60,
        "items": [{"topic": "Review KPIs", "owner": "Alice", "minutes": 30}],
        "action_items": [{"task": "Send deck", "owner": "Bob", "due": "2026-10-30"}],
        "language": "en",
    }
    parsed = ParsedAgenda.model_validate(data)
    assert parsed.title == "Weekly Sync"
    assert len(parsed.items) == 1
    assert parsed.items[0].topic == "Review KPIs"
    assert parsed.action_items[0].due == date(2026, 10, 30)

    # Empty items topic should fail
    with pytest.raises(ValidationError):
        ParsedAgenda.model_validate({**data, "items": [{"topic": ""}]})

    # Duration over 600 minutes should fail
    with pytest.raises(ValidationError):
        ParsedAgenda.model_validate({**data, "duration_minutes": 650})


def test_parse_agenda_successful_mock():
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.usage.input_tokens = 120
    mock_response.usage.output_tokens = 45
    mock_response.stop_reason = "tool_use"

    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.id = "call_123"
    tool_block.input = {
        "title": "Mock Meeting",
        "items": [{"topic": "Discuss roadmap"}],
        "language": "en",
    }
    mock_response.content = [tool_block]
    mock_client.messages.create.return_value = mock_response

    with patch("app.ai.agenda.get_bedrock_client", return_value=mock_client):
        agenda, usage = parse_agenda("Discuss roadmap", date(2026, 10, 28), "Europe/Kyiv")

    assert agenda.title == "Mock Meeting"
    assert agenda.items[0].topic == "Discuss roadmap"
    assert usage["input_tokens"] == 120
    assert usage["output_tokens"] == 45


def test_parse_agenda_no_tool_call_raises():
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.usage.input_tokens = 100
    mock_response.usage.output_tokens = 20
    mock_response.stop_reason = "end_turn"
    mock_response.content = [MagicMock(type="text", text="Sorry, no agenda here.")]
    mock_client.messages.create.return_value = mock_response

    with (
        patch("app.ai.agenda.get_bedrock_client", return_value=mock_client),
        pytest.raises(AgendaParseError, match="no agenda returned"),
    ):
        parse_agenda("Not an agenda", date(2026, 10, 28), "Europe/Kyiv")


def test_parse_agenda_retry_on_validation_error():
    mock_client = MagicMock()

    # First call returns invalid schema (missing required fields)
    bad_block = MagicMock()
    bad_block.type = "tool_use"
    bad_block.id = "bad_1"
    bad_block.input = {"items": "not a list"}
    resp1 = MagicMock()
    resp1.usage.input_tokens = 100
    resp1.usage.output_tokens = 20
    resp1.content = [bad_block]

    # Second call returns valid schema
    good_block = MagicMock()
    good_block.type = "tool_use"
    good_block.id = "good_2"
    good_block.input = {
        "title": "Recovered",
        "items": [{"topic": "Fixed item"}],
        "language": "en",
    }
    resp2 = MagicMock()
    resp2.usage.input_tokens = 150
    resp2.usage.output_tokens = 30
    resp2.content = [good_block]

    mock_client.messages.create.side_effect = [resp1, resp2]

    with patch("app.ai.agenda.get_bedrock_client", return_value=mock_client):
        agenda, usage = parse_agenda("Retry text", date(2026, 10, 28), "UTC")

    assert agenda.title == "Recovered"
    assert usage["input_tokens"] == 250
    assert usage["output_tokens"] == 50
    assert mock_client.messages.create.call_count == 2


@patch("app.ai.agenda_lambda.verify_id_token", return_value={"sub": "test-user"})
def test_lambda_rejects_text_over_10000(mock_verify):
    event = {
        "headers": {"authorization": "Bearer fake_token"},
        "body": json.dumps({"text": "a" * 10001, "today": "2026-10-28", "tz": "UTC"}),
    }
    resp = agenda_lambda.handler(event, None)
    assert resp["statusCode"] == 413
    body = json.loads(resp["body"])
    assert "10,000 characters" in body["error"]


@patch("app.ai.agenda_lambda.verify_id_token", return_value={"sub": "test-user"})
def test_lambda_rejects_empty_text(mock_verify):
    event = {
        "headers": {"authorization": "Bearer fake_token"},
        "body": json.dumps({"text": "", "today": "2026-10-28", "tz": "UTC"}),
    }
    resp = agenda_lambda.handler(event, None)
    assert resp["statusCode"] == 400


@patch("app.ai.agenda_lambda.verify_id_token", return_value={"sub": "test-user"})
def test_lambda_success_flow(mock_verify):
    mock_agenda = ParsedAgenda(
        title="Test Meeting",
        place="Room 101",
        items=[AgendaItem(topic="Topic 1", minutes=15)],
        language="en",
    )
    mock_usage = {"input_tokens": 100, "output_tokens": 50}
    with patch("app.ai.agenda_lambda.parse_agenda", return_value=(mock_agenda, mock_usage)):
        event = {
            "headers": {"authorization": "Bearer fake_token"},
            "body": json.dumps({"text": "Topic 1 15 min", "today": "2026-10-28", "tz": "UTC"}),
        }
        resp = agenda_lambda.handler(event, None)
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["agenda"]["title"] == "Test Meeting"
        assert body["agenda"]["place"] == "Room 101"
        assert body["prompt_version"] == "agenda-v1"
