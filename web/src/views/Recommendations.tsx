import { useState } from "react"
import { toast } from "sonner"
import { FuelSwatch, RiskBar } from "@/components/fuel"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { type Alert as AlertT, type Card, type Status, api, fmtHours, fmtL, fuelName, pretty, simClock, usePoll } from "@/lib/api"
import { Waiting } from "./Overview"

export function Recommendations({ status }: { status: Status | null }) {
  const { data, error, reload } = usePoll<{ cards: Card[]; source: string; mode: string; tick: number }>("/api/recommendations", 1000)
  const { data: alerts } = usePoll<{ alerts: AlertT[] }>("/api/alerts", 2000)
  if (!data) return <Waiting error={error} />
  const actionable = data.cards.filter(c => c.allocations.length)
  const review = data.cards.filter(c => c.review_required).length
  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          {actionable.length} recommendation{actionable.length === 1 ? "" : "s"}, {review} waiting for your review.
          Planned by <strong className="text-foreground">{data.source}</strong>.
          {data.mode === "auto" && " Auto mode sends confident ones by itself; low-confidence ones wait here."}
          {data.mode === "observe" && " Observe mode: nothing is sent."}
        </p>
      </header>
      {alerts && alerts.alerts.length > 0 && (
        <section aria-labelledby="alerts" className="rounded-md border border-warn/40 bg-card">
          <h2 id="alerts" className="border-b px-4 py-2 text-sm font-semibold">Detected now</h2>
          <ul className="divide-y text-sm">{alerts.alerts.map((a, i) => (
            <li key={i} className="px-4 py-2">
              <span className={a.severity === "critical" ? "font-semibold text-alarm" : "font-semibold text-warn"}>{a.kind.replace("_", " ")}</span>
              {a.station_id && <span className="ml-2">{pretty(a.station_id)}{a.fuel ? ` ${fuelName(a.fuel).toLowerCase()}` : ""}</span>}
              {a.depot_id && <span className="ml-2">{pretty(a.depot_id)}</span>}
              <span className="ml-2 text-muted-foreground">{a.detail}</span>
            </li>))}</ul>
        </section>
      )}
      {data.cards.length === 0
        ? <p className="rounded-md border bg-card px-4 py-6 text-center text-sm text-muted-foreground">No station is at risk in the next 12 hours. Nothing to approve.</p>
        : <div className="grid gap-4 2xl:grid-cols-2">{data.cards.map(c =>
          <RecommendationCard key={c.id} card={c} mode={status?.mode ?? data.mode} tickMinutes={status?.tick_minutes ?? 15} onDone={reload} />)}</div>}
    </div>
  )
}

