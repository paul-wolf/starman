export interface TelemetryReading {
  id: number
  timestamp: string
  gps_valid: boolean
  gps_sats: number
  gps_inhibited: boolean
  pnt_filter_state: string
  pop_ping_latency_ms: number | null
  pop_ping_drop_rate: number
  downlink_bps: number | null
  uplink_bps: number | null
  fraction_obstructed: number | null
  attitude_uncertainty_deg: number | null
  attitude_state: string
  uptime_s: number
  software_version: string
  country_code: string
  disablement_code: string
  outage_cause: string | null
  mobility_class: string
}

export interface GpsState {
  valid: boolean
  sats: number
  inhibited: boolean
  watchdog_mode: string
  manual_hold_until: string | null
  last_poll_at: string | null
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}

export const fetchLive = () => get<TelemetryReading>('/api/status/live')
export const fetchGpsState = () => get<GpsState>('/api/gps/state')
