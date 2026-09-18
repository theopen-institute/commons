/**
 * Converting between Gregorian and Bikram Sambat, and naming the result.
 *
 * Pure: no jQuery, no Frappe, no DOM. Everything here is arithmetic over the
 * table in [calendar_data.js], which is what makes the two directions exact
 * inverses of each other rather than two independent guesses that mostly agree.
 *
 * Dates are handled as *calendar days*, never as instants. A JS `Date` carries a
 * time and a zone, and a Bikram Sambat date carries neither; converting through
 * a day number (`Date.UTC` of the local Y/M/D, divided by a day) throws both away
 * at the boundary and puts them back the same way. A desk open in a browser set
 * to Auckland or Los Angeles then reads the same Bikram Sambat date off a stored
 * `2024-09-03` as one open in Kathmandu, which is the only answer that can be
 * right -- the stored value has no time zone to be converted from.
 *
 * Nothing here throws on a date it cannot represent. Out of range returns null,
 * because every caller is drawing a convenience readout beside a field that
 * works perfectly well without one, and a thrown RangeError inside a blur
 * handler is a worse outcome than a blank label. (The vendored library threw;
 * NepalERP did not catch it, so a 1905 date of birth broke the field.)
 */

import {
	EPOCH_UTC_DAY,
	FIRST_BS_YEAR,
	LAST_TRUSTED_BS_YEAR,
	MONTH_LENGTHS,
} from "./calendar_data.js";

const MS_PER_DAY = 86400000;

/** Baisakh through Chaitra. */
export const MONTH_NAMES = {
	devanagari: [
		"बैशाख",
		"जेठ",
		"असार",
		"साउन",
		"भदौ",
		"असोज",
		"कार्तिक",
		"मंसिर",
		"पौष",
		"माघ",
		"फागुन",
		"चैत",
	],
	latin: [
		"Baisakh",
		"Jestha",
		"Asar",
		"Sawan",
		"Bhadra",
		"Asoj",
		"Kartik",
		"Mangsir",
		"Poush",
		"Magh",
		"Falgun",
		"Chaitra",
	],
};

/** Sunday first, matching `Date.prototype.getDay`. */
export const WEEKDAY_NAMES = {
	devanagari: ["आइत", "सोम", "मंगल", "बुध", "बिही", "शुक्र", "शनि"],
	latin: ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
};

const DEVANAGARI_DIGITS = ["०", "१", "२", "३", "४", "५", "६", "७", "८", "९"];

/**
 * Where each Bikram Sambat year starts, as a day number, built once on import.
 *
 * Roughly 1,500 additions over the whole table -- under two milliseconds, and it
 * buys constant-time conversion afterwards in both directions. The alternative,
 * walking the table on every conversion, would be run once per date field per
 * refresh on forms that carry dozens.
 */
const YEAR_START = new Map();
const YEAR_MONTHS = new Map();

(function build_index() {
	let cursor = EPOCH_UTC_DAY;
	MONTH_LENGTHS.forEach((row, offset) => {
		const year = FIRST_BS_YEAR + offset;
		const months = Array.from(row, (character) => Number(character) + 28);
		YEAR_START.set(year, cursor);
		YEAR_MONTHS.set(year, months);
		cursor += months.reduce((total, days) => total + days, 0);
	});
})();

export const MIN_BS_YEAR = FIRST_BS_YEAR;
export const MAX_BS_YEAR = LAST_TRUSTED_BS_YEAR;

/** First and last day numbers this module will answer for. */
const FIRST_DAY = YEAR_START.get(MIN_BS_YEAR);
const LAST_DAY = YEAR_START.get(MAX_BS_YEAR + 1) - 1;

/** A local calendar date, stripped of time and zone. */
function to_day_number(date) {
	if (!(date instanceof Date) || Number.isNaN(date.getTime())) return null;
	return Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()) / MS_PER_DAY;
}

/** The inverse: a `Date` at local midnight on that calendar day. */
function from_day_number(day_number) {
	const utc = new Date(day_number * MS_PER_DAY);
	return new Date(utc.getUTCFullYear(), utc.getUTCMonth(), utc.getUTCDate());
}

/** How many days Baisakh, Jestha ... Chaitra have in this Bikram Sambat year. */
export function days_in_month(year, month) {
	const months = YEAR_MONTHS.get(year);
	if (!months || month < 1 || month > 12) return null;
	return months[month - 1];
}

