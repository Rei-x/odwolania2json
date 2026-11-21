import { useEffect } from "react"
import { Link } from "react-router-dom"
import { ArrowRight } from "lucide-react"
import { SiteNav } from "@/components/brand/site-nav"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { CostBars } from "./CostBars"
import { DatasetsSection } from "./DatasetsSection"
import { DecisionSection } from "./DecisionSection"
import { useBenchmarks } from "./hooks"
import { DEFAULT_BANDS, fmt, pointsFor } from "./lib"
import { ModelsTable } from "./ModelsTable"
import { OcrSection } from "./OcrSection"
import { Section } from "./parts"
import { SizeScatter } from "./SizeScatter"
import { SweepSection } from "./SweepSection"
import type { Benchmarks } from "./types"

const TOC = [
  ["rozmiar", "Rozmiar a F1"],
  ["tabela", "Wszystkie modele"],
  ["sweep", "Sweep modeli"],
  ["koszt", "Koszt"],
  ["ocr", "OCR"],
  ["zbiory", "Zbiory testowe"],
  ["decyzja", "Dlaczego ≤ 8B"],
] as const

function Kpis({ data }: { data: Benchmarks }) {
  const ms = data.models
  const measured = ms.filter((m) => m.f1.train != null && m.arch !== "rules" && m.arch !== "router")
  const top = measured.filter((m) => m.f1.train! >= 0.99).length
  const chosen = ms.filter((m) => m.chosen && m.params_b != null)
  const avg = chosen.length ? chosen.reduce((a, m) => a + m.params_b!, 0) / chosen.length : null
  const items = [
    { v: ms.length, s: null, t: "modeli i konfiguracji porównanych na tych samych dokumentach" },
    { v: top, s: ` / ${measured.length}`, t: "modeli LLM z F1 ≥ 0,99 na danych treningowych" },
    {
      v: avg != null ? pointsFor(avg, data.scoring.bands) : "—",
      s: " pkt",
      t: `za rozmiar w profilu Auto: reguły → ${chosen.map((m) => m.name.replace("Ministral ", "")).join(" / ")} (średnio ${avg != null ? String(avg).replace(".", ",") : "—"}B)`,
      accent: true,
    },
    { v: `~${fmt(data.real_corpus.agreement_low, 2)}`, s: null, t: `zgodność na ${data.real_corpus.docs} prawdziwych dokumentach KIO` },
  ]
  return (
    <div className="mt-8 grid grid-cols-2 gap-3 lg:grid-cols-4">
      {items.map((k, i) => (
        <Card key={i} className={k.accent ? "bg-accent/70 ring-primary/25" : undefined}>
          <CardContent>
            <b className={`block text-[30px] leading-tight font-bold tracking-tight tabular-nums ${k.accent ? "text-primary" : ""}`}>
              {k.v}
              {k.s && <small className="ml-0.5 text-[15px] font-semibold tracking-normal text-muted-foreground">{k.s}</small>}
            </b>
            <span className="mt-1.5 block text-[13px] leading-snug text-muted-foreground">{k.t}</span>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

function Toc() {
  return (
    <nav aria-label="Sekcje" className="sticky top-14 z-30 -mx-4 border-b bg-background/85 px-4 backdrop-blur-md">
      <div className="flex gap-1 overflow-x-auto py-2 [scrollbar-width:none]">
        {TOC.map(([id, label]) => (
          <a key={id} href={`#${id}`} className="shrink-0 rounded-full px-3 py-1 text-[13px] whitespace-nowrap text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground">
            {label}
          </a>
        ))}
      </div>
    </nav>
  )
}

export default function BenchmarksPage() {
  const { data, error } = useBenchmarks()
  const bands = data?.scoring.bands ?? DEFAULT_BANDS
  useEffect(() => {
    document.title = "Benchmarki modeli · Wróbelek"
  }, [])
  return (
    <>
      <div className="min-h-svh bg-background">
        <SiteNav>
          <Button render={<Link to="/app" />} nativeButton={false} size="sm" className="rounded-full">
            Wypróbuj <ArrowRight />
          </Button>
        </SiteNav>
        <main className="mx-auto max-w-[1180px] px-4 pb-20">
          <Toc />
          <header className="pt-10 sm:pt-14">
            <div className="text-xs font-semibold tracking-[0.12em] text-primary uppercase">Benchmarki</div>
            <h1 className="mt-2.5 max-w-[820px] text-[clamp(32px,5vw,54px)] leading-[1.05] font-bold tracking-[-0.035em] text-balance">
              Który model, jakie wyniki i dlaczego wybraliśmy modele do 8B
            </h1>
            <p className="mt-3.5 max-w-[720px] text-[17px] leading-relaxed text-muted-foreground">
              F1 według reguł organizatora, liczone na tych samych dokumentach dla każdego modelu.
            </p>
            {data ? (
              <Kpis data={data} />
            ) : error ? null : (
              <div className="mt-8 grid grid-cols-2 gap-3 lg:grid-cols-4">
                {[0, 1, 2, 3].map((i) => (
                  <Skeleton key={i} className="h-28" />
                ))}
              </div>
            )}
          </header>

          {error && (
            <Card className="mt-10 ring-destructive/30">
              <CardContent className="py-6 text-center text-destructive">Nie udało się wczytać docs/benchmarks.json: {error}</CardContent>
            </Card>
          )}

          {data && (
            <>
              <Section
                id="rozmiar"
                title="Rozmiar modelu a jakość"
                lead="Prawie każdy model mieści się w F1 0,985–1,000. O punktach decyduje rozmiar (tło), nie jakość."
              >
                <SizeScatter models={data.models} bands={bands} />
              </Section>
              <Section id="tabela" title="Wszystkie przetestowane modele" lead="Koszt to przebieg 36 dokumentów treningowych przez API (OpenRouter, USD).">
                <ModelsTable models={data.models} bands={bands} />
              </Section>
            </>
          )}

          {(data || error) && <SweepSection bands={bands} />}

          {data && (
            <>
              <Section id="koszt" title="Koszt przebiegu" lead="Najtańsze są duże modele MoE, ale za ich rozmiar jest 0 pkt.">
                <CostBars models={data.models} bands={bands} />
              </Section>
              <Section id="ocr" title="OCR skanów" lead={`${data.ocr.dataset}. Średnie modele dorównują największym.`}>
                <OcrSection ocr={data.ocr} />
              </Section>
              <Section
                id="zbiory"
                title="Zbiory testowe"
                lead="Poza danymi treningowymi: zamrożony ślepy zbiór, trudne warianty, skany i prawdziwe dokumenty KIO."
              >
                <DatasetsSection data={data} />
              </Section>
              <Section id="decyzja" title={data.decision.headline}>
                <DecisionSection data={data} bands={bands} />
              </Section>
            </>
          )}
        </main>
        <footer className="mx-auto flex max-w-[1180px] flex-wrap gap-4 border-t px-4 pt-7 pb-14 text-[13px] text-muted-foreground">
          {data && <span>Dane: docs/benchmarks.json · aktualizacja {data.updated}</span>}
          <Link to="/" className="hover:text-foreground">
            Strona główna
          </Link>
          <Link to="/app" className="hover:text-foreground">
            Aplikacja
          </Link>
          <a href="/api/benchmarks" className="hover:text-foreground">
            Dane (JSON)
          </a>
        </footer>
      </div>
    </>
  )
}
