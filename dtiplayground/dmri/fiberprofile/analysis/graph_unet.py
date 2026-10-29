#
#   fiberprofile/analysis/graph_unet.py
#
#   Graph U-Net imputation of profile deviations, after CONFETTI (github.com/styner/CONFETTI): a multi-resolution
#   neighbourhood graph over the profile locations (the points of the tract axes) and a hierarchical graph
#   convolutional U-Net. CONFETTI classifies scans (one output per scan); here the network has an output per node
#   and is trained on a normative cohort as a masked autoencoder of the deviations from the norm: observed values are
#   hidden as in the validation (whole profiles, gaps, ends, regions, whole measures) and the network predicts them,
#   with an SD (Gaussian likelihood), from the scan's other values. A scan-wide summary (mean and max over the nodes
#   of the coarsest level) is added there, as the global pooling of the CONFETTI classifier. With --graph-hybrid the
#   prediction of a population model (PPCA) is an input, and the network predicts the correction to it.
#
#   The graph (build_neighborhood_graph.py of CONFETTI): level L keeps every 2**L-th location along each tract (the
#   first and last always, at least 3 per tract); its nodes are linked to their predecessor and successor along the
#   tract and, within a distance threshold, to the closest node of each other tract. The threshold is a multiple of
#   the median distance from a node to the nearest axis point of another tract (default), or, as CONFETTI, to the
#   nearest point of the dense atlas fibers of another tract at the same arc length (--graph-fibers-dir: a larger
#   threshold, 7.7 against 3.6 mm in the validation, and worse imputation). Edge weights exp(-d^2 / sigma^2), sigma
#   the median edge length. Pooling between levels by the kept locations, unpooling by scattering them back, with
#   skip connections.
#

import json
import logging
import os
import time

import numpy as np

log = logging.getLogger("impute")

GRAPH_LEVELS = 4
GRAPH_THRESHOLD_MULTIPLIER = 1.5
GRAPH_ARC_TOLERANCE = 0.5  # mm: fiber points at the same arc length as a node
GRAPH_MIN_POINTS = 3  # per tract and level
GRAPH_FIBER_K = 500
LOGVAR_RANGE = (-6.0, 4.0)


### the graph

