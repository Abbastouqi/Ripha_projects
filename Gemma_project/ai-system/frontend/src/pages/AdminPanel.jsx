import { useState, useEffect } from 'react'
import { Users, Calendar, BarChart2, Stethoscope, Shield, Trash2, ToggleLeft, ToggleRight, ArrowLeft, RefreshCw } from 'lucide-react'

const API = 'http://127.0.0.1:8000'

function authHeaders(token) {
  return { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }
}

function StatCard({ label, value, color }) {
  return (
    <div className={`rounded-2xl p-5 text-white ${color}`}>
      <p className="text-sm opacity-80">{label}</p>
      <p className="text-3xl font-bold mt-1">{value ?? '—'}</p>
    </div>
  )
}

function UsersTab({ token }) {
  const [users, setUsers]   = useState([])
  const [loading, setLoading] = useState(true)

  async function load() {
    setLoading(true)
    const res = await fetch(`${API}/admin/users`, { headers: authHeaders(token) })
    setUsers(await res.json())
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  async function toggleActive(id) {
    await fetch(`${API}/admin/users/${id}/toggle`, { method: 'PUT', headers: authHeaders(token) })
    load()
  }

  async function changeRole(id, role) {
    await fetch(`${API}/admin/users/${id}/role`, {
      method: 'PUT', headers: authHeaders(token),
      body: JSON.stringify({ role }),
    })
    load()
  }

  async function deleteUser(id, username) {
    if (!confirm(`Delete user "${username}"? This cannot be undone.`)) return
    await fetch(`${API}/admin/users/${id}`, { method: 'DELETE', headers: authHeaders(token) })
    load()
  }

  if (loading) return <p className="text-slate-500 text-sm p-4">Loading users…</p>

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-slate-800">All Users ({users.length})</h3>
        <button onClick={load} className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-700">
          <RefreshCw size={12} /> Refresh
        </button>
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-600 text-xs uppercase">
            <tr>
              {['ID', 'Username', 'Email', 'Role', 'Status', 'Joined', 'Actions'].map(h => (
                <th key={h} className="px-4 py-3 text-left font-semibold">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {users.map(u => (
              <tr key={u.id} className="hover:bg-slate-50">
                <td className="px-4 py-3 text-slate-400 font-mono text-xs">{u.id}</td>
                <td className="px-4 py-3 font-medium text-slate-800">{u.username}</td>
                <td className="px-4 py-3 text-slate-600">{u.email}</td>
                <td className="px-4 py-3">
                  <select value={u.role}
                    onChange={e => changeRole(u.id, e.target.value)}
                    className="text-xs border border-slate-200 rounded-lg px-2 py-1 bg-white">
                    <option value="user">user</option>
                    <option value="admin">admin</option>
                  </select>
                </td>
                <td className="px-4 py-3">
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${u.is_active ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-600'}`}>
                    {u.is_active ? 'Active' : 'Disabled'}
                  </span>
                </td>
                <td className="px-4 py-3 text-slate-500 text-xs">
                  {new Date(u.created_at).toLocaleDateString()}
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <button onClick={() => toggleActive(u.id)} title={u.is_active ? 'Disable' : 'Enable'}
                      className="text-slate-400 hover:text-amber-500 transition-colors">
                      {u.is_active ? <ToggleRight size={18} /> : <ToggleLeft size={18} />}
                    </button>
                    <button onClick={() => deleteUser(u.id, u.username)} title="Delete"
                      className="text-slate-400 hover:text-red-500 transition-colors">
                      <Trash2 size={15} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function AppointmentsTab({ token }) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(`${API}/admin/appointments`, { headers: authHeaders(token) })
      .then(r => r.json()).then(setItems).finally(() => setLoading(false))
  }, [])

  if (loading) return <p className="text-slate-500 text-sm p-4">Loading appointments…</p>

  return (
    <div>
      <h3 className="font-semibold text-slate-800 mb-4">All Appointments ({items.length})</h3>
      <div className="overflow-x-auto rounded-xl border border-slate-200">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-600 text-xs uppercase">
            <tr>
              {['ID', 'Patient', 'Doctor', 'Specialty', 'Date & Time', 'Reason', 'Status'].map(h => (
                <th key={h} className="px-4 py-3 text-left font-semibold">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {items.map(a => (
              <tr key={a.id} className="hover:bg-slate-50">
                <td className="px-4 py-3 text-slate-400 font-mono text-xs">{a.id}</td>
                <td className="px-4 py-3 text-slate-700">{a.patient_name || <span className="text-slate-400 italic">Guest</span>}</td>
                <td className="px-4 py-3 font-medium text-slate-800">{a.doctor_name}</td>
                <td className="px-4 py-3 text-slate-600 capitalize">{a.specialty}</td>
                <td className="px-4 py-3 text-slate-600 text-xs">{new Date(a.datetime).toLocaleString()}</td>
                <td className="px-4 py-3 text-slate-500 text-xs max-w-[150px] truncate">{a.reason || '—'}</td>
                <td className="px-4 py-3">
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium
                    ${a.status === 'confirmed' ? 'bg-green-100 text-green-700' : 'bg-slate-100 text-slate-600'}`}>
                    {a.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function DoctorsTab({ token }) {
  const [doctors, setDoctors] = useState([])

  useEffect(() => {
    fetch(`${API}/admin/doctors`, { headers: authHeaders(token) })
      .then(r => r.json()).then(setDoctors)
  }, [])

  return (
    <div>
      <h3 className="font-semibold text-slate-800 mb-4">Doctors ({doctors.length})</h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {doctors.map(d => (
          <div key={d.id} className="border border-slate-200 rounded-xl p-4 bg-white">
            <p className="font-medium text-slate-800">{d.name}</p>
            <p className="text-sm text-teal-600 capitalize mt-0.5">{d.specialty}</p>
            <p className="text-xs text-slate-400 mt-2">{d.available_days} · {d.available_hours}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

function StatsTab({ token }) {
  const [stats, setStats] = useState(null)

  useEffect(() => {
    fetch(`${API}/admin/stats`, { headers: authHeaders(token) })
      .then(r => r.json()).then(setStats)
  }, [])

  if (!stats) return <p className="text-slate-500 text-sm p-4">Loading stats…</p>

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
      <StatCard label="Total Users"            value={stats.total_users}            color="bg-blue-500" />
      <StatCard label="Chat Sessions"          value={stats.total_sessions}         color="bg-teal-500" />
      <StatCard label="Messages Sent"          value={stats.total_messages}         color="bg-purple-500" />
      <StatCard label="Confirmed Appointments" value={stats.confirmed_appointments} color="bg-green-500" />
      <StatCard label="Uploaded Documents"     value={stats.uploaded_documents}     color="bg-orange-500" />
    </div>
  )
}

const TABS = [
  { id: 'stats',        label: 'Overview',     icon: BarChart2 },
  { id: 'users',        label: 'Users',        icon: Users },
  { id: 'appointments', label: 'Appointments', icon: Calendar },
  { id: 'doctors',      label: 'Doctors',      icon: Stethoscope },
]

export default function AdminPanel({ token, user, onBack }) {
  const [tab, setTab] = useState('stats')

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 px-6 py-4 flex items-center gap-4">
        <button onClick={onBack} className="flex items-center gap-2 text-sm text-slate-500 hover:text-slate-800 transition-colors">
          <ArrowLeft size={16} /> Back to Chat
        </button>
        <div className="flex items-center gap-2 ml-2">
          <Shield size={18} className="text-teal-600" />
          <span className="font-semibold text-slate-800">Admin Panel</span>
        </div>
        <span className="ml-auto text-sm text-slate-500">Logged in as <strong>{user.username}</strong></span>
      </header>

      <div className="max-w-6xl mx-auto px-6 py-6">
        {/* Tabs */}
        <div className="flex gap-1 mb-6 bg-white rounded-xl border border-slate-200 p-1 w-fit">
          {TABS.map(t => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors
                ${tab === t.id ? 'bg-teal-600 text-white' : 'text-slate-600 hover:bg-slate-50'}`}>
              <t.icon size={15} />
              {t.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="bg-white rounded-2xl border border-slate-200 p-6">
          {tab === 'stats'        && <StatsTab        token={token} />}
          {tab === 'users'        && <UsersTab        token={token} />}
          {tab === 'appointments' && <AppointmentsTab token={token} />}
          {tab === 'doctors'      && <DoctorsTab      token={token} />}
        </div>
      </div>
    </div>
  )
}
