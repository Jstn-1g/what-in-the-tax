import { describe, expect, it, vi } from 'vitest'
import kitchenerPublicPack from '../public/packs/kitchener-on.json'
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

  it('rejects incomplete citation-audit coverage', async () => {
    const payload = structuredClone(kitchenerPublicPack)
    payload.audit.results.pop()
    const fetcher: PackFetcher = async () => response(payload)

    await expect(
      loadPackWithFetcher('kitchener-on', fetcher, '/'),
    ).rejects.toThrow('exactly one row per public fact')
  })

  it('rejects blocked packs without making a network request', async () => {
    const fetcher = vi.fn<PackFetcher>()
    await expect(
      loadPackWithFetcher('woolwich-on', fetcher, '/'),
    ).rejects.toThrow(/evidence update required/i)
    expect(fetcher).not.toHaveBeenCalled()
  })

  it('rejects a failed public artifact request', async () => {
    const fetcher: PackFetcher = async () => response({}, 404)
    await expect(
      loadPackWithFetcher('kitchener-on', fetcher, '/'),
    ).rejects.toThrow('(404)')
  })
})
