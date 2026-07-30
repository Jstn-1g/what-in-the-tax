// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import ErrorBoundary from './ErrorBoundary'

function Bomb(): never {
  throw new Error('deliberate render failure')
}

afterEach(cleanup)

describe('ErrorBoundary', () => {
  it('renders its children when nothing fails', () => {
    render(
      <ErrorBoundary>
        <p>receipt content</p>
      </ErrorBoundary>,
    )
    expect(screen.getByText('receipt content')).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('replaces a render crash with the fallback alert and a reload control', () => {
    // React logs the caught error to console.error; silence it so the suite
    // output stays readable without hiding other failures.
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    try {
      render(
        <ErrorBoundary>
          <Bomb />
        </ErrorBoundary>,
      )
      const alert = screen.getByRole('alert')
      expect(alert.textContent).toContain('Something went wrong')
      expect(screen.getByRole('button', { name: 'Reload the page' })).toBeTruthy()
    } finally {
      consoleError.mockRestore()
    }
  })
})
