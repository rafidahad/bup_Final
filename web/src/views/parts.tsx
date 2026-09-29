import type { ReactNode } from "react"
import { Skeleton } from "@/components/ui/skeleton"
import type { Fuel } from "@/lib/api"
import { cn } from "@/lib/utils"

export function Panel({ title, children, className }: { title?: string; children: ReactNode; className?: string }) {
  return (
    <section className={cn("rounded-lg border bg-card", className)}>
      {title && <h2 className="border-b px-5 py-3 text-lg font-semibold">{title}</h2>}
      {children}
    </section>
  )
}

export function FuelDot({ fuel }: { fuel: Fuel }) {
  return <span className="inline-block size-3 rounded-full align-[-1px]" style={{ background: `var(--${fuel.toLowerCase()})` }} aria-hidden />
}

export function Loading({ error }: { error: string | null }) {
  const waiting = !error || error.startsWith("Waiting")
  return (
    <div className="space-y-3" aria-busy="true">
      <p className="text-base text-muted-foreground">
        {waiting ? "Connecting to the fuel simulator…" : `The app cannot reach its server (${error}). Trying again every second.`}
      </p>
      <Skeleton className="h-20 w-full" /><Skeleton className="h-56 w-full" />
    </div>
  )
}
