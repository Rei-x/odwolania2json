import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { f1s, pb } from "./lib"
import { Dash } from "./parts"
import type { Benchmarks } from "./types"

function ProfilesTable({ profiles }: { profiles: NonNullable<Benchmarks["profiles_8b"]> }) {
  const head = "text-right text-xs text-muted-foreground"
  return (
    <Table>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <TableHead className="text-xs text-muted-foreground">Profil</TableHead>
          <TableHead className={head}>Śr. rozmiar</TableHead>
          <TableHead className={head}>F1 ślepy</TableHead>
          <TableHead className={head}>F1 warianty</TableHead>
          <TableHead className={head}>F1 trening</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {profiles.map((p, i) => {
          const [name, detail] = p.profile.split(/:\s*/, 2)
          return (
            <TableRow key={p.profile} className={i === 0 ? "bg-accent/50 hover:bg-accent/70" : undefined}>
              <TableCell className="whitespace-normal">
                <div className="flex items-center gap-1.5 font-medium">
                  {name.replace(/\s*\(domyślny\)/, "")}
                  {i === 0 && <Badge>domyślny</Badge>}
                </div>
                {detail && <div className="text-xs text-muted-foreground">{detail}</div>}
                {p.latency && <div className="text-xs text-muted-foreground">Czas: {p.latency}</div>}
              </TableCell>
              <TableCell className="text-right tabular-nums">{p.avg_params_b != null ? pb(p.avg_params_b) : <Dash />}</TableCell>
              <TableCell className="text-right font-medium tabular-nums">{f1s(p.blind) ?? <Dash />}</TableCell>
              <TableCell className="text-right tabular-nums">{f1s(p.variants) ?? <Dash />}</TableCell>
              <TableCell className="text-right tabular-nums">{f1s(p.train ?? p.train_sample) ?? <Dash />}</TableCell>
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}

export function DecisionSection({ data }: { data: Benchmarks }) {
  const profiles = data.profiles_8b ?? []
  return (
    <div className="grid gap-4">
      <Card>
        <CardContent>
          <ol className="grid gap-x-8 gap-y-4 md:grid-cols-2">
            {data.decision.reasons.map((p, i) => (
              <li key={i} className="flex gap-3">
                <span className="grid size-6 shrink-0 place-items-center rounded-full bg-primary/10 text-xs font-semibold text-primary">{i + 1}</span>
                <span className="text-sm leading-relaxed text-foreground/85">{p}</span>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>
      {profiles.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Profile na małych modelach</CardTitle>
          </CardHeader>
          <CardContent className="px-2 sm:px-4">
            <ProfilesTable profiles={profiles} />
          </CardContent>
        </Card>
      )}
    </div>
  )
}
