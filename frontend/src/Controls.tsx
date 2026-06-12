import { useState } from "react"
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
    </div>
  )
}