function RecommendationCard({ card: c, mode, tickMinutes, onDone }: { card: Card; mode: string; tickMinutes: number; onDone: () => void }) {
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null)
  const total = c.allocations.reduce((s, a) => s + a.liters, 0)
  const title = c.before.stockout_hours != null
    ? `${c.station} ${fuelName(c.fuel).toLowerCase()} runs out in about ${fmtHours(c.before.stockout_hours)}`
    : `${c.station} ${fuelName(c.fuel).toLowerCase()} has a ${Math.round(c.before.risk * 100)}% stockout risk`
  const act = async (kind: "approve" | "reject") => {
    setBusy(kind)
    try {
      if (kind === "approve") {
        const r = await api<{ liters_accepted: number }>(`/api/recommendations/${encodeURIComponent(c.id)}/approve`, { method: "POST" })
        r.liters_accepted > 0 ? toast.success(`Sent ${fmtL(r.liters_accepted)} to ${c.station}`)
          : toast.warning("Nothing was sent: the simulator rejected it or limits changed. See Decisions.")
      } else {
        await api(`/api/recommendations/${encodeURIComponent(c.id)}/reject`, { method: "POST" })
        toast(`Rejected; ${c.station} ${fuelName(c.fuel).toLowerCase()} recorded in decision history`)
      }
      onDone()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e))
    } finally { setBusy(null) }
  }
  return (
    <article className="rounded-md border bg-card" aria-labelledby={`t-${c.id}`}>
      <header className="flex flex-wrap items-start justify-between gap-2 border-b px-4 py-3">
        <div>
          <h3 id={`t-${c.id}`} className="flex items-center gap-2 text-base font-semibold"><FuelSwatch fuel={c.fuel} />{title}</h3>
          <p className="text-xs text-muted-foreground">
            {fmtL(c.inventory)} of {fmtL(c.capacity)} in the tank, {fmtL(c.incoming)} on the way, {fmtL(c.before.expected_demand)} expected demand in 12 h
          </p>
        </div>
        {c.review_required
          ? <Badge variant="outline" className="border-warn text-warn">Needs your review</Badge>
          : <Badge variant="secondary">Confident</Badge>}
      </header>

      <div className="grid gap-4 px-4 py-3 md:grid-cols-2">
        <div className="space-y-3">
          <section>
            <h4 className="text-xs font-semibold text-muted-foreground">Why</h4>
            <p className="text-sm">{c.why}</p>
            {c.signals.length > 0 && <ul className="mt-1 flex flex-wrap gap-1.5">{c.signals.map(s => <li key={s}><Badge variant="outline">{s}</Badge></li>)}</ul>}
          </section>
          <section>
            <h4 className="text-xs font-semibold text-muted-foreground">Recommendation</h4>
            {c.allocations.length === 0
              ? <p className="text-sm font-medium text-alarm">{c.alternatives.length > 0 && c.alternatives.every(a => !a.usable)
                  ? "No shipment possible: every route to this station is disrupted."
                  : "No shipment in the current plan. The planner found nothing it can send here now (depot stock, dispatch capacity, tank space, or fuel needed elsewhere)."}</p>
              : <ul className="space-y-1 text-sm">{c.allocations.map(a => (
                <li key={a.route_id}>
                  Send <strong>{fmtL(a.liters)}</strong> from {pretty(a.depot_id)} via {pretty(a.route_id)}
                  <span className="text-muted-foreground">, arrives {simClock(a.arrival_tick, tickMinutes)} ({a.requests} request{a.requests === 1 ? "" : "s"})</span>
                </li>))}</ul>}
          </section>
        </div>
        <div className="space-y-3">
          <section>
            <h4 className="mb-1 text-xs font-semibold text-muted-foreground">Expected impact within 12 h</h4>
            <RiskBar label="Now" value={c.before.risk} />
            {c.after && <RiskBar label="If sent" value={c.after.risk} />}
            <p className="mt-1 text-xs text-muted-foreground">
              Unmet {fmtL(c.before.unmet)}{c.after && <> → {fmtL(c.after.unmet)}</>}; stockout {fmtHours(c.before.stockout_hours)}{c.after && <> → {fmtHours(c.after.stockout_hours)}</>}
            </p>
          </section>
          <section>
            <h4 className="text-xs font-semibold text-muted-foreground">Confidence {Math.round(c.confidence * 100)}%</h4>
            <p className="text-xs text-muted-foreground">
              Demand varies ±{(c.noise_sigma * 100).toFixed(1)}% per tick{c.noise_rows ? `, measured from ${c.noise_rows} observations` : ", from the published profile (no history yet)"}.
              {c.confidence < 0.5 && " Too uncertain to send automatically."}
            </p>
          </section>
        </div>
      </div>

      <details className="border-t px-4 py-2 text-sm">
        <summary className="cursor-pointer text-muted-foreground">Constraints and alternatives</summary>
        <div className="mt-2 grid gap-4 md:grid-cols-2">
          <div>{c.allocations.map(a => (
            <dl key={a.route_id} className="text-xs">
              {Object.entries(a.limits).map(([k, v]) => (
                <div key={k} className="flex justify-between py-0.5">
                  <dt className={a.binding === k ? "font-semibold" : "text-muted-foreground"}>{k}{a.binding === k && " (limits this shipment)"}</dt>
                  <dd>{fmtL(v)}</dd>
                </div>))}
            </dl>))}</div>
          <ul className="space-y-1 text-xs">{c.alternatives.length === 0
            ? <li className="text-muted-foreground">No other route reaches this station.</li>
            : c.alternatives.map(a => (
              <li key={a.route_id}>
                {pretty(a.route_id)}: {a.usable
                  ? <>risk would be {a.risk_after != null ? `${Math.round(a.risk_after * 100)}%` : "—"}, {a.transit_ticks} ticks in transit, {fmtL(a.depot_stock)} at the depot</>
                  : <span className="text-alarm">{a.reason}</span>}
              </li>))}</ul>
        </div>
      </details>

      <footer className="flex items-center justify-end gap-2 border-t px-4 py-2.5">
        {mode === "observe" && <span className="mr-auto text-xs text-muted-foreground">Switch to manual or auto mode to act.</span>}
        <Button variant="ghost" disabled={busy !== null || mode === "observe"} onClick={() => act("reject")}>{busy === "reject" ? "Rejecting…" : "Reject"}</Button>
        <Button disabled={busy !== null || mode === "observe" || c.allocations.length === 0} onClick={() => act("approve")}>
          {busy === "approve" ? "Sending…" : `Approve and send ${total ? fmtL(total) : ""}`}
        </Button>
      </footer>
    </article>
  )
}
