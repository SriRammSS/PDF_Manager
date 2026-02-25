import { useState, useEffect } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { Worker, Viewer } from '@react-pdf-viewer/core'
import { defaultLayoutPlugin } from '@react-pdf-viewer/default-layout'
import '@react-pdf-viewer/core/lib/styles/index.css'
import '@react-pdf-viewer/default-layout/lib/styles/index.css'
import { ArrowLeft, Pencil } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { pdfs } from '../api/client'

const WORKER_URL = 'https://unpkg.com/pdfjs-dist@3.11.174/build/pdf.worker.min.js'

export default function ViewerPage() {
  const { id } = useParams<{ id: string }>()
  const { accessToken } = useAuth()
  const navigate = useNavigate()
  const [pdfName, setPdfName] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    pdfs
      .getPdf(id)
      .then(({ data }) => setPdfName(data.name))
      .catch(() => setError('Failed to load PDF info'))
  }, [id])

  if (!id || !accessToken) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#0a0e17]">
        <div className="h-10 w-10 animate-spin rounded-full border-2 border-[#60a5fa] border-t-transparent" />
      </div>
    )
  }

  const defaultLayoutPluginInstance = defaultLayoutPlugin()

  const fileUrl = pdfs.streamUrl(id)
  const httpHeaders = { Authorization: `Bearer ${accessToken}` }

  return (
    <div className="flex h-screen flex-col bg-[#0a0e17]">
      <header className="flex items-center justify-between border-b border-gray-700 bg-[#0f172a] px-4 py-3">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate('/dashboard')}
            className="flex items-center gap-2 rounded bg-gray-600 px-3 py-2 text-white hover:bg-gray-500"
          >
            <ArrowLeft className="h-4 w-4" /> Back
          </button>
          <span className="text-gray-300">{pdfName || 'Loading...'}</span>
        </div>
        <Link
          to={`/pdf/${id}/edit`}
          className="flex items-center gap-2 rounded bg-[#60a5fa] px-3 py-2 text-white hover:bg-[#3b82f6]"
        >
          <Pencil className="h-4 w-4" /> Edit PDF
        </Link>
      </header>

      <main className="flex-1 overflow-hidden">
        {error ? (
          <div className="flex h-full items-center justify-center text-red-400">{error}</div>
        ) : (
          <Worker workerUrl={WORKER_URL}>
            <div className="h-full overflow-auto">
              <Viewer
                fileUrl={fileUrl}
                httpHeaders={httpHeaders}
                withCredentials={true}
                plugins={[defaultLayoutPluginInstance]}
                theme="dark"
              />
            </div>
          </Worker>
        )}
      </main>
    </div>
  )
}
