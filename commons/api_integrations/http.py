"""How this app's integrations talk HTTP: one session policy, one timeout.

Frappe's `get_request_session` retries five times, immediately, on a 500 only,
and each attempt waits out whatever timeout the caller passed. Against a host
that has stopped answering, a 30-second timeout became several minutes of a web
worker -- and somebody's save -- held open before anything was reported. So the
integrations use this instead:

* **Connect fast, read patiently.** Five seconds to open a connection, which a
  healthy host needs a fraction of; twenty to answer, which is what a slow API
  under load needs.
* **Retry little, and only what is safe to repeat.** Twice, with backoff, on the
  statuses that mean "try again shortly" (502, 503, 504), honouring
  `Retry-After`. Never a POST: creating an account twice is worse than failing
  once. A 500 is not retried either -- it is the host saying the request itself
  is wrong, and repeating it only repeats the answer.
"""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# (connect, read), in seconds. See the module docstring.
TIMEOUT = (5, 20)

RETRY = Retry(
	total=2,
	connect=2,
	read=0,
	backoff_factor=0.5,
	status_forcelist=(502, 503, 504),
	allowed_methods=frozenset({"GET", "HEAD", "PUT", "DELETE", "OPTIONS"}),
	respect_retry_after_header=True,
	raise_on_status=False,
)


def session() -> requests.Session:
	"""A `requests` session with this module's retry policy on both schemes."""
	http = requests.Session()
	adapter = HTTPAdapter(max_retries=RETRY)
	http.mount("https://", adapter)
	http.mount("http://", adapter)
	return http
