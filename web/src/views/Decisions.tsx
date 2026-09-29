import { useState } from "react"
import { FuelSwatch } from "@/components/fuel"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { type Decision, type SimAllocation, fmtL, fmtPct, fuelName, pretty, simClock, usePoll } from "@/lib/api"

const STATUS_TEXT: Record<string, string> = { approved: "Approved by operator", auto_approved: "Sent automatically", rejected: "Rejected" }

export function Decisions({ tickMinutes }: { tickMinutes: number }) {
  const { data: decisions } = usePoll<Decision[]>("/api/decisions?limit=200", 2000)
  const { data: allocs } = usePoll<SimAllocation[]>("/api/allocations", 2000)
  const [filter, setFilter] = useState("ALL")
  const shown = (allocs ?? []).filter(a => filter === "ALL" || a.status === filter)
  return (
    <div className="space-y-8">
      <section aria-labelledby="hist">
        <h2 id="hist" className="mb-1 text-lg font-semibold">Decision history</h2>
        <p className="mb-3 text-sm text-muted-foreground">Every recommendation that was approved, sent automatically, or rejected, with the risk the system expected.</p>
        {!decisions?.length
          ? <p className="rounded-md border bg-card px-4 py-6 text-center text-sm text-muted-foreground">No decisions yet. Approve or reject a recommendation to start the history.</p>
          : <div className="rounded-md border bg-card"><Table>
            <TableHeader><TableRow>
              <TableHead>When</TableHead><TableHead>Station</TableHead><TableHead>Decision</TableHead>
              <TableHead className="text-right">Planned</TableHead><TableHead className="text-right">Accepted</TableHead>
              <TableHead className="text-right">Risk before → after</TableHead><TableHead className="text-right">Confidence</TableHead><TableHead>Planner</TableHead>
            </TableRow></TableHeader>
            <TableBody>{decisions.map(d => (
              <TableRow key={d.id}>
                <TableCell>{simClock(d.tick, tickMinutes)}</TableCell>
                <TableCell><FuelSwatch fuel={d.fuel} /> {pretty(d.station_id)} {fuelName(d.fuel).toLowerCase()}</TableCell>
                <TableCell className={d.status === "rejected" ? "text-muted-foreground" : ""}>{STATUS_TEXT[d.status] ?? d.status}</TableCell>
                <TableCell className="text-right">{fmtL(d.liters)}</TableCell>
                <TableCell className="text-right">{d.outcome ? fmtL(d.outcome.liters_accepted) : "—"}</TableCell>
                <TableCell className="text-right">{fmtPct(d.risk_before)} → {fmtPct(d.risk_after)}</TableCell>
                <TableCell className="text-right">{fmtPct(d.confidence)}</TableCell>
                <TableCell className="text-muted-foreground">{d.source}</TableCell>
              </TableRow>))}</TableBody>
          </Table></div>}
      </section>

      <section aria-labelledby="ship">
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="ship" className="text-lg font-semibold">Shipments in the simulator</h2>
          <label className="flex items-center gap-2 text-sm">Show
            <select value={filter} onChange={e => setFilter(e.target.value)} className="rounded-md border bg-card px-2 py-1">
              {["ALL", "PENDING", "IN_TRANSIT", "ARRIVED", "FAILED", "CANCELLED"].map(s => <option key={s} value={s}>{s === "ALL" ? "all" : s.toLowerCase().replace("_", " ")}</option>)}
            </select>
          </label>
        </div>
        {!shown.length
          ? <p className="rounded-md border bg-card px-4 py-6 text-center text-sm text-muted-foreground">No shipments{filter !== "ALL" ? " with this status" : " yet"}.</p>
          : <div className="rounded-md border bg-card"><Table>
            <TableHeader><TableRow>
              <TableHead>#</TableHead><TableHead>Route</TableHead><TableHead>Fuel</TableHead><TableHead className="text-right">Liters</TableHead>
              <TableHead>Created</TableHead><TableHead>Arrives</TableHead><TableHead>Status</TableHead>
            </TableRow></TableHeader>
            <TableBody>{shown.slice(0, 150).map(a => (
              <TableRow key={a.id}>
                <TableCell className="text-muted-foreground">{a.id}</TableCell>
                <TableCell>{pretty(a.route_id)}</TableCell>
                <TableCell><FuelSwatch fuel={a.fuel_type} /> {fuelName(a.fuel_type)}</TableCell>
                <TableCell className="text-right">{Math.round(a.quantity).toLocaleString("en-US")}</TableCell>
                <TableCell>{simClock(a.created_tick, tickMinutes)}</TableCell>
                <TableCell>{simClock(a.actual_arrival_tick ?? a.expected_arrival_tick, tickMinutes)}</TableCell>
                <TableCell className={a.status === "FAILED" ? "font-semibold text-alarm" : ""}>
                  {a.status.toLowerCase().replace("_", " ")}{a.failure_reason ? ` (${a.failure_reason.toLowerCase().replace(/_/g, " ")})` : ""}
                </TableCell>
              </TableRow>))}</TableBody>
          </Table></div>}
      </section>
    </div>
  )
}
