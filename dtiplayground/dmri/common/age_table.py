#
#   common/age_table.py
#
#   Ages of a cohort from a participants / sessions table (CSV or TSV), for the steps that pick something age
#   appropriate when the session name does not carry the age itself (a cohort with sessions named 'ses-V02', ...):
#
#     dmrifiberprofile qc-registration   --age-csv / --age-column / --age-units
#     dmriprep, DTI_Register module      protocol ageCSV / ageColumn / ageUnits (the age bin of the normative model)
#
#   The table gives one age per (subject, session), or one per subject when it has no session column. Ages are kept
#   in months, the unit of the age bins.
#

import csv
import logging

log = logging.getLogger("age-table")

AGE_TABLE_SUBJECT_COLS = ("participant_id", "subject_id", "subject", "sub", "id")
AGE_TABLE_SESSION_COLS = ("session_id", "session", "ses", "visit_id", "visit")
AGE_TABLE_AGE_COLS = ("age_months", "age_month", "age_mo", "age_m", "candidate_age",
                      "age_at_scan", "scan_age", "age")
# fallback when none of the above matches exactly: any column whose name contains
# one of these (HBCD ships e.g. 'candidate_age_months', 'visit_candidate_age')
AGE_TABLE_AGE_SUBSTRINGS = ("candidate_age",)

AGE_UNIT_TO_MONTHS = {"months": 1.0, "years": 12.0, "days": 12.0 / 365.25, "weeks": 12.0 / 52.1775}


def bids_key(value):
    """'sub-1007170889' / 'SUB-1007170889' -> '1007170889' (entity value, lowercased)."""
    v = str(value).strip().lower()
    for pre in ("sub-", "ses-"):
        if v.startswith(pre):
            v = v[len(pre):]
    return v


def load_age_table(path, units="months", age_column=None):
    """{(subject, session|None): age_in_months} from a CSV/TSV participants/sessions table.

    *age_column* names the age column explicitly (case-insensitive); without it
    the column is auto-detected (BIDS ``age`` and common variants, then a
    partial name match on ``candidate_age`` for HBCD-style headers such as
    ``candidate_age_months``).  The subject and session columns are always
    auto-detected (``participant_id`` / ``session_id`` and variants); a table
    without a session column gives one age per subject, applied to all of that
    subject's sessions.
    """
    with open(path, newline="") as fh:
        sample = fh.read(8192)
        fh.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
        except csv.Error:
            dialect = csv.excel_tab if "\t" in sample.splitlines()[0] else csv.excel
        rows = list(csv.DictReader(fh, dialect=dialect))
    if not rows:
        raise ValueError(f"{path} has no data rows")

    have = {c.strip().lower(): c for c in rows[0] if c}

    def pick(cands):
        return next((have[c] for c in cands if c in have), None)

    sub_col, ses_col = pick(AGE_TABLE_SUBJECT_COLS), pick(AGE_TABLE_SESSION_COLS)
    if age_column:  # user-specified column wins over any auto-detection
        age_col = have.get(age_column.strip().lower())
        if age_col is None:
            raise ValueError(f"{path}: no column '{age_column}', found {sorted(have)}")
    else:
        age_col = pick(AGE_TABLE_AGE_COLS)
        if age_col is None:  # no exact hit -> partial match (in column order)
            age_col = next((have[c] for c in have
                            if any(frag in c for frag in AGE_TABLE_AGE_SUBSTRINGS)), None)
            if age_col is not None:
                log.info("no standard age column in %s; using '%s' (partial match on %s)",
                         path, age_col, "/".join(AGE_TABLE_AGE_SUBSTRINGS))
    if sub_col is None:
        raise ValueError(f"{path}: need a subject column "
                         f"({', '.join(AGE_TABLE_SUBJECT_COLS)}), found {sorted(have)}")
    if age_col is None:
        raise ValueError(f"{path}: need an age column "
                         f"({', '.join(AGE_TABLE_AGE_COLS)}, or a name containing "
                         f"{'/'.join(AGE_TABLE_AGE_SUBSTRINGS)}) -- name it explicitly; "
                         f"found {sorted(have)}")
    scale = AGE_UNIT_TO_MONTHS[units]

    table, n_bad = {}, 0
    for r in rows:
        try:
            age = float(str(r[age_col]).strip()) * scale
        except (TypeError, ValueError):  # BIDS 'n/a' and friends
            n_bad += 1
            continue
        key = (bids_key(r[sub_col]), bids_key(r[ses_col]) if ses_col else None)
        table[key] = int(round(age))
    log.info("Age table %s: %d entries from columns (%s, %s, %s in %s)%s",
             path, len(table), sub_col, ses_col or "-", age_col, units,
             f"; {n_bad} row(s) without a usable age" if n_bad else "")
    if not table:
        raise ValueError(f"{path}: no usable ages in column '{age_col}'")
    return table


def age_from_table(subject, session, age_table):
    """Age in months of a scan: the entry of its session, else the one of its subject (a table without a session
    column holds one age per subject). None when neither is there."""
    if not age_table or subject is None:
        return None
    for key in ((bids_key(subject), bids_key(session) if session is not None else None),
                (bids_key(subject), None)):
        if key in age_table:
            return age_table[key]
    return None
