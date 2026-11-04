#
#   fiberprofile/analysis/functa.py
#
#   Functa imputation of profile deviations (phase 5), after functa (Dupont et al. 2022) and MedFuncta: one SIREN
#   shared by the scans of a normative cohort, modulated per scan by shifts that a linear map makes from a latent
#   vector. A scan's latent starts at a meta-learned initialization and takes a few gradient steps on its observed
#   values (meta-SGD: a learned step size per latent dimension); the network then predicts every location, with an
#   SD (Gaussian likelihood). Training is meta-learning: the inner steps fit the visible values of a training scan,
#   the outer loss scores values hidden in the validation patterns (whole profiles, gaps, ends, regions, whole
#   measures), so the model learns to impute what a scan is missing from what it has.
#
#   Inputs per location: the 3-D position of the tract axis (scaled to [-1, 1]), optionally a one-hot code of the
#   tract and the scan's log age; with *hybrid* the prediction of a population model (PPCA) and its log SD, and the
#   network predicts the correction to that prediction (as the graph U-Net, graph_unet.py).
#

import logging
import time

import numpy as np

from dtiplayground.dmri.fiberprofile.analysis.graph_unet import BatchPPCA, LOGVAR_RANGE

log = logging.getLogger("impute")


### the network

def build_network(in_dim, out_dim, width=256, depth=4, latent=128, omega0=10.0):
    import torch
    import torch.nn as nn

    class ModulatedSiren(nn.Module):
        """A SIREN whose hidden layers are shifted per scan: sin(omega0 (W h + b + s_l(z))), s = A z; a linear head
        gives the mean and log variance of every metric."""

        def __init__(self):
            super().__init__()
            self.layers = nn.ModuleList([nn.Linear(in_dim if i == 0 else width, width) for i in range(depth)])
            self.mod = nn.Linear(latent, depth * width, bias=False)
            self.head = nn.Linear(width, 2 * out_dim)
            with torch.no_grad():
                for i, layer in enumerate(self.layers):
                    n = layer.in_features
                    b = 1.0 / n if i == 0 else np.sqrt(6.0 / n) / omega0
                    layer.weight.uniform_(-b, b)
                self.mod.weight.normal_(0.0, 0.01)
                b = np.sqrt(6.0 / width) / omega0
                self.head.weight.uniform_(-b, b)
                self.head.bias.zero_()

        def forward(self, x, z):
            s = self.mod(z).view(z.shape[0], depth, width)
            h = x
            for i, layer in enumerate(self.layers):
                h = torch.sin(omega0 * (layer(h) + s[:, i, None, :]))
            out = self.head(h)
            return out[..., :out_dim], out[..., out_dim:].clamp(*LOGVAR_RANGE)

    return ModulatedSiren()


### the model

