import { useEffect, useState } from "react"
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import { fetchHistory } from "./api"
import type { TelemetryReading } from "./api"

const WINDOWS = [
  { label: "1h",  hours: 1   },
  { label: "6h",  hours: 6   },
  { label: "24h", hours: 24  },
  { label: "7d",  hours: 168 },
]

function sinceIso(hours: number) {
  return new Date(Date.now() - hours * 3_600_000).toISOString()
}

function tickTime(ts: string, hours: number): string {
  const d = new Date(ts)
  if (hours <= 24) return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
  return d.toLocaleDateString([], { month: "short", day: "numeric" })
}

interface ChartDatum {
  ts: string
  [key: string]: number | string | null
}

function toData(readings: TelemetryReading[]): ChartDatum[] {
  return readings.map(r => ({
    ts: r.timestamp,
    sats: r.gps_sats,
    latency: r.pop_ping_latency_ms,
    drop: +(r.pop_ping_drop_rate * 100).toFixed(3),
    obstruction: r.fraction_obstructed != null ? +(r.fraction_obstructed * 100).toFixed(3) : null,
  }))
}

interface MiniChartProps {
  data: ChartDatum[]
  dataKey: string
  label: string
  unit: string
  color: string
  hours: number
  domain?: [number | "auto", number | "auto"]
}

function MiniChart({ data, dataKey, label, unit, color, hours, domain }: MiniChartProps) {
  return (
    <div className="chart-card">
      <div className="chart-title">{label}</div>
      {data.length === 0 ? (
        <div className="chart-empty">No data</div>
      ) : (
        <ResponsiveContainer width="100%" height={160}>
          <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#2d3748" />
            <XAxis
              dataKey="ts"
              tickFormatter={ts => tickTime(ts as string, hours)}
              tick={{ fontSize: 10, fill: "#64748b" }}
              tickLine={false}
              minTickGap={40}
            />
            <YAxis
              domain={domain ?? ["auto", "auto"]}
              tick={{ fontSize: 10, fill: "#64748b" }}
              tickLine={false}
              width={36}
              tickFormatter={v => `${v}${unit}`}
            />
            <Tooltip
              contentStyle={{ background: "#1e2330", border: "1px solid #2d3748", fontSize: 12 }}
              labelFormatter={ts => new Date(ts as string).toLocaleString()}
              formatter={(v: number) => [`${v}${unit}`, label]}
            />
            <Line
              type="monotone"
              dataKey={dataKey}
              stroke={color}
              dot={false}
              strokeWidth={1.5}
              connectNulls
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}

export default function Charts() {
  const [windowHours, setWindowHours] = useState(1)
  const [data, setData] = useState<ChartDatum[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchHistory(sinceIso(windowHours))
      .then(readings => { if (!cancelled) setData(toData(readings)) })
      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : "Error") })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [windowHours])

  return (
    <div className="charts-wrap">
      <div className="window-selector">
        {WINDOWS.map(w => (
          <button
            key={w.label}
            className={`btn ${windowHours === w.hours ? "btn-active" : ""}`}
            onClick={() => setWindowHours(w.hours)}
          >
            {w.label}
          </button>
        ))}
        {loading && <span className="chart-loading">Loading…</span>}
        {error && <span className="chart-error">{error}</span>}
      </div>

      <div className="chart-grid">
        <MiniChart data={data} dataKey="sats"        label="GPS Satellites" unit=""   color="#22d3ee" hours={windowHours} domain={[0, "auto"]} />
        <MiniChart data={data} dataKey="latency"     label="Latency"        unit=" ms" color="#a78bfa" hours={windowHours} domain={[0, "auto"]} />
        <MiniChart data={data} dataKey="drop"        label="Drop Rate"      unit="%"  color="#f87171" hours={windowHours} domain={[0, "auto"]} />
        <MiniChart data={data} dataKey="obstruction" label="Obstruction"    unit="%"  color="#fb923c" hours={windowHours} domain={[0, "auto"]} />
      </div>
    </div>
  )
}
