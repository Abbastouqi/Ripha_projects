import { useEffect, useRef, useState } from 'react'
import { CheckCircle2, Circle, Loader2, XCircle, Clock } from 'lucide-react'

const STEP_ORDER = [
  'verify_patient',
  'find_slots',
  'present_options',
  'confirm_booking',
  'update_ehr',
  'send_confirmation',
]

const STEP_LABELS = {
  verify_patient:    { label: 'Verify Patient',     agent: 'Auth Agent' },
  find_slots:        { label: 'Find Available Slots', agent: 'Schedule Agent' },
  present_options:   { label: 'Present Options',    agent: 'UI Agent' },
  confirm_booking:   { label: 'Confirm Booking',    agent: 'Schedule Agent' },
  update_ehr:        { label: 'Update EHR Record',  agent: 'EHR Agent' },
  send_confirmation: { label: 'Send Confirmation',  agent: 'Notify Agent' },
}

function StepIcon({ stepStatus }) {
  if (stepStatus === 'completed') return <CheckCircle2 size={20} className="text-emerald-500" />
  if (stepStatus === 'running')   return <Loader2 size={20} className="text-blue-500 animate-spin" />
  if (stepStatus === 'error')     return <XCircle size={20} className="text-red-500" />
  return <Circle size={20} className="text-slate-300" />
}

function getStepStatus(stepKey, stepResults, workflowStatus, currentStepIndex, index) {
  if (stepResults[stepKey]) {
    const r = stepResults[stepKey]
    if (r.status === 'error') return 'error'
    return 'completed'
  }
  if (workflowStatus === 'started' || workflowStatus === 'running') {
    if (index === currentStepIndex) return 'running'
  }
  return 'pending'
}

export default function WorkflowProgress({ workflowId, onSlotsReady, onComplete }) {
  const [stepResults, setStepResults] = useState({})
  const [status, setStatus]           = useState('started')
  const [slots, setSlots]             = useState([])
  const [booking, setBooking]         = useState(null)
  const [notice, setNotice]           = useState('')
  const wsRef = useRef(null)

  useEffect(() => {
    if (!workflowId) return

    const poll = setInterval(async () => {
      try {
        const res  = await fetch(`/api/workflow/${workflowId}`)
        const data = await res.json()
        setStepResults(data.step_results || {})
        setStatus(data.status || 'started')
        if (data.no_specialist_notice) setNotice(data.no_specialist_notice)
        if (data.available_slots?.length) setSlots(data.available_slots)
        if (data.booking && Object.keys(data.booking).length) {
          setBooking(data.booking)
          onComplete?.(data.booking)
        }
        if (data.awaiting_input === 'slot_selection' && data.available_slots?.length) {
          onSlotsReady?.(data.available_slots, workflowId)
        }
        if (['completed', 'error'].includes(data.status)) {
          clearInterval(poll)
        }
      } catch (_) {}
    }, 1200)

    // Also try WebSocket
    try {
      const wsUrl = `ws://localhost:8000/api/workflow/${workflowId}/stream`
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws
      ws.onmessage = (e) => {
        const data = JSON.parse(e.data)
        if (data.step_results)  setStepResults(data.step_results)
        if (data.status)        setStatus(data.status)
        if (data.available_slots?.length) setSlots(data.available_slots)
        if (data.booking && Object.keys(data.booking || {}).length) {
          setBooking(data.booking)
          onComplete?.(data.booking)
        }
        if (data.awaiting_input === 'slot_selection' && data.available_slots?.length) {
          onSlotsReady?.(data.available_slots, workflowId)
        }
      }
    } catch (_) {}

    return () => {
      clearInterval(poll)
      wsRef.current?.close()
    }
  }, [workflowId])

  const completedCount = Object.keys(stepResults).length
  const currentStepIndex = Math.min(completedCount, STEP_ORDER.length - 1)

  const statusColor = {
    started:        'bg-blue-100 text-blue-700',
    running:        'bg-blue-100 text-blue-700',
    awaiting_input: 'bg-amber-100 text-amber-700',
    completed:      'bg-emerald-100 text-emerald-700',
    error:          'bg-red-100 text-red-700',
  }[status] || 'bg-slate-100 text-slate-600'

  return (
    <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h3 className="font-semibold text-slate-800 text-sm">Workflow Progress</h3>
          <p className="text-xs text-slate-400 mt-0.5 font-mono">{workflowId}</p>
        </div>
        <span className={`text-xs font-medium px-2.5 py-1 rounded-full ${statusColor}`}>
          {status.replace('_', ' ').toUpperCase()}
        </span>
      </div>

      {notice && (
        <div className="mb-4 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 text-xs text-amber-700">
          ⚠ {notice}
        </div>
      )}

      <ol className="relative space-y-0">
        {STEP_ORDER.map((key, index) => {
          const stepStatus = getStepStatus(key, stepResults, status, currentStepIndex, index)
          const info       = STEP_LABELS[key] || { label: key, agent: '' }
          const result     = stepResults[key]

          const barColor =
            stepStatus === 'completed' ? 'bg-emerald-400'
            : stepStatus === 'running'  ? 'bg-blue-400'
            : stepStatus === 'error'    ? 'bg-red-400'
            : 'bg-slate-200'

          return (
            <li key={key} className="flex gap-3 pb-5 last:pb-0">
              {/* Vertical line */}
              <div className="flex flex-col items-center">
                <StepIcon stepStatus={stepStatus} />
                {index < STEP_ORDER.length - 1 && (
                  <div className={`w-0.5 flex-1 mt-1 ${barColor} transition-colors duration-500`} />
                )}
              </div>

              {/* Content */}
              <div className="flex-1 pt-0.5 pb-1 min-h-[32px]">
                <p className={`text-sm font-medium leading-tight ${
                  stepStatus === 'pending' ? 'text-slate-400' : 'text-slate-800'
                }`}>
                  {info.label}
                </p>
                <p className="text-xs text-slate-400 mt-0.5">{info.agent}</p>
                {result && stepStatus === 'completed' && (
                  <p className="text-xs text-emerald-600 mt-1 truncate">
                    ✓ {result.status || 'done'}{result.count !== undefined ? ` (${result.count} found)` : ''}
                  </p>
                )}
                {result && stepStatus === 'error' && (
                  <p className="text-xs text-red-500 mt-1">✗ {result.message || 'failed'}</p>
                )}
              </div>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
