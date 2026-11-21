import { useEffect, useState, type RefObject } from "react"
import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { Wordmark } from "@/components/brand/logo"
import { cn } from "@/lib/utils"
import { ArrowIcon } from "./Reveal"

const LINKS: { href: string; label: string; route?: boolean }[] = [
  { href: "#pipeline", label: "Pipeline" },
  { href: "#suwak", label: "Koszt i jakość" },
  { href: "#uczenie", label: "Uczenie" },
  { href: "#rozszerzalnosc", label: "Rozszerzalność" },
  { href: "#wyniki", label: "Wyniki" },
  { href: "/benchmarks", label: "Benchmarki", route: true },
  { href: "#wyprobuj", label: "Przykłady" },
]

/** Fixed nav: transparent over the dark hero, frosted cream once the hero scrolls away. */
export function LandingNav({ heroRef }: { heroRef: RefObject<HTMLElement | null> }) {
  const [solid, setSolid] = useState(false)
  useEffect(() => {
    const onScroll = () => setSolid(window.scrollY > (heroRef.current?.offsetHeight ?? 600) - 90)
    onScroll()
    window.addEventListener("scroll", onScroll, { passive: true })
    window.addEventListener("resize", onScroll, { passive: true })
    return () => {
      window.removeEventListener("scroll", onScroll)
      window.removeEventListener("resize", onScroll)
    }
  }, [heroRef])

  return (
    <nav className={cn("lp-nav", solid && "solid")} aria-label="Główna nawigacja">
      <Link className="home" to="/" aria-label="Wróbelek, strona główna">
        <Wordmark />
      </Link>
      <div className="links">
        {LINKS.map((l) =>
          l.route ? (
            <Link key={l.href} to={l.href}>{l.label}</Link>
          ) : (
            <a key={l.href} href={l.href}>{l.label}</a>
          ),
        )}
      </div>
      <Button nativeButton={false} render={<Link to="/app" />} className="btn btn-p">
        Wypróbuj <ArrowIcon />
      </Button>
    </nav>
  )
}
