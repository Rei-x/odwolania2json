import type { ReactNode } from "react"
import { cn } from "@/lib/utils"

function render(x: unknown, ind: number): ReactNode {
  const pad = "  ".repeat(ind)
  if (x === null || x === undefined) return <span className="text-muted-foreground">null</span>
  if (typeof x === "string") return <span className="text-sage">{JSON.stringify(x)}</span>
  if (typeof x === "number" || typeof x === "boolean") return <span className="text-chart-3">{String(x)}</span>
  if (Array.isArray(x)) {
    if (!x.length) return "[]"
    return (
      <>
        {"[\n"}
        {x.map((v, i) => (
          <span key={i}>
            {pad + "  "}
            {render(v, ind + 1)}
            {i < x.length - 1 ? ",\n" : "\n"}
          </span>
        ))}
        {pad + "]"}
      </>
    )
  }
  const entries = Object.entries(x as Record<string, unknown>)
  if (!entries.length) return "{}"
  return (
    <>
      {"{\n"}
      {entries.map(([k, v], i) => (
        <span key={k}>
          {pad + "  "}
          <span className="text-primary">{JSON.stringify(k)}</span>
          {": "}
          {render(v, ind + 1)}
          {i < entries.length - 1 ? ",\n" : "\n"}
        </span>
      ))}
      {pad + "}"}
    </>
  )
}

/** Pretty JSON with token colours. */
export function JsonView({ value, className }: { value: unknown; className?: string }) {
  return (
    <pre className={cn("overflow-auto font-mono text-xs leading-5 whitespace-pre text-foreground/80", className)}>{render(value, 0)}</pre>
  )
}
