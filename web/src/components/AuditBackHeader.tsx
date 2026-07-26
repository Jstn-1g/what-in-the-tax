type AuditBackHeaderProps = {
  currentPlace?: string
  onChoosePlace: () => void
  onOpenHelp: () => void
}

function BrandMark() {
  return (
    <svg
      className="brand-mark"
      viewBox="0 0 40 44"
      width="32"
      height="35"
      aria-hidden="true"
    >
      <path
        d="M8 2.5h16l9.5 9.5v20.5A7.5 7.5 0 0 1 26 40H8a5.5 5.5 0 0 1-5.5-5.5V8A5.5 5.5 0 0 1 8 2.5Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinejoin="round"
      />
      <path
        d="M24 3v9h9"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinejoin="round"
      />
      <path
        d="M20 22H9.5m0 0 4-4m-4 4 4 4M10 31h10.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
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

export default function AuditBackHeader({
  currentPlace,
  onChoosePlace,
  onOpenHelp,
}: AuditBackHeaderProps) {
  return (
    <header className="site-header">
      <div className="site-header-inner">
        <button
          type="button"
          className="wordmark"
          aria-label="AuditBack home — choose a place"
          onClick={onChoosePlace}
        >
          <BrandMark />
          <span>AuditBack</span>
        </button>
        <nav className="site-actions" aria-label="Product">
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
                ? `Choose a different place. Current place: ${currentPlace}`
                : 'Choose a place'
            }
          >
            <PlaceIcon />
            <span>{currentPlace ?? 'Choose a place'}</span>
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
