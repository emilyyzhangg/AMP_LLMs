// ============================================================================
// AMP LLM Enhanced Web Interface - Main Application
// ============================================================================

const app = {
    // Configuration
    API_BASE: window.location.origin,
    apiKey: localStorage.getItem('amp_llm_api_key') || '',
    
    // State
    currentMode: 'menu',
    nctResults: null,
    selectedFile: null,
    files: [],
    
    // =========================================================================
    // Initialization
    // =========================================================================
    
    init() {
        this.apiKey = localStorage.getItem('amp_llm_api_key') || '';
        if (this.apiKey) {
            this.showApp();
        }
        
        // Add enter key handlers
        document.getElementById('api-key-input')?.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.handleAuth();
        });
        
        document.getElementById('chat-input')?.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage('chat');
            }
        });
        
        document.getElementById('research-input')?.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage('research');
            }
        });
    },
    
    // =========================================================================
    // Authentication
    // =========================================================================
    
    async handleAuth() {
        const input = document.getElementById('api-key-input');
        const apiKey = input.value.trim();
        
        if (!apiKey) {
            alert('Please enter an API key');
            return;
        }
        
        try {
            const response = await fetch(`${this.API_BASE}/health`, {
                headers: { 'Authorization': `Bearer ${apiKey}` }
            });
            
            if (response.ok) {
                this.apiKey = apiKey;
                localStorage.setItem('amp_llm_api_key', apiKey);
                this.showApp();
            } else {
                alert('Invalid API key');
            }
        } catch (error) {
            alert('Connection error: ' + error.message);
        }
    },
    
    handleLogout() {
        localStorage.removeItem('amp_llm_api_key');
        this.apiKey = '';
        location.reload();
    },
    
    showApp() {
        document.getElementById('auth-section').classList.add('hidden');
        document.getElementById('main-app').classList.remove('hidden');
        this.showMenu();
    },
    
    // =========================================================================
    // Navigation
    // =========================================================================
    
    showMenu() {
        this.currentMode = 'menu';
        
        // Hide header
        document.getElementById('app-header').classList.add('hidden');
        
        // Show menu
        document.getElementById('menu-view').classList.remove('hidden');
        
        // Hide all modes
        document.querySelectorAll('.mode-container').forEach(el => {
            el.classList.remove('active');
        });
    },
    
    showMode(mode) {
        this.currentMode = mode;
        
        // Show header
        document.getElementById('app-header').classList.remove('hidden');
        
        // Hide menu
        document.getElementById('menu-view').classList.add('hidden');
        
        // Hide all modes
        document.querySelectorAll('.mode-container').forEach(el => {
            el.classList.remove('active');
        });
        
        // Show selected mode
        const modeElement = document.getElementById(`${mode}-mode`);
        if (modeElement) {
            modeElement.classList.add('active');
        }
        
        // Update header
        const titles = {
            'chat': { title: '💬 Chat Mode', subtitle: 'General purpose conversation' },
            'research': { title: '📚 Research Assistant', subtitle: 'RAG-powered trial analysis' },
            'nct': { title: '🔍 NCT Lookup', subtitle: 'Search clinical trials' },
            'files': { title: '📁 File Manager', subtitle: 'Browse and manage trial data' }
        };
        
        const info = titles[mode] || { title: 'AMP LLM', subtitle: '' };
        document.getElementById('mode-title').textContent = info.title;
        document.getElementById('mode-subtitle').textContent = info.subtitle;
        
        // Mode-specific actions
        if (mode === 'files') {
            this.loadFiles();
        }
    },
    
    // =========================================================================
    // Chat & Research
    // =========================================================================
    
    async sendMessage(mode) {
        const inputId = mode === 'chat' ? 'chat-input' : 'research-input';
        const containerId = mode === 'chat' ? 'chat-container' : 'research-container';
        
        const input = document.getElementById(inputId);
        const text = input.value.trim();
        
        if (!text) return;
        
        // Add user message
        this.addMessage(containerId, 'user', text);
        input.value = '';
        
        // Add loading message
        const loadingId = this.addMessage(containerId, 'system', '🤔 Thinking...');
        
        try {
            const endpoint = mode === 'research' ? '/research' : '/chat';
            const response = await fetch(`${this.API_BASE}${endpoint}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.apiKey}`
                },
                body: JSON.stringify({
                    query: text,
                    model: 'llama3.2',
                    max_trials: 10,
                    context_file: this.selectedFile?.name
                })
            });
            
            const data = await response.json();
            
            // Remove loading message
            document.getElementById(loadingId)?.remove();
            
            // Add response
            if (mode === 'research') {
                this.addMessage(containerId, 'assistant', 
                    `${data.answer}\n\n💡 Used ${data.trials_used} trial(s)`);
            } else {
                this.addMessage(containerId, 'assistant', data.response);
            }
            
        } catch (error) {
            document.getElementById(loadingId)?.remove();
            this.addMessage(containerId, 'error', 'Error: ' + error.message);
        }
    },
    
    addMessage(containerId, role, content) {
        const container = document.getElementById(containerId);
        const messageId = 'msg-' + Date.now();
        
        const avatars = {
            'user': '👤',
            'assistant': '🤖',
            'system': 'ℹ️',
            'error': '⚠️'
        };
        
        const messageDiv = document.createElement('div');
        messageDiv.id = messageId;
        messageDiv.className = `message ${role}`;
        messageDiv.innerHTML = `
            <div class="avatar">${avatars[role] || '🤖'}</div>
            <div class="content">${this.escapeHtml(content)}</div>
        `;
        
        container.appendChild(messageDiv);
        container.scrollTop = container.scrollHeight;
        
        return messageId;
    },
    
    // =========================================================================
    // NCT Lookup
    // =========================================================================
    
    async handleNCTLookup() {
        const input = document.getElementById('nct-input');
        const nctIds = input.value.split(',').map(s => s.trim().toUpperCase()).filter(s => s);
        
        if (nctIds.length === 0) {
            alert('Please enter at least one NCT number');
            return;
        }
        
        const useExtended = document.getElementById('use-extended-apis').checked;
        const resultsDiv = document.getElementById('nct-results');
        const progressDiv = document.getElementById('nct-progress');
        const saveBtn = document.getElementById('nct-save-btn');
        
        // Show progress
        progressDiv.classList.remove('hidden');
        progressDiv.innerHTML = '<span class="spinner"></span> <span>Fetching clinical trial data...</span>';
        resultsDiv.innerHTML = '';
        saveBtn.classList.add('hidden');
        
        try {
            const response = await fetch(`${this.API_BASE}/nct-lookup`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.apiKey}`
                },
                body: JSON.stringify({
                    nct_ids: nctIds,
                    use_extended_apis: useExtended
                })
            });
            
            const data = await response.json();
            this.nctResults = data;
            
            // Hide progress
            progressDiv.classList.add('hidden');
            
            // Show save button
            if (data.success) {
                saveBtn.classList.remove('hidden');
            }
            
            // Display results
            this.displayNCTResults(data);
            
        } catch (error) {
            progressDiv.classList.add('hidden');
            resultsDiv.innerHTML = `
                <div class="result-card">
                    <h3>Error</h3>
                    <p>${this.escapeHtml(error.message)}</p>
                </div>
            `;
        }
    },
    
    displayNCTResults(data) {
        const resultsDiv = document.getElementById('nct-results');
        
        if (!data.success || data.results.length === 0) {
            resultsDiv.innerHTML = `
                <div class="result-card">
                    <h3>No Results</h3>
                    <p>No trials found</p>
                </div>
            `;
            return;
        }
        
        // Summary card
        let html = `
            <div class="summary-card">
                <h3>Summary</h3>
                <div class="summary-grid">
                    <div class="summary-item">
                        <div class="summary-item-label">Total Requested</div>
                        <div class="summary-item-value info">${data.summary.total_requested}</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-item-label">Successful</div>
                        <div class="summary-item-value success">${data.summary.successful}</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-item-label">Failed</div>
                        <div class="summary-item-value error">${data.summary.failed}</div>
                    </div>
                </div>
            </div>
        `;
        
        // Trial cards
        data.results.forEach(result => {
            const ct = result.sources?.clinical_trials?.data?.protocolSection || {};
            const ident = ct.identificationModule || {};
            const status = ct.statusModule || {};
            const conditions = ct.conditionsModule?.conditions || [];
            
            html += `
                <div class="result-card">
                    <div class="result-card-header">
                        <div class="result-card-title">
                            <h3>${result.nct_id}</h3>
                            <div class="result-card-status">${status.overallStatus || 'Unknown Status'}</div>
                        </div>
                        <button class="extract-button" onclick="app.extractTrial('${result.nct_id}')">
                            Extract
                        </button>
                    </div>
                    <div class="result-card-content">
                        <strong>${this.escapeHtml(ident.officialTitle || ident.briefTitle || 'No title')}</strong>
                        ${conditions.length > 0 ? `<br><em>Conditions: ${this.escapeHtml(conditions.join(', '))}</em>` : ''}
                    </div>
                    <div class="result-card-meta">
                        <div class="meta-item">
                            PubMed Articles
                            <strong>${result.sources?.pubmed?.pmids?.length || 0}</strong>
                        </div>
                        <div class="meta-item">
                            PMC Articles
                            <strong>${result.sources?.pmc?.pmcids?.length || 0}</strong>
                        </div>
                    </div>
                </div>
            `;
        });
        
        resultsDiv.innerHTML = html;
    },
    
    async extractTrial(nctId) {
        try {
            const response = await fetch(`${this.API_BASE}/extract`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.apiKey}`
                },
                body: JSON.stringify({ nct_id: nctId })
            });
            
            const data = await response.json();
            
            // Show extraction in a nicely formatted way
            const formatted = JSON.stringify(data.extraction, null, 2);
            alert(`Extraction for ${nctId}:\n\n${formatted.substring(0, 500)}...\n\n(Check console for full output)`);
            console.log('Full extraction:', data.extraction);
            
        } catch (error) {
            alert('Extraction error: ' + error.message);
        }
    },
    
    async saveNCTResults() {
        if (!this.nctResults) return;
        
        const filename = `nct_results_${Date.now()}.json`;
        const content = JSON.stringify(this.nctResults.results, null, 2);
        
        // Download locally
        const blob = new Blob([content], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
        
        // Save to server
        try {
            await fetch(`${this.API_BASE}/files/save`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.apiKey}`
                },
                body: JSON.stringify({ filename, content })
            });
            
            alert('Results saved successfully!\nDownloaded locally and saved to server.');
        } catch (error) {
            alert('Saved locally, but server save failed: ' + error.message);
        }
    },
    
    // =========================================================================
    // File Manager
    // =========================================================================
    
    async loadFiles() {
        const container = document.getElementById('files-container');
        container.innerHTML = '<div class="loading">Loading files...</div>';
        
        try {
            const response = await fetch(`${this.API_BASE}/files/list`, {
                headers: { 'Authorization': `Bearer ${this.apiKey}` }
            });
            
            const data = await response.json();
            this.files = data.files || [];
            
            if (this.files.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <div class="empty-state-icon">📁</div>
                        <p>No files found. Upload some trial data to get started.</p>
                    </div>
                `;
                return;
            }
            
            // Display files
            let html = '<div class="files-grid">';
            this.files.forEach(file => {
                html += `
                    <div class="file-card">
                        <div class="file-card-icon">📄</div>
                        <div class="file-card-name">${this.escapeHtml(file.name)}</div>
                        <div class="file-card-meta">Size: ${file.size}</div>
                        <div class="file-card-meta">Modified: ${file.modified}</div>
                        <button class="file-card-load" onclick="app.loadFileIntoChat('${this.escapeHtml(file.name)}')">
                            Load into Chat
                        </button>
                    </div>
                `;
            });
            html += '</div>';
            
            container.innerHTML = html;
            
        } catch (error) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">⚠️</div>
                    <p>Error loading files: ${this.escapeHtml(error.message)}</p>
                </div>
            `;
        }
    },
    
    async loadFileIntoChat(filename) {
        try {
            const response = await fetch(`${this.API_BASE}/files/content/${filename}`, {
                headers: { 'Authorization': `Bearer ${this.apiKey}` }
            });
            
            const data = await response.json();
            
            this.selectedFile = {
                name: filename,
                content: data.content
            };
            
            // Switch to chat mode
            this.showMode('chat');
            
            // Add system message
            const container = document.getElementById('chat-container');
            container.innerHTML = '';
            this.addMessage('chat-container', 'system', 
                `📄 Loaded file: ${filename} (${(data.content.length / 1024).toFixed(1)} KB)`);
            
            // Pre-fill input
            document.getElementById('chat-input').value = 
                `Analyze this clinical trial data from ${filename}`;
            
        } catch (error) {
            alert('Error loading file: ' + error.message);
        }
    },
    
    async handleFileUpload(event) {
        const file = event.target.files[0];
        if (!file) return;
        
        const formData = new FormData();
        formData.append('file', file);
        
        try {
            const response = await fetch(`${this.API_BASE}/files/upload`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${this.apiKey}` },
                body: formData
            });
            
            if (response.ok) {
                alert('File uploaded successfully!');
                this.loadFiles();
            } else {
                alert('Upload failed');
            }
        } catch (error) {
            alert('Upload error: ' + error.message);
        }
        
        // Reset file input
        event.target.value = '';
    },
    
    // =========================================================================
    // Utilities
    // =========================================================================
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
};

// Initialize app when page loads
document.addEventListener('DOMContentLoaded', () => {
    app.init();
});