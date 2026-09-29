import { useState } from "react"
import { toast } from "sonner"
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { type Incident, type Status, api, getToken, setToken, simClock, usePoll } from "@/lib/api"

const KIND_TEXT: Record<string, string> = {
  run: "Run", degraded: "Simulator unreachable", recovered: "Recovered", alert: "Detected", fallback: "Fallback",
  invalid_response: "Rejected data", stale_flag: "Stale flag", lab: "Lab", mode: "Mode", policy: "Planner",
  intelligence: "Intelligence", error: "Error", replan: "Replanned",
}
const KIND_COLOR: Record<string, string> = {
  degraded: "text-alarm", invalid_response: "text-alarm", error: "text-alarm", fallback: "text-warn", alert: "text-warn",
  recovered: "text-ok", intelligence: "text-warn",
}

const TARGETS: Record<string, { key: string; options: string[] }> = {
  demand_spike: { key: "station_ids", options: ["station-mirpur", "station-tongi", "station-karnaphuli", "station-coxsbazar"] },
  station_outage: { key: "station_ids", options: ["station-mirpur", "station-tongi", "station-karnaphuli", "station-coxsbazar"] },
  route_disruption: { key: "route_ids", options: ["route-gazipur-mirpur", "route-gazipur-tongi", "route-patiya-karnaphuli", "route-patiya-coxsbazar", "route-gazipur-karnaphuli", "route-patiya-mirpur"] },
  depot_constraint: { key: "depot_ids", options: ["depot-gazipur", "depot-patiya"] },
  shipment_delay: { key: "depot_ids", options: ["depot-gazipur", "depot-patiya"] },
  supply_shortfall: { key: "depot_ids", options: ["depot-gazipur", "depot-patiya"] },
}

export function Incidents({ status, onChanged }: { status: Status | null; onChanged: () => void }) {
  const { data } = usePoll<Incident[]>("/api/incidents", 1500)
  const tm = status?.tick_minutes ?? 15
  return (
    <div className="grid gap-8 xl:grid-cols-[3fr_2fr]">
      <section aria-labelledby="timeline">
        <h2 id="timeline" className="mb-1 text-lg font-semibold">What happened</h2>
        <p className="mb-3 text-sm text-muted-foreground">Detections, failures, fallbacks and recoveries, newest first.</p>
        {!data?.length
          ? <p className="rounded-md border bg-card px-4 py-6 text-center text-sm text-muted-foreground">Nothing has happened yet.</p>
          : <ol className="divide-y rounded-md border bg-card text-sm">{data.slice(0, 120).map((i, n) => (
            <li key={n} className="grid grid-cols-[6.5rem_8.5rem_1fr] gap-2 px-4 py-2">
              <span className="text-muted-foreground">{i.tick != null ? simClock(i.tick, tm) : new Date(i.wall * 1000).toLocaleTimeString()}</span>
              <span className={`font-semibold ${KIND_COLOR[i.kind] ?? ""}`}>{KIND_TEXT[i.kind] ?? i.kind}</span>
              <span className="break-words">{i.detail}</span>
            </li>))}</ol>}
      </section>
      <Lab status={status} onChanged={onChanged} />
    </div>
  )
}

