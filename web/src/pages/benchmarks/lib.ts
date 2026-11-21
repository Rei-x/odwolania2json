import type { SweepPart, SweepRun } from "./types"

// ---------------------------------------------------------------- formatting (Polish decimals)
export const fmt = (v: number | null | undefined, d = 3) => (v == null || !Number.isFinite(v) ? null : v.toFixed(d).replace(".", ","))
/** F1 with 3 decimals, or 4 when the 4th digit carries information. */
export const f1s = (v: number | null | undefined) =>
  v == null || !Number.isFinite(v) ? null : v === 1 ? "1,000" : fmt(v, Math.round(v * 10000) % 10 ? 4 : 3)
export const usd = (v: number | null | undefined) => (v == null ? null : v === 0 ? "0 $" : v.toFixed(3).replace(".", ",") + " $")
export const pb = (v: number | null | undefined) =>
  v == null ? "?" : v >= 1000 ? (v / 1000).toFixed(1).replace(".", ",") + "T" : String(v).replace(".", ",") + "B"
export const secs = (v: number | null | undefined) => (v == null ? null : v >= 90 ? Math.round(v / 60) + " min" : Math.round(v) + " s")
export const pct = (v: number, d = 1) => (v * 100).toFixed(d).replace(".", ",") + "%"

export const ARCH_LABEL: Record<string, string> = { dense: "gęsty", moe: "MoE", rules: "reguły", router: "router" }
export const PD_LABEL: Record<string, string> = {
  odwolanie: "Odwołanie",
  pelnomocnictwo: "Pełnomocn.",
  potwierdzenie_przelewu: "Przelew",
  przelew: "Przelew",
  inny: "Inny",
}

/** Models up to this size run comfortably on a single own GPU server. */
export const SMALL_B = 8

// ---------------------------------------------------------------- sweep
const num = (v: unknown): number | null => {
  if (v == null || v === "") return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}
const DOCTYPE_RE = /^[a-z][a-z0-9_]*$/ // per_doc may carry names of out-of-scope test files: skip them
const sum2 = (a: number | null, b: number | null) => (a == null && b == null ? null : (a ?? 0) + (b ?? 0))

const SPECIAL: [RegExp, string][] = [
  [/tower|translat|nllb|madlad|seamless|opus-mt|aya|salamandra/i, "model do tłumaczeń"],
  [/ui-?tars|gui|computer|operator|cua|holo|agent/i, "agent GUI"],
  [/ocr|olmocr|nanonets|dots\.|got-/i, "model OCR"],
  [/coder|code|devstral|codestral/i, "model do kodu"],
  [/guard|safety|shield/i, "model moderacji"],
  [/math|prover/i, "model matematyczny"],
]

function prepPart(p: unknown): SweepPart | null {
  if (!p || typeof p !== "object") return null
  const o = p as Record<string, unknown>
  let per: Record<string, number | null> | null = null
  if (o.per_doc && typeof o.per_doc === "object")
    per = Object.fromEntries(
      Object.entries(o.per_doc as Record<string, unknown>)
        .filter(([d]) => DOCTYPE_RE.test(d))
        .map(([d, v]) => [d, num(v)]),
    )
  return {
    f1: num(o.f1),
    cost: num(o.cost),
    seconds: num(o.seconds),
    per_doc: per,
    negatives_ok: typeof o.negatives_ok === "string" ? o.negatives_ok : null,
    error: typeof o.error === "string" ? o.error : null,
  }
}

export function prepSweep(raw: unknown[]): SweepRun[] {
  const runs: SweepRun[] = raw
    .filter((r): r is Record<string, unknown> => !!r && typeof r === "object" && typeof (r as { model?: unknown }).model === "string")
    .map((r) => {
      const model = r.model as string
      const name = typeof r.name === "string" ? r.name : undefined
      const params_b = num(r.params_b)
      const train = prepPart(r.train)
      const blind = prepPart(r.blind)
      const eu_providers = Array.isArray(r.eu_providers) ? (r.eu_providers as string[]) : []
      return {
        model,
        name,
        params_b,
        eu_providers,
        providers: Array.isArray(r.providers) ? (r.providers as string[]) : [],
        ts: num(r.ts) ?? undefined,
        train,
        blind,
        label: name ? name.replace(/^[^:]{1,30}:\s*/, "") : model.split("/").pop() || model,
        fb: blind?.f1 ?? null,
        ft: train?.f1 ?? null,
        cost: sum2(train?.cost ?? null, blind?.cost ?? null),
        sec: sum2(train?.seconds ?? null, blind?.seconds ?? null),
        eu: eu_providers.length > 0,
        pareto: false,
        special: (SPECIAL.find(([re]) => re.test(`${model} ${name ?? ""}`)) ?? [null, null])[1],
      }
    })
  // Pareto (size vs quality): no other model is at most as large with at least the same blind F1, one strictly better
  const ok = runs.filter((r) => r.fb != null && r.params_b != null)
  ok.forEach((r) => {
    r.pareto = !ok.some((o) => o !== r && o.params_b! <= r.params_b! && o.fb! >= r.fb! && (o.params_b! < r.params_b! || o.fb! > r.fb!))
  })
  return runs
}

export const negRatio = (n: string | null | undefined) => {
  if (!n) return null
  const [a, b] = n.split("/").map(Number)
  return b ? { a, b, r: a / b } : null
}

export const errorOf = (r: SweepRun, part: "train" | "blind") => r[part]?.error ?? null

// ---------------------------------------------------------------- charts
/** Log-axis ticks within a domain. */
export const LOG_TICKS = [1, 3, 8, 14, 32, 70, 150, 300, 1000, 3000]
export const logTicks = (lo: number, hi: number) => LOG_TICKS.filter((t) => t >= lo && t <= hi)
