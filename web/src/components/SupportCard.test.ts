import { describe, expect, it } from 'vitest'
import { normalizeSupportUrl, supportOptionsFor } from './SupportCard'

describe('normalizeSupportUrl', () => {
  it('accepts a trimmed HTTPS payment URL', () => {
    expect(normalizeSupportUrl('  https://buy.stripe.com/example  ')).toBe(
      'https://buy.stripe.com/example',
    )
  })

  it('accepts a donation-host payment link', () => {
    // Stripe issues donation-type links on donate.stripe.com. Rejecting that
    // host dropped a valid live link and left the card saying support was
    // still coming.
    expect(
      normalizeSupportUrl('https://donate.stripe.com/7sY7sMcpteSo4uS4FH2cg01'),
    ).toBe('https://donate.stripe.com/7sY7sMcpteSo4uS4FH2cg01')
  })

  it.each([
    undefined,
    null,
    '',
    '   ',
    'http://example.com/support',
    'https://example.com/support',
    'javascript:alert(1)',
    'https://user:password@example.com/support',
    'https://buy.stripe.com/test_example',
    'https://buy.stripe.com/example#checkout',
    // The test-mode and look-alike-host guards hold on the donation host too.
    'https://donate.stripe.com/test_example',
    'https://donate.stripe.com/example#checkout',
    'https://donate.stripe.com.evil.example/support',
    'https://notdonate.stripe.com/support',
    'not a URL',
  ])('rejects an unsafe or missing value: %s', (value) => {
    expect(normalizeSupportUrl(value)).toBeNull()
  })
})

describe('supportOptionsFor', () => {
  it('returns no actions when payment links are not configured', () => {
    expect(supportOptionsFor()).toEqual([])
  })

  it('returns only the configured contribution action', () => {
    expect(
      supportOptionsFor('https://buy.stripe.com/once_example'),
    ).toEqual([
      {
        label: 'Donate',
        url: 'https://buy.stripe.com/once_example',
        className: 'button button-primary',
      },
    ])
  })

  it('returns both actions when both live links are configured', () => {
    expect(
      supportOptionsFor(
        'https://buy.stripe.com/once_example',
        'https://buy.stripe.com/monthly_example',
      ),
    ).toHaveLength(2)
  })
})
