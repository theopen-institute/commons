// The desk form's half of `commons.document_capture.capture`: the button that
// sends a capture to be read. Nothing reads a capture until somebody presses
// it, here or on the Document Capture page, because every reading is billed.
// Checking the reading and making the draft happen on that page.

const READABLE = ["Unread", "Failed", "Read", "Queued", "Reading"];
const IN_PROGRESS = ["Queued", "Reading"];

// Seconds between reloads while a reading runs, so the form shows the outcome.
const POLL_SECONDS = 5;

frappe.ui.form.on("Captured Document", {
	refresh(frm) {
		clearTimeout(frm.__capture_poll);
		if (frm.is_new()) return;

		if (frm.doc.scan && READABLE.includes(frm.doc.status)) {
			const again = frm.doc.status !== "Unread";
			frm.add_custom_button(again ? __("Read Again") : __("Read"), () => read(frm)).addClass(
				again ? "btn-default" : "btn-primary"
			);
		}

		if (frm.doc.status === "Read") {
			frm.add_custom_button(__("Check and Draft"), () =>
				window.open("/commons/capture", "_blank")
			);
		}

		if (IN_PROGRESS.includes(frm.doc.status)) {
			frm.dashboard.set_headline(
				__("Claude is reading the scan. This form updates when it is done.")
			);
			frm.__capture_poll = setTimeout(() => {
				if (!frm.is_dirty()) frm.reload_doc();
			}, POLL_SECONDS * 1000);
		}
	},
});

function read(frm) {
	if (frm.is_dirty()) {
		frappe.msgprint(__("Save the capture before reading it."));
		return;
	}
	frappe.confirm(
		__("Send {0} to Claude to be read as a {1}? Each reading is billed to the site.", [
			frm.doc.name.bold(),
			__(frm.doc.document_type),
		]),
		() =>
			frappe
				.call({
					method: "commons.document_capture.capture.read",
					args: { name: frm.doc.name, document_type: frm.doc.document_type },
					freeze: true,
				})
				.then(() => {
					frappe.show_alert({ message: __("Sent to be read"), indicator: "blue" });
					frm.reload_doc();
				})
	);
}
