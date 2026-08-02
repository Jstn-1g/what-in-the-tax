import { useEffect, useMemo, useRef, useState } from 'react'
import FirFilingScreen from './components/FirFilingScreen'
import HelpGuide from './components/HelpGuide'
import OntarioRolloutNote from './components/OntarioRolloutNote'
import PlaceFinder from './components/PlaceFinder'
import SiteHeader from './components/SiteHeader'
import { normalizeSupportUrl } from './components/SupportCard'

import ContributeCard from './components/ContributeCard'
import RepoLinks from './components/RepoLinks'
import TaxReceiptScreen from './components/TaxReceiptScreen'
import {
  getPackCatalogEntry,
  isPackId,
  loadPack,
  PACK_CATALOG,
  packRouteFromSearch,
  type PackEntry,
  type PackId,
  type PackRoute,
} from './packs'
import {
  loadOntarioMunicipalHistory,
  ontarioMunicipalHistoryUrl,
  toDirectoryFinderRecord,
  type OntarioMunicipalHistoryRegistry,
} from './lib/ontarioMunicipalHistory'
import {
  filingRouteFromSearch,
  FIR_FILING_YEARS,
  loadFirFiling,
  type FilingRoute,
  type FirFiling,
} from './lib/firFiling'
import { loadFirTaxation, type FirTaxationReceipt } from './lib/firTaxation'
import { formerNamesNote, formerNamesOf } from './lib/formerMunicipalities'
import type { PlaceSearchRecord } from './lib/placeSearch'

type ViewId = 'receipt' | 'help'
type LoadedPack = { id: PackId; pack: PackEntry }
type LoadFailure = { id: PackId }

// FIR filings are a lower evidence grade than gold by-law packs and live on
// their own query parameter. A filing never resolves to ?pack=, and
// PACK_CATALOG never learns about one.
//
// Ontario municipalities file on their own schedule: 129 have a 2025 return,
// 273 stop at 2024, 33 at 2023. There is no single current year, so a
// municipality opens at its own newest filing rather than a shared one.
const HELP_HASH_ROOT = 'help'
const HELP_HISTORY_KEY = 'whatInTheTaxHelpEntry'
const RECEIPT_ASSESSMENT_CODES: ReadonlySet<string> = new Set(
  PACK_CATALOG.map((pack) => pack.firAssessmentCode),
)
const RECEIPT_FINDER_RECORDS = PACK_CATALOG.map((pack) => ({
  ...pack,
  kind: 'receipt' as const,
}))

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
  url.searchParams.delete('filing')
  url.searchParams.delete('year')
  url.hash = ''
  history.pushState(null, '', `${url.pathname}${url.search}`)
}

function writeFilingToUrl(assessmentCode: string, year?: number) {
  const url = new URL(window.location.href)
  url.searchParams.set('filing', assessmentCode)
  if (year === undefined) {
    url.searchParams.delete('year')
  } else {
    url.searchParams.set('year', String(year))
  }
  url.searchParams.delete('pack')
  url.hash = ''
  history.pushState(null, '', `${url.pathname}${url.search}`)
}

