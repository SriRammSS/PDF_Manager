import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

const API_BASE = 'http://localhost:8000'
const MAX_LOGS = 500

type LogEntry = {
  id?: string
  timestamp?: string
  level?: string
  module?: string
  event?: string
  [key: string]: unknown
}

const LEVEL_COLORS: Record<string, string> = {
  DEBUG: '#475569',
  INFO: '#60a5fa',
  WARNING: '#fbbf24',
  ERROR: '#ef4444',
  CRITICAL: '#ef4444',
}

const MODULES = ['auth', 'upload', 'pdf', 'task', 'user'] as const
const LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'] as const

function formatTime(ts: string | undefined): string {
  if (!ts) return '--:--:--.---'
  try {
    const d = new Date(ts)
    const h = d.getHours().toString().padStart(2, '0')
    const m = d.getMinutes().toString().padStart(2, '0')
    const s = d.getSeconds().toString().padStart(2, '0')
    const ms = d.getMilliseconds().toString().padStart(3, '0')
    return `${h}:${m}:${s}.${ms}`
  } catch {
    return '--:--:--.---'
  }
}

function formatLogLine(entry: LogEntry): string {
  const ts = formatTime(entry.timestamp)
  const level = entry.level || 'INFO'
  const mod = entry.module || ''
  const evt = entry.event || ''
  const meta = entry.metadata as Record<string, unknown> | undefined
  const parts: string[] = []
  if (meta && typeof meta === 'object') {
    for (const [k, v] of Object.entries(meta)) {
      if (v !== undefined && v !== null) {
        parts.push(`${k}=${String(v)}`)
      }
    }
  }
  return `[${ts}] [${level}] [${mod}] ${evt} ${parts.join(' ')}`.trim()
}

