import { useCallback, useEffect, useRef, useState } from "react"

export type Fuel = "DIESEL" | "PETROL" | "OCTANE"
export const FUELS: Fuel[] = ["DIESEL", "PETROL", "OCTANE"]

export interface Status {
  run_id: string; mode: "observe" | "manual" | "auto"; policy: string; policies: string[]; source: string
  intelligence_enabled: boolean; degraded: string | null; tick: number | null; sim_status: string | null
  tick_minutes: number | null; snapshot_age_s: number | null; cycles: number; token_required: boolean
}
export interface FuelLevel { fuel: Fuel; inventory: number; capacity: number; incoming?: number; demand_per_day?: number }
export interface Station { id: string; name: string; status: string; region_id: string; demand_profile: string; demand_multiplier: number; fuels: FuelLevel[] }
export interface Depot { id: string; name: string; status: string; region_id: string; dispatch_capacity_per_tick: number; fuels: FuelLevel[] }
export interface Route { id: string; source_depot_id: string; destination_station_id: string; transit_ticks: number; max_shipment: number; status: string }
export interface SimEvent { id: number; type: string; start_tick: number; end_tick: number; status: string; parameters: Record<string, unknown> }
export interface SupplyRow { id: string; depot_id: string; fuel_type: Fuel; quantity: number; planned_tick: number; status: string }
export interface Overview {
  tick: number; tick_minutes: number
  metrics: { served_demand_liters: number; unmet_demand_liters: number; service_level: number; allocation_liters: number; allocation_failures: number } | null
  stations: Station[]; depots: Depot[]; routes: Route[]; events: SimEvent[]; incoming_supply: SupplyRow[]
  regions: { id: string; name: string; demand_per_day: number; demand_factor: number }[]
  supply: { fuel_in_world: number; future_supply: number; demand_per_day: number; days_of_fuel: number | null; last_supply_tick: number | null }
}
export interface Projection { stockout_hours: number | null; risk: number; unmet: number; expected_demand: number }
export interface Allocation {
  route_id: string; depot_id: string; liters: number; transit_ticks: number; arrival_tick: number; requests: number
  limits: Record<string, number>; binding: string | null
}
export interface Card {
  id: string; tick: number; station_id: string; station: string; fuel: Fuel; region_id: string
  inventory: number; capacity: number; incoming: number; before: Projection; after: Projection | null
  allocations: Allocation[]; signals: string[]; confidence: number; noise_sigma: number; noise_rows: number
  source: string; review_required: boolean; why: string
  alternatives: { route_id: string; depot_id: string; usable: boolean; reason: string | null; transit_ticks: number; liters: number; depot_stock: number; risk_after: number | null; stockout_hours_after: number | null }[]
}
export interface Alert { kind: string; severity: string; detail: string; station_id?: string; fuel?: Fuel; depot_id?: string; event_id?: number }
export interface Incident { wall: number; tick: number | null; kind: string; detail: string }
export interface Decision {
  id: number; wall: number; tick: number; station_id: string; fuel: Fuel; status: string; decided_by: string; source: string
  confidence: number; risk_before: number; risk_after: number | null; liters: number; outcome: { liters_accepted: number } | null
}
export interface Health {
  status: string; p95_latency_ms: number | null; error_rate: number; window_requests: number
  components: Record<string, { status: string; detail?: string | null; [k: string]: unknown }>
}
export interface SimAllocation {
  id: number; source_depot_id: string; destination_station_id: string; route_id: string; fuel_type: Fuel; quantity: number
  created_tick: number; departure_tick: number | null; expected_arrival_tick: number | null; actual_arrival_tick: number | null
  status: string; failure_reason: string | null
}

const TOKEN_KEY = "fuelops-operator-token"
export function getToken(): string {
  try { return sessionStorage.getItem(TOKEN_KEY) ?? "" } catch { return "" }
}
export function setToken(t: string) {
  try { sessionStorage.setItem(TOKEN_KEY, t) } catch { /* private mode: token lives only in memory */ }
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) { super(message); this.status = status }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" }
  const token = getToken()
  if (token) headers["X-Operator-Token"] = token
  const r = await fetch(path, { ...init, headers: { ...headers, ...(init?.headers as Record<string, string>) } })
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`
    try {
      const body = await r.json()
      msg = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body)
    } catch { /* keep status text */ }
    throw new ApiError(r.status, msg)
  }
  return r.json() as Promise<T>
}

/** Poll an endpoint. Keeps the last good value when a request fails, and reports the error. */
export function usePoll<T>(path: string, ms = 1000) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [updated, setUpdated] = useState<number | null>(null)
  const alive = useRef(true)
  const load = useCallback(async () => {
    try {
      const d = await api<T>(path)
      if (!alive.current) return
      setData(d); setError(null); setUpdated(Date.now())
    } catch (e) {
      if (alive.current) setError(e instanceof Error ? e.message : String(e))
    }
  }, [path])
  useEffect(() => {
    alive.current = true
    load()
    const id = setInterval(load, ms)
    return () => { alive.current = false; clearInterval(id) }
  }, [load, ms])
  return { data, error, updated, reload: load }
}

export const fmtL = (v: number | null | undefined) => v == null ? "—" : `${Math.round(v).toLocaleString("en-US")} L`
export const fmtPct = (v: number | null | undefined, digits = 0) => v == null ? "—" : `${(v * 100).toFixed(digits)}%`
export const fmtHours = (h: number | null | undefined) => h == null ? "no stockout in 12 h" : h < 1 ? `${Math.round(h * 60)} min` : `${h.toFixed(1)} h`
export function simClock(tick: number | null | undefined, tickMinutes = 15) {
  if (tick == null) return "—"
  const mins = tick * tickMinutes
  const day = Math.floor(mins / 1440) + 1
  const hh = String(Math.floor((mins % 1440) / 60)).padStart(2, "0")
  const mm = String(mins % 60).padStart(2, "0")
  return `Day ${day}, ${hh}:${mm}`
}
export const pretty = (id: string) => id.replace(/^(station|depot|route|region)-/, "").split("-").map(w => w[0].toUpperCase() + w.slice(1)).join(" → ")
export const fuelName = (f: string) => f[0] + f.slice(1).toLowerCase()
