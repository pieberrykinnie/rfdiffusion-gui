/**
 * 3D Structure Viewer for RFdiffusion GUI using 3Dmol.js
 */
class PDBViewer {
    constructor(containerId, options = {}) {
        this.containerId = containerId;
        this.container = document.getElementById(containerId);
        this.options = options;
        this.runId = options.runId || null;
        
        this.viewer = null;
        this.currentScheme = options.scheme || 'spectrum';
        this.mode = 'structure'; // 'structure' | 'frame' | 'trajectory' | 'overlay'
        this.isPlaying = false;
        this.currentUrl = null;
        this.designIndex = options.designIndex || 0;
        this.lastFrameData = null;
        this.overlayData = null;
        this.livePollingInterval = null;

        this.initViewer();
    }

    initViewer() {
        if (!this.container || !window.$3Dmol) return;
        
        this.viewer = $3Dmol.createViewer(this.container, {
            backgroundColor: '#0b0f19'
        });

        window.addEventListener('resize', () => {
            if (this.viewer) {
                this.viewer.resize();
                this.viewer.render();
            }
        });
    }

    setStatus(text, visible = true) {
        let el = document.getElementById('viewer-status-text');
        if (!el && this.container) {
            el = document.createElement('div');
            el.id = 'viewer-status-text';
            el.style.cssText = 'position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);color:#e2e8f0;font-size:0.875rem;text-align:center;pointer-events:none;z-index:10;background:rgba(15,23,42,0.9);padding:0.75rem 1.25rem;border-radius:8px;border:1px solid rgba(255,255,255,0.15);box-shadow:0 4px 20px rgba(0,0,0,0.6);max-width:85%;line-height:1.4;';
            this.container.appendChild(el);
        }
        if (el) {
            el.innerText = text;
            el.style.display = visible ? 'block' : 'none';
        }
    }

    async fetchPDB(url) {
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        return await response.text();
    }

    /**
     * AlphaFold / pLDDT confidence color function.
     * Supports both 0..1 scale (RFdiffusion b-factors) and 0..100 scale (AlphaFold).
     */
    getPlddtColor(atom) {
        let b = (atom && typeof atom.b === 'number') ? atom.b : 0;
        if (b <= 1.0 && b > 0) {
            b = b * 100;
        }
        if (b >= 90) return '#0053D6'; // Very high confidence (Dark Blue)
        if (b >= 70) return '#65CBF3'; // Confident (Cyan / Light Blue)
        if (b >= 50) return '#FFDB13'; // Low confidence (Yellow)
        return '#FF7D45';             // Very low confidence (Orange-Red)
    }

    /**
     * Get style specification for a given coloring scheme.
     */
    getStyleSpec(scheme) {
        scheme = scheme || this.currentScheme;
        if (scheme === 'chain') {
            return {
                cartoon: { colorscheme: 'chainHetatm' },
                stick: { radius: 0.15, colorscheme: 'chainHetatm' }
            };
        } else if (scheme === 'plddt') {
            const colorFunc = (atom) => this.getPlddtColor(atom);
            return {
                cartoon: { colorfunc: colorFunc },
                stick: { radius: 0.15, colorfunc: colorFunc }
            };
        } else {
            // 'spectrum' or 'rainbow'
            return {
                cartoon: { color: 'spectrum' },
                stick: { radius: 0.15, colorscheme: 'chainHetatm' }
            };
        }
    }

    /**
     * Apply styling to the current model(s) in the viewer.
     */
    applyStyle(scheme = null) {
        if (!this.viewer) return;
        if (scheme) {
            this.currentScheme = scheme;
        }
        const activeScheme = this.currentScheme;

        if (this.mode === 'overlay' && this.overlayData) {
            // Model 0: Design Backbone (neutral gray)
            this.viewer.setStyle({ model: 0 }, {
                cartoon: { color: '#94a3b8', opacity: 0.75 },
                stick: { radius: 0.12, color: '#94a3b8', opacity: 0.6 }
            });
            // Model 1: AlphaFold Validation (colored by selected scheme, default plddt)
            const afStyle = this.getStyleSpec(activeScheme);
            this.viewer.setStyle({ model: 1 }, afStyle);
        } else {
            // Standard / trajectory / frame mode
            const style = this.getStyleSpec(activeScheme);
            this.viewer.setStyle({}, style);
        }

        this.viewer.render();
    }

