import { useState } from "react"
import type { FormEvent } from "react"
import { login } from "./api"

interface Props {
  onLogin: (username: string) => void
}

export default function Login({ onLogin }: Props) {
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const me = await login(username, password)
      onLogin(me.username)
    } catch {
      setError("Invalid username or password")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-wrap">
      <form className="login-form" onSubmit={handleSubmit}>
        <h1>Starlink Console</h1>
        {error && <div className="login-error">{error}</div>}
        <label>
          Username
          <input
            type="text"
            autoComplete="username"
            value={username}
            onChange={e => setUsername(e.target.value)}
            required
          />
        </label>
        <label>
          Password
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            required
          />
        </label>
        <button type="submit" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  )
}
