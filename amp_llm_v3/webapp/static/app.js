// ============================================================================
// AMP LLM Enhanced Web Interface - COMPLETELY FIXED VERSION
// ✅ Fixed: insertBefore error - now uses safe DOM manipulation
// ✅ Fixed: Model loading and display
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
        console.log('🚀 App initializing...');
        this.apiKey = localStorage.getItem('amp_llm_api_key') || '';
        this.currentTheme = localStorage.getItem('amp_llm_theme') || 'green';
        
        this.applyTheme(this.currentTheme, false);
        
        if (this.apiKey) {
            console.log('✅ API key found, showing app');
            this.showApp();
        } else {
            console.log('⚠️  No API key, showing auth');
        }
        
        document.addEventListener('click', (e) => {
            const dropdown = document.getElementById('theme-dropdown');
            const button = document.querySelector('.theme-button');
            if (dropdown && !dropdown.contains(e.target) && !button.contains(e.target)) {
                dropdown.classList.add('hidden');
            }
        });
        
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
        
        console.log('✅ App initialized');
    },
    
    // =========================================================================
    // Theme Management
    // =========================================================================
    
    toggleThemeDropdown() {
        const dropdown = document.getElementById('theme-dropdown');
        dropdown.classList.toggle('hidden');
        this.updateActiveTheme();
    },
    
    setTheme(theme) {
        this.currentTheme = theme;
        localStorage.setItem('amp_llm_theme', theme);
        this.applyTheme(theme, true);
        document.getElementById('theme-dropdown').classList.add('hidden');
    },
    
    applyTheme(theme, animate = false) {
        const themeStylesheet = document.getElementById('theme-stylesheet');
        const themeNames = {
            'green': 'Green',
            'blue': 'Blue',
            'balanced': 'Tri-Color'
        };
        
        themeStylesheet.href = `/static/theme-${theme}.css`;
        
        const themeName = document.getElementById('current-theme-name');
        if (themeName) {
            themeName.textContent = themeNames[theme];
        }
        
        this.updateActiveTheme();
        
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
        
        console.log('🔑 Testing API key...');
        
        try {
            const response = await fetch(`${this.API_BASE}/health`, {
                headers: { 'Authorization': `Bearer ${apiKey}` }
            });
            
            console.log('📥 Health check response:', response.status);
            
            if (response.ok) {
                const data = await response.json();
                console.log('✅ Health check data:', data);
                
                this.apiKey = apiKey;
                localStorage.setItem('amp_llm_api_key', apiKey);
                this.showApp();
            } else {
                const errorText = await response.text();
                console.error('❌ Invalid API key:', errorText);
                alert('Invalid API key');
            }
        } catch (error) {
            console.error('❌ Connection error:', error);
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
        console.log('📋 Showing menu');
        this.currentMode = 'menu';
        this.currentConversationId = null;
        this.currentModel = null;
        
        document.getElementById('app-header').classList.add('hidden');
        document.getElementById('menu-view').classList.remove('hidden');
        
        document.querySelectorAll('.mode-container').forEach(el => {
            el.classList.remove('active');
        });
    },
    
    showMode(mode) {
        console.log('🎯 Showing mode:', mode);
        this.currentMode = mode;
        
        document.getElementById('app-header').classList.remove('hidden');
        document.getElementById('menu-view').classList.add('hidden');
        
        document.querySelectorAll('.mode-container').forEach(el => {
            el.classList.remove('active');
        });
        
        const modeElement = document.getElementById(`${mode}-mode`);
        if (modeElement) {
            modeElement.classList.add('active');
        }
        
        const titles = {
            'chat': { title: '💬 Chat with LLM', subtitle: 'Interactive conversation with AI models' },
            'research': { title: '📚 Research Assistant', subtitle: 'RAG-powered trial analysis' },
            'nct': { title: '🔍 NCT Lookup', subtitle: 'Search clinical trials' },
            'files': { title: '📁 File Manager', subtitle: 'Browse and manage trial data' }
        };
        
        const info = titles[mode] || { title: 'AMP LLM', subtitle: '' };
        document.getElementById('mode-title').textContent = info.title;
        document.getElementById('mode-subtitle').textContent = info.subtitle;
        
        this.updateBackButton();
        
        if (mode === 'chat') {
            this.initializeChatMode();
        } else if (mode === 'research') {
            this.ensureChatInfoBar();
        } else if (mode === 'files') {
            this.loadFiles();
        }
    },
    
    updateBackButton() {
        const backButton = document.querySelector('.back-button');
        
        if (this.currentMode === 'chat' && this.currentConversationId) {
            backButton.textContent = '← Back to Models';
            backButton.onclick = () => {
                this.currentConversationId = null;
                this.currentModel = null;
                
                const container = document.getElementById('chat-container');
                container.innerHTML = '';
                
                this.showModelSelection();
                
                const input = document.getElementById('chat-input');
                input.disabled = true;
                input.placeholder = 'Select a model to start chatting...';
                
                this.updateBackButton();
                this.updateChatInfoBar();
            };
        } else {
            backButton.textContent = '← Back';
            backButton.onclick = () => this.showMenu();
        }
    },
    
    // =========================================================================
    // Chat Mode - COMPLETELY FIXED
    // =========================================================================
    
    async initializeChatMode() {
        console.log('🚀 Initializing chat mode...');
        
        // Create info bar FIRST, before any content
        this.ensureChatInfoBar();
        
        const container = document.getElementById('chat-container');
        container.innerHTML = '';
        
        const input = document.getElementById('chat-input');
        input.disabled = true;
        input.placeholder = 'Select a model to start chatting...';
        
        const loadingId = this.addMessage('chat-container', 'system', '🔄 Loading available models...');
        
        try {
            console.log('📡 Fetching models from:', `${this.API_BASE}/models`);
            
            const response = await fetch(`${this.API_BASE}/models`, {
                headers: { 
                    'Authorization': `Bearer ${this.apiKey}`,
                    'Content-Type': 'application/json'
                }
            });
            
            console.log('📥 Response status:', response.status);
            
            if (response.ok) {
                const data = await response.json();
                console.log('✅ Models data:', data);
                
                if (!data.models || data.models.length === 0) {
                    document.getElementById(loadingId)?.remove();
                    this.addMessage('chat-container', 'error', 
                        '❌ No models available.\n\n' +
                        'The chat service is running but no models are available.\n\n' +
                        'To fix:\n' +
                        '1. Check Ollama: ollama list\n' +
                        '2. Install a model: ollama pull llama3.2\n' +
                        '3. Refresh this page');
                    return;
                }
                
                this.availableModels = data.models;
                console.log('✅ Loaded models:', this.availableModels);
                
                document.getElementById(loadingId)?.remove();
                this.showModelSelection();
            } else {
                const errorText = await response.text();
                console.error('❌ Failed to load models:', response.status, errorText);
                
                document.getElementById(loadingId)?.remove();
                this.addMessage('chat-container', 'error', 
                    `❌ Failed to load models (HTTP ${response.status})\n\n` +
                    `The chat service may not be running properly.\n\n` +
                    `To fix:\n` +
                    `1. Restart chat service:\n` +
                    `   cd "standalone modules/chat_with_llm"\n` +
                    `   uvicorn chat_api:app --port 8001 --reload\n\n` +
                    `2. Check: curl http://localhost:8001/models\n\n` +
                    `Error: ${errorText.substring(0, 200)}`);
            }
        } catch (error) {
            console.error('❌ Exception loading models:', error);
            
            document.getElementById(loadingId)?.remove();
            this.addMessage('chat-container', 'error', 
                '❌ Connection Error\n\n' +
                'Cannot connect to the chat service.\n\n' +
                'The chat service must be running on port 8001.\n\n' +
                'To start it:\n' +
                '1. Open terminal\n' +
                '2. cd amp_llm_v3/standalone\\ modules/chat_with_llm\n' +
                '3. uvicorn chat_api:app --port 8001 --reload\n\n' +
                'Then refresh this page.\n\n' +
                `Error: ${error.message}`);
        }
    },

    // COMPLETELY REWRITTEN - Safe DOM manipulation
    ensureChatInfoBar() {
        console.log('📊 Ensuring chat info bar...');
        
        const modeId = this.currentMode + '-mode';
        const modeElement = document.getElementById(modeId);
        
        if (!modeElement) {
            console.warn('⚠️  Mode element not found:', modeId);
            return;
        }
        
        // Check if info bar already exists
        let infoBar = modeElement.querySelector('.chat-info-bar');
        
        if (!infoBar) {
            console.log('➕ Creating new info bar for', this.currentMode);
            
            // Create the info bar
            infoBar = document.createElement('div');
            infoBar.className = 'chat-info-bar';
            
            // SAFE METHOD: Insert as first child using prepend
            // This is the safest way - prepend is supported by all modern browsers
            modeElement.prepend(infoBar);
            
            console.log('✅ Info bar created and inserted using prepend()');
        } else {
            console.log('✅ Info bar already exists');
        }
        
        // Now update its content
        this.updateChatInfoBar();
    },

    updateChatInfoBar() {
        const modeElement = document.getElementById(this.currentMode + '-mode');
        if (!modeElement) {
            console.warn('⚠️  Mode element not found for info bar update');
            return;
        }
        
        let infoBar = modeElement.querySelector('.chat-info-bar');
        if (!infoBar) {
            console.warn('⚠️  Info bar not found, creating...');
            this.ensureChatInfoBar();
            infoBar = modeElement.querySelector('.chat-info-bar');
            if (!infoBar) {
                console.error('❌ Failed to create info bar');
                return;
            }
        }
        
        const modelDisplay = this.currentModel || '<em>Not selected</em>';
        const statusClass = this.currentConversationId ? 'chat-info-status-connected' : 'chat-info-status-disconnected';
        const statusText = this.currentConversationId ? '🟢 Connected' : '⚪ Select a model';
        
        const serviceLabel = this.currentMode === 'research' ? 'Research Assistant' : 'Chat with LLM';
        
        infoBar.innerHTML = `
            <div class="chat-info-item">
                <span class="chat-info-label">💬 Service:</span>
                <span class="chat-info-value">${serviceLabel}</span>
            </div>
            <div class="chat-info-item">
                <span class="chat-info-label">🤖 Model:</span>
                <span class="chat-info-value">${modelDisplay}</span>
            </div>
            <div class="chat-info-item">
                <span class="chat-info-label">Status:</span>
                <span class="chat-info-value ${statusClass}">${statusText}</span>
            </div>
        `;
    },

    showModelSelection() {
        console.log('📦 Showing model selection');
        const container = document.getElementById('chat-container');
        
        this.addMessage('chat-container', 'system', 
            '🤖 Welcome to Chat Mode!\n\nSelect a model to start your conversation:');
        
        const selectionDiv = document.createElement('div');
        selectionDiv.className = 'model-selection';
        selectionDiv.id = 'model-selection-container';
        
        this.availableModels.forEach((model, index) => {
            const button = document.createElement('button');
            button.className = 'model-button';
            button.type = 'button';
            button.dataset.modelName = model.name;
            
            const icon = document.createElement('span');
            icon.textContent = '📦';
            icon.style.fontSize = '1.2em';
            
            const name = document.createElement('span');
            name.textContent = model.name;
            name.style.flex = '1';
            name.style.textAlign = 'left';
            name.style.marginLeft = '10px';
            
            const arrow = document.createElement('span');
            arrow.textContent = '→';
            arrow.style.color = '#666';
            arrow.style.fontSize = '0.9em';
            
            button.appendChild(icon);
            button.appendChild(name);
            button.appendChild(arrow);
            
            // Direct onclick for maximum compatibility
            button.onclick = function() {
                const modelName = this.dataset.modelName;
                console.log('🖱️  Model clicked:', modelName);
                app.selectModel(modelName);
            };
            
            selectionDiv.appendChild(button);
        });
        
        container.appendChild(selectionDiv);
        
        requestAnimationFrame(() => {
            container.scrollTop = container.scrollHeight;
        });
        
        this.updateBackButton();
        console.log('✅ Model selection displayed');
    },
    
    async selectModel(modelName) {
        console.log('🎯 selectModel called with:', modelName);
        
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
                
                console.log('✅ Model initialized:', data);
                
                this.updateChatInfoBar();

                document.getElementById(loadingId)?.remove();
                const modelSelection = document.getElementById('model-selection-container');
                if (modelSelection) {
                    modelSelection.remove();
                }
                
                this.addMessage('chat-container', 'system', 
                    `✅ Connected to ${modelName}\n\n💡 Commands:\n• Type "exit" to select a different model\n• Type "main menu" to return to home`);
                
                const input = document.getElementById('chat-input');
                input.disabled = false;
                input.placeholder = 'Type your message...';
                input.focus();
                
                this.updateBackButton();
            } else {
                const error = await response.json();
                document.getElementById(loadingId)?.remove();
                this.addMessage('chat-container', 'error', '❌ Failed to initialize: ' + error.detail);
            }
        } catch (error) {
            console.error('❌ Error selecting model:', error);
            document.getElementById(loadingId)?.remove();
            this.addMessage('chat-container', 'error', '❌ Error: ' + error.message);
        }
    },
    
    async sendChatMessage(message) {
        const command = message.toLowerCase().trim();
        
        if (command === 'exit') {
            this.currentConversationId = null;
            this.currentModel = null;
            
            const container = document.getElementById('chat-container');
            container.innerHTML = '';

            this.updateChatInfoBar();
            this.showModelSelection();
            
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
        
        this.addMessage('chat-container', 'user', message);
        
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
        
        requestAnimationFrame(() => {
            container.scrollTop = container.scrollHeight;
        });
        
        return messageId;
    },
    
    // =========================================================================
    // NCT Lookup & File Manager
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
            
            progressDiv.classList.add('hidden');
            
            if (data.success) {
                saveBtn.classList.remove('hidden');
            }
            
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
        
        const blob = new Blob([content], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
        
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
            
            this.showMode('chat');
            
            setTimeout(() => {
                const container = document.getElementById('chat-container');
                container.innerHTML = '';
                this.addMessage('chat-container', 'system', 
                    `📄 Loaded file: ${filename} (${(data.content.length / 1024).toFixed(1)} KB)\n\nSelect a model to analyze this file.`);
                
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
        
        event.target.value = '';
    },
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
};

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    console.log('📄 DOM Content Loaded');
    app.init();
});