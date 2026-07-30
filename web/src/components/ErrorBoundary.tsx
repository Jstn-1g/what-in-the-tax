import { Component, type ReactNode } from 'react'

type Props = { children: ReactNode }
type State = { failed: boolean }

/**
 * Last-resort catch for render-time crashes. Every data-loading failure below
 * this point already has its own recoverable UI state; this exists so a defect
 * in render logic itself degrades to a readable, retryable message instead of
 * an empty page.
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { failed: false }

  static getDerivedStateFromError(): State {
    return { failed: true }
  }

  render() {
    if (this.state.failed) {
      return (
        <main>
          <div className="chooser-alert" role="alert">
            <strong>Something went wrong displaying this page</strong>
            <p>
              The page hit an unexpected error while rendering. Reloading
              usually resolves it, and nothing you entered is stored on a
              server.
            </p>
            <button
              type="button"
              className="button button-secondary"
              onClick={() => window.location.reload()}
            >
              Reload the page
            </button>
          </div>
        </main>
      )
    }
    return this.props.children
  }
}
