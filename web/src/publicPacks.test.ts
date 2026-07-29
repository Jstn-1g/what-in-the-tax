import { describe, expect, it } from 'vitest'
import brantPack from '../public/packs/brant-county-on.json'
import cambridgePack from '../public/packs/cambridge-on.json'
import kitchenerPack from '../public/packs/kitchener-on.json'
import northDumfriesPack from '../public/packs/north-dumfries-on.json'
import waterlooPack from '../public/packs/waterloo-on.json'
import woolwichPack from '../public/packs/woolwich-on.json'
import { PACK_CATALOG, type PackId } from './packCatalog'
import { validatePublicPack } from './publicPackSchema'

const PUBLIC_PACKS = [
  brantPack,
  cambridgePack,
  kitchenerPack,
  northDumfriesPack,
  waterlooPack,
  woolwichPack,
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
      expect(pack.schemaVersion, pack.id).toBe('1.2.0')
      expect(pack.receipt.fiscalYear, pack.id).toBe(2026)
      expect(pack.receipt.currency, pack.id).toBe('CAD')
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

  it('publishes Brant scope metadata without pretending approval exists', () => {
    expect(brantPack.receipt.publisher).toEqual({
      name: 'What in the Tax? project',
      role: 'Independent project publisher; not the County of Brant',
    })
    expect(brantPack.receipt).not.toHaveProperty(
      'publisher.repositoryUrl',
    )
    expect(brantPack.receipt.correctionsRoute).toEqual({
      type: 'required-before-publication',
      url: null,
      status: 'pending-public-contact-channel',
    })
    expect(brantPack.receipt.publicationApproval).toEqual({
      status: 'pending-named-human-approval',
      approvedBy: null,
      approvedAt: null,
    })
    expect(brantPack.receipt.coverage).toMatchObject({
      status: 'complete-for-declared-tier-0-scope',
      tier: 0,
      fiscalYear: 2026,
      currency: 'CAD',
      findingsCount: 0,
      openGapsCount: 0,
    })
  })

  // packs.ts validates every pack through this schema on load, so a committed
  // artifact the schema rejects is a receipt no reader can open. Nothing
  // exercised that pairing before: the schema was tested against hand-built
  // fixtures and the artifacts were tested structurally, and the gap between
  // them is exactly where a builder can ship a field the reader's schema
  // refuses.
  it('every committed artifact passes the schema the app loads it through', () => {
    for (const pack of PUBLIC_PACKS) {
      expect(() => validatePublicPack(pack.id as PackId, pack), pack.id).not.toThrow()
    }
  })
})

// A gate that has never refused anything has not been shown to work. Each case
// below plants one defect into the only pack that declares a bill and proves
// the loader refuses it, so the test above means "checked" rather than "ran".
describe('the declared bill is checked, not just carried', () => {
  function brantWith(
    mutate: (profile: Record<string, unknown>) => void,
  ): unknown {
    const clone = structuredClone(brantPack) as typeof brantPack
    mutate(
      clone.receipt.profiles.supportedAverageHousehold as unknown as Record<
        string,
        unknown
      >,
    )
    return clone
  }

  function refusal(pack: unknown): string {
    try {
      validatePublicPack('brant-county-on', pack)
    } catch (error) {
      return (error as Error).message
    }
    throw new Error('expected the pack to be refused, but it validated')
  }

  it('refuses a role the model does not define', () => {
    const pack = brantWith((profile) => {
      ;(profile.taxingBodies as { role: string }[])[0].role = 'transit-authority'
    })
    expect(refusal(pack)).toMatch(/taxingBodies\[0\]\.role must be one of/)
  })

  it('refuses a bill whose parts disagree with its printed total', () => {
    const pack = brantWith((profile) => {
      ;(profile.taxingBodies as { amountCad: number }[])[0].amountCad += 100
    })
    expect(refusal(pack)).toMatch(/is not a coherent bill/)
  })

  it('refuses two bodies claiming the same singular role', () => {
    const pack = brantWith((profile) => {
      const bodies = profile.taxingBodies as { role: string }[]
      bodies[1].role = 'local'
    })
    expect(refusal(pack)).toMatch(/at most one local body/)
  })

  it('refuses a role that is both charged and declared not applicable', () => {
    const pack = brantWith((profile) => {
      ;(profile.inapplicableBodies as { role: string }[])[0].role = 'education'
    })
    expect(refusal(pack)).toMatch(/both as a taxing body and as not applicable/)
  })

  it('refuses a not-applicable entry that gives no reason', () => {
    const pack = brantWith((profile) => {
      ;(profile.inapplicableBodies as { reason: string }[])[0].reason = ''
    })
    expect(refusal(pack)).toMatch(/inapplicableBodies\[0\]\.reason/)
  })

  it('refuses a body carrying a key nobody reviewed', () => {
    const pack = brantWith((profile) => {
      ;(profile.taxingBodies as Record<string, unknown>[])[0].billImpactCad = 999
    })
    expect(refusal(pack)).toMatch(/taxingBodies\[0\]\.billImpactCad is not allowed/)
  })
})
