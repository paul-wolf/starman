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
  NET_OUTAGE_START:      "#dc2626",
  NET_OUTAGE_END:        "#16a34a",
  REBOOT_DETECTED:       "#facc15",
  DISH_UNREACHABLE:      "#ef4444",
  CONTROL_ACTION:        "#60a5fa",
  WATCHDOG_MODE_CHANGED: "#a78bfa",
}

function eventColor(type: string): string {
  return EVENT_COLORS[type] ?? "#64748b"
}

// Starlink DishUnavailableType enum integers (from gRPC reflection)
const DISH_UNAVAILABLE: Record<number, string> = {
  0:  "OK",
  1:  "BOOTING",
  2:  "SEARCHING",
  4:  "NO_SATS",
  5:  "OBSTRUCTED",
  6:  "NO_DOWNLINK",
  7:  "NO_PINGS",
  9:  "THERMAL_THROTTLE",
  10: "SLEEPING",
  11: "TOO_FAST_FOR_POLICY",
  12: "MOVING",
  13: "NO_SCHEDULED_LOCATION",
  14: "UNKNOWN_LOCATION",
  15: "NO_UPLINK",
  16: "STOWED",
}

function decodeCause(raw: unknown): string {
  if (raw == null) return "?"
  const n = Number(raw)
  if (!isNaN(n) && DISH_UNAVAILABLE[n]) return `${DISH_UNAVAILABLE[n]} (${n})`
  return String(raw)
}

function summarise(ev: ApiEvent): string {
  const d = ev.detail
  switch (ev.event_type) {
    case "GPS_DENIED":       return `sats=${d.sats ?? "?"}`
    case "GPS_RECOVERED":    return `sats=${d.sats ?? "?"}`
    case "INHIBIT_SET":      return d.simulated ? `would inhibit (${d.mode})` : "enforced"
    case "INHIBIT_CLEARED":  return d.simulated ? `would clear (${d.mode})` : "enforced"
    case "OUTAGE_START":     return `cause: ${decodeCause(d.cause)}`
    case "OUTAGE_END":       return `was: ${decodeCause(d.cause)}`
    case "NET_OUTAGE_START": return "internet unreachable"
    case "NET_OUTAGE_END":   return "internet restored"
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
