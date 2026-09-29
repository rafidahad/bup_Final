import { useState } from "react"
import { type ForecastSeries, type Forecasts, usePoll } from "@/lib/api"
import { fuel, stationName } from "@/lib/text"
import { cn } from "@/lib/utils"
import { FuelDot, Panel } from "./parts"

const W = 300, H = 120, PAD = { l: 38, r: 8, t: 8, b: 22 }

/** Demand forecast panel: what customers bought, what the formula expects, and the AI forecast range. */
export function DemandForecast() {
  const { data } = usePoll<Forecasts>("/api/forecasts", 3000)
  const [station, setStation] = useState("station-mirpur")
  if (!data) return null
  const ids = [...new Set(data.series.map(s => s.station_id))]
  const e = data.evaluation
  const ready = data.status.state === "ok" && data.series.some(s => s.chronos)

  return (
    <Panel>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b px-5 py-3">
        <h2 className="text-lg font-semibold">Demand forecast, next 12 hours</h2>
        <div className="flex rounded-md border p-0.5 text-sm" role="group" aria-label="Station">
          {ids.map(id => (
            <button key={id} aria-pressed={station === id} onClick={() => setStation(id)}
              className={cn("rounded px-3 py-1", station === id ? "bg-ink text-white" : "hover:bg-muted")}>{stationName(id)}</button>))}
        </div>
      </div>
      <div className="grid gap-4 px-5 py-4 md:grid-cols-3">
        {data.series.filter(s => s.station_id === station).map(s => <FuelChart key={s.fuel} s={s} now={data.tick} tm={data.tick_minutes} />)}
      </div>
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-t px-5 py-3 text-sm text-muted-foreground">
        <Key swatch={<span className="inline-block size-2 rounded-full bg-ink/50" />} text="sold (actual)" />
        <Key swatch={<span className="inline-block w-5 border-t-2 border-dashed border-ink" />} text="published formula" />
        <Key swatch={<span className="inline-block h-3 w-5 rounded-sm bg-diesel/25" />} text="AI forecast range (10–90%)" />
        <Key swatch={<span className="inline-block w-5 border-t-2 border-diesel" />} text="AI forecast (middle)" />
      </div>
      <p className="border-t px-5 py-3 text-base">
        {!ready
          ? <>The AI forecaster (Chronos) is {data.status.state === "down" ? "not reachable" : data.status.state === "waiting" ? "collecting sales history" : "starting"}. The planner uses the published formula.</>
          : e.points === 0
            ? <>AI forecast is running. Its accuracy is measured as its predictions come true. The planner uses the published formula meanwhile.</>
            : <>So far the AI forecast is off by <strong>{((e.chronos_mape ?? 0) * 100).toFixed(1)}%</strong> on average and the formula by <strong>{((e.formula_mape ?? 0) * 100).toFixed(1)}%</strong>
              {" "}({e.points.toLocaleString("en-US")} checks; {Math.round((e.coverage_10_90 ?? 0) * 100)}% of real sales fell inside the AI range). {e.verdict}</>}
      </p>
    </Panel>
  )
}

function Key({ swatch, text }: { swatch: React.ReactNode; text: string }) {
  return <span className="flex items-center gap-1.5">{swatch}{text}</span>
}

function FuelChart({ s, now, tm }: { s: ForecastSeries; now: number; tm: number }) {
  const color = `var(--${s.fuel.toLowerCase()})`
  const t0 = now - 48, t1 = now + 48
  const vals = [...s.observed.map(o => o.liters), ...s.formula.map(f => f.liters), ...(s.chronos ?? []).map(c => c.q90)]
  const ymax = Math.max(1, ...vals) * 1.1
  const x = (t: number) => PAD.l + ((t - t0) / (t1 - t0)) * (W - PAD.l - PAD.r)
  const y = (v: number) => H - PAD.b - (v / ymax) * (H - PAD.t - PAD.b)
  const line = (pts: [number, number][]) => pts.map((p, i) => `${i ? "L" : "M"}${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join("")
  const band = s.chronos?.length
    ? line(s.chronos.map(c => [c.tick, c.q90])) + s.chronos.slice().reverse().map(c => `L${x(c.tick).toFixed(1)},${y(c.q10).toFixed(1)}`).join("") + "Z"
    : ""
  const hours = (tm * 48) / 60
  return (
    <figure>
      <figcaption className="mb-1 flex items-center gap-1.5 text-base font-medium"><FuelDot fuel={s.fuel} />{fuel(s.fuel)}</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img"
        aria-label={`${fuel(s.fuel)} demand at ${stationName(s.station_id)}: last ${hours} hours sold and next ${hours} hours forecast`}>
        <line x1={x(now)} x2={x(now)} y1={PAD.t} y2={H - PAD.b} stroke="var(--border)" strokeWidth={1.5} />
        <text x={x(now)} y={H - 6} textAnchor="middle" className="fill-muted-foreground text-[10px]">now</text>
        <text x={PAD.l} y={H - 6} className="fill-muted-foreground text-[10px]">−{hours} h</text>
        <text x={W - PAD.r} y={H - 6} textAnchor="end" className="fill-muted-foreground text-[10px]">+{hours} h</text>
        <text x={PAD.l - 4} y={y(ymax / 1.1) + 3} textAnchor="end" className="fill-muted-foreground text-[10px]">{Math.round(ymax / 1.1)} L</text>
        <text x={PAD.l - 4} y={y(0) + 3} textAnchor="end" className="fill-muted-foreground text-[10px]">0</text>
        {band && <path d={band} fill={color} opacity={0.2} />}
        {s.chronos?.length ? <path d={line(s.chronos.map(c => [c.tick, c.q50]))} fill="none" stroke={color} strokeWidth={2} /> : null}
        <path d={line(s.formula.map(f => [f.tick, f.liters]))} fill="none" stroke="var(--ink)" strokeWidth={1.5} strokeDasharray="4 3" />
        {s.observed.map(o => <circle key={o.tick} cx={x(o.tick)} cy={y(o.liters)} r={1.8} fill="var(--ink)" opacity={0.5} />)}
      </svg>
      <div className="text-xs text-muted-foreground">liters sold per 15 minutes</div>
    </figure>
  )
}
