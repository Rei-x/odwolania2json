import { Bar, BarChart, CartesianGrid, Cell, LabelList, XAxis, YAxis } from "recharts"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { bandStrength, f1s, pb } from "./lib"
import { Dash, PointsPill } from "./parts"
import type { Band, Benchmarks } from "./types"

const config = { points: { label: "Punkty", color: "var(--sage)" } } satisfies ChartConfig

function BandsChart({ bands }: { bands: Band[] }) {
  const data = bands.map((b) => ({ label: b.label ?? "", points: b.points }))
  return (
    <ChartContainer config={config} className="aspect-auto h-[220px] w-full">
      <BarChart data={data} margin={{ top: 22, right: 4, bottom: 0, left: 0 }}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="label" tickLine={false} axisLine={false} interval={0} tick={{ fontSize: 11 }} />
        <YAxis hide domain={[0, 20]} />
        <ChartTooltip cursor={false} content={<ChartTooltipContent hideIndicator />} />
        <Bar dataKey="points" radius={6} isAnimationActive={false}>
          {data.map((d) => (
            <Cell key={d.label} fill="var(--color-points)" fillOpacity={d.points >= 20 ? 1 : Math.max(0.18, bandStrength(d.points) * 3)} />
          ))}
          <LabelList dataKey="points" position="top" className="fill-foreground" fontSize={12} fontWeight={600} />
        </Bar>
      </BarChart>
    </ChartContainer>
  )
}

function ProfilesTable({ profiles }: { profiles: NonNullable<Benchmarks["profiles_8b"]> }) {
  const head = "text-right text-xs text-muted-foreground"
  return (
    <Table>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <TableHead className="text-xs text-muted-foreground">Profil</TableHead>
          <TableHead className={head}>Śr. rozmiar</TableHead>
          <TableHead className={head}>Punkty</TableHead>
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
              </TableCell>
              <TableCell className="text-right tabular-nums">{p.avg_params_b != null ? pb(p.avg_params_b) : <Dash />}</TableCell>
              <TableCell className="text-right">
                <PointsPill p={p.points} />
              </TableCell>
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

export function DecisionSection({ data, bands }: { data: Benchmarks; bands: Band[] }) {
  const profiles = data.profiles_8b ?? []
  return (
    <div className="grid gap-4">
      <div className="grid items-start gap-4 lg:grid-cols-[1.2fr_1fr]">
        <Card>
          <CardContent>
            <ol className="space-y-3">
              {data.decision.points.map((p, i) => (
                <li key={i} className="flex gap-3">
                  <span className="grid size-6 shrink-0 place-items-center rounded-full bg-primary/10 text-xs font-semibold text-primary">{i + 1}</span>
                  <span className="text-sm leading-relaxed text-foreground/85">{p}</span>
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Punkty UZP za rozmiar</CardTitle>
            <CardDescription>{data.scoring.rule}</CardDescription>
          </CardHeader>
          <CardContent>
            <BandsChart bands={bands} />
          </CardContent>
        </Card>
      </div>
      {profiles.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Profile w paśmie ≤ 8B</CardTitle>
          </CardHeader>
          <CardContent className="px-2 sm:px-4">
            <ProfilesTable profiles={profiles} />
          </CardContent>
        </Card>
      )}
    </div>
  )
}
