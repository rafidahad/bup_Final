import { useEffect, useState } from "react"
import { History as HistoryIcon, House, Send, ServerCog } from "lucide-react"
import { toast } from "sonner"
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"
import { Toaster } from "@/components/ui/sonner"
import { type Card, type Status, api, usePoll } from "@/lib/api"
import { clock } from "@/lib/text"
import { cn } from "@/lib/utils"
import { Actions } from "@/views/Actions"
import { History } from "@/views/History"
import { Home } from "@/views/Home"
import { System } from "@/views/System"

const VIEWS = [
  { id: "home", label: "Home", icon: House, title: "Fuel network today" },
  { id: "actions", label: "Actions", icon: Send, title: "Shipments to send" },
  { id: "history", label: "History", icon: HistoryIcon, title: "What was done" },
  { id: "system", label: "System", icon: ServerCog, title: "System and settings" },
] as const
type ViewId = (typeof VIEWS)[number]["id"]
const OLD: Record<string, ViewId> = { overview: "home", recommendations: "actions", decisions: "history", incidents: "system", health: "system" }

const MODES = [
  { id: "observe", label: "View only", hint: "Nothing is sent" },
  { id: "manual", label: "I approve", hint: "You press Send for each shipment" },
  { id: "auto", label: "Automatic", hint: "Sent automatically; unsure ones wait for you" },
] as const

function useView(): [ViewId, (v: ViewId) => void] {
  const read = (): ViewId => {
    const h = window.location.hash.slice(1)
    return (VIEWS.find(v => v.id === h)?.id ?? OLD[h] ?? "home") as ViewId
  }
  const [view, setView] = useState<ViewId>(read)
  useEffect(() => {
    const on = () => setView(read())
    window.addEventListener("hashchange", on)
    return () => window.removeEventListener("hashchange", on)
  }, [])
  return [view, v => { window.location.hash = v }]
}

export default function App() {
  const [view, go] = useView()
  const { data: status, error, reload } = usePoll<Status>("/api/status", 1000)
  const { data: recs } = usePoll<{ cards: Card[] }>("/api/recommendations", 2000)
  const waiting = recs?.cards.filter(c => c.allocations.length).length ?? 0
  const tm = status?.tick_minutes ?? 15
  const running = status?.sim_status === "RUNNING"
  const page = VIEWS.find(v => v.id === view)!

  const send = async (path: string, body: unknown, method = "PUT") => {
    try { await api(path, { method, body: JSON.stringify(body) }); reload() }
    catch (e) { toast.error(e instanceof Error ? e.message : String(e)) }
  }

  return (
    <div className="min-h-dvh text-base md:grid md:grid-cols-[14rem_1fr]">
      <nav aria-label="Main" className="bg-sidebar text-sidebar-foreground md:sticky md:top-0 md:h-dvh">
        <div className="px-5 pb-4 pt-5">
          <div className="font-heading text-2xl font-bold leading-none text-white">Fuel Operations</div>
          <div className="mt-1.5 text-sm text-sidebar-foreground/80">Bangladesh fuel network</div>
        </div>
        <ul className="flex gap-1 overflow-x-auto px-2 pb-2 md:block md:space-y-1 md:overflow-visible">
          {VIEWS.map(v => (
            <li key={v.id}>
              <a href={`#${v.id}`} onClick={e => { e.preventDefault(); go(v.id) }} aria-current={view === v.id ? "page" : undefined}
                className={cn("flex items-center gap-3 whitespace-nowrap rounded-md px-3 py-2.5 text-base outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring",
                  view === v.id ? "bg-sidebar-accent font-semibold text-white" : "hover:bg-sidebar-accent/60")}>
                <v.icon className="size-5" aria-hidden />
                <span>{v.label}</span>
                {v.id === "actions" && waiting > 0 &&
                  <span className="ml-auto rounded-full bg-warn px-2 text-sm font-bold text-white" aria-label={`${waiting} waiting`}>{waiting}</span>}
              </a>
            </li>))}
        </ul>
      </nav>

      <div className="min-w-0">
        <header className="flex flex-wrap items-center gap-x-8 gap-y-3 border-b bg-card px-4 py-4 md:px-8">
          <h1 className="text-3xl font-semibold leading-tight">{page.title}</h1>
          {status && (
            <div className="flex flex-wrap items-center gap-x-8 gap-y-3 md:ml-auto">
              <div className="flex items-center gap-3">
                <div>
                  <div className="text-sm text-muted-foreground">Simulation time</div>
                  <div className="text-lg font-semibold">{clock(status.tick, tm)}</div>
                </div>
                <span className={cn("rounded-full px-2.5 py-0.5 text-sm font-semibold", running ? "bg-ok/15 text-ok" : "bg-muted text-muted-foreground")}>
                  {running ? "Running" : "Paused"}
                </span>
                <Button variant="outline" onClick={() => send("/api/lab/control", { action: running ? "pause" : "run" }, "POST")}>
                  {running ? "Pause" : "Start"}
                </Button>
                {!running && (status.tick ?? 0) > 0 && (
                  <AlertDialog>
                    <AlertDialogTrigger render={<Button variant="outline" />}>Reset</AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Restart the simulation from Day 1?</AlertDialogTitle>
                        <AlertDialogDescription>All tanks, depots and shipments go back to the start. Your decision history in this app is kept.</AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction variant="destructive" onClick={() => send("/api/lab/control", { action: "reset" }, "POST")}>Reset</AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                )}
              </div>
              <fieldset>
                <legend className="text-sm text-muted-foreground">Sending fuel</legend>
                <div className="mt-0.5 flex rounded-md border bg-background p-0.5">
                  {MODES.map(m => (
                    <label key={m.id} title={m.hint} className={cn("cursor-pointer rounded px-3 py-1.5 text-base has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring",
                      status.mode === m.id ? "bg-ink font-semibold text-white" : "hover:bg-muted")}>
                      <input type="radio" name="mode" value={m.id} checked={status.mode === m.id} className="sr-only"
                        onChange={() => send("/api/operating-mode", { mode: m.id })} />
                      {m.label}
                    </label>))}
                </div>
              </fieldset>
            </div>
          )}
        </header>

        {error && <Banner tone="alarm">The app lost contact with its server. Showing the last known values and retrying.</Banner>}
        {status?.degraded && <Banner tone="warn">The fuel simulator is not answering. You are seeing data from {Math.round(status.snapshot_age_s ?? 0)} seconds ago. Nothing is sent until it is back.</Banner>}
        {status && !status.intelligence_enabled && <Banner tone="warn">Smart planning is off. The simple refill rule is deciding shipments until it is turned back on (System page).</Banner>}
        {status && !running && status.tick === 0 && <Banner tone="info">The simulation has not started. Press Start at the top to begin.</Banner>}

        <main className="px-4 py-6 md:px-8">
          {view === "home" && <Home go={go} />}
          {view === "actions" && <Actions status={status} />}
          {view === "history" && <History status={status} />}
          {view === "system" && <System status={status} onChanged={reload} />}
        </main>
      </div>
      <Toaster position="bottom-right" richColors />
    </div>
  )
}

function Banner({ tone, children }: { tone: "warn" | "alarm" | "info"; children: React.ReactNode }) {
  return (
    <div role="status" className={cn("border-b px-4 py-3 text-base font-medium md:px-8",
      tone === "alarm" ? "border-alarm/30 bg-alarm/10 text-alarm" : tone === "warn" ? "border-warn/30 bg-warn/10 text-warn" : "bg-diesel/10 text-diesel")}>
      {children}
    </div>
  )
}
