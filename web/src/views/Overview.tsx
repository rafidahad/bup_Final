import { NetworkMap } from "@/components/NetworkMap"
import { FuelSwatch, TankGauge } from "@/components/fuel"
import { Skeleton } from "@/components/ui/skeleton"
import { type Overview as OverviewData, type SimAllocation, fmtL, fmtPct, fuelName, simClock, usePoll } from "@/lib/api"

export function Overview() {
  const { data, error } = usePoll<OverviewData>("/api/overview", 1000)
  const { data: allocs } = usePoll<SimAllocation[]>("/api/allocations", 2000)
  if (!data) return <Waiting error={error} />
  const m = data.metrics
  return (
    <div className="space-y-8">
      <section aria-labelledby="kpi" className="grid gap-x-10 gap-y-4 sm:grid-cols-2 xl:grid-cols-4">
        <h2 id="kpi" className="sr-only">Network summary</h2>
        <Figure label="Demand served since start" value={m ? fmtPct(m.service_level, 1) : "unavailable"}
          note={m ? `${fmtL(m.unmet_demand_liters)} unmet` : "simulator metrics unavailable"} />
        <Figure label="Fuel shipped" value={m ? fmtL(m.allocation_liters) : "—"}
          note={m ? `${m.allocation_failures} failed shipment${m.allocation_failures === 1 ? "" : "s"}` : ""} />
        <Figure label="Fuel left in the network" value={data.supply.days_of_fuel ? `${data.supply.days_of_fuel.toFixed(1)} days` : "—"}
          note={`${fmtL(data.supply.fuel_in_world)} on hand, ${fmtL(data.supply.future_supply)} still scheduled`} />
        <Figure label="Scheduled supply ends" value={data.supply.last_supply_tick != null ? simClock(data.supply.last_supply_tick, data.tick_minutes) : "—"}
          note="no resupply is scheduled after this" />
      </section>

      <section aria-labelledby="tanks">
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="tanks" className="text-lg font-semibold">Station tanks</h2>
          <p className="text-xs text-muted-foreground">Hatched: fuel on the way. Dashed line: 12 hours of expected demand.</p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {data.stations.map(s => (
            <div key={s.id} className="rounded-md border bg-card px-4 py-3">
              <div className="mb-3 flex items-baseline justify-between gap-2">
                <h3 className="font-semibold">{s.name}</h3>
                <span className={s.status === "OPEN" ? "text-xs text-muted-foreground" : "text-xs font-semibold text-alarm"}>
                  {s.status === "OPEN" ? (s.demand_multiplier !== 1 ? `demand ×${s.demand_multiplier.toFixed(2)}` : "open") : "outage"}
                </span>
              </div>
              <div className="flex justify-around">{s.fuels.map(f => <TankGauge key={f.fuel} level={f} />)}</div>
            </div>
          ))}
        </div>
      </section>

      <div className="grid gap-8 xl:grid-cols-[3fr_2fr]">
        <section aria-labelledby="net">
          <h2 id="net" className="mb-2 text-lg font-semibold">Routes</h2>
          <div className="rounded-md border bg-card p-3">
            <NetworkMap depots={data.depots} stations={data.stations} routes={data.routes} allocations={allocs ?? []} />
          </div>
        </section>
        <div className="space-y-8">
          <section aria-labelledby="regions">
            <h2 id="regions" className="mb-2 text-lg font-semibold">Regional demand</h2>
            <dl className="divide-y rounded-md border bg-card">
              {data.regions.map(r => (
                <div key={r.id} className="flex items-baseline justify-between px-4 py-2.5">
                  <dt>{r.name}</dt>
                  <dd className="font-semibold">{fmtL(r.demand_per_day)} per day</dd>
                </div>
              ))}
            </dl>
          </section>
          <section aria-labelledby="depots">
            <h2 id="depots" className="mb-2 text-lg font-semibold">Depot stock</h2>
            <table className="w-full rounded-md border bg-card text-sm">
              <thead><tr className="border-b text-left text-muted-foreground"><th className="px-4 py-2 font-medium">Depot</th>
                {data.depots[0]?.fuels.map(f => <th key={f.fuel} className="px-2 py-2 text-right font-medium"><FuelSwatch fuel={f.fuel} /> {fuelName(f.fuel)}</th>)}</tr></thead>
              <tbody>{data.depots.map(d => (
                <tr key={d.id} className="border-b last:border-0">
                  <td className="px-4 py-2">{d.name}{d.status !== "OPEN" && <span className="ml-2 text-xs font-semibold text-warn">constrained</span>}</td>
                  {d.fuels.map(f => <td key={f.fuel} className="px-2 py-2 text-right">{Math.round(f.inventory).toLocaleString("en-US")}</td>)}
                </tr>))}</tbody>
            </table>
          </section>
        </div>
      </div>

      <div className="grid gap-8 xl:grid-cols-2">
        <section aria-labelledby="supply">
          <h2 id="supply" className="mb-2 text-lg font-semibold">Incoming supply to depots</h2>
          {data.incoming_supply.length === 0
            ? <p className="text-sm text-muted-foreground">No more supply is scheduled. Fuel now only moves between depots and stations.</p>
            : <table className="w-full rounded-md border bg-card text-sm">
              <thead><tr className="border-b text-left text-muted-foreground"><th className="px-4 py-2 font-medium">Arrives</th><th className="px-2 py-2 font-medium">Depot</th><th className="px-2 py-2 font-medium">Fuel</th><th className="px-2 py-2 text-right font-medium">Liters</th><th className="px-4 py-2 font-medium">Status</th></tr></thead>
              <tbody>{data.incoming_supply.slice(0, 8).map(s => (
                <tr key={s.id} className="border-b last:border-0">
                  <td className="px-4 py-2">{simClock(s.planned_tick, data.tick_minutes)}</td>
                  <td className="px-2 py-2">{s.depot_id.replace("depot-", "").replace(/^\w/, c => c.toUpperCase())}</td>
                  <td className="px-2 py-2"><FuelSwatch fuel={s.fuel_type} /> {fuelName(s.fuel_type)}</td>
                  <td className="px-2 py-2 text-right">{Math.round(s.quantity).toLocaleString("en-US")}</td>
                  <td className={s.status === "DELAYED" ? "px-4 py-2 font-semibold text-warn" : "px-4 py-2 text-muted-foreground"}>{s.status.toLowerCase()}</td>
                </tr>))}</tbody>
            </table>}
        </section>
        <section aria-labelledby="events">
          <h2 id="events" className="mb-2 text-lg font-semibold">Disruptions</h2>
          {data.events.length === 0
            ? <p className="text-sm text-muted-foreground">No active or scheduled disruptions.</p>
            : <ul className="divide-y rounded-md border bg-card text-sm">{data.events.map(e => (
              <li key={e.id} className="px-4 py-2.5">
                <span className={e.status === "ACTIVE" ? "font-semibold text-alarm" : "font-semibold text-warn"}>{e.type.replace("_", " ")}</span>
                <span className="ml-2 text-muted-foreground">{e.status.toLowerCase()}, {simClock(e.start_tick, data.tick_minutes)} to {simClock(e.end_tick, data.tick_minutes)}</span>
                <div className="mt-0.5 text-xs text-muted-foreground">{describeParams(e.parameters)}</div>
              </li>))}</ul>}
        </section>
      </div>
    </div>
  )
}

function describeParams(p: Record<string, unknown>) {
  const parts = Object.entries(p).map(([k, v]) => `${k.replace("_ids", "s").replace("_", " ")}: ${Array.isArray(v) ? (v.length ? v.join(", ") : "all") : String(v)}`)
  return parts.length ? parts.join("; ") : "applies to all"
}

function Figure({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div>
      <div className="text-sm text-muted-foreground">{label}</div>
      <div className="font-heading text-3xl font-semibold">{value}</div>
      {note && <div className="text-xs text-muted-foreground">{note}</div>}
    </div>
  )
}

export function Waiting({ error }: { error: string | null }) {
  return (
    <div className="space-y-3" aria-busy="true">
      <p className="text-sm text-muted-foreground">{error && !error.startsWith("Waiting") ? `Cannot reach the backend: ${error}. Retrying every second.` : "Waiting for the first snapshot from the simulator…"}</p>
      <Skeleton className="h-24 w-full" /><Skeleton className="h-48 w-full" />
    </div>
  )
}
