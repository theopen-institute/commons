"""What each operation sends, and which refusals are outcomes rather than errors.

Site-less. `client.directory` is the boundary -- everything below it is tested
in `test_client` -- so it is replaced here with something that records what it
was called with and answers what the test wants. `frappe.throw` is replaced for
the reason `commons.api_integrations.auth0.test_client` gives.
"""

import base64
from unittest import TestCase
from unittest.mock import patch

from commons.api_integrations.google_workspace import client, users

CREDENTIALS = client.Credentials(
	key={"client_email": "commons@example-project.iam.gserviceaccount.com"},
	admin_email="directory-bot@example.org",
	customer_id="my_customer",
	org_unit_path="/",
	scopes=client.SCOPES,
)


def throw(message, exc=Exception, **kwargs):
	if isinstance(exc, Exception):
		raise exc
	raise exc(message)


def _format(text):
	return text


class Call(TestCase):
	"""A test case that records what reached `client.directory`."""

	def setUp(self):
		self.sent = []

	def directory(self, answers, credentials=CREDENTIALS):
		"""`answers` is what Google returns, in order; an exception is raised."""
		queue = list(answers)

		def call(method, path, json_body=None, params=None):
			self.sent.append({"method": method, "path": path, "body": json_body, "params": params})
			answer = queue.pop(0)
			if isinstance(answer, Exception):
				raise answer
			return answer

		return patch.multiple(
			users.client,
			directory=call,
			credentials=lambda: credentials,
		)

	def body(self, index=0):
		return self.sent[index]["body"]

	def path(self, index=0):
		return self.sent[index]["path"]


def refused(status):
	return client.GoogleWorkspaceError(f"refused {status}", status=status)


class Segment(TestCase):
	def test_an_address_is_escaped_into_one_path_segment(self):
		self.assertEqual(users._segment("ann@example.org"), "ann%40example.org")

	def test_a_slash_cannot_reach_a_different_endpoint(self):
		self.assertNotIn("/", users._segment("a/../b"))


class GeneratePassword(TestCase):
	def test_it_is_the_length_asked_for(self):
		self.assertEqual(len(users.generate_password(24)), 24)

	def test_it_is_never_shorter_than_google_allows(self):
		"""Google's own floor is eight, and a shorter one is a 400 about `password`."""
		self.assertGreaterEqual(len(users.generate_password(3)), users.MIN_PASSWORD_LENGTH)

	def test_it_has_one_of_every_class_a_strict_domain_wants(self):
		password = users.generate_password()
		for pool in (users.LOWER, users.UPPER, users.DIGITS, users.SYMBOLS):
			self.assertTrue(any(character in pool for character in password), pool)

	def test_it_has_no_characters_that_are_misread_aloud(self):
		password = users.generate_password(64)
		for ambiguous in "lIO01":
			self.assertNotIn(ambiguous, password)

	def test_two_of_them_are_not_the_same(self):
		self.assertNotEqual(users.generate_password(), users.generate_password())

	def test_the_classes_are_not_always_in_the_same_order(self):
		"""Unshuffled, every password starts lower-upper-digit-symbol."""
		starts = {users.generate_password()[:4] for _ in range(40)}
		self.assertGreater(len(starts), 1)


class Get(Call):
	def test_an_account_comes_back_whole(self):
		with self.directory([{"id": "114", "primaryEmail": "ann@example.org"}]):
			self.assertEqual(users.get("114")["primaryEmail"], "ann@example.org")

	def test_a_404_is_an_absence_rather_than_an_error(self):
		with self.directory([refused(404)]):
			self.assertIsNone(users.get("114"))

	def test_a_403_still_raises(self):
		"""A withdrawn delegation must not read as an account that is not there."""
		with self.directory([refused(403)]), self.assertRaises(client.GoogleWorkspaceError):
			users.get("114")


class Find(Call):
	def test_an_address_answers_with_the_immutable_id(self):
		with self.directory([{"id": "114", "primaryEmail": "ann@example.org"}]):
			self.assertEqual(users.find("ann@example.org"), "114")

	def test_it_asks_the_directory_and_not_the_search_index(self):
		"""The index lags, and an account made a minute ago is not in it."""
		with self.directory([{"id": "114"}]):
			users.find("ann@example.org")
		self.assertEqual(self.path(), "users/ann%40example.org")

	def test_an_address_nobody_has_answers_none(self):
		with self.directory([refused(404)]):
			self.assertIsNone(users.find("nobody@example.org"))


class Search(Call):
	def test_it_goes_through_the_customer_from_the_settings(self):
		with self.directory([{"users": [{"id": "114"}]}]):
			users.search("orgUnitPath=/Staff")
		self.assertEqual(self.sent[0]["params"]["customer"], "my_customer")

	def test_a_domain_with_nobody_matching_is_an_empty_list(self):
		"""Google omits the key entirely rather than returning an empty one."""
		with self.directory([{}]):
			self.assertEqual(users.search("givenName:zzz*"), [])