/** Whether a Bikram Sambat date exists in the supported span. */
export function is_valid(bs) {
	if (!bs) return false;
	const length = days_in_month(bs.year, bs.month);
	return (
		bs.year >= MIN_BS_YEAR &&
		bs.year <= MAX_BS_YEAR &&
		length !== null &&
		bs.day >= 1 &&
		bs.day <= length
	);
}

/**
 * Gregorian to Bikram Sambat. Returns `{year, month, day}`, or null outside the
 * supported span (13 April 1913 to 14 April 2039).
 */
export function from_gregorian(date) {
	const day_number = to_day_number(date);
	if (day_number === null || day_number < FIRST_DAY || day_number > LAST_DAY) return null;

	// Start from the arithmetic estimate rather than scanning: a Bikram Sambat
	// year is always 365 or 366 days, so dividing can only ever be a year out,
	// and the correction below settles it in at most one step either way.
	let year = MIN_BS_YEAR + Math.floor((day_number - FIRST_DAY) / 366);
	while (YEAR_START.get(year + 1) !== undefined && YEAR_START.get(year + 1) <= day_number)
		year++;
	while (YEAR_START.get(year) > day_number) year--;

	let remaining = day_number - YEAR_START.get(year);
	const months = YEAR_MONTHS.get(year);
	let month = 0;
	while (remaining >= months[month]) {
		remaining -= months[month];
		month++;
	}
	return { year, month: month + 1, day: remaining + 1 };
}

/**
 * Bikram Sambat to Gregorian, as a `Date` at local midnight. Null if the date
 * does not exist -- Falgun 31 in a year where Falgun has 30 days, say.
 */
export function to_gregorian(bs) {
	if (!is_valid(bs)) return null;
	const months = YEAR_MONTHS.get(bs.year);
	let day_number = YEAR_START.get(bs.year);
	for (let index = 0; index < bs.month - 1; index++) day_number += months[index];
	return from_day_number(day_number + bs.day - 1);
}

/** 0 for Sunday, matching `Date.prototype.getDay`. */
export function weekday(bs) {
	const date = to_gregorian(bs);
	return date ? date.getDay() : null;
}

/** Today in Bikram Sambat, by the browser's own clock. */
export function today() {
	return from_gregorian(new Date());
}

/** Shift a Bikram Sambat month, carrying the year. Used by the picker's arrows. */
export function add_months(bs, delta) {
	const absolute = (bs.year - MIN_BS_YEAR) * 12 + (bs.month - 1) + delta;
	const year = MIN_BS_YEAR + Math.floor(absolute / 12);
	const month = (((absolute % 12) + 12) % 12) + 1;
	if (year < MIN_BS_YEAR || year > MAX_BS_YEAR) return null;
	// Clamp rather than roll over: stepping from Chaitra 31 into a 30-day month
	// should land on its last day, the way every calendar UI behaves.
	return { year, month, day: Math.min(bs.day, days_in_month(year, month)) };
}

export function to_devanagari_digits(text) {
	return String(text).replace(/[0-9]/g, (digit) => DEVANAGARI_DIGITS[Number(digit)]);
}

export function month_name(month, script = "devanagari") {
	return (MONTH_NAMES[script] || MONTH_NAMES.latin)[month - 1];
}

export function weekday_name(index, script = "devanagari") {
	return (WEEKDAY_NAMES[script] || WEEKDAY_NAMES.latin)[index];
}

/**
 * The compact numeric form, `२०८१-०५-१८`.
 *
 * Deliberately the same shape as the Gregorian value sitting next to it: the
 * readout's whole job is to let someone compare the two at a glance, and it
 * cannot do that if one is `2024-09-03` and the other is `18 Bhadra 2081`. The
 * month *names* appear in the picker, where there is room and no second date to
 * line up against.
 *
 * Devanagari by default, here and in the two name helpers above: a Bikram Sambat
 * date written in Latin digits is a transliteration of the calendar rather than
 * the calendar, and the readout exists for people who read the real thing. The
 * `script` option stays because the conversions are also useful to a site script
 * that wants `2081-05-18` for a filename or an export.
 */
export function format(bs, { script = "devanagari" } = {}) {
	if (!bs) return "";
	const pad = (value) => String(value).padStart(2, "0");
	const text = `${bs.year}-${pad(bs.month)}-${pad(bs.day)}`;
	return script === "devanagari" ? to_devanagari_digits(text) : text;
}
