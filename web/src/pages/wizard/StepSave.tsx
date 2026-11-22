import { CheckCircle2 } from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Label } from "@/components/ui/label"
import type { Wizard } from "./useWizard"
import { doctypeLabel } from "@/lib/labels"

function SumRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[5.5rem_1fr] gap-3 border-b py-2.5 text-sm last:border-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="min-w-0 break-words">{children}</span>
    </div>
  )
}

export function StepSave({ wiz, force, setForce }: { wiz: Wizard; force: boolean; setForce: (v: boolean) => void }) {
  const { s } = wiz
  const v = s.valid
  const sp = v?.spec
  if (s.saved)
    return (
      <Card className="mx-auto max-w-2xl">
        <CardContent className="flex flex-col items-center gap-3 py-8 text-center">
          <span className="grid size-16 place-items-center rounded-full bg-success/15 text-success">
            <CheckCircle2 className="size-9" />
          </span>
          <h2 className="text-xl font-semibold">Typ „{doctypeLabel(s.saved.name)}” jest aktywny</h2>
          <p className="max-w-lg text-sm text-muted-foreground">
            <code className="font-mono text-foreground">{s.saved.file}</code> · działa od razu, bez restartu.
          </p>
        </CardContent>
      </Card>
    )
  const located = s.test ? (s.test.trace.evidence ?? []).filter((e) => e.method === "located").length : 0
  return (
    <Card className="mx-auto max-w-2xl">
      <CardContent className="space-y-4">
        <h2 className="text-lg font-semibold">Gotowe do zapisu</h2>
        <div>
          <SumRow label="Nazwa">
            <b className="font-mono">{s.name}</b>
          </SumRow>
          <SumRow label="Plik">
            <code className="font-mono text-xs">config/doctypes/{s.name}.yaml</code>
          </SumRow>
          <SumRow label="Pola">
            {sp?.fields ?? "—"} pól · {sp?.keywords ?? 0} słów kluczowych
          </SumRow>
          <SumRow label="Test">{s.test ? `${s.test.file} · ${located} z cytatem` : <span className="text-muted-foreground">nie testowano</span>}</SumRow>
          <SumRow label="Status">
            <span className={v?.ok ? "text-success" : "text-destructive"}>{v?.ok ? "poprawny" : "zawiera błędy"}</span>
            <span className="text-muted-foreground">{wiz.nameExists ? " · aktualizacja istniejącego" : " · nowy typ"}</span>
          </SumRow>
        </div>
        {wiz.isBuiltin && (
          <Label className="flex items-start gap-2.5 rounded-lg border border-destructive/30 bg-destructive/5 p-3 font-normal">
            <Checkbox checked={force} onCheckedChange={(c) => setForce(!!c)} className="mt-0.5" />
            <span>Nadpisuję typ wbudowany „{doctypeLabel(s.name)}”</span>
          </Label>
        )}
      </CardContent>
    </Card>
  )
}
