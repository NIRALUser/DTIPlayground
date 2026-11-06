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

from dtiplayground.dmri.common.age_table import load_batch_table, value_from_table

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


class BatchAssigner:
    """The batch of a scan: its row in the batch table, else group 1 of the pattern, else NO_BATCH."""

    def __init__(self, table=None, regex=None):
        self.table = table or {}
        self.regex = re.compile(regex) if regex else None

    @property
    def active(self):
        return bool(self.table) or self.regex is not None

    def __call__(self, subject, session, text=""):
        batch = value_from_table(subject, session, self.table)
        if batch is None and self.regex is not None:
            m = self.regex.search(str(text))
            if m:
                batch = m.group(1) if m.groups() else m.group(0)
        return NO_BATCH if batch is None else str(batch)


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
