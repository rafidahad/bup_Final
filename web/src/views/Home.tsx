import { AlertTriangle, CheckCircle2, ArrowRight } from "lucide-react"
import { Button } from "@/components/ui/button"
import { type Alert, type Card, type FuelLevel, type Overview, type Station, usePoll } from "@/lib/api"
import { type Level, LEVEL_TEXT, clock, depotName, describeAlerts, describeEvent, fuel, inTicks, inTime, level, liters, roadName, stationName } from "@/lib/text"
import { cn } from "@/lib/utils"
import { FuelDot, Loading, Panel } from "./parts"

const LEVEL_STYLE: Record<Level, string> = {
  ok: "bg-ok/12 text-ok", low: "bg-warn/15 text-warn", critical: "bg-alarm/12 text-alarm", closed: "bg-alarm/12 text-alarm",
}
const RANK: Record<Level, number> = { ok: 0, low: 1, critical: 2, closed: 3 }

export function LevelBadge({ value }: { value: Level }) {
  return <span className={cn("rounded-full px-2.5 py-0.5 text-sm font-semibold", LEVEL_STYLE[value])}>{LEVEL_TEXT[value]}</span>
}

export function Home({ go }: { go: (v: "actions") => void }) {
  const { data, error } = usePoll<Overview>("/api/overview", 1000)
  const { data: recs } = usePoll<{ cards: Card[] }>("/api/recommendations", 2000)
  const { data: alerts } = usePoll<{ alerts: Alert[] }>("/api/alerts", 2000)
  if (!data) return <Loading error={error} />

  const tm = data.tick_minutes
  const rows = data.stations.flatMap(s => s.fuels.map(f => level(f.stockout_hours, s.status === "OPEN")))
  const needs = rows.filter(l => l !== "ok").length
  const actions = recs?.cards.filter(c => c.allocations.length).length ?? 0
  const problems = [
    ...data.events.map(e => ({ tone: e.status === "ACTIVE" ? "alarm" as const : "warn" as const, text: describeEvent(e, tm) })),
    ...describeAlerts(alerts?.alerts ?? []),
  ]
  const m = data.metrics

  return (
    <div className="space-y-6">
      <Panel className={cn("flex flex-wrap items-center gap-4 px-5 py-4", needs ? "border-warn/50" : "border-ok/40")}>
        {needs
          ? <AlertTriangle className="size-8 shrink-0 text-warn" aria-hidden />
          : <CheckCircle2 className="size-8 shrink-0 text-ok" aria-hidden />}
        <div className="min-w-0 flex-1">
          <p className="text-xl font-semibold">
            {needs ? `${needs} fuel tank${needs === 1 ? "" : "s"} will run short within 12 hours` : "All stations have enough fuel for the next 12 hours"}
          </p>
          <p className="text-base text-muted-foreground">
            {recs == null ? "Checking which shipments can help…" : actions ? `${actions} shipment${actions === 1 ? " is" : "s are"} ready to fix this.` : needs ? "No shipment can help right now; see the problems below." : "Nothing to do right now."}
          </p>
        </div>
        {actions > 0 && <Button size="lg" onClick={() => go("actions")}>Review shipments <ArrowRight aria-hidden /></Button>}
      </Panel>

      {problems.length > 0 && (
        <Panel title="Problems right now">
          <ul className="divide-y">
            {problems.map((p, i) => (
              <li key={i} className="flex items-start gap-3 px-5 py-3 text-base">
                <span className={cn("mt-2 size-2.5 shrink-0 rounded-full", p.tone === "alarm" ? "bg-alarm" : "bg-warn")} aria-hidden />
                {p.text}
              </li>))}
          </ul>
        </Panel>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <Stat label="Customer demand served" value={m ? `${(m.service_level * 100).toFixed(1)}%` : "—"}
          note={m ? `${liters(m.unmet_demand_liters)} could not be sold so far` : "waiting for the simulator"} />
        <Stat label="Fuel left in the whole network" value={data.supply.days_of_fuel ? `${data.supply.days_of_fuel.toFixed(1)} days` : "—"}
          note={data.supply.future_supply > 0 ? `No new supply after ${clock(data.supply.last_supply_tick, tm)}` : "All scheduled supply has arrived; no more is coming"} />
      </div>

      <section aria-labelledby="stations">
        <h2 id="stations" className="mb-3 text-xl font-semibold">Stations</h2>
        <div className="grid gap-4 lg:grid-cols-2">
          {data.stations.map(s => <StationCard key={s.id} station={s} now={data.tick} tickMinutes={tm} />)}
        </div>
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Depots (where fuel comes from)">
          <ul className="divide-y">{data.depots.map(d => (
            <li key={d.id} className="px-5 py-3">
              <div className="flex items-center justify-between">
                <span className="text-base font-semibold">{depotName(d.id)} depot</span>
                {d.status !== "OPEN" && <span className="text-sm font-semibold text-warn">Restricted</span>}
              </div>
              <div className="mt-1 flex flex-wrap gap-x-5 gap-y-1 text-base">
                {d.fuels.map(f => <span key={f.fuel}><FuelDot fuel={f.fuel} /> {fuel(f.fuel)} {liters(f.inventory)}</span>)}
              </div>
            </li>))}
          </ul>
        </Panel>
        <Panel title="Roads">
          <ul className="divide-y">{data.routes.map(r => (
            <li key={r.id} className="flex items-center justify-between px-5 py-2.5 text-base">
              <span>{roadName(r.id)}</span>
              {r.status === "AVAILABLE"
                ? <span className="text-muted-foreground">Open, {(r.transit_ticks * tm) / 60 < 1 ? `${r.transit_ticks * tm} min` : `${(r.transit_ticks * tm) / 60} h`} drive</span>
                : <span className="font-semibold text-alarm">Closed</span>}
            </li>))}
          </ul>
        </Panel>
      </div>
    </div>
  )
}

function StationCard({ station: s, now, tickMinutes }: { station: Station; now: number; tickMinutes: number }) {
  const open = s.status === "OPEN"
  const levels = s.fuels.map(f => level(f.stockout_hours, open))
  const worst = levels.reduce((a, b) => (RANK[b] > RANK[a] ? b : a), "ok" as Level)
  return (
    <Panel className="px-5 py-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="text-lg font-semibold">{stationName(s.id)}</h3>
        <LevelBadge value={worst} />
      </div>
      {!open && <p className="mb-2 text-base font-medium text-alarm">This station is closed; customers cannot buy fuel here.</p>}
      {open && s.demand_multiplier !== 1 && <p className="mb-2 text-base text-warn">Demand is {s.demand_multiplier.toFixed(1)}× normal here.</p>}
      <ul className="space-y-3">
        {s.fuels.map((f, i) => <FuelRow key={f.fuel} f={f} lvl={levels[i]} now={now} tickMinutes={tickMinutes} />)}
      </ul>
    </Panel>
  )
}

function FuelRow({ f, lvl, now, tickMinutes }: { f: FuelLevel; lvl: Level; now: number; tickMinutes: number }) {
  const pct = (v: number) => Math.max(0, Math.min(100, (v / f.capacity) * 100))
  const fill = pct(f.inventory)
  const coming = Math.min(pct(f.incoming ?? 0), 100 - fill)
  const color = lvl === "critical" || lvl === "closed" ? "text-alarm" : lvl === "low" ? "text-warn" : "text-muted-foreground"
  return (
    <li>
      <div className="flex items-baseline justify-between gap-2 text-base">
        <span className="font-medium"><FuelDot fuel={f.fuel} /> {fuel(f.fuel)}</span>
        <span className={cn("font-medium", color)}>
          {lvl === "closed" ? "Not selling" : f.stockout_hours == null ? "Enough for 12+ hours" : `Runs out ${inTime(f.stockout_hours)}`}
        </span>
      </div>
      <div className="mt-1 flex h-3 overflow-hidden rounded-full bg-muted" role="img"
        aria-label={`${fuel(f.fuel)}: ${liters(f.inventory)} of ${liters(f.capacity)}`}>
        <div className="h-full" style={{ width: `${fill}%`, background: `var(--${f.fuel.toLowerCase()})` }} />
        {coming > 0 && <div className="h-full opacity-35" style={{ width: `${coming}%`, background: `var(--${f.fuel.toLowerCase()})` }} />}
      </div>
      <div className="mt-1 flex flex-wrap justify-between gap-x-3 text-sm text-muted-foreground">
        <span>{liters(f.inventory)} of {liters(f.capacity)}</span>
        {(f.incoming ?? 0) > 0 && f.next_arrival_tick != null &&
          <span className="font-medium text-foreground">+{liters(f.incoming ?? 0)} arriving {inTicks(f.next_arrival_tick, now, tickMinutes)}</span>}
      </div>
    </li>
  )
}

function Stat({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <Panel className="px-5 py-4">
      <div className="text-base text-muted-foreground">{label}</div>
      <div className="font-heading text-4xl font-semibold">{value}</div>
      <div className="text-sm text-muted-foreground">{note}</div>
    </Panel>
  )
}
