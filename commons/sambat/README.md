# Sambat

Bikram Sambat dates beside Gregorian ones, everywhere a date appears: a readout and a BS calendar
on every Date and Datetime field in the desk, a tooltip on dates in child tables, list views, Report
View and query reports, and a BS calendar in the Commons frontend's date pickers. Nothing is stored
in Bikram Sambat; documents keep their Gregorian values.

It is switched on per site by **Commons Settings → General → Enable Bikram Sambat Calendar**
(`enable_bikram_sambat`, off by default). Off, the desk is left exactly as core builds it.

## The calendar table

Bikram Sambat month lengths cannot be computed. Nepal's Panchanga Nirnayak Samiti fixes each year and
publishes it as a PDF a few months ahead, so every converter carries a table, and a table nobody
updates goes wrong when a published year differs from the guess that stood in for it.

So this one is not maintained by hand. Weekly, after every migrate, and as soon as the setting is
ticked, `table.refresh` reads the month lengths from opensource-nepal's `nepali` package on GitHub,
**as data**: the file is parsed with `ast.literal_eval`, and none of that package's code is
installed, imported or run. A calendar is used only if it passes `table.validate`:

- every month is 29 to 32 days and every year 365 or 366;
- every year begins between 10 and 16 April, which catches a table a day out as well as a broken one;
- it covers next year in full;
- it agrees with every date in `js/confirmed_dates.json`, the days public holidays fell on in the
  government's published lists.

What passes is kept in Commons Settings (`bikram_sambat_calendar`, with a status line under the
switch) and sent to the browser at boot. The migrate and the settings save only queue the check (one
job at a time), so a slow or offline network never holds either of them up. System Managers get a To
Do when the calendar changes, when one is refused, or when it has not been fetched for 45 days.
Until the first fetch, and for the years before BS 2000 that opensource-nepal does not cover, the
browser uses the table shipped here (`js/calendar_data.js`).

When the government publishes a new year's holidays, adding a few of them to `confirmed_dates.json`
tightens the check; nothing else needs doing.

## What is where

| File | What it is |
| --- | --- |
| `table.py` | The weekly fetch, the checks, what boot sends, and the To Dos |
| `js/bikram_sambat.js` | Conversion both ways, over one table; `use_calendar` swaps in the site's |
| `js/calendar_data.js` | The shipped table: the fallback, and the years before BS 2000 |
| `js/confirmed_dates.json` | Government-published dates, read by `table.validate` and the frontend tests |
| `js/date_control.js` | The readout and calendar on Date and Datetime fields |
| `js/picker.js` | The BS calendar the readout opens |
| `js/table_cells.js` | The tooltip on dates in tables |
| `scss/bikram_sambat.scss` | Styles for the readout and the calendar |
| `test_table.py` | Tests for `table.py`, run with `python -m unittest commons.sambat.test_table` from `sites/` |

Loaded from `commons/public/js/commons.bundle.js` and `commons/public/scss/commons.bundle.scss`. The
Commons frontend imports `js/` as `@sambat` (`frontend/vite.config.js`); its picker is
`frontend/src/components/BikramDatePicker.vue`, and its tests are
`frontend/src/data/bikramSambat*.test.ts`.
