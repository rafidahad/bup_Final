import { useState } from "react"
import { type Decision, type SimAllocation, type Status, usePoll } from "@/lib/api"
import { clock, fuel, inTicks, liters, roadName, stationName } from "@/lib/text"
import { cn } from "@/lib/utils"
import { FuelDot, Panel } from "./parts"

const WHO: Record<string, string> = { approved: "by you", auto_approved: "automatically", auto_low_confidence: "automatically (low confidence — please check)", rejected: "skipped by you" }

export function History({ status }: { status: Status | null }) {
  const tm = status?.tick_minutes ?? 15
  const now = status?.tick ?? 0
  const { data: decisions } = usePoll<Decision[]>("/api/decisions?limit=100", 2000)
  const { data: ships } = usePoll<SimAllocation[]>("/api/allocations", 2000)
  const [show, setShow] = useState<"moving" | "all">("moving")
  const current = (decisions ?? []).filter(d => !status || d.run_id === status.run_id)
  const list = (ships ?? []).filter(a => show === "all" || a.status === "PENDING" || a.status === "IN_TRANSIT")

  return (
    <div className="grid gap-5 xl:grid-cols-2">
      <Panel title="Decisions">
        {!current.length
          ? <p className="px-5 py-8 text-center text-base text-muted-foreground">No decisions yet in this simulation. Send or skip a shipment on the Actions page.</p>
          : <ul className="divide-y">{current.map(d => (
            <li key={d.id} className="px-5 py-3 text-base">
              <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                <span className={cn("font-medium", d.status === "rejected" && "text-muted-foreground")}>
                  <FuelDot fuel={d.fuel} /> {d.status === "rejected" ? "Skipped" : "Sent"} {liters(d.liters)} {fuel(d.fuel).toLowerCase()} to {stationName(d.station_id)}
                </span>
                <span className="text-sm text-muted-foreground">{clock(d.tick, tm)}</span>
              </div>
              <div className="text-sm text-muted-foreground">
                {WHO[d.status] ?? d.status}
                {d.outcome && d.status !== "rejected" && (d.outcome.liters_accepted < d.liters * 0.99
                  ? `, ${liters(d.outcome.liters_accepted)} accepted (limits changed)` : ", accepted by the depot")}
              </div>
            </li>))}
          </ul>}
      </Panel>

      <Panel>
        <div className="flex flex-wrap items-center justify-between gap-2 border-b px-5 py-3">
          <h2 className="text-lg font-semibold">Shipments</h2>
          <div className="flex rounded-md border p-0.5 text-sm" role="group" aria-label="Which shipments">
            {(["moving", "all"] as const).map(v => (
              <button key={v} onClick={() => setShow(v)} aria-pressed={show === v}
                className={cn("rounded px-3 py-1", show === v ? "bg-ink text-white" : "hover:bg-muted")}>
                {v === "moving" ? "On the way" : "All"}
              </button>))}
          </div>
        </div>
        {!list.length
          ? <p className="px-5 py-8 text-center text-base text-muted-foreground">{show === "moving" ? "No shipments on the road right now." : "No shipments yet."}</p>
          : <ul className="divide-y">{list.slice(0, 120).map(a => (
            <li key={a.id} className="flex flex-wrap items-baseline justify-between gap-x-3 px-5 py-2.5 text-base">
              <span><FuelDot fuel={a.fuel_type} /> {liters(a.quantity)} {fuel(a.fuel_type).toLowerCase()}, {roadName(a.route_id)}</span>
              <ShipStatus a={a} now={now} tm={tm} />
            </li>))}
          </ul>}
      </Panel>
    </div>
  )
}

function ShipStatus({ a, now, tm }: { a: SimAllocation; now: number; tm: number }) {
  if (a.status === "ARRIVED") return <span className="text-ok">Delivered {clock(a.actual_arrival_tick, tm)}</span>
  if (a.status === "FAILED") return <span className="font-semibold text-alarm">Failed: {a.failure_reason === "ROUTE_UNAVAILABLE" ? "road closed" : (a.failure_reason ?? "unknown").toLowerCase()}</span>
  if (a.status === "CANCELLED") return <span className="text-muted-foreground">Cancelled</span>
  if (a.status === "PENDING") return <span className="text-muted-foreground">Leaving the depot</span>
  return <span>On the way, arrives {a.expected_arrival_tick != null ? inTicks(a.expected_arrival_tick, now, tm) : "soon"}</span>
}
