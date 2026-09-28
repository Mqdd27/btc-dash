from unittest.mock import patch

import pytest


@pytest.mark.django_db
def test_evaluate_past_accepts_naive_datetime_local_input(client):
    with patch("apps.trading.views.evaluate_now") as mock_eval, \
         patch("apps.trading.views.resolve_market_symbol"):
        response = client.post("/engine/evaluate-past/", {"at": "2024-01-01T10:00"})

    assert response.status_code == 302
    at = mock_eval.call_args.kwargs["at"]
    assert at.tzinfo is not None and at.utcoffset().total_seconds() == 7 * 3600  # WIB


@pytest.mark.django_db
def test_evaluate_past_shows_error_instead_of_500(client):
    with patch("apps.trading.views.evaluate_now", side_effect=RuntimeError("binance down")), \
         patch("apps.trading.views.resolve_market_symbol"):
        response = client.post("/engine/evaluate-past/", {"at": "2024-01-01T10:00"}, follow=True)

    assert response.status_code == 200
    assert "Failed to get signal: binance down" in response.content.decode()
