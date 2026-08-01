# Setup — rfdiffusion-gui on Grex

End-to-end setup for the RFdiffusion web UI on the University of Manitoba Grex cluster.

One-time setup is steps 1–6. After that, each session is step 7.

---

## What you are building

A **submit-and-track** web application:

- A lightweight FastAPI app runs on a Grex **login node**, reachable through an SSH tunnel. It has
  **no GPU, no PyTorch, no Node.js** — it only talks to Slurm and serves HTML.
- The science runs as **ordinary `sbatch` batch jobs** inside an Apptainer container on a GPU node.
- Closing the browser, or restarting the app, does not affect a running job.

---

## 0. Prerequisites

- A Grex account with MFA (Duo) enrolled
- Membership in a Slurm accounting group (`sacctmgr show assoc user=$USER`)
- On your workstation: OpenSSH. Grex warns that older SSH clients may not work with Duo — update if
  anything misbehaves.

---

## 1. Preflight

Log in and clone the repository:

```bash
ssh grex.hpc.umanitoba.ca
```

```bash
git clone <your-repo-url> ~/rfdiffusion-gui && cd ~/rfdiffusion-gui
```

Run the preflight check. It verifies every assumption the container design rests on — partitions,
GPU generations, accounts, container runtime, quota, network egress — and changes nothing:

```bash
bash scripts/preflight-grex.sh
```

Expect `FAIL 0`. If anything fails, stop and resolve it before building — a failed preflight means
the build will fail later and more expensively.

Optionally submit a 5-minute GPU probe that confirms the GPU model and that `$TMPDIR` exists inside a
real allocation:

```bash
bash scripts/preflight-grex.sh --gpu-probe
```

---

## 2. Configure

```bash
cp env.example .env
```

Edit `.env` if you want non-default paths. The defaults put everything under `/home`, which fits
comfortably in the 100 GB quota. Set `RFD_DEFAULT_ACCOUNT` to your accounting group.

To move the heavy data to `/project` later, change `RFD_WEIGHTS` and `RFD_OUTPUT_ROOT` — no code
changes. Keep `RFD_DB` on `/home`: SQLite locking behaves badly on Lustre.

---

## 3. Install the web app environment

The login node's system `python3` is **3.6.8**, far too old. `uv` downloads and manages its own
Python, so this does not matter:

```bash
uv sync
```

If `uv` is missing:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

This environment deliberately contains **no PyTorch, JAX, or CUDA** — the web app is a Slurm client.

---

## 4. Build the container image

**Do this in a CPU allocation, not on a login node.** A multi-GB build is exactly the heavy work
login nodes are not for, and `build-image.sh` will refuse to run on one.

```bash
salloc --partition=skylake --cpus-per-task=4 --mem=16000M --time=0-02:00:00
```

```bash
bash scripts/build-image.sh
```

Expect 15–40 minutes, mostly spent pulling base layers. No GPU is needed to build.

**The script builds on node-local `$TMPDIR`, not in place.** This is deliberate. `--fakeroot` runs
inside a user namespace that remaps your UID to root; on `root_squash` network storage (both `/home`
over NFS and `/project` over Lustre) the server maps that back to `nobody`, which cannot traverse a
`0700` home directory or read your files — so a direct build fails with `permission denied` on the
definition file before doing any work. Staging to node-local disk sidesteps that, and is the right
place for a build regardless: it writes tens of thousands of small files, exactly what Grex's docs
say to keep off the shared filesystem. The finished SIF is copied to `$RFD_IMAGE` before the job ends.

**Note on repository location.** If you cloned into `/project` space
(`~/projects/<group>/<user>/…`), set `RFD_PROJECT_ROOT` in `.env` to that path — the job script
bind-mounts it into the container. `build-image.sh` prints the correct value when it finishes.

The image is built `FROM rosettacommons/rfdiffusion` — inheriting a proven, fully pinned
CUDA 11.6 / torch 1.12.1 / DGL 1.0.2 / e3nn 0.3.3 stack — with the **sokrypton fork** of RFdiffusion
overlaid at a pinned commit. The fork is required: it is the only one with
`inference.dump_pdb`, which the live-progress feature depends on.

If the build fails, the script prints a documented fallback chain (Sylabs remote build, or a local
Docker build and transfer).

---

## 5. Stage model weights

Roughly 8 GB. Safe to interrupt and rerun — downloads resume and completed assets are skipped:

```bash
bash scripts/stage-weights.sh
```

To skip the AlphaFold multimer parameters (several GB; only needed if you enable `use_multimer`):

