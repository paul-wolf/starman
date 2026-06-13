import { useEffect, useState } from "react"
import { fetchSystemStats } from "./api"
import type { SystemStats } from "./api"

interface Props {
  onClose: () => void
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—"
  return new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })
}

function fmtCount(n: number): string {
  return n.toLocaleString()
}

interface RowProps {
  label: string
  value: string
  warn?: boolean
}

function Row({ label, value, warn }: RowProps) {
  return (
    <div className="ss-row">
      <span className="ss-label">{label}</span>
      <span className={`ss-value${warn ? " ss-warn" : ""}`}>{value}</span>
    </div>
  )
}

export default function SystemStatsModal({ onClose }: Props) {
  const [stats, setStats] = useState<SystemStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchSystemStats()
      .then(s => { setStats(s); setLoading(false) })
      .catch(e => { setError(e instanceof Error ? e.message : "Error"); setLoading(false) })
  }, [])

  const diskPct = stats ? (stats.disk_used_gb / stats.disk_total_gb) * 100 : 0

  return (
    <div className="ss-overlay" onClick={onClose}>
      <div className="ss-card" onClick={e => e.stopPropagation()}>
        <div className="ss-header">
          <span className="ss-title">System</span>
          <button className="ss-close" onClick={onClose}>✕</button>
        </div>

        {loading && <div className="ss-loading">Loading…</div>}
        {error && <div className="ss-error">{error}</div>}

        {stats && (
          <>
            <div className="ss-section">Storage</div>
            <Row label="Database" value={`${stats.db_size_mb} MB`} />
            <Row
              label="Disk"
              value={`${stats.disk_free_gb} GB free of ${stats.disk_total_gb} GB`}
              warn={diskPct > 85}
            />
            <div className="ss-disk-bar">
              <div className="ss-disk-fill" style={{ width: `${Math.min(diskPct, 100)}%`, background: diskPct > 85 ? "#ef4444" : "#3b82f6" }} />
            </div>

            <div className="ss-section">Telemetry</div>
            <Row label="Rows" value={fmtCount(stats.telemetry_count)} />
            <Row label="Oldest" value={fmtDate(stats.telemetry_oldest)} />
            <Row label="Newest" value={fmtDate(stats.telemetry_newest)} />

            <div className="ss-section">Events</div>
            <Row label="Rows" value={fmtCount(stats.event_count)} />

            <div className="ss-section">Maintenance</div>
            <Row label="Last retention run" value={fmtDate(stats.last_retain_at)} warn={!stats.last_retain_at} />
          </>
        )}
      </div>
    </div>
  )
}
