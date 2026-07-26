import { useEffect, useRef, useState } from 'react'
import HelpGuide from './components/HelpGuide'
import TaxReceiptScreen from './components/TaxReceiptScreen'
import {
  readSimpleLanguagePreference,
  writeSimpleLanguagePreference,
} from './lib/eli5'
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

function viewFromHash(): ViewId {
  return window.location.hash.replace(/^#/, '').split('/')[0] === 'help'
    ? 'help'
    : 'receipt'
}

function currentPackRoute(): PackRoute {
  if (typeof window === 'undefined') return { kind: 'chooser' }
  return packRouteFromSearch(window.location.search)
}

function writePackToUrl(id: PackId, keepHash = true) {
  const url = new URL(window.location.href)
  url.searchParams.set('pack', id)
  if (!keepHash) url.hash = ''
  history.replaceState(null, '', `${url.pathname}${url.search}${url.hash}`)
}

function setDocumentMeta(route: PackRoute) {
  const metadata =
    route.kind === 'pack' || route.kind === 'blocked'
      ? getPackCatalogEntry(route.id)
      : null
  const title =
    route.kind === 'blocked'
      ? `${metadata?.label ?? 'Receipt'} unavailable`
      : metadata?.label ??
        (route.kind === 'unknown'
          ? 'Receipt unavailable'
          : 'Choose a municipality')
  document.title = `${title} · Taxpayer Receipt`
  const description = metadata
    ? `Independent taxpayer receipt for ${metadata.label} — how residential property tax is allocated. Not tax advice.`
    : 'Choose an available municipality to view an independent taxpayer receipt. Not tax advice.'
  let meta = document.querySelector('meta[name="description"]')
  if (!meta) {
    meta = document.createElement('meta')
    meta.setAttribute('name', 'description')
    document.head.appendChild(meta)
  }
  meta.setAttribute('content', description)
}

export default function App() {
  const pendingFocusPack = useRef<PackId | null>(null)
  const helpReturnFocusKey = useRef<string | null>(null)
  const [route, setRoute] = useState<PackRoute>(currentPackRoute)
  const [loaded, setLoaded] = useState<LoadedPack | null>(null)
  const [loadFailure, setLoadFailure] = useState<LoadFailure | null>(null)
  const [retrySequence, setRetrySequence] = useState(0)
  const [view, setView] = useState<ViewId>(() =>
    typeof window !== 'undefined' ? viewFromHash() : 'receipt',
  )
  const [simpleLanguage, setSimpleLanguage] = useState(() =>
    typeof window !== 'undefined' ? readSimpleLanguagePreference() : false,
  )

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
      document.title = 'Help & glossary · Taxpayer Receipt'
      window.requestAnimationFrame(() => {
        document.getElementById('help-heading')?.focus({ preventScroll: true })
      })
      return
    }
    setDocumentMeta(route)
  }, [route, view])

  useEffect(() => {
    if (route.kind !== 'pack' || loadFailure?.id !== route.id) return
    window.requestAnimationFrame(() => {
      document.getElementById('place-chooser')?.focus({ preventScroll: true })
    })
  }, [loadFailure, route])

  useEffect(() => {
    if (!loaded || pendingFocusPack.current !== loaded.id) return
    pendingFocusPack.current = null
    const target =
      document.getElementById('receipt-hero') ?? document.querySelector('main')
    if (target instanceof HTMLElement) {
      target.focus({ preventScroll: true })
    }
  }, [loaded])

  useEffect(() => {
    const onHash = () => setView(viewFromHash())
    const onPop = () => {
      pendingFocusPack.current = null
      setRoute(currentPackRoute())
      setView(viewFromHash())
    }
    window.addEventListener('hashchange', onHash)
    window.addEventListener('popstate', onPop)
    return () => {
      window.removeEventListener('hashchange', onHash)
      window.removeEventListener('popstate', onPop)
    }
  }, [])

  function setSimpleLanguageAndPersist(on: boolean) {
    setSimpleLanguage(on)
    writeSimpleLanguagePreference(on)
  }

  function selectPack(id: PackId) {
    if (route.kind === 'pack' && route.id === id) return
    const metadata = getPackCatalogEntry(id)
    writePackToUrl(id, false)
    if (metadata.availability !== 'available') {
      pendingFocusPack.current = null
      setRoute({ kind: 'blocked', id })
      return
    }
    pendingFocusPack.current = id
    setRoute({ kind: 'pack', id })
    setView('receipt')
    window.scrollTo(0, 0)
  }

  function openHelp() {
    const active = document.activeElement
    helpReturnFocusKey.current =
      active instanceof HTMLElement ? active.dataset.helpTrigger ?? null : null
    setView('help')
    if (window.location.hash !== '#help') {
      window.location.hash = 'help'
    }
    window.scrollTo(0, 0)
  }

  function openReceipt() {
    const returnKey = helpReturnFocusKey.current
    helpReturnFocusKey.current = null
    setView('receipt')
    if (window.location.hash === '#help' || window.location.hash.startsWith('#help')) {
      history.replaceState(
        null,
        '',
        `${window.location.pathname}${window.location.search}`,
      )
    }
    window.scrollTo(0, 0)
    window.requestAnimationFrame(() => {
      const target = returnKey
        ? document.querySelector<HTMLElement>(
            `[data-help-trigger="${returnKey}"]`,
          )
        : null
      const focusTarget =
        target ??
        document.getElementById('receipt-hero') ??
        document.getElementById('place-chooser')
      focusTarget?.focus({ preventScroll: true })
    })
  }

  const simpleLanguageToggle = (
    <label className={`simple-lang-toggle${simpleLanguage ? ' on' : ''}`}>
      <input
        type="checkbox"
        checked={simpleLanguage}
        onChange={(event) => setSimpleLanguageAndPersist(event.target.checked)}
      />
      <span className="simple-lang-copy">
        <span className="simple-lang-label">Plain language</span>
        <span className="simple-lang-hint">Use simpler receipt labels</span>
      </span>
    </label>
  )

  if (view === 'help') {
    return (
      <div className="page">
        <a className="skip-link" href="#help-main">
          Skip to help
        </a>
        <div className="deploy-banner" role="status">
          Help &amp; glossary · independent reading aid · not tax advice
        </div>
        <div
          className="pack-switcher pack-switcher-help"
          role="group"
          aria-label="Reading options"
        >
          {simpleLanguageToggle}
          <button
            type="button"
            className="pack-tab pack-tab-help"
            onClick={openReceipt}
          >
            ← Receipt
          </button>
        </div>
        <HelpGuide onBack={openReceipt} simpleLanguage={simpleLanguage} />
      </div>
    )
  }

  const packId = route.kind === 'pack' ? route.id : null
  const pack = packId && loaded?.id === packId ? loaded.pack : null
  const activeFailure =
    packId && loadFailure?.id === packId ? loadFailure : null

  if (!pack) {
    const metadata =
      route.kind === 'pack' || route.kind === 'blocked'
        ? getPackCatalogEntry(route.id)
        : null
    const isUnknown = route.kind === 'unknown'
    const isBlocked = route.kind === 'blocked'
    const isLoading = Boolean(packId && !activeFailure)
    return (
      <div className="page">
        <div
          className="deploy-banner"
          role={activeFailure ? 'alert' : 'status'}
        >
          {activeFailure
            ? `${metadata?.label ?? 'Municipality'} receipt could not be loaded · no municipality was substituted`
            : isUnknown || isBlocked
            ? 'Receipt unavailable · no municipality was substituted'
            : isLoading
              ? `Loading ${metadata?.label ?? 'municipality'} receipt`
              : 'Choose a municipality · independent reading aid · not tax advice'}
        </div>
        <a className="skip-link" href="#place-chooser">
          Skip to municipality chooser
        </a>
        <div className="pack-switcher" role="group" aria-label="Reading options">
          {simpleLanguageToggle}
          <button
            type="button"
            className="pack-tab pack-tab-help"
            data-help-trigger="chooser-toolbar"
            onClick={openHelp}
          >
            Help
          </button>
        </div>
        <main id="place-chooser" className="help-page" tabIndex={-1}>
          <section
            className="help-hero"
            aria-live="polite"
            aria-busy={isLoading}
          >
            <p className="help-kicker">Taxpayer Receipt</p>
            <h1>
              {isBlocked
                ? `${metadata?.label ?? 'This'} receipt is temporarily unavailable`
                : isUnknown
                  ? 'That municipality is not available'
                  : activeFailure
                    ? `${metadata?.label ?? 'This'} receipt could not be loaded`
                    : isLoading
                      ? `Loading ${metadata?.label ?? 'receipt'}…`
                      : 'Choose a municipality'}
            </h1>
            <p className="help-lede">
              {isBlocked ? (
                metadata?.availability === 'blocked' ? (
                  metadata.availabilityNote
                ) : (
                  'This receipt is unavailable.'
                )
              ) : isUnknown ? (
                <>
                  No receipt exists for <code>{route.requested || '(blank)'}</code>.
                  Choose an available place below.
                </>
              ) : activeFailure ? (
                <>
                  The requested receipt was not replaced with another municipality.
                  You can try loading it again or choose another place.
                </>
              ) : isLoading ? (
                'Loading only the selected receipt and its public evidence.'
              ) : (
                'Select a place to load its receipt and public evidence. No municipality is selected by default.'
              )}
            </p>
            {activeFailure ? (
              <button
                type="button"
                className="pack-tab active"
                onClick={() => setRetrySequence((value) => value + 1)}
              >
                Try again
              </button>
            ) : null}
            {!isLoading ? (
              <nav className="pack-switcher" aria-label="Municipalities">
                {PACK_CATALOG.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className={`pack-tab${
                      item.availability === 'blocked' ? ' blocked' : ''
                    }`}
                    aria-label={
                      item.availability === 'blocked'
                        ? `${item.label} unavailable: ${item.availabilityNote}`
                        : item.label
                    }
                    onClick={() => selectPack(item.id)}
                  >
                    {item.label}
                    {item.availability === 'blocked'
                      ? ' — evidence update required'
                      : ''}
                  </button>
                ))}
              </nav>
            ) : null}
          </section>
        </main>
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

  return (
    <TaxReceiptScreen
      data={pack.receipt}
      gaps={pack.evidence.gaps}
      evidenceRules={pack.evidence.evidencePolicy.rules}
      sources={pack.evidence.sources}
      facts={pack.evidence.facts}
      derived={pack.evidence.derived}
      citationAudit={pack.audit}
      bannerText={`${pack.metadata.banner} · citations: ${weakCitations} weak · ${hardFails} hard failures`}
      onOpenHelp={openHelp}
      simpleLanguage={simpleLanguage}
      packSwitcher={
        <div className="pack-switcher" role="group" aria-label="Municipality">
          {PACK_CATALOG.map((item) => (
            <button
              key={item.id}
              type="button"
              aria-current={packId === item.id ? 'page' : undefined}
              aria-label={
                item.availability === 'blocked'
                  ? `${item.label} unavailable: ${item.availabilityNote}`
                  : item.label
              }
              className={`${packId === item.id ? 'pack-tab active' : 'pack-tab'}${
                item.availability === 'blocked' ? ' blocked' : ''
              }`}
              onClick={() => selectPack(item.id)}
            >
              {item.label}
              {item.availability === 'blocked'
                ? ' — evidence update required'
                : ''}
            </button>
          ))}
          {simpleLanguageToggle}
          <button
            type="button"
            className="pack-tab pack-tab-help"
            data-help-trigger="receipt-toolbar"
            onClick={openHelp}
          >
            Help
          </button>
        </div>
      }
    />
  )
}
