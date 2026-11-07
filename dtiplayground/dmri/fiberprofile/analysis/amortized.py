#
#   fiberprofile/analysis/amortized.py
#
#   Amortized models of the profile deviations (phase 6): networks that read a scan's observed deviations directly,
#   as the graph U-Net (graph_unet.py) does, trained on a normative cohort to predict hidden values (the validation
#   patterns) with a mean and a log variance per cell:
#
#     vae          a partial-observation VAE (Ma et al. 2019, EDDI; MIWAE, Mattei & Frellsen 2019): a set encoder of
#                  the observed cells (a per-location MLP of the inputs, the values and their mask, pooled by mean and
#                  max) gives the posterior of a latent; the decoder maps the latent through hidden layers to a last
#                  layer with weights per location (a nonlinear relative of the population model's loadings).
#                  Trained on the evidence lower bound with importance samples (iwae > 1); predicts at the posterior
#                  mean.
#     transformer  a masked autoencoder over location tokens: each tract is cut into patches of consecutive locations,
#                  a token holds a patch's values and mask, its tract and its position; global self-attention over all
#                  tokens of a scan, a per-location head.
#
#   With *hybrid* the prediction of a population model (PPCA, cross-fitted by subject for the training scans) and its
#   log SD are inputs, and the network predicts the correction to it. *inputs* adds per-location inputs: dist (the
#   distance to the nearest observed location of each metric, log(1 + d / 4 mm)), and the context of the scan, the
#   same at every location: age (log age, standardized), acq (one-hot acquisition, ACQ_REGEX in the scan name), batch
#   (one-hot cohort). *members* networks trained with different seeds are averaged.
#

import logging
import math
import time

import numpy as np

from dtiplayground.dmri.fiberprofile.analysis.graph_unet import BatchPPCA, LOGVAR_RANGE

log = logging.getLogger("impute")

INPUTS = ("dist", "age", "acq", "batch")
DIST_CAP = 50.0  # mm: the distance input of a metric no location observes


### networks

def build_vae(n_loc, n_in, M, latent=64, hidden=256, depth=2):
    """Partial VAE: per-location inputs (n_loc x n_in, the observed values and mask included) -> latent posterior
    -> mean and log variance of every location and metric (n_loc x M)."""
    import torch
    import torch.nn as nn

    class PartialVAE(nn.Module):
        def __init__(self):
            super().__init__()
            self.point = nn.Sequential(nn.Linear(n_in, hidden), nn.ReLU(), nn.Linear(hidden, hidden), nn.ReLU())
            self.post = nn.Sequential(nn.Linear(2 * hidden, hidden), nn.ReLU(), nn.Linear(hidden, 2 * latent))
            layers, d = [], latent
            for _ in range(depth):
                layers += [nn.Linear(d, hidden), nn.ReLU()]
                d = hidden
            self.dec = nn.Sequential(*layers)
            self.out = nn.Linear(hidden + latent, n_loc * 2 * M)  # weights per location: linear in z, and nonlinear
            with torch.no_grad():
                self.out.weight.mul_(0.1)
                self.out.bias.zero_()

        def encode(self, x, seen):
            h = self.point(x)
            mean = (h * seen).sum(dim=1) / seen.sum(dim=1).clamp(min=1.0)
            mx = torch.where(seen > 0, h, torch.full_like(h, -1e4)).amax(dim=1)
            mu, logv = self.post(torch.cat([mean, mx], dim=-1)).chunk(2, dim=-1)
            return mu, logv.clamp(-8.0, 4.0)

        def decode(self, z):
            out = self.out(torch.cat([self.dec(z), z], dim=-1)).view(*z.shape[:-1], n_loc, 2 * M)
            return out[..., :M], out[..., M:].clamp(*LOGVAR_RANGE)

    return PartialVAE()


