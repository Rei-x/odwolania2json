// Human labels for doctype names and schema keys, so users never see raw identifiers like
// "informacja_z_otwarcia_ofert" or "ZAMAWIAJACY". Display only: JSON keys stay untouched.
//
// Spelling priority for a key: explicit KEY_LABEL -> words found in the field's YAML description (exact diacritics
// from the author) -> the WORDS map below -> the key as written. WORDS lists only unambiguous words: e.g. "zadanie"
// (task) vs "żądanie" (demand) are both plausible in procurement, so it is never "restored".

import { useEffect, useState } from "react"
import { fmtNum } from "./format"

/** ASCII-folded word -> Polish spelling, for keys written without diacritics. Unambiguous words only. */
const WORDS: Record<string, string> = {
  // parties and documents
  odwolanie: "odwołanie", odwolania: "odwołania", odwolaniu: "odwołaniu", odwolujacy: "odwołujący", odwolujacego: "odwołującego",
  odwolawczej: "odwoławczej", odwolawcza: "odwoławcza",
  zamawiajacy: "zamawiający", zamawiajacego: "zamawiającego", zamawiajacych: "zamawiających",
  pelnomocnictwo: "pełnomocnictwo", pelnomocnictwa: "pełnomocnictwa", pelnomocnik: "pełnomocnik", pelnomocnika: "pełnomocnika",
  pelnomocnicy: "pełnomocnicy", pelnomocnikow: "pełnomocników",
  przystapienie: "przystąpienie", przystapienia: "przystąpienia", przystepujacy: "przystępujący", przystepujacego: "przystępującego",
  podpisujacy: "podpisujący", wykonujacy: "wykonujący", skladajacy: "składający", wnoszacy: "wnoszący",
  wykonawcow: "wykonawców", podwykonawcow: "podwykonawców", oferentow: "oferentów", czlonkow: "członków", czlonek: "członek",
  // procurement
  zamowienie: "zamówienie", zamowienia: "zamówienia", zamowien: "zamówień", zamowieniu: "zamówieniu",
  postepowanie: "postępowanie", postepowania: "postępowania", postepowan: "postępowań", postepowaniu: "postępowaniu",
  prowadzacy: "prowadzący", ogloszenie: "ogłoszenie", ogloszenia: "ogłoszenia", ogloszeniu: "ogłoszeniu",
  zlozenia: "złożenia", zlozone: "złożone", zlozonych: "złożonych", zlozona: "złożona", zlozono: "złożono",
  skladania: "składania", skladanie: "składanie", zlozenie: "złożenie", uslugi: "usługi", uslug: "usług", usluga: "usługa",
  srodek: "środek", wlasnie: "właśnie", zrodla: "źródła", szczegolowy: "szczegółowy", szczegolowe: "szczegółowe",
  czesc: "część", czesci: "części", sposob: "sposób", wysokosc: "wysokość", ilosc: "ilość", liczba: "liczba",
  budzet: "budżet", budzetu: "budżetu", wartosc: "wartość", wartosci: "wartości", laczna: "łączna", laczny: "łączny",
  laczne: "łączne", srednia: "średnia", sredni: "średni", najnizsza: "najniższa", najwyzsza: "najwyższa",
  rekojmia: "rękojmia", rekojmi: "rękojmi", wadium: "wadium", zabezpieczenie: "zabezpieczenie",
  miesiecy: "miesięcy", miesiace: "miesiące", miesiac: "miesiąc", dzien: "dzień", dni: "dni", tygodni: "tygodni",
  oplata: "opłata", oplaty: "opłaty", wplata: "wpłata", wplaty: "wpłaty", platnosc: "płatność", platnosci: "płatności",
  srodki: "środki", srodkow: "środków", zrodlo: "źródło", tresc: "treść", tytul: "tytuł", tytulu: "tytułu",
  czynnosc: "czynność", czynnosci: "czynności", miejscowosc: "miejscowość", miejscowosci: "miejscowości",
  wojewodztwo: "województwo", wojewodztwa: "województwa", panstwo: "państwo", kraj: "kraj",
  oswiadczenie: "oświadczenie", oswiadczenia: "oświadczenia", zalacznik: "załącznik", zalaczniki: "załączniki",
  wlasciciel: "właściciel", powod: "powód", uzasadnienie: "uzasadnienie", imie: "imię", nazwisko: "nazwisko",
  wplynelo: "wpłynęło", wplywu: "wpływu", sad: "sąd", sadu: "sądu", glowny: "główny", glowna: "główna",
  // already correct without diacritics (listed so they are not mistaken for unknown words)
  kwota: "kwota", termin: "termin", oferta: "oferta", oferty: "oferty", ofert: "ofert", wykonawca: "wykonawca",
  wykonawcy: "wykonawcy", przelew: "przelew", przelewu: "przelewu", odbiorca: "odbiorca", nadawca: "nadawca",
  rachunek: "rachunek", rachunku: "rachunku", data: "data", cena: "cena", ceny: "ceny", brutto: "brutto", netto: "netto",
  zadanie: "zadanie", zadania: "zadania", nazwa: "nazwa", numer: "numer", typ: "typ", opis: "opis", adres: "adres",
  mail: "e-mail", email: "e-mail",
}
/** Acronyms written in capitals. */
const UPPER = new Set(["nip", "krs", "regon", "pesel", "bzp", "ted", "kio", "uzp", "iban", "pzp", "vat", "id", "eu", "ue", "json", "pdf", "swz", "siwz"])

