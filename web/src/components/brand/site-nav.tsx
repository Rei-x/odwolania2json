import { Link, NavLink } from "react-router-dom"
import { ArrowRight } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { Wordmark } from "./logo"

const LINKS = [
  { to: "/app", label: "Aplikacja" },
  { to: "/benchmarks", label: "Benchmarki" },
  { to: "/nowy-typ", label: "Nowy typ dokumentu" },
]

/** Compact top bar shared by the app pages (the landing page has its own hero nav). */
export function SiteNav({ className, children }: { className?: string; children?: React.ReactNode }) {
  return (
    <header className={cn("sticky top-0 z-40 border-b bg-background/80 backdrop-blur-md", className)}>
      <div className="mx-auto flex h-14 max-w-[1400px] items-center gap-6 px-4">
        <Link to="/" className="text-lg">
          <Wordmark />
        </Link>
        <nav className="hidden items-center gap-1 md:flex">
          {LINKS.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              className={({ isActive }) =>
                cn(
                  "rounded-full px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground",
                  isActive && "bg-secondary text-foreground",
                )
              }
            >
              {l.label}
            </NavLink>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-2">
          {children ?? (
            <Button render={<Link to="/app" />} size="sm" className="rounded-full">
              Wypróbuj <ArrowRight />
            </Button>
          )}
        </div>
      </div>
    </header>
  )
}
