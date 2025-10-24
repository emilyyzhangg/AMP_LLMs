// ============================================================================
// AMP LLM Enhanced Web Interface - FIXED VERSION
// ✅ Info bar only shows after model selection
// ✅ Chats saved per model during session
// ✅ Clear chat button when model is active
// ✅ Session isolation (backend handles this via conversation IDs)
// ============================================================================

const app = {
    // Configuration
    API_BASE: window.location.origin,
    NCT_SERVICE_URL: 'http://localhost:8002',
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
    availableThemes: [],  // NEW: Dynamic theme list
    
    // Session-based chat storage (per model)
    sessionChats: {},
    
    // =========================================================================
    // Initialization
    // =========================================================================
    
    async init() {
        console.log('🚀 App initializing...');
        this.apiKey = localStorage.getItem('amp_llm_api_key') || '';
        this.currentTheme = localStorage.getItem('amp_llm_theme') || 'green';
        app.apiRegistry = null;
        app.selectedAPIs = new Set();
        // Load available themes dynamically
        await this.loadAvailableThemes();
        
        this.applyTheme(this.currentTheme, false);
        
        if (this.apiKey) {
            console.log('✅ API key found, showing app');
            this.showApp();
        } else {
            console.log('⚠️  No API key, showing auth');
        }
        
        document.addEventListener('click', (e) => {
            const allDropdowns = document.querySelectorAll('.theme-dropdown');
            const allButtons = document.querySelectorAll('.theme-button');
            
            let isButton = false;
            allButtons.forEach(btn => {
                if (btn.contains(e.target)) isButton = true;
            });
            
            if (!isButton) {
                allDropdowns.forEach(dropdown => {
                    if (!dropdown.contains(e.target)) {
                        dropdown.classList.add('hidden');
                    }
                });
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
    // NEW: Dynamic Theme Loading
    // =========================================================================
    
    async loadAvailableThemes() {
        console.log('🎨 Loading available themes...');
        
        try {
            // Try to fetch themes from API
            const response = await fetch(`${this.API_BASE}/api/themes`);
            
            if (response.ok) {
                const data = await response.json();
                this.availableThemes = data.themes || [];
                console.log(`✅ Loaded ${this.availableThemes.length} themes from API`);
            } else {
                console.warn('⚠️  API theme endpoint not available, using fallback');
                this.useFallbackThemes();
            }
        } catch (error) {
            console.warn('⚠️  Failed to load themes from API, using fallback:', error);
            this.useFallbackThemes();
        }
        
        // Build theme dropdown after loading
        this.buildThemeDropdown();
    },
    
    useFallbackThemes() {
        // Fallback to hardcoded themes if API not available
        this.availableThemes = [
            {
                id: 'green',
                name: 'Green Primary',
                colors: ['#1BEB49', '#0E1F81']
            },
            {
                id: 'blue',
                name: 'Blue Primary',
                colors: ['#0E1F81', '#1BEB49']
            },
            {
                id: 'balanced',
                name: 'Tri-Color',
                colors: ['#0E1F81', '#1BEB49', '#FFA400']
            },
            {
                id: 'professional',
                name: 'Professional',
                colors: ['#2C3E50', '#16A085', '#E67E22']
            }
        ];
        console.log('✅ Using fallback themes');
    },
    
    buildThemeDropdown() {
    const dropdowns = [
        document.getElementById('theme-dropdown'),      // Landing header
        document.getElementById('theme-dropdown-2')     // Mode header
    ];
    
    dropdowns.forEach(dropdown => {
        if (!dropdown) return;
        
        // Clear existing options
        dropdown.innerHTML = '';
        
        // Build options from available themes
        this.availableThemes.forEach(theme => {
            const option = document.createElement('div');
            option.className = 'theme-option';
            option.onclick = () => this.setTheme(theme.id);
            
            // Create gradient indicator
            const indicator = document.createElement('div');
            indicator.className = 'theme-indicator';
            
            // Generate CSS gradient from colors array
            if (theme.colors && theme.colors.length > 0) {
                const gradientStops = theme.colors.map((color, idx) => {
                    const position = (idx / (theme.colors.length - 1)) * 100;
                    return `${color} ${position}%`;
                }).join(', ');
                indicator.style.background = `linear-gradient(135deg, ${gradientStops})`;
            }
            
            // Create label
            const label = document.createElement('span');
            label.textContent = theme.name;
            
            option.appendChild(indicator);
            option.appendChild(label);
            dropdown.appendChild(option);
        });
    });
    
    console.log(`✅ Built theme dropdowns with ${this.availableThemes.length} options`);
    this.updateActiveTheme();
},



    // =========================================================================
    // Theme Management - UPDATED for dynamic themes
    // =========================================================================
    
    toggleThemeDropdown() {
        // Close all dropdowns first
        const allDropdowns = document.querySelectorAll('.theme-dropdown');
        allDropdowns.forEach(d => d.classList.add('hidden'));
        
        // Find which button was clicked by checking event
        const clickedButton = event.target.closest('.theme-button');
        if (!clickedButton) return;
        
        // Find the dropdown sibling
        const dropdown = clickedButton.nextElementSibling;
        if (dropdown && dropdown.classList.contains('theme-dropdown')) {
            dropdown.classList.toggle('hidden');
            this.updateActiveTheme();
        }
    },
    
    setTheme(themeId) {
        console.log('🎨 Setting theme:', themeId);
        
        // Validate theme exists
        const theme = this.availableThemes.find(t => t.id === themeId);
        if (!theme) {
            console.error('❌ Theme not found:', themeId);
            return;
        }
        
        this.currentTheme = themeId;
        localStorage.setItem('amp_llm_theme', themeId);
        this.applyTheme(themeId, true);
        document.getElementById('theme-dropdown').classList.add('hidden');
    },
    
    applyTheme(themeId, animate = false) {
        const themeStylesheet = document.getElementById('theme-stylesheet');
        
        // Find theme metadata
        const theme = this.availableThemes.find(t => t.id === themeId);
        const themeName = theme ? theme.name : themeId.charAt(0).toUpperCase() + themeId.slice(1);
        
        // Update stylesheet href
        themeStylesheet.href = `/static/theme-${themeId}.css`;
        
        // Update BOTH theme name displays
        const themeNameElements = [
            document.getElementById('current-theme-name'),    // Landing header
            document.getElementById('current-theme-name-2')   // Mode header
        ];
        
        themeNameElements.forEach(element => {
            if (element) {
                element.textContent = themeName;
            }
        });
        
        this.updateActiveTheme();
        
        if (animate) {
            document.body.style.transition = 'background 0.5s ease';
            setTimeout(() => {
                document.body.style.transition = '';
            }, 500);
        }
        
        console.log(`✅ Applied theme: ${themeName}`);
    },
    
    updateActiveTheme() {
        const options = document.querySelectorAll('.theme-option');
        options.forEach(option => {
            // Check if this option's onclick calls setTheme with current theme
            const isActive = option.onclick && option.onclick.toString().includes(this.currentTheme);
            
            if (isActive) {
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
        // Clear session chats
        this.sessionChats = {};
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

        document.getElementById('landing-header').classList.remove('hidden');
        document.getElementById('app-header').classList.add('hidden');
        document.getElementById('menu-view').classList.remove('hidden');
        
        document.getElementById('main-app').classList.add('on-menu');

        document.querySelectorAll('.mode-container').forEach(el => {
            el.classList.remove('active');
        });
    },
    
    showMode(mode) {
        console.log('🎯 Showing mode:', mode);
        this.currentMode = mode;
        
        document.getElementById('landing-header').classList.add('hidden');
        document.getElementById('app-header').classList.remove('hidden');
        document.getElementById('menu-view').classList.add('hidden');
        
        document.getElementById('main-app').classList.remove('on-menu');

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
        } else if (mode === 'nct') {
            this.buildAPICheckboxes();
        }    
    },
    
    updateBackButton() {
        const backButton = document.querySelector('.back-button');
        
        if (this.currentMode === 'chat' && this.currentConversationId) {
            backButton.textContent = '← Back to Models';
            backButton.onclick = () => {
                // Save current chat before going back
                if (this.currentModel) {
                    this.saveCurrentChat();
                }
                
                this.currentConversationId = null;
                this.currentModel = null;
                
                const container = document.getElementById('chat-container');
                container.innerHTML = '';
                
                // Remove info bar
                this.removeInfoBar();
                
                this.showModelSelection();
                
                const input = document.getElementById('chat-input');
                input.disabled = true;
                input.placeholder = 'Select a model to start chatting...';
                
                this.updateBackButton();
            };
        } else {
            backButton.textContent = '← Back';
            backButton.onclick = () => this.showMenu();
        }
    },
    
    // =========================================================================
    // Chat Mode - WITH SESSION STORAGE
    // =========================================================================
    
    async initializeChatMode() {
        console.log('🚀 Initializing chat mode...');
        
        const container = document.getElementById('chat-container');
        container.innerHTML = '';
        
        // Remove info bar during model selection
        this.removeInfoBar();
        
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

    // NEW: Remove info bar helper
    removeInfoBar() {
        const modeElement = document.getElementById(this.currentMode + '-mode');
        if (modeElement) {
            const existingBar = modeElement.querySelector('.chat-info-bar');
            if (existingBar) {
                existingBar.remove();
                console.log('🗑️  Removed info bar');
            }
        }
    },

    // UPDATED: Only create info bar when model is selected
    ensureChatInfoBar() {
        console.log('📊 Ensuring chat info bar...');
        
        const modeId = this.currentMode + '-mode';
        const modeElement = document.getElementById(modeId);
        
        if (!modeElement) {
            console.error('❌ Mode element not found:', modeId);
            return;
        }
        
        // Check if info bar already exists
        let infoBar = modeElement.querySelector('.chat-info-bar');
        
        if (!infoBar) {
            console.log('➕ Creating new info bar for', this.currentMode);
            
            // Create the info bar element
            infoBar = document.createElement('div');
            infoBar.className = 'chat-info-bar';
            
            // Add to top using prepend
            if (typeof modeElement.prepend === 'function') {
                modeElement.prepend(infoBar);
                console.log('✅ Info bar inserted using prepend()');
            } else {
                // Fallback
                modeElement.appendChild(infoBar);
                if (modeElement.firstChild !== infoBar) {
                    modeElement.insertBefore(infoBar, modeElement.firstChild);
                }
                console.log('✅ Info bar inserted using fallback method');
            }
        } else {
            console.log('✅ Info bar already exists');
        }
        
        // Now update its content
        this.updateChatInfoBar();
    },

    updateChatInfoBar() {
        console.log('🔄 Updating chat info bar...');
        
        const modeElement = document.getElementById(this.currentMode + '-mode');
        if (!modeElement) {
            console.error('❌ Mode element not found for info bar update');
            return;
        }
        
        let infoBar = modeElement.querySelector('.chat-info-bar');
        if (!infoBar) {
            console.warn('⚠️  Info bar not found - not creating during model selection');
            return;
        }
        
        const modelDisplay = this.currentModel || '<em>Not selected</em>';
        const statusClass = this.currentConversationId ? 'chat-info-status-connected' : 'chat-info-status-disconnected';
        const statusText = this.currentConversationId ? '🟢 Connected' : '⚪ Select a model';
        
        const serviceLabel = this.currentMode === 'research' ? 'Research Assistant' : 'Chat with LLM';
        
        // Add clear chat button if model is active
        const clearButton = this.currentConversationId ? 
            `<button class="clear-chat-btn" onclick="app.clearCurrentChat()">🗑️ Clear Chat</button>` : '';
        
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
            ${clearButton}
        `;
        
        console.log('✅ Info bar updated');
    },

    showModelSelection() {
        console.log('📦 Showing model selection');
        console.log('📊 Available models:', this.availableModels);
        
        const container = document.getElementById('chat-container');
        
        this.addMessage('chat-container', 'system', 
            '🤖 Welcome to Chat Mode!\n\nSelect a model to start your conversation:');
        
        const selectionDiv = document.createElement('div');
        selectionDiv.className = 'model-selection';
        selectionDiv.id = 'model-selection-container';
        
        this.availableModels.forEach((model, index) => {
            const modelName = typeof model === 'string' ? model : (model.name || String(model));
            
            console.log(`Creating button for model: ${modelName}`);
            
            const button = document.createElement('button');
            button.className = 'model-button';
            button.type = 'button';
            
            button.setAttribute('data-model-name', modelName);
            
            const icon = document.createElement('span');
            icon.textContent = '📦';
            icon.style.fontSize = '1.2em';
            
            const name = document.createElement('span');
            name.textContent = modelName;
            name.style.flex = '1';
            name.style.textAlign = 'left';
            name.style.marginLeft = '10px';
            
            // Show indicator if this model has saved chat
            const hasChat = this.sessionChats[modelName] && this.sessionChats[modelName].messages.length > 0;
            if (hasChat) {
                const indicator = document.createElement('span');
                indicator.textContent = '💬';
                indicator.style.marginRight = '10px';
                indicator.style.fontSize = '0.9em';
                indicator.title = 'Has active conversation';
                button.appendChild(indicator);
            }
            
            const arrow = document.createElement('span');
            arrow.textContent = '→';
            arrow.style.color = '#666';
            arrow.style.fontSize = '0.9em';
            
            button.appendChild(icon);
            button.appendChild(name);
            button.appendChild(arrow);
            
            button.onclick = function() {
                const selectedModel = this.getAttribute('data-model-name');
                console.log('🖱️  Model clicked:', selectedModel);
                app.selectModel(selectedModel);
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
    
    // NEW: Save current chat to session storage
    saveCurrentChat() {
        if (!this.currentModel) return;
        
        const container = document.getElementById('chat-container');
        const messages = [];
        
        // Extract all messages except system and model selection
        container.querySelectorAll('.message').forEach(msg => {
            const role = msg.classList.contains('user') ? 'user' : 
                        msg.classList.contains('assistant') ? 'assistant' : 
                        msg.classList.contains('system') ? 'system' : 'error';
            
            // Skip system messages
            if (role === 'system' || role === 'error') return;
            
            const contentEl = msg.querySelector('.content');
            if (contentEl) {
                messages.push({
                    role: role,
                    content: contentEl.textContent,
                    messageId: msg.id
                });
            }
        });
        
        this.sessionChats[this.currentModel] = {
            conversationId: this.currentConversationId,
            messages: messages
        };
        
        console.log(`💾 Saved ${messages.length} messages for ${this.currentModel}`);
    },
    
    // NEW: Restore chat from session storage
    restoreChat(modelName) {
        const saved = this.sessionChats[modelName];
        if (!saved || saved.messages.length === 0) {
            console.log('📭 No saved chat for', modelName);
            return false;
        }
        
        console.log(`📥 Restoring ${saved.messages.length} messages for ${modelName}`);
        
        const container = document.getElementById('chat-container');
        container.innerHTML = '';
        
        // Restore all messages
        saved.messages.forEach(msg => {
            this.addMessage('chat-container', msg.role, msg.content);
        });
        
        // Use saved conversation ID
        this.currentConversationId = saved.conversationId;
        
        return true;
    },
    
    // NEW: Clear current chat
    async clearCurrentChat() {
        if (!this.currentModel || !this.currentConversationId) return;
        
        const confirmed = confirm(`Clear all chat history with ${this.currentModel}?\n\nThis will:\n• Delete all messages in this session\n• Reset the model's memory\n• Start a fresh conversation`);
        
        if (!confirmed) return;
        
        console.log('🗑️  Clearing chat for', this.currentModel);
        
        // Delete conversation on backend
        try {
            await fetch(`${this.API_BASE}/chat/conversations/${this.currentConversationId}`, {
                method: 'DELETE',
                headers: {
                    'Authorization': `Bearer ${this.apiKey}`
                }
            });
            console.log('✅ Backend conversation deleted');
        } catch (error) {
            console.error('⚠️  Failed to delete backend conversation:', error);
        }
        
        // Clear from session storage
        delete this.sessionChats[this.currentModel];
        
        // Clear UI
        const container = document.getElementById('chat-container');
        container.innerHTML = '';
        
        // Re-initialize with same model
        const modelName = this.currentModel;
        this.currentConversationId = null;
        this.currentModel = null;
        
        this.addMessage('chat-container', 'system', '🔄 Reinitializing conversation...');
        
        setTimeout(() => {
            this.selectModel(modelName);
        }, 500);
    },
    
    async selectModel(modelName) {
        console.log('🎯 selectModel called with:', modelName);
        
        // Check if we have a saved chat for this model
        const hasSavedChat = this.sessionChats[modelName] && 
                            this.sessionChats[modelName].messages.length > 0;
        
        if (hasSavedChat) {
            console.log('📥 Restoring saved chat for', modelName);
            
            // Clear model selection UI
            const modelSelection = document.getElementById('model-selection-container');
            if (modelSelection) {
                modelSelection.remove();
            }
            
            // Restore the chat
            this.currentModel = modelName;
            this.restoreChat(modelName);
            
            // Create info bar now that model is selected
            this.ensureChatInfoBar();
            
            // Enable input
            const input = document.getElementById('chat-input');
            input.disabled = false;
            input.placeholder = 'Type your message...';
            input.focus();
            
            this.updateBackButton();
            
            // Add welcome back message
            this.addMessage('chat-container', 'system', 
                `✅ Resumed conversation with ${modelName}\n\n💡 Commands:\n• Click "Clear Chat" to reset\n• Click "Back to Models" to switch models`);
            
            return;
        }
        
        // No saved chat - initialize new conversation
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
            
            console.log('📥 Init response status:', response.status);
            
            if (response.ok) {
                let data;
                try {
                    const responseText = await response.text();
                    console.log('📄 Response text:', responseText.substring(0, 200));
                    data = JSON.parse(responseText);
                } catch (parseError) {
                    console.error('❌ JSON parse error:', parseError);
                    document.getElementById(loadingId)?.remove();
                    this.addMessage('chat-container', 'error', 
                        `❌ Failed to parse server response\n\n` +
                        `The server returned invalid JSON. This usually means:\n` +
                        `1. The chat service is returning HTML instead of JSON\n` +
                        `2. There's a server error\n\n` +
                        `Error: ${parseError.message}`);
                    return;
                }
                
                this.currentConversationId = data.conversation_id;
                this.currentModel = modelName;
                
                console.log('✅ Model initialized:', data);
                
                // Create info bar now that model is selected
                this.ensureChatInfoBar();

                document.getElementById(loadingId)?.remove();
                const modelSelection = document.getElementById('model-selection-container');
                if (modelSelection) {
                    modelSelection.remove();
                }
                
                this.addMessage('chat-container', 'system', 
                    `✅ Connected to ${modelName}\n\n💡 Commands:\n• Type "exit" to select a different model\n• Type "main menu" to return to home\n• Click "Clear Chat" to reset conversation`);
                
                const input = document.getElementById('chat-input');
                input.disabled = false;
                input.placeholder = 'Type your message...';
                input.focus();
                
                this.updateBackButton();
            } else {
                let errorMessage;
                try {
                    const errorText = await response.text();
                    console.log('❌ Error response:', errorText);
                    const errorData = JSON.parse(errorText);
                    errorMessage = errorData.detail || errorText;
                } catch (e) {
                    errorMessage = `HTTP ${response.status} - ${response.statusText}`;
                }
                
                document.getElementById(loadingId)?.remove();
                this.addMessage('chat-container', 'error', 
                    `❌ Failed to initialize ${modelName}\n\n` +
                    `Error: ${errorMessage}\n\n` +
                    `Possible issues:\n` +
                    `• Model name contains special characters\n` +
                    `• Chat service can't access this model\n` +
                    `• Ollama is not responding\n\n` +
                    `Try a different model or check the server logs.`);
            }
        } catch (error) {
            console.error('❌ Exception selecting model:', error);
            document.getElementById(loadingId)?.remove();
            this.addMessage('chat-container', 'error', 
                `❌ Connection Error\n\n` +
                `Failed to communicate with the chat service.\n\n` +
                `Error: ${error.message}\n\n` +
                `Make sure the chat service is running on port 8001.`);
        }
    },
    
    async sendChatMessage(message) {
        const command = message.toLowerCase().trim();
        
        if (command === 'exit') {
            // Save before exiting
            if (this.currentModel) {
                this.saveCurrentChat();
            }
            
            this.currentConversationId = null;
            this.currentModel = null;
            
            const container = document.getElementById('chat-container');
            container.innerHTML = '';

            this.removeInfoBar();
            this.showModelSelection();
            
            const input = document.getElementById('chat-input');
            input.disabled = true;
            input.placeholder = 'Select a model to start chatting...';
            return;
        }
        
        if (command === 'main menu') {
            // Save before exiting
            if (this.currentModel) {
                this.saveCurrentChat();
            }
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
            console.log('📤 Sending message to chat service');
            
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
            
            console.log('📥 Response status:', response.status);
            
            document.getElementById(loadingId)?.remove();
            
            if (response.ok) {
                let data;
                try {
                    const responseText = await response.text();
                    console.log('📄 Response (first 200 chars):', responseText.substring(0, 200));
                    
                    if (responseText.trim().startsWith('<')) {
                        this.addMessage('chat-container', 'error', 
                            `❌ Server returned HTML instead of JSON\n\n` +
                            `Check console for details.`);
                        console.error('Full response:', responseText);
                        return;
                    }
                    
                    data = JSON.parse(responseText);
                } catch (parseError) {
                    this.addMessage('chat-container', 'error', 
                        `❌ JSON Parse Error: ${parseError.message}\n\n` +
                        `Check console for the full response.`);
                    return;
                }
                
                if (data.message && data.message.content) {
                    this.addMessage('chat-container', 'assistant', data.message.content);
                    
                    // Auto-save after successful exchange
                    this.saveCurrentChat();
                } else {
                    this.addMessage('chat-container', 'error', 
                        `❌ Invalid response structure\n\n` +
                        `Expected message.content but got: ${JSON.stringify(data).substring(0, 100)}`);
                }
            } else {
                let errorMessage;
                try {
                    const errorText = await response.text();
                    const errorData = JSON.parse(errorText);
                    errorMessage = errorData.detail || JSON.stringify(errorData);
                } catch (e) {
                    errorMessage = `HTTP ${response.status}`;
                }
                this.addMessage('chat-container', 'error', `❌ Error: ${errorMessage}`);
            }
        } catch (error) {
            document.getElementById(loadingId)?.remove();
            this.addMessage('chat-container', 'error', `❌ Error: ${error.message}`);
            console.error('Full error:', error);
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

    // ============================================================================
    // Load API Registry
    // ============================================================================

    async loadAPIRegistry() {
        console.log('📚 Loading API registry from:', this.NCT_SERVICE_URL);
        
        try {
            const url = `${this.NCT_SERVICE_URL}/api/registry`;
            console.log('Fetching:', url);
            
            const response = await fetch(url, {
                method: 'GET',
                headers: { 
                    'Authorization': `Bearer ${this.apiKey}`,
                    'Content-Type': 'application/json'
                }
            });
            
            console.log('Registry response status:', response.status);
            
            if (!response.ok) {
                const errorText = await response.text();
                console.error('Registry error response:', errorText);
                throw new Error(`HTTP ${response.status}: ${errorText}`);
            }
            
            this.apiRegistry = await response.json();
            console.log('✅ API registry loaded:', this.apiRegistry);
            
            // Initialize selected APIs with defaults
            if (this.apiRegistry.metadata?.default_enabled) {
                this.selectedAPIs = new Set(this.apiRegistry.metadata.default_enabled);
            } else {
                // Fallback
                this.selectedAPIs = new Set();
                [...this.apiRegistry.core, ...this.apiRegistry.extended].forEach(api => {
                    if (api.enabled_by_default) {
                        this.selectedAPIs.add(api.id);
                    }
                });
            }
            
            console.log('Selected APIs:', Array.from(this.selectedAPIs));
            return this.apiRegistry;
            
        } catch (error) {
            console.error('❌ Failed to load API registry:', error);
            
            // Use fallback registry
            this.apiRegistry = {
                core: [
                    { id: 'clinicaltrials', name: 'ClinicalTrials.gov', description: 'Primary trial registry', enabled_by_default: true, available: true },
                    { id: 'pubmed', name: 'PubMed', description: 'Biomedical literature', enabled_by_default: true, available: true },
                    { id: 'pmc', name: 'PMC', description: 'Full-text articles', enabled_by_default: true, available: true },
                    { id: 'pmc_bioc', name: 'PMC BioC', description: 'Annotated full-text', enabled_by_default: true, available: true }
                ],
                extended: [
                    { id: 'duckduckgo', name: 'DuckDuckGo', description: 'Web search', enabled_by_default: false, available: true },
                    { id: 'serpapi', name: 'Google Search', description: 'Google results', enabled_by_default: false, available: false, requires_key: true },
                    { id: 'scholar', name: 'Google Scholar', description: 'Academic papers', enabled_by_default: false, available: false, requires_key: true },
                    { id: 'openfda', name: 'OpenFDA', description: 'FDA drug data', enabled_by_default: false, available: true }
                ],
                metadata: {
                    default_enabled: ['clinicaltrials', 'pubmed', 'pmc', 'pmc_bioc']
                }
            };
            
            this.selectedAPIs = new Set(this.apiRegistry.metadata.default_enabled);
            return this.apiRegistry;
        }
    },
    // ============================================================================
    // Build API Checkboxes Dynamically
    // ============================================================================

    async buildAPICheckboxes() {
        console.log('🏗️  Building API checkboxes...');
        
        // Load registry if not already loaded
        if (!this.apiRegistry) {
            await this.loadAPIRegistry();
        }
        
        // Build core APIs
        const coreContainer = document.getElementById('core-apis-container');
        if (coreContainer) {
            coreContainer.innerHTML = '';
            
            this.apiRegistry.core.forEach(api => {
                const checkboxItem = this.createAPICheckbox(api, 'core');
                coreContainer.appendChild(checkboxItem);
            });
            
            console.log(`✅ Built ${this.apiRegistry.core.length} core API checkboxes`);
        }
        
        // Build extended APIs
        const extendedContainer = document.getElementById('extended-apis-container');
        if (extendedContainer) {
            extendedContainer.innerHTML = '';
            
            this.apiRegistry.extended.forEach(api => {
                const checkboxItem = this.createAPICheckbox(api, 'extended');
                extendedContainer.appendChild(checkboxItem);
            });
            
            console.log(`✅ Built ${this.apiRegistry.extended.length} extended API checkboxes`);
        }
    },

createAPICheckbox(api, category) {
    const item = document.createElement('div');
    item.className = 'api-checkbox-item';
    
    // Disable if API is not available (missing key)
    if (!api.available) {
        item.classList.add('disabled');
    }
    
    // Checkbox input
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.id = `api-${api.id}`;
    checkbox.value = api.id;
    checkbox.checked = this.selectedAPIs.has(api.id);
    checkbox.disabled = !api.available;
    
    // Handle checkbox change
    checkbox.addEventListener('change', (e) => {
        if (e.target.checked) {
            this.selectedAPIs.add(api.id);
        } else {
            this.selectedAPIs.delete(api.id);
        }
        console.log('Selected APIs:', Array.from(this.selectedAPIs));
    });
    
    // Label
    const label = document.createElement('label');
    label.className = 'api-checkbox-label';
    label.htmlFor = `api-${api.id}`;
    
    // Name with badges
    const nameDiv = document.createElement('div');
    nameDiv.className = 'api-checkbox-name';
    nameDiv.textContent = api.name;
    
    // Add status badges
    if (api.requires_key && !api.available) {
        const badge = document.createElement('span');
        badge.className = 'api-status-badge unavailable';
        badge.textContent = '🔑 Key Required';
        nameDiv.appendChild(badge);
    } else if (api.requires_key) {
        const badge = document.createElement('span');
        badge.className = 'api-status-badge requires-key';
        badge.textContent = '🔑 API Key';
        nameDiv.appendChild(badge);
    }
    
    // Description
    const descDiv = document.createElement('div');
    descDiv.className = 'api-checkbox-desc';
    descDiv.textContent = api.description;
    
    label.appendChild(nameDiv);
    label.appendChild(descDiv);
    
    item.appendChild(checkbox);
    item.appendChild(label);
    
    return item;
},

    // ============================================================================
    // Updated NCT Lookup Handler
    // ============================================================================

    async handleNCTLookup() {
        const input = document.getElementById('nct-input');
        const nctIds = input.value.split(',').map(s => s.trim().toUpperCase()).filter(s => s);
        
        if (nctIds.length === 0) {
            alert('Please enter at least one NCT number');
            return;
        }
        
        // Ensure API registry is loaded
        if (!this.apiRegistry) {
            await this.loadAPIRegistry();
        }
        
        const resultsDiv = document.getElementById('nct-results');
        const progressDiv = document.getElementById('nct-progress');
        const saveBtn = document.getElementById('nct-save-btn');
        const inputArea = document.querySelector('.nct-input-area');
    
        // Hide input area, show results area
        inputArea.classList.add('hidden');
        resultsDiv.classList.add('active');

        progressDiv.classList.remove('hidden');
        progressDiv.innerHTML = '<span class="spinner"></span> <span>Fetching clinical trial data...</span>';
        resultsDiv.innerHTML = '';
        saveBtn.classList.add('hidden');
        
        // Get selected APIs
        const selectedAPIList = Array.from(this.selectedAPIs);
        
        console.log('🔍 Starting NCT lookup with APIs:', selectedAPIList);
        
        const results = [];
        const errors = [];
        const searchJobs = {};
        
        try {
            const NCT_SERVICE_URL = 'http://localhost:8002';
            
            async function makeRequest(url, options) {
                const response = await fetch(url, options);
                if (!response.ok) {
                    const errorText = await response.text();
                    throw new Error(`HTTP ${response.status}: ${errorText}`);
                }
                return response.json();
            }
            
            // Initiate searches for each NCT number
            for (const nctId of nctIds) {
                try {
                    const searchRequest = {
                        include_extended: false, // Not used anymore
                        databases: selectedAPIList  // Send selected databases
                    };
                    
                    const data = await makeRequest(
                        `${NCT_SERVICE_URL}/api/search/${nctId}`,
                        {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'Authorization': `Bearer ${this.apiKey}`
                            },
                            body: JSON.stringify(searchRequest)
                        }
                    );
                    
                    searchJobs[nctId] = data.job_id;
                    console.log(`✅ Initiated search for ${nctId}: ${data.status}`);
                    
                } catch (error) {
                    console.error(`❌ Error initiating search for ${nctId}:`, error);
                    errors.push({
                        nct_id: nctId,
                        error: error.message
                    });
                }
            }
            
            // Poll for results
            const maxWait = 300000; // 5 minutes
            const pollInterval = 2000; // 2 seconds
            const startTime = Date.now();
            
            while (Object.keys(searchJobs).length > 0 && (Date.now() - startTime) < maxWait) {
                const completedJobs = [];
                
                for (const [nctId, jobId] of Object.entries(searchJobs)) {
                    try {
                        const statusData = await makeRequest(
                            `${NCT_SERVICE_URL}/api/search/${jobId}/status`,
                            {
                                headers: { 'Authorization': `Bearer ${this.apiKey}` }
                            }
                        );
                        
                        // Update progress display
                        if (statusData.current_database) {
                            const apiDef = this.apiRegistry.core.find(a => a.id === statusData.current_database) ||
                                        this.apiRegistry.extended.find(a => a.id === statusData.current_database);
                            const apiName = apiDef ? apiDef.name : statusData.current_database;
                            
                            progressDiv.innerHTML = `
                                <span class="spinner"></span>
                                <span>Processing ${nctId}: ${apiName} (${statusData.progress}%)</span>
                            `;
                        }
                        
                        if (statusData.status === 'completed') {
                            const resultData = await makeRequest(
                                `${NCT_SERVICE_URL}/api/results/${jobId}`,
                                {
                                    headers: { 'Authorization': `Bearer ${this.apiKey}` }
                                }
                            );
                            
                            results.push(resultData);
                            completedJobs.push(nctId);
                            console.log(`✅ Retrieved results for ${nctId}`);
                            
                        } else if (statusData.status === 'failed') {
                            errors.push({
                                nct_id: nctId,
                                error: statusData.error || 'Search failed'
                            });
                            completedJobs.push(nctId);
                        }
                        
                    } catch (error) {
                        console.error(`❌ Error checking status for ${nctId}:`, error);
                        errors.push({
                            nct_id: nctId,
                            error: error.message
                        });
                        completedJobs.push(nctId);
                    }
                }
                
                // Remove completed jobs
                completedJobs.forEach(nctId => {
                    delete searchJobs[nctId];
                });
                
                // Wait before next poll
                if (Object.keys(searchJobs).length > 0) {
                    await new Promise(resolve => setTimeout(resolve, pollInterval));
                }
            }
            
            // Handle timeouts
            for (const nctId of Object.keys(searchJobs)) {
                errors.push({
                    nct_id: nctId,
                    error: 'Search timeout'
                });
            }
            
            progressDiv.classList.add('hidden');
            
            if (results.length > 0) {
                this.addNewSearchButton();
                this.nctResults = {
                    success: true,
                    results: results,
                    summary: {
                        total_requested: nctIds.length,
                        successful: results.length,
                        failed: errors.length,
                        errors: errors.length > 0 ? errors : null
                    }
                
                };
                
                saveBtn.classList.remove('hidden');
                this.displayNCTResults(this.nctResults);
            } else {
                resultsDiv.innerHTML = `
                    <div class="result-card">
                        <h3>No Results</h3>
                        <p>No trials could be fetched. Check errors below:</p>
                        <pre>${JSON.stringify(errors, null, 2)}</pre>
                    </div>
                `;
            }
            
        } catch (error) {
            console.error('❌ NCT lookup error:', error);
            progressDiv.classList.add('hidden');
            resultsDiv.innerHTML = `
                <div class="result-card">
                    <h3>Error</h3>
                    <p>${this.escapeHtml(error.message)}</p>
                </div>
            `;
        }
    },

    addNewSearchButton() {
        const resultsDiv = document.getElementById('nct-results');
        
        // Check if button already exists
        if (resultsDiv.querySelector('.nct-new-search-btn')) {
            return;
        }
        
        const buttonBar = document.createElement('div');
        buttonBar.className = 'nct-new-search-btn';
        buttonBar.innerHTML = `
            <button onclick="app.startNewNCTSearch()" style="background: linear-gradient(135deg, #1BEB49 0%, #17C93E 100%);">
                <span>🔍</span>
                <span>New Search</span>
            </button>
            <button onclick="app.saveNCTResults()" style="background: linear-gradient(135deg, #FFA400 0%, #FF8C00 100%);">
                <span>💾</span>
                <span>Save Results</span>
            </button>
        `;
        
        // Insert at the beginning of results
        resultsDiv.insertBefore(buttonBar, resultsDiv.firstChild);
    },

    // Add this new function
    startNewNCTSearch() {
        const inputArea = document.querySelector('.nct-input-area');
        const resultsDiv = document.getElementById('nct-results');
        const progressDiv = document.getElementById('nct-progress');
        
        // Clear input
        document.getElementById('nct-input').value = '';
        
        // Show input area, hide results
        inputArea.classList.remove('hidden');
        resultsDiv.classList.remove('active');
        resultsDiv.innerHTML = '';
        progressDiv.classList.add('hidden');
        
        // Scroll to top
        inputArea.scrollTop = 0;
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
            
            // ====================================================================
            // ROBUST COUNT EXTRACTION - Tries multiple approaches
            // ====================================================================
            
            let pubmedCount = 0;
            let pmcCount = 0;
            let pmcBiocCount = 0;
            
            // Try to get PubMed count from multiple possible locations
            try {
                if (result.sources?.pubmed?.data?.pmids) {
                    pubmedCount = result.sources.pubmed.data.pmids.length;
                } else if (result.sources?.pubmed?.data?.total_found) {
                    pubmedCount = result.sources.pubmed.data.total_found;
                } else if (result.sources?.pubmed?.data?.articles) {
                    pubmedCount = result.sources.pubmed.data.articles.length;
                }
            } catch (e) {
                console.error('Error getting PubMed count:', e);
            }
            
            // Try to get PMC count from multiple possible locations
            try {
                if (result.sources?.pmc?.data?.pmcids) {
                    pmcCount = result.sources.pmc.data.pmcids.length;
                } else if (result.sources?.pmc?.data?.total_found) {
                    pmcCount = result.sources.pmc.data.total_found;
                } else if (result.sources?.pmc?.data?.articles) {
                    pmcCount = result.sources.pmc.data.articles.length;
                }
            } catch (e) {
                console.error('Error getting PMC count:', e);
            }
            
            // Try to get PMC BioC count
            try {
                if (result.sources?.pmc_bioc?.data?.total_fetched) {
                    pmcBiocCount = result.sources.pmc_bioc.data.total_fetched;
                } else if (result.sources?.pmc_bioc?.data?.articles) {
                    pmcBiocCount = result.sources.pmc_bioc.data.articles.length;
                }
            } catch (e) {
                console.error('Error getting PMC BioC count:', e);
            }
            
            // Log what we found for debugging
            console.log(`${result.nct_id} counts:`, {
                pubmed: pubmedCount,
                pmc: pmcCount,
                pmc_bioc: pmcBiocCount,
                sources_available: result.sources ? Object.keys(result.sources) : []
            });
                        
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
                            <div style="color: #666; font-size: 0.9em;">PubMed Articles</div>
                            <strong style="font-size: 1.2em; color: ${pubmedCount > 0 ? '#28a745' : '#999'}">${pubmedCount}</strong>
                        </div>
                        <div class="meta-item">
                            <div style="color: #666; font-size: 0.9em;">PMC Articles</div>
                            <strong style="font-size: 1.2em; color: ${pmcCount > 0 ? '#28a745' : '#999'}">${pmcCount}</strong>
                        </div>
                        <div class="meta-item">
                            <div style="color: #666; font-size: 0.9em;">PMC BioC Articles</div>
                            <strong style="font-size: 1.2em; color: ${pmcBiocCount > 0 ? '#28a745' : '#999'}">${pmcBiocCount}</strong>
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