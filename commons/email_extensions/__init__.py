"""Email Templates that know which document they are for.

Frappe's Email Template is a subject and a body and nothing else: which doctype
it is written for, who it goes to, which account sends it and which print goes
with it are left to whoever opens the composer, every time. The fields under the
template's "Form Button" tab say those things once, and this module acts on
them: every form of a doctype some template names gets an **Email** menu in its
toolbar, one item per template, and picking one opens Frappe's own composer
already filled in.

The fields (`commons/fixtures/custom_field.json`, and the README beside it says
why each exists):

* `email_doctype` -- the doctype whose forms offer the template. A template
  without one is an ordinary template and this module ignores it.
* `custom_recipient_fieldname` -- the field, or comma-separated fields, of the
  document holding its recipient. See `api.recipients` for what a value may be.
* `custom_sending_account` -- the Email Account it is sent from.
* `attach_document_print` and `custom_print_format` -- whether the document's
  print goes with it, and in which format.
* `email_condition` -- when the form offers it, as a `depends_on`-style
  expression over `doc`.

It replaces a client script per doctype, each a copy of the same forty lines:
the doctype was the only thing that differed between them, and it was already
written on the templates.

The desk half is `commons/public/js/email_extensions.js`.
"""
