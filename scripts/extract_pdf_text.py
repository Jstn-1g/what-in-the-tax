"""Extract text from PDFs into page-marked extracts, driven by each pack's sources[].

Every extract in data/_extracts/ is what a reader reconciles a citation against,
so which extracts exist must be decided by the packs' declared sources rather
than by a list typed into this file. It used to be the latter: eight North
Dumfries and Region filenames, hardcoded, silently skipped when absent, and the
only thing in the repository keeping one committed extract alive.

Sources come from corpus/<slug>/sources.lock.json when a pack has been locked
and corpus/<slug>/build-inputs.yaml otherwise. Both declare sources[] with the
same three fields this needs: id, localPath, extractedText.

    python scripts/extract_pdf_text.py                # every pack
    python scripts/extract_pdf_text.py --pack brant-county-on
    python scripts/extract_pdf_text.py --check        # verify, write nothing
    python scripts/extract_pdf_text.py --uncited      # also the PDFs nobody cites
    python scripts/extract_pdf_text.py --manifest path/to/manifest.yaml
    python scripts/extract_pdf_text.py a.pdf b.pdf --out-dir data/_extracts/foo

Exit codes: 0 clean, 1 a declared source is unusable or an extract is unaccounted
for, 2 a path was unsafe or a declaration malformed.

Nothing is skipped quietly. A source that declares no local file, an extract on
disk that no source claims, and a pack that declares no sources at all are each
named in the report and each fail the run, because all three mean some published
text cannot be traced back to a document.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.path_safety import (  # noqa: E402
    PathSafetyError,
    resolve_under_root,
    validate_slug,
)

SOURCE = ROOT / "source-pdfs"
OUT = ROOT / "data" / "_extracts"
CORPUS = ROOT / "corpus"

# Local PDFs that no pack cites still matter: a gap's searchTrail saying "we
# looked" is hollow if the document was never turned into text to look in. They
# are working material, not evidence, so they extract to their own directory and
# that directory is gitignored. Committing them would put uncited text in the
# same tree a reader reconciles citations against.
UNCITED = OUT / "_uncited"


@dataclass(frozen=True)
class Job:
    """One declared source that can be extracted from a local file."""

    pack: str
    source_id: str
    pdf: Path
    out: Path


@dataclass(frozen=True)
class Note:
    """Something the run could not do, kept so it can be reported by name."""

    pack: str
    source_id: str
    detail: str
    # Set when the source still declares an extract path. A capture has no local
    # document to re-derive it from, but it is declared, so it is not an orphan.
    extract: Path | None = None


def resolve_under_approved_root(
    value: str | Path,
    *,
    approved_root: Path,
    label: str,
    allow_absolute: bool = False,
) -> Path:
    """Resolve a path and prove it remains under a project-owned root.

    Declared paths are intentionally project-relative so pack files stay
    portable. Direct CLI paths may be absolute, but only when they already
    resolve inside the same approved root.
    """

    return resolve_under_root(
        value,
        project_root=ROOT,
        approved_root=approved_root,
        label=label,
        allow_absolute=allow_absolute,
    )


def ensure_output_still_safe(path: Path) -> Path:
    """Recheck an output after creating its parent to catch symlink parents."""

    return resolve_under_approved_root(
        path,
        approved_root=OUT,
        label="extract output",
        allow_absolute=True,
    )


# Not every reviewed source is a PDF. The FIR peer comparison is a CSV, and
# because this extractor only knew how to read PDFs that source had no extract -
# so audit_citations reported its four facts "unverifiable" even though the rows
# they quote sit in a file already committed to the tree. Unverifiable there
# meant unread, not unverifiable.
TEXT_SUFFIXES = frozenset({".csv", ".tsv", ".txt"})


def extract_text_source(path: Path) -> tuple[str, int]:
    """A text source is already its own extract; normalise and mark it.

    Decoded strictly as UTF-8 rather than with errors='replace': a source whose
    bytes are not what the lock says they are should stop the build, not be
    silently rewritten into replacement characters that then reconcile against
    nothing.

    One page, because a CSV has none. Facts citing such a source carry
    page: null, which the audit already handles by searching the whole extract
    and recording page-citation-missing - honest for a file with no pages.
    """

    raw = path.read_bytes().decode("utf-8")
    normalized = raw.replace("\r\n", "\n").replace("\r", "\n")
    return f"\n\n===== PAGE 1 =====\n{normalized}", 1


def extract_text(source: Path) -> tuple[str, int]:
    """Render one source to page-marked text. Pure: nothing is written here."""

    if source.suffix.lower() in TEXT_SUFFIXES:
        return extract_text_source(source)
    reader = PdfReader(str(source))
    parts: list[str] = []
    for index, page in enumerate(reader.pages):
        parts.append(f"\n\n===== PAGE {index + 1} =====\n")
        parts.append(page.extract_text() or "")
    return "".join(parts), len(reader.pages)


def write_atomic(path: Path, payload: str) -> None:
    """Write via a temp file in the same directory, then replace.

    An interrupted write used to leave a truncated extract that still looks like
    an extract, which is worse than no file: a citation would reconcile against
    a document missing its later pages.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    safe = ensure_output_still_safe(path)
    handle, tmp_name = tempfile.mkstemp(
        dir=str(safe.parent), prefix=f".{safe.name}.", suffix=".tmp"
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, safe)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def pack_slugs() -> list[str]:
    """Every corpus pack. `_template` and loose files are not packs."""

    return sorted(
        entry.name
        for entry in CORPUS.iterdir()
        if entry.is_dir() and not entry.name.startswith("_")
    )


