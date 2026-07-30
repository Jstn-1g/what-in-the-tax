/**
 * The repository this site is built from. The footer link used to be env-gated
 * so a private repository could never ship a link to a 404; the repository is
 * public now, so the canonical URL is the default and VITE_REPO_URL remains
 * only as an override for forks and mirrors deploying their own copy.
 */
export const CANONICAL_REPO_URL = 'https://github.com/Jstn-1g/what-in-the-tax'

/**
 * A repository link, accepted only when it is plainly a GitHub repository
 * page. Anything that fails the shape check is dropped in favour of the
 * canonical URL rather than rendered, so a typo'd override variable cannot
 * ship a link to somewhere else.
 */
export function normalizeRepoUrl(value: unknown): string | null {
  if (typeof value !== 'string' || value.trim() === '') return null
  try {
    const url = new URL(value.trim())
    if (
      url.protocol !== 'https:' ||
      url.hostname !== 'github.com' ||
      url.username ||
      url.password ||
      url.search ||
      url.hash ||
      !/^\/[\w.-]+\/[\w.-]+\/?$/.test(url.pathname)
    ) {
      return null
    }
    return url.href
  } catch {
    return null
  }
}

/** The repository URL every footer link builds on, without a trailing slash. */
export function repoBaseUrl(): string {
  const repoUrl = normalizeRepoUrl(import.meta.env.VITE_REPO_URL) ?? CANONICAL_REPO_URL
  return repoUrl.replace(/\/$/, '')
}
