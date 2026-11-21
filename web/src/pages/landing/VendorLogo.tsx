import type { ReactNode } from "react"
import { ModelLogo } from "@/components/brand/model-logo"
import { cn } from "@/lib/utils"

/* Thin landing wrapper over the shared model-logo mapping. */
const VENDOR_IDS = { mistral: "mistralai/ministral", anthropic: "anthropic/claude" } as const
export type Vendor = keyof typeof VENDOR_IDS

/** Model name with its vendor mark in front; the mark scales with the text. */
export function ModelName({ vendor, children, className }: { vendor: Vendor; children: ReactNode; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 whitespace-nowrap", className)}>
      <ModelLogo id={VENDOR_IDS[vendor]} className="size-[1em]!" />
      {children}
    </span>
  )
}
