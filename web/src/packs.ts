import type { CitationAudit } from './lib/evidenceLookup'
import {
  getPackCatalogEntry,
  type PackCatalogEntry,
  type PackId,
} from './packCatalog'
import { validatePublicPack } from './publicPackSchema'
import type { Derived, Fact, Gap, Source, TaxpayerReceipt } from './types'

export {
  getPackCatalogEntry,
  isPackId,
  PACK_CATALOG,
  PACK_IDS,
  packRouteFromSearch,
  type PackCatalogEntry,
  type PackId,
  type PackRoute,
} from './packCatalog'

export type PublicEvidence = {
  gaps: Gap[]
  evidencePolicy: { rules: string[] }
  sources: Source[]
  facts: Fact[]
  derived: Derived[]
}

export type PackEntry = {
  id: PackId
  metadata: PackCatalogEntry
  receipt: TaxpayerReceipt
  evidence: PublicEvidence
  audit: CitationAudit
}

export type PackFetchResponse = {
  ok: boolean
  status: number
  json(): Promise<unknown>
}

export type PackFetcher = (url: string) => Promise<PackFetchResponse>

const packCache = new Map<PackId, Promise<PackEntry>>()

function normalizeBaseUrl(baseUrl: string): string {
  return `${baseUrl.replace(/\/+$/, '')}/`
}

function publicPackUrl(id: PackId, baseUrl: string): string {
  return `${normalizeBaseUrl(baseUrl)}packs/${encodeURIComponent(id)}.json`
}

function parsePublicPack(id: PackId, value: unknown): PackEntry {
  const validated = validatePublicPack(id, value)
  const metadata = getPackCatalogEntry(id)
  if (validated.receipt.fiscalYear !== metadata.currentEvidenceYear) {
    throw new Error(
      `${id}: receipt fiscalYear must equal catalog currentEvidenceYear ${metadata.currentEvidenceYear}.`,
    )
  }

  return {
    id,
    metadata,
    receipt: validated.receipt,
    evidence: validated.evidence,
    audit: validated.audit,
  }
}

export async function loadPackWithFetcher(
  id: PackId,
  fetcher: PackFetcher,
  baseUrl: string,
): Promise<PackEntry> {
  const metadata = getPackCatalogEntry(id)
  if (metadata.availability !== 'available') {
    throw new Error(`${metadata.label} is unavailable: ${metadata.availabilityNote}`)
  }

  const response = await fetcher(publicPackUrl(id, baseUrl))
  if (!response.ok) {
    throw new Error(`Public pack request failed for ${id} (${response.status}).`)
  }
  return parsePublicPack(id, await response.json())
}

/** Fetch only the selected municipality's sanitized, committed public artifact. */
export function loadPack(id: PackId): Promise<PackEntry> {
  const cached = packCache.get(id)
  if (cached) return cached

  const pending = loadPackWithFetcher(
    id,
    (url) => fetch(url),
    import.meta.env.BASE_URL,
  ).catch((error: unknown) => {
    packCache.delete(id)
    throw error
  })
  packCache.set(id, pending)
  return pending
}