```bash
bash scripts/stage-weights.sh --no-multimer
```

Weights are downloaded with `curl`, never `aria2c` — `aria2` needs `apt-get` and there is no root on
Grex.

---

## 6. Verify

In a **GPU** allocation:

```bash
salloc --partition=gpu --gpus=1 --cpus-per-task=6 --mem-per-cpu=6000M --time=0-00:30:00
```

```bash
bash scripts/verify-image.sh
```

Seven checks, ordered so the two that could invalidate the approach run first:

| Check | Confirms |
|---|---|
| 3 | The **sokrypton fork** is on `PYTHONPATH` (`dump_pdb` keys present) — gates live progress |
| 4 | **JAX imports and sees the GPU** — the known CUDA-11 risk, with a documented fallback |

If check 4 fails, that is anticipated, not a surprise: see the fallback ladder in
`containers/rfdiffusion.def` and `aidlc-docs/.../infrastructure-design.md` §3.

### Which partitions this image can use

Verified against the live cluster:

| Partition | GPU | Compute cap. | Works? |
|---|---|---|---|
| `gpu` | V100 ×4 / 2 nodes | sm_70 | ✅ |
| `stamps-b` | V100 ×4 / 3 nodes (preemptible) | sm_70 | ✅ |
| `livi-b` | V100 ×16 / 1 node (preemptible) | sm_70 | ✅ |
| `agpu` | A30 ×2 / 2 nodes | sm_80 | ✅ |
| `mcordgpu-b` | A30 ×4 / 2 nodes (preemptible) | sm_80 | ✅ |
| `lgpu` | L40s ×2 / 2 nodes | **sm_89** | ❌ needs the Phase 2 image |

That is 36 V100s and 12 A30s. `-b` partitions are preemptible and open to non-owner groups, with a
1-hour minimum runtime guarantee.

---

## 7. Each session — SSH tunnel and launch

### One-time SSH config

Add to `~/.ssh/config` **on your workstation**:

```
Host grex
    HostName grex.hpc.umanitoba.ca
    User <your-ccdb-username>
    ControlMaster auto
    ControlPath ~/.ssh/cm-%r@%h:%p
    ControlPersist 8h
```

`ControlMaster` is what makes the tunnel work with Duo. Grex's own MFA documentation recommends this
pattern for caching MFA sessions.

### Then, each session

Authenticate **once**, interactively, and answer the Duo push:

```bash
ssh grex
```

Start the web app on the login node (leave it running):

```bash
cd ~/rfdiffusion-gui && uv run rfd-web
```

From your workstation, open the tunnel. It reuses the master socket and **never re-prompts for Duo**:

```bash
ssh -N -L 8080:localhost:8080 grex
```

Open <http://localhost:8080>.

### Why a tunnel spawned by an automated tool fails

Automated tools launch `ssh` without a TTY. Duo needs somewhere to print its prompt and read your
answer; with no terminal it fails. That is an absence-of-terminal problem, not a tunnels-versus-MFA
problem. Authenticating once interactively with `ControlMaster` configured solves it — every later
connection rides the existing socket.

**Do not attempt to work around MFA.** If you ever want the app to start unattended, the supported
path is a CCDB-deposited key plus a conversation with Grex support.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `build-image.sh` refuses to run | You are on a login node | `salloc` a CPU allocation first |
| Build fails pulling base layers | Registry rate limit or transient network | Rerun; layers are cached in `APPTAINER_CACHEDIR` |
| Verify check 3 fails | Image lacks the sokrypton fork | Rebuild; check the `%post` clone step |
| Verify check 4 fails | JAX/CUDA-11 incompatibility | Follow the fallback ladder in `rfdiffusion.def` |
| Verify reports sm_89 | You allocated `lgpu` | Use `gpu`, `agpu`, or a `-b` partition |
| Tunnel asks for Duo every time | `ControlMaster` not configured, or master expired | Check `~/.ssh/config`; re-run `ssh grex` |
| `uv sync` picks the wrong Python | System python3.6 on PATH | `uv` manages its own; ensure `requires-python` is respected |
| Quota exceeded | Weights + image + cache | `stage-weights.sh --no-multimer`, or move `RFD_WEIGHTS`/`RFD_OUTPUT_ROOT` to `/project` |
| Job stuck `PENDING` | GPU queue | Normal. Try `agpu`, or a preemptible `-b` partition |

---

## Reference

- Design documents: `aidlc-docs/`
- Original Colab notebook (unmodified, kept as fallback): `reference/diffusion.py`
- Grex documentation: <https://um-grex.github.io/docs/>
