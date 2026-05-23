import { useState } from 'react'
import { Eye, EyeOff, Loader2 } from 'lucide-react'

const API = 'http://127.0.0.1:8000'

export default function LoginPage({ onLogin, onGoRegister }) {
  const [email, setEmail]       = useState('')
  const [password, setPassword] = useState('')
  const [showPw, setShowPw]     = useState(false)
  const [error, setError]       = useState('')
  const [loading, setLoading]   = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res  = await fetch(`${API}/auth/login`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ email, password }),
      })
      const data = await res.json()
      if (!res.ok) { setError(data.detail || 'Login failed'); return }
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

        <form onSubmit={handleSubmit} className="bg-white/95 backdrop-blur-sm rounded-2xl shadow-2xl p-8 space-y-5">
          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg px-4 py-3">
              {error}
            </div>
          )}

          <div className="space-y-1.5">
            <label className="text-sm font-medium text-slate-700">Email</label>
            <input
              type="email" value={email} onChange={e => setEmail(e.target.value)}
              placeholder="you@riphah.edu.pk" required
              className="w-full px-4 py-2.5 rounded-xl border border-slate-300 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-sm font-medium text-slate-700">Password</label>
            <div className="relative">
              <input
                type={showPw ? 'text' : 'password'} value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••" required
                className="w-full px-4 py-2.5 pr-10 rounded-xl border border-slate-300 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
              />
              <button type="button" onClick={() => setShowPw(v => !v)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400">
                {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          <button type="submit" disabled={loading}
            className="w-full py-2.5 bg-teal-600 hover:bg-teal-700 disabled:bg-slate-300 text-white rounded-xl font-semibold text-sm transition-colors flex items-center justify-center gap-2">
            {loading ? <><Loader2 size={16} className="animate-spin" /> Signing in…</> : 'Sign In'}
          </button>

          <p className="text-center text-sm text-slate-500">
            No account?{' '}
            <button type="button" onClick={onGoRegister} className="text-teal-600 hover:underline font-medium">
              Register
            </button>
          </p>

          <div className="border-t border-slate-100 pt-4 text-xs text-slate-400 text-center">
            Default admin: <span className="font-mono">admin@medical.ai</span> / <span className="font-mono">admin123</span>
          </div>
        </form>
      </div>
    </div>
  )
}
