# Interaction Diagrams

How each business transaction (from `business-overview.md`) is realised across the components in `architecture.md`.

---

## BT-1: Provision Environment

```mermaid
sequenceDiagram
    participant U as User
    participant C1 as Cell 1
    participant APT as apt / pip / git
    participant IPD as files.ipd.uw.edu
    participant GCS as storage.googleapis.com
    participant FS as VM filesystem

    U->>C1: run setup cell
    C1->>APT: apt-get install aria2 (requires root)
    C1->>IPD: aria2c -x16 schedules.zip, 3 checkpoints (background &)
    C1->>GCS: aria2c -x16 alphafold_params.tar (background &)
    Note over C1,GCS: downloads detached; code install proceeds in parallel
    C1->>APT: git clone RFdiffusion
    C1->>APT: pip install hydra-core, omegaconf, dllogger, dgl, e3nn==0.5.5, SE3Transformer
    C1->>APT: pip install git+ColabDesign
    C1->>FS: ln -s /usr/local/lib/python3.*/dist-packages/colabdesign ./colabdesign
    C1->>IPD: wget ananas; chmod +x
    loop until each *.aria2 marker disappears
        C1->>FS: poll, sleep 5
    end
    C1->>FS: mv checkpoints to RFdiffusion/models/; unzip schedules
    C1->>FS: touch params/done.txt
    C1->>C1: os.environ["DGLBACKEND"]="pytorch"; sys.path.append("RFdiffusion")
    C1-->>U: imports resolved, ~3 min elapsed
```

**Port impact**: This entire transaction disappears. It is replaced by a one-time `uv sync` against a lockfile plus a one-time weight-staging step onto persistent storage. The `apt-get` step (root) and the `dist-packages` symlink have no Grex equivalent at all.

---

## BT-2: Generate Backbone

```mermaid
sequenceDiagram
    participant U as User
    participant C2 as Cell 2 form
    participant RD as run_diffusion
    participant GP as get_pdb
    participant NET as RCSB / AlphaFold DB
    participant AN as run_ananas -> ./ananas
    participant CD as colabdesign utils
    participant R as run
    participant RF as run_inference.py
    participant FS as outputs/

    U->>C2: 13 form parameters
    C2->>C2: derive collision-free path (random 5-char suffix)
    C2->>C2: strip quotes from string params
    C2->>RD: run_diffusion(**flags)
    RD->>RD: resolve symmetry -> (sym, copies)
    RD->>RD: tokenise contigs -> infer mode

    alt mode is fixed or partial
        RD->>GP: get_pdb(pdb)
        alt blank
            GP->>U: files.upload() browser dialog
        else 4-char code
            GP->>NET: wget RCSB {code}.pdb1.gz; gunzip
        else other
            GP->>NET: wget AlphaFold AF-{id}-F1-model_v3.pdb
        end
        GP-->>RD: local path
        RD->>CD: pdb_to_string(path, chains)
        opt symmetry == auto
            RD->>AN: run_ananas(pdb_str, path)
            AN->>AN: ./ananas -u -j out.json
            AN->>CD: sym_it() per ATOM to extract asymmetric unit
            AN-->>RD: (group, reduced pdb_str) or (None, unchanged)
        end
        RD->>FS: write outputs/{path}/input.pdb
        RD->>RD: parse_pdb -> fix_contigs / fix_partial_contigs
    end

    RD->>RD: assemble Hydra overrides (opts list)
    RD->>R: run(cmd, iterations, num_designs, visual)
    R->>RF: nohup launch; capture PID
    RF->>FS: outputs/{path}_{n}.pdb + outputs/traj/*.pdb
    R-->>RD: returns when process exits
    RD->>CD: fix_pdb() rewrite of every output and trajectory
    RD-->>C2: (normalised contigs, copies)
    C2-->>U: globals published for downstream cells
```

