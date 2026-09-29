import { useState } from "react"
import { CheckCircle2, CircleX, TriangleAlert } from "lucide-react"
import { toast } from "sonner"
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import { type Health, type Incident, type Status, api, getToken, setToken, usePoll } from "@/lib/api"
import { clock, stationName } from "@/lib/text"
import { cn } from "@/lib/utils"
import { Loading, Panel } from "./parts"

const PARTS: Record<string, [string, string]> = {
  backend_api: ["App server", "Runs this page and the planning"],
  database: ["Decision history", "Stores every decision"],
  simulator: ["Fuel simulator", "The fuel network we operate"],
  prediction_service: ["Forecasting", "Predicts when tanks run out"],
  decision_engine: ["Planner", "Works out what to send where"],
}
export const PLANNERS: Record<string, string> = {
  "lp-buffer": "Smart plan with safety stock (recommended)",
  lp: "Smart plan, no safety stock",
  threshold: "Simple refill rule (backup)",
}

export function System({ status, onChanged }: { status: Status | null; onChanged: () => void }) {
  const { data: health, error } = usePoll<Health>("/api/health", 2000)
  const { data: events } = usePoll<Incident[]>("/api/incidents", 2000)
  if (!health) return <Loading error={error} />
  const ok = health.status === "healthy"
  const tm = status?.tick_minutes ?? 15

  return (
    <div className="grid gap-5 xl:grid-cols-[3fr_2fr]">
      <div className="space-y-5">
        <Panel className="flex items-center gap-4 px-5 py-4">
          {ok ? <CheckCircle2 className="size-8 text-ok" aria-hidden /> : <TriangleAlert className="size-8 text-warn" aria-hidden />}
          <div>
            <p className="text-xl font-semibold">{ok ? "All parts are working" : "Some parts have problems"}</p>
            <p className="text-base text-muted-foreground">
              {health.p95_latency_ms != null ? `Pages answer in ${health.p95_latency_ms < 1000 ? `${Math.round(health.p95_latency_ms)} ms` : `${(health.p95_latency_ms / 1000).toFixed(1)} s`} or less (95% of requests)` : "No traffic measured yet"}
              {`, ${(health.error_rate * 100).toFixed(1)}% errors.`}
            </p>
          </div>
        </Panel>

        <Panel title="Parts of the system">
          <ul className="divide-y">{Object.entries(health.components).map(([k, c]) => {
            const [name, what] = PARTS[k] ?? [k, ""]
            return (
              <li key={k} className="flex items-center justify-between gap-3 px-5 py-3">
                <div>
                  <div className="text-base font-semibold">{name}</div>
                  <div className="text-sm text-muted-foreground">{partNote(k, c) || what}</div>
                </div>
                <PartStatus status={c.status} />
              </li>)
          })}</ul>
        </Panel>

        <Panel title="What happened recently">
          {!events?.length
            ? <p className="px-5 py-8 text-center text-base text-muted-foreground">Nothing has happened yet.</p>
            : <ul className="divide-y">{events.filter(e => e.kind !== "stale_flag").slice(0, 40).map((e, i) => {
              const t = eventText(e)
              return (
                <li key={i} className="grid grid-cols-[7rem_1fr] gap-3 px-5 py-2.5 text-base">
                  <span className="text-sm text-muted-foreground">{e.tick != null ? clock(e.tick, tm) : new Date(e.wall * 1000).toLocaleTimeString()}</span>
                  <span className={t.tone === "bad" ? "text-alarm" : t.tone === "good" ? "text-ok" : t.tone === "warn" ? "text-warn" : ""}>{t.text}</span>
                </li>)
            })}</ul>}
        </Panel>
      </div>

      <div className="space-y-5">
        <Settings status={status} onChanged={onChanged} />
        <TestTools status={status} onChanged={onChanged} />
      </div>
    </div>
  )
}

function PartStatus({ status }: { status: string }) {
  const [Icon, text, color] = status === "healthy" ? [CheckCircle2, "Working", "text-ok"]
    : status === "degraded" ? [TriangleAlert, "Problem", "text-warn"] : [CircleX, "Down", "text-alarm"]
  return <span className={cn("flex items-center gap-1.5 text-base font-semibold", color)}><Icon className="size-5" aria-hidden />{text}</span>
}

function partNote(k: string, c: Record<string, unknown>) {
  if (k === "simulator" && c.status === "down") return "Cannot be reached; showing the last known data"
  if (k === "simulator" && c.state) return c.state === "PAUSED" ? "Paused (the clock is stopped)" : "Running"
  if (k === "prediction_service" && c.status !== "healthy") return "Switched off; the simple refill rule is used instead"
  if (k === "decision_engine" && typeof c.source === "string" && c.source.includes("fallback")) return "Using the simple refill rule (backup)"
  return ""
}