class Create(Call):
	def create(self, answers=None, **kwargs):
		with self.directory(answers or [{"id": "114"}]):
			with patch.object(users.frappe, "throw", throw), patch.object(users, "_", _format):
				return users.create("ann@example.org", "Ann", "Wanjiru", **kwargs)

	def test_it_returns_the_id_google_gave(self):
		self.assertEqual(self.create(), "114")

	def test_the_address_and_the_name_are_what_google_requires(self):
		self.create()
		self.assertEqual(self.body()["primaryEmail"], "ann@example.org")
		self.assertEqual(self.body()["name"], {"givenName": "Ann", "familyName": "Wanjiru"})

	def test_a_password_is_generated_when_none_is_given(self):
		self.create()
		self.assertGreaterEqual(len(self.body()["password"]), users.MIN_PASSWORD_LENGTH)

	def test_the_password_given_is_the_password_sent(self):
		self.create(password="a-known-one")
		self.assertEqual(self.body()["password"], "a-known-one")

	def test_whatever_password_is_used_is_good_for_one_sign_in(self):
		self.create()
		self.assertTrue(self.body()["changePasswordAtNextLogin"])

	def test_the_org_unit_comes_from_the_settings(self):
		self.create()
		self.assertEqual(self.body()["orgUnitPath"], "/")

	def test_a_caller_with_its_own_arrangement_is_not_fighting_the_defaults(self):
		self.create(orgUnitPath="/Staff", changePasswordAtNextLogin=False)
		self.assertEqual(self.body()["orgUnitPath"], "/Staff")
		self.assertFalse(self.body()["changePasswordAtNextLogin"])

	def test_the_fields_this_section_exists_for_go_straight_through(self):
		self.create(
			recoveryEmail="ann@example.net",
			recoveryPhone="+254712345678",
			phones=[{"value": "+254712345678", "type": "mobile", "primary": True}],
		)
		self.assertEqual(self.body()["recoveryEmail"], "ann@example.net")
		self.assertEqual(self.body()["phones"][0]["type"], "mobile")

	def test_a_create_that_returns_no_id_is_said_out_loud(self):
		with self.assertRaises(Exception):
			self.create(answers=[{}])


class Ensure(Call):
	def ensure(self, answers):
		with self.directory(answers):
			with patch.object(users.frappe, "throw", throw), patch.object(users, "_", _format):
				return users.ensure("ann@example.org", "Ann", "Wanjiru")

	def test_an_address_nobody_has_is_created(self):
		self.assertEqual(self.ensure([{"id": "114"}]), "114")
		self.assertEqual(len(self.sent), 1)

	def test_google_is_the_authority_on_whether_it_exists(self):
		"""Create first: two requests that both look first both still race."""
		self.ensure([{"id": "114"}])
		self.assertEqual(self.sent[0]["method"], "POST")

	def test_a_409_is_recovered_by_looking_the_address_up(self):
		"""Which is the whole reason a create-only integration still reads."""
		self.assertEqual(self.ensure([refused(409), {"id": "114"}]), "114")

	def test_a_409_with_nothing_behind_it_is_a_contradiction_worth_naming(self):
		with self.assertRaises(Exception) as raised:
			self.ensure([refused(409), refused(404)])
		self.assertIn("restore", str(raised.exception))

	def test_any_other_refusal_is_not_treated_as_an_existing_account(self):
		with self.assertRaises(client.GoogleWorkspaceError) as raised:
			self.ensure([refused(403)])
		self.assertEqual(raised.exception.status, 403)


class Update(Call):
	def test_it_patches_rather_than_replacing_the_resource(self):
		with self.directory([{"id": "114"}]):
			users.update("114", recoveryEmail="ann@example.net")
		self.assertEqual(self.sent[0]["method"], "PATCH")
		self.assertEqual(self.body(), {"recoveryEmail": "ann@example.net"})


class SetPassword(Call):
	def test_it_returns_the_password_it_set(self):
		with self.directory([{"id": "114"}]):
			password = users.set_password("114")
		self.assertEqual(self.body()["password"], password)

	def test_it_is_good_for_one_sign_in_unless_told_otherwise(self):
		with self.directory([{"id": "114"}]):
			users.set_password("114")
		self.assertTrue(self.body()["changePasswordAtNextLogin"])

	def test_a_shared_mailbox_can_keep_its_password(self):
		with self.directory([{"id": "114"}]):
			users.set_password("114", change_at_next_login=False)
		self.assertFalse(self.body()["changePasswordAtNextLogin"])


class Suspend(Call):
	def test_suspending_is_a_patch_of_one_field(self):
		with self.directory([{"id": "114"}]):
			users.suspend("114")
		self.assertEqual(self.body(), {"suspended": True})

	def test_restoring_is_the_same_call_the_other_way(self):
		with self.directory([{"id": "114"}]):
			users.suspend("114", suspended=False)
		self.assertEqual(self.body(), {"suspended": False})


