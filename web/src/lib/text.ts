// Plain-language wording for operators: no ticks, no internal ids, no statistics jargon.
import type { Alert, SimEvent } from "./api"

const STATION: Record<string, string> = {
  "station-mirpur": "Mirpur", "station-tongi": "Tongi", "station-karnaphuli": "Karnaphuli", "station-coxsbazar": "Cox's Bazar",
}
const DEPOT: Record<string, string> = { "depot-gazipur": "Gazipur", "depot-patiya": "Patiya" }
const REGION: Record<string, string> = { "region-dhaka": "Dhaka", "region-chattogram": "Chattogram" }

export const stationName = (id: string) => STATION[id] ?? id.replace(/^station-/, "")
export const depotName = (id: string) => DEPOT[id] ?? id.replace(/^depot-/, "")
export const regionName = (id: string) => REGION[id] ?? id.replace(/^region-/, "")
export function roadName(routeId: string) {
  const [, from, to] = routeId.split("-")
  return `${depotName(`depot-${from}`)} → ${stationName(`station-${to}`)}`
}
export const fuel = (f: string) => f[0] + f.slice(1).toLowerCase()
export const liters = (v: number) => `${Math.round(v).toLocaleString("en-US")} L`

/** "Day 2, 06:45" from a simulator tick. */
export function clock(tick: number | null | undefined, tickMinutes = 15) {
  if (tick == null) return "—"
  const mins = tick * tickMinutes
  const hh = String(Math.floor((mins % 1440) / 60)).padStart(2, "0")
  const mm = String(mins % 60).padStart(2, "0")
  return `Day ${Math.floor(mins / 1440) + 1}, ${hh}:${mm}`
}

/** "in 45 min" / "in 3.5 hours" for a duration given in hours. */
export function inTime(hours: number) {
  if (hours <= 0.05) return "now"
  if (hours < 1) return `in ${Math.max(1, Math.round(hours * 60))} min`
  return `in ${hours < 10 ? hours.toFixed(1) : Math.round(hours)} hours`
}

/** How soon, from now, a future tick is. */
export function inTicks(tick: number, now: number, tickMinutes = 15) {
  return inTime(((tick - now) * tickMinutes) / 60)
}

export type Level = "ok" | "low" | "critical" | "closed"

export function level(stockoutHours: number | null | undefined, open = true): Level {
  if (!open) return "closed"
  if (stockoutHours == null) return "ok"
  return stockoutHours < 3 ? "critical" : "low"
}

export const LEVEL_TEXT: Record<Level, string> = { ok: "OK", low: "Low", critical: "Critical", closed: "Closed" }

const listOf = (ids: unknown, name: (s: string) => string, all: string) =>
  Array.isArray(ids) && ids.length ? ids.map(i => name(String(i))).join(", ") : all

/** One readable sentence for a simulator event. */
export function describeEvent(e: SimEvent, tickMinutes = 15) {
  const p = e.parameters as Record<string, unknown>
  const until = `until ${clock(e.end_tick, tickMinutes)}`
  const when = e.status === "SCHEDULED" ? `from ${clock(e.start_tick, tickMinutes)} ${until}` : until
  switch (e.type) {
    case "demand_spike": {
      const where = Array.isArray(p.station_ids) && p.station_ids.length ? listOf(p.station_ids, stationName, "")
        : listOf(p.region_ids, regionName, "all stations")
      return `Demand surge at ${where}: about ${Number(p.multiplier ?? 1.5).toFixed(1)}× normal, ${when}`
    }
    case "route_disruption": return `Road closed: ${listOf(p.route_ids, roadName, "all roads")}, ${when}`
    case "station_outage": return `Station closed: ${listOf(p.station_ids, stationName, "all stations")}, ${when}`
    case "depot_constraint": return `Depot restricted: ${listOf(p.depot_ids, depotName, "all depots")}, ${when}`
    case "shipment_delay": {
      const h = (Number(p.delay_ticks ?? 2) * tickMinutes) / 60
      return `Supply to ${listOf(p.depot_ids, depotName, "all depots")} delayed by ${h} hours`
    }
    case "supply_shortfall":
      return `Supply to ${listOf(p.depot_ids, depotName, "all depots")} cut to ${Math.round(Number(p.factor ?? 0.5) * 100)}%` +
        (Array.isArray(p.fuel_types) && p.fuel_types.length ? ` (${p.fuel_types.map(x => fuel(String(x)).toLowerCase()).join(", ")})` : "")
    default: return `${e.type.replace(/_/g, " ")}, ${when}`
  }
}

/** Merge per-fuel alerts into one readable line per place. */
export function describeAlerts(alerts: Alert[]): { tone: "warn" | "alarm"; text: string }[] {
  const out: { tone: "warn" | "alarm"; text: string }[] = []
  const unusual = new Map<string, string[]>()
  for (const a of alerts) {
    if (a.kind === "anomalous_demand" && a.station_id && a.fuel) {
      const k = stationName(a.station_id)
      unusual.set(k, [...(unusual.get(k) ?? []), fuel(a.fuel).toLowerCase()])
    } else if (a.kind === "abnormal_inventory" && a.station_id) {
      out.push({ tone: "warn", text: `${stationName(a.station_id)} ${a.fuel ? fuel(a.fuel).toLowerCase() : ""} stock fell faster than sales explain` })
    } else if (a.kind === "bottleneck" && a.depot_id) {
      out.push({ tone: "warn", text: `${depotName(a.depot_id)} depot is sending at full capacity` })
    }
  }
  for (const [place, fuels] of unusual) out.unshift({ tone: "warn", text: `Unusual demand at ${place}: ${fuels.join(", ")} selling much faster than normal` })
  return out
}
