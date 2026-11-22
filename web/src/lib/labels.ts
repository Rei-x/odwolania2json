// Human labels for doctype names and schema keys, so users never see raw identifiers like
// "informacja_z_otwarcia_ofert" or "ZAMAWIAJACY". Display only: JSON keys stay untouched.

import { useEffect, useState } from "react"

/** ASCII-folded word -> Polish spelling, for keys written without diacritics. */
const WORDS: Record<string, string> = {
  odwolanie: "odwołanie", odwolania: "odwołania", odwolujacy: "odwołujący", odwolujacego: "odwołującego", odwolawczej: "odwoławczej",
  zamawiajacy: "zamawiający", zamawiajacego: "zamawiającego", zamawiajacych: "zamawiających",
  pelnomocnictwo: "pełnomocnictwo", pelnomocnictwa: "pełnomocnictwa", pelnomocnik: "pełnomocnik", pelnomocnika: "pełnomocnika",
  pelnomocnicy: "pełnomocnicy", pelnomocnikow: "pełnomocników",
  przystapienie: "przystąpienie", przystapienia: "przystąpienia", przystepujacy: "przystępujący", przystepujacego: "przystępującego",
  podpisujacy: "podpisujący", wykonujacy: "wykonujący",
  zamowienie: "zamówienie", zamowienia: "zamówienia", zamowien: "zamówień",
  postepowanie: "postępowanie", postepowania: "postępowania", postepowan: "postępowań", prowadzacy: "prowadzący",
  czynnosc: "czynność", czynnosci: "czynności", miejscowosc: "miejscowość", wartosc: "wartość", wartosci: "wartości",
  tytul: "tytuł", tytulu: "tytułu", imie: "imię", nazwisko: "nazwisko",
  oswiadczenie: "oświadczenie", oswiadczenia: "oświadczenia", zalacznik: "załącznik", zalaczniki: "załączniki",
  wplata: "wpłata", wplaty: "wpłaty", platnosc: "płatność", platnosci: "płatności", oplata: "opłata", oplaty: "opłaty",
  srodki: "środki", srodkow: "środków", sad: "sąd", sadu: "sądu", zrodlo: "źródło", tresc: "treść", liczba: "liczba",
  powod: "powód", dzien: "dzień", miesiac: "miesiąc", rok: "rok", godzina: "godzina",
  odbiorca: "odbiorca", nadawca: "nadawca", wlasciciel: "właściciel", siedziba: "siedziba", ulica: "ulica",
  uzasadnienie: "uzasadnienie", zadania: "żądania", zadanie: "żądanie", zarzuty: "zarzuty", wnioski: "wnioski",
  ofert: "ofert", oferta: "oferta", oferty: "oferty", otwarcia: "otwarcia", cena: "cena", ceny: "ceny", kwota: "kwota",
  potwierdzenie: "potwierdzenie", przelewu: "przelewu", przelew: "przelew", rachunek: "rachunek", rachunku: "rachunku",
  wykonawca: "wykonawca", wykonawcy: "wykonawcy", wykonawcow: "wykonawców", umowa: "umowa", umowy: "umowy",
  informacja: "informacja", decyzja: "decyzja", wyrok: "wyrok", postanowienie: "postanowienie", sygnatura: "sygnatura",
  krajowej: "krajowej", izby: "izby", prezes: "prezes", mocodawca: "mocodawca", reprezentacja: "reprezentacja",
  data: "data", numer: "numer", nazwa: "nazwa", typ: "typ", opis: "opis", adres: "adres", mail: "e-mail", email: "e-mail",
  przez: "przez", czy: "czy", na: "na", z: "z", do: "do", od: "od", i: "i", w: "w", o: "o", nr: "nr",
}
/** Acronyms written in capitals. */
const UPPER = new Set(["nip", "krs", "regon", "pesel", "bzp", "ted", "kio", "uzp", "iban", "pzp", "vat", "id", "eu", "ue", "json", "pdf"])

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

const fold = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/ł/g, "l").replace(/Ł/g, "L").toLowerCase()

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

/** "imie_nazwisko" -> "imię i nazwisko", "Zamawiajacy" -> "zamawiający" (lowercase, for field rows). */
export function fieldLabel(key: string): string {
  return KEY_LABEL[key] ?? words(key).map(word).join(" ")
}

