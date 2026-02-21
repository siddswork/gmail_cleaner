"""
Tests for gmail/client.py

Run with: pytest tests/test_client.py -v
"""
import pytest
from unittest.mock import MagicMock, patch, call

from googleapiclient.errors import HttpError

from gmail.client import RateLimiter, execute_with_retry, batch_execute


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_http_error(status: int) -> HttpError:
    resp = MagicMock()
    resp.status = status
    return HttpError(resp=resp, content=b'{"error": "test"}')


# ---------------------------------------------------------------------------
# RateLimiter
# ---------------------------------------------------------------------------

class TestRateLimiter:
    def test_consume_under_budget_does_not_sleep(self):
        limiter = RateLimiter(target_qps=150)
        with patch("gmail.client.time") as mock_time:
            mock_time.time.return_value = 0.0
            limiter.consume(100)
            mock_time.sleep.assert_not_called()

    def test_consume_at_exact_budget_does_not_sleep(self):
        limiter = RateLimiter(target_qps=150)
        with patch("gmail.client.time") as mock_time:
            mock_time.time.return_value = 0.0
            limiter.consume(150)
            mock_time.sleep.assert_not_called()

    def test_consume_over_budget_sleeps(self):
        limiter = RateLimiter(target_qps=150)
        with patch("gmail.client.time") as mock_time:
            mock_time.time.return_value = 0.0
            limiter.consume(100)
            limiter.consume(100)  # total 200 > 150 → must sleep
            mock_time.sleep.assert_called_once()

    def test_window_resets_after_one_second(self):
        limiter = RateLimiter(target_qps=150)
        with patch("gmail.client.time") as mock_time:
            mock_time.time.return_value = 0.0
            limiter.consume(150)           # fill budget in window 1
        with patch("gmail.client.time") as mock_time:
            mock_time.time.return_value = 1.1  # 1.1 sec later → new window
            limiter.consume(150)               # should not sleep
            mock_time.sleep.assert_not_called()


# ---------------------------------------------------------------------------
# execute_with_retry
# ---------------------------------------------------------------------------

class TestExecuteWithRetry:
    def test_returns_result_on_first_success(self):
        request = MagicMock()
        request.execute.return_value = {"id": "msg_001"}
        result = execute_with_retry(request)
        assert result == {"id": "msg_001"}
        request.execute.assert_called_once()

    def test_retries_on_429(self):
        request = MagicMock()
        request.execute.side_effect = [make_http_error(429), {"id": "msg_001"}]
        with patch("time.sleep"):
            result = execute_with_retry(request)
        assert result == {"id": "msg_001"}
        assert request.execute.call_count == 2

    def test_retries_on_500(self):
        request = MagicMock()
        request.execute.side_effect = [make_http_error(500), {"id": "msg_001"}]
        with patch("time.sleep"):
            result = execute_with_retry(request)
        assert result == {"id": "msg_001"}

    def test_retries_on_503(self):
        request = MagicMock()
        request.execute.side_effect = [make_http_error(503), {"id": "msg_001"}]
        with patch("time.sleep"):
            result = execute_with_retry(request)
        assert result == {"id": "msg_001"}

    def test_does_not_retry_on_403(self):
        request = MagicMock()
        request.execute.side_effect = make_http_error(403)
        with pytest.raises(HttpError):
            execute_with_retry(request)
        request.execute.assert_called_once()

    def test_raises_after_max_attempts(self):
        request = MagicMock()
        request.execute.side_effect = make_http_error(429)
        with patch("time.sleep"):
            with pytest.raises(HttpError):
                execute_with_retry(request, max_attempts=3)
        assert request.execute.call_count == 3

    def test_exponential_backoff_delays_increase(self):
        request = MagicMock()
        request.execute.side_effect = [
            make_http_error(429),
            make_http_error(429),
            {"id": "ok"},
        ]
        with patch("time.sleep") as mock_sleep:
            execute_with_retry(request, base_delay=1.0)
        delays = [c.args[0] for c in mock_sleep.call_args_list]
        assert len(delays) == 2
        assert delays[1] > delays[0]


# ---------------------------------------------------------------------------
# batch_execute
# ---------------------------------------------------------------------------

class TestBatchExecute:
    def _make_service(self):
        service = MagicMock()
        batch = MagicMock()
        service.new_batch_http_request.return_value = batch
        return service, batch

    def test_single_batch_for_50_requests(self):
        service, batch = self._make_service()
        requests = [MagicMock() for _ in range(50)]
        batch_execute(service, requests, MagicMock())
        service.new_batch_http_request.assert_called_once()
        assert batch.add.call_count == 50
        batch.execute.assert_called_once()

    def test_two_batches_for_51_requests(self):
        service, batch = self._make_service()
        requests = [MagicMock() for _ in range(51)]
        batch_execute(service, requests, MagicMock())
        assert service.new_batch_http_request.call_count == 2
        assert batch.execute.call_count == 2

    def test_two_batches_for_100_requests(self):
        service, batch = self._make_service()
        requests = [MagicMock() for _ in range(100)]
        batch_execute(service, requests, MagicMock())
        assert service.new_batch_http_request.call_count == 2

    def test_empty_request_list_is_noop(self):
        service, batch = self._make_service()
        batch_execute(service, [], MagicMock())
        service.new_batch_http_request.assert_not_called()

    def test_callback_passed_to_each_batch(self):
        service, batch = self._make_service()
        callback = MagicMock()
        batch_execute(service, [MagicMock(), MagicMock()], callback)
        service.new_batch_http_request.assert_called_once_with(callback=callback)
