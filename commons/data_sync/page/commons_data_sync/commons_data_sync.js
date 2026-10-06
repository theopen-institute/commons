// Data Sync: compares this site's configuration with a source site (usually a
// development copy) and copies changes here one record at a time.
//
// The browser is the bridge. This site cannot reach the source -- a laptop is not
// on the internet -- but the browser reaches both, so the source is read with
// fetch() and an API key, and every write goes to this site's own endpoints.
// The base screen only lists; copying happens in the record's details modal.
// See commons/data_sync/api.py.

frappe.provide("commons.data_sync");

frappe.pages["commons-data-sync"].on_page_load = (wrapper) => {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Data Sync"),
		single_column: true,
	});
	wrapper.data_sync = new commons.data_sync.Page(page);
};

(() => {
	const API = "commons.data_sync.api";

	// How a record can differ between the two sites, in the order listed. The
	// sites are compared as they are now: which one changed is for you to judge.
	const STATUSES = {
		differs: {
			label: __("Differs"),
			color: "blue",
			help: __("Both sites have this record, with different content."),
		},
		only_source: {
			label: __("Only on source"),
			color: "green",
			help: __("The source has this record and this site does not. Copying adds it here."),
		},
		only_here: {
			label: __("Only here"),
			color: "orange",
			help: __("This site has this record and the source does not. You can delete it here."),
		},
	};
	const ORDER = Object.keys(STATUSES);

	// d, p: the record's hash on the source and here (null: absent).
	function classify(d, p) {
		if (d === p) return null;
		return !p ? "only_source" : !d ? "only_here" : "differs";
	}

	const esc = (v) => frappe.utils.escape_html(v == null ? "" : String(v));

	// JSON with sorted keys, so two copies of the same row compare equal whatever
	// order the database returned its columns in.
	function stable(value) {
		if (Array.isArray(value)) return `[${value.map(stable).join(",")}]`;
		if (value && typeof value === "object") {
			return `{${Object.keys(value)
				.sort()
				.map((k) => `${JSON.stringify(k)}:${stable(value[k])}`)
				.join(",")}}`;
		}
		return JSON.stringify(value === undefined ? null : value);
	}

	// ---- The source: live over fetch(), or a snapshot file ------------------

	const TOKEN_PREFIX = "commons.data_sync.token:";

	function read_token(origin) {
		try {
			return localStorage.getItem(TOKEN_PREFIX + origin) || "";
		} catch {
			return "";
		}
	}

	function write_token(origin, value) {
		try {
			if (value) localStorage.setItem(TOKEN_PREFIX + origin, value);
			else localStorage.removeItem(TOKEN_PREFIX + origin);
			return true;
		} catch {
			return false;
		}
	}

	function server_message(body) {
		if (!body) return "";
		try {
			const messages = JSON.parse(body._server_messages || "[]").map(
				(m) => JSON.parse(m).message
			);
			if (messages.length) return frappe.utils.html2text(messages.join(" "));
		} catch {
			// fall through to the exception line
		}
		return (body.exception || body.exc_type || "").toString();
	}

	function live_source(base) {
		const origin = new URL(base).origin;
		async function call(method, args) {
			const token = read_token(origin);
			if (!token) {
				throw new Error(
					__("Set an API key for {0} first (menu: Source API Key).", [origin])
				);
			}
			const url = new URL(`/api/method/${API}.${method}`, base);
			Object.entries(args).forEach(([k, v]) => url.searchParams.set(k, v));
			let response;
			try {
				response = await fetch(url, {
					headers: { Accept: "application/json", Authorization: `token ${token}` },
					credentials: "omit",
					cache: "no-store",
				});
			} catch {
				throw new Error(
					__(
						"Could not reach {0}. Check that it is running, that its allow_cors lists {1}, and that your browser lets this site reach local addresses.",
						[origin, window.location.origin]
					)
				);
			}
			let body = null;
			try {
				body = await response.json();
			} catch {
				// not JSON: the status says enough
			}
			if (!response.ok) {
				const detail = server_message(body);
				if (response.status === 401 || response.status === 403) {
					throw new Error(__("{0} refused the API key. {1}", [origin, detail]));
				}
				throw new Error(__("{0} answered {1}. {2}", [origin, response.status, detail]));
			}
			return body.message;
		}
		return {
			kind: "live",
			origin,
			label: base,
			manifest: (rules) => call("manifest", { rules: JSON.stringify(rules) }),
			record: (rule, key) => call("record", { rule: JSON.stringify(rule), key }),
		};
	}

	function file_source(data, filename) {
		return {
			kind: "file",
			label: __("{0} (snapshot of {1})", [filename, data.site]),
			data,
			manifest: async () => data,
			record: async (rule, key) => {
				const entry = data.entries?.[rule.doctype]?.[key];
				return {
					doc: data.records?.[rule.doctype]?.[key] ?? null,
					hash: entry?.[0] ?? null,
					name: entry?.[1] ?? null,
					modified: entry?.[2] ?? null,
				};
			},
		};
	}

	// ---- Line diff ----------------------------------------------------------

	// Longest common subsequence over lines, after trimming the common head and
	// tail -- which is most of any real edit, and keeps the table small.
	function line_diff(a, b) {
		let start = 0;
		while (start < a.length && start < b.length && a[start] === b[start]) start++;
		let end_a = a.length;
		let end_b = b.length;
		while (end_a > start && end_b > start && a[end_a - 1] === b[end_b - 1]) {
			end_a--;
			end_b--;
		}
		const A = a.slice(start, end_a);
		const B = b.slice(start, end_b);
		const same = (lines, from) => lines.map((x, i) => ({ op: "=", a: x, b: x, ia: from + i }));

		let middle = [];
		const n = A.length;
		const m = B.length;
		if (n * m > 4e6) {
			middle = [...A.map((x) => ({ op: "-", a: x })), ...B.map((x) => ({ op: "+", b: x }))];
		} else {
			const w = m + 1;
			const lcs = new Uint32Array((n + 1) * w);
			for (let i = n - 1; i >= 0; i--) {
				for (let j = m - 1; j >= 0; j--) {
					lcs[i * w + j] =
						A[i] === B[j]
							? lcs[(i + 1) * w + j + 1] + 1
							: Math.max(lcs[(i + 1) * w + j], lcs[i * w + j + 1]);
				}
			}
			let i = 0;
			let j = 0;
			while (i < n && j < m) {
				if (A[i] === B[j]) {
					middle.push({ op: "=", a: A[i], b: B[j] });
					i++;
					j++;
				} else if (lcs[(i + 1) * w + j] >= lcs[i * w + j + 1]) {
					middle.push({ op: "-", a: A[i++] });
				} else {
					middle.push({ op: "+", b: B[j++] });
				}
			}
			while (i < n) middle.push({ op: "-", a: A[i++] });
			while (j < m) middle.push({ op: "+", b: B[j++] });
		}
		return [...same(a.slice(0, start), 0), ...middle, ...same(a.slice(end_a), end_a)];
	}

	// Side by side, this site on the left and the source on the right; a run of
	// removed lines is paired with the run of added lines after it. Long stretches
	// of unchanged lines fold to three lines of context either side.
	function render_diff(ops, left_label, right_label) {
		const rows = [];
		let la = 0;
		let lb = 0;
		let k = 0;
		const CONTEXT = 3;
		while (k < ops.length) {
			if (ops[k].op === "=") {
				let end = k;
				while (end < ops.length && ops[end].op === "=") end++;
				const run = end - k;
				const keep_head = k === 0 ? 0 : CONTEXT;
				const keep_tail = end === ops.length ? 0 : CONTEXT;
				for (let x = k; x < end; x++) {
					const offset = x - k;
					if (run > keep_head + keep_tail + 1 && offset === keep_head) {
						const skipped = run - keep_head - keep_tail;
						rows.push(
							`<tr class="ds-skip"><td colspan="4">${esc(
								__("{0} unchanged lines", [skipped])
							)}</td></tr>`
						);
						la += skipped;
						lb += skipped;
						x += skipped - 1;
						continue;
					}
					la++;
					lb++;
					rows.push(
						`<tr><td class="ds-ln">${la}</td><td>${esc(
							ops[x].a
						)}</td><td class="ds-ln">${lb}</td><td>${esc(ops[x].b)}</td></tr>`
					);
				}
				k = end;
				continue;
			}
			const dels = [];
			const adds = [];
			while (k < ops.length && ops[k].op !== "=") {
				(ops[k].op === "-" ? dels : adds).push(ops[k]);
				k++;
			}
			for (let x = 0; x < Math.max(dels.length, adds.length); x++) {
				const d = dels[x];
				const a = adds[x];
				rows.push(
					`<tr>
						<td class="ds-ln">${d ? ++la : ""}</td><td class="${d ? "del" : ""}">${d ? esc(d.a) : ""}</td>
						<td class="ds-ln">${a ? ++lb : ""}</td><td class="${a ? "add" : ""}">${a ? esc(a.b) : ""}</td>
					</tr>`
				);
			}
		}
		return `<div class="ds-code-wrap"><table class="ds-code">
			<colgroup><col style="width:3rem"><col><col style="width:3rem"><col></colgroup>
			<thead><tr><th></th><th>${esc(left_label)}</th><th></th><th>${esc(right_label)}</th></tr></thead>
			<tbody>${rows.join("")}</tbody></table></div>`;
	}

	// ---- The page -----------------------------------------------------------

	commons.data_sync.Page = class DataSyncPage {
		constructor(page) {
			this.page = page;
			this.filters = {
				statuses: new Set(ORDER),
				doctype: "",
				text: "",
			};
			this.$body = $(`<div class="data-sync">
				<div class="ds-sources"></div>
				<div class="ds-messages"></div>
				<div class="ds-filters"></div>
				<div class="ds-results"></div>
			</div>`).appendTo(page.main);
			this.$file = $('<input type="file" accept=".json,application/json" hidden>')
				.appendTo(this.$body)
				.on("change", (e) => this.load_file(e.target.files[0]));
			this.$body.on("click", ".ds-table tbody tr", (e) => {
				const row = this.visible[$(e.currentTarget).data("index")];
				if (row) this.open(row);
			});
			this.make_menu();
			this.start();
		}

		make_menu() {
			this.page.set_primary_action(__("Compare"), () => this.compare(), "refresh");
			this.page.add_menu_item(__("Source API Key"), () => this.ask_token());
			this.page.add_menu_item(__("Load Snapshot File"), () =>
				this.$file.val("").trigger("click")
			);
			this.page.add_menu_item(__("Use Live Source"), () => this.use_live());
			this.page.add_menu_item(__("Download Snapshot of This Site"), () =>
				this.download_snapshot()
			);
			this.page.add_menu_item(__("Settings"), () =>
				frappe.set_route("Form", "Commons Settings")
			);
		}

		async start() {
			this.settings = await frappe.xcall(`${API}.settings`);
			this.use_live();
		}

		use_live(compare = true) {
			const url = this.settings?.source_url;
			this.source = null;
			this.error = null;
			if (url) {
				try {
					this.source = live_source(url);
				} catch {
					this.error = esc(
						__("The Source Site URL in Commons Settings is not a valid address.")
					);
				}
			}
			this.result = null;
			this.render();
			if (this.source && compare) this.compare();
		}

		// ---- Header and messages

		render_sources() {
			const parts = [
				`${esc(__("Source"))}: <b>${esc(
					this.source ? this.source.label : __("none")
				)}</b>`,
				`${esc(__("This site"))}: <b>${esc(this.settings?.site || "")}</b>`,
			];
			this.$body.find(".ds-sources").html(parts.map((p) => `<span>${p}</span>`).join(""));
		}

		message(html, error = false) {
			this.$body
				.find(".ds-messages")
				.append(`<div class="ds-message ${error ? "error" : ""}">${html}</div>`);
		}

		// ---- Comparing

		async compare() {
			if (!this.source) {
				this.render();
				return;
			}
			this.error = null;
			this.page.btn_primary.prop("disabled", true);
			this.$body
				.find(".ds-results")
				.html(`<div class="ds-empty">${esc(__("Comparing…"))}</div>`);
			try {
				const rules =
					this.source.kind === "file" ? this.source.data.rules : this.settings.rules;
				const [src, here] = await Promise.all([
					this.source.manifest(rules),
					frappe.xcall(`${API}.manifest`, { rules: JSON.stringify(rules) }),
				]);
				if (src.format !== here.format) {
					throw new Error(
						__(
							"The source runs a different version of Data Sync (format {0}, this site {1}). Update both to the same Commons.",
							[src.format, here.format]
						)
					);
				}
				this.result = { rules, src, here };
				this.build_rows();
			} catch (e) {
				this.result = null;
				this.error = esc(e.message || e);
			} finally {
				this.page.btn_primary.prop("disabled", false);
			}
			this.render();
		}

		build_rows() {
			const { rules, src, here } = this.result;
			this.rows = [];
			this.errors = {};
			for (const rule of rules) {
				const dt = rule.doctype;
				const problems = [];
				if (src.errors?.[dt]) problems.push(__("Source: {0}", [src.errors[dt]]));
				if (here.errors?.[dt]) problems.push(__("This site: {0}", [here.errors[dt]]));
				if (problems.length) {
					this.errors[dt] = problems.join(" ");
					continue;
				}
				const s = src.entries[dt] || {};
				const h = here.entries[dt] || {};
				for (const key of new Set([...Object.keys(s), ...Object.keys(h)])) {
					const status = classify(s[key]?.[0] ?? null, h[key]?.[0] ?? null);
					if (status)
						this.rows.push({
							rule,
							key,
							status,
							src: s[key] || null,
							here: h[key] || null,
						});
				}
			}
			this.rows.sort(
				(x, y) =>
					rules.indexOf(x.rule) - rules.indexOf(y.rule) ||
					ORDER.indexOf(x.status) - ORDER.indexOf(y.status) ||
					this.display_key(x).localeCompare(this.display_key(y))
			);
		}

		display_key(row) {
			if (!row.rule.key_fields?.length) return row.key;
			try {
				return JSON.parse(row.key).join(" · ");
			} catch {
				return row.key;
			}
		}

		// ---- Rendering the list

		render() {
			this.render_sources();
			this.$body.find(".ds-messages").empty();
			if (this.error) this.message(this.error, true);
			const $filters = this.$body.find(".ds-filters").empty();
			const $results = this.$body.find(".ds-results").empty();

			if (!this.source) {
				$results.html(
					`<div class="ds-empty">${esc(
						__(
							"No source yet. Set the Source Site URL on the Data Sync tab of Commons Settings, or load a snapshot file from the menu."
						)
					)}</div>`
				);
				return;
			}
			if (!this.result) {
				$results.html(
					`<div class="ds-empty">${esc(__("Press Compare to read both sites."))}</div>`
				);
				return;
			}
			this.render_notes();
			this.render_filters($filters);
			this.render_results($results);
		}

		render_notes() {
			const { src } = this.result;
			for (const [label, manifest] of [
				[__("source"), src],
				[__("this site"), this.result.here],
			]) {
				for (const [dt, dupes] of Object.entries(manifest.duplicates || {})) {
					this.message(
						esc(
							__(
								"{0} on the {1} has records that share a key; only the first of each is compared: {2}",
								[dt, label, Object.values(dupes).flat().join(", ")]
							)
						)
					);
				}
			}
			if (this.source.kind === "file") {
				this.message(
					esc(__("Comparing against a snapshot file, with the rules it was taken with."))
				);
			}
		}

		render_filters($filters) {
			const counts = {};
			this.rows.forEach((r) => (counts[r.status] = (counts[r.status] || 0) + 1));
			for (const status of ORDER) {
				if (!counts[status]) continue;
				const def = STATUSES[status];
				$(
					`<button class="indicator-pill ${def.color} ds-pill ${
						this.filters.statuses.has(status) ? "active" : ""
					}" title="${esc(def.help)}">${esc(def.label)} · ${counts[status]}</button>`
				)
					.on("click", () => {
						const set = this.filters.statuses;
						set.has(status) ? set.delete(status) : set.add(status);
						this.render();
					})
					.appendTo($filters);
			}
			const doctypes = [...new Set(this.rows.map((r) => r.rule.doctype))];
			$(
				`<select class="form-control input-xs"><option value="">${esc(
					__("All doctypes")
				)}</option>${doctypes
					.map(
						(dt) =>
							`<option ${dt === this.filters.doctype ? "selected" : ""} value="${esc(
								dt
							)}">${esc(__(dt))}</option>`
					)
					.join("")}</select>`
			)
				.on("change", (e) => {
					this.filters.doctype = e.target.value;
					this.render();
				})
				.appendTo($filters);
			$(
				`<input class="form-control input-xs" type="search" placeholder="${esc(
					__("Search")
				)}">`
			)
				.val(this.filters.text)
				.on(
					"input",
					frappe.utils.debounce((e) => {
						this.filters.text = e.target.value;
						this.render_results(this.$body.find(".ds-results").empty());
					}, 200)
				)
				.appendTo($filters);
		}

		render_results($results) {
			const text = this.filters.text.trim().toLowerCase();
			this.visible = this.rows.filter(
				(r) =>
					this.filters.statuses.has(r.status) &&
					(!this.filters.doctype || r.rule.doctype === this.filters.doctype) &&
					(!text ||
						`${this.display_key(r)} ${(r.src || r.here)[3] || ""}`
							.toLowerCase()
							.includes(text))
			);

			const groups = {};
			this.visible.forEach((row, index) => {
				(groups[row.rule.doctype] ||= []).push(
					`<tr data-index="${index}">
						<td class="ds-status"><span class="indicator-pill ${STATUSES[row.status].color}">${esc(
						STATUSES[row.status].label
					)}</span></td>
						<td>${esc(this.display_key(row))}${
						(row.src || row.here)[3]
							? ` <span class="text-muted">${esc((row.src || row.here)[3])}</span>`
							: ""
					}</td>
						<td class="ds-when">${esc(this.when(row.src))}</td>
						<td class="ds-when">${esc(this.when(row.here))}</td>
					</tr>`
				);
			});

			const html = [];
			for (const rule of this.result.rules) {
				const dt = rule.doctype;
				if (this.filters.doctype && dt !== this.filters.doctype) continue;
				if (this.errors[dt]) {
					html.push(
						`<div class="ds-group"><div class="ds-group-head">${esc(
							__(dt)
						)}<span class="text-muted">${esc(this.errors[dt])}</span></div></div>`
					);
					continue;
				}
				if (!groups[dt]) continue;
				html.push(`<div class="ds-group">
					<div class="ds-group-head">${esc(__(dt))}<span class="text-muted">${groups[dt].length}</span></div>
					<table class="table table-hover ds-table">
						<thead><tr>
							<th class="ds-status">${esc(__("Status"))}</th>
							<th>${esc(__("Record"))}</th>
							<th class="ds-when">${esc(__("Modified on source"))}</th>
							<th class="ds-when">${esc(__("Modified here"))}</th>
						</tr></thead>
						<tbody>${groups[dt].join("")}</tbody>
					</table>
				</div>`);
			}
			$results.html(
				html.length
					? html.join("")
					: `<div class="ds-empty">${esc(
							this.rows.length
								? __("Nothing matches the filters.")
								: __("Both sites agree on every tracked record.")
					  )}</div>`
			);
		}

		when(entry) {
			return entry?.[2] ? frappe.datetime.str_to_user(entry[2]) : "—";
		}

		// ---- The details modal

		async open(row) {
			const rule = row.rule;
			let src;
			let here;
			try {
				[src, here] = await Promise.all([
					this.source.record(rule, row.key),
					frappe.xcall(`${API}.record`, { rule: JSON.stringify(rule), key: row.key }),
				]);
			} catch (e) {
				frappe.msgprint({
					title: __("Could Not Read Record"),
					message: esc(e.message || e),
					indicator: "red",
				});
				return;
			}
			try {
				await frappe.model.with_doctype(rule.doctype);
			} catch {
				// labels fall back to fieldnames
			}
			new commons.data_sync.RecordDialog(this, row, src, here).show();
		}

		// After a copy or delete: both entries for the record are what the servers
		// last said -- the source's as read for the modal, this site's as the write
		// left it -- and the list is reclassified around them.
		update(row, state, src) {
			const set = (manifest, s) => {
				const entries = (manifest.entries[row.rule.doctype] ||= {});
				if (s.hash)
					entries[row.key] = [
						s.hash,
						s.name,
						s.modified,
						s.label ?? (row.src || row.here)?.[3] ?? "",
					];
				else delete entries[row.key];
			};
			set(this.result.here, state);
			if (this.source.kind === "live") set(this.result.src, src);
			this.build_rows();
			this.render();
		}

		// ---- Snapshot files and the API key

		async download_snapshot() {
			frappe.show_alert({ message: __("Preparing snapshot…"), indicator: "blue" });
			const data = await frappe.xcall(`${API}.snapshot`, {
				rules: JSON.stringify(this.settings.rules),
			});
			const blob = new Blob([JSON.stringify(data)], { type: "application/json" });
			const link = document.createElement("a");
			link.href = URL.createObjectURL(blob);
			link.download = `data-sync-${data.site}-${frappe.datetime.now_date()}.json`;
			link.click();
			setTimeout(() => URL.revokeObjectURL(link.href), 1000);
		}

		async load_file(file) {
			if (!file) return;
			let data;
			try {
				data = JSON.parse(await file.text());
			} catch {
				frappe.msgprint(__("That file is not JSON."));
				return;
			}
			if (!data?.entries || !data?.records || !data?.rules) {
				frappe.msgprint(__("That file is not a Data Sync snapshot."));
				return;
			}
			this.source = file_source(data, file.name);
			this.compare();
		}

		ask_token() {
			const url = this.settings?.source_url;
			if (!url) {
				frappe.msgprint(__("Set the Source Site URL in Commons Settings first."));
				return;
			}
			const origin = new URL(url).origin;
			const dialog = new frappe.ui.Dialog({
				title: __("API Key for {0}", [origin]),
				fields: [
					{
						fieldtype: "HTML",
						options: `<p class="text-muted">${esc(
							__(
								"A key for a System Manager on the source, from their User record (Settings, API Access, Generate Keys). It is kept in this browser only."
							)
						)}</p>`,
					},
					{ fieldname: "api_key", fieldtype: "Data", label: __("API Key"), reqd: 1 },
					{
						fieldname: "api_secret",
						fieldtype: "Password",
						label: __("API Secret"),
						reqd: 1,
					},
				],
				primary_action_label: __("Save"),
				primary_action: ({ api_key, api_secret }) => {
					if (!write_token(origin, `${api_key.trim()}:${api_secret.trim()}`)) {
						frappe.msgprint(__("This browser would not store the key."));
						return;
					}
					dialog.hide();
					this.use_live();
				},
				secondary_action_label: read_token(origin) ? __("Forget Key") : null,
				secondary_action: () => {
					write_token(origin, "");
					dialog.hide();
				},
			});
			dialog.show();
		}
	};

	// ---- One record, both sides --------------------------------------------

	commons.data_sync.RecordDialog = class RecordDialog {
		constructor(owner, row, src, here) {
			this.owner = owner;
			this.row = row;
			this.src = src;
			this.here = here;
			this.meta = frappe.get_meta(row.rule.doctype);
		}

		show() {
			const can_copy = !!this.src.doc;
			const can_delete = !this.src.doc && !!this.here.doc;
			this.dialog = new frappe.ui.Dialog({
				title: `${__(this.row.rule.doctype)}: ${this.owner.display_key(this.row)}`,
				size: "extra-large",
				fields: [{ fieldtype: "HTML", fieldname: "body" }],
				primary_action_label: can_copy
					? __("Copy Source Version Here")
					: can_delete
					? __("Delete Here")
					: null,
				primary_action: can_copy || can_delete ? () => this.confirm(can_copy) : null,
			});
			this.dialog.$wrapper.addClass("ds-dialog");
			if (can_delete)
				this.dialog.get_primary_btn().removeClass("btn-primary").addClass("btn-danger");
			this.dialog.fields_dict.body.$wrapper.html(this.body());
			this.dialog.fields_dict.body.$wrapper.on("click", ".ds-toggle-unchanged", (e) => {
				e.preventDefault();
				this.dialog.fields_dict.body.$wrapper
					.find(".ds-unchanged-body")
					.toggleClass("hidden");
			});
			this.dialog.show();
		}

		body() {
			const { row, src, here } = this;
			const def = STATUSES[row.status];
			const stale =
				(here.hash ?? null) !== (row.here?.[0] ?? null) ||
				(src.hash ?? null) !== (row.src?.[0] ?? null);
			const fields = this.fields();
			const changed = fields.filter((f) => f.changed);
			const unchanged = fields.filter((f) => !f.changed);

			return `
				<div class="ds-summary">
					<p><span class="indicator-pill ${def.color}">${esc(def.label)}</span> ${esc(def.help)}</p>
					<p class="text-muted">${esc(__("Source"))}: ${esc(src.name || __("none"))}${
				src.modified
					? `, ${esc(__("modified {0}", [frappe.datetime.str_to_user(src.modified)]))}`
					: ""
			} · ${esc(__("This site"))}: ${esc(here.name || __("none"))}${
				here.modified
					? `, ${esc(__("modified {0}", [frappe.datetime.str_to_user(here.modified)]))}`
					: ""
			}</p>
					${
						stale
							? `<div class="ds-message">${esc(
									__(
										"This record changed since you compared. Shown here as it is now."
									)
							  )}</div>`
							: ""
					}
					${
						row.rule.ignored_fields.length
							? `<p class="text-muted">${esc(
									__("Ignored, and kept as they are here when copying: {0}", [
										row.rule.ignored_fields.join(", "),
									])
							  )}</p>`
							: ""
					}
				</div>
				${
					!src.doc || !here.doc
						? this.single_html(fields, src.doc ? "source" : "here")
						: changed.length
						? changed.map((f) => this.field_html(f)).join("")
						: `<p class="text-muted">${esc(
								__("No field differs except ignored ones.")
						  )}</p>`
				}
				${src.doc && here.doc && unchanged.length ? this.unchanged_html(unchanged) : ""}`;
		}

		// Every field either copy has, in the doctype's own order where it knows it.
		fields() {
			const a = this.here.doc || {};
			const b = this.src.doc || {};
			const order = (this.meta?.fields || []).map((df) => df.fieldname);
			const rank = (k) => {
				const i = order.indexOf(k);
				return i < 0 ? order.length : i;
			};
			const names = [...new Set([...Object.keys(a), ...Object.keys(b)])].sort(
				(x, y) => rank(x) - rank(y) || x.localeCompare(y)
			);
			const ignored = new Set(this.row.rule.ignored_fields);
			return names.map((name) => {
				const df = this.meta
					? frappe.meta.get_docfield(this.row.rule.doctype, name)
					: null;
				return {
					name,
					df,
					label: df?.label ? __(df.label) : name,
					here: a[name],
					source: b[name],
					ignored: ignored.has(name),
					changed: !ignored.has(name) && stable(a[name]) !== stable(b[name]),
				};
			});
		}

		field_html(f) {
			const head = `<div class="ds-field-head">${esc(f.label)}<span class="text-muted">${esc(
				f.name
			)}</span></div>`;
			const here_label = __("This site");
			const source_label = __("Source");

			if (Array.isArray(f.here) || Array.isArray(f.source)) {
				const lines = (rows) => (rows || []).map((r) => this.row_line(r, f.df));
				return `<div class="ds-field">${head}${render_diff(
					line_diff(lines(f.here), lines(f.source)),
					here_label,
					source_label
				)}</div>`;
			}

			const text_a = this.as_text(f.here);
			const text_b = this.as_text(f.source);
			if (
				text_a.includes("\n") ||
				text_b.includes("\n") ||
				text_a.length > 80 ||
				text_b.length > 80
			) {
				const split = (t) => (t === "" ? [] : t.split("\n"));
				return `<div class="ds-field">${head}${render_diff(
					line_diff(split(text_a), split(text_b)),
					here_label,
					source_label
				)}</div>`;
			}

			const cells = [
				[here_label, f.here, "here"],
				[source_label, f.source, "source"],
			];
			return `<div class="ds-field">${head}<div class="ds-values" style="--ds-columns:${
				cells.length
			}">${cells
				.map(
					([label, value, cls]) =>
						`<div><div class="ds-value-label">${esc(
							label
						)}</div><div class="ds-value ${cls}">${this.value_html(value)}</div></div>`
				)
				.join("")}</div></div>`;
		}

		// A string that holds JSON (a workspace's content, a report's settings) is
		// pretty-printed first, so its diff is by line rather than one long line.
		as_text(value) {
			if (value == null) return "";
			if (typeof value !== "string") return JSON.stringify(value, null, 1);
			const t = value.trim();
			if ((t.startsWith("{") || t.startsWith("[")) && t.length > 80) {
				try {
					return JSON.stringify(JSON.parse(t), null, 1);
				} catch {
					// not JSON after all
				}
			}
			return value;
		}

		value_html(value) {
			if (value == null) return `<span class="text-muted">${esc(__("empty"))}</span>`;
			return esc(typeof value === "object" ? JSON.stringify(value) : value);
		}

		// A child row as one line of "Label: value" pairs, in the child doctype's
		// field order, so a table diff reads row by row.
		row_line(row, df) {
			const child = df?.options ? frappe.get_meta(df.options) : null;
			const order = (child?.fields || []).map((d) => d.fieldname);
			const rank = (k) => {
				const i = order.indexOf(k);
				return i < 0 ? order.length : i;
			};
			return Object.keys(row)
				.filter((k) => k !== "idx")
				.sort((x, y) => rank(x) - rank(y) || x.localeCompare(y))
				.map((k) => {
					const label = child?.fields.find((d) => d.fieldname === k)?.label || k;
					const v =
						typeof row[k] === "string"
							? row[k].replace(/\n/g, " ⏎ ")
							: JSON.stringify(row[k]);
					return `${__(label)}: ${v}`;
				})
				.join(" · ");
		}

		// A record only one site has: its fields, one column, nothing to compare.
		single_html(fields, side) {
			return `<table class="table table-sm ds-single"><tbody>${fields
				.map((f) => {
					const value = f[side];
					const shown = Array.isArray(value)
						? render_diff(
								line_diff(
									...(side === "source" ? [[], value] : [value, []]).map(
										(rows) => rows.map((r) => this.row_line(r, f.df))
									)
								),
								__("This site"),
								__("Source")
						  )
						: `<div style="white-space:pre-wrap">${this.value_html(
								this.as_text(value) || null
						  )}</div>`;
					return `<tr><td>${esc(f.label)}</td><td>${shown}</td></tr>`;
				})
				.join("")}</tbody></table>`;
		}

		unchanged_html(fields) {
			return `<div class="ds-unchanged">
				<a href="#" class="ds-toggle-unchanged">${esc(
					__("Show {0} unchanged fields", [fields.length])
				)}</a>
				<div class="ds-unchanged-body hidden">
					<table class="table table-sm"><tbody>${fields
						.map(
							(f) =>
								`<tr><td style="width:14rem">${esc(f.label)}${
									f.ignored
										? ` <span class="text-muted">(${esc(
												__("ignored")
										  )})</span>`
										: ""
								}</td><td>${
									Array.isArray(f.source ?? f.here)
										? esc(__("{0} rows", [(f.source ?? f.here).length]))
										: this.value_html(f.source ?? f.here)
								}</td></tr>`
						)
						.join("")}</tbody></table>
				</div>
			</div>`;
		}

		// Copying replaces what the modal shows, so the button is the decision;
		// deleting is asked once more.
		confirm(copying) {
			const run = () => this.write(copying);
			if (copying) return run();
			frappe.confirm(
				__("Delete {0} {1} on this site? The source has no such record.", [
					__(this.row.rule.doctype),
					this.here.name,
				]),
				run
			);
		}

		async write(copying) {
			const args = {
				rule: JSON.stringify(this.row.rule),
				key: this.row.key,
				expected: this.here.hash || "",
			};
			if (copying) args.doc = JSON.stringify(this.src.doc);
			this.dialog.disable_primary_action();
			try {
				const state = await frappe.xcall(`${API}.${copying ? "apply" : "delete"}`, args);
				this.dialog.hide();
				const still = copying && state.hash && state.hash !== this.src.hash;
				frappe.show_alert({
					message: still
						? __(
								"Copied, but this site's copy still differs; it may set some fields itself."
						  )
						: copying
						? __("Copied.")
						: __("Deleted."),
					indicator: still ? "orange" : "green",
				});
				this.owner.update(this.row, state, this.src);
			} catch {
				// frappe.xcall has shown the server's message
				this.dialog.enable_primary_action();
			}
		}
	};
})();
