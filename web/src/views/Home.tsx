import { AlertTriangle, CheckCircle2, ArrowRight } from "lucide-react"
import { NetworkMap } from "@/components/NetworkMap"
import { Button } from "@/components/ui/button"
import { type Alert, type Card, type FuelLevel, type Overview, type SimAllocation, type Station, usePoll } from "@/lib/api"
import { type Level, LEVEL_TEXT, clock, depotName, describeAlerts, describeEvent, fuel, inTicks, level, liters, stationName } from "@/lib/text"
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
  const { data: allocs } = usePoll<SimAllocation[]>("/api/allocations", 2000)
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
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="stations" className="text-xl font-semibold">Station tanks</h2>
          <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
            <span className="flex items-center gap-1.5"><span className="inline-block h-3 w-5 rounded-sm" style={{ background: "repeating-linear-gradient(135deg, var(--ink) 0 2px, transparent 2px 5px)", opacity: 0.5 }} />fuel on the way</span>
            <span className="flex items-center gap-1.5"><span className="inline-block w-5 border-t-2 border-dashed border-ink/70" />fuel needed for the next 12 hours</span>
          </p>
        </div>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {data.stations.map(s => <StationCard key={s.id} station={s} now={data.tick} tickMinutes={tm} />)}
        </div>
      </section>

      <div className="grid gap-4 xl:grid-cols-[3fr_2fr]">
        <Panel title="Roads between depots and stations">
          <div className="p-3">
            <NetworkMap depots={data.depots} stations={data.stations} routes={data.routes} allocations={allocs ?? []} tickMinutes={tm} />
          </div>
        </Panel>
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
      <div className="flex justify-around gap-2">
        {s.fuels.map((f, i) => <Tank key={f.fuel} f={f} lvl={levels[i]} now={now} tickMinutes={tickMinutes} />)}
      </div>
    </Panel>
  )
}

/** One tank: stock (solid), fuel on the way (striped), and the fuel needed for the next 12 hours (dashed line). */
function Tank({ f, lvl, now, tickMinutes }: { f: FuelLevel; lvl: Level; now: number; tickMinutes: number }) {
  const pct = (v: number) => Math.max(0, Math.min(100, (v / f.capacity) * 100))
  const fill = pct(f.inventory)
  const coming = Math.min(pct(f.incoming ?? 0), 100 - fill)
  const need12 = pct((f.demand_per_day ?? 0) / 2)
  const color = `var(--${f.fuel.toLowerCase()})`
  const tone = lvl === "critical" || lvl === "closed" ? "text-alarm" : lvl === "low" ? "text-warn" : "text-ok"
  const left = lvl === "closed" ? "Not selling"
    : f.stockout_hours == null ? "12+ h left"
      : f.stockout_hours <= 0.05 ? "Empty now"
        : f.stockout_hours < 1 ? `${Math.max(1, Math.round(f.stockout_hours * 60))} min left` : `${f.stockout_hours.toFixed(1)} h left`
  return (
    <figure className="flex w-[4.75rem] flex-col items-center gap-2" aria-label={`${fuel(f.fuel)}: ${liters(f.inventory)} of ${liters(f.capacity)}, ${left}`}>
      <div className="relative h-40 w-12 overflow-hidden rounded-md border-2 border-ink/25 bg-white">
        <div className="absolute inset-x-0 bottom-0 transition-[height] duration-700" style={{ height: `${fill}%`, background: color }} />
        {coming > 0 && <div className="absolute inset-x-0" style={{
          bottom: `${fill}%`, height: `${coming}%`, opacity: 0.55,
          background: `repeating-linear-gradient(135deg, ${color} 0 3px, transparent 3px 7px)`,
        }} />}
        {need12 > 0 && need12 < 100 && <div className="absolute inset-x-0 border-t-2 border-dashed border-ink/70" style={{ bottom: `${need12}%` }} />}
      </div>
      <figcaption className="text-center leading-snug">
        <div className="flex items-center justify-center gap-1.5 text-base font-medium"><FuelDot fuel={f.fuel} />{fuel(f.fuel)}</div>
        <div className="text-base font-semibold">{liters(f.inventory)}</div>
        <div className={cn("text-sm font-semibold", tone)}>{left}</div>
        {(f.incoming ?? 0) > 0 && f.next_arrival_tick != null &&
          <div className="text-sm text-muted-foreground">+{liters(f.incoming ?? 0)} {inTicks(f.next_arrival_tick, now, tickMinutes)}</div>}
      </figcaption>
    </figure>
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
