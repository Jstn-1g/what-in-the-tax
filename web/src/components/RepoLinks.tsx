import { repoBaseUrl } from '../repoLink'

/**
 * The three open-source links every footer carries: the repository itself,
 * the correction issue form, and the public corrections log. Shared between
 * the product footer and the receipt screen's footer so the receipt page -
 * the page most visitors actually see - makes the same offer as the rest of
 * the site.
 */
export default function RepoLinks() {
  const repoBase = repoBaseUrl()
  return (
    <>
      <a href={repoBase} target="_blank" rel="noreferrer">
        Source code &amp; data
        <span className="visually-hidden"> (opens in a new tab)</span>
      </a>
      <a
        href={`${repoBase}/issues/new?template=wrong-number.yml`}
        target="_blank"
        rel="noreferrer"
      >
        Report a wrong number
        <span className="visually-hidden"> (opens in a new tab)</span>
      </a>
      <a
        href={`${repoBase}/blob/main/CORRECTIONS.md`}
        target="_blank"
        rel="noreferrer"
      >
        Corrections log
        <span className="visually-hidden"> (opens in a new tab)</span>
      </a>
      <a
        href={`${repoBase}/blob/main/CONTRIBUTING.md`}
        target="_blank"
        rel="noreferrer"
      >
        How to contribute
        <span className="visually-hidden"> (opens in a new tab)</span>
      </a>
    </>
  )
}
