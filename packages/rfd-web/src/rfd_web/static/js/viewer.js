class PDBViewer {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        if (this.container && window.$3Dmol) {
            this.viewer = $3Dmol.createViewer(this.container, {
                backgroundColor: 'black'
            });
        }
        this.currentTrajectory = null;
        this.isPlaying = false;
        this.animationInterval = null;
    }

    async fetchPDB(url) {
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        return await response.text();
    }

    async loadFrame(url) {
        if (!this.viewer) return;
        try {
            const pdbData = await this.fetchPDB(url);
            this.viewer.clear();
            this.viewer.addModel(pdbData, "pdb");
            this.viewer.setStyle({}, {cartoon: {color: 'spectrum'}});
            this.viewer.zoomTo();
            this.viewer.render();
        } catch (error) {
            console.error("Error loading live frame:", error);
        }
    }

    async loadStructure(url, scheme = 'rainbow') {
        if (!this.viewer) return;
        try {
            const pdbData = await this.fetchPDB(url);
            this.viewer.clear();
            this.viewer.addModel(pdbData, "pdb");
            
            let style = {};
            if (scheme === 'rainbow') {
                style = {cartoon: {color: 'spectrum'}};
            } else if (scheme === 'chain') {
                style = {cartoon: {colorscheme: 'chain'}};
            } else if (scheme === 'plddt') {
                // b-factor coloring for plddt
                style = {cartoon: {
                    colorfunc: (atom) => {
                        const b = atom.b;
                        if (b > 90) return 'blue';
                        if (b > 70) return 'cyan';
                        if (b > 50) return 'yellow';
                        return 'red';
                    }
                }};
            }
            
            this.viewer.setStyle({}, style);
            this.viewer.zoomTo();
            this.viewer.render();
        } catch (error) {
            console.error("Error loading structure:", error);
        }
    }

    async loadTrajectory(url) {
        if (!this.viewer) return;
        try {
            const pdbData = await this.fetchPDB(url);
            this.viewer.clear();
            this.viewer.addModelsAsFrames(pdbData, "pdb");
            this.viewer.setStyle({}, {cartoon: {color: 'spectrum'}});
            this.viewer.zoomTo();
            this.viewer.animate({loop: "forward", step: 1});
        } catch (error) {
            console.error("Error loading trajectory:", error);
        }
    }
    
    async loadBestOverlay(url) {
        if (!this.viewer) return;
        try {
            const pdbData = await this.fetchPDB(url);
            this.viewer.clear();
            this.viewer.addModelsAsFrames(pdbData, "pdb");
            
            // Set style for model 0 (backbone) and model 1 (design)
            this.viewer.setStyle({model: 0}, {cartoon: {color: 'gray'}});
            this.viewer.setStyle({model: 1}, {cartoon: {color: 'spectrum'}});
            
            this.viewer.zoomTo();
            this.viewer.render();
        } catch (error) {
            console.error("Error loading overlay:", error);
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

    // Design selector logic
    const designSelector = document.getElementById('design-selector');
    if (designSelector) {
        designSelector.addEventListener('change', (e) => {
            const url = e.target.value;
            if (url && window.pdbViewer) {
                const scheme = document.getElementById('color-scheme')?.value || 'rainbow';
                window.pdbViewer.loadStructure(url, scheme);
            }
        });
    }

    // Color scheme selector logic
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
