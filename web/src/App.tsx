import { useEffect, useRef, useState } from 'react'
import HelpGuide from './components/HelpGuide'
import PlaceFinder from './components/PlaceFinder'
import SiteHeader from './components/SiteHeader'
import SupportCard from './components/SupportCard'
import TaxReceiptScreen from './components/TaxReceiptScreen'
import {
  getPackCatalogEntry,
  loadPack,
  PACK_CATALOG,
  packRouteFromSearch,
  type PackEntry,
  type PackId,
  type PackRoute,
} from './packs'

type ViewId = 'receipt' | 'help'
type LoadedPack = { id: PackId; pack: PackEntry }
type LoadFailure = { id: PackId }

const HELP_HASH_ROOT = 'help'
const HELP_HISTORY_KEY = 'whatInTheTaxHelpEntry'

function hashId(): string {
  if (typeof window === 'undefined') return ''
  const value = window.location.hash.replace(/^#/, '')
  try {
    return decodeURIComponent(value)
  } catch {
    return value
  }
}

function viewFromHash(): ViewId {
  const id = hashId()
  return id === HELP_HASH_ROOT || id.startsWith(`${HELP_HASH_ROOT}/`)
    ? 'help'
    : 'receipt'
}

function focusTargetFromLocation(route: PackRoute, view: ViewId): string {
  const id = hashId()
  if (view === 'help') {
    return id.startsWith(`${HELP_HASH_ROOT}/`) ? id : 'help-heading'
  }
  if (id && !id.startsWith(`${HELP_HASH_ROOT}/`)) return id
  return route.kind === 'pack' ? 'receipt-hero' : 'place-chooser'
}

function focusElementById(id: string): boolean {
  const target = document.getElementById(id)
  if (!(target instanceof HTMLElement)) return false
  if (
    !target.matches(
      'a[href], button, input, select, textarea, summary, [tabindex]',
    )
  ) {
    target.tabIndex = -1
  }
  target.focus({ preventScroll: true })
  return document.activeElement === target
}

function isHelpHistoryEntry(): boolean {
  const state: unknown = history.state
  return Boolean(
    state &&
      typeof state === 'object' &&
      HELP_HISTORY_KEY in state &&
      (state as Record<string, unknown>)[HELP_HISTORY_KEY] === true,
  )
}

function currentPackRoute(): PackRoute {
  if (typeof window === 'undefined') return { kind: 'chooser' }
  return packRouteFromSearch(window.location.search)
}

function writePackToUrl(id: PackId) {
  const url = new URL(window.location.href)
  url.searchParams.set('pack', id)
  url.hash = ''
  history.pushState(null, '', `${url.pathname}${url.search}`)
}

function writeChooserToUrl() {
  const url = new URL(window.location.href)
  url.searchParams.delete('pack')
  url.hash = ''
  history.pushState(null, '', `${url.pathname}${url.search}`)
}

function setDocumentMeta(route: PackRoute) {
  const metadata =
    route.kind === 'pack' || route.kind === 'blocked'
      ? getPackCatalogEntry(route.id)
      : null
  const title =
    route.kind === 'blocked'
      ? `${metadata?.label ?? 'Receipt'} receipt unavailable · What in the Tax?`
      : metadata
        ? `${metadata.label} property-tax receipt · What in the Tax?`
        : route.kind === 'unknown'
          ? 'Receipt unavailable · What in the Tax?'
          : 'What in the Tax? — Where did your property-tax dollars go?'
  document.title = title

  const description = metadata
    ? `See how a sample residential property-tax bill in ${metadata.label} is divided, with source links for each supported figure. Independent preview; not tax advice.`
    : 'What in the Tax? helps residents explore a sample property-tax bill and the public records behind each supported figure. Independent preview; not tax advice.'
  let meta = document.querySelector('meta[name="description"]')
  if (!meta) {
    meta = document.createElement('meta')
    meta.setAttribute('name', 'description')
    document.head.appendChild(meta)
  }
  meta.setAttribute('content', description)
}

function ProductFooter() {
  return (
    <footer className="product-footer">
      <p>
        Independent public-information project. Not affiliated with any government.
        Not an official bill, formal audit, or tax advice.
      </p>
      <a href={`${import.meta.env.BASE_URL}privacy.txt`}>Privacy</a>
    </footer>
  )
}

function ReceiptSketch() {
  return (
    <svg
      className="chooser-sketch"
      viewBox="0 0 260 240"
      aria-hidden="true"
    >
      <g transform="rotate(5 130 120)">
        <path
          className="chooser-sketch__paper"
          d="M58 18h144v180l-14-11-14 15-17-12-15 15-17-14-17 13-13-16-18 12Z"
        />
        <path
          className="chooser-sketch__leaf"
          d="m130 52 9 22 15-9-6 24 19-2-9 20 17 9-25 18 5 20-20-9-5 31-5-31-20 9 5-20-25-18 17-9-9-20 19 2-6-24 15 9Z"
        />
        <path className="chooser-sketch__line" d="M95 181h70M101 199h58" />
      </g>
      <path className="chooser-sketch__spark" d="m222 38 13-15m-2 35 18-2m-31-4 4-19" />
    </svg>
  )
}

export default function App() {
  const pendingFocusPack = useRef<PackId | null>(null)
  const pendingLocationFocus = useRef<string | null>(
    typeof window !== 'undefined' && viewFromHash() === 'help'
      ? focusTargetFromLocation(currentPackRoute(), 'help')
      : null,
  )
  const pendingHelpTriggerFocus = useRef<string | null>(null)
  const helpReturnFocusKey = useRef<string | null>(null)
  const [route, setRoute] = useState<PackRoute>(currentPackRoute)
  const [loaded, setLoaded] = useState<LoadedPack | null>(null)
  const [loadFailure, setLoadFailure] = useState<LoadFailure | null>(null)
  const [retrySequence, setRetrySequence] = useState(0)
  const [view, setView] = useState<ViewId>(() =>
    typeof window !== 'undefined' ? viewFromHash() : 'receipt',
  )
  const currentView = useRef(view)

  useEffect(() => {
    if (route.kind !== 'pack') {
      setLoaded(null)
      setLoadFailure(null)
      return
    }

    const id = route.id
    let active = true
    setLoaded((current) => (current?.id === id ? current : null))
    setLoadFailure(null)
    loadPack(id).then(
      (pack) => {
        if (active) setLoaded({ id, pack })
      },
      (_error: unknown) => {
        if (active) setLoadFailure({ id })
      },
    )
    return () => {
      active = false
    }
  }, [route, retrySequence])

  useEffect(() => {
    if (view === 'help') {
      document.title = 'How What in the Tax? works · What in the Tax?'
      return
    }
    setDocumentMeta(route)
  }, [route, view])

  useEffect(() => {
    if (route.kind !== 'pack' || loadFailure?.id !== route.id) return
    pendingLocationFocus.current = 'place-chooser'
  }, [loadFailure, route])

  useEffect(() => {
    if (!loaded || pendingFocusPack.current !== loaded.id) return
    pendingFocusPack.current = null
    pendingLocationFocus.current = 'receipt-hero'
  }, [loaded])

  useEffect(() => {
    const syncFromLocation = () => {
      const nextRoute = currentPackRoute()
      const nextView = viewFromHash()
      currentView.current = nextView
      if (nextView === 'receipt' && helpReturnFocusKey.current) {
        pendingHelpTriggerFocus.current = helpReturnFocusKey.current
        helpReturnFocusKey.current = null
      }
      if (!pendingHelpTriggerFocus.current) {
        pendingLocationFocus.current = focusTargetFromLocation(
          nextRoute,
          nextView,
        )
      }
      pendingFocusPack.current = null
      setRoute(nextRoute)
      setView(nextView)
      window.requestAnimationFrame(() => {
        const returnKey = pendingHelpTriggerFocus.current
        const returnTarget = returnKey
          ? document.querySelector<HTMLElement>(
              `[data-help-trigger="${returnKey}"]`,
            )
          : null
        if (returnTarget) {
          returnTarget.focus({ preventScroll: true })
          pendingHelpTriggerFocus.current = null
          pendingLocationFocus.current = null
          return
        }
        const targetId = pendingLocationFocus.current
        if (targetId && focusElementById(targetId)) {
          pendingLocationFocus.current = null
        }
      })
    }
    const onHashChange = () => {
      if (viewFromHash() === currentView.current) return
      syncFromLocation()
    }
    window.addEventListener('hashchange', onHashChange)
    window.addEventListener('popstate', syncFromLocation)
    return () => {
      window.removeEventListener('hashchange', onHashChange)
      window.removeEventListener('popstate', syncFromLocation)
    }
  }, [])

  useEffect(() => {
    const returnKey = pendingHelpTriggerFocus.current
    const returnTarget = returnKey
      ? document.querySelector<HTMLElement>(
          `[data-help-trigger="${returnKey}"]`,
        )
      : null
    if (returnTarget) {
      returnTarget.focus({ preventScroll: true })
      pendingHelpTriggerFocus.current = null
      pendingLocationFocus.current = null
      return
    }

    const targetId = pendingLocationFocus.current
    if (!targetId) return
    if (
      view === 'receipt' &&
      route.kind === 'pack' &&
      loaded?.id !== route.id &&
      loadFailure?.id !== route.id
    ) {
      return
    }
    const frame = window.requestAnimationFrame(() => {
      if (focusElementById(targetId)) pendingLocationFocus.current = null
    })
    return () => window.cancelAnimationFrame(frame)
  }, [loadFailure, loaded, route, view])

  function selectPack(id: PackId) {
    if (route.kind === 'pack' && route.id === id && view === 'receipt') return
    const metadata = getPackCatalogEntry(id)
    writePackToUrl(id)
    if (!metadata.canDisplay) {
      pendingFocusPack.current = null
      pendingLocationFocus.current = 'place-chooser'
      currentView.current = 'receipt'
      setRoute({ kind: 'blocked', id })
      setView('receipt')
      return
    }
    pendingFocusPack.current = id
    currentView.current = 'receipt'
    setRoute({ kind: 'pack', id })
    setView('receipt')
    window.scrollTo(0, 0)
  }

  function showChooser() {
    pendingFocusPack.current = null
    pendingLocationFocus.current = 'place-chooser'
    currentView.current = 'receipt'
    if (route.kind !== 'chooser' || view !== 'receipt') {
      writeChooserToUrl()
    }
    setRoute({ kind: 'chooser' })
    setView('receipt')
    setLoaded(null)
    window.scrollTo(0, 0)
  }

  function openHelp() {
    const active = document.activeElement
    const returnFocusKey =
      active instanceof HTMLElement ? active.dataset.helpTrigger ?? null : null
    if (returnFocusKey) helpReturnFocusKey.current = returnFocusKey
    pendingLocationFocus.current = 'help-heading'
    const url = new URL(window.location.href)
    url.hash = HELP_HASH_ROOT
    const nextUrl = `${url.pathname}${url.search}${url.hash}`
    if (view === 'help') {
      history.replaceState(history.state, '', nextUrl)
    } else {
      const currentState =
        history.state && typeof history.state === 'object' ? history.state : {}
      history.pushState(
        { ...currentState, [HELP_HISTORY_KEY]: true },
        '',
        nextUrl,
      )
    }
    currentView.current = 'help'
    setView('help')
    window.scrollTo(0, 0)
    window.requestAnimationFrame(() => {
      if (focusElementById('help-heading')) {
        pendingLocationFocus.current = null
      }
    })
  }

  function openReceipt() {
    const returnKey = helpReturnFocusKey.current
    helpReturnFocusKey.current = null
    pendingHelpTriggerFocus.current = returnKey
    if (isHelpHistoryEntry()) {
      history.back()
      return
    }

    pendingLocationFocus.current =
      route.kind === 'pack' ? 'receipt-hero' : 'place-chooser'
    currentView.current = 'receipt'
    setView('receipt')
    if (viewFromHash() === 'help') {
      history.replaceState(
        null,
        '',
        `${window.location.pathname}${window.location.search}`,
      )
    }
    window.scrollTo(0, 0)
    window.requestAnimationFrame(() => {
      const returnTarget = returnKey
        ? document.querySelector<HTMLElement>(
            `[data-help-trigger="${returnKey}"]`,
          )
        : null
      if (returnTarget) {
        returnTarget.focus({ preventScroll: true })
        pendingHelpTriggerFocus.current = null
        pendingLocationFocus.current = null
        return
      }
      const targetId = pendingLocationFocus.current
      if (targetId && focusElementById(targetId)) {
        pendingLocationFocus.current = null
      }
    })
  }

  function navigateWithinHelp(targetId: string) {
    const url = new URL(window.location.href)
    url.hash = targetId
    history.replaceState(history.state, '', `${url.pathname}${url.search}${url.hash}`)
    const target = document.getElementById(targetId)
    target?.scrollIntoView({ block: 'start' })
    if (target instanceof HTMLElement) target.focus({ preventScroll: true })
  }

  const routeMetadata =
    route.kind === 'pack' || route.kind === 'blocked'
      ? getPackCatalogEntry(route.id)
      : null

  if (view === 'help') {
    return (
      <div className="page">
        <a
          className="skip-link"
          href="#help/main"
          onClick={(event) => {
            event.preventDefault()
            navigateWithinHelp('help/main')
          }}
        >
          Skip to how What in the Tax? works
        </a>
        <SiteHeader
          currentPlace={routeMetadata?.label}
          onChoosePlace={showChooser}
          onOpenHelp={openHelp}
        />
        <HelpGuide
          onBack={openReceipt}
          onNavigate={navigateWithinHelp}
          backLabel={route.kind === 'pack' ? 'Back to receipt' : 'Back to places'}
        />
        <ProductFooter />
      </div>
    )
  }

  const packId = route.kind === 'pack' ? route.id : null
  const pack = packId && loaded?.id === packId ? loaded.pack : null
  const activeFailure =
    packId && loadFailure?.id === packId ? loadFailure : null

  if (!pack) {
    const isUnknown = route.kind === 'unknown'
    const isBlocked = route.kind === 'blocked'
    const isLoading = Boolean(packId && !activeFailure)
    const alertText = activeFailure
      ? `${routeMetadata?.label ?? 'This'} could not be loaded. We did not substitute another community.`
      : isBlocked
        ? `${routeMetadata?.label ?? 'This community'} is temporarily unavailable because required evidence needs an update. We will not show another community’s numbers instead.`
        : isUnknown
          ? `We have not added “${route.requested || '(blank)'}” yet. We will not substitute another community’s data.`
          : null

    return (
      <div className="page">
        <a className="skip-link" href="#place-chooser">
          Skip to place finder
        </a>
        <SiteHeader onChoosePlace={showChooser} onOpenHelp={openHelp} />
        <main
          id="place-chooser"
          className="chooser-page"
          tabIndex={-1}
          aria-busy={isLoading}
        >
          <section className="chooser-hero" aria-live="polite">
            <div className="chooser-hero__copy">
              <h1>
                {isLoading
                  ? `Loading ${routeMetadata?.label ?? 'receipt'}…`
                  : (
                      <>
                        Where did your <span className="no-break">property-tax</span>{' '}
                        dollars go?
                      </>
                    )}
              </h1>
              <span className="chooser-hero__rule" aria-hidden="true" />
              <p>
                {isLoading
                  ? 'Loading only the selected receipt and its public evidence.'
                  : 'Choose your community to explore a sample bill and the public records behind it. If the evidence is not ready, we will say so.'}
              </p>
            </div>
            {!isLoading ? <ReceiptSketch /> : null}
          </section>

          {alertText ? (
            <div className="chooser-alert" role="alert">
              <strong>
                {activeFailure
                  ? 'We could not load this community'
                  : isBlocked
                    ? 'We are still checking the evidence'
                    : 'That community is not available yet'}
              </strong>
              <p>{alertText}</p>
              {activeFailure ? (
                <button
                  type="button"
                  className="button button-secondary"
                  onClick={() => setRetrySequence((value) => value + 1)}
                >
                  Try again
                </button>
              ) : null}
            </div>
          ) : null}

          {!isLoading ? (
            <>
              <PlaceFinder
                records={PACK_CATALOG}
                onSelectPlace={selectPack}
                activePlaceId={packId ?? undefined}
              />
              <SupportCard />
            </>
          ) : null}
        </main>
        <ProductFooter />
      </div>
    )
  }

  const counts = pack.audit.counts ?? {}
  const hardFails =
    (counts['not-found'] ?? 0) +
    (counts['wrong-page'] ?? 0) +
    (counts['bad-page-number'] ?? 0)
  const weakCitations =
    (counts['numbers-only'] ?? 0) +
    (counts['unverifiable'] ?? 0) +
    (counts['no-excerpt'] ?? 0)
  const citationSummary =
    hardFails > 0
      ? `${hardFails} source ${hardFails === 1 ? 'check has' : 'checks have'} failed`
      : weakCitations > 0
        ? `${weakCitations} source ${
            weakCitations === 1 ? 'check is' : 'checks are'
          } incomplete`
        : 'source checks complete'
  const selectedMetadata = getPackCatalogEntry(packId!)

  return (
    <TaxReceiptScreen
      data={pack.receipt}
      gaps={pack.evidence.gaps}
      evidenceRules={pack.evidence.evidencePolicy.rules}
      sources={pack.evidence.sources}
      facts={pack.evidence.facts}
      derived={pack.evidence.derived}
      citationAudit={pack.audit}
      bannerText={`Draft — ${citationSummary}.`}
      appHeader={
        <SiteHeader
          currentPlace={`${selectedMetadata.label}, ${selectedMetadata.province}`}
          onChoosePlace={showChooser}
          onOpenHelp={openHelp}
        />
      }
      onOpenHelp={openHelp}
    />
  )
}