/** Labels for specific keys whose humanised form is not good enough. */
const KEY_LABEL: Record<string, string> = {
  czynnosc_dzien: "data czynności",
  czynnosc_powod_id: "powód (id)",
  czynnosc_opis: "czynność",
  "przez-pelnomocnika": "przez pełnomocnika",
  imie_nazwisko: "imię i nazwisko",
  numer_bzp: "nr BZP",
  numer_ted: "nr TED",
  numer_postepowania: "nr postępowania",
  numer_transakcji: "nr transakcji",
  prowadzacy_postepowanie: "prowadzący",
  mail: "e-mail",
  OdwolanieKIO: "Odwołanie",
  ZamowieniePubliczne: "Zamówienie",
  przelew_bankowy: "Przelew",
  pelnomocnicy: "pełnomocnik",
}

/** Built-in doctype display names. */
const DOCTYPE_LABEL: Record<string, string> = {
  odwolanie: "Odwołanie",
  pelnomocnictwo: "Pełnomocnictwo",
  przelew: "Przelew",
  potwierdzenie_przelewu: "Potwierdzenie przelewu",
  inny: "Nie rozpoznano typu",
  error: "Błąd",
}

/** Lowercase ASCII fold that keeps string length for NFC input (one character in, one character out). */
const fold = (s: string) =>
  s
    .normalize("NFC")
    .split("")
    .map((c) => (c === "ł" || c === "Ł" ? "l" : c.normalize("NFD").replace(/[̀-ͯ]/g, "")))
    .join("")
    .toLowerCase()

/** Split snake_case, kebab-case and CamelCase into lowercase words. */
function words(key: string): string[] {
  return key
    .replace(/([a-ząćęłńóśźż])([A-ZĄĆĘŁŃÓŚŹŻ])/g, "$1 $2")
    .split(/[\s_\-.]+/)
    .filter(Boolean)
    .map((w) => w.toLowerCase())
}

const word = (w: string) => (UPPER.has(w) ? w.toUpperCase() : WORDS[w] ?? w)
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)
const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")

/** Spell the key's words the way the field's own description writes them ("budzet_brutto" + "...budżet brutto..."). */
function spell(ws: string[], hint?: string): string[] {
  if (!hint) return ws.map(word)
  const h = hint.normalize("NFC")
  const f = fold(h)
  const at = (needle: string) => {
    const m = new RegExp(`(^|[^a-z0-9])${esc(needle)}(?=$|[^a-z0-9])`).exec(f)
    return m ? h.slice(m.index + m[1].length, m.index + m[1].length + needle.length).toLowerCase() : null
  }
  const phrase = at(ws.join(" "))
  if (phrase && phrase.split(" ").length === ws.length) return phrase.split(" ").map((w, i) => (UPPER.has(ws[i]) ? ws[i].toUpperCase() : w))
  return ws.map((w) => (UPPER.has(w) ? w.toUpperCase() : (w.length > 2 && at(w)) || word(w)))
}

