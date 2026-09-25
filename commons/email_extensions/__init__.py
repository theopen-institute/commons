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

The rest of the module is about what gets sent, and where:

* `mjml` -- templates designed in MJML, compiled on save into the responsive
  HTML every sending path already reads. The editor and its live preview are
  `commons/public/js/email_mjml.js`.
* `commons/templates/emails/standard.html` -- Frappe's email frame, shadowed so
  that a message which is already a complete document is sent as it is rather
  than nested inside the frame. Composer, Notification, workflow and
  `frappe.sendmail` alike; only the composer could ask core for that before.
* `commons/templates/emails/workflow_action.html` -- a workflow state's email,
  shadowed so that when its template is a complete document the signed action
  buttons are placed inside it, at `<!--workflow-actions-->` or before
  `</body>`.
* `notification` -- a Notification may send an Email Template's content in
  place of its own message.
* `commons/public/js/email_composer.js` -- a Visual view of an HTML email in
  core's composer, editable in place. Behind "Enable Visual HTML Email Editor"
  in Commons Settings, as it changes core's dialog.

The desk half of the Email menu is `commons/public/js/email_extensions.js`.
"""