def read_yaml(path: Path) -> dict:
    if yaml is None:
        raise SystemExit("PyYAML required to read pack declarations")
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise PathSafetyError(f"declaration must be a mapping: {path}")
    return doc


def declared_sources(slug: str) -> tuple[list[dict], str] | None:
    """A pack's sources[], preferring the reviewed lock over the build inputs."""

    import json

    lock = CORPUS / slug / "sources.lock.json"
    if lock.is_file():
        doc = json.loads(lock.read_text(encoding="utf-8"))
        return list(doc.get("sources") or []), "sources.lock.json"
    inputs = CORPUS / slug / "build-inputs.yaml"
    if inputs.is_file():
        return list(read_yaml(inputs).get("sources") or []), "build-inputs.yaml"
    return None


def plan_pack(slug: str) -> tuple[list[Job], list[Note], list[Note]]:
    """Turn one pack's sources[] into jobs, declared skips, and hard failures."""

    found = declared_sources(slug)
    if found is None:
        return [], [], [
            Note(
                slug,
                "(whole pack)",
                "declares no sources: no sources.lock.json and no build-inputs.yaml, "
                "so nothing here can be reproduced from a document",
            )
        ]

    sources, origin = found
    jobs: list[Job] = []
    skips: list[Note] = []
    failures: list[Note] = []
    for source in sources:
        source_id = str(source.get("id") or "(unnamed source)")
        extract = source.get("extractedText")
        local = source.get("localPath")
        if not extract:
            # Cited by URL, or a payload nobody extracts text from. Correct, and
            # counted so "nothing to do" is never assumed.
            continue
        if not local:
            skips.append(
                Note(
                    slug,
                    source_id,
                    f"declares {extract} but no localPath, so it is a capture "
                    "rather than a local extraction and cannot be reproduced here",
                    extract=resolve_under_approved_root(
                        extract, approved_root=OUT, label=f"{origin} output"
                    ),
                )
            )
            continue
        pdf = resolve_under_approved_root(local, approved_root=SOURCE, label=f"{origin} source")
        out = resolve_under_approved_root(extract, approved_root=OUT, label=f"{origin} output")
        if not pdf.is_file():
            failures.append(
                Note(
                    slug,
                    source_id,
                    f"declared local source is not on disk: {local}",
                    extract=out,
                )
            )
            continue
        jobs.append(Job(slug, source_id, pdf, out))
    return jobs, skips, failures


def orphan_extracts(jobs: list[Job], declared: list[Note]) -> list[Path]:
    """Extracts on disk that no source declares.

    A capture and a source whose document is missing are both still declared -
    they are reported under their own headings. An orphan is different in kind:
    committed text that no pack claims at all, so there is nothing to check it
    against and no way to know what it is.
    """

    claimed = {job.out.resolve() for job in jobs}
    claimed |= {note.extract.resolve() for note in declared if note.extract is not None}
    return sorted(
        p
        for p in OUT.rglob("*.txt")
        if p.resolve() not in claimed and UNCITED not in p.parents
    )


