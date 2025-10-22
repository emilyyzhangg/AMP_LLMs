// ============================================================================
// AMP LLM Enhanced Web Interface - Main Application with Chat Service
// FIXED VERSION: Model selection now works properly with scrolling
// ============================================================================

const app = {
    // Configuration
    API_BASE: window.location.origin,
    apiKey: localStorage.getItem('amp_llm_api_key') || '',
    
    // State
    currentMode: 'menu',
    currentTheme: localStorage.getItem('amp_llm_theme') || 'green',
    currentConversationId: null,
    currentModel: null,
    nctResults: null,
    selectedFile: null,
    files: [],
    availableModels: [],
    
    // =========================================================================
    // Initialization
    // =========================================================================
    
    init() {
        this.apiKey = localStorage.getItem('amp_llm_api_key') || '';
        this.currentTheme = localStorage.getItem('amp_llm_theme') || 'green';
        
        // Apply saved theme
        this.applyTheme(this.currentTheme, false);
        
        if (this.apiKey) {
            this.showApp();
        }
        
        // Close dropdown when clicking outside
        document.addEventListener('click', (e) => {
            const dropdown = document.getElementById('theme-dropdown');
            const button = document.querySelector('.theme-button');
            if (dropdown && !dropdown.contains(e.target) && !button.contains(e.target)) {
                dropdown.classList.add('hidden');
            }
        });
        
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
    // Theme Management
    // =========================================================================
    
    toggleThemeDropdown() {
        const dropdown = document.getElementById('theme-dropdown');
        dropdown.classList.toggle('hidden');
        
        // Update active state
        this.updateActiveTheme();
    },
    
    setTheme(theme) {
        this.currentTheme = theme;
        localStorage.setItem('amp_llm_theme', theme);
        this.applyTheme(theme, true);
        
        // Close dropdown
        document.getElementById('theme-dropdown').classList.add('hidden');
    },
    
    applyTheme(theme, animate = false) {
        const themeStylesheet = document.getElementById('theme-stylesheet');
        const themeNames = {
            'green': 'Green',
            'blue': 'Blue',
            'balanced': 'Tri-Color'
        };
        
        // Update stylesheet
        themeStylesheet.href = `/static/theme-${theme}.css`;
        
        // Update button text
        const themeName = document.getElementById('current-theme-name');
        if (themeName) {
            themeName.textContent = themeNames[theme];
        }
        
        // Update active state in dropdown
        this.updateActiveTheme();
        
        // Optional: Add transition effect
        if (animate) {
            document.body.style.transition = 'background 0.5s ease';
            setTimeout(() => {
                document.body.style.transition = '';
            }, 500);
        }
    },
    
    updateActiveTheme() {
        const options = document.querySelectorAll('.theme-option');
        options.forEach((option, index) => {
            const themes = ['green', 'blue', 'balanced'];
            if (themes[index] === this.currentTheme) {
                option.classList.add('active');
            } else {
                option.classList.remove('active');
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
        this.currentConversationId = null;
        this.currentModel = null;
        
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
            'chat': { title: '💬 Chat with LLM', subtitle: 'Interactive conversation with AI models' },
            'research': { title: '📚 Research Assistant', subtitle: 'RAG-powered trial analysis' },
            'nct': { title: '🔍 NCT Lookup', subtitle: 'Search clinical trials' },
            'files': { title: '📁 File Manager', subtitle: 'Browse and manage trial data' }
        };
        
        const info = titles[mode] || { title: 'AMP LLM', subtitle: '' };
        document.getElementById('mode-title').textContent = info.title;
        document.getElementById('mode-subtitle').textContent = info.subtitle;
        
        // Mode-specific initialization
        if (mode === 'chat') {
            this.initializeChatMode();
        } else if (mode === 'files') {
            this.loadFiles();
        }
    },
    
    // =========================================================================
    // Chat Mode - Model Selection & Conversation
    // =========================================================================
    
    async initializeChatMode() {
        const container = document.getElementById('chat-container');
        container.innerHTML = '';
        
        // Disable input until model is selected
        const input = document.getElementById('chat-input');
        input.disabled = true;
        input.placeholder = 'Select a model to start chatting...';
        
        // Show loading
        this.addMessage('chat-container', 'system', '🔄 Loading available models...');
        
        try {
            const response = await fetch(`${this.API_BASE}/models`, {
                headers: { 'Authorization': `Bearer ${this.apiKey}` }
            });
            
            if (response.ok) {
                const data = await response.json();
                this.availableModels = data.models;
                
                // Clear loading message
                container.innerHTML = '';
                
                // Show model selection
                this.showModelSelection();
            } else {
                container.innerHTML = '';
                this.addMessage('chat-container', 'error', '❌ Failed to load models. Chat service may be unavailable.');
            }
        } catch (error) {
            container.innerHTML = '';
            this.addMessage('chat-container', 'error', '❌ Chat service unavailable: ' + error.message);
        }
    },
    
    showModelSelection() {
        const container = document.getElementById('chat-container');
        
        // Add welcome message
        this.addMessage('chat-container', 'system', 
            '🤖 Welcome to Chat Mode!\n\nSelect a model to start your conversation:');
        
        // Create model selection UI with proper styling
        const selectionDiv = document.createElement('div');
        selectionDiv.className = 'model-selection';
        selectionDiv.id = 'model-selection-container';
        
        this.availableModels.forEach(model => {
            const button = document.createElement('button');
            button.className = 'model-button';
            button.type = 'button'; // Explicitly set button type
            button.innerHTML = `
                <span style="font-size: 1.2em;">📦</span>
                <span style="flex: 1; text-align: left; margin-left: 10px;">${this.escapeHtml(model.name)}</span>
                <span style="color: #666; font-size: 0.9em;">→</span>
            `;
            // Use addEventListener instead of onclick for better event handling
            button.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                console.log('Model button clicked:', model.name);
                this.selectModel(model.name);
            });
            selectionDiv.appendChild(button);
        });
        
        container.appendChild(selectionDiv);
        
        // Ensure container is scrollable and scroll to show all models
        container.style.overflowY = 'auto';
        setTimeout(() => {
            container.scrollTop = container.scrollHeight;
        }, 100);
    },
    
    async selectModel(modelName) {
        console.log('selectModel called with:', modelName);
        const container = document.getElementById('chat-container');
        
        // Show loading
        const loadingId = this.addMessage('chat-container', 'system', `🔄 Initializing ${modelName}...`);
        
        try {
            const response = await fetch(`${this.API_BASE}/chat/init`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.apiKey}`
                },
                body: JSON.stringify({ model: modelName })
            });
            
            if (response.ok) {
                const data = await response.json();
                this.currentConversationId = data.conversation_id;
                this.currentModel = modelName;
                
                console.log('Model initialized:', data);
                
                // Remove loading and model selection
                document.getElementById(loadingId)?.remove();
                const modelSelection = document.getElementById('model-selection-container');
                if (modelSelection) {
                    modelSelection.remove();
                }
                
                // Show ready message
                this.addMessage('chat-container', 'system', 
                    `✅ Connected to ${modelName}\n\n💡 Commands:\n• Type "exit" to select a different model\n• Type "main menu" to return to home`);
                
                // Enable input
                const input = document.getElementById('chat-input');
                input.disabled = false;
                input.placeholder = 'Type your message...';
                input.focus();
            } else {
                const error = await response.json();
                document.getElementById(loadingId)?.remove();
                this.addMessage('chat-container', 'error', '❌ Failed to initialize: ' + error.detail);
            }
        } catch (error) {
            console.error('Error selecting model:', error);
            document.getElementById(loadingId)?.remove();
            this.addMessage('chat-container', 'error', '❌ Error: ' + error.message);
        }
    },
    
    async sendChatMessage(message) {
        // Handle special commands
        const command = message.toLowerCase().trim();
        
        if (command === 'exit') {
            // Return to model selection
            this.currentConversationId = null;
            this.currentModel = null;
            
            const container = document.getElementById('chat-container');
            container.innerHTML = '';
            
            this.showModelSelection();
            
            // Disable input
            const input = document.getElementById('chat-input');
            input.disabled = true;
            input.placeholder = 'Select a model to start chatting...';
            return;
        }
        
        if (command === 'main menu') {
            this.showMenu();
            return;
        }
        
        if (!this.currentConversationId) {
            this.addMessage('chat-container', 'error', '❌ No active conversation. Please select a model first.');
            return;
        }
        
        // Add user message
        this.addMessage('chat-container', 'user', message);
        
        // Show loading
        const loadingId = this.addMessage('chat-container', 'system', '🤔 Thinking...');
        
        try {
            const response = await fetch(`${this.API_BASE}/chat/message`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.apiKey}`
                },
                body: JSON.stringify({
                    conversation_id: this.currentConversationId,
                    message: message,
                    temperature: 0.7
                })
            });
            
            // Remove loading
            document.getElementById(loadingId)?.remove();
            
            if (response.ok) {
                const data = await response.json();
                this.addMessage('chat-container', 'assistant', data.message.content);
            } else {
                const error = await response.json();
                this.addMessage('chat-container', 'error', '❌ Error: ' + error.detail);
            }
        } catch (error) {
            document.getElementById(loadingId)?.remove();
            this.addMessage('chat-container', 'error', '❌ Error: ' + error.message);
        }
    },
    
    // =========================================================================
    // Message Handling
    // =========================================================================
    
    async sendMessage(mode) {
        if (mode === 'chat') {
            const input = document.getElementById('chat-input');
            const text = input.value.trim();
            
            if (!text) return;
            
            input.value = '';
            await this.sendChatMessage(text);
            
        } else if (mode === 'research') {
            const input = document.getElementById('research-input');
            const text = input.value.trim();
            
            if (!text) return;
            
            this.addMessage('research-container', 'user', text);
            input.value = '';
            
            const loadingId = this.addMessage('research-container', 'system', '🤔 Processing query...');
            
            try {
                const response = await fetch(`${this.API_BASE}/research`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${this.apiKey}`
                    },
                    body: JSON.stringify({
                        query: text,
                        model: 'llama3.2',
                        max_trials: 10
                    })
                });
                
                const data = await response.json();
                
                document.getElementById(loadingId)?.remove();
                
                this.addMessage('research-container', 'assistant', 
                    `${data.answer}\n\n💡 Used ${data.trials_used} trial(s)`);
                
            } catch (error) {
                document.getElementById(loadingId)?.remove();
                this.addMessage('research-container', 'error', 'Error: ' + error.message);
            }
        }
    },
    
    addMessage(containerId, role, content) {
        const container = document.getElementById(containerId);
        const messageId = 'msg-' + Date.now() + '-' + Math.random();
        
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
                            <strong>${result.sources?.pubmed?.data?.pmids?.length || 0}</strong>
                        </div>
                        <div class="meta-item">
                            PMC Articles
                            <strong>${result.sources?.pmc?.data?.pmcids?.length || 0}</strong>
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
            
            // Add system message after a brief delay to let chat mode initialize
            setTimeout(() => {
                const container = document.getElementById('chat-container');
                container.innerHTML = '';
                this.addMessage('chat-container', 'system', 
                    `📄 Loaded file: ${filename} (${(data.content.length / 1024).toFixed(1)} KB)\n\nSelect a model to analyze this file.`);
                
                // Show model selection
                this.showModelSelection();
            }, 100);
            
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