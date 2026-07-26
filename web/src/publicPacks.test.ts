import { describe, expect, it } from 'vitest'
import brantPack from '../public/packs/brant-county-on.json'
import cambridgePack from '../public/packs/cambridge-on.json'
import kitchenerPack from '../public/packs/kitchener-on.json'
import northDumfriesPack from '../public/packs/north-dumfries-on.json'
import waterlooPack from '../public/packs/waterloo-on.json'
import { PACK_CATALOG } from './packCatalog'

const PUBLIC_PACKS = [
  brantPack,
  cambridgePack,
  kitchenerPack,
  northDumfriesPack,
  waterlooPack,
]

const BANNED_KEYS = new Set([
  'closedGaps',
  'extractedText',
  'localPath',
  'searchTrail',
  'suppressed',
])

function findBannedKeys(value: unknown, path = '$'): string[] {
  if (Array.isArray(value)) {
    return value.flatMap((item, index) => findBannedKeys(item, `${path}[${index}]`))
  }
  if (typeof value !== 'object' || value === null) return []

  return Object.entries(value).flatMap(([key, child]) => {
    const childPath = `${path}.${key}`
    return [
      ...(BANNED_KEYS.has(key) ? [childPath] : []),
      ...findBannedKeys(child, childPath),
    ]
  })
}

describe('committed public pack artifacts', () => {
  it('contains exactly the catalog packs marked available', () => {
    const expectedIds = PACK_CATALOG.filter(
      (pack) => pack.availability === 'available',
    )
      .map((pack) => pack.id)
      .sort()
    expect(PUBLIC_PACKS.map((pack) => pack.id).sort()).toEqual(expectedIds)
  })

  it('does not expose internal provenance or analyst-only fields', () => {
    for (const pack of PUBLIC_PACKS) {
      expect(findBannedKeys(pack), pack.id).toEqual([])
      expect(pack.receipt.findings, pack.id).toEqual([])
      expect(pack.receipt.evidencePolicyRef, pack.id).toBe(
        'Evidence included with this preview',
      )
      expect(pack.receipt.uiModelHints.marqueeFindings, pack.id).toEqual([])
      expect(pack.receipt.uiModelHints.publishedFindingIds, pack.id).toEqual([])
      expect(pack.receipt.uiModelHints, pack.id).not.toHaveProperty(
        'materialityFloorCad',
      )
      expect(pack.receipt.uiModelHints, pack.id).not.toHaveProperty(
        'materialityNote',
      )
      expect(pack.receipt.uiModelHints, pack.id).not.toHaveProperty(
        'flaggedDefinition',
      )
      expect(Object.keys(pack.evidence).sort()).toEqual([
        'derived',
        'evidencePolicy',
        'facts',
        'gaps',
        'sources',
      ])
      expect(Object.keys(pack.audit).sort()).toEqual(['counts', 'results'])
      for (const source of pack.evidence.sources) {
        expect(source, pack.id).not.toHaveProperty('note')
      }
      for (const fact of pack.evidence.facts) {
        expect(fact, pack.id).not.toHaveProperty('note')
      }
      for (const derived of pack.evidence.derived) {
        expect(derived, pack.id).not.toHaveProperty('note')
      }

      const factIds = pack.evidence.facts.map((fact) => fact.id).sort()
      const auditIds = pack.audit.results.map((result) => result.id).sort()
      expect(new Set(auditIds).size, pack.id).toBe(auditIds.length)
      expect(auditIds, pack.id).toEqual(factIds)
    }
  })

  it('excludes suppressed findings and facts unrelated to the displayed receipt', () => {
    expect(JSON.stringify(northDumfriesPack)).not.toContain(
      'FIND-ADMIN-CORP-SCALE',
    )
    expect(JSON.stringify(northDumfriesPack)).not.toContain('ND-CAP-ARENA-2026')
    expect(northDumfriesPack.evidence.gaps.length).toBeGreaterThan(0)
  })

})
