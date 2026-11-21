import { useEffect, useRef, useState } from "react"

export const prefersReducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches

/** True once the element has entered the viewport (then stops observing). */
export function useInViewOnce<T extends Element>(options: IntersectionObserverInit = {}) {
  const ref = useRef<T>(null)
  const [seen, setSeen] = useState(false)
  const { threshold, rootMargin } = options
  useEffect(() => {
    const el = ref.current
    if (!el || seen) return
    const io = new IntersectionObserver(
      (es) => {
        if (es.some((e) => e.isIntersecting)) {
          setSeen(true)
          io.disconnect()
        }
      },
      { threshold, rootMargin },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [seen, threshold, rootMargin])
  return [ref, seen] as const
}
