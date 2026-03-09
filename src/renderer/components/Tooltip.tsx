import { useState, useRef, useCallback, useEffect, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

type Position = 'top' | 'bottom' | 'left' | 'right'

interface TooltipProps {
  content: string | ReactNode
  children: ReactNode
  position?: Position
  maxWidth?: number
}

const ARROW_SIZE = 6
const VIEWPORT_PADDING = 8

function getCoords(
  triggerRect: DOMRect,
  tooltipRect: DOMRect,
  position: Position,
): { top: number; left: number; actualPosition: Position } {
  const scrollX = window.scrollX
  const scrollY = window.scrollY
  let top = 0
  let left = 0
  let actualPosition = position

  const calc = (pos: Position) => {
    switch (pos) {
      case 'top':
        top = triggerRect.top + scrollY - tooltipRect.height - ARROW_SIZE - 4
        left = triggerRect.left + scrollX + triggerRect.width / 2 - tooltipRect.width / 2
        break
      case 'bottom':
        top = triggerRect.bottom + scrollY + ARROW_SIZE + 4
        left = triggerRect.left + scrollX + triggerRect.width / 2 - tooltipRect.width / 2
        break
      case 'left':
        top = triggerRect.top + scrollY + triggerRect.height / 2 - tooltipRect.height / 2
        left = triggerRect.left + scrollX - tooltipRect.width - ARROW_SIZE - 4
        break
      case 'right':
        top = triggerRect.top + scrollY + triggerRect.height / 2 - tooltipRect.height / 2
        left = triggerRect.right + scrollX + ARROW_SIZE + 4
        break
    }
  }

  calc(position)

  // Flip if overflowing viewport
  const vw = window.innerWidth
  const vh = window.innerHeight
  if (position === 'top' && top - scrollY < VIEWPORT_PADDING) {
    actualPosition = 'bottom'
    calc('bottom')
  } else if (position === 'bottom' && top - scrollY + tooltipRect.height > vh - VIEWPORT_PADDING) {
    actualPosition = 'top'
    calc('top')
  } else if (position === 'left' && left - scrollX < VIEWPORT_PADDING) {
    actualPosition = 'right'
    calc('right')
  } else if (position === 'right' && left - scrollX + tooltipRect.width > vw - VIEWPORT_PADDING) {
    actualPosition = 'left'
    calc('left')
  }

  // Clamp horizontal
  left = Math.max(scrollX + VIEWPORT_PADDING, Math.min(left, scrollX + vw - tooltipRect.width - VIEWPORT_PADDING))
  // Clamp vertical
  top = Math.max(scrollY + VIEWPORT_PADDING, Math.min(top, scrollY + vh - tooltipRect.height - VIEWPORT_PADDING))

  return { top, left, actualPosition }
}

const arrowPositionStyles: Record<Position, React.CSSProperties> = {
  top: { bottom: 0, left: '50%', transform: 'translateX(-50%) translateY(100%)', borderColor: 'rgb(17 24 39) transparent transparent transparent' },
  bottom: { top: 0, left: '50%', transform: 'translateX(-50%) translateY(-100%)', borderColor: 'transparent transparent rgb(17 24 39) transparent' },
  left: { right: 0, top: '50%', transform: 'translateY(-50%) translateX(100%)', borderColor: 'transparent transparent transparent rgb(17 24 39)' },
  right: { left: 0, top: '50%', transform: 'translateY(-50%) translateX(-100%)', borderColor: 'transparent rgb(17 24 39) transparent transparent' },
}

const translateFrom: Record<Position, string> = {
  top: 'translate-y-1',
  bottom: '-translate-y-1',
  left: 'translate-x-1',
  right: '-translate-x-1',
}

export default function Tooltip({ content, children, position = 'top', maxWidth = 280 }: TooltipProps) {
  const [visible, setVisible] = useState(false)
  const [coords, setCoords] = useState<{ top: number; left: number; actualPosition: Position } | null>(null)
  const triggerRef = useRef<HTMLSpanElement>(null)
  const tooltipRef = useRef<HTMLDivElement>(null)
  const showTimeout = useRef<ReturnType<typeof setTimeout>>()
  const hideTimeout = useRef<ReturnType<typeof setTimeout>>()

  const updatePosition = useCallback(() => {
    if (!triggerRef.current || !tooltipRef.current) return
    const triggerRect = triggerRef.current.getBoundingClientRect()
    const tooltipRect = tooltipRef.current.getBoundingClientRect()
    setCoords(getCoords(triggerRect, tooltipRect, position))
  }, [position])

  const show = useCallback(() => {
    clearTimeout(hideTimeout.current)
    showTimeout.current = setTimeout(() => {
      setVisible(true)
    }, 150)
  }, [])

  const hide = useCallback(() => {
    clearTimeout(showTimeout.current)
    hideTimeout.current = setTimeout(() => {
      setVisible(false)
      setCoords(null)
    }, 100)
  }, [])

  useEffect(() => {
    if (visible) {
      // Use rAF to measure after the portal renders
      const id = requestAnimationFrame(updatePosition)
      return () => cancelAnimationFrame(id)
    }
  }, [visible, updatePosition])

  useEffect(() => {
    return () => {
      clearTimeout(showTimeout.current)
      clearTimeout(hideTimeout.current)
    }
  }, [])

  const actualPos = coords?.actualPosition ?? position

  return (
    <>
      <span
        ref={triggerRef}
        onMouseEnter={show}
        onMouseLeave={hide}
        className="inline-flex"
      >
        {children}
      </span>
      {visible &&
        createPortal(
          <div
            ref={tooltipRef}
            onMouseEnter={show}
            onMouseLeave={hide}
            className={`absolute z-[9999] transition-all duration-150 ease-out ${
              coords ? 'opacity-100 translate-x-0 translate-y-0' : `opacity-0 ${translateFrom[actualPos]}`
            }`}
            style={{
              top: coords?.top ?? -9999,
              left: coords?.left ?? -9999,
              maxWidth,
              pointerEvents: coords ? 'auto' : 'none',
            }}
          >
            <div className="bg-gray-900 text-white text-xs rounded-lg shadow-lg px-3 py-2 relative">
              {content}
              <span
                className="absolute w-0 h-0 border-solid"
                style={{ borderWidth: ARROW_SIZE, ...arrowPositionStyles[actualPos] }}
              />
            </div>
          </div>,
          document.body,
        )}
    </>
  )
}