function eventText(e: Incident): { tone: "bad" | "good" | "warn" | "plain"; text: string } {
  const d = e.detail
  switch (e.kind) {
    case "degraded": return { tone: "bad", text: "Lost contact with the fuel simulator. Showing the last known data." }
    case "recovered": return { tone: "good", text: "Contact with the fuel simulator is back." }
    case "invalid_response": return { tone: "bad", text: "The simulator sent impossible data; it was ignored." }
    case "fallback": return { tone: "warn", text: "The smart planner failed; the simple refill rule took over." }
    case "intelligence": return d.startsWith("enabled") ? { tone: "good", text: "Smart planning switched on." } : { tone: "warn", text: "Smart planning switched off; the simple refill rule took over." }
    case "replan": return { tone: "plain", text: "Conditions changed, so the plan was made again." }
    case "run": return { tone: "plain", text: d.includes("reset") ? "The simulation was restarted from the beginning." : "Operations started." }
    case "mode": return { tone: "plain", text: `Sending mode changed to "${MODE_NAMES[d.split("→ ")[1]?.trim()] ?? d}".` }
    case "policy": return { tone: "plain", text: `Planning method changed to "${PLANNERS[d.split("→ ")[1]?.trim()] ?? d}".` }
    case "alert": {
      const m = d.match(/^anomalous_demand: Demand ([\d.]+)×/)
      if (m) return { tone: "warn", text: `Unusual demand detected: ${Number(m[1]).toFixed(1)}× normal.` }
      if (d.startsWith("disruption:")) return { tone: "warn", text: `New problem: ${d.replace("disruption: ", "").replace(/_/g, " ").replace(/\{.*$/, "").trim()}.` }
      if (d.startsWith("bottleneck")) return { tone: "warn", text: "A depot is sending at full capacity." }
      return { tone: "warn", text: d.replace(/_/g, " ") }
    }
    case "lab": return { tone: "plain", text: `Test tool: ${d.replace("event injected: ", "created ").replace("fault injected: ", "simulated failure ").replace(/_/g, " ").replace(/\{.*?\}/, "").replace(/station-\w+/g, s => stationName(s))}` }
    case "error": return { tone: "bad", text: "The planner hit an error and will retry." }
    default: return { tone: "plain", text: d }
  }
}

const MODE_NAMES: Record<string, string> = { observe: "View only", manual: "I approve", auto: "Automatic" }

async function call(path: string, body: unknown, method = "POST") {
  try {
    await api(path, { method, body: body === undefined ? undefined : JSON.stringify(body) })
    return true
  } catch (e) {
    toast.error(e instanceof Error ? e.message : String(e))
    return false
  }
}