    /**
     * Change coloring scheme and immediately re-render.
     */
    setColorScheme(scheme) {
        this.currentScheme = scheme;
        this.applyStyle(scheme);
    }

    /**
     * Load static PDB structure.
     */
    async loadStructure(url, scheme = null) {
        if (!this.viewer) return;
        this.stopLivePolling();
        if (this.isPlaying) {
            this.viewer.stopAnimate();
            this.isPlaying = false;
        }
        this.mode = 'structure';
        this.currentUrl = url;
        if (scheme) this.currentScheme = scheme;

        this.setStatus('Loading 3D Structure...', true);
        try {
            const pdbData = await this.fetchPDB(url);
            if (!pdbData || (!pdbData.includes('ATOM') && !pdbData.includes('HETATM'))) {
                this.setStatus('No valid PDB coordinates found for this run', true);
                return;
            }
            this.viewer.clear();
            this.viewer.addModel(pdbData, "pdb");
            this.applyStyle();
            this.viewer.resize();
            this.viewer.zoomTo();
            this.viewer.render();
            this.setStatus('', false);
        } catch (error) {
            console.warn("Could not load PDB structure:", error);
            this.setStatus('No 3D structure available for this run', true);
        }
    }

    /**
     * Load single live frame during ongoing run denoising.
     */
    async loadFrame(url) {
        if (!this.viewer) return false;
        try {
            const pdbData = await this.fetchPDB(url);
            if (!pdbData || (!pdbData.includes('ATOM') && !pdbData.includes('HETATM'))) {
                return false;
            }

            if (this.lastFrameData === pdbData) {
                return true;
            }
            this.lastFrameData = pdbData;
            this.mode = 'frame';

            let viewState = null;
            try {
                // Preserve camera view during continuous live frame stream
                viewState = this.viewer.getView();
            } catch (e) {}

            this.viewer.clear();
            this.viewer.addModel(pdbData, "pdb");
            this.applyStyle();
            this.viewer.resize();

            if (viewState && viewState.length) {
                this.viewer.setView(viewState);
            } else {
                this.viewer.zoomTo();
            }
            this.viewer.render();
            this.setStatus('', false);
            return true;
        } catch (error) {
            return false;
        }
    }

    /**
     * Start live polling for an active run.
     */
    startLivePolling(runId, designIndex = 0) {
        this.runId = runId;
        this.designIndex = designIndex;
        this.stopLivePolling();

        this.setStatus('Waiting for live denoising frame...', true);

        const poll = async () => {
            if (this.mode !== 'frame' && this.mode !== 'structure' && this.lastFrameData) {
                // Do not disrupt user if they are playing trajectory or viewing overlay
                return;
            }

            try {
                // Check run status
                const res = await fetch(`/runs/${runId}`, {
                    headers: { 'Accept': 'application/json' }
                });
                if (res.ok) {
                    const runData = await res.json();
                    const status = runData.status;

                    if (status === 'COMPLETED') {
                        this.stopLivePolling();
                        await this.loadStructure(`/runs/${runId}/structure/${this.designIndex}`);
                        this.updateUIForCompletedRun();
                        return;
                    } else if (['FAILED', 'CANCELLED', 'TIMEOUT'].includes(status)) {
                        this.stopLivePolling();
                        this.setStatus(`Run ended with status: ${status}`, true);
                        return;
                    }
                }
            } catch (e) {}

            // Try loading latest frame
            const frameUrl = `/runs/${runId}/frame`;
            const loaded = await this.loadFrame(frameUrl);
            if (!loaded && !this.lastFrameData) {
                this.setStatus('Waiting for live denoising frame...', true);
            }
        };

        poll();
        this.livePollingInterval = setInterval(poll, 2500);
    }

    stopLivePolling() {
        if (this.livePollingInterval) {
            clearInterval(this.livePollingInterval);
            this.livePollingInterval = null;
        }
    }

