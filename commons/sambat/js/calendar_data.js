/**
 * The Bikram Sambat month-length table this app ships, and nothing else.
 *
 * A fallback. A site with Bikram Sambat switched on sends the browser its own
 * table at boot, kept current from opensource-nepal's calendar by
 * `commons.sambat.table`, and `bikram_sambat.js` converts with
 * that instead (`use_calendar`). This one answers until it arrives, and for the
 * years before BS 2000, which that calendar does not cover.
 *
 * Bikram Sambat is a lunisolar calendar: month lengths are 29-32 days and are
 * not computable from a formula, so every implementation carries a table that
 * ultimately traces back to the almanacs published by Nepal's Panchanga Nirnayak
 * Samiti.
 *
 * One string per Bikram Sambat year starting at 1970, twelve characters, one per
 * month from Baisakh to Chaitra. Each character is `days - 28`, so "3" is a
 * 31-day month. Stored this way because the shape of a year is then something a
 * reader can check against a printed patro at a glance, and a year that is later
 * found to be wrong is a one-line fix.
 *
 * Where the rows come from, checked on 2026-10-09 against five independently
 * maintained converters (npm `bikram-sambat`, `nepali-date-converter` and
 * `nepali-datetime`; Python `nepali-datetime` and `nepali`):
 *
 *   - 2000-2083 is what all five agree on, and 2081-2083 was further checked
 *     against the government's published holiday lists (Maghe Sankranti on Magh
 *     1, 2082 is 15 January 2026; Asoj 31, 2083 is 17 October 2026). The table
 *     this replaced, taken from the `nepali-date-picker` that NepalERP vendored,
 *     carried placeholder rows for 2081 onwards and put about a third of the
 *     month starts in those years a day early.
 *   - 1970-1999 is from `bikram-sambat`, the one source that matched the
 *     consensus on every year from 2000 to 2083. These are dates of birth at
 *     most; the old rows had drifted out of alignment here too.
 *   - 2084-2095 has not been published yet, so it is a projection from
 *     `nepali-datetime` (npm) and `nepali`, which agree with each other. The
 *     other camp's projection repeats the 30-30-30 ending of the placeholder
 *     rows that proved wrong for 2081-2083. Expect a day's error here until the
 *     Samiti's almanac for a year appears, and correct the row when it does.
 *
 * Both directions of conversion in `bikram_sambat.js` are derived from this one
 * table, so they are inverses by construction rather than by coincidence.
 */

export const FIRST_BS_YEAR = 1970;

// BS 1970-01-01 fell on 13 April 1913. Everything else is counted from here.
export const EPOCH_UTC_DAY = Date.UTC(1913, 3, 13) / 86400000;

export const MONTH_LENGTHS = [
	"334333212122", // 1970
	"334342212122", // 1971
	"343432221123", // 1972
	"243432221213", // 1973
	"334333212122", // 1974
	"334423212122", // 1975
	"343432221123", // 1976
	"243432221213", // 1977
	"334333212122", // 1978
	"334432212122", // 1979
	"343432221123", // 1980
	"333433122122", // 1981
	"334333212122", // 1982
	"334432212122", // 1983
	"343432221123", // 1984
	"333433122122", // 1985
	"334333212122", // 1986
	"343432212122", // 1987
	"343432221123", // 1988
	"333433212122", // 1989
	"334333212122", // 1990
	"343432212122", // 1991
	"343432221213", // 1992
	"333433212122", // 1993
	"334333212122", // 1994
	"343432221122", // 1995
	"343432221213", // 1996
	"334333212122", // 1997
	"334333212122", // 1998
	"343432221123", // 1999
	"243432221213", // 2000
	"334333212122", // 2001
	"334432212122", // 2002
	"343432221123", // 2003
	"243432221213", // 2004
	"334333212122", // 2005
	"334432212122", // 2006
	"343432221123", // 2007
	"333433122113", // 2008
	"334333212122", // 2009
	"334432212122", // 2010
	"343432221123", // 2011
	"333433122122", // 2012
	"334333212122", // 2013
	"334432212122", // 2014
	"343432221123", // 2015
	"333433122122", // 2016
	"334333212122", // 2017
	"343432212122", // 2018
	"343432221213", // 2019
	"333433212122", // 2020
	"334333212122", // 2021
	"343432221122", // 2022
	"343432221213", // 2023
	"333433212122", // 2024
	"334333212122", // 2025
	"343432221123", // 2026
	"243432221213", // 2027
	"334333212122", // 2028
	"334342212122", // 2029
	"343432221123", // 2030
	"243432221213", // 2031
	"334333212122", // 2032
	"334432212122", // 2033
	"343432221123", // 2034
	"243433122113", // 2035
	"334333212122", // 2036
	"334432212122", // 2037
	"343432221123", // 2038
	"333433122122", // 2039
	"334333212122", // 2040
	"334432212122", // 2041
	"343432221123", // 2042
	"333433122122", // 2043
	"334333212122", // 2044
	"343432212122", // 2045
	"343432221123", // 2046
	"333433212122", // 2047
	"334333212122", // 2048
	"343432221122", // 2049
	"343432221213", // 2050
	"333433212122", // 2051
	"334333212122", // 2052
	"343432221122", // 2053
	"343432221213", // 2054
	"334333212122", // 2055
	"334342212122", // 2056
	"343432221123", // 2057
	"243432221213", // 2058
	"334333212122", // 2059
	"334432212122", // 2060
	"343432221123", // 2061
	"243433121213", // 2062
	"334333212122", // 2063
	"334432212122", // 2064
	"343432221123", // 2065
	"333433122113", // 2066
	"334333212122", // 2067
	"334432212122", // 2068
	"343432221123", // 2069
	"333433122122", // 2070
	"334333212122", // 2071
	"343432212122", // 2072
	"343432221123", // 2073
	"333433212122", // 2074
	"334333212122", // 2075
	"343432221122", // 2076
	"343432221213", // 2077
	"333433212122", // 2078
	"334333212122", // 2079
	"343432221122", // 2080
	"343432221213", // 2081
	"334333212122", // 2082
	"334333212122", // 2083
	"343432221123", // 2084
	"243432221213", // 2085
	"334333212122", // 2086
	"334432212122", // 2087
	"343432221123", // 2088
	"243432221213", // 2089
	"334333212122", // 2090
	"334432212122", // 2091
	"343432221123", // 2092
	"333433122113", // 2093
	"334333212122", // 2094
	"334432212122", // 2095
];
