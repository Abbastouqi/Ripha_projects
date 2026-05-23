import { useState } from 'react'
import { Loader2 } from 'lucide-react'

const API = 'http://127.0.0.1:8000'

export default function RegisterPage({ onLogin, onGoLogin }) {
  const [username, setUsername] = useState('')
  const [email, setEmail]       = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm]   = useState('')
  const [error, setError]       = useState('')
  const [loading, setLoading]   = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    if (password !== confirm) { setError('Passwords do not match'); return }
    if (password.length < 6)  { setError('Password must be at least 6 characters'); return }
    setLoading(true)
    try {
      const res  = await fetch(`${API}/auth/register`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ username, email, password }),
      })
      const data = await res.json()
      if (!res.ok) { setError(data.detail || 'Registration failed'); return }
      onLogin(data.token, data.user)
    } catch {
      setError('Cannot reach server. Is the backend running?')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      className="min-h-screen flex items-center justify-center px-4"
      style={{
        backgroundImage: 'url(/background_image.jpg)',
        backgroundSize: 'cover',
        backgroundPosition: 'center',
      }}
    >
      {/* Dark overlay */}
      <div className="absolute inset-0 bg-black/55" />

      <div className="relative z-10 w-full max-w-md">
        {/* Logo + title */}
        <div className="flex flex-col items-center mb-7">
          <div className="w-24 h-24 rounded-2xl bg-white flex items-center justify-center mb-4 shadow-2xl p-1.5">
            <img src="/logo.png" alt="Riphah" className="w-full h-full object-contain rounded-xl" />
          </div>
          <h1 className="text-3xl font-bold text-white tracking-tight drop-shadow">AskRiphah</h1>
          <p className="text-slate-300 text-sm mt-1">Riphah International University</p>
        </div>

        <form onSubmit={handleSubmit} className="bg-white/95 backdrop-blur-sm rounded-2xl shadow-2xl p-8 space-y-4">
          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg px-4 py-3">{error}</div>
          )}

          {[
            { label: 'Username', value: username, set: setUsername, type: 'text',     ph: 'Full Name' },
            { label: 'Email',    value: email,    set: setEmail,    type: 'email',    ph: 'you@riphah.edu.pk' },
            { label: 'Password', value: password, set: setPassword, type: 'password', ph: '••••••••' },
            { label: 'Confirm Password', value: confirm, set: setConfirm, type: 'password', ph: '••••••••' },
          ].map(({ label, value, set, type, ph }) => (
            <div key={label} className="space-y-1.5">
              <label className="text-sm font-medium text-slate-700">{label}</label>
              <input type={type} value={value} onChange={e => set(e.target.value)}
                placeholder={ph} required
                className="w-full px-4 py-2.5 rounded-xl border border-slate-300 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
              />
            </div>
          ))}

          <button type="submit" disabled={loading}
            className="w-full py-2.5 bg-teal-600 hover:bg-teal-700 disabled:bg-slate-300 text-white rounded-xl font-semibold text-sm transition-colors flex items-center justify-center gap-2">
            {loading ? <><Loader2 size={16} className="animate-spin" /> Creating account…</> : 'Create Account'}
          </button>

          <p className="text-center text-sm text-slate-500">
            Already have an account?{' '}
            <button type="button" onClick={onGoLogin} className="text-teal-600 hover:underline font-medium">
              Sign in
            </button>
          </p>
        </form>
      </div>
    </div>
  )
}
