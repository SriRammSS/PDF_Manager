/**
 * ToolbarSidebar — Fixed left sidebar with tool list and tool-specific settings.
 */

import {
  MousePointer2,
  Type,
  Highlighter,
  Eraser,
  Pencil,
  Square,
  Minus,
  Bold,
  Italic,
  PenLine,
} from 'lucide-react'

export type ToolId =
  | 'select'
  | 'text'
  | 'edit-text'
  | 'highlight'
  | 'erase'
  | 'draw'
  | 'shape-rect'
  | 'shape-line'

export interface ToolSettings {
  text: {
    fontFamily: string
    fontSize: number
    bold: boolean
    italic: boolean
    color: string
  }
  highlight: {
    color: string
    opacity: number
  }
  erase: {
    mode: 'whiteout' | 'redact'
  }
  draw: {
    color: string
    strokeWidth: number
  }
  shape: {
    strokeColor: string
    fillColor: string | null
    strokeWidth: number
  }
}

export const DEFAULT_TOOL_SETTINGS: ToolSettings = {
  text: {
    fontFamily: 'Helvetica',
    fontSize: 14,
    bold: false,
    italic: false,
    color: '#000000',
  },
  highlight: {
    color: '#FFFF00',
    opacity: 0.4,
  },
  erase: {
    mode: 'whiteout',
  },
  draw: {
    color: '#000000',
    strokeWidth: 3,
  },
  shape: {
    strokeColor: '#000000',
    fillColor: null,
    strokeWidth: 2,
  },
}

const HIGHLIGHT_COLORS = [
  { hex: '#FFFF00', label: 'Yellow' },
  { hex: '#90EE90', label: 'Green' },
  { hex: '#FFB6C1', label: 'Pink' },
  { hex: '#ADD8E6', label: 'Blue' },
  { hex: '#FFA07A', label: 'Orange' },
]

const FONT_FAMILIES = ['Helvetica', 'Times New Roman', 'Courier New']

const TOOLS: { id: ToolId; icon: typeof Type; label: string; shortcut: string }[] = [
  { id: 'select', icon: MousePointer2, label: 'Select & Move', shortcut: 'S' },
  { id: 'text', icon: Type, label: 'Add Text', shortcut: 'T' },
  { id: 'edit-text', icon: PenLine, label: 'Edit Text', shortcut: 'X' },
  { id: 'highlight', icon: Highlighter, label: 'Highlight', shortcut: 'H' },
  { id: 'erase', icon: Eraser, label: 'Erase / Redact', shortcut: 'E' },
  { id: 'draw', icon: Pencil, label: 'Freehand Draw', shortcut: 'D' },
  { id: 'shape-rect', icon: Square, label: 'Rectangle', shortcut: 'R' },
  { id: 'shape-line', icon: Minus, label: 'Line', shortcut: 'L' },
]

interface ToolbarSidebarProps {
  activeTool: ToolId
  setActiveTool: (t: ToolId) => void
  fabricCanvas: import('fabric').Canvas | null
  currentPage: number
  toolSettings: ToolSettings
  setToolSettings: React.Dispatch<React.SetStateAction<ToolSettings>>
}

export default function ToolbarSidebar({
  activeTool,
  setActiveTool,
  toolSettings,
  setToolSettings,
}: ToolbarSidebarProps) {
  return (
    <aside
      className="flex w-[200px] shrink-0 flex-col border-r border-gray-700 bg-[#111827]"
      style={{ minWidth: 200 }}
    >
      {/* Tool list */}
      <div className="flex flex-col gap-0.5 p-2">
        {TOOLS.map(({ id, icon: Icon, label, shortcut }) => (
          <button
            key={id}
            onClick={() => setActiveTool(id)}
            className={`flex items-center gap-2 rounded px-3 py-2 text-left text-sm transition-colors ${
              activeTool === id
                ? 'border border-[#3b82f6] bg-[#1e40af]/60 text-white'
                : 'text-gray-300 hover:bg-gray-700 hover:text-white'
            }`}
          >
            <Icon className="h-4 w-4 shrink-0" />
            <span className="flex-1 truncate">{label}</span>
            <span className="rounded bg-gray-600 px-1.5 py-0.5 text-xs text-gray-400">
              {shortcut}
            </span>
          </button>
        ))}
      </div>

      <div className="h-px shrink-0 bg-gray-700" />

      {/* Tool-specific settings */}
      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        {activeTool === 'text' && (
          <TextSettings settings={toolSettings.text} setSettings={(s) => setToolSettings((prev) => ({ ...prev, text: s }))} />
        )}
        {activeTool === 'highlight' && (
          <HighlightSettings
            settings={toolSettings.highlight}
            setSettings={(s) => setToolSettings((prev) => ({ ...prev, highlight: s }))}
          />
        )}
        {activeTool === 'erase' && (
          <EraseSettings
            settings={toolSettings.erase}
            setSettings={(s) => setToolSettings((prev) => ({ ...prev, erase: s }))}
          />
        )}
        {activeTool === 'draw' && (
          <DrawSettings
            settings={toolSettings.draw}
            setSettings={(s) => setToolSettings((prev) => ({ ...prev, draw: s }))}
          />
        )}
        {(activeTool === 'shape-rect' || activeTool === 'shape-line') && (
          <ShapeSettings
            settings={toolSettings.shape}
            setSettings={(s) => setToolSettings((prev) => ({ ...prev, shape: s }))}
          />
        )}
        {activeTool === 'select' && (
          <p className="text-xs text-gray-500">Click and drag to select objects.</p>
        )}
        {activeTool === 'edit-text' && (
          <div className="space-y-3 text-xs text-gray-500" style={{ lineHeight: 1.6 }}>
            <div className="font-semibold text-gray-400">✍️ Edit Existing Text</div>
            <div>
              Hover to highlight text blocks. Click any text to edit it inline.
            </div>
            <div
              className="rounded border p-2 text-amber-200"
              style={{
                background: 'rgba(245,158,11,.08)',
                borderColor: 'rgba(245,158,11,.2)',
                fontSize: 11,
              }}
            >
              ⚠ Font may not match exactly. PDF fonts are embedded and cannot be
              directly accessed. We use the closest standard font.
            </div>
          </div>
        )}
      </div>
    </aside>
  )
}

