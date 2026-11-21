import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { Wordmark } from "@/components/brand/logo"
import { ArrowIcon, Reveal } from "./Reveal"

export function FinalCta() {
  return (
    <section className="final">
      <Reveal as="h2">Wrzuć własne akta.</Reveal>
      <Reveal as="p" delay={1}>Upuść PDF-y i zobacz, skąd pochodzi każde pole.</Reveal>
      <Reveal className="ctas" delay={2}>
        <Button nativeButton={false} render={<Link to="/app" />} className="btn btn-p">
          Wypróbuj <ArrowIcon />
        </Button>
      </Reveal>
      <footer className="foot">
        <Wordmark className="wm" />
        <span>open-source · CPU · hosting w UE</span>
      </footer>
    </section>
  )
}
