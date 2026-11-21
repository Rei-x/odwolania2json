// Shapes of the /api/doctypes/* endpoints (gui.py + o2j/wizard.py) and wizard constants.

export type FieldType = "string" | "date" | "integer" | "number" | "enum" | "object" | "array" | "array_string"

/** One row of the field table; sent as-is in `fields` to POST /api/doctypes/draft. */
export interface FieldRow {
  name: string
  type: FieldType
  normalize?: string
  description: string
  values?: string
  children?: FieldRow[]
}

export interface DoctypeInfo {
  name: string
  file: string
  description?: string
  builtin: boolean
  fields?: number
  keywords?: number
  deterministic?: boolean
  error?: string
}

export interface DoctypeMeta {
  types: string[]
  normalizers: string[]
  builtin: string[]
}

export interface Issue {
  line: number | null
  path: string
  msg: string
}

export interface SpecSummary {
  name: string
  description: string
  fields: number
  keywords: number
  json_schema: unknown
  skeleton: Record<string, unknown>
  preview: Record<string, unknown>
  guide?: string
}

export interface Validation {
  ok: boolean
  errors: Issue[]
  warnings: Issue[]
  name?: string | null
  spec?: SpecSummary
}

export interface DraftResponse {
  yaml: string
  spec: unknown
  validation: Validation
}

export interface Evidence {
  field: string
  method: "located" | "inferred" | "derived" | string
  page?: number
  quote?: string
  context?: string
  rects?: [number, number, number, number][]
}

export interface TestResponse {
  session: string
  file: string
  doctype: string
  result: Record<string, unknown>
  trace: {
    pages: number
    ocr_pages?: number[]
    model?: string
    cost_usd?: number
    elapsed_s: number
    few_shot?: number
    classification?: { scores?: Record<string, number>; best?: string; min_score?: number; confident?: boolean }
    issues?: { field: string; issue: string }[]
    evidence?: Evidence[]
    active_profile?: string
  }
}

export interface InferResponse {
  session: string
  files: string[]
  yaml: string
  spec: { name: string; description: string }
  validation: Validation
  warnings: string[]
  model: string
  cost: number
  elapsed_s: number
}

export interface SaveResponse {
  saved: boolean
  name: string
  file: string
  updated: boolean
  active: boolean
}

export const NAME_RE = /^[a-z][a-z0-9_]{1,40}$/

export const STEPS = ["Definicja", "YAML", "Test", "Zapis"] as const

export const TYPE_OPTS: [FieldType, string][] = [
  ["string", "tekst"],
  ["date", "data"],
  ["integer", "liczba całk."],
  ["number", "kwota / liczba"],
  ["enum", "wybór (enum)"],
  ["object", "obiekt"],
  ["array", "lista obiektów"],
  ["array_string", "lista tekstów"],
]

export const NORM_LABEL: Record<string, string> = {
  auto: "auto",
  none: "brak",
  strip: "tekst (strip)",
  digits: "same cyfry",
  krs: "KRS",
  nip: "NIP",
  regon: "REGON",
  pesel: "PESEL",
  iban: "rachunek (IBAN)",
  bzp: "nr BZP",
  ted: "nr TED",
  date: "data",
  amount: "kwota",
  integer: "liczba",
  person: "osoba",
  city: "miejscowość",
}

export const DEFAULT_BUILTIN = ["odwolanie", "pelnomocnictwo", "przelew"]

export const SAMPLE_NAME = "przystapienie"
export const SAMPLE_TITLE = "Przystąpienie do postępowania odwoławczego"
export const SAMPLE_DESC =
  "Pismo wykonawcy zgłaszające przystąpienie do toczącego się postępowania odwoławczego przed KIO po stronie zamawiającego albo odwołującego."
export const SAMPLE_TPL = `{
  "Przystapienie": {
    "data": "2025-10-14", // Data pisma z nagłówka (YYYY-MM-DD).
    "miejscowosc": "Gdańsk", // Miejscowość z nagłówka pisma.
    "sygnatura": "KIO 3812/25", // Sygnatura akt KIO, jeśli podana (np. 'KIO 1234/25').
    "strona": "zamawiajacy", // Po której stronie zgłoszono przystąpienie: "zamawiajacy" lub "odwolujacy".
    "data_odwolania": null // Data wniesienia odwołania, którego dotyczy przystąpienie.
  },
  "Przystepujacy": [
    {
      // Pełna nazwa wykonawcy zgłaszającego przystąpienie.
      "nazwa": "HYDRO-TRANS S.A.",
      "krs": null, // KRS przystępującego.
      "nip": null, // NIP przystępującego.
      "regon": null, // REGON przystępującego.
      "pelnomocnik": {
        "imie_nazwisko": null, // Imię i nazwisko pełnomocnika w mianowniku, bez tytułów.
        "mail": null // Adres e-mail pełnomocnika.
      }
    }
  ],
  "ZamowieniePubliczne": {
    "numer_bzp": null, // Numer ogłoszenia w BZP, format 'YYYY/BZP ########'.
    "numer_postepowania": null, // Numer referencyjny postępowania nadany przez zamawiającego.
    "tytul": null // Nazwa (tytuł) zamówienia.
  }
}`

export const TEMPLATE_PLACEHOLDER = `{
  "Faktura": {
    "numer": "FV/12/2025", // Numer faktury.
    "data_wystawienia": "2025-10-01", // Data wystawienia.
    "nip_sprzedawcy": null, // NIP sprzedawcy.
    "kwota_brutto": 1230.00 // Kwota brutto.
  }
}`

export const newRow = (): FieldRow => ({ name: "", type: "string", normalize: "auto", description: "" })

const TYPE_COLORS = ["bg-chart-1", "bg-chart-2", "bg-chart-3", "bg-chart-4", "bg-chart-5"]
const KNOWN_COLORS: Record<string, string> = { odwolanie: "bg-chart-1", pelnomocnictwo: "bg-chart-2", przelew: "bg-chart-3" }
/** Stable colour-dot class for a doctype name. */
export function typeColor(name: string): string {
  if (KNOWN_COLORS[name]) return KNOWN_COLORS[name]
  let h = 0
  for (const c of name) h = (h * 31 + c.charCodeAt(0)) >>> 0
  return TYPE_COLORS[3 + (h % 2)]
}