function TextSettings({
  settings,
  setSettings,
}: {
  settings: ToolSettings['text']
  setSettings: (s: ToolSettings['text']) => void
}) {
  return (
    <div className="space-y-3">
      <h4 className="text-xs font-semibold text-gray-400">Text Settings</h4>
      <div>
        <label className="mb-1 block text-xs text-gray-500">Font</label>
        <select
          value={settings.fontFamily}
          onChange={(e) => setSettings({ ...settings, fontFamily: e.target.value })}
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
        <label className="mb-1 block text-xs text-gray-500">Size (8–200)</label>
        <input
          type="number"
          min={8}
          max={200}
          value={settings.fontSize}
          onChange={(e) => setSettings({ ...settings, fontSize: Math.max(8, Math.min(200, Number(e.target.value) || 14)) })}
          className="w-full rounded border border-gray-600 bg-gray-800 px-2 py-1.5 text-sm text-white"
        />
      </div>
      <div className="flex gap-1">
        <button
          onClick={() => setSettings({ ...settings, bold: !settings.bold })}
          className={`rounded px-2 py-1.5 ${settings.bold ? 'bg-[#3b82f6] text-white' : 'bg-gray-700 text-gray-400 hover:bg-gray-600'}`}
          title="Bold"
        >
          <Bold className="h-4 w-4" />
        </button>
        <button
          onClick={() => setSettings({ ...settings, italic: !settings.italic })}
          className={`rounded px-2 py-1.5 ${settings.italic ? 'bg-[#3b82f6] text-white' : 'bg-gray-700 text-gray-400 hover:bg-gray-600'}`}
          title="Italic"
        >
          <Italic className="h-4 w-4" />
        </button>
      </div>
      <div>
        <label className="mb-1 block text-xs text-gray-500">Color</label>
        <div className="flex items-center gap-2">
          <input
            type="color"
            value={settings.color}
            onChange={(e) => setSettings({ ...settings, color: e.target.value })}
            className="h-8 w-12 cursor-pointer rounded border border-gray-600 bg-transparent"
          />
          <span className="text-xs text-gray-400">{settings.color}</span>
        </div>
      </div>
      <div className="rounded border border-gray-600 bg-gray-800 p-2">
        <span
          className="text-lg"
          style={{
            fontFamily: settings.fontFamily,
            fontSize: settings.fontSize,
            color: settings.color,
            fontWeight: settings.bold ? 'bold' : 'normal',
            fontStyle: settings.italic ? 'italic' : 'normal',
          }}
        >
          Aa
        </span>
      </div>
    </div>
  )
}

function HighlightSettings({
  settings,
  setSettings,
}: {
  settings: ToolSettings['highlight']
  setSettings: (s: ToolSettings['highlight']) => void
}) {
  return (
    <div className="space-y-3">
      <h4 className="text-xs font-semibold text-gray-400">Highlight Color</h4>
      <div className="flex flex-wrap gap-2">
        {HIGHLIGHT_COLORS.map(({ hex }) => (
          <button
            key={hex}
            onClick={() => setSettings({ ...settings, color: hex })}
            className={`h-8 w-8 rounded border-2 transition-all ${
              settings.color === hex ? 'border-white ring-2 ring-[#3b82f6]' : 'border-gray-600 hover:border-gray-500'
            }`}
            style={{ backgroundColor: hex }}
            title={hex}
          />
        ))}
      </div>
      <div>
        <label className="mb-1 block text-xs text-gray-500">
          Opacity {Math.round(settings.opacity * 100)}%
        </label>
        <input
          type="range"
          min={0.1}
          max={1}
          step={0.1}
          value={settings.opacity}
          onChange={(e) => setSettings({ ...settings, opacity: Number(e.target.value) })}
          className="w-full"
        />
      </div>
    </div>
  )
}

