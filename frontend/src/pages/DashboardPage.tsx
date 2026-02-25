import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useDropzone } from 'react-dropzone'
import toast from 'react-hot-toast'
import {
  FileText,
  Upload,
  Eye,
  Pencil,
  Trash2,
  Edit2,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { pdfs, type PDFItem, type UploadFileItem } from '../api/client'

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  if (diff < 60000) return 'just now'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`
  return `${Math.floor(diff / 86400000)}d ago`
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    pending: 'bg-yellow-500/20 text-yellow-400',
    processing: 'bg-blue-500/20 text-blue-400',
    ready: 'bg-green-500/20 text-green-400',
    error: 'bg-red-500/20 text-red-400',
  }
  const c = colors[status] ?? 'bg-gray-500/20 text-gray-400'
  return (
    <span className={`rounded px-2 py-0.5 text-xs font-medium ${c}`}>
      {status === 'ready' ? '✓ Ready' : status === 'error' ? '✗ Error' : status}
    </span>
  )
}

export default function DashboardPage() {
  const { user, logout } = useAuth()
  const [items, setItems] = useState<PDFItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [size] = useState(12)
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState<Record<string, string>>({})
  const [deleteModal, setDeleteModal] = useState<PDFItem | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editingName, setEditingName] = useState('')

  const fetchPdfs = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await pdfs.listPdfs(page, size)
      setItems(data.items)
      setTotal(data.total)
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to load PDFs'
      toast.error(msg)
    } finally {
      setLoading(false)
    }
  }, [page, size])

  useEffect(() => {
    fetchPdfs()
  }, [fetchPdfs])

  const pollTask = useCallback(
    async (taskId: string, filename: string) => {
      const poll = async () => {
        try {
          const { data } = await pdfs.getTaskStatus(taskId)
          setUploadProgress((p) => ({ ...p, [taskId]: data.state }))
          if (data.state === 'SUCCESS') {
            setUploadProgress((p) => {
              const next = { ...p }
              delete next[taskId]
              return next
            })
            fetchPdfs()
            toast.success(`${filename} is ready`)
            return
          }
          if (data.state === 'FAILURE') {
            setUploadProgress((p) => {
              const next = { ...p }
              next[taskId] = 'error'
              return next
            })
            toast.error(`${filename} failed to process`)
            return
          }
          setTimeout(poll, 2000)
        } catch {
          setTimeout(poll, 2000)
        }
      }
      poll()
    },
    [fetchPdfs]
  )

  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      const pdfsOnly = acceptedFiles.filter(
        (f) => f.name.toLowerCase().endsWith('.pdf') || f.type === 'application/pdf'
      )
      if (pdfsOnly.length === 0) {
        toast.error('Only PDF files are accepted')
        return
      }
      setUploading(true)
      try {
        const { data } = await pdfs.uploadPdfs(pdfsOnly)
        data.files.forEach((f: UploadFileItem) => {
          setUploadProgress((p) => ({ ...p, [f.task_id]: f.status }))
          pollTask(f.task_id, f.filename)
        })
        toast.success(`Uploading ${data.files.length} file(s)`)
      } catch (err: unknown) {
        const msg =
          (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
          'Upload failed'
        toast.error(msg)
      } finally {
        setUploading(false)
      }
    },
    [pollTask]
  )

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'] },
    disabled: uploading,
    multiple: true,
  })

  const handleRename = async (id: string) => {
    if (!editingName.trim() || editingName === items.find((i) => i.id === id)?.name) {
      setEditingId(null)
      return
    }
    if (!editingName.toLowerCase().endsWith('.pdf')) {
      toast.error('Filename must end with .pdf')
      return
    }
    try {
      await pdfs.rename(id, editingName.trim())
      toast.success('Renamed')
      setEditingId(null)
      fetchPdfs()
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Rename failed'
      toast.error(msg)
    }
  }

  const handleDelete = async () => {
    if (!deleteModal) return
    try {
      await pdfs.deletePdf(deleteModal.id)
      toast.success('Deleted')
      setDeleteModal(null)
      fetchPdfs()
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Delete failed'
      toast.error(msg)
    }
  }

  const totalPages = Math.ceil(total / size) || 1

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
            <Link to="/profile" className="text-gray-300 hover:text-white">
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

      <main className="mx-auto max-w-6xl px-6 py-8">
        <div
          {...getRootProps()}
          className={`mb-8 rounded-lg border-2 border-dashed p-8 text-center transition-colors ${
            isDragActive ? 'border-[#60a5fa] bg-[#60a5fa]/10' : 'border-gray-600 bg-[#0f172a]/50'
          } ${uploading ? 'pointer-events-none opacity-60' : ''}`}
        >
          <input {...getInputProps()} />
          <Upload className="mx-auto mb-2 h-12 w-12 text-gray-400" />
          <p className="text-gray-300">
            {isDragActive ? 'Drop PDFs here' : 'Drag & drop PDFs or click to browse'}
          </p>
          <p className="mt-1 text-sm text-gray-500">Only .pdf files</p>
        </div>

        {Object.keys(uploadProgress).length > 0 && (
          <div className="mb-6 space-y-2">
            {Object.entries(uploadProgress).map(([taskId, status]) => (
              <div
                key={taskId}
                className="flex items-center justify-between rounded bg-[#0f172a] px-4 py-2"
              >
                <span className="text-gray-300">Task {taskId.slice(0, 8)}...</span>
                <StatusBadge status={status} />
              </div>
            ))}
          </div>
        )}

        {loading ? (
          <div className="flex justify-center py-12">
            <div className="h-10 w-10 animate-spin rounded-full border-2 border-[#60a5fa] border-t-transparent" />
          </div>
        ) : items.length === 0 ? (
          <div className="rounded-lg border border-gray-700 bg-[#0f172a] py-16 text-center">
            <FileText className="mx-auto mb-4 h-16 w-16 text-gray-500" />
            <p className="text-gray-400">No PDFs yet. Upload your first file above.</p>
          </div>
        ) : (
          <>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {items.map((item) => (
                <div
                  key={item.id}
                  className="rounded-lg border border-gray-700 bg-[#0f172a] p-4 transition hover:border-gray-600"
                >
                  <div className="mb-3 flex items-start justify-between">
                    <FileText className="h-10 w-10 flex-shrink-0 text-red-400" />
                    <StatusBadge status={item.status} />
                  </div>
                  {editingId === item.id ? (
                    <input
                      type="text"
                      value={editingName}
                      onChange={(e) => setEditingName(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleRename(item.id)
                        if (e.key === 'Escape') setEditingId(null)
                      }}
                      onBlur={() => handleRename(item.id)}
                      className="mb-2 w-full rounded border border-gray-600 bg-[#0a0e17] px-2 py-1 text-white focus:border-[#60a5fa] focus:outline-none"
                      autoFocus
                    />
                  ) : (
                    <p
                      className="mb-2 truncate font-medium text-white"
                      title={item.name}
                    >
                      {item.name}
                    </p>
                  )}
                  <p className="mb-2 text-sm text-gray-400">
                    {formatSize(item.size_bytes)}
                    {item.page_count != null && ` • ${item.page_count} pages`}
                  </p>
                  <p className="mb-4 text-xs text-gray-500">
                    {formatDate(item.created_at)}
                  </p>
                  <div className="flex flex-wrap gap-2">
                    <Link
                      to={`/pdf/${item.id}/view`}
                      className="inline-flex items-center gap-1 rounded bg-gray-600 px-2 py-1 text-sm text-white hover:bg-gray-500"
                    >
                      <Eye className="h-3.5 w-3.5" /> View
                    </Link>
                    <Link
                      to={`/pdf/${item.id}/edit`}
                      className="inline-flex items-center gap-1 rounded bg-gray-600 px-2 py-1 text-sm text-white hover:bg-gray-500"
                    >
                      <Pencil className="h-3.5 w-3.5" /> Edit
                    </Link>
                    <button
                      onClick={() => {
                        setEditingId(item.id)
                        setEditingName(item.name)
                      }}
                      className="inline-flex items-center gap-1 rounded bg-gray-600 px-2 py-1 text-sm text-white hover:bg-gray-500"
                    >
                      <Edit2 className="h-3.5 w-3.5" />
                    </button>
                    <button
                      onClick={() => setDeleteModal(item)}
                      className="inline-flex items-center gap-1 rounded bg-red-600/20 px-2 py-1 text-sm text-red-400 hover:bg-red-600/30"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>

            {totalPages > 1 && (
              <div className="mt-8 flex items-center justify-center gap-4">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  className="flex items-center gap-1 rounded bg-gray-600 px-3 py-2 text-white disabled:opacity-40"
                >
                  <ChevronLeft className="h-4 w-4" /> Previous
                </button>
                <span className="text-gray-400">
                  Page {page} of {totalPages}
                </span>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages}
                  className="flex items-center gap-1 rounded bg-gray-600 px-3 py-2 text-white disabled:opacity-40"
                >
                  Next <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            )}
          </>
        )}
      </main>

      {deleteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="w-full max-w-md rounded-lg bg-[#0f172a] p-6 shadow-xl">
            <h3 className="text-lg font-semibold text-white">Delete PDF</h3>
            <p className="mt-2 text-gray-400">
              Are you sure you want to delete <strong className="text-white">{deleteModal.name}</strong>?
            </p>
            <div className="mt-6 flex justify-end gap-3">
              <button
                onClick={() => setDeleteModal(null)}
                className="rounded bg-gray-600 px-4 py-2 text-white hover:bg-gray-500"
              >
                Cancel
              </button>
              <button
                onClick={handleDelete}
                className="rounded bg-red-600 px-4 py-2 text-white hover:bg-red-500"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
