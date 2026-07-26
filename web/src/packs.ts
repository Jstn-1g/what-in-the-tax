import ndAudit from './data/citation-audit.json'
import ndLedger from './data/evidence-ledger.json'
import ndReceipt from './data/taxpayer-receipt.json'
import brantAudit from './data/brant/citation-audit.json'
import brantLedger from './data/brant/evidence-ledger.json'
import brantReceipt from './data/brant/taxpayer-receipt.json'
import kitAudit from './data/kitchener/citation-audit.json'
import kitLedger from './data/kitchener/evidence-ledger.json'
import kitReceipt from './data/kitchener/taxpayer-receipt.json'
import watAudit from './data/waterloo/citation-audit.json'
import watLedger from './data/waterloo/evidence-ledger.json'
import watReceipt from './data/waterloo/taxpayer-receipt.json'
import camAudit from './data/cambridge/citation-audit.json'
import camLedger from './data/cambridge/evidence-ledger.json'
import camReceipt from './data/cambridge/taxpayer-receipt.json'
import wooAudit from './data/woolwich/citation-audit.json'
import wooLedger from './data/woolwich/evidence-ledger.json'
import wooReceipt from './data/woolwich/taxpayer-receipt.json'
import type { EvidenceLedger, TaxpayerReceipt } from './types'

export type PackId =
  | 'north-dumfries-on'
  | 'brant-county-on'
  | 'kitchener-on'
  | 'waterloo-on'
  | 'cambridge-on'
  | 'woolwich-on'

export type PackEntry = {
  label: string
  banner: string
  receipt: TaxpayerReceipt
  ledger: EvidenceLedger
  audit: {
    counts?: Record<string, number>
    results?: { id?: string; tier?: string }[]
  }
}

/** Registry — add a pack here after build_lower_tier_pack.py emits data/<slug>/. */
export const PACKS: Record<PackId, PackEntry> = {
  'kitchener-on': {
    label: 'Kitchener',
    banner: 'Draft · pack/kitchener-on · City of Kitchener + Region of Waterloo',
    receipt: kitReceipt as unknown as TaxpayerReceipt,
    ledger: kitLedger as unknown as EvidenceLedger,
    audit: kitAudit as PackEntry['audit'],
  },
  'waterloo-on': {
    label: 'Waterloo',
    banner: 'Draft · pack/waterloo-on · City of Waterloo + Region of Waterloo',
    receipt: watReceipt as unknown as TaxpayerReceipt,
    ledger: watLedger as unknown as EvidenceLedger,
    audit: watAudit as PackEntry['audit'],
  },
  'cambridge-on': {
    label: 'Cambridge',
    banner: 'Draft · pack/cambridge-on · City of Cambridge + Region of Waterloo',
    receipt: camReceipt as unknown as TaxpayerReceipt,
    ledger: camLedger as unknown as EvidenceLedger,
    audit: camAudit as PackEntry['audit'],
  },
  'woolwich-on': {
    label: 'Woolwich',
    banner: 'Draft · pack/woolwich-on · Township of Woolwich + Region (area-rated)',
    receipt: wooReceipt as unknown as TaxpayerReceipt,
    ledger: wooLedger as unknown as EvidenceLedger,
    audit: wooAudit as PackEntry['audit'],
  },
  'north-dumfries-on': {
    label: 'North Dumfries',
    banner: 'Sealed · pack/north-dumfries-on/2026.3 · unaffiliated with Township or Region',
    receipt: ndReceipt as unknown as TaxpayerReceipt,
    ledger: ndLedger as unknown as EvidenceLedger,
    audit: ndAudit as PackEntry['audit'],
  },
  'brant-county-on': {
    label: 'Paris / Brant County',
    banner: 'Draft · pack/brant-county-on · Paris via County of Brant (single-tier)',
    receipt: brantReceipt as unknown as TaxpayerReceipt,
    ledger: brantLedger as unknown as EvidenceLedger,
    audit: brantAudit as PackEntry['audit'],
  },
}

export const DEFAULT_PACK_ID: PackId = 'kitchener-on'

export const PACK_IDS = Object.keys(PACKS) as PackId[]
