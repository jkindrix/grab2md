from unittest.mock import MagicMock, patch

import requests

from typer.testing import CliRunner

from html2md.cli.cli import app
from html2md.network.request_scheduler import SequentialRequestScheduler


def test_crawl_help_exposes_sequential_policy_not_concurrency_controls():
    result = CliRunner().invoke(app, ["crawl", "--help"])

    assert result.exit_code == 0
    assert "--max-concurrent" not in result.stdout
    assert "sequential" in result.stdout


def test_adaptive_rate_delay_is_applied_before_request():
    limiter = MagicMock()
    limiter.can_make_request.return_value = (True, 2.5)
    limiter.record_request_start.return_value = 0.0
    sleep = MagicMock()
    with patch(
        "html2md.network.request_scheduler.GlobalRateLimiter", return_value=limiter
    ):
        scheduler = SequentialRequestScheduler(
            requests_per_minute=30, sleep=sleep, clock=lambda: 0.0
        )

    request = scheduler.before_request("https://example.com/page")
    scheduler.after_request(request, success=True, response_time=0.25)

    sleep.assert_called_once_with(2.5)
    limiter.record_request_start.assert_called_once_with("https://example.com/page")
    assert limiter.record_request_end.call_args.args[2] is True
    assert limiter.record_request_end.call_args.kwargs["response_time"] == 0.25


def test_retry_after_defers_the_next_request_to_the_same_origin():
    sleep = MagicMock()
    scheduler = SequentialRequestScheduler(sleep=sleep, clock=lambda: 0.0)
    response = requests.Response()
    response.status_code = 429
    response.headers["Retry-After"] = "7"

    first = scheduler.before_request("https://example.com/one")
    scheduler.after_response(first, response)
    scheduler.before_request("https://example.com/two")

    sleep.assert_called_once_with(7.0)
