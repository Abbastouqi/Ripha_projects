import { useEffect, useRef } from 'react'
import { GraduationCap, Stethoscope, Building2, MessageCircle, Activity } from 'lucide-react'
import MessageBubble from './MessageBubble'
import TypingIndicator from './TypingIndicator'

const CATEGORY_PROMPTS = {
  university: [
    { icon: <GraduationCap size={16} />, text: 'What programs are offered at Riphah?' },
    { icon: <GraduationCap size={16} />, text: 'What is the fee structure for MBBS?' },
    { icon: <GraduationCap size={16} />, text: 'How do I apply for admission?' },
    { icon: <GraduationCap size={16} />, text: 'Which campuses does Riphah have?' },
  ],
  medical: [
    { icon: <Stethoscope size={16} />, text: 'I need to book a cardiology appointment' },
    { icon: <Activity size={16} />,    text: 'What are the symptoms of diabetes?' },
    { icon: <Stethoscope size={16} />, text: 'Book a dermatologist appointment' },
    { icon: <Activity size={16} />,    text: 'Common side effects of ibuprofen?' },
  ],
  property: [
    { icon: <Building2 size={16} />, text: 'Student housing near Riphah Islamabad' },
    { icon: <Building2 size={16} />, text: 'What dormitory options are available?' },
    { icon: <Building2 size={16} />, text: 'Rental rates near Riphah campus' },
    { icon: <Building2 size={16} />, text: 'Are there on-campus hostels?' },
  ],
  default: [
    { icon: <GraduationCap size={16} />, text: 'How do I apply for admission at Riphah?' },
    { icon: <Stethoscope size={16} />,   text: 'I need to book a doctor appointment' },
    { icon: <Activity size={16} />,      text: 'What are symptoms of diabetes?' },
    { icon: <MessageCircle size={16} />, text: 'What programs does Riphah offer?' },
  ],
}

const CATEGORY_STYLE = {
  university: {
    title:    'University Assistant',
    subtitle: 'Ask about admissions, programs, fee structures, campuses, and academic policies.',
    btnCls:   'hover:border-blue-400 hover:bg-blue-50',
    iconCls:  'text-blue-500',
  },
  medical: {
    title:    'Medical Assistant',
    subtitle: 'Book appointments, ask about symptoms, medications, and hospital services.',
    btnCls:   'hover:border-teal-400 hover:bg-teal-50',
    iconCls:  'text-teal-500',
  },
  property: {
    title:    'Property Assistant',
    subtitle: 'Find student housing, rental properties, and campus accommodation.',
    btnCls:   'hover:border-amber-400 hover:bg-amber-50',
    iconCls:  'text-amber-500',
  },
}

export default function ChatWindow({ messages, isLoading, onPromptClick, onSlotConfirmed, activeCategory }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  if (messages.length === 0 && !isLoading) {
    const prompts = CATEGORY_PROMPTS[activeCategory] || CATEGORY_PROMPTS.default
    const style   = activeCategory ? CATEGORY_STYLE[activeCategory] : null

    return (
      <div className="flex-1 flex flex-col items-center justify-center px-6 text-center select-none">
        <div className="w-20 h-20 rounded-2xl bg-white flex items-center justify-center mb-4 shadow-lg border border-slate-100 p-1.5">
          <img src="/logo.png" alt="AskRiphah" className="w-full h-full object-contain rounded-xl" />
        </div>
        <h2 className="text-xl font-semibold text-slate-800 mb-1">
          {style?.title ?? 'How can I help you today?'}
        </h2>
        <p className="text-sm text-slate-500 mb-8 max-w-sm leading-relaxed">
          {style?.subtitle ?? 'Select a topic below or type your question.'}
        </p>
        <div className="grid grid-cols-2 gap-3 w-full max-w-lg">
          {prompts.map((p, i) => (
            <button
              key={i}
              onClick={() => onPromptClick?.(p.text)}
              className={`flex items-start gap-3 text-left px-4 py-3 rounded-xl border border-slate-200 ${style?.btnCls ?? 'hover:border-teal-400 hover:bg-teal-50'} transition-all text-sm text-slate-700`}
            >
              <span className={`${style?.iconCls ?? 'text-teal-500'} shrink-0 mt-0.5`}>{p.icon}</span>
              {p.text}
            </button>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto py-6 space-y-1">
      {messages.map((msg, i) => (
        <MessageBubble key={i} message={msg} onSlotConfirmed={onSlotConfirmed} />
      ))}
      {isLoading && <TypingIndicator />}
      <div ref={bottomRef} />
    </div>
  )
}