class Delete(Call):
	def test_an_account_already_gone_is_success(self):
		with self.directory([refused(404)]):
			self.assertIsNone(users.delete("114"))

	def test_any_other_refusal_still_raises(self):
		with self.directory([refused(403)]), self.assertRaises(client.GoogleWorkspaceError):
			users.delete("114")


class Aliases(Call):
	def test_the_addresses_come_back_rather_than_googles_wrappers(self):
		answer = {"aliases": [{"alias": "a@example.org", "id": "114", "kind": "admin#directory#alias"}]}
		with self.directory([answer]):
			self.assertEqual(users.aliases("114"), ["a@example.org"])

	def test_an_account_with_none_is_an_empty_list(self):
		"""Google omits the key entirely, which turns into a TypeError elsewhere."""
		with self.directory([{}]):
			self.assertEqual(users.aliases("114"), [])

	def test_adding_one_sends_it_as_google_wants_it(self):
		with self.directory([{"alias": "a@example.org"}]):
			users.add_alias("114", "a@example.org")
		self.assertEqual(self.body(), {"alias": "a@example.org"})
		self.assertEqual(self.path(), "users/114/aliases")

	def test_a_duplicate_alias_is_raised_rather_than_swallowed(self):
		"""It may be on somebody else's account, which is worth an error."""
		with self.directory([refused(409)]), self.assertRaises(client.GoogleWorkspaceError):
			users.add_alias("114", "a@example.org")

	def test_removing_one_that_is_not_there_is_success(self):
		with self.directory([refused(404)]):
			self.assertIsNone(users.remove_alias("114", "a@example.org"))

	def test_an_alias_is_escaped_into_its_own_segment(self):
		with self.directory([None]):
			users.remove_alias("114", "a@example.org")
		self.assertEqual(self.path(), "users/114/aliases/a%40example.org")


JPEG = b"\xff\xd8\xff" + bytes(range(256)) * 2
PNG = b"\x89PNG\r\n\x1a\n" + b"rest"


class PhotoFormat(TestCase):
	def format(self, data, mime_type=None):
		with patch.object(users.frappe, "throw", throw), patch.object(users, "_", _format):
			return users.photo_format(data, mime_type)

	def test_a_media_type_is_translated_into_googles_spelling(self):
		"""`image/jpeg` in that field is a 400 that names nothing useful."""
		self.assertEqual(self.format(JPEG, "image/jpeg"), "JPEG")

	def test_googles_own_spelling_passes_through(self):
		self.assertEqual(self.format(JPEG, "JPEG"), "JPEG")

	def test_nothing_given_is_sniffed_from_the_bytes(self):
		self.assertEqual(self.format(PNG), "PNG")

	def test_something_google_will_not_take_is_named_before_it_is_sent(self):
		with self.assertRaises(Exception) as raised:
			self.format(JPEG, "image/svg+xml")
		self.assertIn("JPEG", str(raised.exception))

	def test_a_file_that_is_not_an_image_at_all_is_refused(self):
		with self.assertRaises(Exception):
			self.format(b"%PDF-1.7 not an image")


class SetPhoto(Call):
	def set_photo(self, data=JPEG, mime_type=None):
		with self.directory([{"photoData": "..."}]):
			with patch.object(users.frappe, "throw", throw), patch.object(users, "_", _format):
				return users.set_photo("114", data, mime_type)

	def test_the_encoding_is_web_safe(self):
		"""Plain base64 produces + and /, and Google rejects or mangles those."""
		self.set_photo()
		sent = self.body()["photoData"]
		self.assertNotIn("+", sent)
		self.assertNotIn("/", sent)

	def test_the_bytes_survive_the_round_trip(self):
		self.set_photo()
		sent = self.body()["photoData"]
		restored = base64.urlsafe_b64decode(sent + "=" * (-len(sent) % 4))
		self.assertEqual(restored, JPEG)

	def test_the_padding_comes_off(self):
		self.set_photo()
		self.assertFalse(self.body()["photoData"].endswith("="))

	def test_it_goes_to_the_thumbnail_endpoint(self):
		self.set_photo()
		self.assertEqual(self.path(), "users/114/photos/thumbnail")
		self.assertEqual(self.sent[0]["method"], "PUT")

	def test_nothing_to_send_is_said_rather_than_sent(self):
		with self.assertRaises(Exception):
			self.set_photo(data=b"")

	def test_a_photo_over_googles_limit_is_refused_before_it_is_uploaded(self):
		with self.assertRaises(Exception):
			self.set_photo(data=b"\xff\xd8\xff" + b"0" * users.MAX_PHOTO_BYTES)


class Photo(Call):
	def test_an_account_that_has_never_had_one_is_an_absence(self):
		with self.directory([refused(404)]):
			self.assertIsNone(users.photo("114"))

	def test_removing_one_that_is_not_there_is_success(self):
		with self.directory([refused(404)]):
			self.assertIsNone(users.remove_photo("114"))