def build_transformer(n_in_loc, M, patches, n_tracts, d_model=128, layers=4, heads=4):
    """Masked-autoencoder transformer: *patches* (n_tokens x P, location index or -1) group consecutive locations of
    a tract; a token embeds its locations' inputs (P x n_in_loc), its tract and its mean position."""
    import torch
    import torch.nn as nn
    n_tok, P = patches.shape

    class ProfileTransformer(nn.Module):
        def __init__(self):
            super().__init__()
            self.idx = torch.as_tensor(np.where(patches >= 0, patches, 0))
            self.valid = torch.as_tensor(patches >= 0)
            self.embed = nn.Linear(P * n_in_loc, d_model)
            self.tract = nn.Embedding(n_tracts, d_model)
            layer = nn.TransformerEncoderLayer(d_model, heads, 4 * d_model, dropout=0.1, batch_first=True,
                                               norm_first=True)
            self.encoder = nn.TransformerEncoder(layer, layers, enable_nested_tensor=False)
            self.head = nn.Linear(d_model, P * 2 * M)

        def forward(self, x, tract_of_token):
            B, N, F = x.shape
            idx, valid = self.idx.to(x.device), self.valid.to(x.device)
            tok = x[:, idx.reshape(-1)].view(B, n_tok, P, F) * valid[None, :, :, None]
            h = self.embed(tok.reshape(B, n_tok, P * F)) + self.tract(tract_of_token)[None]
            h = self.encoder(h)
            out = self.head(h).view(B, n_tok, P, 2 * M)
            full = x.new_zeros(B, N, 2 * M)
            sel = valid.reshape(-1)
            full[:, idx.reshape(-1)[sel]] = out.reshape(B, n_tok * P, 2 * M)[:, sel]
            return full[..., :M], full[..., M:].clamp(*LOGVAR_RANGE)

    return ProfileTransformer()


def tract_patches(cohort, pos, size=8):
    """Patches of *size* consecutive locations (along the arc length) of every tract: (tokens x size) indices into
    *pos* (-1: padding), and the tract of every token."""
    rows, tracts = [], []
    at = {int(p): i for i, p in enumerate(pos)}
    for t in np.unique(cohort.tract_of[pos]):
        own = [p for p in pos if cohort.tract_of[p] == t]
        own.sort(key=lambda p: cohort.arcs[p])
        for a in range(0, len(own), size):
            chunk = [at[int(p)] for p in own[a:a + size]]
            rows.append(chunk + [-1] * (size - len(chunk)))
            tracts.append(int(t))
    return np.asarray(rows, dtype=np.int64), np.asarray(tracts, dtype=np.int64)


### the model

