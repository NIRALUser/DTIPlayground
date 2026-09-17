#!/usr/bin/env python3
#
#   make_datasheet.py
#
#   Datasheet (CSV) for EXTRACT_Profile from a reference dataset organized as <subject>/<session>/...: one row per scan,
#   with the case id and one column per image. Each --column is NAME=PATTERN, the pattern a glob relative to the session
#   folder. The first column defines the scans: the case id is taken from its file name with --id-regex (default: the
#   part before '_dwi', e.g. sub-011228_ses-012m_acq-dir79select_dir_run-001). The patterns of the other columns can use
#   {id}; scans without exactly one file for a --column are left out (reported). --optional-column cells are left empty
#   when there is no file (e.g. free water / NODDI maps of single-shell scans); EXTRACT_Profile then doesn't profile that
#   property for the scan.
#
#     python make_datasheet.py /data/DTI_IBISEP_Feb26/ReferenceDataset -o reference.csv \
#         --column "DTI=mask/*_dwi_QCed_tensor.nrrd" \
#         --column "Deformation field=AtlasReg/{id}_dwi_QCed_tensor_DeformedDTI_GlobalDisplacementField.nrrd" \
#         --optional-column "FW DTI=mask/{id}_dwi_QCed_FWtensor.nrrd" \
#         --optional-column "FWF=mask/{id}_dwi_QCed_NODDI_FWF.nii.gz" ...
#

import argparse
import csv
import glob
import os
import re
import sys


def main():
    p = argparse.ArgumentParser(description="Datasheet of a reference dataset for dmrifiberprofile EXTRACT_Profile")
    p.add_argument("reference_dir", help="Reference dataset folder (<subject>/<session>/...)")
    p.add_argument("-o", "--output", required=True, help="Output CSV")
    p.add_argument("--column", action="append", required=True, metavar="NAME=PATTERN",
                   help="Datasheet column and glob relative to the session folder (repeat; the first defines the scans)")
    p.add_argument("--optional-column", action="append", default=[], metavar="NAME=PATTERN",
                   help="Column left empty for scans without a file (repeat)")
    p.add_argument("--id-regex", default=r"^(.+?)_dwi",
                   help="Regex on the file name of the first column; group 1 is the case id (default: part before '_dwi')")
    p.add_argument("--session-glob", default="sub-*/ses-*", help="Session folders under reference_dir (default: sub-*/ses-*)")
    args = p.parse_args()

    columns = []
    for item, optional in [(c, False) for c in args.column] + [(c, True) for c in args.optional_column]:
        name, sep, pattern = item.partition("=")
        if not sep or not name.strip() or not pattern.strip():
            p.error("columns must be NAME=PATTERN: {}".format(item))
        columns.append((name.strip(), pattern.strip(), optional))
    id_regex = re.compile(args.id_regex)

    rows, skipped, empty = [], [], {name: 0 for name, _, optional in columns if optional}
    for session in sorted(glob.glob(os.path.join(args.reference_dir, args.session_glob))):
        if not os.path.isdir(session):
            continue
        first_name, first_pattern, _ = columns[0]
        for path in sorted(glob.glob(os.path.join(session, first_pattern.replace("{id}", "*")))):
            m = id_regex.search(os.path.basename(path))
            case_id = m.group(1) if m else os.path.basename(path).split(".")[0]
            if not re.search(r"ses-\d+m", case_id):
                skipped.append((case_id, "no age (ses-<months>m) in the case id"))
                continue
            row = {"id": case_id, first_name: os.path.abspath(path)}
            for name, pattern, optional in columns[1:]:
                found = sorted(glob.glob(os.path.join(session, pattern.replace("{id}", case_id))))
                if optional and len(found) == 0:
                    row[name] = ""
                    empty[name] += 1
                    continue
                if len(found) != 1:
                    skipped.append((case_id, "{} files for {}".format(len(found), name)))
                    break
                row[name] = os.path.abspath(found[0])
            else:
                rows.append(row)

    ids = [r["id"] for r in rows]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        sys.exit("Case ids are not unique (adapt --id-regex): {}".format(", ".join(duplicates[:10])))
    with open(args.output, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id"] + [name for name, _, _ in columns])
        writer.writeheader()
        writer.writerows(rows)
    for case_id, reason in skipped:
        print("left out {}: {}".format(case_id, reason))
    for name, n in empty.items():
        print("{}: empty for {} scans".format(name, n))
    print("{}: {} scans".format(args.output, len(rows)))


if __name__ == "__main__":
    main()
