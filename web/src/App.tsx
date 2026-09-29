import { useEffect, useState } from "react"
import { Activity, ClipboardList, Gauge, History, Siren } from "lucide-react"
import { toast } from "sonner"
import { Toaster } from "@/components/ui/sonner"
import { type Card, type Status, api, simClock, usePoll } from "@/lib/api"
import { cn } from "@/lib/utils"
import { Decisions } from "@/views/Decisions"
import { Health } from "@/views/Health"
import { Incidents } from "@/views/Incidents"
import { Overview } from "@/views/Overview"
import { Recommendations } from "@/views/Recommendations"

const VIEWS = [
  { id: "overview", label: "Overview", icon: Gauge },
  { id: "recommendations", label: "Recommendations", icon: ClipboardList },
  { id: "decisions", label: "Decisions", icon: History },
  { id: "incidents", label: "Incidents and lab", icon: Siren },
  { id: "health", label: "System health", icon: Activity },
] as const
type ViewId = (typeof VIEWS)[number]["id"]

const MODE_TEXT = { observe: "Observe", manual: "Manual approval", auto: "Auto" } as const

function useHashView(): [ViewId, (v: ViewId) => void] {
  const read = () => (VIEWS.find(v => `#${v.id}` === window.location.hash)?.id ?? "overview") as ViewId
  const [view, setView] = useState<ViewId>(read)
  useEffect(() => {
    const on = () => setView(read())
    window.addEventListener("hashchange", on)
    return () => window.removeEventListener("hashchange", on)
  }, [])
  return [view, v => { window.location.hash = v }]
}

export default function App() {
  const [view, go] = useHashView()
  const { data: status, error, reload } = usePoll<Status>("/api/status", 1000)
  const { data: recs } = usePoll<{ cards: Card[] }>("/api/recommendations", 2000)
  const open = recs?.cards.filter(c => c.allocations.length).length ?? 0
  const tm = status?.tick_minutes ?? 15
  const title = VIEWS.find(v => v.id === view)!.label

  const setMode = async (mode: string) => {
    try { await api("/api/operating-mode", { method: "PUT", body: JSON.stringify({ mode }) }); reload() }
    catch (e) { toast.error(e instanceof Error ? e.message : String(e)) }
  }
  const setPolicy = async (policy: string) => {
    try { await api("/api/policy", { method: "PUT", body: JSON.stringify({ policy }) }); reload(); toast(`Planner switched to ${policy}`) }
    catch (e) { toast.error(e instanceof Error ? e.message : String(e)) }
  }

  return (
    <div className="min-h-dvh md:grid md:grid-cols-[13.5rem_1fr]">
      <nav aria-label="Main" className="bg-sidebar text-sidebar-foreground md:sticky md:top-0 md:h-dvh">
        <div className="px-5 pb-4 pt-5">
          <div className="font-heading text-xl font-bold leading-none text-white">Fuel Operations</div>
          <div className="mt-1 text-xs text-sidebar-foreground/70">Bangladesh supply network</div>
        </div>
        <ul className="flex gap-1 overflow-x-auto px-2 pb-2 md:block md:space-y-0.5 md:overflow-visible">
          {VIEWS.map(v => (
            <li key={v.id}>
              <a href={`#${v.id}`} onClick={e => { e.preventDefault(); go(v.id) }} aria-current={view === v.id ? "page" : undefined}
                className={cn("flex items-center gap-2.5 whitespace-nowrap rounded-md px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring",
                  view === v.id ? "bg-sidebar-accent text-white" : "hover:bg-sidebar-accent/60")}>
                <v.icon className="size-4" aria-hidden />
                <span>{v.label}</span>
                {v.id === "recommendations" && open > 0 && <span className="ml-auto rounded-full bg-white px-1.5 text-xs font-semibold text-ink">{open}</span>}
              </a>
            </li>))}
        </ul>
      </nav>

      <div className="min-w-0">
        <header className="flex flex-wrap items-center gap-x-6 gap-y-3 border-b bg-card px-4 py-3 md:px-8">
          <div>
            <h1 className="text-2xl font-semibold leading-tight">{title}</h1>
            <p className="text-sm text-muted-foreground">
              {status ? <>Simulated time {simClock(status.tick, tm)} (tick {status.tick ?? "—"}), simulator {status.sim_status?.toLowerCase() ?? "unknown"}</> : "Connecting…"}
            </p>
          </div>
          {status && (
            <div className="ml-auto flex flex-wrap items-center gap-4">
              <fieldset className="flex items-center gap-2">
                <legend className="sr-only">Operating mode</legend>
                <span className="text-sm text-muted-foreground">Mode</span>
                <div className="flex rounded-md border bg-background p-0.5">
                  {(["observe", "manual", "auto"] as const).map(m => (
                    <label key={m} className={cn("cursor-pointer rounded px-2.5 py-1 text-sm has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring",
                      status.mode === m ? "bg-ink text-white" : "hover:bg-muted")}>
                      <input type="radio" name="mode" value={m} checked={status.mode === m} onChange={() => setMode(m)} className="sr-only" />
                      {MODE_TEXT[m]}
                    </label>))}
                </div>
              </fieldset>
              <label className="flex items-center gap-2 text-sm">
                <span className="text-muted-foreground">Planner</span>
                <select value={status.policy} onChange={e => setPolicy(e.target.value)} className="rounded-md border bg-background px-2 py-1">
                  {status.policies.filter(p => p !== "none").map(p => <option key={p} value={p}>{p}</option>)}
                </select>
              </label>
            </div>
          )}
        </header>

        {error && !status && <Banner tone="alarm">Backend unreachable: {error}. Retrying every second.</Banner>}
        {error && status && <Banner tone="alarm">Backend not responding. Showing the last known values; retrying.</Banner>}
        {status?.degraded && <Banner tone="warn">Simulator unreachable. Showing data from {Math.round(status.snapshot_age_s ?? 0)} s ago; nothing is sent until it is back.</Banner>}
        {status && !status.intelligence_enabled && <Banner tone="warn">Prediction and optimizer are off. The fallback rule policy is allocating fuel until they are back.</Banner>}

        <main className="px-4 py-6 md:px-8">
          {view === "overview" && <Overview />}
          {view === "recommendations" && <Recommendations status={status} />}
          {view === "decisions" && <Decisions tickMinutes={tm} />}
          {view === "incidents" && <Incidents status={status} onChanged={reload} />}
          {view === "health" && <Health />}
        </main>
      </div>
      <Toaster position="bottom-right" />
    </div>
  )
}

function Banner({ tone, children }: { tone: "warn" | "alarm"; children: React.ReactNode }) {
  return (
    <div role="status" className={cn("border-b px-4 py-2 text-sm font-medium md:px-8",
      tone === "alarm" ? "border-alarm/30 bg-alarm/10 text-alarm" : "border-warn/30 bg-warn/10 text-warn")}>
      {children}
    </div>
  )
}
