import { SiteNav } from "@/components/brand/site-nav"
import { DoctypeWizard } from "./DoctypeWizard"

export { DoctypeWizard }

export default function WizardPage() {
  return (
    <div className="flex min-h-svh flex-col bg-background text-foreground">
      <SiteNav />
      <DoctypeWizard />
    </div>
  )
}
