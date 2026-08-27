class PDBViewer {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        if (this.container && window.$3Dmol) {
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
        this.isPlaying = false;
    }

    setStatus(text, visible = true) {
        let el = document.getElementById('viewer-status-text');
        if (!el && this.container) {
            el = document.createElement('div');
            el.id = 'viewer-status-text';
            el.style.cssText = 'position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);color:#94a3b8;font-size:0.9rem;text-align:center;pointer-events:none;z-index:5;background:rgba(15,23,42,0.85);padding:0.6rem 1.2rem;border-radius:8px;border:1px solid rgba(255,255,255,0.1);box-shadow:0 4px 12px rgba(0,0,0,0.5);';
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

    async loadStructure(url, scheme = 'spectrum') {
        if (!this.viewer) return;
        this.setStatus('Loading 3D Structure...', true);
        try {
            const pdbData = await this.fetchPDB(url);
            if (!pdbData || (!pdbData.includes('ATOM') && !pdbData.includes('HETATM'))) {
                this.setStatus('No valid PDB coordinates found for this run', true);
                return;
            }
            this.viewer.clear();
            this.viewer.addModel(pdbData, "pdb");
            
            let style = {};
            if (scheme === 'spectrum' || scheme === 'rainbow') {
                style = {cartoon: {color: 'spectrum'}, stick: {radius: 0.15, colorscheme: 'chain'}};
            } else if (scheme === 'chain') {
                style = {cartoon: {colorscheme: 'chain'}, stick: {radius: 0.15, colorscheme: 'chain'}};
            } else if (scheme === 'plddt') {
                const colorFunc = (atom) => {
                    const b = atom.b;
                    if (b > 90) return '#3b82f6';
                    if (b > 70) return '#06b6d4';
                    if (b > 50) return '#eab308';
                    return '#ef4444';
                };
                style = {cartoon: {colorfunc: colorFunc}, stick: {radius: 0.15, colorfunc: colorFunc}};
            }
            
            this.viewer.setStyle({}, style);
            this.viewer.resize();
            this.viewer.zoomTo();
            this.viewer.render();
            this.setStatus('', false);
        } catch (error) {
            console.warn("Could not load PDB structure:", error);
            this.setStatus('No 3D structure available for this run', true);
        }
    }

    async loadFrame(url) {
        if (!this.viewer) return;
        try {
            const pdbData = await this.fetchPDB(url);
            if (!pdbData || (!pdbData.includes('ATOM') && !pdbData.includes('HETATM'))) return;
            this.viewer.clear();
            this.viewer.addModel(pdbData, "pdb");
            this.viewer.setStyle({}, {cartoon: {color: 'spectrum'}, stick: {radius: 0.15, colorscheme: 'chain'}});
            this.viewer.resize();
            this.viewer.zoomTo();
            this.viewer.render();
            this.setStatus('', false);
        } catch (error) {
            this.setStatus('Waiting for live denoising frame...', true);
        }
    }

    async loadTrajectory(url) {
        if (!this.viewer) return;
        this.setStatus('Loading Trajectory...', true);
        try {
            const pdbData = await this.fetchPDB(url);
            this.viewer.clear();
            this.viewer.addModelsAsFrames(pdbData, "pdb");
            this.viewer.setStyle({}, {cartoon: {color: 'spectrum'}, stick: {radius: 0.15, colorscheme: 'chain'}});
            this.viewer.resize();
            this.viewer.zoomTo();
            this.viewer.animate({loop: "backAndForth", step: 1});
            this.setStatus('', false);
        } catch (error) {
            console.warn("Error loading trajectory:", error);
            this.setStatus('Trajectory file not available', true);
        }
    }
    
    async loadBestOverlay(url) {
        if (!this.viewer) return;
        this.setStatus('Loading Overlay...', true);
        try {
            const pdbData = await this.fetchPDB(url);
            this.viewer.clear();
            this.viewer.addModelsAsFrames(pdbData, "pdb");
            this.viewer.setStyle({model: 0}, {cartoon: {color: 'gray'}, stick: {radius: 0.12, color: 'gray'}});
            this.viewer.setStyle({model: 1}, {cartoon: {color: 'spectrum'}, stick: {radius: 0.15, colorscheme: 'chain'}});
            this.viewer.resize();
            this.viewer.zoomTo();
            this.viewer.render();
            this.setStatus('', false);
        } catch (error) {
            console.warn("Error loading overlay:", error);
            this.setStatus('Overlay file not available', true);
        }
    }

    toggleAnimation() {
        if (this.viewer && this.viewer.isAnimated()) {
            if (this.isPlaying) {
                this.viewer.pauseAnimate();
            } else {
                this.viewer.resumeAnimate();
            }
            this.isPlaying = !this.isPlaying;
        }
    }
    
    setFrame(frameIndex) {
        if (this.viewer && this.viewer.isAnimated()) {
            this.viewer.setFrame(frameIndex);
        }
    }
}

// Global instance
window.pdbViewer = null;

document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('3dmol-viewer')) {
        window.pdbViewer = new PDBViewer('3dmol-viewer');
    }

    const designSelector = document.getElementById('design-selector');
    if (designSelector) {
        designSelector.addEventListener('change', (e) => {
            const url = e.target.value;
            if (url && window.pdbViewer) {
                const scheme = document.getElementById('color-scheme')?.value || 'spectrum';
                window.pdbViewer.loadStructure(url, scheme);
            }
        });
    }

    const colorScheme = document.getElementById('color-scheme');
    if (colorScheme && designSelector) {
        colorScheme.addEventListener('change', (e) => {
            const url = designSelector.value;
            if (url && window.pdbViewer) {
                window.pdbViewer.loadStructure(url, e.target.value);
            }
        });
    }
});
