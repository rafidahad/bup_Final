import { useState } from "react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { type Card, type Status, api, usePoll } from "@/lib/api"
import { depotName, fuel, inTime, liters, roadName, stationName } from "@/lib/text"
import { cn } from "@/lib/utils"
import { FuelDot, Loading, Panel } from "./parts"

type Recs = { cards: Card[]; mode: string; tick: number }

const LIMIT: Record<string, string> = {
  "depot stock": "the depot stock", "dispatch budget this tick": "the depot sending limit", "destination headroom": "space in the tank",
}

export function Actions({ status }: { status: Status | null }) {
  const { data, error, reload } = usePoll<Recs>("/api/recommendations", 1000)
  const [sendingAll, setSendingAll] = useState(false)
  if (!data) return <Loading error={error} />
  const mode = status?.mode ?? data.mode
  const tm = status?.tick_minutes ?? 15
  const ready = data.cards.filter(c => c.allocations.length)
  const stuck = data.cards.filter(c => !c.allocations.length)
  const sure = ready.filter(c => !c.review_required)

  const sendAll = async () => {
    setSendingAll(true)
    let total = 0
    for (const c of sure) {
      try { total += (await approve(c)).liters_accepted } catch (e) { toast.error(e instanceof Error ? e.message : String(e)) }
    }
    setSendingAll(false)
    toast.success(`Sent ${liters(total)} in ${sure.length} shipment${sure.length === 1 ? "" : "s"}`)
    reload()
  }

  return (
    <div className="space-y-5">
      <Panel className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
        <p className="max-w-2xl text-base">
          {mode === "auto" && "Automatic sending is on. The system sends shipments by itself; only the ones it is not sure about wait here for you."}
          {mode === "manual" && (ready.length ? "These shipments are waiting for you. Read the reason, then press Send." : "No shipment is waiting for you.")}
          {mode === "observe" && "View only: nothing will be sent. Choose \"I approve\" at the top to send shipments."}
        </p>
        {mode === "manual" && sure.length > 1 &&
          <Button size="lg" disabled={sendingAll} onClick={sendAll}>{sendingAll ? "Sending…" : `Send all ${sure.length} checked shipments`}</Button>}
      </Panel>

      {ready.length === 0 && stuck.length === 0 && (
        <Panel className="px-5 py-10 text-center text-lg text-muted-foreground">All stations have enough fuel for the next 12 hours. Nothing to send.</Panel>
      )}

      <div className="grid gap-4 xl:grid-cols-2">
        {ready.map(c => <ActionCard key={c.id} card={c} mode={mode} tickMinutes={tm} onDone={reload} />)}
      </div>

      {stuck.length > 0 && (
        <Panel title="Short on fuel, but no shipment possible now">
          <ul className="divide-y">{stuck.map(c => (
            <li key={c.id} className="px-5 py-3 text-base">
              <span className="font-semibold"><FuelDot fuel={c.fuel} /> {stationName(c.station_id)} {fuel(c.fuel).toLowerCase()}</span>
              {c.before.stockout_hours != null && <span> runs out {inTime(c.before.stockout_hours)}.</span>}
              <span className="text-muted-foreground"> {stuckReason(c)}</span>
            </li>))}
          </ul>
        </Panel>
      )}
    </div>
  )
}

/** Approve exactly what is on screen; the server refuses (409) if the plan changed meanwhile. */
function approve(c: Card) {
  return api<{ liters_accepted: number }>(`/api/recommendations/${encodeURIComponent(c.id)}/approve`, {
    method: "POST", body: JSON.stringify({ allocations: c.allocations.map(a => ({ route_id: a.route_id, liters: a.liters })) }),
  })
}

function stuckReason(c: Card) {
  if (c.alternatives.length && c.alternatives.every(a => !a.usable)) return "Every road to this station is closed."
  if (c.inventory >= c.capacity * 0.95) return "The tank is full; more fuel would not fit."
  return "The depots cannot send more right now (stock or daily sending limit), or the fuel is needed more elsewhere. The plan is checked again automatically."
}

