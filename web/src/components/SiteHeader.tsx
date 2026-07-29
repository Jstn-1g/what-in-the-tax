import ThemeToggle from './ThemeToggle'

type SiteHeaderProps = {
  currentPlace?: string
  onChoosePlace: () => void
  onOpenHelp: () => void
}

function PlaceIcon() {
  return (
    <svg viewBox="0 0 24 24" width="21" height="21" aria-hidden="true">
      <path
        d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <circle cx="12" cy="10" r="2.6" fill="none" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  )
}

function HelpIcon() {
  return (
    <svg viewBox="0 0 24 24" width="21" height="21" aria-hidden="true">
      <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <path
        d="M9.7 9a2.45 2.45 0 0 1 4.7 1c0 1.85-2.4 2-2.4 3.6M12 17.5h.01"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  )
}

export default function SiteHeader({
  currentPlace,
  onChoosePlace,
  onOpenHelp,
}: SiteHeaderProps) {
  return (
    <header className="site-header">
      <div className="site-header-inner">
        <button
          type="button"
          className="wordmark"
          aria-label="What in the Tax? home — choose a community"
          onClick={onChoosePlace}
        >
          <span className="wordmark-name">What in the Tax?</span>
          <span className="wordmark-domain">whatinthetax.com</span>
        </button>
        <nav className="site-actions" aria-label="Main navigation">
          <ThemeToggle />
          <button
            type="button"
            className="site-action site-action-help"
            data-help-trigger="site-header"
            onClick={onOpenHelp}
          >
            <HelpIcon />
            <span>How it works</span>
          </button>
          <button
            type="button"
            className="site-action site-action-place"
            onClick={onChoosePlace}
            aria-label={
              currentPlace
                ? `Choose a different community. Current community: ${currentPlace}`
                : 'Choose a community'
            }
          >
            <PlaceIcon />
            <span>{currentPlace ?? 'Choose a community'}</span>
            {currentPlace ? (
              <svg
                className="site-action-caret"
                viewBox="0 0 12 8"
                width="12"
                height="8"
                aria-hidden="true"
              >
                <path
                  d="m1 1.25 5 5 5-5"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.75"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            ) : null}
          </button>
        </nav>
      </div>
    </header>
  )
}
