import { GraduationCap, Stethoscope, Building2, ArrowRight } from 'lucide-react'

const CATEGORIES = [
  {
    id: 'university',
    icon: GraduationCap,
    title: 'University',
    subtitle: 'Riphah International University',
    description:
      'Admissions, programs, fee structures, campuses, departments, academic policies, and student services.',
    examples: [
      'What programs are offered at Riphah?',
      'How do I apply for admission?',
      'What is the MBBS fee structure?',
    ],
    gradient: 'from-blue-600 to-indigo-700',
    chipCls: 'bg-blue-50 text-blue-700',
    borderCls: 'border-blue-100 hover:border-blue-400 hover:shadow-blue-100',
  },
  {
    id: 'medical',
    icon: Stethoscope,
    title: 'Medical',
    subtitle: 'Riphah International Hospital',
    description:
      'Book doctor appointments, get health information, check symptoms, medications, and hospital services.',
    examples: [
      'Book a cardiology appointment',
      'What are symptoms of diabetes?',
      'Find an available specialist',
    ],
    gradient: 'from-teal-500 to-emerald-600',
    chipCls: 'bg-teal-50 text-teal-700',
    borderCls: 'border-teal-100 hover:border-teal-400 hover:shadow-teal-100',
  },
  {
    id: 'property',
    icon: Building2,
    title: 'Property',
    subtitle: 'Housing & Real Estate',
    description:
      'Find student housing, on-campus hostels, rental properties near Riphah campuses, and real estate queries.',
    examples: [
      'Student housing near Riphah Islamabad',
      'What dormitory options are available?',
      'Rental rates near campus',
    ],
    gradient: 'from-amber-500 to-orange-600',
    chipCls: 'bg-amber-50 text-amber-700',
    borderCls: 'border-amber-100 hover:border-amber-400 hover:shadow-amber-100',
  },
]

export default function CategoryPage({ user, onSelectCategory, onLogout }) {
  return (
    <div
      className="min-h-screen flex flex-col"
      style={{
        backgroundImage: 'url(/background_image.jpg)',
        backgroundSize: 'cover',
        backgroundPosition: 'center',
      }}
    >
      <div className="absolute inset-0 bg-black/65" />

      <div className="relative z-10 flex flex-col min-h-screen">
        {/* Header */}
        <header className="flex items-center justify-between px-6 py-4 shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-white flex items-center justify-center p-1 shadow-lg">
              <img src="/logo.png" alt="Riphah" className="w-full h-full object-contain rounded-lg" />
            </div>
            <div>
              <p className="text-white font-bold text-lg leading-tight">AskRiphah</p>
              <p className="text-slate-400 text-xs">Riphah International University</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-slate-300 text-sm">Hello, {user?.username}</span>
            <button
              onClick={onLogout}
              className="text-xs px-3 py-1.5 rounded-lg bg-white/10 text-slate-300 hover:bg-white/20 transition-colors"
            >
              Logout
            </button>
          </div>
        </header>

        {/* Hero */}
        <div className="flex-1 flex flex-col items-center justify-center px-6 py-8">
          <h1 className="text-4xl font-bold text-white text-center mb-3 drop-shadow">
            How can I help you today?
          </h1>
          <p className="text-slate-300 text-center max-w-lg mb-12 leading-relaxed text-sm">
            Select a category to open a dedicated AI assistant. Each one is specialized
            for its domain and grounded in Riphah&apos;s own data.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 w-full max-w-4xl">
            {CATEGORIES.map(cat => {
              const Icon = cat.icon
              return (
                <button
                  key={cat.id}
                  onClick={() => onSelectCategory(cat.id)}
                  className={`group relative bg-white rounded-2xl p-6 text-left border-2 ${cat.borderCls} transition-all duration-200 hover:shadow-2xl hover:-translate-y-1 cursor-pointer`}
                >
                  {/* Icon */}
                  <div className={`w-12 h-12 rounded-xl bg-gradient-to-br ${cat.gradient} flex items-center justify-center mb-4 shadow-md`}>
                    <Icon size={24} className="text-white" />
                  </div>

                  {/* Text */}
                  <h3 className="text-xl font-bold text-slate-800 mb-0.5">{cat.title}</h3>
                  <p className="text-xs text-slate-500 font-medium mb-3">{cat.subtitle}</p>
                  <p className="text-sm text-slate-600 leading-relaxed mb-4">{cat.description}</p>

                  {/* Example chips */}
                  <div className="space-y-1.5">
                    {cat.examples.map((ex, i) => (
                      <div key={i} className={`text-xs ${cat.chipCls} px-2.5 py-1.5 rounded-lg text-left`}>
                        &quot;{ex}&quot;
                      </div>
                    ))}
                  </div>

                  {/* Arrow */}
                  <div className="absolute top-5 right-5 text-slate-300 group-hover:text-slate-500 group-hover:translate-x-0.5 transition-all">
                    <ArrowRight size={18} />
                  </div>
                </button>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}
