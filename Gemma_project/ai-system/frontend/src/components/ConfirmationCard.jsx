import { CheckCircle2, Calendar, Clock, User, Hash, Bell } from 'lucide-react'

export default function ConfirmationCard({ booking }) {
  if (!booking || !Object.keys(booking).length) return null

  const refNum = booking.appointment_id || `APT-${booking.slot_id || '???'}`
  const doctorName = booking.doctor_name?.startsWith('Dr.')
    ? booking.doctor_name
    : `Dr. ${booking.doctor_name}`

  return (
    <div className="mt-3 bg-emerald-50 border border-emerald-200 rounded-2xl p-5">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-10 h-10 bg-emerald-500 rounded-full flex items-center justify-center shrink-0">
          <CheckCircle2 size={22} className="text-white" />
        </div>
        <div>
          <h3 className="font-semibold text-emerald-800">Appointment Confirmed!</h3>
          <p className="text-sm text-emerald-600">Your booking is all set</p>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-emerald-100 p-4 space-y-3">
        <Row icon={<User size={15} className="text-teal-600" />}    label="Doctor"    value={doctorName} />
        <Row icon={<Bell size={15} className="text-teal-600" />}    label="Specialty" value={capitalize(booking.specialty)} />
        <Row icon={<Calendar size={15} className="text-teal-600" />} label="Date"     value={booking.date} />
        <Row icon={<Clock size={15} className="text-teal-600" />}   label="Time"      value={booking.time} />
        <div className="border-t border-slate-100 pt-3">
          <Row icon={<Hash size={15} className="text-slate-400" />} label="Ref #" value={String(refNum)} mono />
        </div>
      </div>

      <p className="text-xs text-emerald-600 mt-3 text-center">
        Please arrive 15 minutes before your scheduled time.
      </p>
    </div>
  )
}

function capitalize(str) {
  if (!str) return ''
  return str.charAt(0).toUpperCase() + str.slice(1)
}

function Row({ icon, label, value, mono }) {
  return (
    <div className="flex items-center gap-3">
      <span className="shrink-0">{icon}</span>
      <span className="text-xs text-slate-500 w-20 shrink-0">{label}</span>
      <span className={`text-sm font-medium text-slate-800 ${mono ? 'font-mono' : ''}`}>{value}</span>
    </div>
  )
}