**Port impact**: `run_diffusion`'s logic ports almost verbatim and is the core asset. What changes: `get_pdb`'s upload branch, the shell-string assembly (must become an argument list), and the return values (must become a persisted run record rather than notebook globals).

---

## BT-3: Monitor Diffusion Progress

```mermaid
sequenceDiagram
    participant R as run
    participant OS as OS process table
    participant RF as run_inference.py
    participant SHM as /dev/shm
    participant W as ipywidgets
    participant U as User

    R->>SHM: delete stale {0..steps-1}.pdb
    R->>RF: nohup {cmd} & echo $! > /dev/shm/pid
    R->>R: read PID, remove pid file
    R->>W: display VBox(FloatProgress, Output)

    loop for each design, for each step n
        loop poll every 100 ms
            R->>SHM: does {n}.pdb exist?
            alt exists and content ends with TER
                R->>R: wait = False
            else process dead
                R->>OS: os.kill(pid, 0) -> OSError
                R->>W: bar_style = danger, description = failed
            end
        end
        R->>W: progress.value = (n+1)/steps
        opt visual == image
            R->>W: get_ca + plot_pseudo_3D -> matplotlib figure
        end
        opt visual == interactive
            R->>W: py3Dmol view of {n}.pdb
        end
        R->>SHM: delete {n}.pdb
        W-->>U: live progress and structure
    end

    loop until process exits
        R->>OS: os.kill(pid, 0); sleep 100 ms
    end

    opt KeyboardInterrupt
        R->>OS: os.kill(pid, SIGTERM)
        R->>W: bar_style = danger, description = stopped
    end
```

**Port impact**: **Full rewrite.** There is no ipywidgets in a web app, and on a shared cluster the fixed `/dev/shm` paths collide between users. The transaction becomes: job writes step dumps to a per-run scratch directory; the web server exposes run status; the browser polls or subscribes (SSE/websocket) and renders with 3Dmol.js client-side. The `TER`-suffix completeness check and the PID-liveness pattern are worth carrying over conceptually; under Slurm, liveness is better answered by `squeue`/`sacct` than by `os.kill`.

---

## BT-4: Review Backbone

```mermaid
sequenceDiagram
    participant U as User
    participant C3 as Cell 3
    participant PP as plot_pdb
    participant FS as outputs/traj/
    participant CD as colabdesign
    participant P3 as py3Dmol
    participant MPL as matplotlib

    U->>C3: set animate, color, dpi
    alt num_designs > 1
        C3->>U: ipywidgets Dropdown of design indices
        U->>PP: select design n
    else
        C3->>PP: plot_pdb()
    end
    PP->>FS: read {path}_{n}_pX0_traj.pdb (or _Xt-1_ if denoise False)
    alt animate == none
        PP->>FS: read final outputs/{path}_{n}.pdb
        PP->>P3: addModel + setStyle(cartoon)
    else animate == interactive
        PP->>P3: addModelsAsFrames + animate(backAndForth)
    else animate == movie
        PP->>CD: get_Ls, get_ca, make_animation
        PP->>MPL: render GIF -> display(HTML(...))
    end
    P3-->>U: 3D view (loads 3Dmol.js from 3dmol.org)
```

**Port impact**: Rewrite as browser-side rendering. Note that py3Dmol already delegates to client-side 3Dmol.js — so the *rendering* is already happening in the browser, and only the Python wrapper needs replacing. The matplotlib "movie" path is server-side and would need either server-side GIF generation or a client-side frame animation instead.

---

## BT-5: Design and Validate Sequence