function EraseSettings({
  settings,
  setSettings,
}: {
  settings: ToolSettings['erase']
  setSettings: (s: ToolSettings['erase']) => void
}) {
  return (
    <div className="space-y-3">
      <h4 className="text-xs font-semibold text-gray-400">Erase Mode</h4>
      <div className="flex flex-col gap-2">
        <button
          onClick={() => setSettings({ mode: 'whiteout' })}
          className={`flex items-center gap-2 rounded px-3 py-2 text-left text-sm ${
            settings.mode === 'whiteout' ? 'bg-[#3b82f6]/30 border border-[#3b82f6]' : 'bg-gray-700 hover:bg-gray-600'
          }`}
        >
          <span className={`h-3 w-3 rounded-full border ${settings.mode === 'whiteout' ? 'border-[#3b82f6] bg-[#3b82f6]' : 'border-gray-500'}`} />
          <span>Whiteout</span>
          <span className="ml-auto rounded bg-white px-1.5 py-0.5 text-xs text-gray-800">#FFF</span>
        </button>
        <button
          onClick={() => setSettings({ mode: 'redact' })}
          className={`flex items-center gap-2 rounded px-3 py-2 text-left text-sm ${
            settings.mode === 'redact' ? 'bg-[#3b82f6]/30 border border-[#3b82f6]' : 'bg-gray-700 hover:bg-gray-600'
          }`}
        >
          <span className={`h-3 w-3 rounded-full border ${settings.mode === 'redact' ? 'border-[#3b82f6] bg-[#3b82f6]' : 'border-gray-500'}`} />
          <span>Redact</span>
          <span className="ml-auto rounded bg-black px-1.5 py-0.5 text-xs text-white">#000</span>
        </button>
      </div>
    </div>
  )
}

function DrawSettings({
  settings,
  setSettings,
}: {
  settings: ToolSettings['draw']
  setSettings: (s: ToolSettings['draw']) => void
}) {
  return (
    <div className="space-y-3">
      <h4 className="text-xs font-semibold text-gray-400">Draw Settings</h4>
      <div>
        <label className="mb-1 block text-xs text-gray-500">Color</label>
        <div className="flex items-center gap-2">
          <input
            type="color"
            value={settings.color}
            onChange={(e) => setSettings({ ...settings, color: e.target.value })}
            className="h-8 w-12 cursor-pointer rounded border border-gray-600 bg-transparent"
          />
        </div>
      </div>
      <div>
        <label className="mb-1 block text-xs text-gray-500">Stroke width (1–20px)</label>
        <input
          type="range"
          min={1}
          max={20}
          value={settings.strokeWidth}
          onChange={(e) => setSettings({ ...settings, strokeWidth: Number(e.target.value) })}
          className="w-full"
        />
        <div className="mt-1 flex items-center gap-2">
          <div
            className="rounded bg-gray-700"
            style={{ height: settings.strokeWidth, width: 40, backgroundColor: settings.color }}
          />
          <span className="text-xs text-gray-400">{settings.strokeWidth}px</span>
        </div>
      </div>
    </div>
  )
}

function ShapeSettings({
  settings,
  setSettings,
}: {
  settings: ToolSettings['shape']
  setSettings: (s: ToolSettings['shape']) => void
}) {
  return (
    <div className="space-y-3">
      <h4 className="text-xs font-semibold text-gray-400">Shape Settings</h4>
      <div>
        <label className="mb-1 block text-xs text-gray-500">Stroke color</label>
        <input
          type="color"
          value={settings.strokeColor}
          onChange={(e) => setSettings({ ...settings, strokeColor: e.target.value })}
          className="h-8 w-full cursor-pointer rounded border border-gray-600 bg-transparent"
        />
      </div>
      <div>
        <label className="mb-1 flex items-center gap-2 text-xs text-gray-500">
          <input
            type="checkbox"
            checked={settings.fillColor === null}
            onChange={(e) =>
              setSettings({ ...settings, fillColor: e.target.checked ? null : '#000000' })
            }
          />
          No fill
        </label>
        {settings.fillColor !== null && (
          <input
            type="color"
            value={settings.fillColor}
            onChange={(e) => setSettings({ ...settings, fillColor: e.target.value })}
            className="mt-1 h-8 w-full cursor-pointer rounded border border-gray-600 bg-transparent"
          />
        )}
      </div>
      <div>
        <label className="mb-1 block text-xs text-gray-500">Stroke width (1–10px)</label>
        <input
          type="range"
          min={1}
          max={10}
          value={settings.strokeWidth}
          onChange={(e) => setSettings({ ...settings, strokeWidth: Number(e.target.value) })}
          className="w-full"
        />
        <span className="text-xs text-gray-400">{settings.strokeWidth}px</span>
      </div>
    </div>
  )
}
