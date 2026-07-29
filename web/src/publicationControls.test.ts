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
})
