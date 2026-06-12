import { useEffect, useState } from "react"
import type { GpsState, WatchdogConfig } from "./api"
import { controlInhibitGps, controlReboot, controlStow, updateWatchdogConfig } from "./api"

interface Props {
  gps: GpsState | null
  config: WatchdogConfig | null
  onGpsChange: (g: GpsState) => void
  onConfigChange: (c: WatchdogConfig) => void
}

export default function Controls({ gps, config, onGpsChange, onConfigChange }: Props) {
  const [rebootConfirm, setRebootConfirm] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Threshold form state (mirrors config; kept in sync when config changes)
  const [pollInterval, setPollInterval] = useState(config?.poll_interval_s ?? 10)
  const [denyDebounce, setDenyDebounce] = useState(config?.deny_debounce_s ?? 90)
  const [recoverDebounce, setRecoverDebounce] = useState(config?.recover_debounce_s ?? 120)
  const [minSats, setMinSats] = useState(config?.min_sats_for_good ?? 5)
  const [cfgSaved, setCfgSaved] = useState(false)

  useEffect(() => {
    if (!config) return
    setPollInterval(config.poll_interval_s)
    setDenyDebounce(config.deny_debounce_s)
    setRecoverDebounce(config.recover_debounce_s)
    setMinSats(config.min_sats_for_good)
  }, [config])

  async function act(key: string, fn: () => Promise<unknown>) {
    setBusy(key)
    setError(null)
    try {
      await fn()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error")
    } finally {
      setBusy(null)
    }
  }

  async function handleInhibit(enabled: boolean) {
    await act("inhibit", async () => {
      const state = await controlInhibitGps(enabled)
      onGpsChange(state)
    })
  }

  async function handleReboot() {
    if (!rebootConfirm) { setRebootConfirm(true); return }
    await act("reboot", async () => {
      await controlReboot()
      setRebootConfirm(false)
    })
  }

  async function handleStow(stow: boolean) {
    await act("stow", () => controlStow(stow))
  }

  async function handleModeChange(mode: string) {
    await act("mode", async () => {
      const updated = await updateWatchdogConfig({ mode })
      onConfigChange(updated)
    })
  }

  async function handleSaveThresholds() {
    await act("thresholds", async () => {
      const updated = await updateWatchdogConfig({
        poll_interval_s: pollInterval,
        deny_debounce_s: denyDebounce,
        recover_debounce_s: recoverDebounce,
        min_sats_for_good: minSats,
      })
      onConfigChange(updated)
      setCfgSaved(true)
      setTimeout(() => setCfgSaved(false), 2000)
    })
  }

  return (
    <div className="controls">
      {error && <div className="ctrl-error">{error}</div>}

      <div className="ctrl-row">
        <span className="ctrl-label">GPS Inhibit</span>
        <button
          className="btn btn-warn"
          disabled={!!busy || gps?.inhibited === true}
          onClick={() => handleInhibit(true)}
        >
          {busy === "inhibit" ? "…" : "Inhibit"}
        </button>
        <button
          className="btn"
          disabled={!!busy || gps?.inhibited === false}
          onClick={() => handleInhibit(false)}
        >
          Clear
        </button>
      </div>

      <div className="ctrl-row">
        <span className="ctrl-label">Dish</span>
        <button className="btn" disabled={!!busy} onClick={() => handleStow(true)}>
          {busy === "stow" ? "…" : "Stow"}
        </button>
        <button className="btn" disabled={!!busy} onClick={() => handleStow(false)}>
          Unstow
        </button>
      </div>

      <div className="ctrl-row">
        <span className="ctrl-label">Reboot</span>
        {rebootConfirm ? (
          <>
            <span className="ctrl-confirm-label">Sure?</span>
            <button className="btn btn-danger" disabled={busy === "reboot"} onClick={handleReboot}>
              {busy === "reboot" ? "…" : "Yes, reboot"}
            </button>
            <button className="btn" onClick={() => setRebootConfirm(false)}>Cancel</button>
          </>
        ) : (
          <button className="btn btn-warn" disabled={!!busy} onClick={handleReboot}>Reboot</button>
        )}
      </div>

      <div className="ctrl-row">
        <span className="ctrl-label">Watchdog Mode</span>
        {(["LOG_ONLY", "MONITOR", "ENFORCE"] as const).map(m => (
          <button
            key={m}
            className={`btn ${config?.mode === m ? "btn-active" : ""}`}
            disabled={!!busy || config?.mode === m}
            onClick={() => handleModeChange(m)}
          >
            {busy === "mode" && config?.mode !== m ? "…" : m}
          </button>
        ))}
      </div>

      <div className="ctrl-divider" />

      <div className="ctrl-thresholds">
        <div className="ctrl-thresholds-title">Thresholds</div>
        <div className="ctrl-threshold-grid">
          <label>
            Poll interval (s)
            <input type="number" min={1} max={300} value={pollInterval}
              onChange={e => setPollInterval(+e.target.value)} />
          </label>
          <label>
            Deny debounce (s)
            <input type="number" min={1} max={3600} value={denyDebounce}
              onChange={e => setDenyDebounce(+e.target.value)} />
          </label>
          <label>
            Recover debounce (s)
            <input type="number" min={1} max={3600} value={recoverDebounce}
              onChange={e => setRecoverDebounce(+e.target.value)} />
          </label>
          <label>
            Min sats for good
            <input type="number" min={1} max={30} value={minSats}
              onChange={e => setMinSats(+e.target.value)} />
          </label>
        </div>
        <div className="ctrl-row">
          <button
            className={`btn ${cfgSaved ? "btn-active" : ""}`}
            disabled={!!busy}
            onClick={handleSaveThresholds}
          >
            {busy === "thresholds" ? "Saving…" : cfgSaved ? "Saved ✓" : "Save thresholds"}
          </button>
        </div>
      </div>
    </div>
  )
}
