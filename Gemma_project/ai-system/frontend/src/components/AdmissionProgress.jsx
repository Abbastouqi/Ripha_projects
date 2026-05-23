import { useEffect, useRef, useState } from 'react'
import { CheckCircle, XCircle, Loader2, Globe, Camera, ExternalLink, KeyRound, MailCheck, ShieldAlert } from 'lucide-react'

const API = 'http://127.0.0.1:8000'
const WS  = 'ws://127.0.0.1:8000'

export default function AdmissionProgress({ sessionId }) {
  const [steps,  setSteps]  = useState([])
  const [status, setStatus] = useState('connecting')
  const [result, setResult] = useState(null)
  const bottomRef = useRef(null)
  const wsRef     = useRef(null)

  useEffect(() => {
    if (!sessionId) return

    const ws = new WebSocket(`${WS}/api/admission/${sessionId}/stream`)
    wsRef.current = ws

    ws.onopen  = () => setStatus('running')
    ws.onclose = () => setStatus(s => s === 'running' ? 'error' : s)

    ws.onmessage = (e) => {
      const data = JSON.parse(e.data)

      if (data.type === 'step') {
        setSteps(prev => [...prev, {
          message:        data.message,
          success:        data.success,
          step_type:      data.step_type,
          screenshot_url: data.screenshot_url || null,
        }])
      } else if (data.type === 'complete') {
        setSteps(prev => [...prev, {
          message:   data.success ? 'Application submitted successfully!' : data.message,
          success:   data.success,
          step_type: 'final',
        }])
        setResult(data)
        setStatus('complete')
        ws.close()
      } else if (data.type === 'error') {
        setSteps(prev => [...prev, { message: data.message, success: false, step_type: 'error' }])
        setStatus('error')
      }
    }

    return () => ws.close()
  }, [sessionId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [steps])

  if (!sessionId) return null

  return (
    <div className="mt-3 rounded-xl border border-teal-200 bg-teal-50 overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-2.5 bg-teal-600 text-white">
        <Globe size={14} />
        <span className="text-sm font-semibold">Admission Portal Automation — Live</span>
        {status === 'running'  && <Loader2 size={13} className="animate-spin ml-auto" />}
        {status === 'complete' && <CheckCircle size={14} className="ml-auto text-teal-200" />}
        {status === 'error'    && <XCircle size={14} className="ml-auto text-red-300" />}
      </div>

      {/* Steps + inline screenshots */}
      <div className="px-4 py-3 space-y-2 max-h-96 overflow-y-auto">
        {status === 'connecting' && (
          <div className="flex items-center gap-2 text-sm text-teal-600">
            <Loader2 size={13} className="animate-spin shrink-0" />
            Connecting to automation stream...
          </div>
        )}

        {steps.map((step, i) => {
          const isLast    = i === steps.length - 1
          const isRunning = isLast && status === 'running'
          const isScreenshot = step.step_type === 'screenshot'

          return (
            <div key={i} className="space-y-1.5">
              {/* Step row */}
              <div className={`flex items-start gap-2 text-sm ${
                step.success === false ? 'text-red-600' : 'text-slate-700'
              }`}>
                {isRunning ? (
                  <Loader2 size={13} className="animate-spin shrink-0 mt-0.5 text-teal-600" />
                ) : step.success === false ? (
                  <XCircle size={13} className="shrink-0 mt-0.5 text-red-500" />
                ) : isScreenshot ? (
                  <Camera size={13} className="shrink-0 mt-0.5 text-teal-500" />
                ) : (
                  <CheckCircle size={13} className="shrink-0 mt-0.5 text-teal-600" />
                )}
                <span className="leading-snug">{step.message}</span>
              </div>

              {/* Inline screenshot thumbnail */}
              {isScreenshot && step.screenshot_url && (
                <div className="ml-5">
                  <a
                    href={`${API}${step.screenshot_url}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block w-fit"
                  >
                    <img
                      src={`${API}${step.screenshot_url}`}
                      alt={step.message}
                      className="h-36 w-auto rounded-lg border border-teal-200 shadow-sm hover:border-teal-400 cursor-zoom-in transition-all object-cover"
                      onError={e => { e.currentTarget.style.display = 'none' }}
                    />
                  </a>
                </div>
              )}
            </div>
          )
        })}

        <div ref={bottomRef} />
      </div>

      {/* Final result banner */}
      {status === 'complete' && result && (
        <div className={`px-4 py-3 border-t text-sm font-medium ${
          result.success
            ? 'bg-teal-100 border-teal-200 text-teal-800'
            : 'bg-amber-50 border-amber-200 text-amber-800'
        }`}>
          {result.success ? '🎉 ' : '⚠ '}
          {result.message}
          {result.reference && (
            <span className="ml-2 font-mono bg-white/70 px-2 py-0.5 rounded text-xs">
              Ref: {result.reference}
            </span>
          )}
        </div>
      )}

      {/* Email verification notice */}
      {status === 'complete' && result?.needs_verification && (
        <div className="px-4 py-3 border-t border-amber-200 bg-amber-50 text-sm space-y-2">
          <div className="flex items-center gap-2 font-semibold text-amber-800">
            {result.verification_type === 'otp' ? <ShieldAlert size={14} /> : <MailCheck size={14} />}
            {result.verification_type === 'otp' ? 'OTP Verification Required' : 'Email Verification Required'}
          </div>
          <ol className="list-decimal list-inside space-y-1 text-amber-700 text-xs leading-relaxed">
            {result.verification_type === 'otp' ? (
              <>
                <li>Check your phone or email for the OTP</li>
                <li>Enter it on the portal</li>
                <li>Then log in with your credentials below</li>
              </>
            ) : (
              <>
                <li>Check your inbox <span className="font-medium">and spam folder</span></li>
                <li>Click the verification link from Riphah</li>
                <li>Then log in with your credentials below</li>
              </>
            )}
          </ol>
        </div>
      )}

      {/* Portal credentials + guide */}
      {status === 'complete' && result && (result.portal_email || result.portal_password) && (
        <div className="border-t border-teal-200 bg-white divide-y divide-slate-100">
          <div className="px-4 py-3 space-y-2">
            <div className="flex items-center gap-1.5 text-sm font-semibold text-slate-700">
              <ExternalLink size={13} />
              How to check your application
            </div>
            <ol className="space-y-2 text-xs text-slate-600">
              <li className="flex gap-2">
                <span className="flex-shrink-0 w-5 h-5 rounded-full bg-teal-100 text-teal-700 text-[10px] font-bold flex items-center justify-center">1</span>
                <span>
                  Open:{' '}
                  <a href={result.dashboard_url || 'https://admissions.riphah.edu.pk/'} target="_blank" rel="noopener noreferrer"
                    className="font-medium text-teal-600 hover:text-teal-800 underline underline-offset-2 break-all">
                    {result.dashboard_url || 'admissions.riphah.edu.pk'}
                  </a>
                </span>
              </li>
              <li className="flex gap-2">
                <span className="flex-shrink-0 w-5 h-5 rounded-full bg-teal-100 text-teal-700 text-[10px] font-bold flex items-center justify-center">2</span>
                <span>
                  Log in:&nbsp;
                  <span className="font-mono bg-slate-100 px-1.5 py-0.5 rounded text-slate-800">{result.portal_email}</span>
                  {' / '}
                  <span className="font-mono bg-slate-100 px-1.5 py-0.5 rounded text-slate-800">{result.portal_password}</span>
                </span>
              </li>
              <li className="flex gap-2">
                <span className="flex-shrink-0 w-5 h-5 rounded-full bg-teal-100 text-teal-700 text-[10px] font-bold flex items-center justify-center">3</span>
                <span>Click <strong>"My Applications"</strong> to see your status</span>
              </li>
            </ol>
            <a href={result.dashboard_url || 'https://admissions.riphah.edu.pk/'} target="_blank" rel="noopener noreferrer"
              className="mt-1 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-teal-600 hover:bg-teal-700 text-white text-xs font-semibold transition-colors">
              <ExternalLink size={11} />
              Open Portal
            </a>
          </div>

          <div className="px-4 py-2.5 flex flex-wrap gap-4 text-xs">
            <div className="flex items-center gap-1.5 text-slate-500">
              <KeyRound size={11} className="text-teal-600" />
              <span className="text-slate-400">Email:</span>
              <span className="font-mono text-slate-700 select-all">{result.portal_email}</span>
            </div>
            <div className="flex items-center gap-1.5 text-slate-500">
              <KeyRound size={11} className="text-teal-600" />
              <span className="text-slate-400">Password:</span>
              <span className="font-mono text-slate-700 select-all">{result.portal_password}</span>
            </div>
          </div>
        </div>
      )}

      {/* Final screenshots gallery (from result) */}
      {status === 'complete' && result?.screenshot_urls?.length > 0 && (
        <div className="px-4 py-3 border-t border-teal-200 bg-white">
          <div className="flex items-center gap-1.5 text-sm font-semibold text-slate-700 mb-3">
            <Camera size={13} />
            All Screenshots
          </div>
          <div className="flex flex-wrap gap-3">
            {result.screenshot_urls.map((item, i) => {
              const url   = typeof item === 'string' ? item : item.url
              const label = typeof item === 'string' ? `Screenshot ${i + 1}` : item.label
              const full  = `${API}${url}`
              return (
                <div key={i} className="flex flex-col items-center gap-1">
                  <a href={full} target="_blank" rel="noopener noreferrer">
                    <img src={full} alt={label}
                      className="h-28 w-auto rounded border border-slate-200 hover:border-teal-400 transition-colors cursor-zoom-in object-cover shadow-sm" />
                  </a>
                  <span className="text-[10px] text-slate-500 text-center max-w-[110px] leading-tight">{label}</span>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
