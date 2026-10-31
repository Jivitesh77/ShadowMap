import type { KeyboardEvent } from 'react'

/** Keyboard support for a role="tablist" (WAI-ARIA tabs): Left / Right move between tabs, Home / End jump to the first /
 *  last one; the tab is selected and focused. Use with tabIndex={selected ? 0 : -1} on each tab. */
export function tabKeys<T>(values: readonly T[], current: T, select: (value: T) => void) {
  return (e: KeyboardEvent<HTMLElement>) => {
    const i = values.indexOf(current)
    const next =
      e.key === 'ArrowRight' ? (i + 1) % values.length
        : e.key === 'ArrowLeft' ? (i - 1 + values.length) % values.length
          : e.key === 'Home' ? 0
            : e.key === 'End' ? values.length - 1
              : -1
    if (next < 0) return
    e.preventDefault()
    select(values[next])
    const tabs = e.currentTarget.querySelectorAll<HTMLElement>('[role="tab"]')
    tabs[next]?.focus()
  }
}
