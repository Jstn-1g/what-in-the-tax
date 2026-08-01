export type SupportCardProps = {
  onceUrl?: string
  monthlyUrl?: string
}

export type SupportOption = {
  label: string
  url: string
  className: string
}

// Stripe serves Payment Links from two hosts: buy.stripe.com for ordinary
// links and donate.stripe.com for donation-type links, where the contributor
// chooses the amount. Both are hosted checkout pages Stripe controls; neither
// carries a key. Allowing only the first silently dropped a valid donation
// link, which is the shape this project actually wants.
const SUPPORT_HOSTS = new Set(['buy.stripe.com', 'donate.stripe.com'])

export function normalizeSupportUrl(value: unknown): string | null {
  if (typeof value !== 'string' || value.trim() === '') return null

  try {
    const url = new URL(value.trim())
    if (
      url.protocol !== 'https:' ||
      !SUPPORT_HOSTS.has(url.hostname) ||
      url.username ||
      url.password ||
      url.hash ||
      url.pathname.split('/').some((part) => part.startsWith('test_'))
    ) {
      return null
    }
    return url.href
  } catch {
    return null
  }
}

export function supportOptionsFor(
  onceUrl?: string,
  monthlyUrl?: string,
): SupportOption[] {
  return [
    {
      label: 'Donate',
      url: normalizeSupportUrl(onceUrl),
      className: 'button button-primary',
    },
    {
      label: 'Support monthly',
      url: normalizeSupportUrl(monthlyUrl),
      className: 'button button-secondary',
    },
  ].filter((option): option is SupportOption => option.url != null)
}

export default function SupportCard({
  onceUrl = import.meta.env.VITE_SUPPORT_ONCE_URL,
  monthlyUrl = import.meta.env.VITE_SUPPORT_MONTHLY_URL,
}: SupportCardProps) {
  const supportOptions = supportOptionsFor(onceUrl, monthlyUrl)

  return (
    <aside className="support-card" aria-labelledby="support-card-heading">
      <span className="support-card__pin" aria-hidden="true" />
      <div className="support-card__body">
        <h2 id="support-card-heading">
          Keep What in the Tax? free and independent
        </h2>
        <p>
          No paywalls, paid rankings, or sponsored findings. Voluntary support
          helps pay for official records, secure hosting, accessibility,
          bilingual review, and independent verification.
        </p>
        <p className="support-card__promise">
          Support never influences which communities we cover or what a receipt
          says.
        </p>

        {supportOptions.length > 0 ? (
          <div className="support-card__actions">
            {supportOptions.map((option) => (
              <a
                key={option.label}
                className={option.className}
                href={option.url}
                rel="noopener noreferrer"
              >
                {option.label}
              </a>
            ))}
          </div>
        ) : (
          <p className="support-card__pending">
            Support options are coming at launch.
          </p>
        )}

        <p className="support-card__legal">
          Contributions are not eligible for charitable tax receipts.
        </p>
      </div>
    </aside>
  )
}
