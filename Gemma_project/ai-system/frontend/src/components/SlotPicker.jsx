import { Calendar, Clock, User, Loader2, CheckCircle } from 'lucide-react'
import { useState } from 'react'

const API = 'http://localhost:8000'

export default function SlotPicker({ slots, workflowId, onConfirmed }) {
  const [confirming, setConfirming] = useState(null)
  const [confirmed,  setConfirmed]  = useState(null)

  async function handleSelect(slot) {
    if (confirming || confirmed) return
    setConfirming(slot.slot_id)
    try {
      const res = await fetch(`${API}/api/workflow/${workflowId}/confirm`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          slot_id:      slot.slot_id,
          doctor_name:  slot.doctor_name,
          specialty:    slot.specialty,
          date:         slot.date,
          time:         slot.time,
          datetime_iso: slot.datetime_iso || '',
        }),
      })
      if (!res.ok) throw new Error('confirm failed')
      setConfirmed(slot.slot_id)
      onConfirmed?.(slot)
    } catch {
      setConfirming(null)
    }
  }

  if (!slots?.length) return null

  return (
    <div className="mt-3 space-y-2">
      {slots.map(slot => {
        const isThis     = confirming === slot.slot_id
        const isDone     = confirmed  === slot.slot_id
        const isDisabled = !!(confirming || confirmed)

        return (
          <button
            key={slot.slot_id}
            onClick={() => handleSelect(slot)}
            disabled={isDisabled}
            className={`w-full text-left rounded-xl border px-4 py-3 transition-all
              ${isDone
                ? 'border-teal-500 bg-teal-50'
                : isDisabled
                  ? 'border-slate-200 bg-slate-50 opacity-50 cursor-not-allowed'
                  : 'border-slate-200 hover:border-teal-400 hover:bg-teal-50 cursor-pointer'
              }`}
          >
            <div className="flex items-center justify-between gap-3">
              <div className="flex-1 space-y-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <User size={13} className="text-teal-600 shrink-0" />
                  <span className="text-sm font-medium text-slate-800">
                    {slot.doctor_name?.startsWith('Dr.') ? slot.doctor_name : `Dr. ${slot.doctor_name}`}
                  </span>
                  <span className="text-[11px] bg-teal-100 text-teal-700 px-2 py-0.5 rounded-full capitalize">
                    {slot.specialty}
                  </span>
                </div>
                <div className="flex items-center gap-4 text-xs text-slate-500">
                  <span className="flex items-center gap-1"><Calendar size={11} /> {slot.date}</span>
                  <span className="flex items-center gap-1"><Clock size={11} /> {slot.time}</span>
                </div>
              </div>

              <div className="shrink-0">
                {isDone
                  ? <CheckCircle size={18} className="text-teal-600" />
                  : isThis
                    ? <Loader2 size={16} className="animate-spin text-teal-600" />
                    : <span className="text-xs font-medium text-teal-600">Select →</span>
                }
              </div>
            </div>
          </button>
        )
      })}
    </div>
  )
}
