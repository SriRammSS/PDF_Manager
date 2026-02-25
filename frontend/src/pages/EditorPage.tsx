/**
 * Visual Canvas PDF Editor
 * Architecture: 3 stacked layers
 *   Layer 1: PDF background (rendered pages via pdf.js)
 *   Layer 2: Fabric.js canvas (annotations: text, highlight, erase, shapes, draw)
 *   Layer 3: UI overlay (toolbar, zoom, page nav)
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { getDocument, GlobalWorkerOptions } from 'pdfjs-dist'
import {
  Canvas,
  Rect,
  Line,
  IText,
  PencilBrush,
} from 'fabric'
import {
  ArrowLeft,
  Save,
  Undo2,
  Redo2,
  ZoomIn,
  ZoomOut,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { pdfs } from '../api/client'
import ToolbarSidebar, {
  type ToolId,
  type ToolSettings,
  DEFAULT_TOOL_SETTINGS,
} from '../components/ToolbarSidebar'
import PropertiesPanel from '../components/PropertiesPanel'
import PageManagerPanel from '../components/PageManagerPanel'

const WORKER_URL = '/pdf.worker.min.js'
const BASE = 'http://localhost:8000/api'

type PageDim = { page: number; width_pts: number; height_pts: number }

interface TextBlock {
  text: string
  x: number
  y: number
  width: number
  height: number
  font_family: string
  font_size: number
  bold: boolean
  italic: boolean
  raw_font: string
  canvasX?: number
  canvasY?: number
  canvasW?: number
  canvasH?: number
}

interface TextEdit {
  originalBlock: TextBlock
  newText: string
  page: number
}

function rgbStringToHex(rgb: string): string {
  if (!rgb || rgb.startsWith('#')) return rgb
  const m = rgb.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/)
  if (!m) return '#000000'
  return (
    '#' +
    [m[1], m[2], m[3]]
      .map((n) => parseInt(n, 10).toString(16).padStart(2, '0'))
      .join('')
      .toUpperCase()
  )
}

export default function EditorPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { accessToken } = useAuth()
  const [pdfName, setPdfName] = useState('')
  const [version, setVersion] = useState(1)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [activeTool, setActiveTool] = useState<ToolId>('select')
  const [toolSettings, setToolSettings] = useState<ToolSettings>(DEFAULT_TOOL_SETTINGS)
  const [currentPage, setCurrentPage] = useState(0)
  const [zoom, setZoom] = useState(1)
  const [pageDims, setPageDims] = useState<PageDim[]>([])
  const [pageImages, setPageImages] = useState<Map<number, string>>(new Map())
  const [pageOrder, setPageOrder] = useState<number[]>([])
  const [pendingPageOps, setPendingPageOps] = useState<Array<Record<string, unknown>>>([])
  const [thumbnails, setThumbnails] = useState<string[]>([])
  const [totalPages, setTotalPages] = useState(0)
  const [dirty, setDirty] = useState(false)
  const [canUndo, setCanUndo] = useState(false)
  const [canRedo, setCanRedo] = useState(false)
  const [unsavedCount, setUnsavedCount] = useState(0)
  const [textBlocks, setTextBlocks] = useState<TextBlock[]>([])
  const [hoveredBlock, setHoveredBlock] = useState<TextBlock | null>(null)
  const [activeEditBlock, setActiveEditBlock] = useState<TextBlock | null>(null)
  const [editValue, setEditValue] = useState('')
  const [pendingTextEdits, setPendingTextEdits] = useState<TextEdit[]>([])
  const [noTextBanner, setNoTextBanner] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const overlayRef = useRef<HTMLDivElement>(null)
  const pageStatesRef = useRef<Map<number, string>>(new Map())
  const historyRef = useRef<string[]>([])
  const redoRef = useRef<string[]>([])
  const pdfDocRef = useRef<Awaited<ReturnType<typeof getDocument>['promise']> | null>(null)
  const skipSnapshotRef = useRef(false)

  const containerRef = useRef<HTMLDivElement>(null)
  const pdfLayerRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const fabricRef = useRef<Canvas | null>(null)

  // Fetch PDF metadata and dimensions
  const fetchPdf = useCallback(async () => {
    if (!id) return
    try {
      const { data } = await pdfs.getPdf(id)
      setPdfName(data.name)
      setVersion(data.version)
      const dims = await pdfs.getDimensions(id)
      setPageDims(dims.data.pages)
    } catch {
      toast.error('Failed to load PDF')
    }
  }, [id])

  const fetchVersions = useCallback(async () => {
    if (!id) return
    try {
      await pdfs.getVersions(id)
    } catch {
      // ignore
    }
  }, [id])

  useEffect(() => {
    if (!id) return
    setLoading(true)
    Promise.all([fetchPdf(), fetchVersions()]).finally(() => setLoading(false))
  }, [id, fetchPdf, fetchVersions])

  // Initialize pageOrder and totalPages when page count is known
  useEffect(() => {
    if (pageDims.length > 0) {
      setPageOrder(Array.from({ length: pageDims.length }, (_, i) => i))
      setTotalPages(pageDims.length)
    }
  }, [pageDims.length])

  // Sync thumbnails from pageImages and pageOrder
  useEffect(() => {
    if (pageImages.size > 0 && pageOrder.length > 0) {
      setThumbnails(
        pageOrder
          .map((i) => pageImages.get(i))
          .filter((t): t is string => !!t)
      )
    }
  }, [pageImages, pageOrder])

  // Load PDF document and render pages
  useEffect(() => {
    if (!id || !accessToken || pageDims.length === 0) return
    let cancelled = false
    const token = localStorage.getItem('access_token')
    if (!token) return

    GlobalWorkerOptions.workerSrc = WORKER_URL

    const run = async () => {
      try {
        const res = await fetch(`${BASE.replace('/api', '')}/api/pdfs/${id}/stream`, {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (!res.ok || cancelled) return
        const blob = await res.blob()
        if (cancelled) return
        const arrayBuffer = await blob.arrayBuffer()
        if (cancelled) return
        const doc = await getDocument({ data: arrayBuffer }).promise
        if (cancelled) return
        pdfDocRef.current = doc
        const images = new Map<number, string>()
        for (let i = 0; i < doc.numPages; i++) {
          if (cancelled) return
          const page = await doc.getPage(i + 1)
          const viewport = page.getViewport({ scale: 2 })
          const canvas = document.createElement('canvas')
          canvas.width = viewport.width
          canvas.height = viewport.height
          const ctx = canvas.getContext('2d')
          if (!ctx) continue
          await page.render({ canvasContext: ctx, viewport }).promise
          images.set(i, canvas.toDataURL('image/png'))
        }
        if (!cancelled) setPageImages(images)
      } catch {
        if (!cancelled) toast.error('Failed to load PDF')
      }
    }
    run()
    return () => {
      cancelled = true
    }
  }, [id, accessToken, pageDims.length])

  const originalPageIdx = pageOrder[currentPage] ?? currentPage
  const dim = pageDims[originalPageIdx] ?? pageDims[currentPage]
  const widthPx = dim ? dim.width_pts * zoom : 612 * zoom
  const heightPx = dim ? dim.height_pts * zoom : 792 * zoom

  const prevPageRef = useRef(currentPage)

  const loadTextBlocks = useCallback(
    async (pageIndex: number) => {
      if (!id) return
      try {
        const { data } = await pdfs.getTextContent(id, pageIndex)
        const blocks: TextBlock[] = data.blocks
        const pageDim = pageDims[pageIndex]
        if (!pageDim) {
          setTextBlocks([])
          return
        }
        const scaleX = widthPx / pageDim.width_pts
        const scaleY = heightPx / pageDim.height_pts
        const converted = blocks.map((b) => ({
          ...b,
          canvasX: b.x * scaleX,
          canvasY: (pageDim.height_pts - b.y - b.height) * scaleY,
          canvasW: b.width * scaleX,
          canvasH: b.height * scaleY,
        }))
        setTextBlocks(converted)
        setNoTextBanner(converted.length === 0)
      } catch {
        console.warn('Could not extract text blocks')
        setTextBlocks([])
        setNoTextBanner(false)
      }
    },
    [id, pageDims, widthPx, heightPx]
  )

  useEffect(() => {
    if (activeTool === 'edit-text') {
      loadTextBlocks(originalPageIdx)
    } else {
      setTextBlocks([])
      setHoveredBlock(null)
      setActiveEditBlock(null)
      setNoTextBanner(false)
    }
  }, [activeTool, originalPageIdx, loadTextBlocks])

  const updateUnsavedCount = useCallback(() => {
    const c = fabricRef.current
    if (c) pageStatesRef.current.set(currentPage, JSON.stringify(c.toObject(['data'])))
    let count = 0
    pageStatesRef.current.forEach((json) => {
      try {
        const data = JSON.parse(json)
        count += (data.objects?.length ?? 0)
      } catch {
        // ignore
      }
    })
    setUnsavedCount(count)
  }, [currentPage])

  const snapshot = useCallback(() => {
    if (skipSnapshotRef.current) return
    const c = fabricRef.current
    if (!c) return
    const json = JSON.stringify(c.toObject(['data']))
    historyRef.current.push(json)
    if (historyRef.current.length > 50) historyRef.current.shift()
    redoRef.current = []
    setCanUndo(historyRef.current.length > 1)
    setCanRedo(false)
    setDirty(true)
    updateUnsavedCount()
  }, [updateUnsavedCount])

  // Init Fabric canvas when page changes or dimensions available
  useEffect(() => {
    if (!canvasRef.current || !dim) return
    const el = canvasRef.current
    const prevPage = prevPageRef.current
    prevPageRef.current = currentPage
    const prevCanvas = fabricRef.current
    if (prevCanvas && prevPage >= 0) {
      const json = JSON.stringify(prevCanvas.toObject(['data']))
      pageStatesRef.current.set(prevPage, json)
      prevCanvas.dispose()
    }
    const canvas = new Canvas(el, {
      width: widthPx,
      height: heightPx,
      selection: true,
      preserveObjectStacking: true,
    })
    fabricRef.current = canvas
    const saved = pageStatesRef.current.get(currentPage)
    const initHistory = () => {
      const initialJson = JSON.stringify(canvas.toObject(['data']))
      historyRef.current = [initialJson]
      redoRef.current = []
      setCanUndo(false)
      setCanRedo(false)
    }
    if (saved) {
      skipSnapshotRef.current = true
      void canvas.loadFromJSON(saved).then(() => {
        canvas.renderAll()
        skipSnapshotRef.current = false
        initHistory()
      })
    } else {
      initHistory()
    }

    const snapshotHandler = () => snapshot()
    canvas.on('object:added', snapshotHandler)
    canvas.on('object:modified', snapshotHandler)
    canvas.on('object:removed', snapshotHandler)

    return () => {
      canvas.off('object:added', snapshotHandler)
      canvas.off('object:modified', snapshotHandler)
      canvas.off('object:removed', snapshotHandler)
      const json = JSON.stringify(canvas.toObject(['data']))
      pageStatesRef.current.set(currentPage, json)
      canvas.dispose()
      fabricRef.current = null
    }
  }, [currentPage, dim?.page])

  // Resize canvas when zoom/dim changes
  useEffect(() => {
    const c = fabricRef.current
    if (!c || !dim) return
    c.setDimensions({ width: widthPx, height: heightPx })
    c.renderAll()
  }, [widthPx, heightPx, dim])

  // Tool activation — setup handlers per active tool
  useEffect(() => {
    const fc = fabricRef.current
    if (!fc || !dim) return

    // Remove all tool-specific handlers
    fc.off('mouse:down')
    fc.off('mouse:move')
    fc.off('mouse:up')
    fc.off('path:created')
    fc.isDrawingMode = false
    fc.selection = activeTool === 'select'

    if (activeTool === 'edit-text') {
      fc.selection = false
      fc.isDrawingMode = false
      fc.defaultCursor = 'text'
      fc.forEachObject((obj) => {
        obj.selectable = false
        obj.evented = false
      })
    } else {
      fc.forEachObject((obj) => {
        obj.selectable = true
        obj.evented = true
      })
    }

    const cursors: Record<ToolId, string> = {
      select: 'default',
      text: 'text',
      'edit-text': 'text',
      highlight: 'crosshair',
      erase: 'crosshair',
      draw: 'crosshair',
      'shape-rect': 'crosshair',
      'shape-line': 'crosshair',
    }
    fc.defaultCursor = cursors[activeTool] ?? 'default'
    fc.hoverCursor = activeTool === 'select' ? 'move' : 'crosshair'

    switch (activeTool) {
      case 'text':
        setupTextTool(fc, toolSettings, currentPage, snapshot)
        break
      case 'highlight':
        setupDragRectTool(fc, 'highlight', toolSettings, currentPage, snapshot)
        break
      case 'erase':
        setupDragRectTool(fc, 'erase', toolSettings, currentPage, snapshot)
        break
      case 'draw':
        setupDrawTool(fc, toolSettings, currentPage, snapshot)
        break
      case 'shape-rect':
        setupDragRectTool(fc, 'shape-rect', toolSettings, currentPage, snapshot)
        break
      case 'shape-line':
        setupLineTool(fc, toolSettings, currentPage, snapshot)
        break
      case 'edit-text':
        break
    }
  }, [activeTool, toolSettings, currentPage, dim, snapshot])

  const undo = useCallback(() => {
    if (historyRef.current.length < 2) return
    const c = fabricRef.current
    if (!c) return
    skipSnapshotRef.current = true
    redoRef.current.push(historyRef.current.pop()!)
    const prev = historyRef.current[historyRef.current.length - 1]
    if (prev) {
      void c.loadFromJSON(prev).then(() => {
        c.renderAll()
        skipSnapshotRef.current = false
        setCanUndo(historyRef.current.length > 1)
        setCanRedo(true)
      })
    } else {
      skipSnapshotRef.current = false
    }
  }, [])

  const redo = useCallback(() => {
    if (!redoRef.current.length) return
    const c = fabricRef.current
    if (!c) return
    skipSnapshotRef.current = true
    const next = redoRef.current.pop()!
    historyRef.current.push(next)
    void c.loadFromJSON(next).then(() => {
      c.renderAll()
      skipSnapshotRef.current = false
      setCanUndo(true)
      setCanRedo(redoRef.current.length > 0)
    })
  }, [])

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      const map: Record<string, ToolId> = {
        s: 'select',
        t: 'text',
        x: 'edit-text',
        h: 'highlight',
        e: 'erase',
        d: 'draw',
        r: 'shape-rect',
        l: 'shape-line',
      }
      if (map[e.key.toLowerCase()]) {
        setActiveTool(map[e.key.toLowerCase()])
        e.preventDefault()
      }
      if ((e.key === 'Delete' || e.key === 'Backspace') && fabricRef.current) {
        const obj = fabricRef.current.getActiveObject()
        if (obj) {
          fabricRef.current.remove(obj)
          fabricRef.current.renderAll()
          e.preventDefault()
        }
      }
      if (e.ctrlKey && e.key === 'z') {
        undo()
        e.preventDefault()
      }
      if (e.ctrlKey && e.key === 'y') {
        redo()
        e.preventDefault()
      }
      if (e.key === 'Escape') {
        setActiveTool('select')
        fabricRef.current?.discardActiveObject()
        fabricRef.current?.renderAll()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [undo, redo])

  const commitEdit = useCallback(() => {
    if (!activeEditBlock || !editValue.trim()) {
      setActiveEditBlock(null)
      return
    }
    if (editValue.trim() === activeEditBlock.text) {
      setActiveEditBlock(null)
      return
    }
    setPendingTextEdits((prev) => {
      const filtered = prev.filter((ed) => ed.originalBlock !== activeEditBlock)
      return [
        ...filtered,
        {
          originalBlock: activeEditBlock,
          newText: editValue.trim(),
          page: originalPageIdx,
        },
      ]
    })
    setDirty(true)
    setActiveEditBlock(null)
  }, [activeEditBlock, editValue, originalPageIdx])

  const handleEditTextMouseMove = useCallback(
    (e: React.MouseEvent) => {
      const rect = overlayRef.current?.getBoundingClientRect()
      if (!rect) return
      const mx = e.clientX - rect.left
      const my = e.clientY - rect.top
      const hit = textBlocks.find(
        (b) =>
          mx >= (b.canvasX ?? 0) &&
          mx <= (b.canvasX ?? 0) + (b.canvasW ?? 0) &&
          my >= (b.canvasY ?? 0) &&
          my <= (b.canvasY ?? 0) + (b.canvasH ?? 0)
      )
      setHoveredBlock(hit ?? null)
    },
    [textBlocks]
  )

  const handleEditTextClick = useCallback(
    (e: React.MouseEvent) => {
      const rect = overlayRef.current?.getBoundingClientRect()
      if (!rect) return
      const mx = e.clientX - rect.left
      const my = e.clientY - rect.top
      const hit = textBlocks.find(
        (b) =>
          mx >= (b.canvasX ?? 0) &&
          mx <= (b.canvasX ?? 0) + (b.canvasW ?? 0) &&
          my >= (b.canvasY ?? 0) &&
          my <= (b.canvasY ?? 0) + (b.canvasH ?? 0)
      )
      if (!hit) {
        commitEdit()
        return
      }
      const existingEdit = pendingTextEdits.find((ed) => ed.originalBlock === hit)
      setEditValue(existingEdit ? existingEdit.newText : hit.text)
      setActiveEditBlock(hit)
      setTimeout(() => textareaRef.current?.focus(), 50)
    },
    [textBlocks, pendingTextEdits, commitEdit]
  )

  const canvasToPdf = useCallback(
    (canvasX: number, canvasY: number, pageIdx: number) => {
      const pageDim = pageDims[pageIdx]
      if (!pageDim) return { x: canvasX, y: canvasY }
      const wPx = pageDim.width_pts * zoom
      const hPx = pageDim.height_pts * zoom
      const scaleX = pageDim.width_pts / wPx
      const scaleY = pageDim.height_pts / hPx
      return {
        x: canvasX * scaleX,
        y: pageDim.height_pts - canvasY * scaleY,
      }
    },
    [pageDims, zoom]
  )

  const serializeAllOps = useCallback(() => {
    const c = fabricRef.current
    if (c) {
      pageStatesRef.current.set(currentPage, JSON.stringify(c.toObject(['data'])))
    }
    const ops: Array<Record<string, unknown>> = []

    for (let pageIdx = 0; pageIdx < pageOrder.length; pageIdx++) {
      const originalPageIdx = pageOrder[pageIdx] ?? pageIdx
      const saved = pageStatesRef.current.get(pageIdx)
      const canvasJson = saved ? JSON.parse(saved) : null
      if (!canvasJson?.objects) continue

      const objects = canvasJson.objects as Array<Record<string, unknown>>
      for (const obj of objects) {
        const d = (obj.data as Record<string, unknown>) || {}
        const typ = obj.type as string

        if (typ === 'i-text' || typ === 'text' || typ === 'textbox') {
          const left = (obj.left as number) ?? 0
          const top = (obj.top as number) ?? 0
          const fontSize = (obj.fontSize as number) ?? 12
          const { x, y } = canvasToPdf(left, top + fontSize, originalPageIdx)
          const fontFamily = (obj.fontFamily as string) || 'Helvetica'
          ops.push({
            type: 'text',
            page: originalPageIdx,
            x,
            y,
            text: (obj.text as string) || '',
            font_family: fontFamily === 'Times New Roman' ? 'Times-Roman' : fontFamily,
            font_size: fontSize,
            bold: obj.fontWeight === 'bold',
            italic: obj.fontStyle === 'italic',
            color_hex: rgbStringToHex((obj.fill as string) || '#000000') || '#000000',
            rotation: -((obj.angle as number) || 0),
          })
        } else if (typ === 'rect' && d.type === 'highlight') {
          const left = (obj.left as number) ?? 0
          const top = (obj.top as number) ?? 0
          const width = (obj.width as number) ?? 0
          const height = (obj.height as number) ?? 0
          const tl = canvasToPdf(left, top + height, originalPageIdx)
          const br = canvasToPdf(left + width, top, originalPageIdx)
          ops.push({
            type: 'highlight',
            page: originalPageIdx,
            x: tl.x,
            y: tl.y,
            width: br.x - tl.x,
            height: tl.y - br.y,
            color_hex: rgbStringToHex(obj.fill as string) || '#FFFF00',
            opacity: (obj.opacity as number) ?? 0.4,
          })
        } else if (typ === 'rect' && d.type === 'erase') {
          const left = (obj.left as number) ?? 0
          const top = (obj.top as number) ?? 0
          const width = (obj.width as number) ?? 0
          const height = (obj.height as number) ?? 0
          const tl = canvasToPdf(left, top + height, originalPageIdx)
          const br = canvasToPdf(left + width, top, originalPageIdx)
          ops.push({
            type: 'erase',
            page: originalPageIdx,
            x: tl.x,
            y: tl.y,
            width: br.x - tl.x,
            height: tl.y - br.y,
            fill_color: rgbStringToHex(obj.fill as string) || '#FFFFFF',
          })
        } else if (typ === 'rect' && d.type === 'shape') {
          const left = (obj.left as number) ?? 0
          const top = (obj.top as number) ?? 0
          const width = (obj.width as number) ?? 0
          const height = (obj.height as number) ?? 0
          const tl = canvasToPdf(left, top + height, originalPageIdx)
          const br = canvasToPdf(left + width, top, originalPageIdx)
          const fill = obj.fill as string
          const fc =
            fill && fill !== 'transparent' ? rgbStringToHex(fill) : null
          ops.push({
            type: 'shape',
            shape_type: 'rectangle',
            page: originalPageIdx,
            x: tl.x,
            y: tl.y,
            width: br.x - tl.x,
            height: tl.y - br.y,
            stroke_color: rgbStringToHex(obj.stroke as string) || '#000000',
            fill_color: fc,
            stroke_width: (obj.strokeWidth as number) || 1.5,
          })
        } else if (typ === 'line' && d.type === 'shape') {
          const x1 = (obj.x1 as number) ?? 0
          const y1 = (obj.y1 as number) ?? 0
          const x2 = (obj.x2 as number) ?? 0
          const y2 = (obj.y2 as number) ?? 0
          const p1 = canvasToPdf(x1, y1, originalPageIdx)
          const p2 = canvasToPdf(x2, y2, originalPageIdx)
          ops.push({
            type: 'shape',
            shape_type: 'line',
            page: originalPageIdx,
            x: p1.x,
            y: p1.y,
            width: p2.x - p1.x,
            height: p2.y - p1.y,
            stroke_color: rgbStringToHex(obj.stroke as string) || '#000000',
            stroke_width: (obj.strokeWidth as number) || 1.5,
          })
        } else if (typ === 'path' && d.type === 'draw') {
          const pathData = obj.path as unknown[]
          const rawPath = Array.isArray(pathData)
            ? pathData
                .map((cmd: unknown) =>
                  Array.isArray(cmd)
                    ? (cmd as [string, ...number[]])
                        .map((x, i) => (i === 0 ? x : Number(x).toFixed(2)))
                        .join(' ')
                    : ''
                )
                .filter(Boolean)
                .join(' ')
            : ''
          ops.push({
            type: 'draw',
            page: originalPageIdx,
            path: rawPath,
            color_hex: rgbStringToHex(obj.stroke as string) || '#000000',
            stroke_width: (obj.strokeWidth as number) ?? 2,
          })
        }
      }
    }

    for (const edit of pendingTextEdits) {
      const b = edit.originalBlock
      const pageIdx = edit.page
      const dims = pageDims[pageIdx]
      if (!dims) continue
      ops.push({
        type: 'erase',
        page: pageIdx,
        x: b.x - 1,
        y: b.y - 1,
        width: b.width + 2,
        height: b.height + 2,
        fill_color: '#FFFFFF',
      })
      ops.push({
        type: 'text',
        page: pageIdx,
        x: b.x,
        y: b.y,
        text: edit.newText,
        font_family: b.font_family,
        font_size: b.font_size,
        bold: b.bold,
        italic: b.italic,
        color_hex: '#000000',
        rotation: 0,
      })
    }

    return [...ops, ...pendingPageOps]
  }, [currentPage, pageDims, pageOrder, pendingPageOps, pendingTextEdits, zoom, canvasToPdf])

  const handleReorder = useCallback((newOrder: number[]) => {
    setPageOrder(newOrder)
    setPendingPageOps((prev) => [
      ...prev,
      { type: 'page', action: 'reorder', page: 0, new_order: newOrder },
    ])
    setDirty(true)
  }, [])

  const handleRotatePage = useCallback(
    (displayIdx: number) => {
      const origIdx = pageOrder[displayIdx] ?? displayIdx
      setPendingPageOps((prev) => [
        ...prev,
        { type: 'page', action: 'rotate', page: origIdx, rotate_degrees: 90 },
      ])
      setDirty(true)
      toast(`Page ${displayIdx + 1} will be rotated 90° on Save`)
    },
    [pageOrder]
  )

  const handleDeletePage = useCallback(
    (displayIdx: number) => {
      if (totalPages <= 1) return
      const confirmed = window.confirm(
        `Delete page ${displayIdx + 1}? This applies on Save.`
      )
      if (!confirmed) return
      setThumbnails((prev) => prev.filter((_, i) => i !== displayIdx))
      setPageOrder((prev) => prev.filter((_, i) => i !== displayIdx))
      setTotalPages((t) => t - 1)
      const origIdx = pageOrder[displayIdx] ?? displayIdx
      setPendingPageOps((prev) => [
        ...prev,
        { type: 'page', action: 'delete', page: origIdx },
      ])
      setDirty(true)
      if (currentPage === displayIdx) {
        setCurrentPage(Math.max(0, displayIdx - 1))
      } else if (currentPage > displayIdx) {
        setCurrentPage((p) => p - 1)
      }
      toast.success(`Page ${displayIdx + 1} marked for deletion — will apply on Save`)
    },
    [totalPages, currentPage, pageOrder]
  )

  const reloadPdf = useCallback(
    async (pageToReloadBlocks?: number) => {
      if (!id || !accessToken) return
      const token = localStorage.getItem('access_token')
      if (!token) return
      try {
        const res = await fetch(`${BASE.replace('/api', '')}/api/pdfs/${id}/stream`, {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (!res.ok) return
        const arrayBuffer = await res.arrayBuffer()
        const doc = await getDocument({ data: arrayBuffer }).promise
        pdfDocRef.current = doc
        const images = new Map<number, string>()
        for (let i = 0; i < doc.numPages; i++) {
          const page = await doc.getPage(i + 1)
          const viewport = page.getViewport({ scale: 2 })
          const canvas = document.createElement('canvas')
          canvas.width = viewport.width
          canvas.height = viewport.height
          const ctx = canvas.getContext('2d')
          if (!ctx) continue
          await page.render({ canvasContext: ctx, viewport }).promise
          images.set(i, canvas.toDataURL('image/png'))
        }
        setPageImages(images)
        if (activeTool === 'edit-text' && pageToReloadBlocks !== undefined) {
          loadTextBlocks(pageToReloadBlocks)
        }
      } catch {
        toast.error('Failed to reload PDF')
      }
    },
    [id, accessToken, activeTool, loadTextBlocks]
  )

  const handleSave = useCallback(async () => {
    if (!id) return
    const ops = serializeAllOps()

    if (ops.length === 0 && pendingTextEdits.length === 0) {
      toast('No changes to save', { icon: 'ℹ️' })
      return
    }

    setSaving(true)
    const savingToast = toast.loading(`Saving ${ops.length} change(s)…`)

    try {
      const { data } = await pdfs.editPdf(id, ops as never[], `${ops.length} edit(s) via visual editor`)
      const taskId = (data as { task_id?: string }).task_id
      if (!taskId) {
        toast.success(`Saved! Version ${(data as { version?: number }).version ?? version + 1}`, {
          id: savingToast,
        })
        setDirty(false)
        setVersion((data as { version?: number }).version ?? version + 1)
        setUnsavedCount(0)
        setPendingPageOps([])
        setPendingTextEdits([])
        await fetchPdf()
        await fetchVersions()
        await reloadPdf(originalPageIdx)
        setSaving(false)
        return
      }

      for (let i = 0; i < 60; i++) {
        await new Promise((r) => setTimeout(r, 1000))
        const { data: taskData } = await pdfs.getTaskStatus(taskId)
        const state = (taskData as { state?: string }).state

        if (state === 'SUCCESS') {
          toast.success(`Saved! Version ${(data as { version?: number }).version ?? version + 1}`, {
            id: savingToast,
          })
          setDirty(false)
          setVersion((data as { version?: number }).version ?? version + 1)
          setUnsavedCount(0)
          setPendingPageOps([])
        await fetchPdf()
        await fetchVersions()
        await reloadPdf(originalPageIdx)
        break
        } else if (state === 'FAILURE') {
          toast.error('Save failed. Your original file is safe.', { id: savingToast })
          break
        }
      }
    } catch (err: unknown) {
      const msg =
        (err as { message?: string; response?: { data?: { detail?: string } } })?.message ||
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Save error'
      toast.error('Save error: ' + msg, { id: savingToast })
    } finally {
      setSaving(false)
    }
  }, [id, serializeAllOps, version, fetchPdf, fetchVersions, reloadPdf])

  if (!id || loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#0f172a]">
        <div className="h-10 w-10 animate-spin rounded-full border-2 border-[#60a5fa] border-t-transparent" />
      </div>
    )
  }

  const pageImg = pageImages.get(originalPageIdx)
  const numPages = pageOrder.length || pageDims.length

  return (
    <div className="flex h-screen flex-col bg-[#0f172a]">
      {/* Top header */}
      <header className="flex shrink-0 items-center justify-between border-b border-gray-700 bg-[#0f172a] px-4 py-2">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/dashboard')}
            className="flex items-center gap-2 rounded px-3 py-1.5 text-white hover:bg-gray-600"
          >
            <ArrowLeft className="h-4 w-4" /> Back
          </button>
          <span className="text-gray-300">{pdfName}</span>
          <span className="rounded bg-gray-600 px-2 py-0.5 text-xs text-gray-300">v{version}</span>
        </div>

        <div className="flex items-center gap-1">
          <button
            onClick={undo}
            disabled={!canUndo}
            className="rounded p-1.5 text-gray-400 hover:bg-gray-600 hover:text-white disabled:opacity-40"
            title="Undo"
          >
            <Undo2 className="h-4 w-4" />
          </button>
          <button
            onClick={redo}
            disabled={!canRedo}
            className="rounded p-1.5 text-gray-400 hover:bg-gray-600 hover:text-white disabled:opacity-40"
            title="Redo"
          >
            <Redo2 className="h-4 w-4" />
          </button>
          <div className="mx-2 h-6 w-px bg-gray-600" />
          <button
            onClick={() => setZoom((z) => Math.min(2, z + 0.25))}
            className="rounded p-1.5 text-gray-400 hover:bg-gray-600 hover:text-white"
          >
            <ZoomIn className="h-4 w-4" />
          </button>
          <button
            onClick={() => setZoom((z) => Math.max(0.5, z - 0.25))}
            className="rounded p-1.5 text-gray-400 hover:bg-gray-600 hover:text-white"
          >
            <ZoomOut className="h-4 w-4" />
          </button>
          <span className="text-sm text-gray-500">{Math.round(zoom * 100)}%</span>
          <div className="mx-2 h-6 w-px bg-gray-600" />
          {unsavedCount > 0 && (
            <span className="rounded bg-amber-500/80 px-2 py-0.5 text-xs text-white">
              ● {unsavedCount} unsaved
            </span>
          )}
          <button
            onClick={handleSave}
            disabled={(!dirty && pendingTextEdits.length === 0) || saving}
            className="flex items-center gap-2 rounded bg-green-600 px-3 py-1.5 text-sm text-white hover:bg-green-500 disabled:opacity-40"
          >
            {saving ? (
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
            ) : (
              <Save className="h-4 w-4" />
            )}
            Save
          </button>
        </div>

        <div className="flex items-center gap-2">
          <Link
            to={`/pdf/${id}/view`}
            className="rounded bg-[#60a5fa] px-3 py-1.5 text-sm text-white hover:bg-[#3b82f6]"
          >
            View PDF
          </Link>
        </div>
      </header>

      {/* Page nav */}
      <div className="flex shrink-0 items-center justify-center gap-2 border-b border-gray-700 bg-[#0f172a] px-4 py-2">
        <button
          onClick={() => setCurrentPage((p) => Math.max(0, p - 1))}
          disabled={currentPage === 0}
          className="rounded p-2 text-gray-400 hover:bg-gray-600 hover:text-white disabled:opacity-40"
        >
          <ChevronLeft className="h-5 w-5" />
        </button>
        <span className="text-sm text-gray-300">
          Page {currentPage + 1} / {numPages || 1}
        </span>
        <button
          onClick={() => setCurrentPage((p) => Math.min(numPages - 1, p + 1))}
          disabled={currentPage >= numPages - 1}
          className="rounded p-2 text-gray-400 hover:bg-gray-600 hover:text-white disabled:opacity-40"
        >
          <ChevronRight className="h-5 w-5" />
        </button>
      </div>

      {/* Warning banner when page structure changed */}
      {pendingPageOps.some(
        (op) => (op.action === 'delete' || op.action === 'reorder') && op.type === 'page'
      ) && (
        <div className="flex shrink-0 items-center justify-center gap-2 border-b border-amber-500/50 bg-amber-500/10 px-4 py-2 text-amber-200">
          <span className="font-medium">⚠</span>
          <span>
            Page structure changed. Save to apply, then re-open to continue annotating.
          </span>
        </div>
      )}

      {/* Main content: Sidebar | Canvas | Properties */}
      <div className="flex flex-1 overflow-hidden">
        <div className="flex w-[200px] shrink-0 flex-col overflow-hidden border-r border-gray-700 bg-[#111827]">
          <ToolbarSidebar
            activeTool={activeTool}
            setActiveTool={setActiveTool}
            fabricCanvas={fabricRef.current}
            currentPage={currentPage}
            toolSettings={toolSettings}
            setToolSettings={setToolSettings}
          />
          <PageManagerPanel
            thumbnails={thumbnails}
            currentPage={currentPage + 1}
            onSelect={(page) => setCurrentPage(page - 1)}
            onRotate={handleRotatePage}
            onDelete={handleDeletePage}
            totalPages={totalPages || pageOrder.length}
            pageOrder={pageOrder}
            onReorder={handleReorder}
            pagesWithTextEdits={[...new Set(pendingTextEdits.map((e) => e.page))]}
          />
        </div>

        <main
          ref={containerRef}
          className="flex flex-1 items-start justify-center overflow-auto bg-gray-800 p-4"
        >
          <div className="relative" style={{ width: widthPx, height: heightPx }}>
            <div
              ref={pdfLayerRef}
              className="absolute left-0 top-0 bg-white"
              style={{
                width: widthPx,
                height: heightPx,
                boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
              }}
            >
              {pageImg && (
                <img
                  src={pageImg}
                  alt={`Page ${currentPage + 1}`}
                  style={{
                    width: '100%',
                    height: '100%',
                    objectFit: 'fill',
                    display: 'block',
                  }}
                />
              )}
            </div>
            <canvas
              ref={canvasRef}
              className="absolute left-0 top-0"
              style={{
                width: widthPx,
                height: heightPx,
                pointerEvents: activeTool === 'edit-text' ? 'none' : 'auto',
              }}
            />
            {activeTool === 'edit-text' && (
              <div
                ref={overlayRef}
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  width: widthPx,
                  height: heightPx,
                  cursor: hoveredBlock ? 'text' : 'default',
                  zIndex: 10,
                }}
                onMouseMove={handleEditTextMouseMove}
                onClick={handleEditTextClick}
              />
            )}
            {activeTool === 'edit-text' &&
              textBlocks.map((block, i) => {
                const isHovered = hoveredBlock === block
                const isEditing = activeEditBlock === block
                const isEdited = pendingTextEdits.some((e) => e.originalBlock === block)
                return (
                  <div
                    key={i}
                    style={{
                      position: 'absolute',
                      left: block.canvasX ?? 0,
                      top: block.canvasY ?? 0,
                      width: block.canvasW ?? 0,
                      height: block.canvasH ?? 0,
                      border: `1.5px solid ${
                        isEdited ? '#10b981' : isHovered ? '#3b82f6' : 'transparent'
                      }`,
                      background: isEditing
                        ? 'transparent'
                        : isEdited
                          ? 'rgba(16,185,129,.08)'
                          : isHovered
                            ? 'rgba(59,130,246,.08)'
                            : 'transparent',
                      borderRadius: 2,
                      pointerEvents: 'none',
                      zIndex: 9,
                      boxSizing: 'border-box',
                    }}
                  />
                )
              })}
            {activeEditBlock && (
              <textarea
                ref={textareaRef}
                value={editValue}
                onChange={(e) => {
                  setEditValue(e.target.value)
                  const el = e.target
                  el.style.height = 'auto'
                  el.style.height = el.scrollHeight + 'px'
                }}
                onBlur={commitEdit}
                onKeyDown={(e) => {
                  if (e.key === 'Escape') {
                    setActiveEditBlock(null)
                    return
                  }
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    commitEdit()
                  }
                }}
                style={{
                  position: 'absolute',
                  left: (activeEditBlock.canvasX ?? 0) - 2,
                  top: (activeEditBlock.canvasY ?? 0) - 2,
                  width: Math.max((activeEditBlock.canvasW ?? 0) + 40, 120),
                  minHeight: (activeEditBlock.canvasH ?? 0) + 4,
                  fontSize: activeEditBlock.font_size * zoom,
                  fontFamily:
                    activeEditBlock.font_family === 'Times-Roman'
                      ? 'Times New Roman'
                      : activeEditBlock.font_family === 'Courier'
                        ? 'Courier New'
                        : 'Helvetica Neue, Arial, sans-serif',
                  fontWeight: activeEditBlock.bold ? 'bold' : 'normal',
                  fontStyle: activeEditBlock.italic ? 'italic' : 'normal',
                  color: '#000',
                  background: 'rgba(255,255,255,0.97)',
                  border: '2px solid #3b82f6',
                  borderRadius: 3,
                  outline: 'none',
                  resize: 'both',
                  padding: '2px 4px',
                  lineHeight: 1.2,
                  zIndex: 20,
                  boxShadow: '0 2px 12px rgba(59,130,246,0.3)',
                  overflow: 'hidden',
                }}
              />
            )}
            {activeTool === 'edit-text' && noTextBanner && (
              <div
                className="absolute bottom-4 left-1/2 -translate-x-1/2 rounded border border-amber-500/50 bg-amber-500/20 px-4 py-2 text-sm text-amber-200"
                style={{ zIndex: 15 }}
              >
                No selectable text found on this page. This may be a scanned PDF or an image-only
                page. Use the Text tool to add new text instead.
                <button
                  onClick={() => setNoTextBanner(false)}
                  className="ml-2 text-amber-400 hover:text-amber-300"
                >
                  Dismiss
                </button>
              </div>
            )}
          </div>
        </main>

        <PropertiesPanel
          fabricCanvas={fabricRef.current}
          onObjectModified={() => snapshot()}
          pdfId={id}
          currentVersion={version}
          pendingTextEdits={pendingTextEdits.map((e) => ({
            originalBlock: { text: e.originalBlock.text, page: e.page },
            newText: e.newText,
            page: e.page,
          }))}
          onRemovePendingEdit={(i) =>
            setPendingTextEdits((prev) => prev.filter((_, j) => j !== i))
          }
        />
      </div>
    </div>
  )
}

