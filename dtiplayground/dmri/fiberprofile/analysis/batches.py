#
#   fiberprofile/analysis/batches.py
#
#   Batches (sites, scanners, protocol versions, studies) of a cohort for the QC steps, qc-registration and
#   qc-profiles: a scanner offset of FA or of the diffusivities makes every scan of a batch differ from the normative
#   reference, which the QC would read as outliers. The batch of a scan comes from a column of a table (--batch-csv,
#   by default the --age-csv, and --batch-column) or from a pattern on its path or name (--batch-regex).
#

import logging
import re
import warnings

import numpy as np

from dtiplayground.dmri.common.age_table import BatchRows, load_batch_table, value_from_table

log = logging.getLogger("batches")

NO_BATCH = ""  # the batch of the scans that neither the table nor the pattern assigns, and of all without batches


def add_batch_arguments(p, regex_target):
    """The options that assign the batches; *regex_target* says what --batch-regex is matched on."""
    p.add_argument("--batch-column", default=None, metavar="NAME",
                   help="Column of the batch (site, scanner, ...) of each scan in --batch-csv (by default the "
                        "--age-csv): the batch correction and the outlier scores are computed per batch, so that a "
                        "batch with a technical offset is not flagged as a whole")
    p.add_argument("--batch-csv", default=None, metavar="TABLE",
                   help="CSV/TSV with the --batch-column (default: the --age-csv); its subject and session columns "
                        "are detected as those of the age table, or named with --batch-subject-column / "
                        "--batch-session-column")
    p.add_argument("--batch-subject-column", default=None, metavar="NAME",
                   help="Subject column of --batch-csv (default: as --age-subject-column for the age table, else "
                        "auto-detect)")
    p.add_argument("--batch-session-column", default=None, metavar="NAME",
                   help="Session column of --batch-csv (default: as --age-session-column for the age table, else "
                        "auto-detect)")
    p.add_argument("--batch-regex", default=None, metavar="REGEX",
                   help=f"Pattern whose group 1 is the batch, matched on {regex_target}, for the scans the batch "
                        "table doesn't have (or without a table)")
    p.add_argument("--batch-min-scans", type=int, default=5, metavar="N",
                   help="Scans a batch needs (per age bin for the shifts) for its own estimates; a smaller batch "
                        "gets those of the whole cohort (default: 5)")


def _in_name(value, name):
    """Whether *value* is in *name* as a whole token: not inside a longer run of letters and digits ('dir79' is in
    'acq-dir79_dwi', '79' is not, 'CMRR_APPA' is in '999434_VSA_CMRR_APPA_tensor'), case-insensitive."""
    return bool(value) and re.search(r"(?<![A-Za-z0-9]){}(?![A-Za-z0-9])".format(re.escape(value)), name,
                                     re.IGNORECASE) is not None


def resolve_batch_rows(rows, name):
    """The batch of the scan *name* among the BatchRows of its session (rows of different batches): the row whose
    values, in the columns where the rows differ (an acquisition, protocol or scan column, or the batch itself),
    appear in the name. Returns (batch, [matching columns]), or (None, reason) when no row or rows of different
    batches match."""
    columns = sorted({c for _, cells in rows for c in cells})
    differ = [c for c in columns if len({cells.get(c, "") for _, cells in rows}) > 1]
    matches = []
    for batch, cells in rows:
        hit = [c for c in differ if _in_name(cells.get(c, ""), name)]
        if hit:
            matches.append((batch, hit))
    batches = {b for b, _ in matches}
    if len(batches) == 1:
        return batches.pop(), sorted({c for _, hit in matches for c in hit})
    if not matches:
        return None, "no row's {} in the name".format("/".join(differ) or "values")
    return None, "rows of batches {} match".format(", ".join(sorted(batches)))


