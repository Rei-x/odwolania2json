import { useMemo, useRef, useState } from "react"
import { TriangleAlert, CheckCircle2, Copy, Loader2, Lock, PencilLine, Trash2, XCircle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { cn } from "@/lib/utils"
import { doctypeLabel } from "@/lib/labels"
import { JsonView } from "./JsonView"
import { InferProgress } from "./StartDrop"
import type { Wizard } from "./useWizard"
import { YamlCode, type YamlCodeHandle } from "./YamlCode"

const plErr = (n: number) => (n === 1 ? "błąd" : n < 5 ? "błędy" : "błędów")

function Banner({ tone, icon, children, action }: { tone: "muted" | "accent"; icon: React.ReactNode; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl border px-3 py-2 text-sm",
        tone === "muted" ? "bg-secondary/70" : "border-primary/25 bg-accent text-accent-foreground",
      )}
    >
      <span className="shrink-0 [&_svg]:size-4">{icon}</span>
      <span className="min-w-[min(100%,16rem)] flex-1">{children}</span>
      {action}
    </div>
  )
}

export function StepYaml({ wiz }: { wiz: Wizard }) {
  const { s } = wiz
  const ed = useRef<YamlCodeHandle>(null)
  const [confirmDel, setConfirmDel] = useState(false)
  const v = s.valid
  const errLines = useMemo(() => new Set((v?.errors ?? []).map((e) => e.line).filter((l): l is number => !!l)), [v])
  const warnLines = useMemo(() => new Set((v?.warnings ?? []).map((e) => e.line).filter((l): l is number => !!l)), [v])
  const items = [
    ...(v?.errors ?? []).map((e) => ({ ...e, k: "e" as const })),
    ...(v?.warnings ?? []).filter((w) => !(s.readonly && w.path === "name")).map((e) => ({ ...e, k: "w" as const })),
  ].slice(0, 30)
  const sp = v?.spec
  const waiting = s.validating || !v

  return (
    <div className="grid gap-5 lg:h-[calc(100svh-15rem)] lg:min-h-[520px] lg:grid-cols-[minmax(0,1fr)_minmax(300px,400px)]">
      <div className="flex min-h-0 flex-col gap-3">
        {(s.testing || s.inferWarnings.length > 0) && (
          <div className="space-y-2 rounded-xl border bg-card px-3 py-2.5">
            {s.testing && <InferProgress phase="test" />}
            {s.inferWarnings.map((w, i) => (
              <p key={i} className="flex gap-2 text-xs text-muted-foreground">
                <TriangleAlert className="mt-px size-3.5 shrink-0 text-chart-3" /> {w}
              </p>
            ))}
          </div>
        )}
        {s.readonly ? (
          <Banner
            tone="muted"
            icon={<Lock />}
            action={
              <Button size="sm" variant="outline" onClick={wiz.duplicate}>
                <Copy /> Duplikuj
              </Button>
            }
          >
            <b>„{doctypeLabel(s.name)}”</b> — typ wbudowany, tylko do odczytu
          </Banner>
        ) : s.editing ? (
          <Banner
            tone="accent"
            icon={<PencilLine />}
            action={
              <Button size="sm" variant="destructive" onClick={() => setConfirmDel(true)}>
                <Trash2 /> Usuń
              </Button>
            }
          >
            Edytujesz <b>„{doctypeLabel(s.editing)}”</b>
          </Banner>
        ) : null}
        <YamlCode
          ref={ed}
          value={s.yaml}
          onChange={s.readonly ? undefined : wiz.setYaml}
          readOnly={s.readonly}
          errorLines={errLines}
          warnLines={warnLines}
          className="h-[60vh] flex-1 lg:h-auto"
        />
      </div>

      <div className="flex min-h-0 flex-col gap-4 lg:overflow-y-auto">
        <Card size="sm" className="shrink-0 gap-3">
          <CardContent className="space-y-3">
            <div className="flex items-center gap-3" aria-live="polite">
              <span
                className={cn(
                  "grid size-9 shrink-0 place-items-center rounded-full text-white",
                  waiting ? "bg-muted-foreground/60" : v.ok ? "bg-success" : "bg-destructive",
                )}
              >
                {waiting ? <Loader2 className="size-4 animate-spin" /> : v.ok ? <CheckCircle2 className="size-5" /> : <XCircle className="size-5" />}
              </span>
              <div className="min-w-0">
                <div className="font-medium">
                  {waiting ? "Sprawdzam…" : v.ok ? "YAML poprawny" : `${v.errors.length} ${plErr(v.errors.length)}`}
                </div>
              </div>
            </div>
            {items.length > 0 && (
              <ul className="space-y-1">
                {items.map((e, i) => (
                  <li key={i}>
                    <button
                      type="button"
                      onClick={() => e.line && ed.current?.jump(e.line)}
                      className={cn(
                        "flex w-full gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors",
                        e.k === "e" ? "bg-destructive/8 text-destructive hover:bg-destructive/15" : "bg-wheat/15 hover:bg-wheat/25",
                      )}
                    >
                      <span className="w-8 shrink-0 font-mono opacity-70">{e.line ? `L${e.line}` : "—"}</span>
                      <span>{e.msg}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {sp && (
              <div className="grid grid-cols-3 gap-2 text-center">
                {[
                  [sp.fields, "pól"],
                  [sp.keywords, "słów kluczowych"],
                  [Object.keys(sp.skeleton).length, "sekcji"],
                ].map(([n, l]) => (
                  <div key={l} className="rounded-lg bg-secondary/70 px-2 py-2">
                    <div className="text-lg font-semibold tabular-nums">{n}</div>
                    <div className="text-[11px] text-muted-foreground">{l}</div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
        <Card size="sm" className="shrink-0 gap-2">
          <CardHeader>
            <CardTitle className="text-sm">Wynik (szkielet JSON)</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {sp ? (
              <JsonView value={sp.preview || sp.skeleton} className="max-h-80 rounded-lg bg-secondary/50 p-3" />
            ) : (
              <p className="rounded-lg border border-dashed p-4 text-center text-xs text-muted-foreground">Popraw błędy, aby zobaczyć wynik.</p>
            )}
          </CardContent>
        </Card>
      </div>

      <Dialog open={confirmDel} onOpenChange={setConfirmDel}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Usunąć typ „{doctypeLabel(s.editing)}”?</DialogTitle>
            <DialogDescription>
              Plik <code className="font-mono">config/doctypes/{s.editing}.yaml</code> zostanie skasowany.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose render={<Button variant="outline" />}>Anuluj</DialogClose>
            <Button
              variant="destructive"
              onClick={() => {
                setConfirmDel(false)
                wiz.deleteEditing()
              }}
            >
              <Trash2 /> Usuń
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
