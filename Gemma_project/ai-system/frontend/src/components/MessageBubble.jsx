import { useState } from 'react'
import { ChevronDown, ChevronUp, FileText, CheckCircle, AlertCircle, Info, FileDown } from 'lucide-react'
import WorkflowBadge from './WorkflowBadge'
import SlotPicker from './SlotPicker'
import ConfirmationCard from './ConfirmationCard'
import AdmissionProgress from './AdmissionProgress'

function renderContent(text) {
  return text.split('\n').map((line, i, arr) => {
    const parts = line.split(/(\*\*[^*]+\*\*)/)
    return (
      <span key={i}>
        {parts.map((part, j) =>
          part.startsWith('**') && part.endsWith('**')
            ? <strong key={j}>{part.slice(2, -2)}</strong>
            : part
        )}
        {i < arr.length - 1 && <br />}
      </span>
    )
  })
}

function SystemMessage({ message }) {
  const cfg = {
    file:    { icon: FileText,    style: 'bg-blue-50 border-blue-200 text-blue-700' },
    success: { icon: CheckCircle, style: 'bg-teal-50 border-teal-200 text-teal-700' },
    error:   { icon: AlertCircle, style: 'bg-red-50 border-red-200 text-red-700'   },
    info:    { icon: Info,        style: 'bg-slate-50 border-slate-200 text-slate-600' },
  }
  const { icon: Icon, style } = cfg[message.systemType] ?? cfg.info
  return (
    <div className="flex justify-center px-4 py-1.5">
      <div className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl border text-xs font-medium max-w-md ${style}`}>
        <Icon size={13} className="shrink-0" />
        <span>{message.content}</span>
      </div>
    </div>
  )
}

export default function MessageBubble({ message, onSlotConfirmed }) {
  const [sourcesOpen, setSourcesOpen] = useState(false)

  if (message.role === 'system') return <SystemMessage message={message} />

  if (message.role === 'user') {
    return (
      <div className="flex justify-end px-4 py-1">
        <div className="max-w-[75%] bg-slate-100 text-slate-800 rounded-2xl rounded-tr-sm px-4 py-3 text-sm leading-relaxed">
          {message.content}
        </div>
      </div>
    )
  }

  // Assistant message
  return (
    <div className="flex items-start gap-3 px-4 py-1">
      <div className="w-7 h-7 rounded-full bg-teal-600 flex items-center justify-center text-white text-[10px] font-bold shrink-0 mt-1">
        AI
      </div>
      <div className="max-w-[82%] space-y-1.5">
        {/* Text bubble */}
        <div className="bg-white border border-slate-200 rounded-2xl rounded-tl-sm px-4 py-3 text-sm text-slate-800 leading-relaxed">
          {renderContent(message.content)}
        </div>

        {/* Live portal automation progress panel */}
        {message.admission_session_id && (
          <AdmissionProgress sessionId={message.admission_session_id} />
        )}

        {/* PDF download button — rendered when admission workflow completes */}
        {message.download_url && (
          <a
            href={`http://localhost:8000${message.download_url}`}
            download
            className="flex items-center gap-2 mt-2 px-4 py-2.5 bg-teal-600 hover:bg-teal-700 text-white text-sm font-medium rounded-xl w-fit transition-colors shadow-sm"
          >
            <FileDown size={16} />
            Download Application PDF
          </a>
        )}

        {/* Interactive slot picker — rendered inline when appointment workflow returns slots */}
        {message.slots?.length > 0 && !message.booking && (
          <SlotPicker
            slots={message.slots}
            workflowId={message.appointmentWorkflowId}
            onConfirmed={(slot) => onSlotConfirmed?.(slot)}
          />
        )}

        {/* Confirmation card — shown after booking */}
        {message.booking && Object.keys(message.booking).length > 0 && (
          <ConfirmationCard booking={message.booking} />
        )}

        {/* Workflow badge + sources */}
        <div className="flex items-center gap-2 pl-0.5">
          {message.workflow && message.workflow !== 'general' && (
            <WorkflowBadge workflow={message.workflow} />
          )}
          {message.sources?.length > 0 && (
            <button
              onClick={() => setSourcesOpen(v => !v)}
              className="flex items-center gap-1 text-[10px] text-slate-400 hover:text-slate-600 transition-colors"
            >
              {sourcesOpen ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
              {message.sources.length} source{message.sources.length !== 1 ? 's' : ''}
            </button>
          )}
        </div>

        {sourcesOpen && message.sources?.length > 0 && (
          <div className="space-y-1">
            {message.sources.map((src, i) => (
              <div key={i} className="text-[11px] text-slate-500 bg-slate-50 border border-slate-100 rounded-lg px-3 py-2 leading-relaxed">
                {src.slice(0, 220)}{src.length > 220 ? '…' : ''}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
