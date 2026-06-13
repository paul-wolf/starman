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
  connectivity_ok: boolean | null
}

export interface GpsState {
  valid: boolean
  sats: number
  inhibited: boolean
  watchdog_mode: string
  manual_hold_until: string | null
  last_poll_at: string | null
}

export interface WatchdogConfig {
  mode: string
  poll_interval_s: number
  deny_debounce_s: number
  recover_debounce_s: number
  min_sats_for_good: number
  boot_warmup_s: number
  probe_hosts: string
  manual_override_until: string | null
  last_poll_at: string | null
}

export interface ApiEvent {
  id: number
  timestamp: string
  event_type: string
  source: string
  actor: string | null
  detail: Record<string, unknown>
}

export class AuthError extends Error {}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(path, options)
  if (res.status === 401) throw new AuthError("Unauthenticated")
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`${res.status}: ${text}`)
  }
  return res.json() as Promise<T>
}

function post<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export const login = (username: string, password: string) =>
  post<{ username: string }>("/api/auth/login", { username, password })

export const logout = () =>
  post<{ ok: boolean }>("/api/auth/logout", {})

export const fetchMe = () =>
  request<{ username: string }>("/api/auth/me")

// ── Read ──────────────────────────────────────────────────────────────────────

export const fetchLive = () => request<TelemetryReading>("/api/status/live")
export const fetchGpsState = () => request<GpsState>("/api/gps/state")
export const fetchWatchdogConfig = () => request<WatchdogConfig>("/api/watchdog/config")

export const fetchHistory = (sinceIso: string) =>
  request<TelemetryReading[]>(`/api/status/history?since=${encodeURIComponent(sinceIso)}&limit=500`)

export const fetchEvents = (limit = 50) =>
  request<ApiEvent[]>(`/api/events?limit=${limit}`)

// ── Control ───────────────────────────────────────────────────────────────────

export const controlInhibitGps = (enabled: boolean) =>
  post<GpsState>("/api/control/inhibit-gps", { enabled })

export const controlReboot = () =>
  post<{ ok: boolean; detail: string }>("/api/control/reboot", { confirm: true })

export const controlStow = (stow: boolean) =>
  post<{ ok: boolean; detail: string }>("/api/control/stow", { stow })

export const updateWatchdogConfig = (
  updates: Partial<Pick<WatchdogConfig, "mode" | "poll_interval_s" | "deny_debounce_s" | "recover_debounce_s" | "min_sats_for_good" | "probe_hosts">>
) => post<WatchdogConfig>("/api/watchdog/config", updates)
