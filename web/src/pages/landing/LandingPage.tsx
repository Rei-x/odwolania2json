import { useEffect, useRef } from "react"
import "./landing.css"
import { LandingNav } from "./LandingNav"
import { Hero } from "./Hero"
import { Kpis } from "./Kpis"
import { Pipeline } from "./Pipeline"
import { TierSlider } from "./TierSlider"
import { Learning } from "./Learning"
import { Extensibility } from "./Extensibility"
import { Results } from "./Results"
import { ForUzp } from "./ForUzp"
import { Samples } from "./Samples"
import { FinalCta } from "./FinalCta"
import { prefersReducedMotion } from "./hooks"

export default function LandingPage() {
  const heroRef = useRef<HTMLElement>(null)

  useEffect(() => {
    document.title = "Wróbelek · akta KIO → JSON"
    // in-page anchors glide like the legacy page did
    const html = document.documentElement
    const prev = html.style.scrollBehavior
    if (!prefersReducedMotion()) html.style.scrollBehavior = "smooth"
    return () => { html.style.scrollBehavior = prev }
  }, [])

  return (
    <div className="lp">
      <LandingNav heroRef={heroRef} />
      <main>
        <Hero ref={heroRef} />
        <Kpis />
        <Pipeline />
        <TierSlider />
        <Learning />
        <Extensibility />
        <Results />
        <ForUzp />
        <Samples />
        <FinalCta />
      </main>
    </div>
  )
}