// ——— Tool setup functions ———

function setupTextTool(
  fc: Canvas,
  settings: ToolSettings,
  currentPage: number,
  onModified: () => void
) {
  const handler = (opt: { target?: unknown; e: Event; scenePoint?: { x: number; y: number } }) => {
    if (opt.target) return
    const ptr = opt.scenePoint ?? fc.getScenePoint(opt.e as MouseEvent)
    if (!ptr) return

    const itext = new IText('Type here...', {
      left: ptr.x,
      top: ptr.y,
      fontSize: settings.text.fontSize,
      fontFamily: settings.text.fontFamily,
      fill: settings.text.color,
      fontWeight: settings.text.bold ? 'bold' : 'normal',
      fontStyle: settings.text.italic ? 'italic' : 'normal',
      editable: true,
      selectable: true,
      padding: 5,
      cursorColor: '#3b82f6',
      originX: 'left',
      originY: 'top',
      data: { type: 'text', page: currentPage },
    } as Record<string, unknown>)
    fc.add(itext)
    fc.setActiveObject(itext)
    itext.enterEditing()
    itext.selectAll()
    fc.renderAll()
    onModified()

    itext.once('editing:exited', () => {
      if (!itext.text || itext.text === 'Type here...') fc.remove(itext)
      fc.renderAll()
    })
  }
  fc.on('mouse:down', handler)
}

