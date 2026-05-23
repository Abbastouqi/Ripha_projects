import { Plus, Trash2, GraduationCap, Stethoscope, Building2, ChevronLeft } from 'lucide-react'

const CATEGORY_META = {
  university: { label: 'University', Icon: GraduationCap, dot: 'bg-blue-500',  text: 'text-blue-400'  },
  medical:    { label: 'Medical',    Icon: Stethoscope,   dot: 'bg-teal-500',  text: 'text-teal-400'  },
  property:   { label: 'Property',   Icon: Building2,     dot: 'bg-amber-500', text: 'text-amber-400' },
}

export default function Sidebar({
  sessions, activeSessionId,
  onNewChat, onSelectSession, onDeleteSession,
  activeCategory, onChangeCategory,
}) {
  const cat = activeCategory ? CATEGORY_META[activeCategory] : null

  return (
    <aside className="w-64 shrink-0 flex flex-col h-full" style={{ background: '#0f172a', color: '#e2e8f0' }}>
      {/* Brand */}
      <div className="px-4 pt-4 pb-3 flex items-center gap-3 shrink-0">
        <div className="w-9 h-9 rounded-xl bg-white flex items-center justify-center shrink-0 p-0.5 shadow">
          <img src="/logo.png" alt="Riphah" className="w-full h-full object-contain rounded-lg" />
        </div>
        <span className="text-sm font-semibold text-white tracking-tight">AskRiphah</span>
      </div>

      {/* Active category badge with change button */}
      {cat && (
        <div className="px-3 pb-2 shrink-0">
          <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-slate-800 border border-slate-700">
            <div className={`w-5 h-5 rounded-md ${cat.dot} flex items-center justify-center shrink-0`}>
              <cat.Icon size={11} className="text-white" />
            </div>
            <span className={`text-xs font-medium ${cat.text} flex-1 truncate`}>{cat.label}</span>
            <button
              onClick={onChangeCategory}
              className="text-slate-600 hover:text-slate-300 transition-colors shrink-0"
              title="Change category"
            >
              <ChevronLeft size={14} />
            </button>
          </div>
        </div>
      )}

      {/* New chat */}
      <div className="px-3 pb-2 shrink-0">
        <button
          onClick={onNewChat}
          className="w-full flex items-center gap-2 px-3 py-2.5 rounded-xl border border-slate-700 hover:border-slate-500 hover:bg-slate-800 transition-colors text-sm font-medium text-slate-300"
        >
          <Plus size={15} />
          New Chat
        </button>
      </div>

      {/* Sessions */}
      <div className="flex-1 overflow-y-auto px-2 min-h-0 py-1">
        {sessions.length > 0 && (
          <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-600 px-2 mb-2">
            Recent
          </p>
        )}
        <div className="space-y-0.5">
          {sessions.map(s => (
            <div
              key={s.id}
              onClick={() => onSelectSession(s.id)}
              className={`group flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-colors
                ${activeSessionId === s.id
                  ? 'bg-slate-700 text-white'
                  : 'hover:bg-slate-800/70 text-slate-400 hover:text-slate-200'}`}
            >
              <span className="flex-1 truncate text-xs leading-relaxed">{s.title || 'New Chat'}</span>
              <button
                onClick={e => { e.stopPropagation(); onDeleteSession(s.id) }}
                className="opacity-0 group-hover:opacity-100 text-slate-600 hover:text-red-400 transition-all shrink-0 p-0.5"
              >
                <Trash2 size={11} />
              </button>
            </div>
          ))}
          {sessions.length === 0 && (
            <p className="text-xs text-slate-700 px-3 py-4 text-center">No conversations yet</p>
          )}
        </div>
      </div>
    </aside>
  )
}
