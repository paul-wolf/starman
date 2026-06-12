import { useEffect, useState } from "react"
import { fetchEvents } from "./api"
import type { ApiEvent } from "./api"

const EVENT_COLORS: Record<string, string> = {
  GPS_DENIED:            "#f59e0b",
  GPS_RECOVERED:         "#22c55e",
  INHIBIT_SET:           "#ef4444",
  INHIBIT_CLEARED:       "#22c55e",
  OUTAGE_START:          "#ef4444",
  OUTAGE_END:            "#22c55e",
  REBOOT_DETECTED:       "#facc15",
  DISH_UNREACHABLE:      "#ef4444",
  CONTROL_ACTION:        "#60a5fa",
  WATCHDOG_MODE_CHANGED: "#a78bfa",
}

function eventColor(type: string): string {
  return EVENT_COLORS[type] ?? "#64748b"
}

function summarise(ev: ApiEvent): string {
  const d = ev.detail
  switch (ev.event_type) {
    case "GPS_DENIED":       return `sats=${d.sats ?? "?"}`
    case "GPS_RECOVERED":    return `sats=${d.sats ?? "?"}`
    case "INHIBIT_SET":      return d.simulated ? `simulated (${d.mode})` : "enforced"
    case "INHIBIT_CLEARED":  return d.simulated ? `simulated (${d.mode})` : "enforced"
    case "OUTAGE_START":     return `cause: ${d.cause ?? "?"}`
    case "OUTAGE_END":       return `was: ${d.cause ?? "?"}`
    case "REBOOT_DETECTED":  return `uptime ${d.prev_uptime_s}s → ${d.uptime_s}s`
    case "CONTROL_ACTION":   return `${d.action}${d.enabled !== undefined ? ` enabled=${d.enabled}` : ""}${d.stow !== undefined ? ` stow=${d.stow}` : ""}`
    case "WATCHDOG_MODE_CHANGED": return `${d.from} → ${d.to}`
    default:                 return ""
  }
}

function relTime(ts: string): string {
  const diff = Math.floor((Date.now() - new Date(ts).getTime()) / 1000)
  if (diff < 60)   return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

const REFRESH_MS = 10_000

export default function EventTimeline() {
  const [events, setEvents] = useState<ApiEvent[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    function load() {
      fetchEvents(60)
        .then(setEvents)
        .catch(e => setError(e instanceof Error ? e.message : "Error"))
    }
    load()
    const id = setInterval(load, REFRESH_MS)
    return () => clearInterval(id)
  }, [])

  if (error) return <div className="tl-error">{error}</div>
  if (events.length === 0) return <div className="tl-empty">No events yet</div>

  return (
    <div className="timeline">
      {events.map(ev => {
        const color = eventColor(ev.event_type)
        const detail = summarise(ev)
        return (
          <div key={ev.id} className="tl-row">
            <span className="tl-time" title={new Date(ev.timestamp).toLocaleString()}>
              {relTime(ev.timestamp)}
            </span>
            <span className="tl-badge" style={{ color, borderColor: color }}>
              {ev.event_type}
            </span>
            <span className="tl-source">
              {ev.source}{ev.actor ? ` · ${ev.actor}` : ""}
            </span>
            {detail && <span className="tl-detail">{detail}</span>}
          </div>
        )
      })}
    </div>
  )
}