function Settings({ status, onChanged }: { status: Status | null; onChanged: () => void }) {
  return (
    <Panel title="Settings">
      <div className="space-y-4 px-5 py-4">
        <label className="block space-y-1.5 text-base">
          <span className="font-medium">Planning method</span>
          <select className="w-full rounded-md border bg-background px-3 py-2" value={status?.policy ?? "lp-buffer"}
            onChange={async e => { if (await call("/api/policy", { policy: e.target.value }, "PUT")) { toast(`Planning method: ${PLANNERS[e.target.value]}`); onChanged() } }}>
            {Object.entries(PLANNERS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="text-base font-medium">Smart planning</div>
            <div className="text-sm text-muted-foreground">Turn off to test the backup rule (as if forecasting failed)</div>
          </div>
          <Switch checked={status?.intelligence_enabled ?? true} aria-label="Smart planning"
            onCheckedChange={async (v: boolean) => { if (await call("/api/intelligence", { enabled: v }, "PUT")) onChanged() }} />
        </div>
      </div>
    </Panel>
  )
}

const PROBLEMS: Record<string, { label: string; key: string; options: [string, string][]; extra?: { name: string; label: string; value: number } }> = {
  demand_spike: { label: "Demand surge at a station", key: "station_ids", options: [["station-mirpur", "Mirpur"], ["station-tongi", "Tongi"], ["station-karnaphuli", "Karnaphuli"], ["station-coxsbazar", "Cox's Bazar"]], extra: { name: "multiplier", label: "How many times normal", value: 2 } },
  route_disruption: { label: "Close a road", key: "route_ids", options: [["route-gazipur-mirpur", "Gazipur → Mirpur"], ["route-gazipur-tongi", "Gazipur → Tongi"], ["route-patiya-karnaphuli", "Patiya → Karnaphuli"], ["route-patiya-coxsbazar", "Patiya → Cox's Bazar"], ["route-gazipur-karnaphuli", "Gazipur → Karnaphuli"], ["route-patiya-mirpur", "Patiya → Mirpur"]] },
  station_outage: { label: "Close a station", key: "station_ids", options: [["station-mirpur", "Mirpur"], ["station-tongi", "Tongi"], ["station-karnaphuli", "Karnaphuli"], ["station-coxsbazar", "Cox's Bazar"]] },
  supply_shortfall: { label: "Cut depot supply", key: "depot_ids", options: [["depot-gazipur", "Gazipur"], ["depot-patiya", "Patiya"]], extra: { name: "factor", label: "Share still delivered (0–1)", value: 0.5 } },
  shipment_delay: { label: "Delay depot supply", key: "depot_ids", options: [["depot-gazipur", "Gazipur"], ["depot-patiya", "Patiya"]], extra: { name: "delay_ticks", label: "Delay in 15-minute steps", value: 12 } },
}
const FAILURES: [string, string][] = [["unavailable", "Simulator stops answering"], ["latency", "Simulator becomes slow"], ["error_rate", "Simulator gives random errors"]]

function TestTools({ status, onChanged }: { status: Status | null; onChanged: () => void }) {
  const [token, setTok] = useState(getToken())
  const [kind, setKind] = useState("demand_spike")
  const [where, setWhere] = useState(PROBLEMS.demand_spike.options[0][0])
  const [hours, setHours] = useState(12)
  const [extra, setExtra] = useState(2)
  const [failure, setFailure] = useState("unavailable")
  const [secs, setSecs] = useState(15)
  const p = PROBLEMS[kind]
  const tm = status?.tick_minutes ?? 15

  return (
    <details className="rounded-lg border bg-card" open={false}>
      <summary className="cursor-pointer px-5 py-3 text-lg font-semibold">Test tools (for demos)</summary>
      <div className="space-y-5 border-t px-5 py-4 text-base">
        {status?.token_required && (
          <label className="block space-y-1.5"><span className="font-medium">Operator password</span>
            <Input type="password" value={token} autoComplete="off" onChange={e => { setTok(e.target.value); setToken(e.target.value) }} />
          </label>
        )}

        <fieldset className="space-y-2">
          <legend className="font-semibold">Simulation clock</legend>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => call("/api/lab/control", { action: "run" }).then(onChanged)}>Start</Button>
            <Button variant="outline" onClick={() => call("/api/lab/control", { action: "pause" }).then(onChanged)}>Pause</Button>
            <Button variant="outline" onClick={() => call("/api/lab/control", { action: "step" }).then(onChanged)}>Forward 15 min</Button>
            <AlertDialog>
              <AlertDialogTrigger render={<Button variant="destructive" />}>Restart simulation</AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Restart the simulation from Day 1?</AlertDialogTitle>
                  <AlertDialogDescription>All tanks, depots and shipments go back to the start. Your decision history in this app is kept.</AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction variant="destructive" onClick={() => call("/api/lab/control", { action: "reset" }).then(onChanged)}>Restart</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        </fieldset>

        <fieldset className="space-y-2">
          <legend className="font-semibold">Create a problem</legend>
          <select className="w-full rounded-md border bg-background px-3 py-2" value={kind}
            onChange={e => { const k = e.target.value; setKind(k); setWhere(PROBLEMS[k].options[0][0]); setExtra(PROBLEMS[k].extra?.value ?? 0) }}>
            {Object.entries(PROBLEMS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
          </select>
          <div className="grid gap-2 sm:grid-cols-2">
            <label className="space-y-1"><span className="text-sm text-muted-foreground">Where</span>
              <select className="w-full rounded-md border bg-background px-3 py-2" value={where} onChange={e => setWhere(e.target.value)}>
                {p.options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </label>
            <label className="space-y-1"><span className="text-sm text-muted-foreground">For how many hours</span>
              <Input type="number" min={1} max={200} value={hours} onChange={e => setHours(Number(e.target.value))} />
            </label>
            {p.extra && <label className="space-y-1 sm:col-span-2"><span className="text-sm text-muted-foreground">{p.extra.label}</span>
              <Input type="number" step="0.1" value={extra} onChange={e => setExtra(Number(e.target.value))} />
            </label>}
          </div>
          <Button onClick={async () => {
            const params: Record<string, unknown> = { [p.key]: [where] }
            if (p.extra) params[p.extra.name] = p.extra.name === "delay_ticks" ? Math.round(extra) : extra
            if (await call("/api/lab/events", { type: kind, duration_ticks: Math.max(1, Math.round((hours * 60) / tm)), parameters: params })) {
              toast.success(`${p.label} started`); onChanged()
            }
          }}>Start this problem now</Button>
        </fieldset>

        <fieldset className="space-y-2">
          <legend className="font-semibold">Simulate a software failure</legend>
          <div className="grid gap-2 sm:grid-cols-[1fr_8rem]">
            <select className="rounded-md border bg-background px-3 py-2" value={failure} onChange={e => setFailure(e.target.value)}>
              {FAILURES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
            <label className="flex items-center gap-2"><Input type="number" min={1} max={3600} value={secs} onChange={e => setSecs(Number(e.target.value))} aria-label="Seconds" /><span className="text-sm">sec</span></label>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button onClick={async () => { if (await call("/api/lab/faults", { type: failure, duration_seconds: secs })) toast.success("Failure started") }}>Start failure</Button>
            <Button variant="outline" onClick={() => call("/api/lab/faults/clear", undefined)}>Stop all failures</Button>
          </div>
        </fieldset>
      </div>
    </details>
  )
}
