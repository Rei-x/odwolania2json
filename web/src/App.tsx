import { lazy, Suspense } from "react"
import { BrowserRouter, Route, Routes } from "react-router-dom"
import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"

const Landing = lazy(() => import("@/pages/landing/LandingPage"))
const Workbench = lazy(() => import("@/pages/app/AppPage"))
const Benchmarks = lazy(() => import("@/pages/benchmarks/BenchmarksPage"))
const Wizard = lazy(() => import("@/pages/wizard/WizardPage"))

export default function App() {
  return (
    <TooltipProvider>
      <BrowserRouter>
        <Suspense fallback={<div className="min-h-svh bg-background" />}>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/app" element={<Workbench />} />
            <Route path="/benchmarks" element={<Benchmarks />} />
            <Route path="/nowy-typ" element={<Wizard />} />
            <Route path="*" element={<Landing />} />
          </Routes>
        </Suspense>
      </BrowserRouter>
      <Toaster richColors position="bottom-right" />
    </TooltipProvider>
  )
}
