/**
 * PageManagerPanel — Sortable page thumbnails with rotate/delete.
 */

import {
  DndContext,
  closestCenter,
  type DragEndEvent,
} from '@dnd-kit/core'
import {
  SortableContext,
  verticalListSortingStrategy,
  useSortable,
  arrayMove,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { RotateCw, Trash2, GripVertical } from 'lucide-react'

interface PageManagerPanelProps {
  thumbnails: string[]
  currentPage: number // 1-indexed
  onSelect: (page: number) => void
  onRotate: (pageIndex: number) => void
  onDelete: (pageIndex: number) => void
  totalPages: number
  pageOrder: number[]
  onReorder: (newOrder: number[]) => void
  pagesWithTextEdits?: number[]
}

function SortablePageCard({
  id,
  index,
  thumbnail,
  isActive,
  totalPages,
  onSelect,
  onRotate,
  onDelete,
  hasTextEdits,
}: {
  id: string
  index: number
  thumbnail: string
  isActive: boolean
  totalPages: number
  onSelect: () => void
  onRotate: () => void
  onDelete: () => void
  hasTextEdits?: boolean
}) {
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({ id })
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  }

  return (
    <div
      ref={setNodeRef}
      style={style}
      onClick={() => onSelect()}
      className={`flex cursor-pointer items-center gap-2 rounded border p-2 transition-colors ${
        isActive
          ? 'border-[#3b82f6] bg-[#1e40af]/30'
          : 'border-gray-600 bg-gray-800/50 hover:border-gray-500 hover:bg-gray-700/50'
      }`}
    >
      <div
        {...attributes}
        {...listeners}
        className="flex shrink-0 cursor-grab touch-none items-center justify-center rounded p-1 text-gray-500 hover:bg-gray-600 hover:text-gray-300 active:cursor-grabbing"
        onClick={(e) => e.stopPropagation()}
      >
        <GripVertical className="h-4 w-4" />
      </div>
      <div className="relative min-w-0 flex-1 overflow-hidden rounded bg-white">
        <img
          src={thumbnail}
          alt={`Page ${index + 1}`}
          className="block h-12 w-full object-contain"
        />
        {hasTextEdits && (
          <span
            className="absolute right-0.5 top-0.5 rounded bg-green-600 px-1 py-0.5 text-[10px] font-medium text-white"
            title="Has pending text edits"
          >
            edited
          </span>
        )}
      </div>
      <div className="flex shrink-0 flex-col items-center gap-0.5">
        <span className="text-xs font-medium text-gray-300">Page {index + 1}</span>
        <div className="flex gap-0.5">
          <button
            onClick={(e) => {
              e.stopPropagation()
              onRotate()
            }}
            title="Rotate 90°"
            className="rounded p-1 text-gray-500 hover:bg-gray-600 hover:text-gray-300"
            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 2 }}
          >
            <RotateCw className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation()
              onDelete()
            }}
            title="Delete page"
            disabled={totalPages <= 1}
            className="rounded p-1 disabled:cursor-not-allowed disabled:opacity-50"
            style={{
              background: 'none',
              border: 'none',
              cursor: totalPages > 1 ? 'pointer' : 'not-allowed',
              color: totalPages > 1 ? '#ef4444' : '#374151',
              padding: 2,
            }}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </div>
  )
}

export default function PageManagerPanel({
  thumbnails,
  currentPage,
  onSelect,
  onRotate,
  onDelete,
  totalPages,
  pageOrder,
  onReorder,
  pagesWithTextEdits = [],
}: PageManagerPanelProps) {
  const editsSet = new Set(pagesWithTextEdits)
  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event
    if (!over || active.id === over.id) return
    const oldIdx = pageOrder.indexOf(Number(active.id))
    const newIdx = pageOrder.indexOf(Number(over.id))
    if (oldIdx === -1 || newIdx === -1) return
    const newOrder = arrayMove(pageOrder, oldIdx, newIdx)
    onReorder(newOrder)
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden border-t border-gray-700 bg-[#111827] p-2">
      <h3 className="mb-2 shrink-0 px-2 text-xs font-semibold uppercase tracking-wider text-gray-400">
        Pages
      </h3>
      <DndContext collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={pageOrder.map(String)} strategy={verticalListSortingStrategy}>
          <div className="flex flex-col gap-1.5 overflow-y-auto">
            {pageOrder.map((origPageIdx, displayIdx) => {
              const thumb = thumbnails[displayIdx]
              if (!thumb) return null
              return (
                <SortablePageCard
                  key={origPageIdx}
                  id={String(origPageIdx)}
                  index={displayIdx}
                  thumbnail={thumb}
                  isActive={currentPage === displayIdx + 1}
                  totalPages={totalPages}
                  onSelect={() => onSelect(displayIdx + 1)}
                  onRotate={() => onRotate(displayIdx)}
                  onDelete={() => onDelete(displayIdx)}
                  hasTextEdits={editsSet.has(origPageIdx)}
                />
              )
            })}
          </div>
        </SortableContext>
      </DndContext>
    </div>
  )
}
