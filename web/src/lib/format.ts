// Polish number formatting for everything user-facing (times, costs, scores, percentages).

const cache = new Map<string, Intl.NumberFormat>()
function nf(min: number, max: number, style: "decimal" | "percent" = "decimal") {
  const k = `${style}:${min}:${max}`
  let f = cache.get(k)
  if (!f) {
    f = new Intl.NumberFormat("pl-PL", { style, minimumFractionDigits: min, maximumFractionDigits: max })
    cache.set(k, f)
  }
  return f
}

/** Plain number with Polish separators: 1234.5 -> "1 234,5". */
export const fmtNum = (v: number, min = 0, max = 2) => nf(min, max).format(v)

/** Seconds: 5.18 -> "5,18 s", 0.004 -> "<0,01 s", 12.3 -> "12,3 s". */
export function fmtSec(s: number | null | undefined): string {
  if (s == null || !isFinite(s)) return "—"
  if (s > 0 && s < 0.01) return "<0,01 s"
  return `${nf(s < 10 ? 2 : 1, s < 10 ? 2 : 1).format(s)} s`
}

/** US dollars, amount first like the rest of the UI: 0.00031 -> "0,0003 $", 0 -> "0 $". */
export function fmtUsd(v: number | null | undefined): string {
  if (v == null || !isFinite(v)) return "—"
  if (v === 0) return "0 $"
  const digits = v >= 1 ? 2 : v >= 0.01 ? 3 : 4
  if (v < 0.0001) return "<0,0001 $"
  return `${nf(digits, digits).format(v)} $`
}

/** Score in [0, 1] such as F1: 0.9845 -> "0,985" (3 decimals). */
export const fmtScore = (v: number | null | undefined, digits = 3) => (v == null ? "—" : nf(digits, digits).format(v))

/** Fraction in [0, 1] as a percentage: 0.983 -> "98,3%". */
export const fmtPct = (v: number | null | undefined, digits = 1) =>
  v == null ? "—" : nf(0, digits, "percent").format(v).replace(/\s(?=%)/, "")
