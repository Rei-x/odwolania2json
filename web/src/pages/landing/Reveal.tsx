import type { ElementType, HTMLAttributes, ReactNode } from "react"
import { cn } from "@/lib/utils"
import { useInViewOnce } from "./hooks"

type Props = HTMLAttributes<HTMLElement> & { as?: ElementType; delay?: 0 | 1 | 2 | 3; children?: ReactNode }

/** Fades/slides its content in the first time it scrolls into view (.rv/.in in landing.css). */
export function Reveal({ as: Tag = "div", delay = 0, className, ...rest }: Props) {
  const [ref, seen] = useInViewOnce<HTMLElement>({ rootMargin: "0px 0px -8% 0px" })
  return <Tag ref={ref} className={cn("rv", delay && `d${delay}`, seen && "in", className)} {...rest} />
}

export function SectionHead({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <Reveal className="shead">
      <h2>{title}</h2>
      {children}
    </Reveal>
  )
}

export const ArrowIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M5 12h14M13 6l6 6-6 6" />
  </svg>
)

export const CheckIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="m5 12 4.5 4.5L19 7" />
  </svg>
)