function Lab({ status, onChanged }: { status: Status | null; onChanged: () => void }) {
  const [token, setTok] = useState(getToken())
  const [type, setType] = useState("demand_spike")
  const [target, setTarget] = useState("station-mirpur")
  const [duration, setDuration] = useState(40)
  const [value, setValue] = useState(1.8)
  const [fault, setFault] = useState("unavailable")
  const [faultSecs, setFaultSecs] = useState(15)
  const call = async (path: string, body?: unknown, method = "POST") => {
    try {
      await api(path, { method, body: body ? JSON.stringify(body) : undefined })
      onChanged()
      return true
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e))
      return false
    }
  }
  const injectEvent = async () => {
    const t = TARGETS[type]
    const params: Record<string, unknown> = { [t.key]: [target] }
    if (type === "demand_spike") params.multiplier = value
    if (type === "shipment_delay") params.delay_ticks = Math.round(value)
    if (type === "supply_shortfall") params.factor = value
    if (await call("/api/lab/events", { type, duration_ticks: duration, parameters: params }))
      toast.success(`Injected ${type.replace("_", " ")} at ${target.replace(/^\w+-/, "")}`)
  }
  const valueLabel = type === "demand_spike" ? "Multiplier" : type === "shipment_delay" ? "Delay (ticks)" : type === "supply_shortfall" ? "Factor" : null
  return (
    <section aria-labelledby="lab" className="space-y-6">
      <div>
        <h2 id="lab" className="text-lg font-semibold">Lab</h2>
        <p className="text-sm text-muted-foreground">Create crises and failures to watch the system detect, respond and recover. Uses simulator test controls only.</p>
      </div>
      {status?.token_required && (
        <div className="space-y-1.5">
          <Label htmlFor="token">Operator token</Label>
          <Input id="token" type="password" value={token} autoComplete="off"
            onChange={e => { setTok(e.target.value); setToken(e.target.value) }} placeholder="Needed for lab, mode and planner changes" />
        </div>
      )}

      <fieldset className="space-y-2 rounded-md border bg-card p-4">
        <legend className="px-1 text-sm font-semibold">Simulator clock</legend>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => call("/api/lab/control", { action: "run" })}>Run</Button>
          <Button variant="outline" onClick={() => call("/api/lab/control", { action: "pause" })}>Pause</Button>
          <Button variant="outline" onClick={() => call("/api/lab/control", { action: "step" })}>Step one tick</Button>
          <AlertDialog>
            <AlertDialogTrigger render={<Button variant="destructive" className="ml-auto" />}>Reset simulation</AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Reset the simulation?</AlertDialogTitle>
                <AlertDialogDescription>All simulator state returns to tick 0 and its shipments are erased. Decision history in this app is kept.</AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Keep running</AlertDialogCancel>
                <AlertDialogAction variant="destructive" onClick={() => call("/api/lab/control", { action: "reset" })}>Reset simulation</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      </fieldset>

      <fieldset className="space-y-3 rounded-md border bg-card p-4">
        <legend className="px-1 text-sm font-semibold">Crisis event</legend>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="space-y-1 text-sm">Type
            <select className="w-full rounded-md border bg-background px-2 py-1.5" value={type}
              onChange={e => { setType(e.target.value); setTarget(TARGETS[e.target.value].options[0]); setValue(e.target.value === "supply_shortfall" ? 0.5 : e.target.value === "shipment_delay" ? 12 : 1.8) }}>
              {Object.keys(TARGETS).map(t => <option key={t} value={t}>{t.replace("_", " ")}</option>)}
            </select>
          </label>
          <label className="space-y-1 text-sm">Where
            <select className="w-full rounded-md border bg-background px-2 py-1.5" value={target} onChange={e => setTarget(e.target.value)}>
              {TARGETS[type].options.map(o => <option key={o} value={o}>{o.replace(/^\w+-/, "").replace("-", " to ")}</option>)}
            </select>
          </label>
          <label className="space-y-1 text-sm">Duration (ticks)
            <Input type="number" min={1} max={2000} value={duration} onChange={e => setDuration(Number(e.target.value))} />
          </label>
          {valueLabel && <label className="space-y-1 text-sm">{valueLabel}
            <Input type="number" step="0.1" value={value} onChange={e => setValue(Number(e.target.value))} />
          </label>}
        </div>
        <Button onClick={injectEvent}>Start this crisis now</Button>
      </fieldset>

      <fieldset className="space-y-3 rounded-md border bg-card p-4">
        <legend className="px-1 text-sm font-semibold">Software failure</legend>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="space-y-1 text-sm">Fault
            <select className="w-full rounded-md border bg-background px-2 py-1.5" value={fault} onChange={e => setFault(e.target.value)}>
              {["unavailable", "latency", "error_rate", "stale_data", "stream_disconnect"].map(f => <option key={f} value={f}>{f.replace("_", " ")}</option>)}
            </select>
          </label>
          <label className="space-y-1 text-sm">Seconds
            <Input type="number" min={1} max={3600} value={faultSecs} onChange={e => setFaultSecs(Number(e.target.value))} />
          </label>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button onClick={async () => { if (await call("/api/lab/faults", { type: fault, duration_seconds: faultSecs })) toast.success(`Injected ${fault} for ${faultSecs}s`) }}>Inject failure</Button>
          <Button variant="outline" onClick={() => call("/api/lab/faults/clear")}>Clear failures</Button>
        </div>
        <div className="flex items-center justify-between gap-4 border-t pt-3">
          <Label htmlFor="intel" className="text-sm font-normal">
            Prediction and optimizer {status?.intelligence_enabled ? "running" : "switched off (fallback rules in use)"}
          </Label>
          <Switch id="intel" checked={status?.intelligence_enabled ?? true}
            onCheckedChange={(v: boolean) => call("/api/intelligence", { enabled: v }, "PUT")} />
        </div>
      </fieldset>
    </section>
  )
}
