/**
 * Resident-friendly help for reading a What in the Tax? receipt.
 */

const SECTIONS = [
  { id: 'quick-start', title: 'Quick start' },
  { id: 'evidence-labels', title: 'Evidence labels' },
  { id: 'calculations', title: 'How calculations work' },
  { id: 'governing-bodies', title: 'Which governing bodies can appear' },
  { id: 'sources-corrections', title: 'Sources and corrections' },
  { id: 'faq', title: 'FAQ' },
] as const

export default function HelpGuide({
  onBack,
  onNavigate,
  backLabel = 'Back to receipt',
  simpleLanguage = false,
}: {
  onBack: () => void
  onNavigate: (targetId: string) => void
  backLabel?: string
  simpleLanguage?: boolean
}) {
  return (
    <main id="help/main" className="help-page" tabIndex={-1}>
      <header className="help-hero">
        <p className="help-kicker">Help</p>
        <h1 id="help-heading" tabIndex={-1}>
          How to use What in the Tax?
        </h1>
        <p className="help-lede">
          What in the Tax? turns public budgets, tax-rate schedules, and by-laws
          into a plain-language example. It is independent—not a government
          service, formal financial audit, official tax bill, or tax advice.
        </p>
        {simpleLanguage ? (
          <p className="help-eli5-note" role="status">
            <strong>Plain language is on.</strong> Technical evidence labels remain visible so you
            can match this guide to the receipt.
          </p>
        ) : null}
        <div className="help-hero-actions">
          <button type="button" className="cta" onClick={onBack}>
            {backLabel}
          </button>
          <a
            className="cta cta-ghost help-toc-jump"
            href="#help/toc"
            onClick={(event) => {
              event.preventDefault()
              onNavigate('help/toc')
            }}
          >
            See help topics
          </a>
        </div>
      </header>

      <div className="help-layout">
        <nav
          className="help-toc"
          id="help/toc"
          aria-label="Help topics"
          tabIndex={-1}
        >
          <p className="help-toc-title">On this page</p>
          <ol>
            {SECTIONS.map((section, index) => (
              <li key={section.id}>
                <a
                  href={`#help/${section.id}`}
                  onClick={(event) => {
                    event.preventDefault()
                    onNavigate(`help/${section.id}`)
                  }}
                >
                  <span className="help-toc-num">{String(index + 1).padStart(2, '0')}</span>
                  {section.title}
                </a>
              </li>
            ))}
          </ol>
        </nav>

        <article className="help-article">
          <section id="help/quick-start" className="help-section" tabIndex={-1}>
            <h2>Quick start</h2>
            <ol className="help-steps">
              <li>
                <strong>Confirm the place, tax year, and status.</strong> A draft or preview may
                still have open gaps. A published receipt has passed the project&apos;s release
                checks.
              </li>
              <li>
                <strong>Check the sample assessment.</strong> What in the Tax?
                does not look up an address or roll number. The amount shown is
                an example unless you calculate from your own assessed value.
              </li>
              <li>
                <strong>Read the combined total and its parts.</strong> Each part shows which public
                body levies or controls that amount.
              </li>
              <li>
                <strong>Check the evidence.</strong> Open a source link for any figure you want to
                verify and review any listed gaps before relying on the result.
              </li>
            </ol>
          </section>

          <section id="help/evidence-labels" className="help-section" tabIndex={-1}>
            <h2>Evidence labels</h2>
            <p>
              These labels describe how a claim was produced. They do not grade a government or
              imply that anyone did something wrong.
            </p>
            <dl className="help-glossary">
              <div>
                <dt>FACT</dt>
                <dd>
                  A figure copied from an identified public source. Technical details should name
                  the document and, when possible, the page or record.
                </dd>
              </div>
              <div>
                <dt>DERIVED</dt>
                <dd>
                  A result calculated from sourced inputs with a stated formula. It can be checked
                  again, but it is not necessarily a number printed on an official bill.
                </dd>
              </div>
              <div>
                <dt>GAP</dt>
                <dd>
                  Evidence is missing, incomplete, or not strong enough to support a claim. The
                  receipt leaves the value open instead of guessing.
                </dd>
              </div>
              <div>
                <dt>JUDGMENT</dt>
                <dd>
                  A clearly identified interpretation based on cited facts. A judgment does not
                  imply wrongdoing, and its bill impact stays unset unless a reviewed formula
                  supports one.
                </dd>
              </div>
            </dl>
            <p>
              A citation or source check only tests whether a claim points to supporting material.
              It does not, by itself, make a receipt complete or ready to publish.
            </p>
          </section>

          <section id="help/calculations" className="help-section" tabIndex={-1}>
            <h2>How calculations work</h2>
            <p className="help-formula">tax component = assessed value × published tax rate</p>
            <p>
              What in the Tax? adds the applicable components to show a combined
              sample total. Depending on the place, those components may include
              local, regional, education, or special levies. Rounding is shown
              rather than hidden when cents need to be reconciled.
            </p>
            <p>
              A service or department breakdown may be a proportional model over a government&apos;s
              published net requirement. Those lines are marked <strong>DERIVED</strong> and are not
              a second official bill. Values are never borrowed from another municipality to fill
              a missing local figure.
            </p>
          </section>

          <section id="help/governing-bodies" className="help-section" tabIndex={-1}>
            <h2>Which governing bodies can appear</h2>
            <p>
              Canadian property-tax systems vary. A receipt may include a municipality, township,
              city, county, regional or district government, education body, province or territory,
              or another authority with a documented levy that applies to the selected place.
            </p>
            <p>
              Some places have one local tier; others have two or more public bodies on the same
                bill. What in the Tax? follows the structure in official records.
                It does not substitute a nearby or similarly named municipality
                when the correct body or source is missing.
            </p>
          </section>

          <section id="help/sources-corrections" className="help-section" tabIndex={-1}>
            <h2>Sources and corrections</h2>
            <p>
              Sources can include adopted budgets, tax-rate schedules, by-laws, financial reports,
              and official open-data records. A source link lets you compare the receipt with the
              public record.
            </p>
            <dl className="help-glossary">
              <div>
                <dt>Draft</dt>
                <dd>Work is in progress and may contain unresolved evidence or calculation gaps.</dd>
              </div>
              <div>
                <dt>Preview</dt>
                <dd>
                  The receipt can be reviewed publicly, but it has not passed every publication
                  gate.
                </dd>
              </div>
              <div>
                <dt>Not published</dt>
                <dd>
                  This static preview does not label any receipt Published. A
                  public publisher and correction route have not been designated.
                </dd>
              </div>
            </dl>
            <p>
              Corrections and additional official evidence are welcome. A covered governing body
              has a right to reply to a finding, and a disputed point remains clearly labelled
              while it is reviewed. A gap, question, or correction request is not an allegation of
              waste, misconduct, or wrongdoing.
            </p>
            <p>
              The project is open source: every number on this site, the evidence behind it, and
              the checks that gate it live in a{' '}
              <a
                href="https://github.com/Jstn-1g/what-in-the-tax"
                target="_blank"
                rel="noreferrer"
              >
                public repository
                <span className="visually-hidden"> (opens in a new tab)</span>
              </a>
              . To report a figure that looks wrong, open a{' '}
              <a
                href="https://github.com/Jstn-1g/what-in-the-tax/issues/new?template=wrong-number.yml"
                target="_blank"
                rel="noreferrer"
              >
                correction issue
                <span className="visually-hidden"> (opens in a new tab)</span>
              </a>{' '}
              or write to{' '}
              <a href="mailto:corrections@whatinthetax.com">corrections@whatinthetax.com</a>.
              Every resolved report is recorded in the repository&apos;s public corrections log,
              whatever the outcome.
            </p>
          </section>

          <section id="help/faq" className="help-section" tabIndex={-1}>
            <h2>FAQ</h2>
            <div className="help-faq">
              <details>
                <summary>Why does the sample differ from my tax bill?</summary>
                <p>
                  Your bill uses your property&apos;s assessed value and any area-specific charges.
                    What in the Tax? may use a published average, median, or other
                    documented example. Your official bill remains the source for
                    what you owe.
                </p>
              </details>
              <details>
                <summary>Can I enter my address or roll number?</summary>
                <p>
                    No. What in the Tax? does not provide an address or roll-number
                    lookup. Use the assessed value on your official notice if the
                    receipt offers a calculator.
                </p>
              </details>
              <details>
                <summary>Why is a governing body or amount missing?</summary>
                <p>
                    The correct official source may not yet be available or
                    verified. What in the Tax? marks that as a gap instead of
                    using another municipality&apos;s data or an unsupported
                    estimate.
                </p>
              </details>
              <details>
                <summary>Does a source check mean the receipt is ready?</summary>
                <p>
                  No. Source matching is one check. Place identity, calculation, completeness,
                  review, and release-state checks must also pass before publication.
                </p>
              </details>
              <details>
                <summary>What should I do if a figure is wrong?</summary>
                <p>
                  Note the place, tax year, line, and official source that supports the correction.
                    What in the Tax? can then review the evidence, update the
                    receipt, and preserve a clear record of the change.
                </p>
              </details>
            </div>
          </section>

          <p className="help-footer-note">
            What in the Tax? receipts are independent summaries of public
            information. Always use your official notice for payment, deadlines,
            exemptions, and account-specific questions.
          </p>

          <button type="button" className="cta help-back-bottom" onClick={onBack}>
            {backLabel}
          </button>
        </article>
      </div>
    </main>
  )
}
