# Response to the round-3 review

We thank the reviewer for the independent re-computation. The two remaining points and the preamble cleanup are done.
Figure, table and section numbers are unchanged (43 pages).

1. **Principal finding 6 vs Fig. 6b and Table A23.**
   - **Computed from our caches.** `realmask_tables.py` now computes per-scan ratios against the age-bin mean from the
     per-pass sums, and they match your values. On HBCD passes hiding less than 5% of the scan (247 of 433):

     | Setting | Ratio to the age-bin mean | Better than the norm on |
     |---|---|---|
     | PPCA + SIREN | 0.901 [0.845, 0.966] | 63% of scans |
     | Transformer | 0.748 | 90% |
     | Released default | 0.760 | 82% |

     Over all in-scope passes, PPCA + SIREN is 0.861 [0.820, 0.902], better on 76% of scans; the transformer is better
     on 98%.
   - **New wording of finding 6.** The population model:
     - gained little on HBCD's real masks: 0.975 within the tool's scope, cell-weighted; per scan 0.861, better than the
       norm in only 76% of scans against 98% for the transformer;
     - was above the norm's cell-weighted error for the smallest masks (1.081), driven by a minority of poorly imputed
       scans;
     - was clearly worse than the norm when most of a scan was hidden.

     The finding closes with "for a large multi-site cohort the transformer is the safer choice".
   - **Section 4.7** gives the per-scan numbers for the smallest masks and for all in-scope passes, and the
     single-tract-donor value (1.201).
2. **The apparent U-shape in Section 4.7.** The text now gives the number of passes behind each class (86, 64 and 16).
   It states that these cell-weighted scores rest on few passes, are dominated by the same heavy tails, and should not
   be read as a U-shaped dependence on load.
3. **`\pending`.** The unused macro definition is removed from the preamble. The PDF compiles cleanly: no errors, no
   undefined references, no overfull lines.

**Author placeholders still open:** these are unchanged from round 2 and are listed in the reply to the editor.