```mermaid
sequenceDiagram
    participant U as User
    participant C4 as Cell 4
    participant FS as params/
    participant DT as designability_test.py
    participant MPNN as ProteinMPNN
    participant AF as AlphaFold
    participant OUT as outputs/{path}/

    U->>C4: num_seqs, mpnn_sampling_temp, rm_aa, use_solubleMPNN,<br/>initial_guess, num_recycles, use_multimer
    loop until params/done.txt exists
        C4->>FS: poll, sleep 5
    end
    C4->>C4: contigs_str = ":".join(contigs)  [global from BT-2]
    C4->>DT: python designability_test.py --pdb --loc --contig --copies<br/>--num_seqs --num_recycles --rm_aa --mpnn_sampling_temp --num_designs [flags]
    DT->>MPNN: sample num_seqs sequences for the backbone
    MPNN-->>DT: sequences
    DT->>AF: predict structure per sequence (num_recycles, optional initial_guess/multimer)
    AF-->>DT: predicted structures + pLDDT
    DT->>DT: score RMSD vs. intended backbone
    DT->>OUT: best.pdb (REMARK 001 design m N n RMSD r), best_design{n}.pdb
    DT-->>U: stdout scores
```

**Port impact**: Ports with moderate change. The blocking `params/done.txt` poll disappears (weights are pre-staged). The `!python` magic becomes a subprocess or a second Slurm step. Because this stage is itself GPU-bound and long-running, it is a natural second job rather than something to run inline in a web request.

---

## BT-6: Review Best Design

```mermaid
sequenceDiagram
    participant U as User
    participant C5 as Cell 5
    participant PP as plot_pdb (shadows Cell 3)
    participant OUT as outputs/
    participant P3 as py3Dmol

    U->>C5: run cell
    alt num_designs > 1
        C5->>U: Dropdown ["best", "0", "1", ...]
    end
    opt num == "best"
        PP->>OUT: read first line of {path}/best.pdb
        PP->>PP: parse REMARK 001 design {m} -> num = field 3
    end
    PP->>OUT: read {path}_{num}.pdb (RFdiffusion backbone)
    PP->>P3: addModel -> plain cartoon
    PP->>OUT: read {path}/best_design{num}.pdb (AlphaFold prediction)
    PP->>P3: addModel -> cartoon coloured by pLDDT (roygb, 0-100)
    P3-->>U: superposed comparison view
```

**Port impact**: Same as BT-4 — client-side rendering. Also the point at which the `plot_pdb` shadowing bug (TD-10) must be resolved by giving the two views distinct names.

---

## BT-7: Export Results

```mermaid
sequenceDiagram
    participant U as User
    participant C6 as Cell 6
    participant SH as zip
    participant GC as google.colab.files
    participant B as Browser

    U->>C6: run cell
    C6->>SH: zip -r {path}.result.zip outputs/{path}* outputs/traj/{path}*
    SH-->>C6: {path}.result.zip
    C6->>GC: files.download("{path}.result.zip")
    GC->>B: browser download
    B-->>U: result archive on local machine
```

**Port impact**: `google.colab.files.download` is a hard blocker and becomes an HTTP download endpoint. On Grex there is also a viable alternative the notebook never had: results already live on persistent `/project` storage, so download is a convenience rather than a necessity for data survival — and for large result sets, Globus is the documented transfer path.

---

## Cross-Transaction State Dependencies

```mermaid
flowchart LR
    BT2["BT-2 Generate Backbone"]
    BT3["BT-3 Monitor Progress"]
    BT4["BT-4 Review Backbone"]
    BT5["BT-5 Design + Validate"]
    BT6["BT-6 Review Best"]
    BT7["BT-7 Export"]

    BT2 -->|path, contigs, copies, num_designs| BT4
    BT2 -->|path, contigs, copies, num_designs| BT5
    BT2 -->|steps, num_designs, visual| BT3
    BT5 -->|best.pdb, best_design n| BT6
    BT2 -->|outputs/ path| BT7
    BT5 -->|outputs/ path| BT7
```

**The single most important finding for the port**: every downstream transaction depends on state produced by BT-2 and carried in the Python global namespace — `path`, `contigs` (normalised and symmetry-replicated), `copies`, and `num_designs`. In a notebook this is free. In a web application it must become an explicit, persisted **run record**, because HTTP requests share no memory and a Slurm job outlives the request that submitted it.