function writeChooserToUrl() {
  const url = new URL(window.location.href)
  url.searchParams.delete('pack')
  url.searchParams.delete('filing')
  url.searchParams.delete('year')
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
  // The repository links default to the canonical public repository (see
  // repoLink.ts); a fork deploying its own copy overrides them with
  // VITE_REPO_URL. The donate link stays env-gated - the deployment declares
  // what is true of it - and reuses the card's normalizer so a test-mode or
  // non-Stripe URL can never reach the footer either.
  const supportUrl = normalizeSupportUrl(import.meta.env.VITE_SUPPORT_ONCE_URL)
  return (
    <footer className="product-footer">
      <p>
        Independent public-information project. Not affiliated with any government.
        Not an official bill, formal audit, or tax advice. Open source: every
        published number, and the checks behind it, can be inspected and re-run
        from the repository. The code is MIT-licensed; the data carries the
        licences below.
      </p>
      {/* Both source licences require these statements to travel with the
          data: the FIR figures are Open Government Licence - Ontario, and the
          geography and census tables are Statistics Canada Open Licence. */}
      <p>
        Contains information licensed under the Open Government Licence
        &ndash; Ontario. Includes data adapted from Statistics Canada. This
        does not constitute an endorsement by Statistics Canada of this
        product.
      </p>
      <nav className="product-footer__links" aria-label="Project links">
        <a href="#help/about">About this site</a>
        <a href={`${import.meta.env.BASE_URL}privacy.txt`}>Privacy</a>
        <RepoLinks />
        {supportUrl ? (
          <a href={supportUrl} target="_blank" rel="noreferrer">
            Support this project
            <span className="visually-hidden"> (opens in a new tab)</span>
          </a>
        ) : null}
      </nav>
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
  const [municipalHistory, setMunicipalHistory] =
    useState<OntarioMunicipalHistoryRegistry | null>(null)
  const [municipalHistoryUnavailable, setMunicipalHistoryUnavailable] =
    useState(false)
  const [view, setView] = useState<ViewId>(() =>
    typeof window !== 'undefined' ? viewFromHash() : 'receipt',
  )
  const [filingRoute, setFilingRoute] = useState<FilingRoute | null>(() =>
    typeof window !== 'undefined'
      ? filingRouteFromSearch(window.location.search)
      : null,
  )
  const [filing, setFiling] = useState<FirFiling | null>(null)
  const [filingUnavailable, setFilingUnavailable] = useState(false)
  const [taxation, setTaxation] = useState<FirTaxationReceipt | null>(null)
  // Set only when the artifact resolved as genuinely absent - an upper tier
  // that does not levy on assessment, or a municipality with no FIR record. A
  // transport failure leaves this false, so a network problem can never be
  // rendered as a claim about how a municipality is governed.
  const [taxationAbsent, setTaxationAbsent] = useState(false)
  const currentView = useRef(view)

  // Years available per municipality, derived from the registry the app
  // already holds rather than a second fetch. Verified against the emitted
  // artifacts: an exact match for 435 of 436 records.
  const filingYearsByCode = useMemo(() => {
    const map = new Map<string, number[]>()
    if (!municipalHistory) return map
    for (const record of municipalHistory.records) {
      if (!record.assessmentCode) continue
      const years = record.firYears
        .map((entry) => entry.fiscalYear)
        .filter((year) =>
          (FIR_FILING_YEARS as readonly number[]).includes(year),
        )
        .sort((a, b) => b - a)
      if (years.length > 0) map.set(record.assessmentCode, years)
    }
    return map
  }, [municipalHistory])

  const filingCode = filingRoute?.code ?? null
  const availableFilingYears = filingCode
    ? (filingYearsByCode.get(filingCode) ?? [])
    : []
  // An explicit ?year= wins when that year exists for this municipality;
  // otherwise open the newest one it actually filed.
  const resolvedFilingYear =
    filingRoute?.year && availableFilingYears.includes(filingRoute.year)
      ? filingRoute.year
      : (availableFilingYears[0] ?? null)

  useEffect(() => {
    if (!filingCode) {
      setFiling(null)
      setFilingUnavailable(false)
      return
    }
    if (resolvedFilingYear === null) {
      // Either the registry has not loaded yet, or this municipality filed
      // nothing in the published window. Only the second is a dead end.
      if (municipalHistory) setFilingUnavailable(true)
      return
    }
    let active = true
    setFiling((current) =>
      current?.assessmentCode === filingCode &&
      current?.fiscalYear === resolvedFilingYear
        ? current
        : null,
    )
    setFilingUnavailable(false)
    loadFirFiling(filingCode, resolvedFilingYear).then(
      (next) => {
        if (active) setFiling(next)
      },
      (_error: unknown) => {
        if (active) setFilingUnavailable(true)
      },
    )
    // Who levied it, alongside what it was spent on. Loaded separately because
    // 405 municipalities have a taxation receipt and 435 have a functional one,
    // so one being absent must not withhold the other.
    setTaxation(null)
    setTaxationAbsent(false)
    loadFirTaxation(filingCode, resolvedFilingYear).then(
      (next) => {
        if (!active) return
        setTaxation(next)
        setTaxationAbsent(next === null)
      },
      (_error: unknown) => {
        if (active) setTaxationAbsent(false)
      },
    )
    return () => {
      active = false
    }
  }, [filingCode, resolvedFilingYear, municipalHistory])

  useEffect(() => {
    let active = true
    loadOntarioMunicipalHistory().then(
      (registry) => {
        if (!active) return
        setMunicipalHistory(registry)
        setMunicipalHistoryUnavailable(false)
      },
      (_error: unknown) => {
        if (!active) return
        setMunicipalHistory(null)
        setMunicipalHistoryUnavailable(true)
      },
    )
    return () => {
      active = false
    }
  }, [])

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
      setFilingRoute(filingRouteFromSearch(window.location.search))
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

  function selectFiling(assessmentCode: string, year?: number) {
    if (
      filingCode === assessmentCode &&
      view === 'receipt' &&
      (year === undefined || year === resolvedFilingYear)
    ) {
      return
    }
    writeFilingToUrl(assessmentCode, year)
    pendingFocusPack.current = null
    pendingLocationFocus.current = 'fir-filing-heading'
    currentView.current = 'receipt'
    setRoute({ kind: 'chooser' })
    setLoaded(null)
    setFilingRoute({ code: assessmentCode, year: year ?? null })
    setView('receipt')
    window.scrollTo(0, 0)
  }

  function showChooser() {
    pendingFocusPack.current = null
    pendingLocationFocus.current = 'place-chooser'
    currentView.current = 'receipt'
    if (route.kind !== 'chooser' || view !== 'receipt' || filingCode) {
      writeChooserToUrl()
    }
    setRoute({ kind: 'chooser' })
    setView('receipt')
    setLoaded(null)
    setFilingRoute(null)
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

  const directoryCodeById = useMemo(() => {
    const map = new Map<string, string>()
    if (!municipalHistory) return map
    for (const record of municipalHistory.records) {
      if (record.assessmentCode) {
        map.set(`directory-${record.directoryId}`, record.assessmentCode)
      }
    }
    return map
  }, [municipalHistory])

  const finderRecords: readonly PlaceSearchRecord[] = useMemo(() => {
    if (!municipalHistory) return RECEIPT_FINDER_RECORDS
    const directoryByCode = new Map(
      municipalHistory.records.flatMap((record) =>
        record.assessmentCode ? [[record.assessmentCode, record] as const] : [],
      ),
    )
    const receiptRecords = RECEIPT_FINDER_RECORDS.map((record) => {
      const history = directoryByCode.get(record.firAssessmentCode)
      return {
        ...record,
        latestFirYear: history?.latestFirYear ?? null,
        firYears: history?.firYears.map((item) => item.fiscalYear) ?? [],
      }
    })
    const directoryRecords = municipalHistory.records
      .filter(
        (record) =>
          record.assessmentCode === null ||
          !RECEIPT_ASSESSMENT_CODES.has(record.assessmentCode),
      )
      .map((record) => {
        const finder = toDirectoryFinderRecord(record)
        // Fold dissolved municipalities into their successor's search record,
        // so "Scarborough" finds Toronto instead of an empty state that reads
        // as a missing city. Navigation aid only: nothing here reaches a
        // ledger or a published figure, and the row says why it matched.
        const formerNames = formerNamesOf(finder.label)
        if (formerNames.length > 0) {
          finder.aliases = [...(finder.aliases ?? []), ...formerNames]
          finder.formerNote = formerNamesNote(finder.label) ?? undefined
        }
        // Offer a filing only where one is actually published. Filing in any
        // covered year is an exact proxy but for Manitouwadge, which filed
        // without a Schedule 40 total; that one falls through to the honest
        // could-not-be-loaded state rather than a broken promise.
        const hasFiling =
          record.assessmentCode !== null &&
          record.firYears.some((year) =>
            (FIR_FILING_YEARS as readonly number[]).includes(year.fiscalYear),
          )
        return hasFiling && record.assessmentCode
          ? {
              ...finder,
              filingHref: `?filing=${record.assessmentCode}`,
            }
          : finder
      })
    return [...receiptRecords, ...directoryRecords]
  }, [municipalHistory])

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

  if (filingCode) {
    return (
      <div className="page">
        <SiteHeader
          currentPlace={filing?.name}
          onChoosePlace={showChooser}
          onOpenHelp={openHelp}
        />
        {filing ? (
          <FirFilingScreen
            filing={filing}
            taxation={taxation}
            taxationAbsent={taxationAbsent}
            availableYears={availableFilingYears}
            onSelectYear={(year) => selectFiling(filing.assessmentCode, year)}
            onBack={showChooser}
          />
        ) : filingUnavailable ? (
          <main className="fir-filing" aria-labelledby="fir-filing-heading">
            <h1 id="fir-filing-heading">That filing could not be loaded</h1>
            <p>
              No Financial Information Return filing is published here for
              assessment code {filingCode}. Missing evidence stays visible
              instead of being estimated.
            </p>
            <button type="button" className="fir-filing__back" onClick={showChooser}>
              All places
            </button>
          </main>
        ) : (
          <main className="fir-filing" aria-labelledby="fir-filing-heading">
            <h1 id="fir-filing-heading">Loading filing...</h1>
          </main>
        )}
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
          <section className="chooser-hero">
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
              <p aria-live="polite">
                {isLoading
                  ? 'Loading only the selected receipt and its public evidence.'
                  : 'Search your community to start with current 2026 tax evidence where a receipt is ready, then see which 2025, 2024, and 2023 FIR years are available for context.'}
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
                records={finderRecords}
                onSelectPlace={(id) => {
                  if (isPackId(id)) {
                    selectPack(id)
                    return
                  }
                  // Directory records were previously inert. One with an
                  // assessment code now opens its FIR filing, a lower
                  // evidence grade on a route separate from ?pack=.
                  const assessmentCode = directoryCodeById.get(id)
                  if (assessmentCode) selectFiling(assessmentCode)
                }}
                activePlaceId={packId ?? undefined}
                registryState={
                  municipalHistory
                    ? 'ready'
                    : municipalHistoryUnavailable
                      ? 'unavailable'
                      : 'loading'
                }
                registryCoverage={
                  municipalHistory
                    ? {
                        currentMunicipalities:
                          municipalHistory.coverage.currentMunicipalities,
                        withFirHistory:
                          municipalHistory.coverage.withFirHistory,
                        withoutFirHistory:
                          municipalHistory.coverage.withoutFirHistory,
                        latest2025:
                          municipalHistory.coverage.latestFirYearCounts['2025'],
                      }
                    : undefined
                }
              />
              <ContributeCard />
              {municipalHistory ? (
                <OntarioRolloutNote
                  registry={municipalHistory}
                  receiptPreviewCount={PACK_CATALOG.length}
                  verificationHref={ontarioMunicipalHistoryUrl(
                    import.meta.env.BASE_URL,
                  )}
                />
              ) : null}
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
  const selectedHistoryRecord = municipalHistory?.records.find(
    (record) =>
      record.assessmentCode === selectedMetadata.firAssessmentCode,
  )
  const selectedHistoryYears = selectedHistoryRecord?.firYears.map(
    (item) => item.fiscalYear,
  )
  const selectedHistoryState = municipalHistory
    ? selectedHistoryRecord
      ? 'ready'
      : 'unavailable'
    : municipalHistoryUnavailable
      ? 'unavailable'
      : 'loading'

  return (
    <TaxReceiptScreen
      data={pack.receipt}
      firYears={selectedHistoryYears}
      firHistoryState={selectedHistoryState}
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
