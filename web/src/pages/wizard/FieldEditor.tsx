import { Braces, CornerDownRight, List, Plus, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"
import { NORM_LABEL, TYPE_OPTS, type FieldRow, type FieldType } from "./types"
import type { RowPath, Wizard } from "./useWizard"

const TYPE_ITEMS = Object.fromEntries(TYPE_OPTS)

function MiniSelect({
  value,
  items,
  onChange,
  disabled,
  label,
  className,
}: {
  value: string
  items: Record<string, string>
  onChange: (v: string) => void
  disabled?: boolean
  label: string
  className?: string
}) {
  return (
    <Select value={value} items={items} onValueChange={(v) => v != null && onChange(String(v))} disabled={disabled}>
      <SelectTrigger aria-label={label} className={cn("w-full bg-card", className)}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {Object.entries(items).map(([v, l]) => (
          <SelectItem key={v} value={v}>
            {l}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

function IconAction({ label, onClick, children, danger }: { label: string; onClick: () => void; children: React.ReactNode; danger?: boolean }) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={label}
            onClick={onClick}
            className={cn("text-muted-foreground", danger && "hover:bg-destructive/10 hover:text-destructive")}
          />
        }
      >
        {children}
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  )
}

function RowEditor({ row, path, wiz, normItems }: { row: FieldRow; path: RowPath; wiz: Wizard; normItems: Record<string, string> }) {
  const nested = row.type === "object" || row.type === "array"
  const noNorm = nested || row.type === "enum" || row.type === "array_string"
  const upd = (patch: Partial<FieldRow>) => wiz.rows.update(path, patch)
  return (
    <div className={cn(path.length > 1 && "border-l-2 border-primary/20 pl-3 sm:pl-4")}>
      <div
        className={cn(
          "group/row grid grid-cols-[1fr_1fr_auto] gap-2 rounded-xl border bg-background/60 p-2 transition-colors focus-within:border-primary/40 focus-within:bg-card",
          "md:grid-cols-[minmax(0,1.1fr)_9.5rem_10.5rem_minmax(0,1.6fr)_auto] md:items-center",
          nested && "bg-secondary/50",
        )}
      >
        <div className="col-span-2 row-start-1 flex items-center gap-1.5 md:col-span-1 md:row-start-auto">
          {path.length > 1 && <CornerDownRight className="size-3.5 shrink-0 text-muted-foreground" />}
          {nested && (row.type === "array" ? <List className="size-3.5 shrink-0 text-primary" /> : <Braces className="size-3.5 shrink-0 text-primary" />)}
          <Input
            aria-label="Nazwa pola"
            value={row.name}
            placeholder="nazwa_pola"
            spellCheck={false}
            onChange={(e) => upd({ name: e.target.value })}
            className="bg-card font-mono text-[13px]"
          />
        </div>
        <MiniSelect label="Typ pola" value={row.type} items={TYPE_ITEMS} onChange={(v) => upd({ type: v as FieldType })} className="max-md:row-start-2" />
        <MiniSelect
          label="Normalizacja"
          value={row.normalize || "auto"}
          items={normItems}
          disabled={noNorm}
          onChange={(v) => upd({ normalize: v })}
          className="max-md:col-span-2 max-md:row-start-2"
        />
        <Input
          aria-label="Opis pola"
          value={row.description}
          placeholder={nested ? "opis grupy (opcjonalnie)" : "opis dla modelu — co wpisać, skąd wziąć"}
          onChange={(e) => upd({ description: e.target.value })}
          className="col-span-3 bg-card md:col-span-1"
        />
        <div className="col-start-3 row-start-1 flex justify-end gap-0.5 md:col-start-auto md:row-start-auto">
          {nested && (
            <IconAction label="Dodaj pole podrzędne" onClick={() => wiz.rows.addChild(path)}>
              <Plus />
            </IconAction>
          )}
          <IconAction label="Usuń pole" onClick={() => wiz.rows.remove(path)} danger>
            <Trash2 />
          </IconAction>
        </div>
        {row.type === "enum" && (
          <Input
            aria-label="Wartości enum"
            value={row.values ?? ""}
            placeholder="wartości: 1=tak, 0=nie  lub  osoba_prawna, osoba_fizyczna"
            onChange={(e) => upd({ values: e.target.value })}
            className="col-span-3 bg-card font-mono text-[13px] md:col-span-5"
          />
        )}
      </div>
      {nested && (
        <div className="mt-2 space-y-2">
          {(row.children ?? []).map((c, i) => (
            <RowEditor key={i} row={c} path={[...path, i]} wiz={wiz} normItems={normItems} />
          ))}
        </div>
      )}
    </div>
  )
}

/** Form-builder style editor for the field table (POST /api/doctypes/draft `fields`). */
export function FieldEditor({ wiz }: { wiz: Wizard }) {
  const norms = ["auto", "none", ...(wiz.meta?.normalizers ?? Object.keys(NORM_LABEL).filter((k) => k !== "auto" && k !== "none"))]
  const normItems = Object.fromEntries(norms.map((n) => [n, NORM_LABEL[n] ?? n]))
  const rows = wiz.s.rows
  return (
    <div className="space-y-2">
      <div className="hidden grid-cols-[minmax(0,1.1fr)_9.5rem_10.5rem_minmax(0,1.6fr)_4rem] gap-2 px-2 text-xs font-medium text-muted-foreground md:grid">
        <span>Pole</span>
        <span>Typ</span>
        <span>Normalizacja</span>
        <span>Opis</span>
        <span />
      </div>
      {rows.length ? (
        rows.map((r, i) => <RowEditor key={i} row={r} path={[i]} wiz={wiz} normItems={normItems} />)
      ) : (
        <div className="rounded-xl border border-dashed p-6 text-center text-sm text-muted-foreground">Brak pól</div>
      )}
      <div className="flex flex-wrap gap-2 pt-1">
        <Button variant="outline" size="sm" onClick={() => wiz.rows.add("field")}>
          <Plus /> pole
        </Button>
        <Button variant="outline" size="sm" onClick={() => wiz.rows.add("object")}>
          <Braces /> grupa (obiekt)
        </Button>
        <Button variant="outline" size="sm" onClick={() => wiz.rows.add("array")}>
          <List /> lista obiektów
        </Button>
      </div>
    </div>
  )
}