class AmortizedModel:
    """A vae or transformer of the deviations of a normative cohort (as the population model: impute(Y, norm))."""

    def __init__(self, kind, net, cfg, scale, info, device):
        self.kind, self.cfg, self.scale, self.info, self.device = kind, cfg, scale, info, device
        self.nets = [] if net is None else (list(net) if isinstance(net, (list, tuple)) else [net])
        self.method = kind
        self._cohort = self._pos = self._static = self._ppca = self._tok_tract = self._D = None
        self._index = None
        self.ensemble_table = None  # --ensemble-weights fit: the weights fitted with this model

    def bind(self, cohort):
        """Predict the scans of another cohort on the same locations (tracts, arc lengths, axes)."""
        self._cohort, self._index = cohort, None

    @property
    def net(self):
        return self.nets[0] if self.nets else None

    @property
    def inputs(self):
        return [x for x in str(self.cfg.get("inputs", "")).replace("+", ",").split(",") if x]

    @property
    def needs_age(self):
        return bool(set(self.inputs) & {"age", "acq", "batch"})

    def n_in(self, M):
        ctx = self.cfg.get("context") or {}
        return (3 + 2 * M + (2 * M if self.cfg["hybrid"] else 0) + (M if "dist" in self.inputs else 0)
                + ("age" in self.inputs) + len(ctx.get("acq", [])) * ("acq" in self.inputs)
                + len(ctx.get("batch", [])) * ("batch" in self.inputs))

    def context_of(self, age, scan):
        """The context inputs of a scan (its age in months and its index or name in the cohort)."""
        import re
        from dtiplayground.dmri.fiberprofile.analysis.impute_profiles import ACQ_REGEX
        ctx, cohort, out = self.cfg.get("context") or {}, self._cohort, []
        if isinstance(scan, str):
            if self._index is None:
                self._index = {n: i for i, n in enumerate(cohort.scans)}
            scan = self._index.get(scan)
        name = "" if scan is None else cohort.scans[scan]
        if "age" in self.inputs:
            a = ctx["age"]
            out.append(0.0 if age is None else (np.log(max(float(age), 0.0) + 1.0) - a[0]) / a[1])
        if "acq" in self.inputs:
            m = re.search(ACQ_REGEX, name)
            out += [float(m is not None and m.group(1) == x) for x in ctx["acq"]]
        if "batch" in self.inputs:
            b = None if scan is None else cohort.batches[cohort.scan_batch[scan]]
            out += [float(b == x) for x in ctx["batch"]]
        return np.asarray(out, dtype=np.float32)

    def distances(self, obs):
        """log(1 + d / 4 mm) of every location to the nearest observed location of each metric (obs: B x n x M)."""
        import torch
        if self._D is None:
            p = torch.as_tensor(self._cohort.points[self._pos], dtype=torch.float32, device=self.device)
            self._D = torch.cdist(p, p)
        D = self._D
        o = torch.as_tensor(obs, device=self.device)
        out = torch.empty(o.shape, dtype=torch.float32, device=self.device)
        inf = torch.tensor(float("inf"), device=self.device)
        for b in range(o.shape[0]):
            for m in range(o.shape[2]):
                out[b, :, m] = torch.where(o[b, :, m][None, :], D, inf).amin(dim=1)
        out = torch.log1p(out.clamp(max=DIST_CAP) / 4.0)
        return out.cpu().numpy()

    @staticmethod
    def static_inputs(cohort):
        pos = np.flatnonzero(cohort.has_point)
        pts = cohort.points[pos]
        lo, hi = pts.min(axis=0), pts.max(axis=0)
        xyz = 2.0 * (pts - lo) / np.maximum(hi - lo, 1e-6) - 1.0
        return pos, xyz.astype(np.float32)

    def features(self, Zm, pop=None, ctx=None):
        """Per-location inputs of masked deviations: position, the values (0 where missing), the mask, with a
        population prediction its mean and log SD, the distances to the observed locations (dist) and the context
        rows *ctx* (B x C)."""
        pos = self._pos
        z = Zm[:, pos]
        obs = ~np.isnan(z)
        cols = [np.broadcast_to(self._static, (len(Zm),) + self._static.shape), np.where(obs, z, 0.0), obs]
        if pop is not None:
            cols += [np.nan_to_num(pop[0][:, pos]), np.log(np.nan_to_num(pop[1][:, pos], nan=1.0).clip(1e-3))]
        if "dist" in self.inputs:
            cols.append(self.distances(obs))
        if ctx is not None and ctx.shape[1]:
            cols.append(np.broadcast_to(ctx[:, None, :], (len(Zm), len(pos), ctx.shape[1])))
        return np.concatenate(cols, axis=2).astype(np.float32), obs

    def forward(self, x, obs, sample=False, k=1, net=None):
        """(mean, log variance, KL) of a batch; the vae draws *k* latents with *sample*, else uses the posterior
        mean. Without *net*: the average of the members (mean of the means, mean of the variances plus the variance
        of the means)."""
        import torch
        if net is None and len(self.nets) > 1:
            outs = [self.forward(x, obs, sample, k, n)[:2] for n in self.nets]
            means = torch.stack([o[0] for o in outs])
            var = torch.stack([torch.exp(o[1]) for o in outs]).mean(0) + means.var(0, unbiased=False)
            return means.mean(0), torch.log(var), None, None
        net = self.nets[0] if net is None else net
        if self.kind == "transformer":
            mean, logvar = net(x, self._tok_tract)
            return mean[None], logvar[None], None, None
        seen = torch.as_tensor(obs.any(axis=2, keepdims=True), dtype=torch.float32, device=x.device)
        mu, logv = net.encode(x, seen)
        if sample:
            eps = torch.randn((k,) + mu.shape, device=x.device)
            z = mu[None] + torch.exp(0.5 * logv)[None] * eps
        else:
            z = mu[None]
        mean, logvar = net.decode(z)
        return mean, logvar, (mu, logv), z

    @classmethod
    def fit(cls, cohort, prior, scans, masker, kind="vae", hybrid=0, latent=64, hidden=256, depth=2, iwae=5,
            beta=1.0, patch=8, d_model=128, layers=4, heads=4, epochs=60, batch=16, lr=1e-3, seed=0, device="cuda",
            holdout=0.1, visible_weight=0.1, ppca_folds=5, min_scans=10, inputs="", members=1, ages=None):
        import torch
        from dtiplayground.dmri.fiberprofile.analysis.impute_profiles import subject_of
        t0 = time.time()
        if str(device) == "mps":
            device = "cpu"
        rng = np.random.default_rng(seed)
        torch.manual_seed(seed)
        M = len(cohort.metrics)
        Z = np.full((len(scans), cohort.n_positions, M), np.nan, dtype=np.float32)
        for i, s in enumerate(scans):
            nrm = prior.norm(s)
            if nrm is not None:
                Z[i] = (cohort.scan(s) - nrm[0]) / nrm[1]
        Z = np.where(cohort.valid[None], Z, np.nan)
        inputs = ",".join(x for x in str(inputs or "").replace("+", ",").split(",") if x)
        bad = [x for x in inputs.split(",") if x and x not in INPUTS]
        if bad:
            raise ValueError("unknown {} inputs {} ({})".format(kind, ",".join(bad), ", ".join(INPUTS)))
        cfg = {"kind": kind, "hybrid": int(hybrid), "latent": latent, "hidden": hidden, "depth": depth,
               "iwae": iwae, "beta": beta, "patch": patch, "d_model": d_model, "layers": layers, "heads": heads,
               "inputs": inputs, "members": int(members)}
        if set(inputs.split(",")) & {"age", "acq", "batch"}:
            import re
            from collections import Counter
            from dtiplayground.dmri.fiberprofile.analysis.impute_profiles import ACQ_REGEX
            la = np.log(np.maximum([0.0 if ages is None or ages[s] is None else float(ages[s]) for s in scans], 0)
                        + 1.0)
            acq = Counter(m.group(1) for m in (re.search(ACQ_REGEX, cohort.scans[s]) for s in scans) if m)
            cfg["context"] = {"age": [float(la.mean()), float(max(la.std(), 1e-3))],
                              "acq": sorted(a for a, n in acq.items() if n >= 5),
                              "batch": list(cohort.batches) if len(cohort.batches) > 1 else []}
        subjects = sorted({subject_of(cohort.scans[s]) for s in scans})
        rng.shuffle(subjects)
        held = set(subjects[:max(1, int(round(holdout * len(subjects))))])
        is_held = np.asarray([subject_of(cohort.scans[s]) in held for s in scans])
        tr, ho = np.flatnonzero(~is_held), np.flatnonzero(is_held)
        ppca_of, full = None, None
        if hybrid:
            Zf = Z.reshape(len(scans), -1)
            cells = np.flatnonzero(cohort.valid.reshape(-1) & ((~np.isnan(Zf[tr])).sum(axis=0) >= min_scans))
            if not len(cells):
                raise ValueError("{}: no cell observed in {} training scans (--min-scans)".format(kind, min_scans))
            full = BatchPPCA.fit(Zf, tr, cells, cohort.valid.shape, hybrid, device)
            subj_tr = np.asarray([subject_of(cohort.scans[scans[i]]) for i in tr])
            shuffled = np.random.default_rng(seed).permutation(np.unique(subj_tr))
            fold_of = {u: k % ppca_folds for k, u in enumerate(shuffled)}
            fold = np.asarray([fold_of[u] for u in subj_tr])
            ppca_of = [full] * len(scans)
            for k in range(ppca_folds):
                pk = BatchPPCA.fit(Zf, tr[fold != k], cells, cohort.valid.shape, hybrid, device)
                for i in tr[fold == k]:
                    ppca_of[i] = pk
        model = cls(kind, None, cfg, np.ones(M), {}, device)
        model._cohort = cohort
        model._pos, model._static = cls.static_inputs(cohort)
        pos = model._pos
        n_in = model.n_in(M)
        ctx_all = np.stack([model.context_of(None if ages is None else ages[s], s) for s in scans]) \
            if model.needs_age else np.zeros((len(scans), 0), dtype=np.float32)
        if kind == "transformer":
            patches, tok_tract = tract_patches(cohort, pos, patch)
            model._tok_tract = torch.as_tensor(tok_tract, device=device)

        def new_net():
            if kind == "vae":
                return build_vae(len(pos), n_in, M, latent, hidden, depth).to(device)
            return build_transformer(n_in, M, patches, len(cohort.tracts), d_model, layers, heads).to(device)

        def pop_of(idx, Zm):
            if ppca_of is None:
                return None
            pm = np.full(Zm.shape, np.nan, dtype=np.float32)
            ps = np.full(Zm.shape, np.nan, dtype=np.float32)
            for mdl in {id(ppca_of[i]): ppca_of[i] for i in idx}.values():
                sel = [k for k, i in enumerate(idx) if ppca_of[i] is mdl]
                pm[sel], ps[sel] = mdl.posterior(Zm[sel])
            return pm, ps

        def masked(idx, r):
            Zm, hid = Z[idx].copy(), np.zeros((len(idx), len(pos), M), dtype=bool)
            for k, i in enumerate(idx):
                h = masker(Z[i], r) & ~np.isnan(Z[i])
                Zm[k][h] = np.nan
                hid[k] = h[pos]
            return Zm, hid

        def loss_of(idx, Zm, hid, pop=None, train=True, net=None):
            pop = pop_of(idx, Zm) if pop is None else pop
            xf, obs_v = model.features(Zm, pop, ctx_all[idx])
            x = torch.as_tensor(xf, device=device)
            base = 0.0 if pop is None else torch.as_tensor(np.nan_to_num(pop[0][:, pos]), device=device)
            k = iwae if (train and kind == "vae") else 1
            mean, logvar, post, z = model.forward(x, obs_v, sample=train and kind == "vae", k=k, net=net)
            mean = mean + base
            target = torch.as_tensor(np.nan_to_num(Z[idx][:, pos]), device=device)
            obs = torch.as_tensor(~np.isnan(Z[idx][:, pos]), device=device)
            h = torch.as_tensor(hid, device=device)
            w = torch.where(h, 1.0, visible_weight) * obs
            nll = 0.5 * (logvar + (mean - target[None]) ** 2 * torch.exp(-logvar) + math.log(2 * math.pi))
            rec = (nll * w[None]).sum(dim=(2, 3))  # k x B
            if post is not None and train:
                mu, logv = post
                # importance weights: log p(z) - log q(z | observed), per sample and scan
                lp = -0.5 * (z ** 2).sum(-1)
                lq = -0.5 * (((z - mu[None]) ** 2) * torch.exp(-logv[None]) + logv[None]).sum(-1)
                logw = -rec + beta * (lp - lq)
                loss = -(torch.logsumexp(logw, dim=0) - math.log(k)).sum() / w.sum().clamp(min=1.0)
            else:
                loss = rec.mean(dim=0).sum() / w.sum().clamp(min=1.0)
            return loss, mean[0], logvar[0]

        hr = np.random.default_rng(seed + 1)
        Zh, hid_h = masked(ho, hr)
        pop_h = pop_of(ho, Zh)
        hb = lambda b: None if pop_h is None else (pop_h[0][b:b + batch], pop_h[1][b:b + batch])
        fits = []
        for member in range(max(1, int(members))):
            torch.manual_seed(seed + member)
            mrng = rng if member == 0 else np.random.default_rng(seed + 1000 * member)
            net = new_net()
            opt = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=1e-4)
            sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, epochs)
            best, best_state, best_epoch, history = np.inf, None, 0, []
            for epoch in range(epochs):
                net.train()
                order = mrng.permutation(tr)
                tl = []
                for b in range(0, len(order), batch):
                    idx = order[b:b + batch]
                    if len(idx) < 2:
                        continue
                    Zm, hid = masked(idx, mrng)
                    loss, _, _ = loss_of(idx, Zm, hid, net=net)
                    opt.zero_grad()
                    loss.backward()
                    opt.step()
                    tl.append(loss.item())
                sched.step()
                net.eval()
                with torch.no_grad():
                    vl = float(np.mean([loss_of(ho[b:b + batch], Zh[b:b + batch], hid_h[b:b + batch], hb(b),
                                                False, net=net)[0].item() for b in range(0, len(ho), batch)]))
                history.append((float(np.mean(tl)), vl))
                if vl < best:
                    best, best_epoch = vl, epoch
                    best_state = {k: v.detach().clone() for k, v in net.state_dict().items()}
            net.load_state_dict(best_state)
            net.eval()
            model.nets.append(net)
            fits.append((best, best_epoch, history[best_epoch][0]))
        best, best_epoch, train_best = fits[0]
        num, den = np.zeros(M), np.zeros(M)
        with torch.no_grad():
            for b in range(0, len(ho), batch):
                idx = ho[b:b + batch]
                _, mean, logvar = loss_of(idx, Zh[b:b + batch], hid_h[b:b + batch], hb(b), False)
                zt = Z[idx][:, pos]
                r2 = (mean.cpu().numpy() - zt) ** 2 / np.exp(logvar.cpu().numpy())
                h = hid_h[b:b + batch] & ~np.isnan(zt)
                num += np.where(h, r2, 0.0).sum(axis=(0, 1))
                den += h.sum(axis=(0, 1))
        model.scale = np.sqrt(np.where(den > 0, num / np.maximum(den, 1), 1.0))
        model._ppca = full
        model.info = dict(cfg, epochs=epochs, best_epoch=int(best_epoch), holdout_loss=round(best, 4),
                          train_loss_at_best=round(train_best, 4), train_scans=int(len(tr)),
                          member_best_epochs=[int(f[1]) + 1 for f in fits],
                          holdout_subjects=sorted(str(x) for x in held),
                          seconds=round(time.time() - t0, 1),
                          sd_scale={cohort.metrics[m]: round(float(model.scale[m]), 3) for m in range(M)})
        log.info("  %s %s: %d scans, best epoch %s of %d, NLL train %.3f / held-out %.3f there, SD scale %s (%.0f s)",
                 kind, describe(cfg), len(tr), ",".join(str(f[1] + 1) for f in fits), epochs, train_best, best,
                 " ".join("{} {:.2f}".format(cohort.metrics[m], model.scale[m]) for m in range(M)), time.time() - t0)
        return model

    def predict(self, z, crossfit=5, ctx=None):
        """Mean and SD (positions x metrics) of the deviations of a scan from its observed ones *z* (*ctx*: its
        context inputs); with *crossfit* the observed cells too, each group of tracts predicted with its values hidden
        (as graph_unet)."""
        import torch
        cohort, pos = self._cohort, self._pos
        passes, groups = [z], []
        if crossfit and crossfit > 1:
            order = np.random.default_rng(0).permutation(np.unique(cohort.tract_of))
            for k in range(crossfit):
                g = np.isin(cohort.tract_of, order[k::crossfit])
                zk = z.copy()
                zk[g] = np.nan
                passes.append(zk)
                groups.append(g)
        Zp = np.stack(passes).astype(np.float32)
        pop = None if self._ppca is None else self._ppca.posterior(Zp)
        xf, obs = self.features(Zp, pop, None if ctx is None else np.repeat(ctx[None], len(Zp), axis=0))
        with torch.no_grad():
            mean, logvar, _, _ = self.forward(torch.as_tensor(xf, device=self.device), obs)
            mean = mean[0] + (0.0 if pop is None else torch.as_tensor(np.nan_to_num(pop[0][:, pos]),
                                                                      device=self.device))
        mean, sd = mean.cpu().numpy(), np.exp(0.5 * logvar[0].cpu().numpy()) * self.scale[None, None]
        out_m = np.full((len(passes),) + z.shape, np.nan)
        out_s = np.full((len(passes),) + z.shape, np.nan)
        out_m[:, pos], out_s[:, pos] = mean, sd
        m, s = out_m[0], out_s[0]
        observed = ~np.isnan(z)
        for k, g in enumerate(groups, 1):
            sel = observed & g[:, None]
            m[sel], s[sel] = out_m[k][sel], out_s[k][sel]
        valid = cohort.valid
        return np.where(valid, m, np.nan), np.where(valid, s, np.nan)

    def impute(self, Y, norm, age=None, scan=None):
        """Mean and SD of the values of a scan *Y* on *norm*; with context inputs, its *age* (months) and its index or
        name *scan* in the cohort."""
        ctx = self.context_of(age, scan) if self.needs_age else None
        zm, zsd = self.predict((Y - norm[0]) / norm[1], ctx=ctx)
        return norm[0] + zm * norm[1], zsd * norm[1]

    def save(self, path):
        """The network, its settings, the SD calibration and the population model of a hybrid, with the tracts, arc
        lengths and metrics it was fitted on (torch .pt of tensors and plain values, loaded with weights_only). The
        norm is not saved: it is that of the run using it. Returns the path."""
        import json
        import torch
        c, ppca = self._cohort, self._ppca
        t = lambda a: torch.as_tensor(np.ascontiguousarray(a))
        plain = lambda d: json.loads(json.dumps(d, default=float))
        torch.save({"kind": self.kind,
                    "states": [{k: v.cpu() for k, v in n.state_dict().items()} for n in self.nets],
                    "cfg": plain(self.cfg), "info": plain(self.info), "scale": t(self.scale),
                    "tracts": [str(x) for x in np.asarray(c.tracts)[c.tract_of]], "arcs": t(c.arcs),
                    "metrics": list(c.metrics), "ensemble_table": self.ensemble_table,
                    "ppca": None if ppca is None else {"mu": ppca.mu.cpu(), "W": ppca.W.cpu(), "psi": ppca.psi.cpu(),
                                                       "cells": t(ppca.cells), "shape": [int(x) for x in ppca.shape]}},
                   str(path))
        return str(path)

    @classmethod
    def load(cls, path, cohort, device="auto"):
        """A saved model for *cohort*, which must have its tracts, arc lengths and metrics and their axes."""
        import torch
        from dtiplayground.dmri.fiberprofile.analysis.impute_profiles import pick_device
        device = pick_device(device)
        if str(device) == "mps":
            device = "cpu"
        d = torch.load(str(path), map_location="cpu", weights_only=True)
        arcs = d["arcs"].numpy()
        tracts = np.asarray(cohort.tracts)[cohort.tract_of]
        if len(arcs) != cohort.n_positions or not (np.asarray(d["tracts"]) == tracts).all() or \
                not np.allclose(arcs, cohort.arcs) or list(d["metrics"]) != list(cohort.metrics):
            raise ValueError("the {} {} was fitted on other tracts, arc lengths or metrics than the profiles".format(
                d["kind"], path))
        if cohort.points is None:
            raise ValueError("the {} {} needs the axes of the tracts (--axis-dir)".format(d["kind"], path))
        cfg = d["cfg"]
        M = len(cohort.metrics)
        model = cls(d["kind"], None, cfg, d["scale"].numpy(), d["info"], device)
        model.ensemble_table = d.get("ensemble_table")
        model._cohort = cohort
        model._pos, model._static = cls.static_inputs(cohort)
        n_in = model.n_in(M)
        if d["kind"] == "transformer":
            patches, tok_tract = tract_patches(cohort, model._pos, cfg["patch"])
            model._tok_tract = torch.as_tensor(tok_tract, device=device)
        for state in d["states"] if "states" in d else [d["state"]]:
            if d["kind"] == "vae":
                net = build_vae(len(model._pos), n_in, M, cfg["latent"], cfg["hidden"], cfg["depth"])
            else:
                net = build_transformer(n_in, M, patches, len(cohort.tracts), cfg["d_model"], cfg["layers"],
                                        cfg["heads"])
            net.load_state_dict(state)
            model.nets.append(net.to(device).eval())
        pp = d["ppca"]
        if pp is not None:
            model._ppca = BatchPPCA(pp["mu"].numpy(), pp["W"].numpy(), pp["psi"].numpy(), pp["cells"].numpy(),
                                    tuple(pp["shape"]), device)
        return model


def describe(cfg):
    """A short name of the settings of a model."""
    if cfg["kind"] == "vae":
        s = "z{} h{} d{} iwae{} beta{:g}".format(cfg["latent"], cfg["hidden"], cfg["depth"], cfg["iwae"], cfg["beta"])
    else:
        s = "patch{} d{} L{} heads{}".format(cfg["patch"], cfg["d_model"], cfg["layers"], cfg["heads"])
    if cfg.get("inputs"):
        s += " +" + cfg["inputs"].replace(",", "+")
    if cfg.get("members", 1) > 1:
        s += " x{}".format(cfg["members"])
    return s + (" on population q={}".format(cfg["hybrid"]) if cfg["hybrid"] else "")