/** "imie_nazwisko" -> "imię i nazwisko", "Zamawiajacy" -> "zamawiający" (lowercase, for field rows). */
export function fieldLabel(key: string, hint?: string): string {
  return KEY_LABEL[key] ?? spell(words(key), hint).join(" ")
}

/** Object keys that read better as a section title than their humanised form. */
const SECTION_LABEL: Record<string, string> = { data: "Dane", pelnomocnicy: "Pełnomocnik" }

/** Section heading: "Zamawiajacy" -> "Zamawiający" (CSS may upper-case it to "ZAMAWIAJĄCY"). */
export const sectionLabel = (key: string, hint?: string) => SECTION_LABEL[key] ?? cap(fieldLabel(key, hint))

/** "Odwolujacy[0].pelnomocnik.imie_nazwisko" -> "Pełnomocnik · imię i nazwisko" (array indices and wrapper objects dropped). */
export function pathLabel(path: string, meta?: DoctypeMeta): string {
  const parts = path.replace(/\[\d+\]/g, "").split(".").filter(Boolean)
  const leaf = parts[parts.length - 1] ?? path
  const parent = parts.length > 1 ? parts[parts.length - 2] : ""
  const wrapper = /^(OdwolanieKIO|ZamowieniePubliczne|przelew_bankowy|data)$/.test(parent)
  const h = meta?.hints
  return parent && !wrapper ? `${sectionLabel(parent, h?.[parent])} · ${fieldLabel(leaf, h?.[leaf])}` : fieldLabel(leaf, h?.[leaf])
}

/* ------------------------------------------------------------------ doctype names */

// Custom doctypes keep their human title as the first sentence of the YAML description ("Informacja z otwarcia ofert. …").
const titles = new Map<string, string>()
let loading: Promise<void> | null = null
const listeners = new Set<() => void>()

/** Feed doctype list rows (name + description) so custom types get their real title with diacritics. */
export function rememberDoctypes(rows: { name: string; description?: string }[]) {
  let changed = false
  for (const r of rows) {
    const first = (r.description || "").split(/\.\s/)[0].trim().replace(/\.$/, "")
    const key = words(r.name).join(" ")
    if (first && first.length <= 80 && fold(first).replace(/[^a-z0-9 ]/g, "").replace(/\s+/g, " ").startsWith(key) && titles.get(r.name) !== first) {
      titles.set(r.name, cap(first))
      changed = true
    }
  }
  if (changed) listeners.forEach((f) => f())
}

function loadTitles() {
  loading ??= fetch("/api/doctypes/list")
    .then((r) => (r.ok ? r.json() : []))
    .then((rows: { name: string; description?: string }[]) => rememberDoctypes(rows))
    .catch(() => {})
  return loading
}

/** "informacja_z_otwarcia_ofert" -> "Informacja z otwarcia ofert". */
export function doctypeLabel(name?: string | null): string {
  if (!name) return ""
  return DOCTYPE_LABEL[name] ?? titles.get(name) ?? cap(words(name).map(word).join(" "))
}

/** Re-renders the caller once custom doctype titles are known. */
export function useDoctypeLabels() {
  const [, bump] = useState(0)
  useEffect(() => {
    const f = () => bump((n) => n + 1)
    listeners.add(f)
    loadTitles()
    return () => {
      listeners.delete(f)
    }
  }, [])
  return doctypeLabel
}

/* ------------------------------------------------------------------ per-doctype YAML hints */

export type EnumLabels = Record<string, Record<string, string>>
/** What the doctype YAML says about its fields: enum labels and descriptions, keyed by the field's leaf name. */
export type DoctypeMeta = { enums: EnumLabels; hints: Record<string, string> }
const EMPTY: DoctypeMeta = { enums: {}, hints: {} }

/**
 * Field descriptions and enum labels from a doctype YAML, without a YAML parser: every non-meta key opens a field;
 * `description:` and `{value: X, label: "..."}` items that follow (inline or in its block) belong to it.
 */
