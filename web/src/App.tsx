import { useEffect, useMemo, useState } from 'react'
import HelpGuide from './components/HelpGuide'
import TaxReceiptScreen from './components/TaxReceiptScreen'
import {
  readSimpleLanguagePreference,
  writeSimpleLanguagePreference,
} from './lib/eli5'
import { DEFAULT_PACK_ID, PACK_IDS, PACKS, type PackId } from './packs'

type ViewId = 'receipt' | 'help'

function viewFromHash(): ViewId {
  return window.location.hash.replace(/^#/, '').split('/')[0] === 'help' ? 'help' : 'receipt'
}

function isPackId(value: string | null): value is PackId {
  return Boolean(value && (PACK_IDS as string[]).includes(value))
}

function packFromSearch(): PackId {
  if (typeof window === 'undefined') return DEFAULT_PACK_ID
  const raw = new URLSearchParams(window.location.search).get('pack')
  return isPackId(raw) ? raw : DEFAULT_PACK_ID
}

function writePackToUrl(id: PackId, keepHash = true) {
  const url = new URL(window.location.href)
  url.searchParams.set('pack', id)
  const hash = keepHash ? url.hash : ''
  history.replaceState(null, '', `${url.pathname}?${url.searchParams.toString()}${hash}`)
}

function setDocumentMeta(packId: PackId) {
  const pack = PACKS[packId]
  document.title = `${pack.label} · Taxpayer Receipt`
  const description = `Independent taxpayer receipt for ${pack.label} — how residential property tax is allocated. Not tax advice.`
  let meta = document.querySelector('meta[name="description"]')
  if (!meta) {
    meta = document.createElement('meta')
    meta.setAttribute('name', 'description')
    document.head.appendChild(meta)
  }
  meta.setAttribute('content', description)
}

export default function App() {
  const [packId, setPackId] = useState<PackId>(() =>
    typeof window !== 'undefined' ? packFromSearch() : DEFAULT_PACK_ID,
  )
  const [view, setView] = useState<ViewId>(() =>
    typeof window !== 'undefined' ? viewFromHash() : 'receipt',
  )
  const [simpleLanguage, setSimpleLanguage] = useState(() =>
    typeof window !== 'undefined' ? readSimpleLanguagePreference() : false,
  )
  const pack = PACKS[packId]
  const hardFails = useMemo(() => {
    const counts = pack.audit.counts ?? {}
    return (counts['not-found'] ?? 0) + (counts['wrong-page'] ?? 0) + (counts['bad-page-number'] ?? 0)
  }, [pack.audit])

  useEffect(() => {
    writePackToUrl(packId, true)
    setDocumentMeta(packId)
  }, [packId])

  useEffect(() => {
    const onHash = () => setView(viewFromHash())
    const onPop = () => {
      setPackId(packFromSearch())
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
    if (id === packId) return
    setPackId(id)
    writePackToUrl(id, false)
    setDocumentMeta(id)
    window.scrollTo(0, 0)
    requestAnimationFrame(() => {
      const target =
        document.getElementById('receipt-hero') ?? document.querySelector('main')
      if (target instanceof HTMLElement) {
        target.focus({ preventScroll: true })
      }
    })
  }

  function openHelp() {
    setView('help')
    if (window.location.hash !== '#help') {
      window.location.hash = 'help'
    }
    window.scrollTo(0, 0)
  }

  function openReceipt() {
    setView('receipt')
    if (window.location.hash === '#help' || window.location.hash.startsWith('#help')) {
      history.replaceState(
        null,
        '',
        `${window.location.pathname}${window.location.search}`,
      )
    }
    window.scrollTo(0, 0)
  }

  const simpleLanguageToggle = (
    <label className={`simple-lang-toggle${simpleLanguage ? ' on' : ''}`}>
      <input
        type="checkbox"
        checked={simpleLanguage}
        onChange={(event) => setSimpleLanguageAndPersist(event.target.checked)}
      />
      <span className="simple-lang-copy">
        <span className="simple-lang-label">Simple language</span>
        <span className="simple-lang-hint">Explain like I&apos;m 5</span>
      </span>
    </label>
  )

  if (view === 'help') {
    return (
      <div className="page">
        <div className="deploy-banner" role="status">
          Help &amp; glossary · independent reading aid · not tax advice
        </div>
        <div className="pack-switcher pack-switcher-help" role="toolbar" aria-label="Reading options">
          {simpleLanguageToggle}
          <button type="button" className="pack-tab pack-tab-help" onClick={openReceipt}>
            ← Receipt
          </button>
        </div>
        <HelpGuide onBack={openReceipt} simpleLanguage={simpleLanguage} />
      </div>
    )
  }

  return (
    <TaxReceiptScreen
      data={pack.receipt}
      gaps={pack.ledger.gaps}
      evidenceRules={pack.ledger.evidencePolicy.rules}
      sources={pack.ledger.sources}
      facts={pack.ledger.facts}
      derived={pack.ledger.derived}
      citationAudit={pack.audit}
      bannerText={`${pack.banner} · citation hard-fail count: ${hardFails}`}
      onOpenHelp={openHelp}
      simpleLanguage={simpleLanguage}
      packSwitcher={
        <div className="pack-switcher" role="tablist" aria-label="Municipality">
          {PACK_IDS.map((id) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={packId === id}
              className={packId === id ? 'pack-tab active' : 'pack-tab'}
              onClick={() => selectPack(id)}
            >
              {PACKS[id].label}
            </button>
          ))}
          {simpleLanguageToggle}
          <button type="button" className="pack-tab pack-tab-help" onClick={openHelp}>
            Help
          </button>
        </div>
      }
    />
  )
}