type DragRectMode = 'highlight' | 'erase' | 'shape-rect'

function setupDragRectTool(
  fc: Canvas,
  mode: DragRectMode,
  settings: ToolSettings,
  currentPage: number,
  onModified: () => void
) {
  let isDrawing = false
  let startX = 0
  let startY = 0
  let rect: Rect | null = null

  const getFill = () => {
    if (mode === 'highlight') return settings.highlight.color
    if (mode === 'erase') return settings.erase.mode === 'whiteout' ? '#FFFFFF' : '#000000'
    return settings.shape.fillColor ?? 'transparent'
  }
  const getOpacity = () => (mode === 'highlight' ? settings.highlight.opacity : 1)
  const getStroke = () => (mode === 'shape-rect' ? settings.shape.strokeColor : 'transparent')
  const getStrokeWidth = () => (mode === 'shape-rect' ? settings.shape.strokeWidth : 0)
  const getDataType = () => (mode === 'shape-rect' ? 'shape' : mode)

  fc.on('mouse:down', (opt: { target?: unknown; e: Event; scenePoint?: { x: number; y: number } }) => {
    if (opt.target && mode !== 'erase') return
    isDrawing = true
    const ptr = opt.scenePoint ?? fc.getScenePoint(opt.e as MouseEvent)
    if (!ptr) return
    startX = ptr.x
    startY = ptr.y
    rect = new Rect({
      left: startX,
      top: startY,
      width: 0,
      height: 0,
      fill: getFill(),
      opacity: getOpacity(),
      stroke: getStroke(),
      strokeWidth: getStrokeWidth(),
      selectable: false,
      evented: false,
      originX: 'left',
      originY: 'top',
      data: { type: getDataType(), shape_type: 'rectangle', page: currentPage },
    } as Record<string, unknown>)
    fc.add(rect)
    fc.renderAll()
  })

  fc.on('mouse:move', (opt: { e: Event; scenePoint?: { x: number; y: number } }) => {
    if (!isDrawing || !rect) return
    const ptr = opt.scenePoint ?? fc.getScenePoint(opt.e as MouseEvent)
    if (!ptr) return
    const w = ptr.x - startX
    const h = ptr.y - startY
    rect.set({
      left: w < 0 ? ptr.x : startX,
      top: h < 0 ? ptr.y : startY,
      width: Math.abs(w),
      height: Math.abs(h),
    })
    fc.renderAll()
  })

  fc.on('mouse:up', () => {
    if (!rect) return
    isDrawing = false
    if ((rect.width ?? 0) < 4 || (rect.height ?? 0) < 4) {
      fc.remove(rect)
      rect = null
      return
    }
    rect.set({ selectable: true, evented: true })
    fc.setActiveObject(rect)
    fc.renderAll()
    onModified()
    rect = null
  })
}

