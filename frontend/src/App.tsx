import { useEffect, useState } from "react"
import { AuthError, fetchGpsState, fetchLive, fetchMe, fetchWatchdogConfig, logout } from "./api"
import type { GpsState, TelemetryReading, WatchdogConfig } from "./api"
import Charts from "./Charts"
import Controls from "./Controls"
import EventTimeline from "./EventTimeline"
import Login from "./Login"
import "./App.css"

const POLL_MS = 2500

function fmt(n: number | null | undefined, decimals = 1): string {
  if (n == null) return "—"
  return n.toFixed(decimals)
}

function bps(n: number | null | undefined): string {
  if (n == null) return "—"
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)} Mbps`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)} kbps`
  return `${n.toFixed(0)} bps`
}

function uptime(s: number): string {
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  return `${h}h ${m}m`
}

interface TileProps {
  label: string
  value: string
  ok?: boolean | null
}

function Tile({ label, value, ok }: TileProps) {
  const color = ok == null ? "" : ok ? "tile--ok" : "tile--warn"
  return (
    <div className={`tile ${color}`}>
      <div className="tile-label">{label}</div>
      <div className="tile-value">{value}</div>
    </div>
  )
}

export default function App() {
  const [username, setUsername] = useState<string | null>(null)
  const [authChecked, setAuthChecked] = useState(false)
  const [live, setLive] = useState<TelemetryReading | null>(null)
  const [gps, setGps] = useState<GpsState | null>(null)
  const [config, setConfig] = useState<WatchdogConfig | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)

  // Check session on mount
  useEffect(() => {
    fetchMe()
      .then(me => { setUsername(me.username); setAuthChecked(true) })
      .catch(() => setAuthChecked(true))
  }, [])

  // Poll when authenticated
  useEffect(() => {
    if (!username) return

    async function poll() {
      try {
        const [liveData, gpsData, cfgData] = await Promise.all([
          fetchLive(),
          fetchGpsState(),
          fetchWatchdogConfig(),
        ])
        setLive(liveData)
        setGps(gpsData)
        setConfig(cfgData)
        setLastUpdate(new Date())
        setError(null)
      } catch (e) {
        if (e instanceof AuthError) { setUsername(null); return }
        setError(e instanceof Error ? e.message : "Unknown error")
      }
    }

    poll()
    const id = setInterval(poll, POLL_MS)
    return () => clearInterval(id)
  }, [username])

  async function handleLogout() {
    await logout().catch(() => {})
    setUsername(null)
    setLive(null)
    setGps(null)
    setConfig(null)
  }

  if (!authChecked) return null

  if (!username) return <Login onLogin={setUsername} />

  return (
    <div className="app">
      <header className="header">
        <h1>Starlink Console</h1>
        <span className="header-right">
          {lastUpdate && (
            <span className="last-update">
              Updated {lastUpdate.toLocaleTimeString()}
              {error && <span className="stale"> — connection lost</span>}
            </span>
          )}
          <button className="btn-logout" onClick={handleLogout}>{username} · Sign out</button>
        </span>
      </header>

      <section className="section-title">GPS</section>
      <div className="tile-grid">
        <Tile label="GPS Valid" value={gps ? (gps.valid ? "Yes" : "No") : "…"} ok={gps?.valid} />
        <Tile label="Satellites" value={gps ? String(gps.sats) : "…"} ok={gps ? gps.sats >= 5 : null} />
        <Tile label="Inhibited" value={gps ? (gps.inhibited ? "Yes" : "No") : "…"} ok={gps ? !gps.inhibited : null} />
        <Tile label="Watchdog Mode" value={gps?.watchdog_mode ?? "…"} />
      </div>

      <section className="section-title">Connectivity</section>
      <div className="tile-grid">
        <Tile label="Latency" value={live ? `${fmt(live.pop_ping_latency_ms)} ms` : "…"} ok={live ? (live.pop_ping_latency_ms ?? 999) < 100 : null} />
        <Tile label="Drop Rate" value={live ? `${fmt(live.pop_ping_drop_rate * 100, 2)}%` : "…"} ok={live ? live.pop_ping_drop_rate < 0.01 : null} />
        <Tile label="Downlink" value={live ? bps(live.downlink_bps) : "…"} />
        <Tile label="Uplink" value={live ? bps(live.uplink_bps) : "…"} />
      </div>

      <section className="section-title">Dish</section>
      <div className="tile-grid">
        <Tile label="Obstruction" value={live ? `${fmt((live.fraction_obstructed ?? 0) * 100, 1)}%` : "…"} ok={live ? (live.fraction_obstructed ?? 0) < 0.05 : null} />
        <Tile label="Attitude" value={live?.attitude_state ?? "…"} />
        <Tile label="Attitude Uncertainty" value={live ? `${fmt(live.attitude_uncertainty_deg)}°` : "…"} />
        <Tile label="Uptime" value={live ? uptime(live.uptime_s) : "…"} />
      </div>

      <section className="section-title">Device</section>
      <div className="tile-grid">
        <Tile label="Software" value={live?.software_version ?? "…"} />
        <Tile label="Country" value={live?.country_code ?? "…"} />
        <Tile label="Disablement" value={live?.disablement_code || "None"} />
        <Tile label="Outage" value={live?.outage_cause || "None"} />
      </div>

      <section className="section-title">Charts</section>
      <Charts />

      <section className="section-title">Event Timeline</section>
      <EventTimeline />

      <section className="section-title">Controls</section>
      <Controls
        gps={gps}
        config={config}
        onGpsChange={setGps}
        onConfigChange={setConfig}
      />
    </div>
  )
}
