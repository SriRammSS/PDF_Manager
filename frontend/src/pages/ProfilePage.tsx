import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import { useAuth } from '../context/AuthContext'
import { users } from '../api/client'

export default function ProfilePage() {
  const { user, logout } = useAuth()
  const [displayName, setDisplayName] = useState('')
  useEffect(() => {
    if (user?.display_name) setDisplayName(user.display_name)
  }, [user?.display_name])
  const [saveNameLoading, setSaveNameLoading] = useState(false)
  const [saveNameSuccess, setSaveNameSuccess] = useState(false)

  const [newEmail, setNewEmail] = useState('')
  const [emailPassword, setEmailPassword] = useState('')
  const [saveEmailLoading, setSaveEmailLoading] = useState(false)
  const [emailError, setEmailError] = useState('')

  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [savePasswordLoading, setSavePasswordLoading] = useState(false)
  const [passwordError, setPasswordError] = useState('')

  const handleSaveName = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaveNameLoading(true)
    setSaveNameSuccess(false)
    try {
      await users.updateProfile({ display_name: displayName.trim() })
      toast.success('Display name updated')
      setSaveNameSuccess(true)
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to update'
      toast.error(msg)
    } finally {
      setSaveNameLoading(false)
    }
  }

  const handleSaveEmail = async (e: React.FormEvent) => {
    e.preventDefault()
    setEmailError('')
    setSaveEmailLoading(true)
    try {
      await users.updateProfile({
        email: newEmail.trim(),
        current_password: emailPassword,
      })
      toast.success('Email updated')
      setNewEmail('')
      setEmailPassword('')
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to update'
      setEmailError(msg)
      toast.error(msg)
    } finally {
      setSaveEmailLoading(false)
    }
  }

  const handleSavePassword = async (e: React.FormEvent) => {
    e.preventDefault()
    setPasswordError('')
    if (newPassword !== confirmPassword) {
      setPasswordError('Passwords do not match')
      toast.error('Passwords do not match')
      return
    }
    if (newPassword.length < 8) {
      setPasswordError('Password must be at least 8 characters')
      return
    }
    if (!/[A-Z]/.test(newPassword)) {
      setPasswordError('Password must contain an uppercase letter')
      return
    }
    if (!/\d/.test(newPassword)) {
      setPasswordError('Password must contain a digit')
      return
    }
    setSavePasswordLoading(true)
    try {
      await users.updateProfile({
        current_password: currentPassword,
        new_password: newPassword,
      })
      toast.success('Password changed')
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to update'
      setPasswordError(msg)
      toast.error(msg)
    } finally {
      setSavePasswordLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#0a0e17]">
      <header className="flex items-center justify-between border-b border-gray-700 bg-[#0f172a] px-6 py-4">
        <div className="flex items-center gap-6">
          <Link to="/dashboard" className="text-xl font-bold text-white">
            PDF Manager
          </Link>
          <nav className="flex gap-4">
            <Link to="/dashboard" className="text-gray-300 hover:text-white">
              Dashboard
            </Link>
            <Link to="/logs" className="text-gray-300 hover:text-white">
              Logs
            </Link>
            <Link to="/profile" className="text-white">
              Profile
            </Link>
          </nav>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-sm text-gray-400">{user?.display_name}</span>
          <button
            onClick={() => logout()}
            className="rounded bg-gray-600 px-3 py-1.5 text-sm text-white hover:bg-gray-500"
          >
            Logout
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-2xl px-6 py-8">
        <h1 className="mb-8 text-2xl font-bold text-white">Profile</h1>

        <section className="mb-8 rounded-lg border border-gray-700 bg-[#0f172a] p-6">
          <h2 className="mb-4 text-lg font-semibold text-white">Display Info</h2>
          <p className="text-gray-400">Name: {user?.display_name}</p>
          <p className="mt-1 text-gray-400">Email: {user?.email}</p>
        </section>

        <section className="mb-8 rounded-lg border border-gray-700 bg-[#0f172a] p-6">
          <h2 className="mb-4 text-lg font-semibold text-white">Change Display Name</h2>
          <form onSubmit={handleSaveName} className="space-y-4">
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="Display name"
              className="w-full rounded border border-gray-600 bg-[#0a0e17] px-3 py-2 text-white"
            />
            <button
              type="submit"
              disabled={saveNameLoading}
              className="rounded bg-[#60a5fa] px-4 py-2 text-white hover:bg-[#3b82f6] disabled:opacity-50"
            >
              {saveNameLoading ? 'Saving...' : 'Save Name'}
            </button>
            {saveNameSuccess && (
              <p className="text-sm text-green-400">Name updated successfully</p>
            )}
          </form>
        </section>

        <section className="mb-8 rounded-lg border border-gray-700 bg-[#0f172a] p-6">
          <h2 className="mb-4 text-lg font-semibold text-white">Change Email</h2>
          <form onSubmit={handleSaveEmail} className="space-y-4">
            <input
              type="email"
              value={newEmail}
              onChange={(e) => setNewEmail(e.target.value)}
              placeholder="New email"
              className="w-full rounded border border-gray-600 bg-[#0a0e17] px-3 py-2 text-white"
            />
            <input
              type="password"
              value={emailPassword}
              onChange={(e) => setEmailPassword(e.target.value)}
              placeholder="Current password"
              className="w-full rounded border border-gray-600 bg-[#0a0e17] px-3 py-2 text-white"
            />
            {emailError && <p className="text-sm text-red-400">{emailError}</p>}
            <button
              type="submit"
              disabled={saveEmailLoading}
              className="rounded bg-[#60a5fa] px-4 py-2 text-white hover:bg-[#3b82f6] disabled:opacity-50"
            >
              {saveEmailLoading ? 'Updating...' : 'Update Email'}
            </button>
          </form>
        </section>

        <section className="rounded-lg border border-gray-700 bg-[#0f172a] p-6">
          <h2 className="mb-4 text-lg font-semibold text-white">Change Password</h2>
          <form onSubmit={handleSavePassword} className="space-y-4">
            <input
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              placeholder="Current password"
              className="w-full rounded border border-gray-600 bg-[#0a0e17] px-3 py-2 text-white"
            />
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="New password"
              className="w-full rounded border border-gray-600 bg-[#0a0e17] px-3 py-2 text-white"
            />
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="Confirm new password"
              className="w-full rounded border border-gray-600 bg-[#0a0e17] px-3 py-2 text-white"
            />
            {passwordError && <p className="text-sm text-red-400">{passwordError}</p>}
            <p className="text-xs text-gray-500">Min 8 chars, 1 uppercase, 1 digit</p>
            <button
              type="submit"
              disabled={savePasswordLoading}
              className="rounded bg-[#60a5fa] px-4 py-2 text-white hover:bg-[#3b82f6] disabled:opacity-50"
            >
              {savePasswordLoading ? 'Changing...' : 'Change Password'}
            </button>
          </form>
        </section>
      </main>
    </div>
  )
}
