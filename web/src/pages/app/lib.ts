// Types, API calls and display helpers for the /app workbench (mirrors gui.py payloads).

export type Evidence = {
  field: string
  method: "located" | "inferred" | "derived" | string
  page?: number
  quote?: string
  context?: string
  rects?: [number, number, number, number][]
}

export type Trace = {
  classification?: unknown
  model?: string
  pages?: number
  ocr_pages?: number[]
  elapsed_s?: number
  verification?: { rounds?: { changes?: { field: string; before: unknown; after: unknown }[] }[] }
  voting?: { models?: string[] }
  active_profile?: string
  router?: { escalate?: boolean; vote?: { steps?: { models: string[] }[] } }
  model_override?: string | null
  ocr_model?: string | null
  evidence?: Evidence[]
}

export type Json = null | string | number | boolean | Json[] | { [k: string]: Json }
export type JsonObj = { [k: string]: Json }

export type Doc = {
  id: number
  file: string
  pending: boolean
  session?: string
  doctype?: string
  result?: JsonObj
  trace?: Trace
  error?: string
  edited?: JsonObj | null
  approved?: boolean
}

export type Profile = { name: string; opis: string }
export type Model = {
  id: string
  name: string
  params_b: number | null
  active_b?: number | null
  eu: boolean
  eu_providers?: string[]
  f1_blind: number | null
  f1_train: number | null
  cost: number | null
}
export type Stats = {
  reviews: number
  fields: number
  corrected: number
  accuracy: number | null
  timeline: { cumulative_accuracy: number }[]
  most_corrected: [string, number][]
  examples: Record<string, number>
}
export type Sample = { name: string; title: string; opis: string; kind?: string; typ?: string; files?: string[] }
export type CaseReport = {
  dokumenty?: Record<string, string>
  kontrole?: { status: string; opis: string; szczegoly: string }[]
  uzupelnienia_krzyzowe?: { dokument: string; pole: string; wartosc: string; zrodlo: string }[]
}

async function json<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error((await r.text()) || r.statusText)
  return r.json() as Promise<T>
}

export const api = {
  profiles: () => fetch("/api/profiles").then((r) => json<{ default: string | null; profiles: Profile[] }>(r)),
  models: () => fetch("/api/models").then((r) => json<{ models: Model[] }>(r)),
  stats: () => fetch("/api/stats").then((r) => json<Stats>(r)),
  samples: () => fetch("/api/samples").then((r) => json<Sample[]>(r)),
  caseReport: (sid: string) => fetch(`/api/case/${sid}`).then((r) => json<CaseReport>(r)),
  process: (file: File, caseId: string, profile: string, model: string | null) => {
    const fd = new FormData()
    fd.append("files", file)
    fd.append("case", caseId)
    fd.append("profile", profile)
    if (model && profile !== "deterministyczny") fd.append("model", model)
    return fetch("/api/process", { method: "POST", body: fd }).then((r) =>
      json<{ session: string; documents: Omit<Doc, "id" | "pending">[] }>(r),
    )
  },
  feedback: (session: string, file: string, corrected: JsonObj) =>
    fetch("/api/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session, file, corrected }),
    }).then((r) => json<{ saved: boolean; corrected_fields: number; changes: unknown }>(r)),
  sampleFile: (name: string) =>
    fetch("/samples/" + encodeURIComponent(name))
      .then((r) => {
        if (!r.ok) throw new Error(r.statusText)
        return r.blob()
      })
      .then((b) => new File([b], name, { type: "application/pdf" })),
  pageUrl: (sid: string, file: string, n: number) => `/api/page/${sid}/${encodeURIComponent(file)}/${n}.png`,
}

export const LABEL: Record<string, string> = {
  odwolanie: "Odwołanie",
  pelnomocnictwo: "Pełnomocnictwo",
  przelew: "Przelew",
  inny: "Nie rozpoznano typu",
  error: "Błąd",
}
export const NICE: Record<string, string> = {
  OdwolanieKIO: "Odwołanie",
  Odwolujacy: "Odwołujący",
  Zamawiajacy: "Zamawiający",
  ZamowieniePubliczne: "Zamówienie",
  przelew_bankowy: "Przelew",
  mocodawca: "Mocodawca",
  pelnomocnicy: "Pełnomocnik",
  podpisujacy: "Podpisujący",
  pelnomocnik: "Pełnomocnik",
  data: "Dane",
}
export const KEY: Record<string, string> = {
  czynnosc_dzien: "data czynności",
  czynnosc_powod_id: "powód (id)",
  czynnosc_opis: "czynność",
  miejscowosc: "miejscowość",
  "przez-pelnomocnika": "przez pełnomocnika",
  imie_nazwisko: "imię i nazwisko",
  numer_bzp: "nr BZP",
  numer_ted: "nr TED",
  numer_postepowania: "nr postępowania",
  tytul: "tytuł",
  prowadzacy_postepowanie: "prowadzący",
  data_operacji: "data operacji",
  na_rachunek: "na rachunek",
  z_rachunku: "z rachunku",
  numer_transakcji: "nr transakcji",
  nazwa: "nazwa",
  mail: "e-mail",
  typ: "typ",
  krs: "KRS",
  nip: "NIP",
  regon: "REGON",
  pesel: "PESEL",
  kwota: "kwota",
  data: "data",
}
export const PNAME: Record<string, string> = {
  deterministyczny: "Reguły",
  ekonomiczny: "Ekonomiczny",
  standard: "Standard",
  auto: "Auto",
  maksymalny: "Maksymalny",
}
export const pname = (n: string) => PNAME[n] || n

