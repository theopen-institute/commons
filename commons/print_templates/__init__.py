"""One print layout, written once on the site, printed from several doctypes.

A Print Format belongs to one doctype, so a layout that several doctypes share
-- a student's statement printed from a Student, a Fees record or a Loan --
would otherwise be copied into each of their formats and drift apart. Here the
layout lives in a Web Template, a site record edited in the desk, and each
Print Format is one line that passes it its inputs:

    {{ render_web_template("Student Statement", student=doc.name) }}      on Student
    {{ render_web_template("Student Statement", student=doc.student) }}   on Fees

**Inputs** are declared in the template's own Fields table, the one core gives
every Web Template: one row per input, whose fieldname is the name a Print
Format passes and whose fieldtype and Required say what to pass (`contract`).
They are the whole of what a Print Format has to know about the template.
Rows before the first Table Break are single inputs; a Table Break starts a
list input. A Property Setter adds Currency, Date, Float and JSON to the
fieldtypes core offers there.

The **Context Prep** turns the inputs into what the layout reads: Python run
in Frappe's Server Script sandbox, with the inputs as `inputs`, setting
`values`:

    student = frappe.get_doc("Student", inputs.student)
    values = {"student_name": student.student_name, "fees": ..., ...}

A Print Format may pass the printed document as well --
`render_web_template("X", doc, ...)` -- and the prep reads it as `doc`; a
template with no Fields is written that way. With no prep, the template is
given the inputs themselves. Only a Script Manager may change the prep, the
role core asks of a Server Script's author, because it runs whenever anybody
prints through the template. Anything heavier than looking records up -- a
balance, a query that needs permission checks -- still belongs in an app
function the prep calls through `frappe.call`.

Nothing checks a real print against the Fields: a statement printed short is
better than one refused. The **Test PDF** dialog on the form is where a
mismatch shows. It asks for the inputs, one control per Field -- a Student
picker for Student Statement -- runs the prep in the editor on them, and prints
the template in the editor inside Frappe's own print page and through its own
PDF generator, so the page size, margins and print style are the site's. It
can add a Letter Head, marked up as Frappe's standard format does. A real
print decides that in the print dialog, but Frappe only places the letter head
on its standard format, so a Print Format that should carry one wraps the call
in the same markup; the Print section's description on the form has it. For a
test the inputs cannot express, the dialog shows the
prep's output as JSON to edit and prints that. None of it is kept, since it is
usually a real record's figures.

Edited values are JSON, so the template sees plain dicts and lists where a
real print may hand it documents: `x.field` reads the same from both, but a
method call such as `doc.get_formatted("total")` only works on the real thing.

The field (`commons/fixtures/custom_field.json`), under a "Print" section at
the foot of the Web Template form, is `context_prep`. The desk half is
`commons/public/js/print_templates.js`.
"""