    updateUIForCompletedRun() {
        const trajBtn = document.getElementById('toggle-trajectory');
        if (trajBtn) trajBtn.disabled = false;
        const overlayBtn = document.getElementById('toggle-overlay');
        if (overlayBtn) overlayBtn.disabled = false;
    }

    /**
     * Toggle or load trajectory playback.
     */
    async toggleTrajectory(url) {
        if (!this.viewer) return false;

        if (this.mode === 'trajectory') {
            // Already in trajectory mode: toggle play/pause
            if (this.isPlaying) {
                this.viewer.pauseAnimate();
                this.isPlaying = false;
            } else {
                this.viewer.resumeAnimate();
                this.isPlaying = true;
            }
            return this.isPlaying;
        }

        // Switch to trajectory mode
        this.stopLivePolling();
        this.mode = 'trajectory';
        this.setStatus('Loading Trajectory...', true);

        try {
            const pdbData = await this.fetchPDB(url);
            if (!pdbData || (!pdbData.includes('ATOM') && !pdbData.includes('HETATM'))) {
                this.setStatus('Trajectory file not available for this run', true);
                setTimeout(() => this.setStatus('', false), 3000);
                this.mode = 'structure';
                return false;
            }

            this.viewer.clear();
            this.viewer.addModelsAsFrames(pdbData, "pdb");
            this.applyStyle();
            this.viewer.resize();
            this.viewer.zoomTo();
            this.viewer.animate({ loop: "backAndForth", step: 1, interval: 100 });
            this.isPlaying = true;
            this.setStatus('', false);
            return true;
        } catch (error) {
            console.warn("Error loading trajectory:", error);
            this.setStatus('Trajectory not available yet', true);
            setTimeout(() => this.setStatus('', false), 3000);
            this.mode = 'structure';
            return false;
        }
    }

    /**
     * Toggle or load AlphaFold / Best overlay.
     */
    async toggleBestOverlay(url, fallbackStructureUrl) {
        if (!this.viewer) return { active: false };

        if (this.mode === 'overlay') {
            // Exit overlay mode back to standard structure
            this.overlayData = null;
            await this.loadStructure(fallbackStructureUrl);
            return { active: false };
        }

        // Switch to overlay mode
        this.stopLivePolling();
        if (this.isPlaying) {
            this.viewer.stopAnimate();
            this.isPlaying = false;
        }

        this.setStatus('Loading Best Overlay...', true);
        try {
            const response = await fetch(url);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            
            const data = await response.json();
            if (!data || !data.design_pdb || !data.af_pdb) {
                this.setStatus('Best overlay data not available (validation incomplete)', true);
                setTimeout(() => this.setStatus('', false), 3000);
                return { active: false };
            }

            this.overlayData = data;
            this.mode = 'overlay';

            this.viewer.clear();
            this.viewer.addModel(data.design_pdb, "pdb"); // Model 0: Design Backbone
            this.viewer.addModel(data.af_pdb, "pdb");      // Model 1: AlphaFold Prediction

            this.applyStyle();
            this.viewer.resize();
            this.viewer.zoomTo();
            this.viewer.render();
            this.setStatus('', false);

            return {
                active: true,
                designIndex: data.design_index,
                rmsd: data.rmsd
            };
        } catch (error) {
            console.warn("Error loading overlay:", error);
            this.setStatus('Best overlay not available (run validation required)', true);
            setTimeout(() => this.setStatus('', false), 3000);
            return { active: false };
        }
    }
}

// Global viewer instance
window.pdbViewer = null;

