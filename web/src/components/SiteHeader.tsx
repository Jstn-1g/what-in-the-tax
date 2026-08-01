import ThemeToggle from './ThemeToggle'
import { repoBaseUrl } from '../repoLink'

type SiteHeaderProps = {
  currentPlace?: string
  onChoosePlace: () => void
  onOpenHelp: () => void
}

function GitHubMark() {
  // The GitHub invertocat mark, used as GitHub's brand guidance permits: as a
  // link to the project's page on GitHub, unmodified.
  return (
    <svg viewBox="0 0 16 16" width="20" height="20" aria-hidden="true">
      <path
        fill="currentColor"
        d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z"
      />
    </svg>
  )
}

function ContributeIcon() {
  // A branch/fork mark rather than any trademarked logo: two commits joining
  // a line, the visual for "this is built in the open".
  return (
    <svg viewBox="0 0 24 24" width="21" height="21" aria-hidden="true">
      <circle cx="6" cy="6" r="2.4" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <circle cx="6" cy="18" r="2.4" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <circle cx="18" cy="6" r="2.4" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <path
        d="M6 8.4v7.2M18 8.4c0 3.4-3 4.6-6 4.9-2 .2-3.6.8-4.6 2"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
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
          <a
            className="site-action site-action-contribute"
            href={`${repoBaseUrl()}/blob/main/CONTRIBUTING.md`}
            target="_blank"
            rel="noreferrer"
          >
            <ContributeIcon />
            <span>Contribute</span>
            <span className="visually-hidden"> (opens in a new tab)</span>
          </a>
          <a
            className="site-action site-action-github"
            href={repoBaseUrl()}
            target="_blank"
            rel="noreferrer"
            aria-label="View the source on GitHub (opens in a new tab)"
          >
            <GitHubMark />
          </a>
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
