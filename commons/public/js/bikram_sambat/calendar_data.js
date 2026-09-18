/**
 * The Bikram Sambat month-length table, and nothing else.
 *
 * Bikram Sambat is a lunisolar calendar: month lengths are 29-32 days and are
 * not computable from a formula, so every implementation carries a table that
 * ultimately traces back to the almanacs published by Nepal's Panchanga Nirnayak
 * Samiti. This one was extracted from the `nepali-date-picker` table that
 * NepalERP already vendored, which is the same lineage.
 *
 * One string per Bikram Sambat year starting at 1970, twelve characters, one per
 * month from Baisakh to Chaitra. Each character is `days - 28`, so "3" is a
 * 31-day month. Stored this way because the shape of a year is then something a
 * reader can check against a printed patro at a glance, and a year that is later
 * found to be wrong is a one-line fix.
 *
 * Why the table rather than the library it came from: the library ships two
 * conversion functions, and only one of them is correct.
 * `getAdDateByBsDate` (BS to Gregorian) walks this table and is a clean bijection.
 * `getBsDateByAdDate` (Gregorian to BS) -- the direction a "what is today in
 * Bikram Sambat?" readout leans on for every single field -- takes a different
 * route and disagrees with its own inverse on 838 of 47,849 days. The
 * disagreements cluster in Chaitra, the month that straddles the Gregorian leap
 * day, and are not all off-by-one: the library reports 13 April 2025 as Baisakh 1,
 * 2081, which is a year and a day out from the true Chaitra 30, 2081. NepalERP
 * shows those wrong dates today, because it calls exactly that function.
 *
 * Deriving both directions from one table instead removes the possibility: the
 * conversions are inverses by construction rather than by coincidence.
 *
 * Two flaws in the source data survive extraction, and neither is ours to invent
 * a fix for:
 *
 *   - BS 2088 is fine here; it was only the *library's* year-start arithmetic
 *     that placed Baisakh 1, 2088 two days late (17 April 2031 instead of the
 *     15th). Accumulating this table gets it right, as the 2086-2089 spans
 *     independently confirm.
 *   - BS 2096 sums to 364 days. A Bikram Sambat year is always 365 or 366, so a
 *     month in that row is short by one and the error is in the almanac data
 *     itself. Every year after it would inherit the drift, so `bikram_sambat.js`
 *     stops at the end of BS 2095 (14 April 2039) rather than show dates it
 *     cannot stand behind. The row is kept, marked, so that whoever has an
 *     authoritative 2096 can correct it and move the bound.
 *
 * Verified against the vendored library across all 47,849 days it can represent:
 * identical in the BS-to-Gregorian direction everywhere except BS 2088, where
 * this table is the one that is right.
 */

export const FIRST_BS_YEAR = 1970;

// BS 1970-01-01 fell on 13 April 1913. Everything else is counted from here.
export const EPOCH_UTC_DAY = Date.UTC(1913, 3, 13) / 86400000;

// Beyond this year the source almanac data is known to be defective; see above.
export const LAST_TRUSTED_BS_YEAR = 2095;

export const MONTH_LENGTHS = [
	"334333212122", // 1970
	"243432221213", // 1971
	"343432221123", // 1972
	"334333212122", // 1973
	"333433212122", // 1974
	"343432221213", // 1975
	"343432221122", // 1976
	"334333212122", // 1977
	"333433212122", // 1978
	"343432221213", // 1979
	"343432212122", // 1980
	"334333212122", // 1981
	"333433122122", // 1982
	"343432221123", // 1983
	"334432212122", // 1984
	"334333212122", // 1985
	"333433122122", // 1986
	"343432221123", // 1987
	"334432212122", // 1988
	"334333212122", // 1989
	"333433122113", // 1990
	"343432221123", // 1991
	"334432212122", // 1992
	"334333212122", // 1993
	"243432221213", // 1994
	"343432221123", // 1995
	"334432122122", // 1996
	"334333212122", // 1997
	"243432221213", // 1998
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
	"334432221222", // 2081
	"243432221222", // 2082
	"334332221222", // 2083
	"334332221222", // 2084
	"343423221222", // 2085
	"243432221222", // 2086
	"334333221222", // 2087
	"234423221222", // 2088
	"243432221222", // 2089
	"243432221222", // 2090
	"334333221222", // 2091
	"234432221222", // 2092
	"243432221222", // 2093
	"334332221222", // 2094
	"334333212222", // 2095
	"234432212122", // 2096  <-- 364 days
	"343432221222", // 2097
	"334333121213", // 2098
	"343432221123", // 2099
	"243432221213", // 2100
];