export default function LogsPage() {
  const { user, logout } = useAuth()
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [filterLevel, setFilterLevel] = useState<Set<string>>(new Set())
  const [filterModule, setFilterModule] = useState<Set<string>>(new Set())
  const [autoScroll, setAutoScroll] = useState(true)
  const [paused, setPaused] = useState(false)
  const [connected, setConnected] = useState(false)
  const [reconnecting, setReconnecting] = useState(false)
  const logEndRef = useRef<HTMLDivElement>(null)
  const eventSourceRef = useRef<EventSource | null>(null)
  const reconnectTimeoutRef = useRef<number | null>(null)
  const backoffRef = useRef(1)
  const filterLevelRef = useRef(filterLevel)
  const filterModuleRef = useRef(filterModule)
  const pausedRef = useRef(paused)
  filterLevelRef.current = filterLevel
  filterModuleRef.current = filterModule
  pausedRef.current = paused

  const scrollToBottom = useCallback(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(() => {
    if (autoScroll) scrollToBottom()
  }, [autoScroll, logs, scrollToBottom])

  const connect = useCallback(() => {
    const token = localStorage.getItem('access_token')
    if (!token) {
      setConnected(false)
      return
    }
    const url = `${API_BASE}/api/logs/stream?token=${encodeURIComponent(token)}`
    const es = new EventSource(url)
    eventSourceRef.current = es

    es.onopen = () => {
      setConnected(true)
      setReconnecting(false)
      backoffRef.current = 1
    }

    es.onmessage = (e) => {
      if (pausedRef.current) return
      try {
        const entry = JSON.parse(e.data) as LogEntry
        const fl = filterLevelRef.current
        const fm = filterModuleRef.current
        const levelOk = fl.size === 0 || (entry.level && fl.has(entry.level))
        const moduleOk = fm.size === 0 || (entry.module && fm.has(entry.module))
        if (levelOk && moduleOk) {
          setLogs((prev) => {
            const next = [entry, ...prev]
            if (next.length > MAX_LOGS) next.splice(MAX_LOGS)
            return next
          })
        }
      } catch {
        // ignore parse errors
      }
    }

    es.onerror = () => {
      es.close()
      eventSourceRef.current = null
      setConnected(false)
      setReconnecting(true)
      const delays = [1000, 2000, 4000, 8000, 16000, 30000]
      const delay = delays[Math.min(backoffRef.current - 1, delays.length - 1)]
      backoffRef.current = Math.min(backoffRef.current + 1, delays.length)
      reconnectTimeoutRef.current = window.setTimeout(() => {
        connect()
      }, delay)
    }
  }, [])

  useEffect(() => {
    connect()
    return () => {
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current)
      eventSourceRef.current?.close()
      eventSourceRef.current = null
    }
  }, [connect])

  const toggleLevel = (level: string) => {
    setFilterLevel((prev) => {
      const next = new Set(prev)
      if (next.has(level)) next.delete(level)
      else next.add(level)
      return next
    })
  }

  const toggleModule = (mod: string) => {
    setFilterModule((prev) => {
      const next = new Set(prev)
      if (next.has(mod)) next.delete(mod)
      else next.add(mod)
      return next
    })
  }

  const clearLogs = () => setLogs([])

  const token = localStorage.getItem('access_token')
  if (!token) {
    return (
      <div className="p-8">
        <h1 className="text-2xl font-bold">Live Logs</h1>
        <p className="mt-4 text-gray-500">Please log in to view logs.</p>
      </div>
    )
  }

  return (
    <div className="flex h-screen flex-col bg-[#0a0e17] text-sm" style={{ fontFamily: "'JetBrains Mono', 'Fira Code', monospace" }}>
      <div className="flex flex-wrap items-center gap-4 border-b border-gray-700 bg-[#0f172a] px-4 py-3">
        <Link to="/dashboard" className="text-xl font-bold text-white hover:text-gray-200">
          PDF Manager
        </Link>
        <nav className="flex gap-4">
          <Link to="/dashboard" className="text-gray-400 hover:text-white">Dashboard</Link>
          <Link to="/logs" className="text-white">Logs</Link>
          <Link to="/profile" className="text-gray-400 hover:text-white">Profile</Link>
        </nav>
        <h1 className="text-lg font-bold text-white">Live Logs</h1>
        <div className="flex items-center gap-2">
          <span
            className={`h-2 w-2 rounded-full ${
              connected ? 'bg-green-500' : reconnecting ? 'bg-yellow-500' : 'bg-red-500'
            }`}
          />
          <span className="text-gray-300">
            {connected ? 'Connected' : reconnecting ? 'Reconnecting' : 'Disconnected'}
          </span>
        </div>
        <div className="flex gap-2">
          <span className="text-gray-400">Level:</span>
          {LEVELS.map((l) => (
            <label key={l} className="flex cursor-pointer items-center gap-1 text-gray-300">
              <input
                type="checkbox"
                checked={filterLevel.has(l)}
                onChange={() => toggleLevel(l)}
              />
              {l}
            </label>
          ))}
        </div>
        <div className="flex gap-2">
          <span className="text-gray-400">Module:</span>
          {MODULES.map((m) => (
            <label key={m} className="flex cursor-pointer items-center gap-1 text-gray-300">
              <input
                type="checkbox"
                checked={filterModule.has(m)}
                onChange={() => toggleModule(m)}
              />
              {m}
            </label>
          ))}
        </div>
        <label className="flex cursor-pointer items-center gap-2 text-gray-300">
          <input type="checkbox" checked={autoScroll} onChange={(e) => setAutoScroll(e.target.checked)} />
          Auto-scroll
        </label>
        <button
          onClick={() => setPaused((p) => !p)}
          className="rounded bg-gray-600 px-3 py-1 text-white hover:bg-gray-500"
        >
          {paused ? 'Resume' : 'Pause'}
        </button>
        <button
          onClick={clearLogs}
          className="rounded bg-gray-600 px-3 py-1 text-white hover:bg-gray-500"
        >
          Clear
        </button>
        <div className="ml-auto flex items-center gap-4">
          <span className="text-sm text-gray-400">{user?.display_name}</span>
          <button
            onClick={() => logout()}
            className="rounded bg-gray-600 px-3 py-1 text-white hover:bg-gray-500"
          >
            Logout
          </button>
        </div>
      </div>
      <LogTerminal logs={logs} />
      <div ref={logEndRef} />
    </div>
  )
}

function LogTerminal({ logs }: { logs: LogEntry[] }) {
  const [expandedId, setExpandedId] = useState<string | null>(null)

  return (
    <div className="flex-1 overflow-auto p-2">
      {logs.map((entry) => {
        const id = entry.id ?? String(Math.random())
        const level = entry.level || 'INFO'
        const color = LEVEL_COLORS[level] ?? '#94a3b8'
        const isCritical = level === 'CRITICAL'
        const isExpanded = expandedId === id

        return (
          <div key={id} className="mb-1">
            <div
              onClick={() => setExpandedId(isExpanded ? null : id)}
              className="cursor-pointer rounded px-2 py-1 hover:bg-white/5"
              style={{
                color,
                fontWeight: isCritical ? 'bold' : 'normal',
              }}
            >
              {formatLogLine(entry)}
            </div>
            {isExpanded && (
              <pre className="ml-4 mt-1 overflow-auto rounded bg-black/30 p-2 text-xs text-gray-300">
                {JSON.stringify(entry, null, 2)}
              </pre>
            )}
          </div>
        )
      })}
    </div>
  )
}
