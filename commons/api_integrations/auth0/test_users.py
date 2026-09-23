"""The user operations, and the one piece of real logic among them.

That piece is `ensure`: create, and if Auth0 says the address is taken, go and
find what has it. Everything else here is a path and a body, and is tested for
the two things that were wrong in the Server Scripts this replaced -- a password
that was the same for every account, and `email_verified` sent as the string
`"false"`, which Auth0 reads as a value rather than as a negative.
"""

from unittest import TestCase
from unittest.mock import patch

from commons.api_integrations.auth0 import client, users


def throw(message, exc=Exception, **kwargs):
	if isinstance(exc, Exception):
		raise exc
	raise exc(message)


def refusal(status):
	return client.Auth0Error(f"refused ({status})", status=status)


class Segment(TestCase):
	"""An Auth0 id is a provider and an identifier joined by a pipe."""

	def test_the_pipe_is_escaped(self):
		self.assertEqual(users._segment("auth0|65f"), "auth0%7C65f")

	def test_a_slash_does_not_escape_the_path(self):
		"""Frappe's own `quoted` leaves `/` alone, which would reach another endpoint."""
		self.assertNotIn("/", users._segment("oauth2|weird/id"))


class Create(TestCase):
	def create(self, email="a@b.c", **fields):
		self.sent = {}

		def management(method, path, json_body=None, params=None):
			self.sent = {"method": method, "path": path, "body": json_body}
			return {"user_id": "auth0|65f"}

		with (
			patch.object(users.client, "management", management),
			patch.object(users.client, "credentials", lambda: FakeCredentials()),
		):
			return users.create(email, **fields)

	def test_the_id_comes_back(self):
		self.assertEqual(self.create(), "auth0|65f")

	def test_email_verified_is_a_boolean_and_not_the_string_false(self):
		"""Auth0 reads `"false"` as a value, and marks the address verified."""
		self.create()
		self.assertIs(self.sent["body"]["email_verified"], False)

	def test_every_account_gets_its_own_password(self):
		"""`generate_hash` with a fixed salt gives every account on the tenant the same
		one -- and its text argument is deprecated in v17 besides."""
		self.create()
		first = self.sent["body"]["password"]
		self.create()
		self.assertNotEqual(first, self.sent["body"]["password"])
		self.assertEqual(len(first), users.PASSWORD_LENGTH)

	def test_the_connection_comes_from_the_settings(self):
		self.create()
		self.assertEqual(self.sent["body"]["connection"], "Staff")

	def test_extra_fields_are_passed_through(self):
		self.create(given_name="Ada", app_metadata={"member": "a@b.c"})
		self.assertEqual(self.sent["body"]["given_name"], "Ada")
		self.assertEqual(self.sent["body"]["app_metadata"], {"member": "a@b.c"})

	def test_a_caller_may_override_a_default(self):
		"""So a caller with its own arrangement is not fighting this one."""
		self.create(password="theirs", email_verified=True)
		self.assertEqual(self.sent["body"]["password"], "theirs")
		self.assertIs(self.sent["body"]["email_verified"], True)


class FakeCredentials:
	connection = "Staff"


class Ensure(TestCase):
	"""Create first; the lookup is the recovery, not the test."""

	def ensure(self, on_create=None, found=None):
		self.calls = []

		def create(email, **fields):
			self.calls.append("create")
			if on_create:
				raise on_create
			return "auth0|new"

		def find(email):
			self.calls.append("find")
			return found

		with (
			patch.object(users, "create", create),
			patch.object(users, "find", find),
			patch.object(users.frappe, "throw", throw),
			patch.object(users, "_", lambda text: text),
		):
			return users.ensure("a@b.c")

	def test_a_new_address_is_created_in_one_call(self):
		self.assertEqual(self.ensure(), "auth0|new")
		self.assertEqual(self.calls, ["create"])

	def test_a_409_recovers_the_existing_id(self):
		"""The 409 body does not carry it, so it has to be looked up."""
		self.assertEqual(self.ensure(on_create=refusal(409), found="auth0|old"), "auth0|old")
		self.assertEqual(self.calls, ["create", "find"])

	def test_any_other_refusal_is_raised_rather_than_looked_up(self):
		"""A missing scope must not read as an account that already exists."""
		with self.assertRaises(client.Auth0Error) as raised:
			self.ensure(on_create=refusal(403))
		self.assertEqual(raised.exception.status, 403)
		self.assertEqual(self.calls, ["create"])

	def test_a_409_with_nothing_found_says_so_rather_than_returning_nothing(self):
		"""Contradictory: taken, and held by nothing. Usually a missing read:users."""
		with self.assertRaises(Exception) as raised:
			self.ensure(on_create=refusal(409), found=None)
		self.assertIn("read:users", str(raised.exception))


