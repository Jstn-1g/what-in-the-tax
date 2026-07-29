import { describe, expect, it } from 'vitest'

import { normalizeRepoUrl } from '../App'
import { normalizeSupportUrl } from '../components/SupportCard'

// The footer renders on every page shape, so a bad value here ships
// everywhere at once. Both links are env-gated and normalized: the rule under
// test is that an unset or malformed variable renders NO link rather than a
// wrong one. A footer link to a 404 - or to somewhere that merely resembles
// the repository - is worse than no link.
describe('the footer repository link', () => {
  it('accepts the canonical repository page', () => {
    expect(normalizeRepoUrl('https://github.com/Jstn-1g/what-in-the-tax')).toBe(
      'https://github.com/Jstn-1g/what-in-the-tax',
    )
  })

  it('renders nothing while the variable is unset', () => {
    // The pre-launch state: repository private, no VITE_REPO_URL configured.
    expect(normalizeRepoUrl(undefined)).toBeNull()
    expect(normalizeRepoUrl('')).toBeNull()
  })

  it('refuses anything that is not a GitHub repository page', () => {
    expect(normalizeRepoUrl('http://github.com/Jstn-1g/what-in-the-tax')).toBeNull()
    expect(normalizeRepoUrl('https://github.com.evil.example/a/b')).toBeNull()
    expect(normalizeRepoUrl('https://github.com/Jstn-1g')).toBeNull()
    expect(
      normalizeRepoUrl('https://github.com/Jstn-1g/what-in-the-tax?tab=stargazers'),
    ).toBeNull()
    expect(normalizeRepoUrl('https://gitlab.com/Jstn-1g/what-in-the-tax')).toBeNull()
  })
})

describe('the footer support link', () => {
  it('reuses the support card normalizer, so test-mode links stay out', () => {
    expect(
      normalizeSupportUrl('https://donate.stripe.com/test_7sY7sMcpteSo4uS'),
    ).toBeNull()
    expect(normalizeSupportUrl('https://donate.stripe.com/7sY7sMcpteSo4uS')).toBe(
      'https://donate.stripe.com/7sY7sMcpteSo4uS',
    )
  })
})
