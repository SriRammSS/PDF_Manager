import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { auth } from '../api/client'

export default function SignupPage() {
  const [email, setEmail] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [password, setPassword] = useState('')
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setErrors({})
    const next: Record<string, string> = {}
    if (!email.trim()) next.email = 'Email is required'
    if (!displayName.trim()) next.displayName = 'Display name is required'
    if (!password) next.password = 'Password is required'
    else if (password.length < 8) next.password = 'Password must be at least 8 characters'
    else if (!/[A-Z]/.test(password)) next.password = 'Password must contain an uppercase letter'
    else if (!/\d/.test(password)) next.password = 'Password must contain a digit'
    setErrors(next)
    if (Object.keys(next).length) return

    setLoading(true)
    try {
      await auth.signup(email.trim(), displayName.trim(), password)
      toast.success('Account created! Please sign in.')
      navigate('/login')
    } catch (err: unknown) {
      const res = (err as { response?: { data?: { detail?: string | Array<{ msg?: string }> } } })
        ?.response?.data
      let msg = 'Signup failed'
      if (res?.detail) {
        msg = typeof res.detail === 'string'
          ? res.detail
          : Array.isArray(res.detail) && res.detail[0]?.msg
            ? res.detail[0].msg
            : String(res.detail)
      }
      toast.error(msg)
      setErrors((p) => ({ ...p, form: msg }))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#0a0e17] px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-bold text-white">PDF Manager</h1>
          <p className="mt-1 text-sm text-gray-400">Create your account</p>
        </div>
        <form
          onSubmit={handleSubmit}
          className="rounded-lg border border-gray-700 bg-[#0f172a] p-6 shadow-xl"
        >
          {errors.form && (
            <p className="mb-4 rounded bg-red-500/20 px-3 py-2 text-sm text-red-400">
              {errors.form}
            </p>
          )}
          <div className="mb-4">
            <label className="mb-1 block text-sm text-gray-300">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded border border-gray-600 bg-[#0a0e17] px-3 py-2 text-white placeholder-gray-500 focus:border-[#60a5fa] focus:outline-none"
              placeholder="you@example.com"
              autoComplete="email"
            />
            {errors.email && <p className="mt-1 text-sm text-red-400">{errors.email}</p>}
          </div>
          <div className="mb-4">
            <label className="mb-1 block text-sm text-gray-300">Display name</label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className="w-full rounded border border-gray-600 bg-[#0a0e17] px-3 py-2 text-white placeholder-gray-500 focus:border-[#60a5fa] focus:outline-none"
              placeholder="Your name"
              autoComplete="name"
            />
            {errors.displayName && (
              <p className="mt-1 text-sm text-red-400">{errors.displayName}</p>
            )}
          </div>
          <div className="mb-6">
            <label className="mb-1 block text-sm text-gray-300">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded border border-gray-600 bg-[#0a0e17] px-3 py-2 text-white placeholder-gray-500 focus:border-[#60a5fa] focus:outline-none"
              placeholder="••••••••"
              autoComplete="new-password"
            />
            <p className="mt-1 text-xs text-gray-500">
              Min 8 chars, 1 uppercase, 1 digit
            </p>
            {errors.password && <p className="mt-1 text-sm text-red-400">{errors.password}</p>}
          </div>
          <button
            type="submit"
            disabled={loading}
            className="w-full rounded bg-[#60a5fa] py-2 font-medium text-white hover:bg-[#3b82f6] disabled:opacity-50"
          >
            {loading ? (
              <span className="inline-flex items-center gap-2">
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                Creating account...
              </span>
            ) : (
              'Sign up'
            )}
          </button>
          <p className="mt-4 text-center text-sm text-gray-400">
            Already have an account?{' '}
            <Link to="/login" className="text-[#60a5fa] hover:underline">
              Sign in
            </Link>
          </p>
        </form>
      </div>
    </div>
  )
}