def account(user_id, *connections):
	"""One `users-by-email` row. The first connection given is the primary one."""
	return {
		"user_id": user_id,
		"identities": [{"connection": name} for name in connections],
	}


# The two accounts one address really had on the tenant this was built for: a
# staff directory federated in through Azure AD, and the database account with a
# Google login linked into it. Auth0 listed the Azure one first.
AZURE = account("waad|WiL-eB3i2-ReZLsBYwCBUNt2U6HfD6HAh_6fFr8Ck_Y", "OI-Azure-AD")
DATABASE = account("auth0|5dde985629f9cd0e3203ee55", "Username-Password-Authentication", "google-oauth2")


class Find(TestCase):
	def find(self, matches, connection=None):
		with (
			patch.object(users.client, "management", lambda *args, **kwargs: matches),
			patch.object(users.client, "credentials", lambda: FakeCredentials()),
		):
			return users.find("a@b.c", connection=connection)

	def test_the_id_of_the_one_match(self):
		self.assertEqual(self.find([account("auth0|65f", "Staff")]), "auth0|65f")

	def test_no_match_is_none_rather_than_an_error(self):
		self.assertIsNone(self.find([]))

	def test_a_null_answer_is_not_an_error(self):
		"""`management` returns `None` for an empty body."""
		self.assertIsNone(self.find(None))

	def test_an_account_in_another_connection_is_not_this_site_s(self):
		"""A federated login is a different account with a different id."""
		self.assertIsNone(self.find([AZURE], connection="Username-Password-Authentication"))

	def test_the_database_account_wins_over_one_auth0_happens_to_list_first(self):
		"""The regression: taking Auth0's first row returned the Azure AD account,
		and asking it for a password change ticket earned a 400 -- "The user's main
		connection does not support this operation"."""
		found = self.find([AZURE, DATABASE], connection="Username-Password-Authentication")
		self.assertEqual(found, "auth0|5dde985629f9cd0e3203ee55")

	def test_a_linked_identity_does_not_move_an_account_out_of_its_connection(self):
		"""`DATABASE` has Google linked into it; it is still one database account."""
		self.assertEqual(
			self.find([DATABASE], connection="Username-Password-Authentication"),
			"auth0|5dde985629f9cd0e3203ee55",
		)

	def test_a_linked_identity_does_not_make_an_account_that_connection_s(self):
		"""Matching on any identity rather than the primary would return it here."""
		self.assertIsNone(self.find([DATABASE], connection="google-oauth2"))

	def test_the_settings_connection_is_the_default(self):
		"""`FakeCredentials` is `Staff`, so the database account is not this site's."""
		self.assertIsNone(self.find([DATABASE]))
		self.assertEqual(self.find([account("auth0|65f", "Staff")]), "auth0|65f")


class MainConnection(TestCase):
	def test_the_primary_identity_is_the_one_that_counts(self):
		self.assertEqual(users.main_connection(DATABASE), "Username-Password-Authentication")

	def test_an_account_with_no_identities_belongs_to_nothing(self):
		self.assertIsNone(users.main_connection({"user_id": "auth0|65f"}))

	def test_the_provider_is_not_the_connection(self):
		"""`waad` is the provider; the connection is whatever it was named."""
		self.assertEqual(users.main_connection(AZURE), "OI-Azure-AD")


