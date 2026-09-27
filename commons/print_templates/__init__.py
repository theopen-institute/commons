"""One print layout, written once on the site, printed from several doctypes.

A Print Format belongs to one doctype, so a layout that several doctypes share
-- a statement printed from a Customer, a Student and an Employee -- would
otherwise be copied into each of their formats and drift apart. Here the layout
lives in a Web Template, a site record edited in the desk, and each doctype's
Print Format is one line that hands it the document:

    {{ render_web_template("Statement Body", doc) }}

What differs between the doctypes is not the layout but what it is fed: the
party's name is `customer_name` on one and `student_name` on the other. That
translation is the template's **Context Prep**, a few lines of Python run in
Frappe's Server Script sandbox with `doc` in scope, setting `values`:

    if doc.doctype == "Customer":
        values = {"party": doc.customer_name, "tax_id": doc.tax_id}
    else:
        values = {"party": doc.student_name, "tax_id": None}

The template then reads `party` and `tax_id` and never `doc`. A template with
no Context Prep is given `doc` itself. Anything heavier than picking fields --
a balance, a query that needs permission checks -- still belongs in an app
function exposed to Jinja, as `commons.statement.api.party_statement` is; the
prep is for the part that is only a site's own wiring.

The fields (`commons/fixtures/custom_field.json`), under a collapsible "Print"
section at the foot of the Web Template form:

* `context_prep` -- the Python above. Only a Script Manager may change it, the
  role core asks of a Server Script's author, because it runs whenever anybody
  prints a document through the template.
* `test_values` -- JSON standing in for what the prep returns, so the layout can
  be printed with no document at all. **Fill from a Record** writes it by
  running the prep against a real one, which keeps the test data the shape the
  prep really produces; replace the real names in it before saving.

**Test PDF** on the form renders the template as it is in the editor, saved or
not, with the test values, inside Frappe's own print page and through its own
PDF generator -- the page size, margins and print style are the site's. The
letter head is not added: a Print Format that wants one puts it in itself, and
so would the test.

Test values are JSON, so the template sees plain dicts and lists where a real
print may hand it documents: `x.field` reads the same from both, but a method
call such as `doc.get_formatted("total")` only works on the real thing.

The desk half is `commons/public/js/print_templates.js`.
"""
