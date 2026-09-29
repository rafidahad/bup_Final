import { CircleAlert, CircleCheck, CircleX, TriangleAlert } from "lucide-react"
import { type Fuel, type FuelLevel, fmtL, fuelName } from "@/lib/api"
import { cn } from "@/lib/utils"

const FUEL_VAR: Record<Fuel, string> = { DIESEL: "var(--diesel)", PETROL: "var(--petrol)", OCTANE: "var(--octane)" }

export function FuelSwatch({ fuel }: { fuel: Fuel }) {
  return <span className="inline-block size-2.5 rounded-[2px] align-middle" style={{ background: FUEL_VAR[fuel] }} aria-hidden />
}

/** One tank: stock fill, incoming (hatched), and a line at 12 hours of expected demand. */
export function TankGauge({ level }: { level: FuelLevel }) {
  const { fuel, inventory, capacity, incoming = 0, demand_per_day = 0 } = level
  const pct = (v: number) => Math.max(0, Math.min(100, (v / capacity) * 100))
  const fill = pct(inventory)
  const inc = Math.min(pct(incoming), 100 - fill)
  const need12 = pct(demand_per_day / 2)
  const cover = demand_per_day > 0 ? (inventory / demand_per_day) * 24 : null
  const low = inventory < demand_per_day / 2
  return (
    <figure className="flex flex-col items-center gap-1.5" aria-label={`${fuelName(fuel)}: ${fmtL(inventory)} of ${fmtL(capacity)}`}>
      <div className="relative h-32 w-11 overflow-hidden rounded-[3px] border border-ink/25 bg-white">
        <div className="absolute inset-x-0 bottom-0 transition-[height] duration-700" style={{ height: `${fill}%`, background: FUEL_VAR[fuel] }} />
        {inc > 0 && (
          <div className="absolute inset-x-0" style={{
            bottom: `${fill}%`, height: `${inc}%`,
            background: `repeating-linear-gradient(135deg, ${FUEL_VAR[fuel]} 0 3px, transparent 3px 7px)`, opacity: 0.55,
          }} title={`${fmtL(incoming)} on the way`} />
        )}
        {need12 > 0 && need12 < 100 && (
          <div className="absolute inset-x-0 border-t border-dashed border-ink/70" style={{ bottom: `${need12}%` }} title="12 hours of expected demand" />
        )}
      </div>
      <figcaption className="text-center leading-tight">
        <div className="flex items-center justify-center gap-1 text-xs font-medium"><FuelSwatch fuel={fuel} />{fuelName(fuel)}</div>
        <div className="text-[13px] font-semibold">{Math.round(inventory).toLocaleString("en-US")}</div>
        <div className={cn("text-[11px]", low ? "font-semibold text-alarm" : "text-muted-foreground")}>
          {cover == null ? "no demand" : cover < 1 ? `${Math.round(cover * 60)} min left` : `${cover.toFixed(1)} h left`}
        </div>
      </figcaption>
    </figure>
  )
}

export type Health = "healthy" | "degraded" | "down" | string

export function StatusText({ status, children }: { status: Health; children?: React.ReactNode }) {
  const Icon = status === "healthy" ? CircleCheck : status === "degraded" ? TriangleAlert : status === "down" ? CircleX : CircleAlert
  const color = status === "healthy" ? "text-ok" : status === "degraded" ? "text-warn" : status === "down" ? "text-alarm" : "text-muted-foreground"
  return (
    <span className={cn("inline-flex items-center gap-1.5 font-medium", color)}>
      <Icon className="size-4" aria-hidden />
      <span>{children ?? status[0].toUpperCase() + status.slice(1)}</span>
    </span>
  )
}

/** Risk as a bar, labelled in words and numbers (never colour alone). */
export function RiskBar({ value, label }: { value: number; label: string }) {
  const color = value >= 0.6 ? "bg-alarm" : value >= 0.25 ? "bg-warn" : "bg-ok"
  return (
    <div className="grid grid-cols-[4.5rem_1fr_3rem] items-center gap-2 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <div className="h-2 rounded-full bg-muted" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(value * 100)} aria-label={`${label} stockout risk`}>
        <div className={cn("h-2 rounded-full", color)} style={{ width: `${Math.max(2, value * 100)}%` }} />
      </div>
      <span className="text-right font-semibold">{Math.round(value * 100)}%</span>
    </div>
  )
}
