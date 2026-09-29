import type { Depot, Route, SimAllocation, Station } from "@/lib/api"

const DEPOT_Y: Record<string, number> = { "depot-gazipur": 95, "depot-patiya": 225 }
const STATION_Y: Record<string, number> = { "station-mirpur": 40, "station-tongi": 118, "station-karnaphuli": 200, "station-coxsbazar": 278 }
const X_DEPOT = 118
const X_STATION = 470

/** Schematic of the six real routes (not geography). Disrupted routes are dashed and labelled. */
export function NetworkMap({ depots, stations, routes, allocations }: {
  depots: Depot[]; stations: Station[]; routes: Route[]; allocations: SimAllocation[]
}) {
  const moving = new Map<string, number>()
  for (const a of allocations) {
    if (a.status === "IN_TRANSIT" || a.status === "PENDING") moving.set(a.route_id, (moving.get(a.route_id) ?? 0) + a.quantity)
  }
  const yOf = (id: string, table: Record<string, number>, i: number) => table[id] ?? 40 + i * 70
  return (
    <svg viewBox="0 0 620 320" className="h-auto w-full" role="img" aria-label="Route network between depots and stations">
      {routes.map(r => {
        const y1 = yOf(r.source_depot_id, DEPOT_Y, 0)
        const y2 = yOf(r.destination_station_id, STATION_Y, 0)
        const down = r.status !== "AVAILABLE"
        const load = moving.get(r.id) ?? 0
        const mx = (X_DEPOT + X_STATION) / 2, my = (y1 + y2) / 2
        return (
          <g key={r.id}>
            <line x1={X_DEPOT + 10} y1={y1} x2={X_STATION - 10} y2={y2}
              stroke={down ? "var(--alarm)" : "var(--ink)"} strokeOpacity={down ? 1 : 0.55}
              strokeWidth={load > 0 ? 3 : 1.5} strokeDasharray={down ? "6 5" : undefined} />
            <text x={mx} y={my - 6} textAnchor="middle" className="fill-muted-foreground text-[11px]" paintOrder="stroke" stroke="var(--background)" strokeWidth={4}>
              {down ? "disrupted" : `${r.transit_ticks} ticks${load > 0 ? `, ${Math.round(load).toLocaleString("en-US")} L moving` : ""}`}
            </text>
          </g>
        )
      })}
      {depots.map((d, i) => {
        const y = yOf(d.id, DEPOT_Y, i)
        const total = d.fuels.reduce((s, f) => s + f.inventory, 0)
        const cap = d.fuels.reduce((s, f) => s + f.capacity, 0)
        return (
          <g key={d.id}>
            <rect x={8} y={y - 26} width={X_DEPOT - 4} height={52} rx={4} fill="var(--ink)" />
            <text x={18} y={y - 6} className="fill-white text-[14px] font-semibold">{d.name.replace(" Depot", "")}</text>
            <text x={18} y={y + 13} className="fill-white/75 text-[11px]">
              {Math.round(total / 1000)}k of {Math.round(cap / 1000)}k L{d.status !== "OPEN" ? ", constrained" : ""}
            </text>
          </g>
        )
      })}
      {stations.map((s, i) => {
        const y = yOf(s.id, STATION_Y, i)
        const out = s.status !== "OPEN"
        return (
          <g key={s.id}>
            <circle cx={X_STATION} cy={y} r={9} fill={out ? "var(--alarm)" : "var(--background)"} stroke="var(--ink)" strokeWidth={2} />
            <text x={X_STATION + 16} y={y - 2} className="fill-foreground text-[14px] font-semibold">{s.name.replace(/ (Fuel|Highway) Station/, "").replace(" Station", "")}</text>
            <text x={X_STATION + 16} y={y + 13} className={out ? "fill-alarm text-[11px] font-semibold" : "fill-muted-foreground text-[11px]"}>
              {out ? "outage" : s.demand_multiplier !== 1 ? `demand ×${s.demand_multiplier.toFixed(2)}` : s.demand_profile.replace("_", " ")}
            </text>
          </g>
        )
      })}
    </svg>
  )
}
