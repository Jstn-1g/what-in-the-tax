import { describe, expect, it } from 'vitest'

import { CANONICAL_REPO_URL, normalizeRepoUrl, repoBaseUrl } from '../repoLink'
import { normalizeSupportUrl } from '../components/SupportCard'

// The footer renders on every page shape, so a bad value here ships
// everywhere at once. The repository links default to the canonical public
// repository and VITE_REPO_URL is only an override for forks; the rule under
// test is that a malformed override falls back to the canonical URL rather
// than shipping a link to somewhere that merely resembles the repository.
// The support link stays env-gated: unset or malformed renders NO link.
describe('the footer repository link', () => {
  it('accepts the canonical repository page', () => {
    expect(normalizeRepoUrl(CANONICAL_REPO_URL)).toBe(CANONICAL_REPO_URL)
    expect(CANONICAL_REPO_URL).toBe('https://github.com/Jstn-1g/what-in-the-tax')
  })

  it('falls back to the canonical repository while the override is unset', () => {
    expect(normalizeRepoUrl(undefined)).toBeNull()
    expect(normalizeRepoUrl('')).toBeNull()
    expect(repoBaseUrl()).toBe(CANONICAL_REPO_URL)
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