/** Object keys that read better as a section title than their humanised form. */
const SECTION_LABEL: Record<string, string> = { data: "Dane", pelnomocnicy: "Pełnomocnik" }

/** Section heading: "Zamawiajacy" -> "Zamawiający" (CSS may upper-case it to "ZAMAWIAJĄCY"). */
export const sectionLabel = (key: string) => SECTION_LABEL[key] ?? cap(fieldLabel(key))

/** "Odwolujacy[0].pelnomocnik.imie_nazwisko" -> "Pełnomocnik · imię i nazwisko" (array indices and wrapper objects dropped). */
export function pathLabel(path: string): string {
  const parts = path.replace(/\[\d+\]/g, "").split(".").filter(Boolean)
  const leaf = parts[parts.length - 1] ?? path
  const parent = parts.length > 1 ? parts[parts.length - 2] : ""
  const wrapper = /^(OdwolanieKIO|ZamowieniePubliczne|przelew_bankowy|data)$/.test(parent)
  return parent && !wrapper ? `${sectionLabel(parent)} · ${fieldLabel(leaf)}` : fieldLabel(leaf)
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

/* ------------------------------------------------------------------ values */

export type EnumLabels = Record<string, Record<string, string>>

/**
 * Enum labels from a doctype YAML without a YAML parser: for every key followed by `{value: X, label: "..."}` items
 * (block or inline list) collect value -> label. Keyed by the field's leaf name.
 */
export function parseEnumLabels(yaml: string): EnumLabels {
  const out: EnumLabels = {}
  const meta = new Set(["values", "type", "description", "label", "value", "normalize", "pattern", "properties", "items", "dedupe", "required"])
  const item = /\{\s*value:\s*["']?([^,"'}]+?)["']?\s*,\s*label:\s*["']?([^"'}]+?)["']?\s*\}/g
  let field: string | null = null
  for (const line of yaml.split("\n")) {
    const km = /^\s*([\w-]+):/.exec(line)
    if (km && !meta.has(km[1])) field = km[1]
    if (!field) continue
    for (const v of line.matchAll(item)) (out[field] ??= {})[v[1].trim()] ??= v[2].trim()
  }
  return out
}

const enumCache = new Map<string, EnumLabels>()
const enumLoading = new Set<string>()

/** Enum labels of a saved doctype (fetched once from /api/doctypes/<name>/yaml); re-renders when they arrive. */
export function useEnumLabels(doctype?: string | null): EnumLabels {
  const [, bump] = useState(0)
  useEffect(() => {
    if (!doctype || enumCache.has(doctype) || enumLoading.has(doctype)) return
    enumLoading.add(doctype)
    fetch(`/api/doctypes/${encodeURIComponent(doctype)}/yaml`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d: { yaml?: string } | null) => {
        enumCache.set(doctype, d?.yaml ? parseEnumLabels(d.yaml) : {})
        bump((n) => n + 1)
      })
      .catch(() => enumCache.set(doctype, {}))
  }, [doctype])
  return (doctype && enumCache.get(doctype)) || {}
}

const BOOL_KEY = /^(przez|czy|is|has|ma)[-_]/i
const SNAKE_WORDS = /^[a-ząćęłńóśźż]+(_[a-ząćęłńóśźż]+)+$/

/**
 * Display value of a leaf: yes/no for boolean-like fields ("przez-pelnomocnika": 1 -> "tak"), the YAML label for enum
 * values ("9 · Decyzja o unieważnieniu postępowania"), humanised snake-case enums ("osoba_prawna" -> "osoba prawna"),
 * "—" for empty. Display only; JSON and the edit box keep the raw value.
 */
export function displayValue(key: string, v: unknown, enums?: EnumLabels): string {
  if (v === null || v === undefined || v === "") return "—"
  if (typeof v === "boolean") return v ? "tak" : "nie"
  if (BOOL_KEY.test(key) && (v === 0 || v === 1 || v === "0" || v === "1")) return Number(v) === 1 ? "tak" : "nie"
  if (typeof v === "object") return JSON.stringify(v)
  const label = enums?.[key]?.[String(v)]
  if (label) return typeof v === "number" ? `${v} · ${label}` : label
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
