const BADGE_CONFIG = {
  general:              { label: 'General AI',      cls: 'bg-slate-100 text-slate-600' },
  medical_appointment:  { label: 'Appointment',     cls: 'bg-blue-100 text-blue-700' },
  hr_tasks:             { label: 'HR Assistant',    cls: 'bg-purple-100 text-purple-700' },
  medical_qa:           { label: 'Medical Q&A',     cls: 'bg-green-100 text-green-700' },
  document_chat:        { label: 'Document Chat',   cls: 'bg-orange-100 text-orange-700' },
}

export default function WorkflowBadge({ workflow }) {
  const cfg = BADGE_CONFIG[workflow] || BADGE_CONFIG.general
  return (
    <span className={`inline-block text-[10px] font-semibold px-2 py-0.5 rounded-full ${cfg.cls}`}>
      {cfg.label}
    </span>
  )
}