export function parseDoctypeYaml(yaml: string): DoctypeMeta {
  const enums: EnumLabels = {}
  const hints: Record<string, string> = {}
  const meta = new Set(["values", "type", "description", "label", "value", "normalize", "pattern", "properties", "items", "dedupe", "required"])
  const item = /\{\s*value:\s*["']?([^,"'}]+?)["']?\s*,\s*label:\s*["']?([^"'}]+?)["']?\s*\}/g
  const desc = /description:\s*(?:"([^"]*)"|'([^']*)'|([^,}\n]+))/
  let field: string | null = null
  let inFields = false
  for (const line of yaml.split("\n")) {
    if (/^fields:/.test(line)) inFields = true
    else if (/^\S/.test(line)) inFields = false // top-level key: name, description, classify, deterministic, ...
    if (!inFields) continue
    const km = /^\s*([\w-]+):/.exec(line)
    if (km && !meta.has(km[1])) field = km[1]
    if (!field) continue
    const d = desc.exec(line)
    if (d) hints[field] ??= (d[1] ?? d[2] ?? d[3] ?? "").trim()
    for (const v of line.matchAll(item)) (enums[field] ??= {})[v[1].trim()] ??= v[2].trim()
  }
  return { enums, hints }
}

const metaCache = new Map<string, DoctypeMeta>()
const metaLoading = new Set<string>()

/** YAML hints of a saved doctype (fetched once from /api/doctypes/<name>/yaml); re-renders when they arrive. */
export function useDoctypeMeta(doctype?: string | null): DoctypeMeta {
  const [, bump] = useState(0)
  useEffect(() => {
    if (!doctype || metaCache.has(doctype) || metaLoading.has(doctype)) return
    metaLoading.add(doctype)
    fetch(`/api/doctypes/${encodeURIComponent(doctype)}/yaml`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d: { yaml?: string } | null) => {
        metaCache.set(doctype, d?.yaml ? parseDoctypeYaml(d.yaml) : EMPTY)
        bump((n) => n + 1)
      })
      .catch(() => metaCache.set(doctype, EMPTY))
  }, [doctype])
  return (doctype && metaCache.get(doctype)) || EMPTY
}

/* ------------------------------------------------------------------ values */

const BOOL_KEY = /^(przez|czy|is|has|ma)[-_]/i
const MONEY_KEY = /kwota|budzet|budżet|wartosc|wartość|cena|wadium/i
const SNAKE_WORDS = /^[a-ząćęłńóśźż]+(_[a-ząćęłńóśźż]+)+$/

/**
 * Display value of a leaf: yes/no for boolean-like fields ("przez-pelnomocnika": 1 -> "tak"), the YAML label for enum
 * values ("9 · Decyzja o unieważnieniu postępowania"), money in money-like fields ("11 000 000,00 zł"), humanised
 * snake-case enums ("osoba_prawna" -> "osoba prawna"), "—" for empty. Display only; JSON and the edit box keep the raw value.
 */
export function displayValue(key: string, v: unknown, meta?: DoctypeMeta): string {
  if (v === null || v === undefined || v === "") return "—"
  if (typeof v === "boolean") return v ? "tak" : "nie"
  if (BOOL_KEY.test(key) && (v === 0 || v === 1 || v === "0" || v === "1")) return Number(v) === 1 ? "tak" : "nie"
  if (typeof v === "object") return JSON.stringify(v)
  const label = meta?.enums[key]?.[String(v)]
  if (label) return typeof v === "number" ? `${v} · ${label}` : label
  if (MONEY_KEY.test(key) && !/_id$|procent|proc$|liczba/i.test(key)) {
    const n = typeof v === "number" ? v : /^\d+([.,]\d{1,2})?$/.test(String(v).trim()) ? Number(String(v).trim().replace(",", ".")) : NaN
    if (isFinite(n)) return `${fmtNum(n, 2, 2)} zł`
  }
  if (typeof v === "string" && SNAKE_WORDS.test(v)) return v.split("_").map(word).join(" ")
  return String(v)
}

/* ------------------------------------------------------------------ models */

/** "mistralai/ministral-8b-2512" -> "Ministral 8B" */
export function prettyModel(id?: string | null): string {
  if (!id) return ""
  if (id === "deterministic") return "reguły"
  const base = (String(id).split("/").pop() || id).replace(/[-_:]?\d{4}$/, "").replace(/-(it|instruct|chat)$/i, "")
  return base
    .split(/[-_]/)
    .filter(Boolean)
    .map((t) => (/^\d+(\.\d+)?[bkmt]$/i.test(t) || /^a\d+b$/i.test(t) ? t.toUpperCase() : t[0].toUpperCase() + t.slice(1)))
    .join(" ")
}
