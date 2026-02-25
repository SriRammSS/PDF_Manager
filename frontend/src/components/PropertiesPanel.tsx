/**
 * PropertiesPanel — Right sidebar showing properties of the selected Fabric object.
 */

import { useState, useEffect } from 'react'
import { Copy, ArrowUp, ArrowDown, Trash2, Bold, Italic, ChevronDown, ChevronRight, ExternalLink } from 'lucide-react'
import type { FabricObject } from 'fabric'
import type { IText } from 'fabric'
import { pdfs, type VersionItem } from '../api/client'

const FONT_FAMILIES = ['Helvetica', 'Times New Roman', 'Courier New']
const BASE = 'http://localhost:8000/api'

export interface TextEditDisplay {
  originalBlock: { text: string; page: number }
  newText: string
  page: number
}

interface PropertiesPanelProps {
  fabricCanvas: import('fabric').Canvas | null
  onObjectModified?: () => void
  pdfId?: string
  currentVersion?: number
  pendingTextEdits?: TextEditDisplay[]
  onRemovePendingEdit?: (index: number) => void
}

export default function PropertiesPanel({
  fabricCanvas,
  onObjectModified,
  pdfId,
  currentVersion,
  pendingTextEdits = [],
  onRemovePendingEdit,
}: PropertiesPanelProps) {
  const [activeObject, setActiveObject] = useState<FabricObject | null>(null)
  const [versionsExpanded, setVersionsExpanded] = useState(false)
  const [versions, setVersions] = useState<VersionItem[]>([])

  useEffect(() => {
    const fc = fabricCanvas
    if (!fc) return

    const updateSelection = () => {
      const obj = fc.getActiveObject()
      setActiveObject(obj ?? null)
    }

    fc.on('selection:created', updateSelection)
    fc.on('selection:updated', updateSelection)
    fc.on('selection:cleared', updateSelection)
    updateSelection()

    return () => {
      fc.off('selection:created', updateSelection)
      fc.off('selection:updated', updateSelection)
      fc.off('selection:cleared', updateSelection)
    }
  }, [fabricCanvas])

  useEffect(() => {
    if (versionsExpanded && pdfId) {
      pdfs.getVersions(pdfId).then((r) => setVersions(r.data)).catch(() => setVersions([]))
    }
  }, [versionsExpanded, pdfId])

  const viewVersion = async (versionId: string) => {
    if (!pdfId) return
    const token = localStorage.getItem('access_token')
    if (!token) return
    const res = await fetch(`${BASE}/pdfs/${pdfId}/versions/${versionId}/stream`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok) return
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    window.open(url, '_blank')
    setTimeout(() => URL.revokeObjectURL(url), 10000)
  }

  if (!fabricCanvas) return null

  if (!activeObject) {
    return (
      <aside className="flex w-[240px] shrink-0 flex-col border-l border-gray-700 bg-[#111827] overflow-y-auto">
        <div className="p-4">
          <h3 className="mb-2 text-sm font-semibold text-gray-400">Properties</h3>
          <p className="text-sm text-gray-500">Select an object to edit its properties.</p>
        </div>
        {pdfId && (
          <VersionHistorySection
            currentVersion={currentVersion}
            versionsExpanded={versionsExpanded}
            setVersionsExpanded={setVersionsExpanded}
            versions={versions}
            viewVersion={viewVersion}
          />
        )}
        {pendingTextEdits.length > 0 && (
          <div className="mt-4 border-t border-[#1f2d45] pt-4">
            <div className="mb-2 text-[11px] font-medium uppercase tracking-wider text-gray-400">
              Pending Text Edits ({pendingTextEdits.length})
            </div>
            {pendingTextEdits.map((edit, i) => (
              <div
                key={i}
                className="mb-2 rounded border border-[#1f2d45] bg-[#0f172a] p-2"
              >
                <div className="mb-1 text-[11px] text-gray-500">
                  Page {edit.page + 1} — original:
                </div>
                <div className="mb-1 text-xs text-red-400 line-through break-words">
                  {edit.originalBlock.text}
                </div>
                <div className="text-xs text-green-400 break-words">→ {edit.newText}</div>
                <button
                  onClick={() => onRemovePendingEdit?.(i)}
                  className="mt-1 cursor-pointer border-none bg-transparent text-[11px] text-red-500 hover:text-red-400"
                >
                  ✕ Remove
                </button>
              </div>
            ))}
          </div>
        )}
      </aside>
    )
  }

  const obj = activeObject as FabricObject & { type?: string; text?: string; fontSize?: number; fontFamily?: string; fill?: string; fontWeight?: string; fontStyle?: string }
  const data = (obj as { data?: Record<string, unknown> }).data

  const handleDuplicate = async () => {
    const clone = await obj.clone()
    if (clone) {
      const left = (obj.left ?? 0) + 10
      const top = (obj.top ?? 0) + 10
      clone.set({ left, top })
      fabricCanvas.add(clone)
      fabricCanvas.setActiveObject(clone)
      fabricCanvas.renderAll()
      onObjectModified?.()
    }
  }

  const handleBringForward = () => {
    fabricCanvas.bringObjectForward(obj)
    fabricCanvas.renderAll()
    onObjectModified?.()
  }

  const handleSendBackward = () => {
    fabricCanvas.sendObjectBackwards(obj)
    fabricCanvas.renderAll()
    onObjectModified?.()
  }

  const handleDelete = () => {
    fabricCanvas.remove(obj)
    fabricCanvas.discardActiveObject()
    fabricCanvas.renderAll()
    onObjectModified?.()
  }

  const type = obj.type ?? ''

  return (
    <aside className="flex w-[240px] shrink-0 flex-col border-l border-gray-700 bg-[#111827] overflow-y-auto">
      <div className="p-4">
        <h3 className="mb-3 text-sm font-semibold text-gray-400">Properties</h3>

        {/* IText / text */}
        {(type === 'i-text' || type === 'text' || type === 'textbox') && (
          <ITextProperties obj={obj as IText} canvas={fabricCanvas} onModified={onObjectModified} />
        )}

        {/* Rect (highlight, erase, shape) */}
        {type === 'rect' && (
          <RectProperties obj={obj} canvas={fabricCanvas} data={data} onModified={onObjectModified} />
        )}

        {/* Path (draw) */}
        {type === 'path' && (
          <PathProperties obj={obj} canvas={fabricCanvas} onModified={onObjectModified} />
        )}

        {/* Line */}
        {type === 'line' && (
          <LineProperties obj={obj} canvas={fabricCanvas} onModified={onObjectModified} />
        )}

        {/* Common actions */}
        <div className="mt-4 flex flex-wrap gap-2 border-t border-gray-700 pt-4">
          <button
            onClick={handleDuplicate}
            className="flex items-center gap-1.5 rounded bg-gray-700 px-2 py-1.5 text-xs text-white hover:bg-gray-600"
          >
            <Copy className="h-3.5 w-3.5" /> Duplicate
          </button>
          <button
            onClick={handleBringForward}
            className="flex items-center gap-1.5 rounded bg-gray-700 px-2 py-1.5 text-xs text-white hover:bg-gray-600"
          >
            <ArrowUp className="h-3.5 w-3.5" /> Bring Forward
          </button>
          <button
            onClick={handleSendBackward}
            className="flex items-center gap-1.5 rounded bg-gray-700 px-2 py-1.5 text-xs text-white hover:bg-gray-600"
          >
            <ArrowDown className="h-3.5 w-3.5" /> Send Backward
          </button>
          <button
            onClick={handleDelete}
            className="flex items-center gap-1.5 rounded bg-red-600/80 px-2 py-1.5 text-xs text-white hover:bg-red-600"
          >
            <Trash2 className="h-3.5 w-3.5" /> Delete
          </button>
        </div>

        {pdfId && (
          <VersionHistorySection
            currentVersion={currentVersion}
            versionsExpanded={versionsExpanded}
            setVersionsExpanded={setVersionsExpanded}
            versions={versions}
            viewVersion={viewVersion}
          />
        )}
        {pendingTextEdits.length > 0 && (
          <div className="mt-4 border-t border-[#1f2d45] pt-4">
            <div className="mb-2 text-[11px] font-medium uppercase tracking-wider text-gray-400">
              Pending Text Edits ({pendingTextEdits.length})
            </div>
            {pendingTextEdits.map((edit, i) => (
              <div
                key={i}
                className="mb-2 rounded border border-[#1f2d45] bg-[#0f172a] p-2"
              >
                <div className="mb-1 text-[11px] text-gray-500">
                  Page {edit.page + 1} — original:
                </div>
                <div className="mb-1 text-xs text-red-400 line-through break-words">
                  {edit.originalBlock.text}
                </div>
                <div className="text-xs text-green-400 break-words">→ {edit.newText}</div>
                <button
                  onClick={() => onRemovePendingEdit?.(i)}
                  className="mt-1 cursor-pointer border-none bg-transparent text-[11px] text-red-500 hover:text-red-400"
                >
                  ✕ Remove
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </aside>
  )
}

function VersionHistorySection({
  currentVersion,
  versionsExpanded,
  setVersionsExpanded,
  versions,
  viewVersion,
}: {
  currentVersion?: number
  versionsExpanded: boolean
  setVersionsExpanded: (v: boolean) => void
  versions: VersionItem[]
  viewVersion: (id: string) => void
}) {
  return (
    <div className="mt-4 border-t border-gray-700 pt-4">
      <button
        onClick={() => setVersionsExpanded(!versionsExpanded)}
        className="flex w-full items-center gap-2 text-left text-sm font-semibold text-gray-400 hover:text-white"
      >
        {versionsExpanded ? (
          <ChevronDown className="h-4 w-4" />
        ) : (
          <ChevronRight className="h-4 w-4" />
        )}
        Version History
      </button>
      {versionsExpanded && (
        <ul className="mt-2 space-y-2">
          {versions.map((v) => (
            <li
              key={v.id}
              className="flex flex-col gap-0.5 rounded border border-gray-600 bg-gray-800/50 p-2 text-xs"
            >
              <div className="flex items-center justify-between">
                <span className="font-medium text-white">v{v.version}</span>
                {v.version === currentVersion && (
                  <span className="rounded bg-green-600/80 px-1.5 py-0.5 text-[10px] text-white">
                    Current
                  </span>
                )}
              </div>
              <div className="text-gray-500">{new Date(v.saved_at).toLocaleString()}</div>
              {v.version !== currentVersion && (
                <button
                  onClick={() => viewVersion(v.id)}
                  className="mt-1 flex items-center gap-1 text-[#06b6d4] hover:underline"
                  style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 12 }}
                >
                  <ExternalLink className="h-3 w-3" /> View
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function ITextProperties({
  obj,
  canvas,
  onModified,
}: {
  obj: IText
  canvas: import('fabric').Canvas
  onModified?: () => void
}) {
  const apply = (updates: Record<string, unknown>) => {
    obj.set(updates)
    canvas.requestRenderAll()
    onModified?.()
  }

  return (
    <div className="space-y-3">
      <div>
        <label className="mb-1 block text-xs text-gray-500">Font</label>
        <select
          value={obj.fontFamily ?? 'Helvetica'}
          onChange={(e) => apply({ fontFamily: e.target.value })}
          className="w-full rounded border border-gray-600 bg-gray-800 px-2 py-1.5 text-sm text-white"
        >
          {FONT_FAMILIES.map((f) => (
            <option key={f} value={f}>
              {f}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label className="mb-1 block text-xs text-gray-500">Size</label>
        <input
          type="number"
          min={8}
          max={200}
          value={obj.fontSize ?? 14}
          onChange={(e) => apply({ fontSize: Math.max(8, Math.min(200, Number(e.target.value) || 14)) })}
          className="w-full rounded border border-gray-600 bg-gray-800 px-2 py-1.5 text-sm text-white"
        />
      </div>
      <div className="flex gap-1">
        <button
          onClick={() => apply({ fontWeight: obj.fontWeight === 'bold' ? 'normal' : 'bold' })}
          className={`rounded px-2 py-1.5 ${obj.fontWeight === 'bold' ? 'bg-[#3b82f6] text-white' : 'bg-gray-700 text-gray-400 hover:bg-gray-600'}`}
        >
          <Bold className="h-4 w-4" />
        </button>
        <button
          onClick={() => apply({ fontStyle: obj.fontStyle === 'italic' ? 'normal' : 'italic' })}
          className={`rounded px-2 py-1.5 ${obj.fontStyle === 'italic' ? 'bg-[#3b82f6] text-white' : 'bg-gray-700 text-gray-400 hover:bg-gray-600'}`}
        >
          <Italic className="h-4 w-4" />
        </button>
      </div>
      <div>
        <label className="mb-1 block text-xs text-gray-500">Color</label>
        <input
          type="color"
          value={typeof obj.fill === 'string' ? obj.fill : '#000000'}
          onChange={(e) => apply({ fill: e.target.value })}
          className="h-8 w-full cursor-pointer rounded border border-gray-600 bg-transparent"
        />
      </div>
    </div>
  )
}

function RectProperties({
  obj,
  canvas,
  data,
  onModified,
}: {
  obj: FabricObject
  canvas: import('fabric').Canvas
  data?: Record<string, unknown>
  onModified?: () => void
}) {
  const apply = (updates: Record<string, unknown>) => {
    obj.set(updates)
    canvas.requestRenderAll()
    onModified?.()
  }

  const isHighlight = data?.type === 'highlight'
  const isErase = data?.type === 'erase'
  const isShape = data?.type === 'shape'

  return (
    <div className="space-y-3">
      {(isHighlight || isShape) && (
        <div>
          <label className="mb-1 block text-xs text-gray-500">Fill color</label>
          <input
            type="color"
            value={typeof obj.fill === 'string' && obj.fill !== 'transparent' ? obj.fill : '#ffffff'}
            onChange={(e) => apply({ fill: e.target.value })}
            className="h-8 w-full cursor-pointer rounded border border-gray-600 bg-transparent"
          />
        </div>
      )}
      {(isHighlight || isShape) && (
        <div>
          <label className="mb-1 block text-xs text-gray-500">Opacity</label>
          <input
            type="range"
            min={0.1}
            max={1}
            step={0.1}
            value={obj.opacity ?? 1}
            onChange={(e) => apply({ opacity: Number(e.target.value) })}
            className="w-full"
          />
          <span className="text-xs text-gray-400">{Math.round((obj.opacity ?? 1) * 100)}%</span>
        </div>
      )}
      {isErase && (
        <div>
          <label className="mb-1 block text-xs text-gray-500">Fill (whiteout/redact)</label>
          <input
            type="color"
            value={typeof obj.fill === 'string' ? obj.fill : '#ffffff'}
            onChange={(e) => apply({ fill: e.target.value })}
            className="h-8 w-full cursor-pointer rounded border border-gray-600 bg-transparent"
          />
        </div>
      )}
      {isShape && (
        <>
          <div>
            <label className="mb-1 block text-xs text-gray-500">Stroke color</label>
            <input
              type="color"
              value={typeof obj.stroke === 'string' ? obj.stroke : '#000000'}
              onChange={(e) => apply({ stroke: e.target.value })}
              className="h-8 w-full cursor-pointer rounded border border-gray-600 bg-transparent"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-gray-500">Stroke width</label>
            <input
              type="number"
              min={1}
              max={20}
              value={obj.strokeWidth ?? 2}
              onChange={(e) => apply({ strokeWidth: Math.max(1, Number(e.target.value) || 2) })}
              className="w-full rounded border border-gray-600 bg-gray-800 px-2 py-1.5 text-sm text-white"
            />
          </div>
        </>
      )}
    </div>
  )
}

function PathProperties({
  obj,
  canvas,
  onModified,
}: {
  obj: FabricObject
  canvas: import('fabric').Canvas
  onModified?: () => void
}) {
  const apply = (updates: Record<string, unknown>) => {
    obj.set(updates)
    canvas.requestRenderAll()
    onModified?.()
  }

  return (
    <div className="space-y-3">
      <div>
        <label className="mb-1 block text-xs text-gray-500">Stroke color</label>
        <input
          type="color"
          value={typeof obj.stroke === 'string' ? obj.stroke : '#000000'}
          onChange={(e) => apply({ stroke: e.target.value })}
          className="h-8 w-full cursor-pointer rounded border border-gray-600 bg-transparent"
        />
      </div>
      <div>
        <label className="mb-1 block text-xs text-gray-500">Stroke width</label>
        <input
          type="number"
          min={1}
          max={20}
          value={obj.strokeWidth ?? 2}
          onChange={(e) => apply({ strokeWidth: Math.max(1, Number(e.target.value) || 2) })}
          className="w-full rounded border border-gray-600 bg-gray-800 px-2 py-1.5 text-sm text-white"
        />
      </div>
    </div>
  )
}

function LineProperties({
  obj,
  canvas,
  onModified,
}: {
  obj: FabricObject
  canvas: import('fabric').Canvas
  onModified?: () => void
}) {
  const apply = (updates: Record<string, unknown>) => {
    obj.set(updates)
    canvas.requestRenderAll()
    onModified?.()
  }

  return (
    <div className="space-y-3">
      <div>
        <label className="mb-1 block text-xs text-gray-500">Stroke color</label>
        <input
          type="color"
          value={typeof obj.stroke === 'string' ? obj.stroke : '#000000'}
          onChange={(e) => apply({ stroke: e.target.value })}
          className="h-8 w-full cursor-pointer rounded border border-gray-600 bg-transparent"
        />
      </div>
      <div>
        <label className="mb-1 block text-xs text-gray-500">Stroke width</label>
        <input
          type="number"
          min={1}
          max={20}
          value={obj.strokeWidth ?? 2}
          onChange={(e) => apply({ strokeWidth: Math.max(1, Number(e.target.value) || 2) })}
          className="w-full rounded border border-gray-600 bg-gray-800 px-2 py-1.5 text-sm text-white"
        />
      </div>
    </div>
  )
}