class BatchAssigner:
    """The batch of a scan: its row in the batch table (the row matching its name, see resolve_batch_rows, when the
    table gives its session several batches), else group 1 of the pattern, else NO_BATCH."""

    def __init__(self, table=None, regex=None):
        self.table = table or {}
        self.regex = re.compile(regex) if regex else None
        self.resolved, self.unresolved = {}, {}  # scan name -> (batch, columns) / reason

    @property
    def active(self):
        return bool(self.table) or self.regex is not None

    def __call__(self, subject, session, text="", name=None):
        """*text*: what --batch-regex is matched on; *name*: the name of the scan (default *text*), to pick its row
        when the table gives its session several batches."""
        batch = value_from_table(subject, session, self.table)
        if isinstance(batch, BatchRows):
            name = str(text if name is None else name)
            batch, why = resolve_batch_rows(batch, name)
            if batch is None:
                self.unresolved[name] = why
            else:
                self.resolved[name] = (batch, why)
        if batch is None and self.regex is not None:
            m = self.regex.search(str(text))
            if m:
                batch = m.group(1) if m.groups() else m.group(0)
        return NO_BATCH if batch is None else str(batch)

    def report(self):
        """Log how the scans of the sessions with rows of different batches were told apart."""
        if self.resolved:
            by_column = {}
            for name, (batch, columns) in self.resolved.items():
                by_column.setdefault("/".join(columns), []).append(name)
            for columns, names in sorted(by_column.items()):
                log.info("Batch of %d scan(s) of sessions with rows of different batches told apart by the %s in "
                         "the scan name (e.g. %s -> %s)", len(names), columns, names[0], self.resolved[names[0]][0])
        if self.unresolved:
            log.warning("%d scan(s) of sessions with rows of different batches match none or several of them, so "
                        "their batch is unknown%s: %s", len(self.unresolved),
                        " (--batch-regex gives it, if it matches)" if self.regex else
                        "; give the table a column whose value is in the scan name (e.g. the acquisition) or use "
                        "--batch-regex",
                        "; ".join(f"{n} ({why})" for n, why in sorted(self.unresolved.items())[:5])
                        + (" ..." if len(self.unresolved) > 5 else ""))


def batch_assigner(args, p):
    """The BatchAssigner of the --batch-* options (an inactive one without them); option errors go to *p*."""
    if args.batch_min_scans < 1:
        p.error("--batch-min-scans must be at least 1")
    for opt in ("batch_csv", "batch_subject_column", "batch_session_column"):
        if getattr(args, opt) and not args.batch_column:
            p.error("--{} needs --batch-column".format(opt.replace("_", "-")))
    table = None
    if args.batch_column:
        path = args.batch_csv or args.age_csv
        if not path:
            p.error("--batch-column needs --batch-csv or --age-csv (the table that has the column)")
        same = not args.batch_csv or args.batch_csv == args.age_csv
        subject_column = args.batch_subject_column or (args.age_subject_column if same else None)
        session_column = args.batch_session_column or (args.age_session_column if same else None)
        try:
            table = load_batch_table(path, args.batch_column, subject_column, session_column)
        except (OSError, ValueError) as exc:
            p.error(f"--batch-column: {exc}")
    if args.batch_regex:
        try:
            re.compile(args.batch_regex)
        except re.error as exc:
            p.error(f"--batch-regex is not a valid regex: {exc}")
    return BatchAssigner(table, args.batch_regex)


def log_batches(batches, what="scan"):
    """Log the size of every batch (*batches*: the batch of each scan) and warn about the scans without one."""
    names, counts = np.unique(np.asarray(batches, dtype=object).astype(str), return_counts=True)
    log.info("Batches: %s", ", ".join(f"{n or '(none)'} {c}" for n, c in zip(names, counts)))
    n_none = int(sum(c for n, c in zip(names, counts) if n == NO_BATCH))
    if n_none and len(names) > 1:
        log.warning("%d %s(s) have no batch (no row in the batch table, no match of --batch-regex): they form a "
                    "batch of their own", n_none, what)


def center_by_batch(values, batches, min_scans):
    """*values* (scans x features, or a vector) less the median of their batch, per column: a batch offset of the
    scores is removed, so that the outlier cut compares every scan with its own batch. A batch of fewer than
    *min_scans* scans with a value is centred on the median of the whole cohort instead. Returns (centred values,
    {batch: (n scans, medians)})."""
    X = np.asarray(values, dtype=float)
    vector = X.ndim == 1
    X = X[:, None] if vector else X
    batches = np.asarray(batches, dtype=object).astype(str)
    out = np.full_like(X, np.nan)
    with np.errstate(invalid="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)  # all-NaN batches
        overall = np.nanmedian(X, axis=0)
        info = {}
        for b in np.unique(batches):
            rows = batches == b
            n = int(np.isfinite(X[rows]).any(axis=1).sum())
            med = np.nanmedian(X[rows], axis=0) if n >= min_scans else overall
            med = np.where(np.isfinite(med), med, overall)
            out[rows] = X[rows] - med
            info[b] = (n, med if n >= min_scans else None)
    # back on the scale of the values, around the cohort median, so that the scores stay readable
    out = out + overall
    return (out[:, 0] if vector else out), info
