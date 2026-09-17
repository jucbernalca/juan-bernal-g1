import json
import pytest
from src.pipeline.ingester import Ingester


class TestIngester:
    def test_load_valid_json(self):
        data = [
            {"ticket_id": "T-001", "text": "No puedo acceder"},
            {"ticket_id": "T-002", "text": "Error 503"},
        ]
        raw = json.dumps(data)
        tickets, errors = Ingester.load_from_string(raw)
        assert len(tickets) == 2
        assert len(errors) == 0

    def test_load_single_ticket_dict(self):
        raw = json.dumps({"ticket_id": "T-001", "text": "Problema"})
        tickets, errors = Ingester.load_from_string(raw)
        assert len(tickets) == 1
        assert len(errors) == 0

    def test_invalid_json(self):
        with pytest.raises(ValueError, match="JSON invalido"):
            Ingester.load_from_string("{invalid json")

    def test_malformed_ticket_does_not_stop_batch(self):
        data = [
            {"ticket_id": "T-001", "text": "Valido"},
            {"ticket_id": "", "text": "Invalido"},
            {"ticket_id": "T-003", "text": "Tambien valido"},
        ]
        raw = json.dumps(data)
        tickets, errors = Ingester.load_from_string(raw)
        assert len(tickets) == 2
        assert len(errors) == 1
        assert errors[0]["ticket_id"] == ""

    def test_empty_text_ticket(self):
        data = [{"ticket_id": "T-001", "text": ""}]
        raw = json.dumps(data)
        tickets, errors = Ingester.load_from_string(raw)
        assert len(tickets) == 0
        assert len(errors) == 1

    def test_not_a_list(self):
        with pytest.raises(ValueError):
            Ingester.load_from_string('"just a string"')

    def test_load_single_valid(self):
        ticket, error = Ingester.load_single({"ticket_id": "T-001", "text": "Problema"})
        assert ticket is not None
        assert error is None

    def test_load_single_invalid(self):
        ticket, error = Ingester.load_single({"ticket_id": "", "text": ""})
        assert ticket is None
        assert error is not None