document.addEventListener('DOMContentLoaded', () => {
    // 1. Color Scheme change handler
    const colorScheme = document.getElementById('color-scheme');
    if (colorScheme) {
        colorScheme.addEventListener('change', (e) => {
            if (window.pdbViewer) {
                window.pdbViewer.setColorScheme(e.target.value);
            }
        });
    }

    // 2. Design selector change handler
    const designSelector = document.getElementById('design-selector');
    if (designSelector) {
        designSelector.addEventListener('change', (e) => {
            const designIndex = parseInt(e.target.value.split('/').pop(), 10) || 0;
            if (window.pdbViewer) {
                window.pdbViewer.designIndex = designIndex;
                const trajBtn = document.getElementById('toggle-trajectory');
                const overlayBtn = document.getElementById('toggle-overlay');
                
                if (window.pdbViewer.mode === 'trajectory') {
                    const trajUrl = `/runs/${window.pdbViewer.runId}/trajectory/${designIndex}`;
                    window.pdbViewer.toggleTrajectory(trajUrl).then((isPlaying) => {
                        if (trajBtn) {
                            trajBtn.innerText = isPlaying ? '⏸ Pause Trajectory' : '▶ Play Trajectory';
                        }
                    });
                } else {
                    if (overlayBtn) {
                        overlayBtn.innerText = 'Overlay Best';
                        overlayBtn.classList.remove('btn-primary');
                        overlayBtn.classList.add('btn-secondary');
                    }
                    if (trajBtn) {
                        trajBtn.innerText = 'Play Trajectory';
                        trajBtn.classList.remove('btn-primary');
                        trajBtn.classList.add('btn-secondary');
                    }
                    window.pdbViewer.loadStructure(e.target.value);
                }
            }
        });
    }

    // 3. Toggle Trajectory button handler
    const trajBtn = document.getElementById('toggle-trajectory');
    if (trajBtn) {
        trajBtn.addEventListener('click', async () => {
            if (!window.pdbViewer) return;
            const designIndex = window.pdbViewer.designIndex || 0;
            const trajUrl = `/runs/${window.pdbViewer.runId}/trajectory/${designIndex}`;
            const overlayBtn = document.getElementById('toggle-overlay');
            if (overlayBtn) {
                overlayBtn.innerText = 'Overlay Best';
                overlayBtn.classList.remove('btn-primary');
                overlayBtn.classList.add('btn-secondary');
            }

            const isPlaying = await window.pdbViewer.toggleTrajectory(trajUrl);
            if (isPlaying) {
                trajBtn.innerText = '⏸ Pause Trajectory';
                trajBtn.classList.add('btn-primary');
                trajBtn.classList.remove('btn-secondary');
            } else if (window.pdbViewer.mode === 'trajectory') {
                trajBtn.innerText = '▶ Play Trajectory';
                trajBtn.classList.add('btn-primary');
                trajBtn.classList.remove('btn-secondary');
            } else {
                trajBtn.innerText = 'Play Trajectory';
                trajBtn.classList.remove('btn-primary');
                trajBtn.classList.add('btn-secondary');
            }
        });
    }

    // 4. Toggle Overlay button handler
    const overlayBtn = document.getElementById('toggle-overlay');
    if (overlayBtn) {
        overlayBtn.addEventListener('click', async () => {
            if (!window.pdbViewer) return;
            const designIndex = window.pdbViewer.designIndex || 0;
            const overlayUrl = `/runs/${window.pdbViewer.runId}/best`;
            const fallbackUrl = `/runs/${window.pdbViewer.runId}/structure/${designIndex}`;
            const trajBtn = document.getElementById('toggle-trajectory');
            if (trajBtn) {
                trajBtn.innerText = 'Play Trajectory';
                trajBtn.classList.remove('btn-primary');
                trajBtn.classList.add('btn-secondary');
            }

            const res = await window.pdbViewer.toggleBestOverlay(overlayUrl, fallbackUrl);
            if (res && res.active) {
                overlayBtn.innerText = '✕ Exit Overlay';
                overlayBtn.classList.add('btn-primary');
                overlayBtn.classList.remove('btn-secondary');
            } else {
                overlayBtn.innerText = 'Overlay Best';
                overlayBtn.classList.remove('btn-primary');
                overlayBtn.classList.add('btn-secondary');
            }
        });
    }

    // 5. Detect run status completion via HTMX updates
    document.body.addEventListener('htmx:afterSwap', (event) => {
        const badge = document.querySelector('[data-testid="status-badge"]');
        if (badge && badge.innerText.trim() === 'COMPLETED' && window.pdbViewer) {
            if (window.pdbViewer.mode === 'frame') {
                window.pdbViewer.stopLivePolling();
                window.pdbViewer.loadStructure(`/runs/${window.pdbViewer.runId}/structure/${window.pdbViewer.designIndex || 0}`);
                window.pdbViewer.updateUIForCompletedRun();
            }
        }
    });
});

