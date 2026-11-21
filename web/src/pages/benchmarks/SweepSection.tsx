import { RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"
import { useSweep } from "./hooks"
import { Section } from "./parts"
import { SweepCallouts } from "./SweepCallouts"
import { SweepScatter } from "./SweepScatter"
import { SweepTable } from "./SweepTable"
import type { Band } from "./types"

export function SweepSection({ bands }: { bands: Band[] }) {
  const { runs, status, loading, auto, setAuto, refresh, seen } = useSweep(bands)
  return (
    <Section
      id="sweep"
      title="Sweep modeli"
      lead="Ten sam pipeline z jednym modelem na wszystko, na 12 sprawach treningowych i zamrożonym ślepym zbiorze. Sweep trwa, więc dane dorastają."
      aside={
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span className="tabular-nums" aria-live="polite">
            {status}
          </span>
          <Button variant="outline" size="sm" className="rounded-full" onClick={refresh} title="Pobierz najnowsze wyniki">
            <RefreshCw className={cn(loading && "animate-spin")} />
            Odśwież
          </Button>
          <Button
            variant={auto ? "default" : "outline"}
            size="sm"
            className={cn("rounded-full", auto && "bg-foreground text-background hover:bg-foreground/85")}
            onClick={() => setAuto(!auto)}
            aria-pressed={auto}
            title="Automatyczne odświeżanie co 30 s"
          >
            <span className={cn("size-2 rounded-full", auto ? "bg-success shadow-[0_0_0_3px_color-mix(in_oklab,var(--success)_30%,transparent)]" : "bg-muted-foreground/50")} />
            Auto 30 s
          </Button>
        </div>
      }
    >
      {runs == null ? (
        <div className="grid gap-3">
          <div className="grid gap-3 sm:grid-cols-3">
            <Skeleton className="h-32" />
            <Skeleton className="h-32" />
            <Skeleton className="h-32" />
          </div>
          <Skeleton className="h-80" />
        </div>
      ) : runs.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground">
            Brak wyników sweepu (docs/bench_sweep.json jeszcze nie istnieje albo jest pusty). Strona odświeży się sama, gdy pojawią się dane.
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4">
          <SweepScatter runs={runs} bands={bands} />
          <SweepCallouts runs={runs} />
          <SweepTable runs={runs} seen={seen} />
        </div>
      )}
    </Section>
  )
}
