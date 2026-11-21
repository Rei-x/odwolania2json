import { useImperativeHandle, useMemo, useRef, type Ref } from "react"
import { cn } from "@/lib/utils"

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;")

const C = {
  key: "text-rust",
  punct: "text-muted-foreground",
  str: "text-[color-mix(in_oklch,var(--sage),white_45%)]",
  num: "text-wheat",
  bool: "text-[color-mix(in_oklch,var(--chart-5),white_35%)]",
  comment: "text-muted-foreground italic",
}

/** Minimal YAML syntax highlighter (ported from the legacy wizard); returns escaped HTML. */
export function highlightYaml(src: string, bad: Set<number> = new Set()): string {
  return (
    src
      .split("\n")
      .map((ln, i) => {
        let q: string | null = null
        let cut = -1 // YAML comment: '#' at line start or after whitespace, outside quotes
        for (let k = 0; k < ln.length; k++) {
          const c = ln[k]
          if (q) {
            if (c === q) q = null
            continue
          }
          if ((c === "'" || c === '"') && (k === 0 || /[\s:{[,]/.test(ln[k - 1]))) q = c
          else if (c === "#" && (k === 0 || /\s/.test(ln[k - 1]))) {
            cut = k
            break
          }
        }
        let h = esc(cut >= 0 ? ln.slice(0, cut) : ln)
        const comment = cut >= 0 ? esc(ln.slice(cut)) : ""
        h = h
          .replace(
            /^(\s*-?\s*)([\w\-\\.()|?*+[\]{}ĄĆĘŁŃÓŚŹŻąćęłńóśźż' ]+?)(:)(?=\s|$)/,
            (_m, a, k, c) => `${a}<span class="${C.key}">${k}</span><span class="${C.punct}">${c}</span>`,
          )
          .replace(/(\{|, )([a-z_]+)(:)/g, `$1<span class="${C.key}">$2</span>$3`)
          .replace(/'[^']*'|&quot;.*?&quot;/g, `<span class="${C.str}">$&</span>`)
          .replace(/(:<\/span>\s|:\s|\[|, )(-?\d+(?:\.\d+)?)(?=[,\]}\s]|$)/g, `$1<span class="${C.num}">$2</span>`)
          .replace(/\b(true|false|null)\b/g, `<span class="${C.bool}">$1</span>`)
        if (comment) h += `<span class="${C.comment}">${comment}</span>`
        return bad.has(i + 1) ? `<span class="inline-block w-full bg-primary/25">${h || " "}</span>` : h
      })
      .join("\n") + "\n"
  )
}

export interface YamlCodeHandle {
  jump: (line: number) => void
}

const EMPTY = new Set<number>()
const LINE = 20 // px, keep in sync with leading-[20px]

/**
 * Mono code panel: line gutter, highlighted <pre>, and (when editable) a transparent textarea on top.
 */
export function YamlCode({
  value,
  onChange,
  readOnly,
  errorLines,
  warnLines,
  className,
  ref,
  label,
}: {
  value: string
  onChange?: (v: string) => void
  readOnly?: boolean
  errorLines?: Set<number>
  warnLines?: Set<number>
  className?: string
  ref?: Ref<YamlCodeHandle>
  label?: string
}) {
  const ta = useRef<HTMLTextAreaElement>(null)
  const pre = useRef<HTMLPreElement>(null)
  const gut = useRef<HTMLDivElement>(null)
  const bad = errorLines ?? EMPTY
  const warn = warnLines ?? EMPTY
  const html = useMemo(() => highlightYaml(value, bad), [value, bad])
  const n = value.split("\n").length
  const editable = !!onChange && !readOnly

  useImperativeHandle(ref, () => ({
    jump(line) {
      const el = ta.current
      if (!el || !line) return
      const lines = el.value.split("\n")
      const a = lines.slice(0, line - 1).join("\n").length + (line > 1 ? 1 : 0)
      el.focus()
      el.setSelectionRange(a, a + (lines[line - 1]?.length ?? 0))
      el.scrollTop = Math.max(0, (line - 6) * LINE)
    },
  }))

  const sync = (src: HTMLElement) => {
    if (pre.current && src !== pre.current) {
      pre.current.scrollTop = src.scrollTop
      pre.current.scrollLeft = src.scrollLeft
    }
    if (gut.current) gut.current.scrollTop = src.scrollTop
  }

  return (
    <div
      className={cn(
        "relative grid min-h-0 grid-cols-[44px_1fr] overflow-hidden rounded-xl bg-bark font-mono text-[12.5px] leading-[20px] text-[color-mix(in_oklch,var(--wheat),white_75%)] shadow-sm ring-1 ring-foreground/10 dark:bg-black/40",
        className,
      )}
    >
      <div ref={gut} aria-hidden className="overflow-hidden bg-black/20 py-3.5 text-right text-muted-foreground/70 select-none">
        {Array.from({ length: n }, (_, i) => (
          <div
            key={i}
            className={cn(
              "relative pr-2.5",
              bad.has(i + 1) && "text-rust before:absolute before:top-[7px] before:left-1.5 before:size-1.5 before:rounded-full before:bg-primary",
              !bad.has(i + 1) && warn.has(i + 1) && "text-wheat",
            )}
          >
            {i + 1}
          </div>
        ))}
        <div>&nbsp;</div>
      </div>
      <div className="relative min-h-0 min-w-0">
        <pre
          ref={pre}
          onScroll={editable ? undefined : (e) => sync(e.currentTarget)}
          className={cn(
            "absolute inset-0 m-0 overflow-auto px-4 py-3.5 [tab-size:2] whitespace-pre",
            editable && "pointer-events-none",
          )}
          dangerouslySetInnerHTML={{ __html: html }}
        />
        {editable && (
          <textarea
            ref={ta}
            aria-label={label ?? "Edytor YAML"}
            value={value}
            spellCheck={false}
            onChange={(e) => onChange(e.target.value)}
            onScroll={(e) => sync(e.currentTarget)}
            onKeyDown={(e) => {
              if (e.key === "Tab") {
                e.preventDefault()
                document.execCommand("insertText", false, "  ")
              }
            }}
            className="absolute inset-0 m-0 resize-none overflow-auto border-0 bg-transparent px-4 py-3.5 font-mono text-[12.5px] leading-[20px] text-transparent caret-white outline-none [tab-size:2] whitespace-pre selection:bg-white/20 selection:text-transparent"
          />
        )}
      </div>
    </div>
  )
}
