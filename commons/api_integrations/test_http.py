"""The integrations' HTTP policy, as the adapter will apply it.

Site-less. Pinned because each part of it is a decision a later edit could undo
without noticing: a POST retried is an account created twice, and a long
timeout multiplied by retries is a web worker held for minutes.
"""

from unittest import TestCase

from commons.api_integrations import http


class Policy(TestCase):
	def test_connect_fast_read_patiently(self):
		connect, read = http.TIMEOUT
		self.assertLessEqual(connect, 10)
		self.assertLessEqual(read, 30)

	def test_a_post_is_never_retried(self):
		self.assertFalse(http.RETRY.is_retry("POST", 503))

	def test_an_idempotent_call_is_retried_when_the_host_says_try_again(self):
		for status in (502, 503, 504):
			self.assertTrue(http.RETRY.is_retry("GET", status))

	def test_a_500_is_not_retried(self):
		self.assertFalse(http.RETRY.is_retry("GET", 500))

	def test_both_schemes_carry_the_policy(self):
		session = http.session()
		for prefix in ("https://", "http://"):
			self.assertIs(session.get_adapter(prefix + "example.com").max_retries, http.RETRY)
