"""The files a record's attachments point at, carried along when it is copied.

A record copies as its field values, and an Attach or Attach Image field holds
only a URL -- `/files/logo.svg` -- so the record arrives pointing at a file this
site may not have. Before a copy, the page asks this site which of the record's
files it lacks (`missing`), reads those from the source (`export`, through the
source's `file` endpoint or a snapshot's `files`), and hands them to `apply`,
which writes them here (`restore`) before saving the record.

A file is written under the source's own URL, so the copied record is the same
content on both sites and compares equal afterwards. Only when that name is
taken here by different content does it get a new one, and the record its new
URL -- the copy then still differs, which the page reports.

Only this site's file URLs travel: `/files/<name>` and `/private/files/<name>`.
A private file stays private; both ends are System Manager only.
"""

import base64
import os

import frappe
from frappe.core.doctype.file.utils import get_content_hash
from frappe.model import table_fields

ATTACH_FIELDTYPES = frozenset({"Attach", "Attach Image"})
PUBLIC_PREFIX = "/files/"
PRIVATE_PREFIX = "/private/files/"


def urls_in(doctype: str, doc: dict) -> list[str]:
	"""This site's file URLs in the record's attach fields, its child rows' included."""
	urls: list[str] = []

	def collect(meta, values: dict):
		for df in meta.fields:
			if df.fieldtype in ATTACH_FIELDTYPES:
				url = values.get(df.fieldname)
				if _parse(url) and url not in urls:
					urls.append(url)
			elif df.fieldtype in table_fields:
				child_meta = frappe.get_meta(df.options)
				for row in values.get(df.fieldname) or []:
					collect(child_meta, row)

	collect(frappe.get_meta(doctype), doc)
	return urls


def missing(urls: list[str]) -> list[str]:
	"""The URLs this site has no file for: no File record, or nothing on disk."""
	return [url for url in urls if not (frappe.db.exists("File", {"file_url": url}) and _on_disk(url))]


def export(url: str) -> dict | None:
	"""The file at `url` on this site, to send to another; None if it has none."""
	parsed = _parse(url)
	if not parsed or not _on_disk(url):
		return None
	name, private = parsed
	with open(_path(name, private), "rb") as f:
		content = f.read()
	return {"file_url": url, "content": base64.b64encode(content).decode()}


def restore(files: list[dict]) -> dict[str, str]:
	"""Write the source's files here. Returns `{source URL: URL here}` for each written.

	A file whose name is free here is written under it. One whose name holds the
	same content already only gets its File record. One whose name holds other
	content is saved the way Frappe saves an upload -- under a new name, or as a
	file this site already has with that content.
	"""
	urls = {}
	for item in files or []:
		url = item.get("file_url")
		parsed = _parse(url)
		if not parsed or item.get("content") is None:
			continue
		name, private = parsed
		content = base64.b64decode(item["content"])
		path = _path(name, private)

		if os.path.exists(path):
			with open(path, "rb") as f:
				same = f.read() == content
		else:
			_write(path, content)
			same = True

		if not same:
			file = frappe.get_doc(
				{"doctype": "File", "file_name": name, "is_private": private, "content": content}
			).insert()
			urls[url] = file.file_url
			continue

		if not frappe.db.exists("File", {"file_url": url}):
			file = frappe.get_doc(
				{
					"doctype": "File",
					"file_url": url,
					"file_name": name,
					"is_private": private,
					"content_hash": get_content_hash(content),
				}
			)
			# The blob is in place under its URL: insert the record without Frappe
			# saving the content again under a name of its own.
			file.flags.copy_from_existing_file = True
			file.insert()
		urls[url] = url
	return urls


def attach(urls: list[str], doctype: str, name: str) -> None:
	"""Attach the File records at `urls` that are attached to nothing to the copied record."""
	for url in urls:
		for file_name in frappe.get_all(
			"File", filters={"file_url": url, "attached_to_doctype": ["is", "not set"]}, pluck="name"
		):
			frappe.db.set_value("File", file_name, {"attached_to_doctype": doctype, "attached_to_name": name})


def rewrite(doctype: str, doc: dict, urls: dict[str, str]) -> None:
	"""Point the record's attach fields at the URLs its files got here, in place."""
	moved = {old: new for old, new in urls.items() if old != new}
	if not moved:
		return

	def walk(meta, values: dict):
		for df in meta.fields:
			if df.fieldtype in ATTACH_FIELDTYPES and values.get(df.fieldname) in moved:
				values[df.fieldname] = moved[values[df.fieldname]]
			elif df.fieldtype in table_fields:
				child_meta = frappe.get_meta(df.options)
				for row in values.get(df.fieldname) or []:
					walk(child_meta, row)

	walk(frappe.get_meta(doctype), doc)


def _parse(url) -> tuple[str, int] | None:
	"""`(file name, is_private)` for a URL to this site's files, else None."""
	if not isinstance(url, str):
		return None
	for prefix, private in ((PRIVATE_PREFIX, 1), (PUBLIC_PREFIX, 0)):
		if url.startswith(prefix):
			name = url[len(prefix) :]
			if name and "/" not in name and "\\" not in name and name not in (".", ".."):
				return name, private
	return None


def _path(name: str, private: int) -> str:
	return frappe.get_site_path("private" if private else "public", "files", name)


def _on_disk(url: str) -> bool:
	parsed = _parse(url)
	return bool(parsed) and os.path.exists(_path(*parsed))


def _write(path: str, content: bytes) -> None:
	with open(path, "wb") as f:
		f.write(content)
	# A failed copy leaves no file behind: the record it was for was never saved.
	frappe.db.after_rollback.add(lambda: os.path.exists(path) and os.remove(path))
