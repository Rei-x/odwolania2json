import type { ReactNode } from "react"
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Reveal, SectionHead } from "./Reveal"

const ic = (d: ReactNode) => (
  <span className="ic">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{d}</svg>
  </span>
)

const ITEMS: { tone: string; icon: ReactNode; title: string; text: string }[] = [
  { tone: "", icon: ic(<><rect x="3" y="4" width="7" height="9" rx="1.5" /><rect x="14" y="4" width="7" height="9" rx="1.5" /><path d="M6.5 13v3h11v-3M12 16v4" /></>),
    title: "Widok całej sprawy", text: "Trzy dokumenty, jedna lista kontroli spójności." },
  { tone: "teal", icon: ic(<><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5M8 11h6" /></>),
    title: "Audyt każdego pola", text: "Strona, cytat i podświetlenie w PDF." },
  { tone: "amber", icon: ic(<><path d="M12 3 5 6v5c0 4.5 3 8 7 10 4-2 7-5.5 7-10V6z" /><path d="m9 12 2 2 4-4" /></>),
    title: "Zgodność i offline", text: "Modele open-weight w UE. Tryb Reguły działa offline na CPU." },
]

export function ForUzp() {
  return (
    <section className="sec" id="dla-uzp">
      <div className="wrap">
        <SectionHead eyebrow="Dla UZP" title="Co dostaje Urząd." />
        <div className="uzp">
          {ITEMS.map((it, i) => (
            <Reveal key={it.title} delay={i as 0 | 1 | 2}>
              <Card className={`lp-card uz h-full ${it.tone}`}>
                <CardHeader>
                  {it.icon}
                  <CardTitle className="mt-3 text-lg font-semibold tracking-tight">{it.title}</CardTitle>
                  <CardDescription className="text-[15px]">{it.text}</CardDescription>
                </CardHeader>
              </Card>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  )
}