function ActionCard({ card: c, mode, tickMinutes, onDone }: { card: Card; mode: string; tickMinutes: number; onDone: () => void }) {
  const [busy, setBusy] = useState<"send" | "skip" | null>(null)
  const total = c.allocations.reduce((s, a) => s + a.liters, 0)
  const first = Math.min(...c.allocations.map(a => a.transit_ticks))
  const place = stationName(c.station_id)
  const f = fuel(c.fuel).toLowerCase()
  const before = c.before.stockout_hours

  const act = async (kind: "send" | "skip") => {
    setBusy(kind)
    try {
      if (kind === "send") {
        const r = await approve(c)
        if (r.liters_accepted > 0) toast.success(`Sent ${liters(r.liters_accepted)} ${f} to ${place}`)
        else toast.warning("Nothing was sent: limits changed a moment ago. The list will refresh with a new plan.")
      } else {
        await api(`/api/recommendations/${encodeURIComponent(c.id)}/reject`, { method: "POST" })
        toast(`Skipped. Saved in History.`)
      }
      onDone()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e))
    } finally { setBusy(null) }
  }

  return (
    <article className={cn("rounded-lg border bg-card", c.review_required && "border-warn/60")} aria-labelledby={`a-${c.id}`}>
      <div className="space-y-3 px-5 py-4">
        <div>
          <h3 id={`a-${c.id}`} className="flex items-center gap-2 text-xl font-semibold">
            <FuelDot fuel={c.fuel} /> Send {liters(total)} {f} to {place}
          </h3>
          <p className="text-base text-muted-foreground">
            From {[...new Set(c.allocations.map(a => depotName(a.depot_id)))].join(" and ")} depot, arrives {inTime((first * tickMinutes) / 60)}.
          </p>
        </div>

        <p className="text-base">
          <span className="font-semibold">Why: </span>
          {before == null
            ? c.before.risk < 0.2 ? `Tops up ${place}'s ${f} to keep a safety reserve for the next hours.` : `${place} may run short of ${f} within 12 hours if demand keeps changing.`
            : before <= 0.05 ? `${place} has no ${f} left right now.` : `${place} will run out of ${f} ${inTime(before)}.`}
          {c.signals.length > 0 && ` ${signalText(c)}`}
        </p>

        <div className="flex flex-wrap items-center gap-2 rounded-md bg-muted px-3 py-2 text-base">
          <span className="font-semibold">If sent:</span>
          <span>{ifSent(c, f, inTime((first * tickMinutes) / 60))}</span>
        </div>

        {c.review_required && (
          <p className="rounded-md border border-warn/50 bg-warn/10 px-3 py-2 text-base text-warn">
            Please check this one yourself: the system is not sure enough ({Math.round(c.confidence * 100)}% confident) because
            {c.signals.length ? " conditions are changing." : " it has little sales history yet."}
          </p>
        )}
      </div>

      <details className="border-t px-5 py-3 text-base">
        <summary className="cursor-pointer text-muted-foreground">More details</summary>
        <dl className="mt-3 grid gap-x-6 gap-y-1.5 sm:grid-cols-[auto_1fr]">
          <dt className="text-muted-foreground">In the tank now</dt><dd>{liters(c.inventory)} of {liters(c.capacity)}{c.incoming > 0 && `, ${liters(c.incoming)} already on the way`}</dd>
          <dt className="text-muted-foreground">Expected sales, next 12 h</dt><dd>{liters(c.before.expected_demand)}</dd>
          <dt className="text-muted-foreground">Shortage, next 12 h</dt><dd>{liters(c.before.unmet)} without this shipment{c.after && `, ${liters(c.after.unmet)} with it`}</dd>
          <dt className="text-muted-foreground">Chance of running out</dt><dd>{Math.round(c.before.risk * 100)}% now{c.after && `, ${Math.round(c.after.risk * 100)}% if sent`}</dd>
          <dt className="text-muted-foreground">How sure the system is</dt><dd>{Math.round(c.confidence * 100)}% (sales vary about ±{(c.noise_sigma * 100).toFixed(0)}%{c.noise_rows ? `, learned from ${c.noise_rows} sales records` : ", no sales history yet"})</dd>
          {c.allocations.map(a => (
            <FragmentRow key={a.route_id} label={`Road ${roadName(a.route_id)}`}
              value={`${liters(a.liters)}${a.binding ? `, limited by ${LIMIT[a.binding] ?? a.binding}` : ""}`} />))}
          {c.alternatives.map(a => (
            <FragmentRow key={a.route_id} label={`Other road ${roadName(a.route_id)}`}
              value={a.usable ? `possible, ${(a.transit_ticks * tickMinutes) / 60} h drive` : "closed"} />))}
          <dt className="text-muted-foreground">Planned by</dt><dd>{c.source.includes("fallback") ? "Simple refill rule (backup)" : "Smart planner"}</dd>
        </dl>
      </details>

      <footer className="flex items-center justify-end gap-2 border-t px-5 py-3">
        {mode === "observe" && <span className="mr-auto text-sm text-muted-foreground">View only: choose "I approve" at the top to send.</span>}
        <Button variant="ghost" size="lg" disabled={busy !== null || mode === "observe"} onClick={() => act("skip")}>{busy === "skip" ? "Skipping…" : "Skip"}</Button>
        <Button size="lg" disabled={busy !== null || mode === "observe"} onClick={() => act("send")}>{busy === "send" ? "Sending…" : "Send"}</Button>
      </footer>
    </article>
  )
}

function ifSent(c: Card, f: string, arrives: string) {
  const before = c.before.stockout_hours, after = c.after?.stockout_hours
  if (!c.after) return "—"
  if (after == null) return `enough ${f} for the next 12 hours`
  const shortage = `the shortage over the next 12 hours falls from ${liters(c.before.unmet)} to ${liters(c.after.unmet)}`
  if (before != null && before <= 0.05) return `the tank is refilled ${arrives}; ${shortage}`
  if (before != null && after > before + 0.1) return `fuel lasts until ${inTime(after).replace("in ", "")} from now instead of ${inTime(before).replace("in ", "")}; more shipments will follow`
  return shortage
}

function FragmentRow({ label, value }: { label: string; value: string }) {
  return <><dt className="text-muted-foreground">{label}</dt><dd>{value}</dd></>
}

function signalText(c: Card) {
  const parts: string[] = []
  for (const s of c.signals) {
    const m = s.match(/multiplier ×([\d.]+)/)
    if (m) parts.push(`Demand is ${Number(m[1]).toFixed(1)}× normal.`)
    else if (s.startsWith("route_disruption")) parts.push("A road is closed.")
    else if (s.startsWith("station")) parts.push("The station is closed.")
    else if (s.startsWith("depot_constraint")) parts.push("A depot is restricted.")
    else if (s.startsWith("shipment_delay") || s.startsWith("supply_shortfall")) parts.push("Depot supply is disrupted.")
  }
  return [...new Set(parts)].join(" ")
}
