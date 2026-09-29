import { StatusText } from "@/components/fuel"
import { type Health as HealthT, usePoll } from "@/lib/api"
import { Waiting } from "./Overview"

const NAMES: Record<string, string> = {
  backend_api: "Backend API", database: "Database", simulator: "Fuel simulator",
  prediction_service: "Prediction service", decision_engine: "Decision engine",
}

export function Health() {
  const { data, error } = usePoll<HealthT>("/api/health", 2000)
  const { data: plans } = usePoll<{ solves: { tick: number; status: number; seconds: number }[]; executor: { sent: number; accepted: number; rejected: Record<string, number> }; prediction_mape: number | null }>("/api/plans", 3000)
  if (!data) return <Waiting error={error} />
  const solves = plans?.solves ?? []
  const avgSolve = solves.length ? solves.reduce((s, x) => s + x.seconds, 0) / solves.length : null
  return (
    <div className="grid gap-8 xl:grid-cols-[3fr_2fr]">
      <section aria-labelledby="comp">
        <h2 id="comp" className="mb-3 text-lg font-semibold">System status: <StatusText status={data.status} /></h2>
        <table className="w-full rounded-md border bg-card text-sm">
          <tbody>{Object.entries(data.components).map(([k, c]) => (
            <tr key={k} className="border-b last:border-0 align-top">
              <th scope="row" className="w-44 px-4 py-2.5 text-left font-medium">{NAMES[k] ?? k}</th>
              <td className="px-2 py-2.5"><StatusText status={c.status} /></td>
              <td className="px-4 py-2.5 text-muted-foreground">{describe(k, c)}</td>
            </tr>))}</tbody>
        </table>
      </section>
      <section aria-labelledby="perf" className="space-y-4">
        <h2 id="perf" className="text-lg font-semibold">Performance</h2>
        <dl className="divide-y rounded-md border bg-card text-sm">
          <Row k="p95 API latency" v={data.p95_latency_ms != null ? `${data.p95_latency_ms} ms` : "—"} />
          <Row k="API error rate" v={`${(data.error_rate * 100).toFixed(2)}% of the last ${data.window_requests} requests`} />
          <Row k="Optimizer solve time" v={avgSolve != null ? `${(avgSolve * 1000).toFixed(0)} ms average, last ${solves.length}` : "—"} />
          <Row k="Demand prediction error" v={plans?.prediction_mape != null ? `${(plans.prediction_mape * 100).toFixed(1)}% mean absolute` : "not enough history yet"} />
          <Row k="Shipment requests" v={plans ? `${plans.executor.accepted} accepted of ${plans.executor.sent}` : "—"} />
        </dl>
        <p className="text-sm text-muted-foreground">
          Detailed metrics: <a className="underline" href="http://localhost:3000" target="_blank" rel="noreferrer">Grafana</a> and <a className="underline" href="http://localhost:9090" target="_blank" rel="noreferrer">Prometheus</a> when the full stack is running.
        </p>
      </section>
    </div>
  )
}

function Row({ k, v }: { k: string; v: string }) {
  return <div className="flex justify-between gap-4 px-4 py-2.5"><dt className="text-muted-foreground">{k}</dt><dd className="text-right font-medium">{v}</dd></div>
}

function describe(k: string, c: Record<string, unknown>) {
  if (c.detail) return String(c.detail)
  if (k === "simulator" && c.tick != null) return `tick ${c.tick}, ${String(c.state).toLowerCase()}`
  if (k === "decision_engine") return `planner ${c.source}, last cycle ${c.last_cycle_age_s ?? "—"} s ago`
  if (k === "prediction_service") return c.history_rows ? `${c.history_rows} demand observations in use` : "waiting for history"
  return ""
}
