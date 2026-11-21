import { useEffect, useState } from "react"
import { AlertCircle, FileCode2, FileUp, Sparkles, Table2 } from "lucide-react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"
import { ApiError, wizardApi } from "./api"
import { FieldEditor } from "./FieldEditor"
import { StartDrop } from "./StartDrop"
import { TypesList } from "./TypesList"
import { NAME_RE, TEMPLATE_PLACEHOLDER } from "./types"
import type { Mode, Wizard } from "./useWizard"
import { YamlCode } from "./YamlCode"

type Preview = { yaml: string; fields: number | null } | { error: string } | null

/** Live YAML preview: the draft endpoint is pure parsing (no LLM), so it is safe to call on every edit (debounced). */
function useLiveDraft(wiz: Wizard): { preview: Preview; busy: boolean } {
  const { name, title, desc, template, rows, mode } = wiz.s
  const [preview, setPreview] = useState<Preview>(null)
  const [busy, setBusy] = useState(false)
  const hasContent = mode === "template" ? !!template.trim() : rows.some((r) => r.name.trim())
  const ready = NAME_RE.test(name) && hasContent
  useEffect(() => {
    if (!ready) return
    const ctl = new AbortController()
    const t = setTimeout(() => {
      setBusy(true)
      wizardApi
        .draft(
          mode === "template" ? { name, title, description: desc, template } : { name, title, description: desc, fields: rows },
          ctl.signal,
        )
        .then((r) => setPreview({ yaml: r.yaml, fields: r.validation.spec?.fields ?? null }))
        .catch((e: unknown) => {
          if ((e as Error).name === "AbortError") return
          const err = e as ApiError
          setPreview({ error: err.line ? `${err.message} (linia ${err.line})` : err.message })
        })
        .finally(() => setBusy(false))
    }, 600)
    return () => {
      clearTimeout(t)
      ctl.abort()
    }
  }, [ready, name, title, desc, template, rows, mode])
  return { preview: ready ? preview : null, busy }
}

export function StepDefine({ wiz }: { wiz: Wizard }) {
  const { s, set } = wiz
  const { preview, busy } = useLiveDraft(wiz)
  if (!s.manual) return <StartDrop wiz={wiz} />
  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(320px,420px)]">
      <Card>
        <CardContent className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-[minmax(0,14rem)_1fr]">
            <div className="space-y-1.5">
              <Label htmlFor="wz-name">Nazwa techniczna</Label>
              <Input
                id="wz-name"
                value={s.name}
                placeholder="np. faktura"
                autoComplete="off"
                spellCheck={false}
                aria-invalid={!!wiz.nameIssue || undefined}
                onChange={(e) => set({ name: e.target.value, draftErr: null })}
                className="font-mono"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="wz-title" className="flex-wrap gap-x-1.5 gap-y-0">
                Nazwa dokumentu
              </Label>
              <Input
                id="wz-title"
                value={s.title}
                placeholder="np. Przystąpienie do postępowania odwoławczego"
                onChange={(e) => set({ title: e.target.value })}
              />
            </div>
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="wz-desc" className="flex-wrap gap-x-1.5 gap-y-0">
                Opis <span className="font-normal text-muted-foreground">· czym jest, a czym nie jest</span>
              </Label>
              <Textarea
                id="wz-desc"
                rows={2}
                value={s.desc}
                placeholder="np. Pismo wykonawcy zgłaszające przystąpienie do postępowania odwoławczego…"
                onChange={(e) => set({ desc: e.target.value })}
                className="min-h-0 resize-y"
              />
            </div>
            {(wiz.nameIssue || wiz.nameExists) && (
              <p className={cn("-mt-2 text-xs sm:col-span-2", wiz.nameIssue ? "text-destructive" : "text-muted-foreground")}>
                {wiz.nameIssue ?? `„${s.name}” już istnieje — zapis go zaktualizuje.`}
              </p>
            )}
          </div>

          <Tabs value={s.mode} onValueChange={(v) => set({ mode: v as Mode, draftErr: null })}>
            <div className="flex flex-wrap items-center gap-2">
              <TabsList>
                <TabsTrigger value="template">
                  <FileCode2 /> Szablon JSON
                </TabsTrigger>
                <TabsTrigger value="table">
                  <Table2 /> Tabela pól
                </TabsTrigger>
              </TabsList>
              <div className="ml-auto flex items-center gap-3">
                {s.mode === "template" && (
                  <Button variant="link" size="sm" className="px-0" onClick={wiz.insertSample}>
                    <Sparkles /> Wstaw przykład
                  </Button>
                )}
                <Button variant="link" size="sm" className="px-0 text-muted-foreground" onClick={() => set({ manual: false })}>
                  <FileUp /> Upuść dokument
                </Button>
              </div>
            </div>
            <TabsContent value="template" className="pt-2">
              <Textarea
                aria-label="Szablon JSON"
                value={s.template}
                spellCheck={false}
                placeholder={TEMPLATE_PLACEHOLDER}
                onChange={(e) => set({ template: e.target.value })}
                onKeyDown={(e) => {
                  if (e.key === "Tab") {
                    e.preventDefault()
                    document.execCommand("insertText", false, "  ")
                  }
                }}
                className="min-h-80 bg-card font-mono text-[12.5px] leading-5 [tab-size:2] whitespace-pre"
              />
            </TabsContent>
            <TabsContent value="table" className="pt-2">
              <FieldEditor wiz={wiz} />
            </TabsContent>
          </Tabs>

          {s.draftErr && (
            <Alert variant="destructive">
              <AlertCircle />
              <AlertDescription>{s.draftErr}</AlertDescription>
            </Alert>
          )}
        </CardContent>
      </Card>

      <div className="flex min-w-0 flex-col gap-5 lg:sticky lg:top-20 lg:self-start">
        <Card size="sm" className="gap-2">
          <CardHeader className="flex items-center gap-2">
            <CardTitle className="text-sm">YAML</CardTitle>
            <span className="ml-auto text-xs text-muted-foreground">
              {busy ? "aktualizuję…" : preview && "yaml" in preview && preview.fields != null ? `${preview.fields} pól` : ""}
            </span>
          </CardHeader>
          <CardContent>
            {preview && "yaml" in preview ? (
              <YamlCode value={preview.yaml} className="h-72 lg:h-96" />
            ) : (
              <div className="grid h-40 place-items-center rounded-xl border border-dashed px-6 text-center text-xs text-muted-foreground">
                {preview && "error" in preview ? (
                  <span className="text-destructive">{preview.error}</span>
                ) : (
                  "Podaj nazwę i pola — YAML pojawi się tutaj."
                )}
              </div>
            )}
          </CardContent>
        </Card>
        <Card size="sm" className="gap-2">
          <CardHeader>
            <CardTitle className="text-sm">Istniejące typy</CardTitle>
          </CardHeader>
          <CardContent>
            <TypesList types={wiz.types} onOpen={wiz.openExisting} />
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
