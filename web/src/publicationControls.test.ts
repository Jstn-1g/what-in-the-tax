import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

// noindex is the only control limiting the reach of a fleet nobody has sealed,
// and until this file existed it was enforced by nothing automated - the
// readiness audit called that out by name. PUBLISH.md is explicit that the
// deployment must keep serving noindex until the seal gates pass, so dropping
// either copy of it in a refactor must fail CI, not wait for someone to notice
// receipts in search results.
//
// Both layers are pinned deliberately: the meta tag is what a saved or proxied
// copy of the page carries, and the _headers file is what Cloudflare actually
// serves. Losing either one silently is the same failure.

const root = resolve(__dirname, '..')

describe('publication controls stay closed until sealing', () => {
  it('the page itself declares noindex', () => {
    const html = readFileSync(resolve(root, 'index.html'), 'utf-8')
    expect(html).toMatch(/<meta\s+name="robots"\s+content="noindex,\s*nofollow"\s*\/>/)
  })

  it('the deployment serves X-Robots-Tag noindex', () => {
    const headers = readFileSync(resolve(root, 'public', '_headers'), 'utf-8')
    expect(headers).toMatch(/X-Robots-Tag:\s*noindex,\s*nofollow/)
  })

  it('sharing metadata never contradicts the draft posture', () => {
    // Open Graph text is the one part of the page that travels without its
    // disclaimers, so the disclaimer has to travel inside it.
    const html = readFileSync(resolve(root, 'index.html'), 'utf-8')
    const og = html.match(/property="og:description"[^>]*content="([^"]+)"/s)
    expect(og).not.toBeNull()
    expect(og![1]).toMatch(/not tax advice/i)
    expect(og![1]).toMatch(/draft|preview/i)
  })

  it('identifies the single canonical public URL without opening indexing', () => {
    const html = readFileSync(resolve(root, 'index.html'), 'utf-8')
    const canonicals = html.match(/<link\s+rel="canonical"\s+href="https:\/\/whatinthetax\.com\/"\s*\/>/g)
    expect(canonicals).toHaveLength(1)
    expect(html).toMatch(/<meta\s+name="robots"\s+content="noindex,\s*nofollow"\s*\/>/)
  })

  it('publishes one complete large-image share contract', () => {
    const html = readFileSync(resolve(root, 'index.html'), 'utf-8')
    const imageUrl = 'https://whatinthetax.com/what-in-the-tax-share.png'

    expect(html).toContain(`<meta property="og:image" content="${imageUrl}" />`)
    expect(html).toContain(`<meta property="og:image:secure_url" content="${imageUrl}" />`)
    expect(html).toContain('<meta property="og:image:type" content="image/png" />')
    expect(html).toContain('<meta property="og:image:width" content="1200" />')
    expect(html).toContain('<meta property="og:image:height" content="630" />')
    expect(html).toMatch(/property="og:image:alt"[\s\S]*content="[^"]+"/)
    expect(html).toContain('<meta name="twitter:card" content="summary_large_image" />')
    expect(html).toContain(`<meta name="twitter:image" content="${imageUrl}" />`)
    expect(html).toMatch(/name="twitter:image:alt"[\s\S]*content="[^"]+"/)
  })

  it('ships the declared PNG at exactly 1200 by 630 pixels', () => {
    const image = readFileSync(resolve(root, 'public', 'what-in-the-tax-share.png'))

    expect(image.subarray(0, 8)).toEqual(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))
    expect(image.subarray(12, 16).toString('ascii')).toBe('IHDR')
    expect(image.readUInt32BE(16)).toBe(1200)
    expect(image.readUInt32BE(20)).toBe(630)
  })

  it('does not advertise a sitemap while every response is noindex', () => {
    const html = readFileSync(resolve(root, 'index.html'), 'utf-8')
    const robots = readFileSync(resolve(root, 'public', 'robots.txt'), 'utf-8')

    expect(html).not.toMatch(/rel="sitemap"/i)
    expect(robots).not.toMatch(/^Sitemap:/im)
  })
})
