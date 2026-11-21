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
import { f1s, fmt, usd } from "./lib"
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
  ["decyzja", "Dlaczego małe modele"],
] as const

function Kpis({ data }: { data: Benchmarks }) {
  const auto = data.profiles_8b?.[0]
  const chosen = data.models.filter((m) => m.chosen && m.cost_usd?.train != null).sort((a, b) => a.cost_usd!.train! - b.cost_usd!.train!)[0]
  const median = auto?.latency?.match(/mediana\s+([\d.,]+)\s*s/)?.[1]?.replace(".", ",")
  const items: { v: string; s?: string; t: string; accent?: boolean }[] = [
    ...(auto?.blind != null ? [{ v: f1s(auto.blind)!, t: "F1 na ślepym zbiorze (nowe sprawy), profil Auto" }] : []),
    ...(chosen ? [{ v: usd(chosen.cost_usd!.train)!, t: `za 36 dokumentów modelem ${chosen.name} przez API`, accent: true }] : []),
    ...(median ? [{ v: median, s: " s", t: "mediana czasu na dokument" }] : []),
    { v: `~${fmt(data.real_corpus.agreement_low, 2)}`, t: `zgodność na ${data.real_corpus.docs} prawdziwych dokumentach KIO` },
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
                lead="Model 8B, który uruchomisz na własnym serwerze, daje prawie tę samą jakość co modele setki razy większe."
              >
                <SizeScatter models={data.models} />
              </Section>
              <Section id="tabela" title="Wszystkie przetestowane modele" lead="Koszt to przebieg 36 dokumentów treningowych przez API (OpenRouter, USD).">
                <ModelsTable models={data.models} />
              </Section>
            </>
          )}

          {(data || error) && <SweepSection />}

          {data && (
            <>
              <Section id="koszt" title="Koszt przebiegu" lead="Przebieg 36 dokumentów przez API kosztuje grosze. Reguły YAML nie kosztują nic.">
                <CostBars models={data.models} />
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
                <DecisionSection data={data} />
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