def subsample_indices(n, step, min_pts=GRAPH_MIN_POINTS):
    """Local indices kept of a polyline of *n* points: every *step*-th from the first, the last, and midpoints of the
    largest gaps until at least *min_pts* (CONFETTI select_subsample_indices)."""
    if n <= min_pts:
        return list(range(n))
    kept = list(range(0, n, step))
    if kept[-1] != n - 1:
        kept.append(n - 1)
    while len(kept) < min_pts:
        gaps = np.diff(kept)
        i = int(np.argmax(gaps))
        if gaps[i] <= 1:
            break
        kept.insert(i + 1, (kept[i] + kept[i + 1]) // 2)
    return kept


def read_fiber_points(fibers_dir, tracts):
    """(points, tract index, arc length) of the fiber points of *tracts* in *fibers_dir* (<tract>.vtk with stored arc
    lengths, as parametrize-fibers writes them); tracts without a file are left out."""
    import dtiplayground.dmri.common.fibers as fibers
    pts, lab, arc = [], [], []
    for i, tract in enumerate(tracts):
        path = os.path.join(fibers_dir, "{}.vtk".format(tract))
        if not os.path.isfile(path):
            continue
        bundle = fibers.read_fibers(path)
        if fibers.STORED_ARC_LENGTH not in bundle.point_data:
            continue
        a = np.asarray(fibers.stored_arc_lengths(bundle), dtype=np.float64).reshape(-1)
        ok = np.isfinite(a)
        pts.append(np.asarray(bundle.points, dtype=np.float64)[ok])
        arc.append(a[ok])
        lab.append(np.full(ok.sum(), i, dtype=np.int64))
    if not pts:
        return None
    return np.concatenate(pts), np.concatenate(lab), np.concatenate(arc)


def cross_tract_distances(points, labels, arcs, fiber=None, arc_tolerance=GRAPH_ARC_TOLERANCE, k=GRAPH_FIBER_K):
    """Distance from every node to the nearest fiber point of another tract within *arc_tolerance* of its arc length
    (*fiber*: (points, labels, arcs)), or without fibers to the nearest node of another tract; inf where none."""
    from scipy.spatial import cKDTree
    if fiber is None:
        out = np.full(len(points), np.inf)
        for t in np.unique(labels):
            own = labels == t
            d, _ = cKDTree(points[~own]).query(points[own], k=1)
            out[own] = d
        return out
    fp, fl, fa = fiber
    tree = cKDTree(fp)
    k = min(k, len(fp))
    d, idx = tree.query(points, k=k)
    match = (fl[idx] != labels[:, None]) & (np.abs(fa[idx] - arcs[:, None]) <= arc_tolerance)
    out = np.where(match.any(axis=1), d[np.arange(len(points)), np.argmax(match, axis=1)], np.inf)
    for i in np.flatnonzero(~match.any(axis=1)):
        kk = k
        while kk < len(fp):
            kk = min(2 * kk, len(fp))
            di, ii = tree.query(points[i], k=kk)
            m = (fl[ii] != labels[i]) & (np.abs(fa[ii] - arcs[i]) <= arc_tolerance)
            if m.any():
                out[i] = di[m][0]
                break
    return out


def level_adjacency(points, labels, seq, threshold):
    """Undirected edges (i < j) of one level: the sequential pairs *seq* and, from each node, the closest node of each
    other tract within *threshold* (CONFETTI build_adjacency)."""
    from scipy.spatial import cKDTree
    tree = cKDTree(points)
    edges = set(map(tuple, seq))
    for i, cand in enumerate(tree.query_ball_point(points, r=threshold)):
        js = np.asarray([j for j in cand if j != i], dtype=np.int64)
        if not js.size:
            continue
        d2 = ((points[js] - points[i]) ** 2).sum(axis=1)
        seen = {labels[i]}
        for j in js[np.argsort(d2, kind="stable")]:
            if labels[j] in seen:
                continue
            seen.add(labels[j])
            edges.add((min(i, int(j)), max(i, int(j))))
    return np.asarray(sorted(edges), dtype=np.int64).reshape(-1, 2)


class FiberGraph:
    """The multi-resolution graph over the positions of a cohort with a 3-D point (cohort.has_point).

    nodes[L]: positions (cohort indices) of the nodes of level L (level 0: all with a point); edges[L], weights[L]:
    undirected edges and their weights; pool[L]: for each node of level L+1, its row among the nodes of level L."""

    def __init__(self, cohort, levels=GRAPH_LEVELS, fibers_dir=None, multiplier=GRAPH_THRESHOLD_MULTIPLIER):
        t0 = time.time()
        pos = np.flatnonzero(cohort.has_point)
        points, labels, arcs = cohort.points[pos], cohort.tract_of[pos], cohort.arcs[pos]
        fiber = read_fiber_points(fibers_dir, cohort.tracts) if fibers_dir else None
        if fibers_dir and fiber is None:
            log.warning("no fibers with stored arc lengths in %s: the graph threshold is taken from the axes",
                        fibers_dir)
        nearest = cross_tract_distances(points, labels, arcs, fiber)
        self.levels, self.nodes, self.edges, self.weights, self.pool, self.info = levels, [], [], [], [], []
        rows = np.arange(len(pos))
        for L in range(levels):
            keep, seq = [], []
            for t in np.unique(labels):
                own = rows[labels == t]
                own = own[np.argsort(arcs[own], kind="stable")]
                local = [own[i] for i in subsample_indices(len(own), 1 << L)]
                start = len(keep)
                keep += local
                seq += [(start + i, start + i + 1) for i in range(len(local) - 1)]
            keep = np.asarray(keep, dtype=np.int64)
            finite = nearest[keep][np.isfinite(nearest[keep])]
            threshold = multiplier * float(np.median(finite)) if finite.size else 0.0
            e = level_adjacency(points[keep], labels[keep], np.asarray(seq, dtype=np.int64).reshape(-1, 2), threshold)
            d = np.linalg.norm(points[keep][e[:, 0]] - points[keep][e[:, 1]], axis=1) if len(e) else np.zeros(0)
            sigma = float(np.median(d)) if d.size else 1.0
            self.nodes.append(pos[keep])
            self.edges.append(e)
            self.weights.append(np.exp(-d ** 2 / max(sigma ** 2, 1e-9)).astype(np.float32))
            self.info.append({"nodes": int(len(keep)), "edges": int(len(e)), "threshold_mm": round(threshold, 3),
                              "sigma_mm": round(sigma, 3), "degree": round(2 * len(e) / max(len(keep), 1), 2)})
            if L:
                prev = {int(p): i for i, p in enumerate(self.nodes[L - 1])}
                fine = cohort.points[self.nodes[L - 1]]
                mp = np.empty(len(keep), dtype=np.int64)
                for i, p in enumerate(pos[keep]):
                    if int(p) in prev:
                        mp[i] = prev[int(p)]
                    else:  # the minimum points per tract can pick other midpoints at adjacent levels
                        mp[i] = int(np.argmin(((fine - cohort.points[p]) ** 2).sum(axis=1)))
                self.pool.append(mp)
        log.info("Graph (%s, x%g): %s (%.0f s)", "fibers" if fiber is not None else "axes", multiplier, "; ".join(
            "L{} {} nodes, degree {}, {} mm".format(L, i["nodes"], i["degree"], i["threshold_mm"])
            for L, i in enumerate(self.info)), time.time() - t0)


### the network

def normalized_adjacency(n, edges, weights, device):
    """D^-1/2 (A + I) D^-1/2 of a weighted undirected graph as a sparse torch tensor (GCNConv with self loops)."""
    import torch
    i = np.concatenate([edges[:, 0], edges[:, 1], np.arange(n)])
    j = np.concatenate([edges[:, 1], edges[:, 0], np.arange(n)])
    w = np.concatenate([weights, weights, np.ones(n, dtype=np.float32)]).astype(np.float64)
    deg = np.bincount(i, weights=w, minlength=n)
    w = w / np.sqrt(deg[i] * deg[j])
    idx = torch.as_tensor(np.vstack([i, j]), dtype=torch.long, device=device)
    return torch.sparse_coo_tensor(idx, torch.as_tensor(w.astype(np.float32), device=device), (n, n),
                                   check_invariants=False).coalesce()


def build_network(in_dim, out_dim, levels, hidden=128, convs=2, dropout=0.1, global_context=True):
    import torch
    import torch.nn as nn

    class GCNBlock(nn.Module):
        """Graph convolution (A_hat X W) + BatchNorm + ReLU + dropout, on (B, N, F) nodes of one shared graph."""

        def __init__(self, i, o):
            super().__init__()
            self.lin, self.bn = nn.Linear(i, o), nn.BatchNorm1d(o)

        def forward(self, x, a):
            b, n, f = x.shape
            h = self.lin(x)
            h = torch.sparse.mm(a, h.transpose(0, 1).reshape(n, -1)).reshape(n, b, -1).transpose(0, 1)
            h = self.bn(h.reshape(b * n, -1)).reshape(b, n, -1)
            return nn.functional.dropout(torch.relu(h), dropout, self.training)

    class GraphUNet(nn.Module):
        """Encoder (convs blocks per level, pooling by index), decoder (unpooling by scattering, skip connection,
        convs blocks), per-node head: mean and log variance of every metric. *global_context*: the mean and max of
        the coarsest level over the nodes of a scan, added to each of its nodes there (a scan-wide summary, as the
        global pooling of the CONFETTI classifier)."""

        def __init__(self):
            super().__init__()
            self.enc = nn.ModuleList([nn.ModuleList([GCNBlock(in_dim if (L == 0 and c == 0) else hidden, hidden)
                                                     for c in range(convs)]) for L in range(levels)])
            self.dec = nn.ModuleList([nn.ModuleList([GCNBlock(2 * hidden if c == 0 else hidden, hidden)
                                                     for c in range(convs)]) for _ in range(levels - 1)])
            self.head = nn.Linear(hidden + in_dim, 2 * out_dim)
            self.glob = nn.Sequential(nn.Linear(2 * hidden, hidden), nn.ReLU(), nn.Linear(hidden, hidden)) \
                if global_context else None

        def forward(self, x0, adj, pool):
            x, skips = x0, []
            for L in range(levels):
                for blk in self.enc[L]:
                    x = blk(x, adj[L])
                if L == levels - 1 and self.glob is not None:
                    x = x + self.glob(torch.cat([x.mean(dim=1), x.amax(dim=1)], dim=-1))[:, None]
                skips.append(x)
                if L < levels - 1:
                    x = x[:, pool[L]]
            for L in range(levels - 2, -1, -1):
                up = x.new_zeros(x.shape[0], skips[L].shape[1], x.shape[2])
                up[:, pool[L]] = x
                x = torch.cat([up, skips[L]], dim=-1)
                for blk in self.dec[L]:
                    x = blk(x, adj[L])
            out = self.head(torch.cat([x, x0], dim=-1))
            m = out.shape[-1] // 2
            return out[..., :m], out[..., m:].clamp(*LOGVAR_RANGE)

    return GraphUNet()


def sparse_device(device):
    """The device for the graph's sparse products: the CPU instead of mps (no sparse tensors there)."""
    if str(device) == "mps":
        log.info("graph-unet: the sparse graph products run on the CPU instead of mps")
        return "cpu"
    return device


### the population prediction as an input (hybrid)

class BatchPPCA:
    """A probabilistic PCA of the deviations (fit_ppca of impute_profiles) whose posterior is computed for a batch
    of scans at once on the GPU: the population prediction the hybrid Graph U-Net corrects."""

    def __init__(self, mu, W, psi, cells, shape, device):
        import torch
        self.cells, self.shape, self.device = cells, shape, device
        self.mu = torch.as_tensor(mu, dtype=torch.float32, device=device)
        self.W = torch.as_tensor(W, dtype=torch.float32, device=device)
        self.psi = torch.as_tensor(psi, dtype=torch.float32, device=device)

    @classmethod
    def fit(cls, Zflat, rows, cells, shape, q=80, device="cuda", max_iter=300):
        """Fit on the rows *rows* of *Zflat* (scans x positions*metrics, NaN missing), the cells *cells*."""
        from dtiplayground.dmri.fiberprofile.analysis.impute_profiles import fit_ppca
        Zk = Zflat[np.ix_(rows, cells)]
        Zk = Zk[(~np.isnan(Zk)).any(axis=1)]
        mu, W, psi, _ = fit_ppca(Zk, q, "isotropic", None, max_iter, 1e-6, device)
        return cls(mu, W, psi, cells, shape, device)

    def posterior(self, Z):
        """Posterior mean and SD (scans x positions x metrics, NaN outside the model) of deviations *Z* (scans x
        positions x metrics, NaN missing)."""
        import torch
        B = len(Z)
        z = torch.as_tensor(Z.reshape(B, -1)[:, self.cells], dtype=torch.float32, device=self.device)
        o = ~torch.isnan(z)
        r = torch.where(o, z - self.mu, torch.zeros_like(z)) / self.psi
        Wo = self.W[None] * (o.float() / self.psi)[..., None]  # B x cells x q
        q = self.W.shape[1]
        A = torch.eye(q, device=self.device)[None] + torch.einsum("bcq,cr->bqr", Wo, self.W)
        Sigma = torch.linalg.inv(A)
        x = torch.einsum("bqr,br->bq", Sigma, torch.einsum("cq,bc->bq", self.W, r))
        mean = self.mu + x @ self.W.T
        var = self.psi + (torch.einsum("cq,bqr->bcr", self.W, Sigma) * self.W[None]).sum(-1)
        out_m = np.full((B, int(np.prod(self.shape))), np.nan, dtype=np.float32)
        out_s = np.full_like(out_m, np.nan)
        out_m[:, self.cells] = mean.cpu().numpy()
        out_s[:, self.cells] = torch.sqrt(var).cpu().numpy()
        return out_m.reshape((B,) + tuple(self.shape)), out_s.reshape((B,) + tuple(self.shape))


### the model

class GraphUNetModel:
    """A Graph U-Net of the deviations of a normative cohort from the norm (positions x metrics), as the population
    model: impute(Y, norm) gives the values and SDs of every cell of a scan from its observed values."""

    method = "graph-unet"

    def __init__(self, graph, net, n_metrics, scale, info, device):
        self.graph, self.net, self.n_metrics, self.scale, self.info, self.device = graph, net, n_metrics, scale, info, \
            device
        self._adj = None

    @staticmethod
    def features(graph, cohort, Z, pop=None):
        """Node features of deviations *Z* (scans x positions x metrics, NaN missing): the deviations (0 where
        missing), the observed mask, the 3-D position and the arc length (standardized); with *pop* (mean, SD of the
        population prediction, same shape) also those (0 and 1 outside the model)."""
        nodes = graph.nodes[0]
        z = Z[:, nodes]
        obs = ~np.isnan(z)
        extra = []
        if pop is not None:
            pm, ps = pop[0][:, nodes], pop[1][:, nodes]
            extra = [np.nan_to_num(pm), np.log(np.nan_to_num(ps, nan=1.0).clip(1e-3))]
        pts = cohort.points[nodes]
        pts = (pts - pts.mean(axis=0)) / pts.std(axis=0).clip(1e-6)
        arc = cohort.arcs[nodes]
        arc = ((arc - arc.mean()) / max(arc.std(), 1e-6))[:, None]
        static = np.broadcast_to(np.concatenate([pts, arc], axis=1), (len(Z), len(nodes), 4))
        return np.concatenate([np.where(obs, z, 0.0), obs, static] + extra, axis=2).astype(np.float32)

    @classmethod
    def fit(cls, cohort, prior, scans, graph, masker, levels=GRAPH_LEVELS, hidden=128, convs=2, epochs=200,
            batch=16, lr=1e-3, seed=0, device="cuda", holdout=0.1, visible_weight=0.1, global_context=True,
            hybrid=0, ppca_folds=5, min_scans=10):
        """Train on the deviations of *scans* from the norm of their age bin (*prior*): each epoch hides observed
        values of every scan (*masker*(Y, rng) -> boolean positions x metrics) and fits their mean and log variance
        (Gaussian likelihood; the visible values with *visible_weight*). A share *holdout* of the subjects, with fixed
        hidden values, picks the epoch and calibrates the SDs per metric. *hybrid* > 0: the population prediction
        (a PPCA with that many components) is an input and the network predicts the correction to it; a training scan
        gets it from a PPCA fitted without its subject (*ppca_folds*), as an unseen scan would; its cells are those
        observed in at least *min_scans* training scans."""
        import torch
        from dtiplayground.dmri.fiberprofile.analysis.impute_profiles import subject_of
        t0 = time.time()
        device = sparse_device(device)
        rng = np.random.default_rng(seed)
        torch.manual_seed(seed)
        Z = np.full((len(scans), cohort.n_positions, len(cohort.metrics)), np.nan, dtype=np.float32)
        for i, s in enumerate(scans):
            nrm = prior.norm(s)
            if nrm is not None:
                Z[i] = (cohort.scan(s) - nrm[0]) / nrm[1]
        Z = np.where(cohort.valid[None], Z, np.nan)
        subjects = sorted({subject_of(cohort.scans[s]) for s in scans})
        rng.shuffle(subjects)
        held = set(subjects[:max(1, int(round(holdout * len(subjects))))])
        is_held = np.asarray([subject_of(cohort.scans[s]) in held for s in scans])
        tr, ho = np.flatnonzero(~is_held), np.flatnonzero(is_held)
        nodes = graph.nodes[0]
        M = len(cohort.metrics)
        in_dim = (4 if hybrid else 2) * M + 4
        ppca_of = None
        if hybrid:
            Zf = Z.reshape(len(scans), -1)
            cells = np.flatnonzero(cohort.valid.reshape(-1) & ((~np.isnan(Zf[tr])).sum(axis=0) >= min_scans))
            if not len(cells):
                raise ValueError("graph-unet: no cell observed in {} training scans (--min-scans) for its population "
                                 "model".format(min_scans))
            shape = cohort.valid.shape
            full = BatchPPCA.fit(Zf, tr, cells, shape, hybrid, device)
            subj_tr = np.asarray([subject_of(cohort.scans[scans[i]]) for i in tr])
            us = np.unique(subj_tr)
            fold_of = {u: k % ppca_folds for k, u in enumerate(np.random.default_rng(seed).permutation(us))}
            ppca_of = [full] * len(scans)
            for k in range(ppca_folds):
                inner = tr[np.asarray([fold_of[u] for u in subj_tr]) != k]
                pk = BatchPPCA.fit(Zf, inner, cells, shape, hybrid, device)
                for i in tr[np.asarray([fold_of[u] for u in subj_tr]) == k]:
                    ppca_of[i] = pk
            log.info("  graph-unet hybrid: population prediction of %d components, %d folds (%.0f s)", hybrid,
                     ppca_folds, time.time() - t0)

        def pop_of(idx, Zm):
            if ppca_of is None:
                return None
            pm = np.full(Zm.shape, np.nan, dtype=np.float32)
            ps = np.full(Zm.shape, np.nan, dtype=np.float32)
            for mdl in {id(ppca_of[i]): ppca_of[i] for i in idx}.values():
                sel = [k for k, i in enumerate(idx) if ppca_of[i] is mdl]
                pm[sel], ps[sel] = mdl.posterior(Zm[sel])
            return pm, ps
        net = build_network(in_dim, M, levels, hidden, convs, global_context=global_context).to(device)
        adj = [normalized_adjacency(len(graph.nodes[L]), graph.edges[L], graph.weights[L], device)
               for L in range(levels)]
        pool = [torch.as_tensor(p, device=device) for p in graph.pool[:levels - 1]]
        opt = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=1e-4)
        sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, epochs)

        def masked(idx, r):
            Zm, hid = Z[idx].copy(), np.zeros((len(idx), len(nodes), M), dtype=bool)
            for k, i in enumerate(idx):
                h = masker(Z[i], r) & ~np.isnan(Z[i])
                Zm[k][h] = np.nan
                hid[k] = h[nodes]
            return Zm, hid

        def loss_of(idx, Zm, hid, pop=None):
            pop = pop_of(idx, Zm) if pop is None else pop
            x = torch.as_tensor(cls.features(graph, cohort, Zm, pop), device=device)
            mean, logvar = net(x, adj, pool)
            if pop is not None:
                mean = mean + torch.as_tensor(np.nan_to_num(pop[0][:, nodes]), device=device)
            target = torch.as_tensor(np.nan_to_num(Z[idx][:, nodes]), device=device)
            obs = torch.as_tensor(~np.isnan(Z[idx][:, nodes]), device=device)
            h = torch.as_tensor(hid, device=device)
            nll = 0.5 * (logvar + (mean - target) ** 2 * torch.exp(-logvar))
            w = torch.where(h, 1.0, visible_weight) * obs
            return (nll * w).sum() / w.sum().clamp(min=1.0), mean, logvar

        hr = np.random.default_rng(seed + 1)
        Zh, hid_h = masked(ho, hr)
        pop_h = pop_of(ho, Zh)
        hb = lambda b: None if pop_h is None else (pop_h[0][b:b + batch], pop_h[1][b:b + batch])
        best, best_state, history = np.inf, None, []
        for epoch in range(epochs):
            net.train()
            order = rng.permutation(tr)
            for b in range(0, len(order), batch):
                idx = order[b:b + batch]
                if len(idx) < 2:
                    continue
                Zm, hid = masked(idx, rng)
                loss, _, _ = loss_of(idx, Zm, hid)
                opt.zero_grad()
                loss.backward()
                opt.step()
            sched.step()
            net.eval()
            with torch.no_grad():
                vl = float(np.mean([loss_of(ho[b:b + batch], Zh[b:b + batch], hid_h[b:b + batch], hb(b))[0].item()
                                    for b in range(0, len(ho), batch)]))
            history.append(vl)
            if vl < best:
                best, best_state, best_epoch = vl, {k: v.detach().clone() for k, v in net.state_dict().items()}, epoch
        net.load_state_dict(best_state)
        net.eval()
        # SDs calibrated per metric on the hidden values of the held-out subjects
        num, den = np.zeros(M), np.zeros(M)
        with torch.no_grad():
            for b in range(0, len(ho), batch):
                idx = ho[b:b + batch]
                _, mean, logvar = loss_of(idx, Zh[b:b + batch], hid_h[b:b + batch], hb(b))
                zt = Z[idx][:, nodes]
                r2 = (mean.cpu().numpy() - zt) ** 2 / np.exp(logvar.cpu().numpy())
                h = hid_h[b:b + batch] & ~np.isnan(zt)
                num += np.where(h, r2, 0.0).sum(axis=(0, 1))
                den += h.sum(axis=(0, 1))
        scale = np.sqrt(np.where(den > 0, num / np.maximum(den, 1), 1.0))
        info = {"levels": levels, "hidden": hidden, "convs": convs, "global": global_context, "hybrid": hybrid,
                "epochs": epochs, "best_epoch": int(best_epoch),
                "holdout_loss": round(best, 4), "train_scans": int(len(tr)), "holdout_scans": int(len(ho)),
                "sd_scale": {cohort.metrics[m]: round(float(scale[m]), 3) for m in range(M)},
                "seconds": round(time.time() - t0, 1)}
        log.info("  graph-unet L%d h%d x%d: %d scans, best epoch %d of %d, held-out NLL %.3f, SD scale %s (%.0f s)",
                 levels, hidden, convs, len(tr), best_epoch + 1, epochs, best, " ".join(
                     "{} {:.2f}".format(cohort.metrics[m], scale[m]) for m in range(M)), time.time() - t0)
        model = cls(graph, net, M, scale, info, device)
        model._adj, model._pool, model._cohort = adj, pool, cohort
        model._ppca = full if hybrid else None
        return model

    def predict(self, z, crossfit=5):
        """Mean and SD (positions x metrics, NaN off the graph) of the deviations of a scan from its observed ones
        *z* (positions x metrics, NaN missing). The missing cells are predicted from all observed ones. With
        *crossfit* > 1 the observed cells are predicted too, without their own values: the tracts are split into that
        many groups, and each group is predicted with its observed values hidden (as whole profiles), so the
        residuals of the observed values (e.g. imputed by SIREN, --norm population) are those of a prediction."""
        import torch
        cohort = self._cohort
        nodes = self.graph.nodes[0]
        passes = [z]
        groups = []
        if crossfit and crossfit > 1:
            tracts = np.unique(cohort.tract_of)
            order = np.random.default_rng(0).permutation(tracts)
            for k in range(crossfit):
                g = np.isin(cohort.tract_of, order[k::crossfit])
                zk = z.copy()
                zk[g] = np.nan
                passes.append(zk)
                groups.append(g)
        Zp = np.stack(passes).astype(np.float32)
        pop = None if self._ppca is None else self._ppca.posterior(Zp)
        x = torch.as_tensor(self.features(self.graph, cohort, Zp, pop), device=self.device)
        with torch.no_grad():
            mean, logvar = self.net(x, self._adj, self._pool)
            if pop is not None:
                mean = mean + torch.as_tensor(np.nan_to_num(pop[0][:, nodes]), device=self.device)
        mean, sd = mean.cpu().numpy(), np.exp(0.5 * logvar.cpu().numpy()) * self.scale[None, None]
        out_m, out_s = np.full((len(passes),) + z.shape, np.nan), np.full((len(passes),) + z.shape, np.nan)
        out_m[:, nodes], out_s[:, nodes] = mean, sd
        m, s = out_m[0], out_s[0]
        obs = ~np.isnan(z)
        for k, g in enumerate(groups, 1):
            sel = obs & g[:, None]
            m[sel], s[sel] = out_m[k][sel], out_s[k][sel]
        valid = cohort.valid
        return np.where(valid, m, np.nan), np.where(valid, s, np.nan)

    def impute(self, Y, norm):
        """(values, SDs) of every cell of a scan with values *Y* and the norm (mean, SD) of its age bin."""
        zm, zsd = self.predict((Y - norm[0]) / norm[1])
        return norm[0] + zm * norm[1], zsd * norm[1]

    def save(self, path):
        """The network, its graph, the SD calibration and the population model of a hybrid, with the tracts, arc
        lengths and metrics it was fitted on (torch .pt, tensors, lists and plain numbers only, so that it loads with
        weights_only). The norm is not saved: it is that of the run using it."""
        import torch
        c, g, ppca = self._cohort, self.graph, self._ppca
        t = lambda a: torch.as_tensor(np.ascontiguousarray(a))
        plain = lambda d: json.loads(json.dumps(d, default=float))  # numpy numbers -> Python ones
        torch.save({"state": {k: v.cpu() for k, v in self.net.state_dict().items()}, "info": plain(self.info),
                    "scale": t(self.scale),
                    "config": plain({k: self.info[k] for k in ("levels", "hidden", "convs", "global", "hybrid")}),
                    "tracts": [str(x) for x in np.asarray(c.tracts)[c.tract_of]], "arcs": t(c.arcs),
                    "metrics": list(c.metrics),
                    "graph": {"nodes": [t(a) for a in g.nodes], "edges": [t(a) for a in g.edges],
                              "weights": [t(a) for a in g.weights], "pool": [t(a) for a in g.pool],
                              "info": plain(g.info), "levels": int(g.levels)},
                    "ppca": None if ppca is None else {"mu": ppca.mu.cpu(), "W": ppca.W.cpu(), "psi": ppca.psi.cpu(),
                                                       "cells": t(ppca.cells), "shape": [int(x) for x in ppca.shape]}},
                   path)

    @classmethod
    def load(cls, path, cohort, device="auto"):
        """A saved network for *cohort*, which must have its tracts, arc lengths (positions) and metrics."""
        import torch
        from dtiplayground.dmri.fiberprofile.analysis.impute_profiles import pick_device
        device = sparse_device(pick_device(device))
        d = torch.load(path, map_location="cpu", weights_only=True)  # tensors and plain values only, no code
        arcs = d["arcs"].numpy()
        tracts = np.asarray(cohort.tracts)[cohort.tract_of]
        if len(arcs) != cohort.n_positions or not (np.asarray(d["tracts"]) == tracts).all() or \
                not np.allclose(arcs, cohort.arcs) or list(d["metrics"]) != list(cohort.metrics):
            raise ValueError("the graph U-Net {} was fitted on other tracts, arc lengths or metrics than the "
                             "profiles".format(path))
        graph = FiberGraph.__new__(FiberGraph)
        gd = d["graph"]
        graph.nodes, graph.edges = [a.numpy() for a in gd["nodes"]], [a.numpy() for a in gd["edges"]]
        graph.weights, graph.pool = [a.numpy() for a in gd["weights"]], [a.numpy() for a in gd["pool"]]
        graph.info, graph.levels = gd["info"], gd["levels"]
        if cohort.points is None or not cohort.has_point[graph.nodes[0]].all():
            raise ValueError("the graph U-Net {} needs the axes of all its tracts (--axis-dir)".format(path))
        cfg = d["config"]
        M = len(cohort.metrics)
        net = build_network((4 if cfg["hybrid"] else 2) * M + 4, M, cfg["levels"], cfg["hidden"], cfg["convs"],
                            global_context=cfg["global"]).to(device)
        net.load_state_dict(d["state"])
        net.eval()
        model = cls(graph, net, M, d["scale"].numpy(), d["info"], device)
        L = cfg["levels"]
        model._adj = [normalized_adjacency(len(graph.nodes[i]), graph.edges[i], graph.weights[i], device)
                      for i in range(L)]
        model._pool = [torch.as_tensor(p, device=device) for p in graph.pool[:L - 1]]
        model._cohort = cohort
        pp = d["ppca"]
        model._ppca = None if pp is None else BatchPPCA(pp["mu"].numpy(), pp["W"].numpy(), pp["psi"].numpy(),
                                                        pp["cells"].numpy(), tuple(pp["shape"]), device)
        return model


def describe(info):
    """One line of the settings and fit of a model (its info)."""
    return "{} levels, {} features x {} convolutions{}, fitted on {} scans (best epoch {} of {})".format(
        info["levels"], info["hidden"], info["convs"],
        ", on the population prediction of {} components".format(info["hybrid"]) if info.get("hybrid") else "",
        info["train_scans"], info["best_epoch"] + 1, info["epochs"])
