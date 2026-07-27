import { describe, expect, it, vi } from 'vitest'
import kitchenerPublicPack from '../public/packs/kitchener-on.json'
import woolwichPublicPack from '../public/packs/woolwich-on.json'
import {
  loadPackWithFetcher,
  type PackFetchResponse,
  type PackFetcher,
} from './packs'

function response(value: unknown, status = 200): PackFetchResponse {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => value,
  }
}

describe('on-demand public pack loading', () => {
  it('fetches only the selected sanitized artifact under the configured base path', async () => {
    const fetcher = vi.fn<PackFetcher>(async () => response(kitchenerPublicPack))
    const pack = await loadPackWithFetcher(
      'kitchener-on',
      fetcher,
      '/tax-receipt-prototype/',
    )

    expect(fetcher).toHaveBeenCalledOnce()
    expect(fetcher).toHaveBeenCalledWith(
      '/tax-receipt-prototype/packs/kitchener-on.json',
    )
    expect(pack.id).toBe('kitchener-on')
    expect(pack.receipt.fiscalYear).toBe(2026)
    expect(pack.receipt.currency).toBe('CAD')
    expect(pack.receipt.jurisdiction?.slug).toBe('kitchener-on')
    expect(pack.evidence.sources.length).toBeGreaterThan(0)
  })

  it('rejects an artifact whose identity does not match the requested place', async () => {
    const fetcher: PackFetcher = async () =>
      response({ ...kitchenerPublicPack, id: 'waterloo-on' })
    await expect(
      loadPackWithFetcher('kitchener-on', fetcher, '/'),
    ).rejects.toThrow('must equal kitchener-on')
  })

  it('rejects an unsupported public envelope schema', async () => {
    const payload = structuredClone(kitchenerPublicPack)
    payload.schemaVersion = '99.0.0'
    const fetcher: PackFetcher = async () => response(payload)

    await expect(
      loadPackWithFetcher('kitchener-on', fetcher, '/'),
    ).rejects.toThrow('schemaVersion')
  })

  it('rejects a malformed receipt before rendering it', async () => {
    const payload = structuredClone(kitchenerPublicPack) as unknown as {
      receipt: Record<string, unknown>
    }
    delete payload.receipt.profiles
    const fetcher: PackFetcher = async () => response(payload)

    await expect(
      loadPackWithFetcher('kitchener-on', fetcher, '/'),
    ).rejects.toThrow('receipt.profiles')
  })

  it('rejects a receipt that relies on prose instead of an explicit year', async () => {
    const payload = structuredClone(kitchenerPublicPack) as unknown as {
      receipt: Record<string, unknown>
    }
    delete payload.receipt.fiscalYear
    const fetcher: PackFetcher = async () => response(payload)

    await expect(
      loadPackWithFetcher('kitchener-on', fetcher, '/'),
    ).rejects.toThrow('receipt.fiscalYear')
  })

  it('rejects a receipt year that disagrees with the catalog', async () => {
    const payload = structuredClone(kitchenerPublicPack)
    payload.receipt.fiscalYear = 2025
    const fetcher: PackFetcher = async () => response(payload)

    await expect(
      loadPackWithFetcher('kitchener-on', fetcher, '/'),
    ).rejects.toThrow('must equal catalog currentEvidenceYear 2026')
  })

  it('rejects incomplete citation-audit coverage', async () => {
    const payload = structuredClone(kitchenerPublicPack)
    payload.audit.results.pop()
    const fetcher: PackFetcher = async () => response(payload)

    await expect(
      loadPackWithFetcher('kitchener-on', fetcher, '/'),
    ).rejects.toThrow('exactly one row per public fact')
  })

  it('loads the sanitized Woolwich draft preview without hiding its limits', async () => {
    const fetcher = vi.fn<PackFetcher>(async () => response(woolwichPublicPack))
    const pack = await loadPackWithFetcher('woolwich-on', fetcher, '/')

    expect(fetcher).toHaveBeenCalledWith('/packs/woolwich-on.json')
    expect(pack.receipt.status).toBe('partial_evidence_based')
    expect(
      pack.receipt.profiles.supportedAverageHousehold.description,
    ).toMatch(/not a published Township of Woolwich average/i)
    expect(pack.evidence.gaps.length).toBeGreaterThan(0)
  })

  it('rejects a failed public artifact request', async () => {
    const fetcher: PackFetcher = async () => response({}, 404)
    await expect(
      loadPackWithFetcher('kitchener-on', fetcher, '/'),
    ).rejects.toThrow('(404)')
  })
})