function setupDrawTool(
  fc: Canvas,
  settings: ToolSettings,
  currentPage: number,
  onModified: () => void
) {
  fc.isDrawingMode = true
  const brush = new PencilBrush(fc)
  brush.color = settings.draw.color
  brush.width = settings.draw.strokeWidth
  fc.freeDrawingBrush = brush

  fc.on('path:created', (opt: { path: { set: (p: Record<string, unknown>) => void } }) => {
    opt.path.set({ data: { type: 'draw', page: currentPage } })
    onModified()
  })
}

function setupLineTool(
  fc: Canvas,
  settings: ToolSettings,
  currentPage: number,
  onModified: () => void
) {
  let isDrawing = false
  let startX = 0
  let startY = 0
  let line: Line | null = null

  fc.on('mouse:down', (opt: { e: Event; scenePoint?: { x: number; y: number } }) => {
    isDrawing = true
    const ptr = opt.scenePoint ?? fc.getScenePoint(opt.e as MouseEvent)
    if (!ptr) return
    startX = ptr.x
    startY = ptr.y
    line = new Line([startX, startY, startX, startY], {
      stroke: settings.shape.strokeColor,
      strokeWidth: settings.shape.strokeWidth,
      selectable: false,
      evented: false,
      data: { type: 'shape', shape_type: 'line', page: currentPage },
    } as Record<string, unknown>)
    fc.add(line)
    fc.renderAll()
  })

  fc.on('mouse:move', (opt: { e: Event; scenePoint?: { x: number; y: number } }) => {
    if (!isDrawing || !line) return
    const ptr = opt.scenePoint ?? fc.getScenePoint(opt.e as MouseEvent)
    if (!ptr) return
    line.set({ x2: ptr.x, y2: ptr.y })
    fc.renderAll()
  })

  fc.on('mouse:up', () => {
    if (!line) return
    isDrawing = false
    line.set({ selectable: true, evented: true })
    fc.renderAll()
    onModified()
    line = null
  })
}