class Get(TestCase):
	def get(self, answer):
		def management(method, path, json_body=None, params=None):
			if isinstance(answer, Exception):
				raise answer
			return answer

		with patch.object(users.client, "management", management):
			return users.get("auth0|65f")

	def test_an_account_comes_back_whole(self):
		self.assertEqual(self.get({"user_id": "auth0|65f"}), {"user_id": "auth0|65f"})

	def test_an_id_that_points_at_nothing_is_none(self):
		"""An account deleted in the dashboard is a state, not an error."""
		self.assertIsNone(self.get(refusal(404)))

	def test_a_missing_scope_is_not_mistaken_for_a_missing_account(self):
		with self.assertRaises(client.Auth0Error):
			self.get(refusal(403))


class Delete(TestCase):
	def delete(self, answer=None):
		def management(method, path, json_body=None, params=None):
			if isinstance(answer, Exception):
				raise answer
			return None

		with patch.object(users.client, "management", management):
			users.delete("auth0|65f")

	def test_an_account_is_removed(self):
		self.delete()

	def test_one_already_gone_is_success(self):
		"""An end state rather than an act, so every caller does not write this."""
		self.delete(refusal(404))

	def test_a_refused_delete_is_still_an_error(self):
		with self.assertRaises(client.Auth0Error):
			self.delete(refusal(403))


class Tickets(TestCase):
	def ticket(self, answer, **kwargs):
		self.sent = {}

		def management(method, path, json_body=None, params=None):
			self.sent = {"path": path, "body": json_body}
			return answer

		with (
			patch.object(users.client, "management", management),
			patch.object(users.frappe, "throw", throw),
			patch.object(users, "_", lambda text: text),
		):
			return users.password_change_ticket("auth0|65f", **kwargs)

	def test_the_url_comes_back(self):
		self.assertEqual(self.ticket({"ticket": "https://example/t/abc"}), "https://example/t/abc")

	def test_the_optional_arguments_are_left_out_when_not_given(self):
		"""So the tenant's own defaults apply rather than being overridden with blanks."""
		self.ticket({"ticket": "x"})
		self.assertEqual(self.sent["body"], {"user_id": "auth0|65f"})

	def test_a_lifetime_and_a_landing_page_are_passed_on(self):
		self.ticket({"ticket": "x"}, result_url="https://site/done", ttl_seconds=604800)
		self.assertEqual(self.sent["body"]["result_url"], "https://site/done")
		self.assertEqual(self.sent["body"]["ttl_sec"], 604800)

	def test_an_answer_without_a_ticket_is_an_error_rather_than_an_empty_link(self):
		with self.assertRaises(Exception):
			self.ticket({})

	def test_marking_the_address_verified_is_off_unless_asked_for(self):
		"""An account made on somebody's behalf has proved nothing yet."""
		self.ticket({"ticket": "x"})
		self.assertNotIn("mark_email_as_verified", self.sent["body"])

	def test_marking_the_address_verified_is_a_boolean_not_the_string_true(self):
		"""The same trap as `email_verified` -- Auth0 reads a string as a value."""
		self.ticket({"ticket": "x"}, mark_email_as_verified=True)
		self.assertIs(self.sent["body"]["mark_email_as_verified"], True)

	def test_keeping_the_address_out_of_the_redirect_sends_a_real_false(self):
		"""`"false"` is a non-empty string, so it means the opposite of itself."""
		self.ticket({"ticket": "x"}, include_email_in_redirect=False)
		self.assertIs(self.sent["body"]["includeEmailInRedirect"], False)

	def test_no_opinion_on_the_redirect_leaves_the_tenant_default_alone(self):
		"""`False` and "not given" are different instructions, so `None` sends nothing."""
		self.ticket({"ticket": "x"})
		self.assertNotIn("includeEmailInRedirect", self.sent["body"])
