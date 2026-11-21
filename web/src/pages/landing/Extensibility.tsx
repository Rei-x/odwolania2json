import { useEffect, useState, type CSSProperties, type ReactNode } from "react"
import { Plus } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Link } from "react-router-dom"
import { cn } from "@/lib/utils"
import { prefersReducedMotion, useInViewOnce } from "./hooks"
import { Reveal, SectionHead } from "./Reveal"

type Line = ["c" | "k" | "t", string] | ["kv" | "kn", string, string]

const YAML: Line[] = [
  ["c", "# nowy typ dokumentu: zero zmian w kodzie"],
  ["kv", "name", "przystapienie"],
  ["kv", "description", "Zgłoszenie przystąpienia do postępowania odwoławczego"],
  ["k", "classify"],
  ["kv", "  keywords", "{'PRZYSTĄPIENIE': 6, 'po stronie': 3}"],
  ["kv", "  filename", "[przystapienie]"],
  ["kn", "pages", "2"],
  ["kn", "few_shot", "2"],
  ["kv", "instructions", "|"],
  ["t", "  - Sygnatura w formacie KIO 1234/26."],
  ["k", "fields"],
  ["k", "  przystapienie"],
  ["kv", "    type", "object"],
  ["k", "    properties"],
  ["kv", "      sygnatura", "{type: string, pattern: 'KIO \\d+/\\d{2}'}"],
  ["kv", "      data", "{type: date}"],
  ["kv", "      przystepujacy", "{type: string}"],
  ["kv", "      nip", "{type: string, normalize: [nip]}"],
  ["k", "      po_stronie"],
  ["kv", "        type", "enum"],
  ["k", "        values"],
  ["t", "          - {value: 1, label: Zamawiającego}"],
  ["t", "          - {value: 2, label: Odwołującego}"],
]

// Static strings only; escaped before highlighting.
const E = (s: string) => s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c]!)
const hl = (v: string) =>
  E(v)
    .replace(/(\{|\}|\[|\]|,)/g, '<span class="p">$1</span>')
    .replace(/\b(\d+)\b(?![^<]*>)/g, '<span class="n">$1</span>')
    .replace(/(type|pattern|normalize|value|label):/g, '<span class="k">$1</span>:')
const lineHtml = (l: Line) =>
  l[0] === "c" ? `<span class="c">${E(l[1])}</span>`
  : l[0] === "t" ? `<span class="s">${hl(l[1])}</span>`
  : l[0] === "k" ? `<span class="k">${E(l[1])}</span>:`
  : l[0] === "kn" ? `<span class="k">${E(l[1])}</span>: <span class="n">${l[2]}</span>`
  : `<span class="k">${E(l[1])}</span>: <span class="s">${hl(l[2] ?? "")}</span>`
const plain = (l: Line) => (l[0] === "c" || l[0] === "t" ? l[1] : l[0] === "k" ? `${l[1]}:` : `${l[1]}: ${l[2]}`)
const FULL = YAML.map(lineHtml).join("\n")
const CARET = '<span class="caret"></span>'

/** YAML that types itself once the editor is in view, then the new doctype pill pops in. */
function Editor() {
  const [ref, seen] = useInViewOnce<HTMLDivElement>({ threshold: 0.45 })
  const [html, setHtml] = useState(() => (prefersReducedMotion() ? FULL : CARET))
  const [done, setDone] = useState(() => prefersReducedMotion())

  useEffect(() => {
    if (!seen || done) return
    let li = 0, ci = 0, timer = 0
    const out: string[] = []
    const step = () => {
      if (li >= YAML.length) { setHtml(FULL); setDone(true); return }
      const full = plain(YAML[li])
      ci = Math.min(full.length, ci + 2 + ((Math.random() * 3) | 0))
      setHtml(out.join("\n") + (out.length ? "\n" : "") + E(full.slice(0, ci)) + CARET)
      if (ci >= full.length) { out.push(lineHtml(YAML[li])); li++; ci = 0; timer = window.setTimeout(step, 70) }
      else timer = window.setTimeout(step, 16)
    }
    step()
    return () => clearTimeout(timer)
  }, [seen, done])

  const pill = (label: string, c: string, extra?: string) => (
    <span className={cn("pill", extra)} style={{ "--c": c } as CSSProperties}><span className="d" />{label}</span>
  )

  return (
    <Reveal className="editor">
      <div ref={ref}>
        <div className="ebar"><i /><i /><i /><span>config/doctypes/<b>przystapienie.yaml</b></span></div>
        <pre className="ecode" aria-label="Przykładowy plik YAML z nowym typem dokumentu" dangerouslySetInnerHTML={{ __html: html }} />
        <div className="eres">
          {pill("odwołanie", "var(--acc)")}
          {pill("pełnomocnictwo", "var(--teal-l)")}
          {pill("przelew", "var(--amber-l)")}
          {pill("+ przystąpienie", "var(--white)", cn("new", done && "on"))}
          <span className="nocode">0 linii kodu</span>
        </div>
      </div>
    </Reveal>
  )
}

const TILES: { code: string; title: string; body: ReactNode }[] = [
  { code: "config/case.yaml", title: "Kontrole sprawy", body: "Nowa reguła spójności to kilka linii." },
  { code: "settings.yaml", title: "Profile suwaka", body: "Modele, OCR i router per profil." },
  { code: "OpenAI API", title: "Dowolny model open-weight", body: "Dostawcy w UE, data_collection: deny." },
  { code: "REST API", title: "Integracja z Urzędem", body: (
    <span className="api">
      <span><em className="po">POST</em>/api/process</span>
      <span><em>GET</em>/api/case/{"{id}"}</span>
      <span><em className="po">POST</em>/api/feedback</span>
    </span>
  ) },
]

export function Extensibility() {
  return (
    <section className="sec" id="rozszerzalnosc">
      <div className="wrap">
        <SectionHead eyebrow="Rozszerzalność" title="Nowy typ dokumentu = jeden plik YAML.">
          <p className="lede">Bez zmian w kodzie.</p>
          <Button nativeButton={false} variant="outline" render={<Link to="/nowy-typ" />} className="mt-6 h-10 rounded-full bg-card px-4">
            <Plus /> Otwórz kreator
          </Button>
        </SectionHead>
        <div className="ext">
          <Editor />
          <div className="tiles">
            {TILES.map((t, i) => (
              <Reveal key={t.title} delay={(i % 3) as 0 | 1 | 2}>
                <Card className="lp-card tile h-full">
                  <CardHeader>
                    <Badge variant="secondary" className="font-mono text-primary">{t.code}</Badge>
                    <CardTitle className="mt-2 text-base font-semibold">{t.title}</CardTitle>
                    <CardDescription>{t.body}</CardDescription>
                  </CardHeader>
                </Card>
              </Reveal>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
