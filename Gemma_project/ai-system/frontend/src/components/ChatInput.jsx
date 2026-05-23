import { useState, useRef } from 'react'
import { Send, Loader2, Paperclip, X, FileText } from 'lucide-react'

const CATEGORY_PLACEHOLDER = {
  university: 'Ask about admissions, programs, fees, campuses…',
  medical:    'Ask about appointments or health questions…',
  property:   'Ask about housing or rental properties…',
}

export default function ChatInput({ onSend, onFileUpload, disabled, category }) {
  const [text, setText]             = useState('')
  const [attachedFile, setAttached] = useState(null)
  const fileRef = useRef(null)

  function handleFileChange(e) {
    const file = e.target.files?.[0]
    if (file) setAttached(file)
    e.target.value = ''
  }

  async function handleSubmit(e) {
    e.preventDefault()
    if (disabled) return

    if (attachedFile) {
      const msg = text.trim()
      setAttached(null)
      setText('')
      await onFileUpload(attachedFile, msg)
      return
    }

    const trimmed = text.trim()
    if (!trimmed) return
    setText('')
    onSend(trimmed)
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  const canSend = !disabled && (text.trim() || attachedFile)

  return (
    <form onSubmit={handleSubmit} className="shrink-0 border-t border-slate-200 bg-white px-4 py-3">
      <div className="max-w-3xl mx-auto space-y-2">
        {/* Attached file chip */}
        {attachedFile && (
          <div className="flex items-center gap-2 px-3 py-1.5 bg-teal-50 border border-teal-200 rounded-xl w-fit max-w-xs">
            <FileText size={13} className="text-teal-600 shrink-0" />
            <span className="text-xs text-teal-700 font-medium truncate">{attachedFile.name}</span>
            <button
              type="button"
              onClick={() => setAttached(null)}
              className="text-teal-400 hover:text-teal-700 shrink-0 ml-1"
            >
              <X size={12} />
            </button>
          </div>
        )}

        <div className="flex items-end gap-2">
          {/* File attach button */}
          <input ref={fileRef} type="file" accept=".pdf,.docx,.txt" className="hidden" onChange={handleFileChange} />
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            disabled={disabled}
            title="Attach a document (PDF, DOCX, TXT)"
            className="w-10 h-10 rounded-xl border border-slate-300 hover:border-teal-500 hover:bg-teal-50 text-slate-400 hover:text-teal-600 disabled:opacity-40 flex items-center justify-center transition-colors shrink-0"
          >
            <Paperclip size={16} />
          </button>

          {/* Text area */}
          <div className="flex-1 flex items-end border border-slate-300 rounded-2xl px-4 py-2.5 focus-within:ring-2 focus-within:ring-teal-500 focus-within:border-teal-500 transition-all bg-white">
            <textarea
              value={text}
              onChange={e => setText(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={attachedFile ? 'Add a message (optional)…' : (CATEGORY_PLACEHOLDER[category] ?? 'Message… (Enter to send, Shift+Enter for new line)')}
              rows={1}
              disabled={disabled}
              className="flex-1 resize-none bg-transparent text-sm text-slate-800 placeholder-slate-400 outline-none max-h-32 overflow-y-auto"
              style={{ minHeight: '24px' }}
            />
          </div>

          {/* Send button */}
          <button
            type="submit"
            disabled={!canSend}
            className="w-10 h-10 rounded-xl bg-teal-600 hover:bg-teal-700 disabled:bg-slate-300 text-white flex items-center justify-center transition-colors shrink-0"
          >
            {disabled
              ? <Loader2 size={16} className="animate-spin" />
              : <Send size={16} />}
          </button>
        </div>

        <p className="text-[10px] text-slate-400 text-center">
          Workflows auto-detected · Attach a document to chat with it
        </p>
      </div>
    </form>
  )
}