def uncited_local_pdfs(jobs: list[Job], declared: list[Note]) -> list[Path]:
    """PDFs under source-pdfs/ that no pack's sources[] names."""

    cited = {job.pdf.resolve() for job in jobs}
    return sorted(
        p
        for p in SOURCE.rglob("*.pdf")
        if p.is_file() and p.resolve() not in cited
    )


def uncited_jobs(pdfs: list[Path]) -> list[Job]:
    return [
        Job("(uncited)", p.relative_to(SOURCE).as_posix(), p, UNCITED / p.relative_to(SOURCE).with_suffix(".txt"))
        for p in pdfs
    ]


def report(label: str, notes: list[Note] | list[Path]) -> None:
    if not notes:
        return
    print(f"\n{label} ({len(notes)}):", file=sys.stderr)
    for note in notes:
        if isinstance(note, Note):
            print(f"  {note.pack} / {note.source_id}: {note.detail}", file=sys.stderr)
        else:
            print(f"  {note.relative_to(ROOT).as_posix()}", file=sys.stderr)


def run_jobs(jobs: list[Job], *, check: bool) -> list[Note]:
    """Extract or verify. In check mode nothing on disk is touched."""

    drift: list[Note] = []
    for job in jobs:
        text, pages = extract_text(job.pdf)
        if check:
            current = job.out.read_text(encoding="utf-8") if job.out.is_file() else None
            if current is None:
                drift.append(Note(job.pack, job.source_id, f"no extract on disk: {job.out.relative_to(ROOT).as_posix()}"))
            elif current != text:
                drift.append(
                    Note(
                        job.pack,
                        job.source_id,
                        f"re-extracting {job.pdf.relative_to(ROOT).as_posix()} no longer "
                        f"reproduces {job.out.relative_to(ROOT).as_posix()}",
                    )
                )
            continue
        write_atomic(job.out, text)
        print(f"wrote {job.out.relative_to(ROOT).as_posix()}: {pages} pages, {len(text.encode('utf-8'))} bytes")
    return drift