/** Extra descriptions for profiles whose `opis` is empty in /api/profiles. */
export const PROFILE_OPIS_FALLBACK: Record<string, string> = {
  auto: "Reguły + mały model; trudne dokumenty eskalują do większego",
}

/**
 * Models each quality level runs (config/settings.yaml `profiles`). /api/profiles does not expose them, so they
 * are mirrored here; `llm` is the extraction model, `extra` the escalation / voting partners.
 */
export const PROFILE_MODELS: Record<string, { llm: string | null; extra?: string[]; mode?: "escalate" | "vote" }> = {
  deterministyczny: { llm: null },
  ekonomiczny: { llm: "mistralai/ministral-3b-2512" },
  standard: { llm: "mistralai/ministral-8b-2512" },
  auto: { llm: "mistralai/ministral-3b-2512", extra: ["mistralai/ministral-8b-2512"], mode: "escalate" },
  maksymalny: { llm: "mistralai/ministral-8b-2512", extra: ["mistralai/ministral-3b-2512"], mode: "vote" },
}

export const shortModel = (m: string) => String(m).split("/").pop() || m
export const modelName = (id: string, models: Model[]) => models.find((m) => m.id === id)?.name ?? shortModel(id)

/** Human label of the model(s) a level will actually use, honouring the manual model override. */
export function levelModelLabel(profile: string, models: Model[], override: string | null): string {
  if (profile === "deterministyczny") return "bez LLM"
  if (override) return modelName(override, models)
  const pm = PROFILE_MODELS[profile]
  if (!pm || !pm.llm) return "wg profilu"
  const base = modelName(pm.llm, models)
  if (!pm.extra?.length) return base
  const others = pm.extra.map((x) => modelName(x, models).replace(/^Ministral /, ""))
  return pm.mode === "vote" ? `${base} + ${others.join(" + ")}` : `${base} → ${others.join(" → ")}`
}

export const pb = (v: number | null | undefined) =>
  v == null ? "?" : v >= 1000 ? (v / 1000).toFixed(1).replace(".", ",") + "T" : String(v).replace(".", ",") + "B"
export const f3 = (v: number | null | undefined) => (v == null ? null : v.toFixed(v === 1 ? 3 : 4).replace(".", ","))

const TOKENS = /[^.[\]]+|\[\d+\]/g
const tok = (t: string): string | number => (t[0] === "[" ? +t.slice(1, -1) : t)

export function getP(obj: unknown, path: string): unknown {
  try {
    return (path.match(TOKENS) || []).reduce<unknown>(
      (c, t) => (c == null ? c : (c as Record<string | number, unknown>)[tok(t)]),
      obj,
    )
  } catch {
    return undefined
  }
}

export function setP(obj: JsonObj, path: string, val: Json) {
  const toks = path.match(TOKENS) || []
  let cur: Record<string | number, Json> = obj
  toks.forEach((t, i) => {
    const k = tok(t)
    if (i === toks.length - 1) cur[k] = val
    else cur = cur[k] as Record<string | number, Json>
  })
}

/** Same coercion as the legacy editor: empty -> null, short plain numbers -> number, else trimmed string. */
export function parseEdit(raw: string): Json {
  const v = raw.trim()
  if (v === "") return null
  return isNaN(+raw) || /^0\d/.test(raw) || raw.length > 9 ? v : +raw
}

export const TYPE_DOT: Record<string, string> = {
  odwolanie: "bg-primary",
  pelnomocnictwo: "bg-sage",
  przelew: "bg-wheat",
  error: "bg-destructive",
  inny: "bg-muted-foreground",
}
export const typeDot = (t?: string) => TYPE_DOT[t || ""] || "bg-muted-foreground"

export const METHOD_DOT: Record<string, string> = {
  located: "bg-success",
  inferred: "bg-wheat",
  derived: "bg-bark/50",
}
export const METHOD_LABEL: Record<string, string> = {
  located: "cytat z dokumentu",
  inferred: "wywnioskowane",
  derived: "reguła",
}
