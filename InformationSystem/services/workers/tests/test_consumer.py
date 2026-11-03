"""Unit-тести обробки повідомлень у consumer.py (RabbitMQ і API замінені фейками)."""
import json
import os
import sys
import unittest
from unittest import mock

os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))   # services/ -> common
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))         # workers/

import requests  # noqa: E402

import consumer  # noqa: E402


class FakeChannel:
    def __init__(self):
        self.acked, self.published = [], []

    def basic_ack(self, tag):
        self.acked.append(tag)

    def basic_publish(self, exchange, routing_key, body, properties=None):
        self.published.append((routing_key, body, dict(properties.headers or {}) if properties else {}))


class Props:
    def __init__(self, headers=None):
        self.headers = headers


class Method:
    delivery_tag = 7


def response(status: int, text: str = ""):
    r = requests.Response()
    r.status_code = status
    r._content = text.encode()
    return r


EVENT = json.dumps({"appId": "a", "sessionId": "s", "eventType": "click", "url": "/", "userAgent": "UA"}).encode()


class ConsumerTest(unittest.TestCase):
    def setUp(self):
        self.ch = FakeChannel()
        sleep = mock.patch.object(consumer.time, "sleep")
        sleep.start()
        self.addCleanup(sleep.stop)

    def handle(self, body, headers=None, post=None):
        with mock.patch.object(consumer.session, "post", **(post or {"return_value": response(200)})) as p:
            consumer.handle(self.ch, Method(), Props(headers), body)
        return p

    def test_valid_event_is_posted_and_acked(self):
        p = self.handle(EVENT, {"x-sent-at": "1.0", "traceparent": "00-" + "1" * 32 + "-" + "2" * 16 + "-01"})
        self.assertEqual(self.ch.acked, [7])
        self.assertEqual(self.ch.published, [])
        sent = p.call_args.kwargs
        self.assertEqual(sent["headers"]["User-Agent"], "UA")
        self.assertNotIn("userAgent", sent["json"])

    def test_bad_sent_at_does_not_dead_letter_stored_event(self):
        self.handle(EVENT, {"x-sent-at": "not-a-number"})
        self.assertEqual(self.ch.acked, [7])
        self.assertEqual(self.ch.published, [])

    def test_non_object_json_goes_to_dlq_without_crash(self):
        for body in (b"[]", b'"x"', b"1", b"{broken"):
            self.ch = FakeChannel()
            self.handle(body)
            self.assertEqual(self.ch.acked, [7], body)
            self.assertEqual(self.ch.published[0][0], consumer.DLQ, body)
            self.assertIn("x-error", self.ch.published[0][2])

    def test_client_error_goes_to_dlq_without_retries(self):
        self.handle(EVENT, {"traceparent": "tp"}, post={"return_value": response(400, "bad")})
        queue, _, headers = self.ch.published[0]
        self.assertEqual(queue, consumer.DLQ)
        self.assertEqual(headers["traceparent"], "tp")
        self.assertTrue(headers["x-error"].startswith("HTTP 400"))
        self.assertEqual(self.ch.acked, [7])

    def test_server_error_is_retried_then_dead_lettered(self):
        boom = {"side_effect": requests.ConnectionError("api down")}
        self.handle(EVENT, {"traceparent": "tp"}, post=boom)
        queue, _, headers = self.ch.published[0]
        self.assertEqual((queue, headers["x-retries"], headers["traceparent"]), (consumer.QUEUE, 1, "tp"))
        self.ch = FakeChannel()
        self.handle(EVENT, {"x-retries": consumer.MAX_RETRIES}, post=boom)
        self.assertEqual(self.ch.published[0][0], consumer.DLQ)
        self.assertEqual(self.ch.acked, [7])

    def test_5xx_is_retried(self):
        self.handle(EVENT, post={"return_value": response(503)})
        self.assertEqual(self.ch.published[0][0], consumer.QUEUE)

    def test_unexpected_error_does_not_stop_consumer(self):
        self.handle(EVENT, post={"side_effect": RuntimeError("bug")})
        self.assertEqual(self.ch.published[0][0], consumer.DLQ)
        self.assertEqual(self.ch.acked, [7])


if __name__ == "__main__":
    unittest.main()
