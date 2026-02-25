import { useState } from 'react'
import { Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import { useAuth } from '../context/AuthContext'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(false)
  const { login } = useAuth()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setErrors({})
    if (!email.trim()) setErrors((p) => ({ ...p, email: 'Email is required' }))
    if (!password) setErrors((p) => ({ ...p, password: 'Password is required' }))
    if (Object.keys(errors).length) return

    setLoading(true)
    try {
      await login(email.trim(), password)
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Invalid credentials'
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
          <p className="mt-1 text-sm text-gray-400">Sign in to your account</p>
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
          <div className="mb-6">
            <label className="mb-1 block text-sm text-gray-300">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded border border-gray-600 bg-[#0a0e17] px-3 py-2 text-white placeholder-gray-500 focus:border-[#60a5fa] focus:outline-none"
              placeholder="••••••••"
              autoComplete="current-password"
            />
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
                Signing in...
              </span>
            ) : (
              'Sign in'
            )}
          </button>
          <p className="mt-4 text-center text-sm text-gray-400">
            Don't have an account?{' '}
            <Link to="/signup" className="text-[#60a5fa] hover:underline">
              Sign up
            </Link>
          </p>
        </form>
      </div>
    </div>
  )
}