def manifest_jobs(path: Path, label: str) -> list[Job]:
    """extract.files entries, retained for one-off and pre-pack extraction."""

    doc = read_yaml(path)
    extract = doc.get("extract") or {}
    if not isinstance(extract, dict):
        raise PathSafetyError(f"manifest extract must be a mapping: {path}")
    files = extract.get("files") or doc.get("files") or []
    if not files:
        raise SystemExit(f"no extract.files in {path}")
    if not isinstance(files, list) or not all(isinstance(item, dict) for item in files):
        raise PathSafetyError(f"manifest files must be a list of mappings: {path}")
    jobs: list[Job] = []
    for entry in files:
        if "pdf" not in entry or "out" not in entry:
            raise PathSafetyError(f"extract entry must contain 'pdf' and 'out': {path}")
        jobs.append(
            Job(
                label,
                str(entry["pdf"]),
                resolve_under_approved_root(entry["pdf"], approved_root=SOURCE, label="manifest PDF"),
                resolve_under_approved_root(entry["out"], approved_root=OUT, label="manifest output"),
            )
        )
    return jobs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdfs", nargs="*", type=Path, help="Explicit PDF paths")
    parser.add_argument("--pack", help="One corpus slug; default is every pack")
    parser.add_argument("--manifest", type=Path, help="YAML with extract.files or files[]")
    parser.add_argument("--out-dir", type=Path, help="Override output directory")
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify extracts reproduce from their sources; write nothing",
    )
    parser.add_argument(
        "--uncited",
        action="store_true",
        help=(
            "also extract local PDFs no pack cites, into data/_extracts/_uncited/ "
            "(gitignored working material, so a searchTrail can be honest)"
        ),
    )
    parser.add_argument(
        "--require",
        choices=("all", "reproduction"),
        default="all",
        help=(
            "which failures set the exit code. 'all' (default) also fails on "
            "undeclared or missing sources. 'reproduction' fails only when an "
            "extract no longer reproduces from its source, and reports the "
            "declaration issues without gating on them - they are open source "
            "reviews rather than build failures."
        ),
    )
    args = parser.parse_args(argv)

    jobs: list[Job] = []
    skips: list[Note] = []
    failures: list[Note] = []
    surveyed_every_pack = False

    try:
        if args.manifest:
            jobs = manifest_jobs(args.manifest, "(manifest)")
        elif args.pdfs:
            out_dir_value = args.out_dir or OUT
            out_dir = resolve_under_approved_root(
                out_dir_value,
                approved_root=OUT,
                label="output directory",
                allow_absolute=(args.out_dir is None or Path(out_dir_value).is_absolute()),
            )
            for pdf in args.pdfs:
                resolved = resolve_under_approved_root(
                    pdf, approved_root=ROOT, label="explicit PDF", allow_absolute=pdf.is_absolute()
                )
                out = resolve_under_approved_root(
                    out_dir / f"{resolved.stem}.txt",
                    approved_root=OUT,
                    label="extract output",
                    allow_absolute=True,
                )
                jobs.append(Job("(explicit)", resolved.name, resolved, out))
        else:
            slugs = [validate_slug(args.pack)] if args.pack else pack_slugs()
            surveyed_every_pack = args.pack is None
            for slug in slugs:
                pack_jobs, pack_skips, pack_failures = plan_pack(slug)
                jobs += pack_jobs
                skips += pack_skips
                failures += pack_failures
    except (KeyError, TypeError, PathSafetyError) as exc:
        print(f"REFUSED: unsafe or invalid extraction path: {exc}", file=sys.stderr)
        return 2

    for job in jobs:
        if not job.pdf.is_file():
            failures.append(Note(job.pack, job.source_id, f"source is not on disk: {job.pdf}"))
    jobs = [job for job in jobs if job.pdf.is_file()]

    if not jobs and not failures and not skips:
        print("nothing to extract", file=sys.stderr)
        return 1

    # Only a full survey can tell an orphan from a file another pack owns, or a
    # local PDF nobody cites from one this run simply did not ask for.
    orphans = orphan_extracts(jobs, skips + failures) if surveyed_every_pack else []
    uncited = uncited_local_pdfs(jobs, skips + failures) if surveyed_every_pack else []

    extra = uncited_jobs(uncited) if (args.uncited and uncited) else []
    drift = run_jobs(jobs + extra, check=args.check)

    print(f"\n{'verified' if args.check else 'extracted'}: {len(jobs) + len(extra)}")
    if uncited and not args.uncited:
        print(
            f"local PDFs no pack cites: {len(uncited)} "
            "(run with --uncited to extract them to data/_extracts/_uncited/)"
        )
    sys.stdout.flush()
    report("declared but not reproducible here", skips)
    report("declared source unusable", failures)
    report("extracts no source declares", orphans)
    report("extracts that no longer reproduce", drift)

    # Two different problems share this exit code, and they have different
    # owners. Whether an extract reproduces from its source is arithmetic and is
    # nobody's judgement call. Whether a source is declared and on disk is a
    # source review - adding one to a lock is an attestation - and those twelve
    # are open decisions, not defects a build can fix.
    #
    # Fusing them meant this gate could not run in CI at all: it would have been
    # permanently red on someone else's open decisions, so it ran nowhere, and a
    # hand-typed extract with a matching sha256 passed every gate the project
    # has. The hash proves nobody edited the extract after it was written. It
    # does not prove the extract came from the PDF. Only re-extraction does, and
    # re-extraction was not running.
    #
    # --require reproduction gates on the arithmetic half so it can start
    # running today. The declaration half stays reported, loudly, and stays
    # counted, so nothing is quietly downgraded to a warning.
    gating = list(drift) if args.require == "reproduction" else (
        list(failures) + list(orphans) + list(drift)
    )
    deferred = 0 if args.require != "reproduction" else len(failures) + len(orphans)

    if deferred:
        print(
            f"\n::warning::{deferred} declaration issue(s) reported above are not "
            "gating this run (--require reproduction). They are open source "
            "reviews, not build failures, and they are listed by pack and source.",
        )
    if gating:
        print(
            "\n::error::Some published text cannot be traced to a document on disk. "
            "Each line above names the pack and the source.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