class FunctaModel:
    """A modulated SIREN of the deviations of a normative cohort from the norm, as the population model:
    impute(Y, norm, age) gives the values and SDs of every cell of a scan from its observed values."""

    method = "functa"

    def __init__(self, net, z0, inner_lr, cfg, scale, info, device):
        self.net, self.z0, self.inner_lr, self.cfg, self.scale, self.info, self.device = \
            net, z0, inner_lr, cfg, scale, info, device
        self._cohort = self._static = self._ppca = None

    ### inputs

    @staticmethod
    def static_inputs(cohort, inputs="xyz"):
        """Per-location inputs of the positions with a 3-D point: xyz scaled to [-1, 1] per axis, and for
        'xyz+tract' a one-hot code of the tract."""
        pos = np.flatnonzero(cohort.has_point)
        pts = cohort.points[pos]
        lo, hi = pts.min(axis=0), pts.max(axis=0)
        cols = [2.0 * (pts - lo) / np.maximum(hi - lo, 1e-6) - 1.0]
        if inputs == "xyz+tract":
            cols.append(np.eye(len(cohort.tracts))[cohort.tract_of[pos]])
        return pos, np.concatenate(cols, axis=1).astype(np.float32)

    def features(self, Zm, ages, pop=None):
        """Network inputs (scans x positions x features) of masked deviations *Zm*: the static inputs, the log
        age (standardized) with cfg['age'], and with a population prediction *pop* its mean and log SD."""
        pos, static = self._pos, self._static
        B = len(Zm)
        cols = [np.broadcast_to(static, (B,) + static.shape)]
        if self.cfg["age"]:
            a = (np.log(np.asarray(ages, dtype=np.float32) + 1.0) - self.cfg["age_mu"]) / self.cfg["age_sd"]
            cols.append(np.broadcast_to(a[:, None, None], (B, len(pos), 1)))
        if pop is not None:
            cols += [np.nan_to_num(pop[0][:, pos]), np.log(np.nan_to_num(pop[1][:, pos], nan=1.0).clip(1e-3))]
        return np.concatenate(cols, axis=2).astype(np.float32)

    ### the inner loop

    def adapt(self, x, y, obs, steps=None, create_graph=False):
        """Latents (B x latent) fitted to the observed deviations *y* (B x positions x metrics, 0 where not *obs*)
        in *steps* meta-SGD steps from the learned initialization (mean squared error per scan)."""
        import torch
        steps = self.cfg["steps"] if steps is None else steps
        z = self.z0[None].expand(x.shape[0], -1)
        n = obs.sum(dim=(1, 2)).clamp(min=1.0)
        for _ in range(steps):
            if not create_graph:
                z = z.detach().requires_grad_(True)
            mean, _ = self.net(x, z)
            loss = ((((mean - y) ** 2) * obs).sum(dim=(1, 2)) / n).sum()
            g, = torch.autograd.grad(loss, z, create_graph=create_graph)
            z = z - self.inner_lr * g
        return z if create_graph else z.detach()

    @classmethod
    def fit(cls, cohort, prior, scans, masker, ages, inputs="xyz", age=False, hybrid=0, latent=128, steps=5,
            width=256, depth=4, omega0=10.0, epochs=60, batch=16, lr=1e-4, seed=0, device="cuda", holdout=0.1,
            visible_weight=0.1, ppca_folds=5, min_scans=10):
        """Meta-train on the deviations of *scans* from the norm of their age bin (*prior*): each epoch hides
        observed values of every scan (*masker*(z, rng)), fits its latent to the visible ones (*steps* inner steps)
        and the mean and log variance of the hidden ones (the visible ones with *visible_weight*). A share *holdout*
        of the subjects, with fixed hidden values, picks the epoch and calibrates the SDs per metric. *ages*: of
        every cohort scan (months). *hybrid* > 0: the prediction of a population model of that many components is
        an input and the network predicts its correction; a training scan gets it from a model fitted without its
        subject (*ppca_folds*)."""
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
        A = np.asarray([ages[s] if ages[s] is not None else np.nan for s in scans], dtype=np.float32)
        la = np.log(A + 1.0)
        cfg = {"inputs": inputs, "age": bool(age), "hybrid": int(hybrid), "latent": latent, "steps": steps,
               "width": width, "depth": depth, "omega0": float(omega0),
               "age_mu": float(np.nanmean(la)), "age_sd": float(np.nanstd(la) or 1.0)}
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
                raise ValueError("functa: no cell observed in {} training scans (--min-scans)".format(min_scans))
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

        model = cls(None, None, None, cfg, np.ones(M), {}, device)
        model._cohort = cohort
        model._pos, model._static = cls.static_inputs(cohort, inputs)
        pos = model._pos
        in_dim = model._static.shape[1] + (1 if age else 0) + (2 * M if hybrid else 0)
        net = build_network(in_dim, M, width, depth, latent, omega0).to(device)
        z0 = torch.zeros(latent, device=device, requires_grad=True)
        inner_lr = torch.full((latent,), 1e-2, device=device, requires_grad=True)
        model.net, model.z0, model.inner_lr = net, z0, inner_lr
        opt = torch.optim.Adam([{"params": net.parameters(), "lr": lr}, {"params": [z0, inner_lr], "lr": lr * 10}])
        sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, epochs)

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

        def loss_of(idx, Zm, hid, pop=None, train=True):
            pop = pop_of(idx, Zm) if pop is None else pop
            x = torch.as_tensor(model.features(Zm, A[idx], pop), device=device)
            base = 0.0 if pop is None else torch.as_tensor(np.nan_to_num(pop[0][:, pos]), device=device)
            vis = Zm[:, pos]
            obs_v = torch.as_tensor(~np.isnan(vis), dtype=torch.float32, device=device)
            y_v = torch.as_tensor(np.nan_to_num(vis), device=device) - base
            z = model.adapt(x, y_v, obs_v, create_graph=train)
            mean, logvar = net(x, z)
            mean = mean + base
            target = torch.as_tensor(np.nan_to_num(Z[idx][:, pos]), device=device)
            obs = torch.as_tensor(~np.isnan(Z[idx][:, pos]), device=device)
            h = torch.as_tensor(hid, device=device)
            nll = 0.5 * (logvar + (mean - target) ** 2 * torch.exp(-logvar))
            w = torch.where(h, 1.0, visible_weight) * obs
            return (nll * w).sum() / w.sum().clamp(min=1.0), mean, logvar

        hr = np.random.default_rng(seed + 1)
        Zh, hid_h = masked(ho, hr)
        pop_h = pop_of(ho, Zh)
        hb = lambda b: None if pop_h is None else (pop_h[0][b:b + batch], pop_h[1][b:b + batch])
        best, best_state, best_epoch = np.inf, None, 0
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
                with torch.no_grad():
                    inner_lr.clamp_(min=0.0)
            sched.step()
            net.eval()
            vl = float(np.mean([loss_of(ho[b:b + batch], Zh[b:b + batch], hid_h[b:b + batch], hb(b), False)[0].item()
                                for b in range(0, len(ho), batch)]))
            if vl < best:
                best, best_epoch = vl, epoch
                best_state = ({k: v.detach().clone() for k, v in net.state_dict().items()}, z0.detach().clone(),
                              inner_lr.detach().clone())
        net.load_state_dict(best_state[0])
        with torch.no_grad():
            z0.copy_(best_state[1])
            inner_lr.copy_(best_state[2])
        net.eval()
        # SDs calibrated per metric on the hidden values of the held-out subjects
        num, den = np.zeros(M), np.zeros(M)
        for b in range(0, len(ho), batch):
            idx = ho[b:b + batch]
            _, mean, logvar = loss_of(idx, Zh[b:b + batch], hid_h[b:b + batch], hb(b), False)
            zt = Z[idx][:, pos]
            r2 = (mean.detach().cpu().numpy() - zt) ** 2 / np.exp(logvar.detach().cpu().numpy())
            h = hid_h[b:b + batch] & ~np.isnan(zt)
            num += np.where(h, r2, 0.0).sum(axis=(0, 1))
            den += h.sum(axis=(0, 1))
        model.scale = np.sqrt(np.where(den > 0, num / np.maximum(den, 1), 1.0))
        model._ppca = full
        model.info = dict(cfg, epochs=epochs, best_epoch=int(best_epoch), holdout_loss=round(best, 4),
                          train_scans=int(len(tr)), seconds=round(time.time() - t0, 1),
                          sd_scale={cohort.metrics[m]: round(float(model.scale[m]), 3) for m in range(M)})
        log.info("  functa %s: %d scans, best epoch %d of %d, held-out NLL %.3f, SD scale %s (%.0f s)",
                 describe(cfg), len(tr), best_epoch + 1, epochs, best,
                 " ".join("{} {:.2f}".format(cohort.metrics[m], model.scale[m]) for m in range(M)), time.time() - t0)
        return model

    ### prediction

    def predict(self, z, age=None, crossfit=5):
        """Mean and SD (positions x metrics, NaN off the axes) of the deviations of a scan from its observed ones
        *z* (positions x metrics, NaN missing) and its *age* (months; needed with cfg['age']). With *crossfit* > 1 the
        observed cells are predicted without their own values too (each of that many groups of tracts with its
        values hidden), so their residuals are those of a prediction (as graph_unet)."""
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
        ages = np.full(len(passes), np.nan if age is None else float(age), dtype=np.float32)
        x = torch.as_tensor(self.features(Zp, ages, pop), device=self.device)
        base = 0.0 if pop is None else torch.as_tensor(np.nan_to_num(pop[0][:, pos]), device=self.device)
        vis = Zp[:, pos]
        obs = torch.as_tensor(~np.isnan(vis), dtype=torch.float32, device=self.device)
        y = torch.as_tensor(np.nan_to_num(vis), device=self.device) - base
        with torch.enable_grad():
            zl = self.adapt(x, y, obs)
        with torch.no_grad():
            mean, logvar = self.net(x, zl)
            mean = mean + base
        mean, sd = mean.cpu().numpy(), np.exp(0.5 * logvar.cpu().numpy()) * self.scale[None, None]
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

    def impute(self, Y, norm, age=None):
        """(values, SDs) of every cell of a scan with values *Y*, the norm (mean, SD) of its age bin and its age."""
        zm, zsd = self.predict((Y - norm[0]) / norm[1], age)
        return norm[0] + zm * norm[1], zsd * norm[1]


def describe(cfg):
    """A short name of the settings of a model."""
    return "{}{}{} z{} k{} {}x{} w{:g}".format(
        cfg["inputs"], "+age" if cfg["age"] else "",
        " on population q={}".format(cfg["hybrid"]) if cfg["hybrid"] else "", cfg["latent"], cfg["steps"],
        cfg["depth"], cfg["width"], cfg["omega0"])
