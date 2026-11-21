import { Card, CardContent } from "@/components/ui/card"
import { f1s, fmt } from "./lib"
import type { Benchmarks } from "./types"

/** One card per test set, with the default (Auto) profile's result on it. */
export function DatasetsSection({ data }: { data: Benchmarks }) {
  const auto = data.profiles_8b?.[0]
  const rc = data.real_corpus
  const result: Record<string, string | null | undefined> = {
    train: f1s(auto?.train_sample ?? auto?.train),
    blind: f1s(auto?.blind),
    variants: f1s(auto?.variants),
    ocr: f1s(auto?.uzp_scans),
    real: `${fmt(rc.agreement_low, 2)}–${fmt(rc.agreement_high, 2)}`,
  }
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
      {data.datasets.map((d) => (
        <Card key={d.id} size="sm">
          <CardContent className="flex h-full flex-col">
            <div className="text-[13px] font-medium">{d.name}</div>
            <div className="text-xs text-muted-foreground">{d.docs != null ? `${d.docs} dokumentów` : "20 spraw"}</div>
            <p className="mt-2 flex-1 text-xs leading-relaxed text-muted-foreground">{d.desc}</p>
            {result[d.id] && (
              <div className="mt-3 border-t pt-2.5">
                <div className="text-2xl font-semibold tracking-tight tabular-nums">{result[d.id]}</div>
                <div className="text-xs text-muted-foreground">{d.id === "real" ? "zgodność z adnotacją" : "F1 profilu Auto"}</div>
              </div>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
