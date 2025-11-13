// ============================================================================
// AMP LLM Enhanced Web Interface - COMPLETE WORKING VERSION
// ============================================================================

const app = {
    // Configuration
    API_BASE: window.location.origin,
    NCT_SERVICE_URL: window.location.origin,

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
    availableThemes: [],

    // Session-based chat storage (per model)
    sessionChats: {},

    nct2step: {
        currentNCT: null,
        step1Results: null,
        step2Results: null,
        selectedAPIs: new Set(),
        selectedFields: {}
    },

    // API registry
    apiRegistry: null,
    selectedAPIs: new Set(),

    // =========================================================================
    // Initialization
    // =========================================================================

    async init() {
        console.log('🚀 App initializing...');
        this.apiKey = localStorage.getItem('amp_llm_api_key') || '';
        this.currentTheme = localStorage.getItem('amp_llm_theme') || 'green';

        // ============================================================================
        // SERVICE CONFIGURATION LOGGING
        // ============================================================================
        console.group('🔧 Service Configuration');
        console.log('🌐 API Base URL:', this.API_BASE);
        console.log('🔍 NCT Service URL:', this.NCT_SERVICE_URL);
        console.log('📍 Current Hostname:', window.location.hostname);
        console.log('🔗 Current Origin:', window.location.origin);
        console.log('🔌 Current Port:', window.location.port || '(default)');
        console.groupEnd();
        
        await this.loadAvailableThemes();
        this.applyTheme(this.currentTheme, false);
        
        if (this.apiKey) {
            console.log('✅ API key found, showing app');
            this.showApp();
        } else {
            console.log('⚠️  No API key, showing auth');
        }
        
        // Global click handler for theme dropdowns
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

        // Enter key handlers
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
    // Dynamic Theme Loading
    // =========================================================================

    async loadAvailableThemes() {
        console.log('🎨 Loading available themes...');
        
        try {
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
        
        this.buildThemeDropdown();
    },

    useFallbackThemes() {
        this.availableThemes = [
            { id: 'green', name: 'Green Primary', colors: ['#1BEB49', '#0E1F81'] },
            { id: 'blue', name: 'Blue Primary', colors: ['#0E1F81', '#1BEB49'] },
            { id: 'balanced', name: 'Tri-Color', colors: ['#0E1F81', '#1BEB49', '#FFA400'] },
            { id: 'professional', name: 'Professional', colors: ['#2C3E50', '#16A085', '#E67E22'] }
        ];
        console.log('✅ Using fallback themes');
    },

    buildThemeDropdown() {
        const dropdowns = [
            document.getElementById('theme-dropdown'),
            document.getElementById('theme-dropdown-2')
        ];
        
        dropdowns.forEach(dropdown => {
            if (!dropdown) return;
            
            dropdown.innerHTML = '';
            
            this.availableThemes.forEach(theme => {
                const option = document.createElement('div');
                option.className = 'theme-option';
                option.onclick = () => this.setTheme(theme.id);
                
                const indicator = document.createElement('div');
                indicator.className = 'theme-indicator';
                
                if (theme.colors && theme.colors.length > 0) {
                    const gradientStops = theme.colors.map((color, idx) => {
                        const position = (idx / (theme.colors.length - 1)) * 100;
                        return `${color} ${position}%`;
                    }).join(', ');
                    indicator.style.background = `linear-gradient(135deg, ${gradientStops})`;
                }
                
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
    // Theme Management
    // =========================================================================

    toggleThemeDropdown() {
        const allDropdowns = document.querySelectorAll('.theme-dropdown');
        allDropdowns.forEach(d => d.classList.add('hidden'));
        
        const clickedButton = event.target.closest('.theme-button');
        if (!clickedButton) return;
        
        const dropdown = clickedButton.nextElementSibling;
        if (dropdown && dropdown.classList.contains('theme-dropdown')) {
            dropdown.classList.toggle('hidden');
            this.updateActiveTheme();
        }
    },

    setTheme(themeId) {
        console.log('🎨 Setting theme:', themeId);
        
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
        
        const theme = this.availableThemes.find(t => t.id === themeId);
        const themeName = theme ? theme.name : themeId.charAt(0).toUpperCase() + themeId.slice(1);
        
        themeStylesheet.href = `/static/theme-${themeId}.css`;
        
        const themeNameElements = [
            document.getElementById('current-theme-name'),
            document.getElementById('current-theme-name-2')
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
            'research': { title: '🔬 Research Assistant', subtitle: 'Automated clinical trial annotation' },
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
            this.initializeResearchMode();  // ← ADD THIS LINE
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
                
                this.updateBackButton();
            };
        } else {
            backButton.textContent = '← Back';
            backButton.onclick = () => this.showMenu();
        }
    },
    // ============================================================================
    // STEP 1: Core API Search
    // ============================================================================

    async executeStep1() {
        const input = document.getElementById('nct2step-input');
        const nctId = input.value.trim().toUpperCase();
        
        if (!nctId) {
            alert('Please enter an NCT number');
            return;
        }
        
        // Validate NCT format
        if (!nctId.startsWith('NCT') || nctId.length !== 11) {
            alert('Invalid NCT format. Expected: NCT followed by 8 digits (e.g., NCT03936426)');
            return;
        }
        
        this.nct2step.currentNCT = nctId;
        
        // Show progress
        const progressDiv = document.getElementById('nct2step-step1-progress');
        progressDiv.classList.remove('hidden');
        progressDiv.classList.add('step-progress');
        progressDiv.innerHTML = `
            <span class="progress-spinner"></span>
            <strong>Step 1 in progress...</strong> Searching core APIs (ClinicalTrials, PubMed, PMC, PMC BioC)
        `;
        
        console.log('🔬 Starting Step 1 for:', nctId);
        
        try {
            const response = await fetch(`${this.API_BASE}/api/nct-2step/step1/${nctId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-API-Key': this.apiKey
                }
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || `HTTP ${response.status}`);
            }
            
            const results = await response.json();
            this.nct2step.step1Results = results;
            
            console.log('✅ Step 1 complete:', results);
            
            // Hide progress
            progressDiv.classList.add('hidden');
            
            // Hide input area, show results
            document.getElementById('nct2step-step1-area').classList.add('hidden');
            document.getElementById('nct2step-step1-results').classList.remove('hidden');
            
            // Display Step 1 results
            this.displayStep1Results(results);
            
            // Load extended APIs for Step 2
            await this.loadExtendedAPIs();
            
        } catch (error) {
            console.error('❌ Step 1 error:', error);
            progressDiv.innerHTML = `
                <span style="color: #dc3545;">❌ <strong>Step 1 failed:</strong> ${error.message}</span>
            `;
            
            // Show error toast
            this.showToast('Step 1 search failed: ' + error.message, 'error');
        }
    },

    displayStep1Results(results) {
        const container = document.getElementById('nct2step-step1-data');
        
        const metadata = results.metadata || {};
        const coreAPIs = results.core_apis || {};
        const summary = results.summary || {};
        
        let html = `
            <!-- Trial Metadata -->
            <div class="step1-result-card">
                <div class="step1-result-header">
                    <h3 class="step1-result-title">${results.nct_id}</h3>
                    <span class="step1-result-badge">${summary.total_results || 0} Results</span>
                </div>
                
                <div class="step1-metadata">
                    <div class="metadata-item">
                        <div class="metadata-label">Title</div>
                        <div class="metadata-value">${metadata.title || 'N/A'}</div>
                    </div>
                    <div class="metadata-item">
                        <div class="metadata-label">Status</div>
                        <div class="metadata-value">${metadata.status || 'N/A'}</div>
                    </div>
                    <div class="metadata-item">
                        <div class="metadata-label">Condition</div>
                        <div class="metadata-value">${this.formatArrayOrString(metadata.condition)}</div>
                    </div>
                    <div class="metadata-item">
                        <div class="metadata-label">Intervention</div>
                        <div class="metadata-value">${this.formatArrayOrString(metadata.intervention)}</div>
                    </div>
                </div>
                
                <!-- API Results Summary -->
                <div class="api-results-table">
                    <h4 style="margin-bottom: 15px; color: #2C3E50;">Core API Results</h4>
        `;
        
        // Display results from each core API
        for (const [apiName, apiData] of Object.entries(coreAPIs)) {
            if (!apiData.success) {
                html += `
                    <div class="api-results-row" style="background: #FFF3CD; border-left: 4px solid #FFC107;">
                        <div class="api-name">${this.formatAPIName(apiName)}</div>
                        <div class="api-searches-list" style="color: #856404;">
                            ❌ Error: ${apiData.error || 'Unknown error'}
                        </div>
                        <div class="api-result-count" style="color: #856404;">0</div>
                    </div>
                `;
                continue;
            }
            
            const searches = apiData.searches || [];
            const totalResults = apiData.total_results || 0;
            
            const searchSummary = searches.map(s => 
                `${s.search_type}: ${s.results_count} results`
            ).join('<br>');
            
            html += `
                <div class="api-results-row">
                    <div class="api-name">${this.formatAPIName(apiName)}</div>
                    <div class="api-searches-list">
                        ${searches.length} searches performed<br>
                        <small>${searchSummary}</small>
                    </div>
                    <div class="api-result-count">${totalResults}</div>
                </div>
            `;
        }
        
        html += `
                </div>
            </div>
            
            <!-- Summary Stats -->
            <div class="summary-stats">
                <div class="summary-stat">
                    <div class="summary-stat-number">${summary.core_apis_searched?.length || 0}</div>
                    <div class="summary-stat-label">APIs Searched</div>
                </div>
                <div class="summary-stat">
                    <div class="summary-stat-number">${summary.total_searches || 0}</div>
                    <div class="summary-stat-label">Total Searches</div>
                </div>
                <div class="summary-stat">
                    <div class="summary-stat-number">${summary.total_results || 0}</div>
                    <div class="summary-stat-label">Results Found</div>
                </div>
            </div>
        `;
        
        container.innerHTML = html;
    },

    formatAPIName(apiName) {
        const names = {
            'clinicaltrials': 'ClinicalTrials.gov',
            'pubmed': 'PubMed',
            'pmc': 'PMC',
            'pmc_bioc': 'PMC BioC'
        };
        return names[apiName] || apiName;
    },

    formatArrayOrString(value) {
        if (!value) return 'N/A';
        if (Array.isArray(value)) {
            return value.join(', ') || 'N/A';
        }
        return value;
    },

    // ============================================================================
    // STEP 2: Extended API Selection
    // ============================================================================

    async loadExtendedAPIs() {
        console.log('📡 Loading extended APIs registry...');
        
        try {
            const response = await fetch(`${this.API_BASE}/api/nct-2step/registry`, {
                headers: { 'X-API-Key': this.apiKey }
            });
            
            if (!response.ok) throw new Error('Failed to load API registry');
            
            const registry = await response.json();
            const extendedAPIs = registry.extended || [];
            
            console.log('✅ Loaded', extendedAPIs.length, 'extended APIs');
            
            this.renderExtendedAPICheckboxes(extendedAPIs);
            
        } catch (error) {
            console.error('❌ Error loading extended APIs:', error);
            document.getElementById('nct2step-extended-apis-container').innerHTML = `
                <div style="color: #dc3545; padding: 20px; text-align: center;">
                    Failed to load extended APIs: ${error.message}
                </div>
            `;
        }
    },

    renderExtendedAPICheckboxes(apis) {
        const container = document.getElementById('nct2step-extended-apis-container');
        
        let html = '';
        
        for (const api of apis) {
            const disabled = !api.available;
            const disabledClass = disabled ? 'disabled' : '';
            
            html += `
                <div class="api-checkbox-item ${disabledClass}" data-api-id="${api.id}">
                    <input 
                        type="checkbox" 
                        id="ext-api-${api.id}" 
                        value="${api.id}"
                        ${disabled ? 'disabled' : ''}
                        onchange="app.handleExtendedAPISelection('${api.id}', this.checked)"
                    />
                    <label class="api-checkbox-label" for="ext-api-${api.id}">
                        <div class="api-checkbox-name">
                            ${api.name}
                            ${api.requires_key && !api.available ? 
                                '<span class="api-status-badge unavailable">🔑 Key Required</span>' : 
                                ''}
                        </div>
                        <div class="api-checkbox-desc">${api.description}</div>
                    </label>
                </div>
            `;
        }
        
        container.innerHTML = html;
    },

    handleExtendedAPISelection(apiId, checked) {
        if (checked) {
            this.nct2step.selectedAPIs.add(apiId);
            document.querySelector(`[data-api-id="${apiId}"]`)?.classList.add('selected');
        } else {
            this.nct2step.selectedAPIs.delete(apiId);
            document.querySelector(`[data-api-id="${apiId}"]`)?.classList.remove('selected');
            // Remove field selections for this API
            delete this.nct2step.selectedFields[apiId];
        }
        
        console.log('Selected APIs:', Array.from(this.nct2step.selectedAPIs));
        
        // Show field selection if any API is selected
        if (this.nct2step.selectedAPIs.size > 0) {
            this.renderFieldSelection();
            document.getElementById('nct2step-field-selection').classList.remove('hidden');
        } else {
            document.getElementById('nct2step-field-selection').classList.add('hidden');
        }
        
        this.updateExecuteButton();
    },
    
    /* ============================================================================
    NCT 2-STEP WORKFLOW - PART 2 (Field Selection & Step 2 Execution)
    ============================================================================ */

    renderFieldSelection() {
        const container = document.getElementById('nct2step-field-checkboxes');
        const step1Results = this.nct2step.step1Results;
        
        if (!step1Results) {
            container.innerHTML = '<p>No Step 1 results available</p>';
            return;
        }
        
        // Available fields to select from
        const availableFields = this.extractAvailableFields(step1Results);
        
        let html = '';
        
        // Group fields by API
        for (const apiId of this.nct2step.selectedAPIs) {
            const apiName = this.getExtendedAPIName(apiId);
            
            html += `
                <div class="field-checkbox-group">
                    <div class="field-checkbox-group-title">${apiName}</div>
                    <div class="field-checkbox-grid">
            `;
            
            for (const field of availableFields) {
                if (field.values.length === 0) continue;
                
                const fieldId = `field-${apiId}-${field.name}`;
                const isChecked = this.nct2step.selectedFields[apiId]?.includes(field.name);
                
                html += `
                    <div class="field-checkbox-item">
                        <input 
                            type="checkbox" 
                            id="${fieldId}" 
                            value="${field.name}"
                            ${isChecked ? 'checked' : ''}
                            onchange="app.handleFieldSelection('${apiId}', '${field.name}', this.checked)"
                        />
                        <label class="field-checkbox-label" for="${fieldId}">
                            <div class="field-checkbox-name">${field.label}</div>
                            <div class="field-checkbox-value">
                                ${field.preview}
                            </div>
                            <div class="field-checkbox-count">
                                ${field.values.length} value${field.values.length > 1 ? 's' : ''}
                            </div>
                        </label>
                    </div>
                `;
            }
            
            html += `
                    </div>
                </div>
            `;
        }
        
        container.innerHTML = html;
    },

    extractAvailableFields(step1Results) {
        const metadata = step1Results.metadata || {};
        const coreAPIs = step1Results.core_apis || {};
        
        const fields = [];
        
        // Title
        if (metadata.title) {
            fields.push({
                name: 'title',
                label: 'Trial Title',
                values: [metadata.title],
                preview: metadata.title.substring(0, 60) + (metadata.title.length > 60 ? '...' : '')
            });
        }
        
        // NCT ID
        fields.push({
            name: 'nct_id',
            label: 'NCT ID',
            values: [step1Results.nct_id],
            preview: step1Results.nct_id
        });
        
        // Condition
        const conditions = Array.isArray(metadata.condition) ? 
            metadata.condition : 
            (metadata.condition ? [metadata.condition] : []);
        
        if (conditions.length > 0) {
            fields.push({
                name: 'condition',
                label: 'Condition(s)',
                values: conditions,
                preview: conditions.slice(0, 2).join(', ') + (conditions.length > 2 ? '...' : '')
            });
        }
        
        // Intervention
        const interventions = Array.isArray(metadata.intervention) ? 
            metadata.intervention : 
            (metadata.intervention ? [metadata.intervention] : []);
        
        if (interventions.length > 0) {
            fields.push({
                name: 'intervention',
                label: 'Intervention(s)',
                values: interventions,
                preview: interventions.slice(0, 2).join(', ') + (interventions.length > 2 ? '...' : '')
            });
        }
        
        // PMIDs from PubMed
        const pubmedData = coreAPIs.pubmed?.data || {};
        const pmids = pubmedData.pmids || [];
        
        if (pmids.length > 0) {
            fields.push({
                name: 'pmid',
                label: 'PubMed IDs',
                values: pmids,
                preview: `${pmids.length} PMIDs found`
            });
        }
        
        return fields;
    },

    getExtendedAPIName(apiId) {
        const names = {
            'duckduckgo': 'DuckDuckGo',
            'serpapi': 'Google Search (SERP API)',
            'scholar': 'Google Scholar',
            'openfda': 'OpenFDA'
        };
        return names[apiId] || apiId;
    },

    handleFieldSelection(apiId, fieldName, checked) {
        if (!this.nct2step.selectedFields[apiId]) {
            this.nct2step.selectedFields[apiId] = [];
        }
        
        if (checked) {
            if (!this.nct2step.selectedFields[apiId].includes(fieldName)) {
                this.nct2step.selectedFields[apiId].push(fieldName);
            }
        } else {
            this.nct2step.selectedFields[apiId] = this.nct2step.selectedFields[apiId]
                .filter(f => f !== fieldName);
        }
        
        console.log('Selected fields:', this.nct2step.selectedFields);
        
        this.updateExecuteButton();
    },

    updateExecuteButton() {
        const button = document.getElementById('nct2step-execute-btn');
        
        // Check if at least one API has at least one field selected
        const hasSelections = Array.from(this.nct2step.selectedAPIs).some(apiId => {
            const fields = this.nct2step.selectedFields[apiId] || [];
            return fields.length > 0;
        });
        
        button.disabled = !hasSelections;
        
        if (hasSelections) {
            button.style.opacity = '1';
            button.style.cursor = 'pointer';
        } else {
            button.style.opacity = '0.5';
            button.style.cursor = 'not-allowed';
        }
    },

    // ============================================================================
    // STEP 2: Execute Extended Search
    // ============================================================================

    async executeStep2() {
        const nctId = this.nct2step.currentNCT;
        
        if (!nctId || !this.nct2step.step1Results) {
            alert('Please complete Step 1 first');
            return;
        }
        
        // Prepare request
        const selectedAPIs = Array.from(this.nct2step.selectedAPIs);
        const fieldSelections = {};
        
        for (const apiId of selectedAPIs) {
            const fields = this.nct2step.selectedFields[apiId] || [];
            if (fields.length > 0) {
                fieldSelections[apiId] = fields;
            }
        }
        
        if (Object.keys(fieldSelections).length === 0) {
            alert('Please select at least one field to search');
            return;
        }
        
        console.log('🚀 Starting Step 2');
        console.log('APIs:', selectedAPIs);
        console.log('Fields:', fieldSelections);
        
        // Show progress
        const progressDiv = document.getElementById('nct2step-step2-progress');
        progressDiv.classList.remove('hidden');
        progressDiv.classList.add('step-progress');
        progressDiv.innerHTML = `
            <span class="progress-spinner"></span>
            <strong>Step 2 in progress...</strong> Searching extended APIs with selected fields
        `;
        
        try {
            const response = await fetch(`${this.API_BASE}/api/nct-2step/step2/${nctId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-API-Key': this.apiKey
                },
                body: JSON.stringify({
                    selected_apis: selectedAPIs,
                    field_selections: fieldSelections
                })
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || `HTTP ${response.status}`);
            }
            
            const results = await response.json();
            this.nct2step.step2Results = results;
            
            console.log('✅ Step 2 complete:', results);
            
            // Hide progress
            progressDiv.classList.add('hidden');
            
            // Hide step 2 config, show final results
            document.getElementById('nct2step-step1-results').classList.add('hidden');
            document.getElementById('nct2step-step2-results').classList.remove('hidden');
            
            // Display Step 2 results
            this.displayStep2Results(results);
            
            this.showToast('Step 2 complete!', 'success');
            
        } catch (error) {
            console.error('❌ Step 2 error:', error);
            progressDiv.innerHTML = `
                <span style="color: #dc3545;">❌ <strong>Step 2 failed:</strong> ${error.message}</span>
            `;
            
            this.showToast('Step 2 search failed: ' + error.message, 'error');
        }
    },

    displayStep2Results(results) {
        const container = document.getElementById('nct2step-final-data');
        
        const extendedAPIs = results.extended_apis || {};
        const summary = results.summary || {};
        
        let html = `
            <!-- Summary Stats -->
            <div class="summary-stats">
                <div class="summary-stat">
                    <div class="summary-stat-number">${summary.extended_apis_searched?.length || 0}</div>
                    <div class="summary-stat-label">APIs Searched</div>
                </div>
                <div class="summary-stat">
                    <div class="summary-stat-number">${summary.total_searches || 0}</div>
                    <div class="summary-stat-label">Total Searches</div>
                </div>
                <div class="summary-stat">
                    <div class="summary-stat-number">${summary.successful_searches || 0}</div>
                    <div class="summary-stat-label">Successful Searches</div>
                </div>
                <div class="summary-stat">
                    <div class="summary-stat-number">${summary.total_results || 0}</div>
                    <div class="summary-stat-label">Results Found</div>
                </div>
            </div>
        `;
        
        // Display results from each extended API
        for (const [apiName, apiData] of Object.entries(extendedAPIs)) {
            if (!apiData.success) {
                html += `
                    <div class="step2-result-card" style="border-color: #FFC107;">
                        <div class="step2-api-header">
                            <h3 class="step2-api-title">${this.getExtendedAPIName(apiName)}</h3>
                            <span class="step1-result-badge" style="background: #FFF3CD; color: #856404;">Error</span>
                        </div>
                        <p style="color: #856404;">❌ ${apiData.error || 'Unknown error'}</p>
                    </div>
                `;
                continue;
            }
            
            const searches = apiData.searches || [];
            const data = apiData.data || {};
            const results_list = data.results || [];
            
            html += `
                <div class="step2-result-card">
                    <div class="step2-api-header">
                        <h3 class="step2-api-title">${this.getExtendedAPIName(apiName)}</h3>
                        <span class="step1-result-badge">${data.total_found || 0} Results</span>
                    </div>
                    
                    <h4 style="margin-bottom: 15px; color: #34495E;">Searches Performed</h4>
            `;
            
            // Display each search
            for (const search of searches) {
                const statusClass = search.status === 'success' ? 'success' : 'error';
                
                html += `
                    <div class="step2-search-record">
                        <div class="search-record-header">
                            <span class="search-record-number">Search ${search.search_number}</span>
                            <span class="search-record-status ${statusClass}">
                                ${search.status === 'success' ? '✓ Success' : '✗ Failed'}
                            </span>
                        </div>
                        <div class="search-record-query">
                            <strong>Query:</strong> ${search.query}
                        </div>
                        <div class="search-record-results">
                            <strong>Fields used:</strong> ${this.formatFieldsUsed(search.fields_used)}
                            ${search.status === 'success' ? 
                                `<br><strong>Results:</strong> ${search.results_count}` :
                                `<br><strong>Error:</strong> ${search.error}`
                            }
                        </div>
                    </div>
                `;
            }
            
            // Display actual results
            if (results_list.length > 0) {
                html += `
                    <h4 style="margin: 25px 0 15px 0; color: #34495E;">Results (${results_list.length})</h4>
                `;
                
                for (const result of results_list.slice(0, 20)) {  // Show first 20
                    html += `
                        <div class="result-item">
                            <div class="result-item-title">${result.title || 'No title'}</div>
                            ${result.url ? 
                                `<a href="${result.url}" target="_blank" class="result-item-url">${result.url}</a>` : 
                                ''
                            }
                            ${result.snippet ? 
                                `<div class="result-item-snippet">${result.snippet}</div>` : 
                                ''
                            }
                        </div>
                    `;
                }
                
                if (results_list.length > 20) {
                    html += `
                        <p style="text-align: center; color: #7F8C8D; margin-top: 15px;">
                            ... and ${results_list.length - 20} more results
                        </p>
                    `;
                }
            }
            
            html += `</div>`;
        }
        
        container.innerHTML = html;
    },

    formatFieldsUsed(fields) {
        return Object.entries(fields)
            .map(([key, value]) => `${key}="${value}"`)
            .join(', ');
    },

    // ============================================================================
    // Reset & Utility Functions
    // ============================================================================

    resetStep1() {
        // Reset state
        this.nct2step.currentNCT = null;
        this.nct2step.step1Results = null;
        this.nct2step.step2Results = null;
        this.nct2step.selectedAPIs.clear();
        this.nct2step.selectedFields = {};
        
        // Clear input
        document.getElementById('nct2step-input').value = '';
        
        // Hide all result areas, show input
        document.getElementById('nct2step-step1-area').classList.remove('hidden');
        document.getElementById('nct2step-step1-results').classList.add('hidden');
        document.getElementById('nct2step-step2-results').classList.add('hidden');
        
        // Clear progress
        document.getElementById('nct2step-step1-progress').classList.add('hidden');
        document.getElementById('nct2step-step2-progress').classList.add('hidden');
    },

    async downloadStep2Results() {
        const results = {
            step1: this.nct2step.step1Results,
            step2: this.nct2step.step2Results
        };
        
        const blob = new Blob([JSON.stringify(results, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `nct_2step_${this.nct2step.currentNCT}_${Date.now()}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        
        this.showToast('Results downloaded', 'success');
    },

    showToast(message, type = 'success') {
        // Implement toast notification
        const toast = document.createElement('div');
        toast.className = `toast toast-${type} toast-show`;
        toast.textContent = message;
        document.body.appendChild(toast);
        
        setTimeout(() => {
            toast.classList.remove('toast-show');
            toast.classList.add('toast-hide');
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    },


    // =========================================================================
    // Chat Mode
    // =========================================================================

    async initializeChatMode() {
        console.log('🚀 Initializing chat mode...');
        
        const container = document.getElementById('chat-container');
        container.innerHTML = '';
        
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
                    `   uvicorn chat_api:app --port 9001 --reload\n\n` +
                    `2. Check: curl http://localhost:9001/models\n\n` +
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

    ensureChatInfoBar() {
        console.log('📊 Ensuring chat info bar...');
        
        const modeId = this.currentMode + '-mode';
        const modeElement = document.getElementById(modeId);
        
        if (!modeElement) {
            console.error('❌ Mode element not found:', modeId);
            return;
        }
        
        let infoBar = modeElement.querySelector('.chat-info-bar');
        
        if (!infoBar) {
            console.log('➕ Creating new info bar for', this.currentMode);
            
            infoBar = document.createElement('div');
            infoBar.className = 'chat-info-bar';
            
            if (typeof modeElement.prepend === 'function') {
                modeElement.prepend(infoBar);
                console.log('✅ Info bar inserted using prepend()');
            } else {
                modeElement.appendChild(infoBar);
                if (modeElement.firstChild !== infoBar) {
                    modeElement.insertBefore(infoBar, modeElement.firstChild);
                }
                console.log('✅ Info bar inserted using fallback method');
            }
        } else {
            console.log('✅ Info bar already exists');
        }
        
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

    saveCurrentChat() {
        if (!this.currentModel) return;
        
        const container = document.getElementById('chat-container');
        const messages = [];
        
        container.querySelectorAll('.message').forEach(msg => {
            const role = msg.classList.contains('user') ? 'user' : 
                        msg.classList.contains('assistant') ? 'assistant' : 
                        msg.classList.contains('system') ? 'system' : 'error';
            
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

    restoreChat(modelName) {
        const saved = this.sessionChats[modelName];
        if (!saved || saved.messages.length === 0) {
            console.log('📭 No saved chat for', modelName);
            return false;
        }
        
        console.log(`📥 Restoring ${saved.messages.length} messages for ${modelName}`);
        
        const container = document.getElementById('chat-container');
        container.innerHTML = '';
        
        saved.messages.forEach(msg => {
            this.addMessage('chat-container', msg.role, msg.content);
        });
        
        this.currentConversationId = saved.conversationId;
        
        return true;
    },

    async clearCurrentChat() {
        if (!this.currentModel || !this.currentConversationId) return;
        
        const confirmed = confirm(`Clear all chat history with ${this.currentModel}?\n\nThis will:\n• Delete all messages in this session\n• Reset the model's memory\n• Start a fresh conversation`);
        
        if (!confirmed) return;
        
        console.log('🗑️  Clearing chat for', this.currentModel);
        
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
        
        delete this.sessionChats[this.currentModel];
        
        const container = document.getElementById('chat-container');
        container.innerHTML = '';
        
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
        
        const hasSavedChat = this.sessionChats[modelName] && 
                            this.sessionChats[modelName].messages.length > 0;
        
        if (hasSavedChat) {
            console.log('📥 Restoring saved chat for', modelName);
            
            const modelSelection = document.getElementById('model-selection-container');
            if (modelSelection) {
                modelSelection.remove();
            }
            
            this.currentModel = modelName;
            this.restoreChat(modelName);
            
            this.ensureChatInfoBar();
            
            const input = document.getElementById('chat-input');
            input.disabled = false;
            input.placeholder = 'Type your message...';
            input.focus();
            
            this.updateBackButton();
            
            this.addMessage('chat-container', 'system', 
                `✅ Resumed conversation with ${modelName}\n\n💡 Commands:\n• Click "Clear Chat" to reset\n• Click "Back to Models" to switch models`);
            
            return;
        }
        
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
            
            input.value = '';
            
            // Check if model is selected
            if (!this.currentModel) {
                this.addMessage('research-container', 'error', 
                    '❌ Please select a model first');
                return;
            }
            
            await this.sendResearchMessage(text);
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
        console.log('📚 Loading API registry...');        
        
        try {
            const url = `${this.API_BASE}/api/nct/registry`;
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
            console.log('📋 Registry loaded:', JSON.stringify(this.apiRegistry, null, 2));
            console.log('📊 Extended APIs:', this.apiRegistry.extended?.map(a => a.id));
            console.log('✅ API registry loaded:', this.apiRegistry);
            
            if (this.apiRegistry.metadata?.default_enabled) {
                this.selectedAPIs = new Set(this.apiRegistry.metadata.default_enabled);
            } else {
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
                    { id: 'openfda', name: 'OpenFDA', description: 'FDA drug data', enabled_by_default: false, available: true },
                    { id: 'uniprot', name: 'UniProt', description: 'Protein database', enabled_by_default: false, available: true }
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
        
        if (!this.apiRegistry) {
            await this.loadAPIRegistry();
        }
        
        const coreContainer = document.getElementById('core-apis-container');
        if (coreContainer) {
            coreContainer.innerHTML = '';
            
            this.apiRegistry.core.forEach(api => {
                const checkboxItem = this.createAPICheckbox(api, 'core');
                coreContainer.appendChild(checkboxItem);
            });
            
            console.log(`✅ Built ${this.apiRegistry.core.length} core API checkboxes`);
        }
        
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
        
        if (!api.available) {
            item.classList.add('disabled');
        }
        
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.id = `api-${api.id}`;
        checkbox.value = api.id;
        checkbox.checked = this.selectedAPIs.has(api.id);
        checkbox.disabled = !api.available;
        
        checkbox.addEventListener('change', (e) => {
            if (e.target.checked) {
                this.selectedAPIs.add(api.id);
            } else {
                this.selectedAPIs.delete(api.id);
            }
            console.log('Selected APIs:', Array.from(this.selectedAPIs));
        });
        
        const label = document.createElement('label');
        label.className = 'api-checkbox-label';
        label.htmlFor = `api-${api.id}`;
        
        const nameDiv = document.createElement('div');
        nameDiv.className = 'api-checkbox-name';
        nameDiv.textContent = api.name;
        
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
        
        const descDiv = document.createElement('div');
        descDiv.className = 'api-checkbox-desc';
        descDiv.textContent = api.description;
        
        label.appendChild(nameDiv);
        label.appendChild(descDiv);
        
        item.appendChild(checkbox);
        item.appendChild(label);
        
        return item;
    },

    // =========================================================================
    // Progress Tracking for NCT Search
    // =========================================================================

    updateSearchProgress(message, details = {}) {
        const progressDiv = document.getElementById('nct-progress');
        if (!progressDiv) return;
        
        progressDiv.classList.remove('hidden');
        
        let html = `
            <div class="progress-message">
                <span class="spinner"></span>
                <span class="progress-main-text">${message}</span>
            </div>
        `;
        
        if (details.current && details.total) {
            const percentage = Math.round((details.current / details.total) * 100);
            html += `
                <div class="progress-bar-container">
                    <div class="progress-bar" style="width: ${percentage}%"></div>
                </div>
                <div class="progress-details">
                    Trial ${details.current} of ${details.total} (${percentage}%)
                </div>
            `;
        }
        
        if (details.database) {
            html += `
                <div class="progress-database">
                    Currently fetching: <strong>${details.database}</strong>
                </div>
            `;
        }
        
        if (details.completed && details.completed.length > 0) {
            html += `
                <div class="progress-completed">
                    ✓ Completed: ${details.completed.join(', ')}
                </div>
            `;
        }
        
        progressDiv.innerHTML = html;
    },

    clearSearchProgress() {
        const progressDiv = document.getElementById('nct-progress');
        if (progressDiv) {
            progressDiv.style.transition = 'opacity 0.3s ease';
            progressDiv.style.opacity = '0';
            
            setTimeout(() => {
                progressDiv.remove();
            }, 300);
        }
    },

    // ============================================================================
    // FIXED: checkForAPIFailures method
    // ============================================================================

    checkForAPIFailures(resultData, nctId, errors, apiFailures) {
        const sources = resultData.sources || {};
        
        console.log(`🔍 Checking API failures for ${nctId}`);
        console.log('Sources available:', Object.keys(sources));
        
        // Check core sources (don't include 'extended' itself)
        Object.entries(sources).forEach(([sourceName, sourceData]) => {
            if (sourceName === 'extended') return; // Skip, handle separately
            
            console.log(`📊 ${sourceName}:`, {
                success: sourceData?.success,
                hasData: !!sourceData?.data,
                error: sourceData?.error
            });
            
            if (sourceData && !sourceData.success) {
                const failure = {
                    nct_id: nctId,
                    api: sourceName,
                    error: sourceData.error || 'Unknown API error',
                    stage: 'api_failure',
                    timestamp: new Date().toISOString()
                };
                apiFailures.push(failure);
                console.error(`❌ ${sourceName} failed for ${nctId}:`, failure.error);
            }
        });
        
        // Check extended sources
        if (sources.extended && typeof sources.extended === 'object') {
            console.log('📦 Extended sources found:', Object.keys(sources.extended));
            
            Object.entries(sources.extended).forEach(([api, data]) => {
                if (data) {
                    console.log(`📊 Extended ${api}:`, {
                        success: data.success,
                        hasData: !!data.data,
                        error: data.error,
                        dataKeys: data.data ? Object.keys(data.data) : []
                    });
                    
                    // Check if API failed
                    if (!data.success) {
                        const failure = {
                            nct_id: nctId,
                            api: api,
                            error: data.error || 'Unknown API error',
                            stage: 'api_failure',
                            timestamp: new Date().toISOString()
                        };
                        apiFailures.push(failure);
                        console.error(`❌ Extended ${api} failed for ${nctId}:`, failure.error);
                    } else if (data.data) {
                        // Check if extended API returned 0 results (not an error, but worth noting)
                        const resultCount = this.countSourceResults(api, data.data);
                        if (resultCount === 0) {
                            console.warn(`⚠️  Extended ${api} returned 0 results for ${nctId}`);
                            console.log(`ℹ️  ${api} response:`, data.data);
                        } else {
                            console.log(`✅ Extended ${api} returned ${resultCount} results for ${nctId}`);
                        }
                    }
                }
            });
        } else {
            console.warn(`⚠️  No extended sources in result for ${nctId}`);
        }
    },

    // ============================================================================
    // NCT Lookup Handler
    // ============================================================================

    async handleNCTLookup() {
        const input = document.getElementById('nct-input');
        const nctIds = input.value.split(',').map(s => s.trim().toUpperCase()).filter(s => s);
        
        if (nctIds.length === 0) {
            alert('Please enter at least one NCT number');
            return;
        }
        
        if (!this.apiRegistry) {
            await this.loadAPIRegistry();
        }
        
        const resultsDiv = document.getElementById('nct-results');
        const inputArea = document.querySelector('.nct-input-area');
        
        console.log('Starting NCT lookup for:', nctIds);
        
        inputArea.classList.add('hidden');
        resultsDiv.classList.add('active');
        
        resultsDiv.innerHTML = `
            <div id="nct-progress" class="search-progress">
                <div class="progress-message">
                    <span class="spinner"></span>
                    <span class="progress-main-text">Initializing search...</span>
                </div>
            </div>
        `;
        
        const selectedAPIList = Array.from(this.selectedAPIs);
        const coreAPIs = ['clinicaltrials', 'pubmed', 'pmc', 'pmc_bioc'];
        const extendedAPIs = selectedAPIList.filter(api => !coreAPIs.includes(api));
        
        console.log('🔍 Starting NCT lookup');
        console.log('Core APIs (always included):', coreAPIs);
        console.log('Extended APIs (user selected):', extendedAPIs);
        
        const results = [];
        const errors = [];
        const apiFailures = [];
        const searchJobs = {};
        
        try {
            const NCT_API_BASE = `${this.API_BASE}/api/nct`;
            
            async function makeRequest(url, options) {
                const response = await fetch(url, options);
                if (!response.ok) {
                    const errorText = await response.text();
                    throw new Error(`HTTP ${response.status}: ${errorText}`);
                }
                return response.json();
            }
            
            this.updateSearchProgress('Initiating searches...', {
                current: 0,
                total: nctIds.length
            });
            
            // Initiate searches
            for (let i = 0; i < nctIds.length; i++) {
                const nctId = nctIds[i];
                
                try {
                    const searchRequest = {
                        include_extended: extendedAPIs.length > 0
                    };
                    
                    if (extendedAPIs.length > 0) {
                        searchRequest.databases = extendedAPIs;
                    }
                    
                    console.log(`Searching ${nctId} with request:`, searchRequest);
                    
                    this.updateSearchProgress(`Initiating search for ${nctId}...`, {
                        current: i + 1,
                        total: nctIds.length
                    });
                    
                    const data = await makeRequest(
                        `${NCT_API_BASE}/search/${nctId}`,
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
                        error: error.message,
                        stage: 'initiation',
                        timestamp: new Date().toISOString()
                    });
                }
            }
            
            this.updateSearchProgress('Fetching trial data from databases...', {
                current: 0,
                total: Object.keys(searchJobs).length
            });
            
            // Poll for results
            const maxWait = 300000;
            const pollInterval = 2000;
            const startTime = Date.now();
            
            while (Object.keys(searchJobs).length > 0 && (Date.now() - startTime) < maxWait) {
                const completedJobs = [];
                const totalJobs = nctIds.length;
                const completedCount = results.length + errors.filter(e => e.stage !== 'api_failure').length;
                
                for (const [nctId, jobId] of Object.entries(searchJobs)) {
                    try {
                        const statusData = await makeRequest(
                            `${NCT_API_BASE}/search/${jobId}/status`,
                            {
                                headers: { 'Authorization': `Bearer ${this.apiKey}` }
                            }
                        );
                        
                        if (statusData.current_database) {
                            const apiDef = this.apiRegistry.core.find(a => a.id === statusData.current_database) ||
                                        this.apiRegistry.extended.find(a => a.id === statusData.current_database);
                            const apiName = apiDef ? apiDef.name : statusData.current_database;
                            
                            this.updateSearchProgress(`Processing ${nctId}...`, {
                                current: completedCount,
                                total: totalJobs,
                                database: apiName,
                                completed: statusData.completed_databases || []
                            });
                        }
                        
                        if (statusData.status === 'completed') {
                            const resultData = await makeRequest(
                                `${NCT_API_BASE}/results/${jobId}`,
                                {
                                    headers: { 'Authorization': `Bearer ${this.apiKey}` }
                                }
                            );
                            
                            // FIXED: Check for API failures and log them
                            this.checkForAPIFailures(resultData, nctId, errors, apiFailures);
                            
                            results.push(resultData);
                            completedJobs.push(nctId);
                            console.log(`✅ Retrieved results for ${nctId}`);
                            
                            this.updateSearchProgress(`Completed ${nctId}`, {
                                current: results.length + errors.filter(e => e.stage !== 'api_failure').length,
                                total: totalJobs
                            });
                            
                        } else if (statusData.status === 'failed') {
                            errors.push({
                                nct_id: nctId,
                                error: statusData.error || 'Search failed',
                                stage: 'execution',
                                timestamp: new Date().toISOString()
                            });
                            completedJobs.push(nctId);
                        }
                        
                    } catch (error) {
                        console.error(`❌ Error checking status for ${nctId}:`, error);
                        errors.push({
                            nct_id: nctId,
                            error: error.message,
                            stage: 'status_check',
                            timestamp: new Date().toISOString()
                        });
                        completedJobs.push(nctId);
                    }
                }
                
                completedJobs.forEach(nctId => {
                    delete searchJobs[nctId];
                });
                
                if (Object.keys(searchJobs).length > 0) {
                    await new Promise(resolve => setTimeout(resolve, pollInterval));
                }
            }
            
            // Handle timeouts
            for (const nctId of Object.keys(searchJobs)) {
                errors.push({
                    nct_id: nctId,
                    error: 'Search timeout (exceeded 5 minutes)',
                    stage: 'timeout',
                    timestamp: new Date().toISOString()
                });
            }
            
            const progressDiv = document.getElementById('nct-progress');
            if (progressDiv) {
                progressDiv.remove();
            }

            // ENHANCED: Log all collected errors and API failures
            console.log('📊 Search Complete Summary:');
            console.log(`✅ Successful results: ${results.length}`);
            console.log(`❌ Total errors: ${errors.length}`);
            console.log(`⚠️  API-level failures: ${apiFailures.length}`);
            
            if (errors.length > 0) {
                console.group('❌ Errors by Type:');
                const errorsByType = {};
                errors.forEach(err => {
                    errorsByType[err.stage] = (errorsByType[err.stage] || 0) + 1;
                });
                Object.entries(errorsByType).forEach(([stage, count]) => {
                    console.log(`  ${stage}: ${count}`);
                });
                console.groupEnd();
            }
            
            if (apiFailures.length > 0) {
                console.group('⚠️  API Failures by API:');
                const failuresByAPI = {};
                apiFailures.forEach(fail => {
                    failuresByAPI[fail.api] = (failuresByAPI[fail.api] || 0) + 1;
                });
                Object.entries(failuresByAPI).forEach(([api, count]) => {
                    console.log(`  ${api}: ${count} failure(s)`);
                });
                console.groupEnd();
            }

            // Display results
            if (results.length > 0) {
                this.nctResults = {
                    success: true,
                    results: results,
                    summary: {
                        total_requested: nctIds.length,
                        successful: results.length,
                        failed: errors.filter(e => e.stage !== 'api_failure').length,
                        api_failures: apiFailures.length,
                        errors: errors.length > 0 ? errors : null
                    }
                };
                
                this.displayNCTResults(this.nctResults);
                
                // Add errors after results are displayed
                if (errors.length > 0 || apiFailures.length > 0) {
                    const errorSummaryHTML = this.showSearchErrorSummary(errors, apiFailures);
                    resultsDiv.insertAdjacentHTML('beforeend', errorSummaryHTML);
                }
                
                // Note: Buttons are now created inside displayNCTResults()
                // No need to show/hide them separately
                
            } else {
                resultsDiv.innerHTML = `
                    <div class="result-card">
                        <h3>❌ No Results</h3>
                        <p>No trials could be fetched. Check errors below:</p>
                    </div>
                `;
                
                if (errors.length > 0 || apiFailures.length > 0) {
                    const errorSummaryHTML = this.showSearchErrorSummary(errors, apiFailures);
                    resultsDiv.insertAdjacentHTML('beforeend', errorSummaryHTML);
                }
            }
            
        } catch (error) {
            console.error('❌ NCT lookup error:', error);
            
            const progressDiv = document.getElementById('nct-progress');
            if (progressDiv) {
                progressDiv.remove();
            }
            
            resultsDiv.innerHTML = `
                <div class="result-card error-card">
                    <h3>❌ Critical Error</h3>
                    <p>${this.escapeHtml(error.message)}</p>
                    <pre>${error.stack || 'No stack trace available'}</pre>
                </div>
            `;
        }
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
        if (!this.nctResults) {
            this.showToast('⚠️ No results to save', 'error');
            return;
        }
        
        const nctId = this.nctResults.summary.nct_id;
        
        try {
            // Step 1: Check for duplicates
            const checkResponse = await fetch(`${this.NCT_SERVICE_URL}/api/results/${nctId}/check-duplicate`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            if (!checkResponse.ok) {
                throw new Error('Failed to check for duplicates');
            }
            
            const duplicateInfo = await checkResponse.json();
            
            // Step 2: If file exists, prompt user
            if (duplicateInfo.exists) {
                this.showDuplicateDialog(nctId, duplicateInfo);
            } else {
                // No duplicate, proceed with save
                await this.performSave(nctId, false);
            }
            
        } catch (error) {
            console.error('Save error:', error);
            this.showToast(
                `❌ Save failed: ${error.message}`,
                'error',
                5000
            );
        }
    },

    // New function to show duplicate dialog
    showDuplicateDialog(nctId, duplicateInfo) {
        const existingFiles = duplicateInfo.existing_files.join(', ');
        const suggestedFilename = duplicateInfo.suggested_filename;
        
        // Create modal dialog
        const dialog = document.createElement('div');
        dialog.className = 'duplicate-dialog-overlay';
        dialog.innerHTML = `
            <div class="duplicate-dialog">
                <div class="duplicate-dialog-header">
                    <h3>⚠️ File Already Exists</h3>
                </div>
                <div class="duplicate-dialog-content">
                    <p>Files already exist for <strong>${nctId}</strong>:</p>
                    <ul class="existing-files-list">
                        ${duplicateInfo.existing_files.map(f => `<li>📄 ${f}</li>`).join('')}
                    </ul>
                    <p>What would you like to do?</p>
                </div>
                <div class="duplicate-dialog-actions">
                    <button class="dialog-btn dialog-btn-primary" id="save-new-version">
                        💾 Save as New Version
                        <small>(${suggestedFilename})</small>
                    </button>
                    <button class="dialog-btn dialog-btn-warning" id="overwrite-existing">
                        ⚠️ Overwrite Existing
                        <small>(${nctId}.json)</small>
                    </button>
                    <button class="dialog-btn dialog-btn-secondary" id="cancel-save">
                        ❌ Cancel
                    </button>
                </div>
            </div>
        `;
        
        document.body.appendChild(dialog);
        
        // Add event listeners
        document.getElementById('save-new-version').addEventListener('click', async () => {
            document.body.removeChild(dialog);
            await this.performSave(nctId, false);
        });
        
        document.getElementById('overwrite-existing').addEventListener('click', async () => {
            document.body.removeChild(dialog);
            await this.performSave(nctId, true);
        });
        
        document.getElementById('cancel-save').addEventListener('click', () => {
            document.body.removeChild(dialog);
            this.showToast('💭 Save cancelled', 'info', 2000);
        });
        
        // Close on overlay click
        dialog.addEventListener('click', (e) => {
            if (e.target === dialog) {
                document.body.removeChild(dialog);
                this.showToast('💭 Save cancelled', 'info', 2000);
            }
        });
    },

    // New function to perform the actual save
    async performSave(nctId, overwrite = false) {
        try {
            const response = await fetch(`${this.NCT_SERVICE_URL}/api/results/${nctId}/save`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    overwrite: overwrite
                })
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Save failed');
            }
            
            const saveInfo = await response.json();
            
            // Show success message
            const sizeFormatted = this.formatFileSize(saveInfo.size_bytes);
            const action = saveInfo.overwritten ? 'Overwritten' : 
                        saveInfo.was_duplicate ? 'Saved as new version' : 'Saved';
            
            this.showToast(
                `✅ ${action} successfully!<br>` +
                `<small>📄 File: ${saveInfo.filename}<br>` +
                `💾 Size: ${sizeFormatted}<br>` +
                `📍 Location: ${saveInfo.filepath}</small>`,
                'success',
                5000
            );
            
            console.log('✅ Save successful:', saveInfo);
            
        } catch (error) {
            console.error('Save error:', error);
            this.showToast(
                `❌ Save failed: ${error.message}`,
                'error',
                5000
            );
        }
    },

    // Updated downloadNCTResults with NCT ID-based naming
    downloadNCTResults() {
        if (!this.nctResults) {
            this.showToast('⚠️ No results to download', 'error');
            return;
        }
        
        // Use NCT ID for filename
        const nctId = this.nctResults.summary.nct_id;
        const filename = `${nctId}.json`;
        const content = JSON.stringify(this.nctResults.results, null, 2);
        
        const blob = new Blob([content], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        
        console.log(`✅ Downloaded ${filename} to local computer`);
        
        const sizeFormatted = this.formatFileSize(content.length);
        
        this.showToast(
            `📥 Downloaded: ${filename}<br><small>Size: ${sizeFormatted}</small>`,
            'success',
            4000
        );
    },

    // Helper function for file size formatting
    formatFileSize(bytes) {
        if (bytes < 1024) return bytes + ' B';
        const kb = bytes / 1024;
        if (kb < 1024) return kb.toFixed(1) + ' KB';
        const mb = kb / 1024;
        return mb.toFixed(2) + ' MB';
    },


    showSearchErrorSummary(errors, apiFailures = []) {
        if (!errors || errors.length === 0) return '';
        
        console.error('❌ NCT Search Errors:', errors);
        
        const errorsByNCT = {};
        const errorsByAPI = {};
        const apiFailuresByAPI = {};
        
        errors.forEach(error => {
            // Group by NCT
            if (!errorsByNCT[error.nct_id]) {
                errorsByNCT[error.nct_id] = [];
            }
            errorsByNCT[error.nct_id].push(error);
            
            // Group by API
            if (error.api) {
                if (!errorsByAPI[error.api]) {
                    errorsByAPI[error.api] = [];
                }
                errorsByAPI[error.api].push(error);
            }
        });
        
        // Separate API-level failures
        if (apiFailures && apiFailures.length > 0) {
            apiFailures.forEach(failure => {
                if (!apiFailuresByAPI[failure.api]) {
                    apiFailuresByAPI[failure.api] = [];
                }
                apiFailuresByAPI[failure.api].push(failure);
            });
        }
        
        let errorHTML = `
            <div class="result-card error-card">
                <h3>⚠️ Search Issues (${errors.length} total)</h3>
                
                <div class="error-summary">
        `;
        
        // Show trial-level errors if any
        if (Object.keys(errorsByNCT).length > 0) {
            errorHTML += `
                <h4>🔴 Trial Fetch Errors:</h4>
                <ul class="error-list">
            `;
            
            Object.entries(errorsByNCT).forEach(([nctId, nctErrors]) => {
                errorHTML += `<li><strong>${nctId}</strong>: ${nctErrors.length} error(s)`;
                errorHTML += `<ul class="error-details">`;
                nctErrors.forEach(err => {
                    const apiName = err.api ? ` [${err.api}]` : '';
                    errorHTML += `<li>${apiName} ${err.error || 'Unknown error'}</li>`;
                });
                errorHTML += `</ul></li>`;
            });
            
            errorHTML += `</ul>`;
        }
        
        // Show API-level failures prominently
        if (Object.keys(apiFailuresByAPI).length > 0) {
            errorHTML += `
                <h4 style="margin-top: 20px; color: #c53030;">⚠️ API Failures:</h4>
                <div class="api-failures-grid">
            `;
            
            Object.entries(apiFailuresByAPI).forEach(([api, failures]) => {
                const apiInfo = this.getAPIInfo(api);
                const apiName = apiInfo ? apiInfo.name : api;
                const uniqueErrors = [...new Set(failures.map(f => f.error))];
                
                errorHTML += `
                    <div class="api-failure-card">
                        <div class="api-failure-header">
                            <span class="api-failure-icon">❌</span>
                            <strong>${apiName}</strong>
                            <span class="api-failure-count">${failures.length} failure(s)</span>
                        </div>
                        <div class="api-failure-details">
                            ${uniqueErrors.map(err => `<div class="api-failure-error">• ${err}</div>`).join('')}
                        </div>
                        <div class="api-failure-trials">
                            Affected trials: ${[...new Set(failures.map(f => f.nct_id))].join(', ')}
                        </div>
                    </div>
                `;
            });
            
            errorHTML += `</div>`;
        }
        
        // Show regular API errors
        if (Object.keys(errorsByAPI).length > 0 && Object.keys(apiFailuresByAPI).length === 0) {
            errorHTML += `
                <h4 style="margin-top: 20px;">Errors by API:</h4>
                <ul class="error-list">
            `;
            
            Object.entries(errorsByAPI).forEach(([api, apiErrors]) => {
                const apiInfo = this.getAPIInfo(api);
                const apiName = apiInfo ? apiInfo.name : api;
                errorHTML += `<li><strong>${apiName}</strong>: ${apiErrors.length} failure(s)</li>`;
            });
            
            errorHTML += `</ul>`;
        }
        
        errorHTML += `
                </div>
                <button class="error-details-toggle" onclick="this.nextElementSibling.classList.toggle('hidden')">
                    🔍 Show Full Error Details (for debugging)
                </button>
                <pre class="error-full-details hidden">${JSON.stringify({
                    errors: errors,
                    apiFailures: apiFailures
                }, null, 2)}</pre>
            </div>
        `;
        
        return errorHTML;
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

    startNewNCTSearch() {
        console.log('🔄 Starting new search...');
        
        const resultsDiv = document.getElementById('nct-results');
        const inputArea = document.querySelector('.nct-input-area');
        
        // Clear results
        resultsDiv.innerHTML = '';
        resultsDiv.classList.remove('active');
        inputArea.classList.remove('hidden');
        
        // Reset input field
        const nctInput = document.getElementById('nct-input');
        if (nctInput) {
            nctInput.value = '';
        }
        
        // Reset API selection to defaults
        if (this.apiRegistry && this.apiRegistry.metadata && this.apiRegistry.metadata.default_enabled) {
            this.selectedAPIs = new Set(this.apiRegistry.metadata.default_enabled);
        } else {
            this.selectedAPIs = new Set(['clinicaltrials', 'pubmed', 'pmc', 'pmc_bioc']);
        }
        
        // Rebuild checkboxes with reset selections
        this.buildAPICheckboxes();
        
        // Clear stored results
        this.nctResults = null;
        
        console.log('✅ New search initiated - form reset');
    },

    displayNCTResults(data) {
        const resultsDiv = document.getElementById('nct-results');
        const inputArea = document.querySelector('.nct-input-area');
        
        // Store results globally for action buttons
        window.lastNCTResults = data;
    
        let html = '';
        
        // Compact button HTML with smaller styling
        html += `
            <div class="results-actions-bar">
                <button class="results-actions-btn new-search-btn" onclick="app.startNewNCTSearch(); event.preventDefault();">
                    🔍 New Search
                </button>
                <button class="results-actions-btn download-btn" onclick="app.downloadNCTResults(); event.preventDefault();">
                    📥 Download
                </button>
                <button class="results-actions-btn save-btn" onclick="app.saveNCTResults(); event.preventDefault();">
                    💾 Save to Server
                </button>
            </div>
        `;
        
        html += `
            <div class="result-card summary-card">
                <h3>📊 Search Summary</h3>
                <div class="summary-stats">
                    <div class="stat-item">
                        <span class="stat-label">Trials Requested:</span>
                        <span class="stat-value">${data.summary.total_requested}</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-label">Successfully Retrieved:</span>
                        <span class="stat-value success">${data.summary.successful}</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-label">Failed:</span>
                        <span class="stat-value ${data.summary.failed > 0 ? 'error' : ''}">${data.summary.failed}</span>
                    </div>
                </div>
        `;
        
        const sourceStats = {};
        let totalResults = 0;
        
        data.results.forEach(trial => {
            const sources = trial.sources || {};
            
            console.log('🔍 Trial sources structure:', Object.keys(sources));
            if (sources.extended) {
                console.log('🔬 Extended sources:', Object.keys(sources.extended));
            }
            
            // Count core sources
            Object.entries(sources).forEach(([sourceName, sourceData]) => {
                if (sourceName === 'extended') return;
                
                if (!sourceStats[sourceName]) {
                    sourceStats[sourceName] = {
                        count: 0,
                        successful: 0,
                        failed: 0
                    };
                }
                
                if (sourceData && sourceData.success && sourceData.data) {
                    sourceStats[sourceName].successful++;
                    
                    const resultCount = this.countSourceResults(sourceName, sourceData.data);
                    sourceStats[sourceName].count += resultCount;
                    totalResults += resultCount;
                } else {
                    sourceStats[sourceName].failed++;
                }
            });
            
            // Count extended sources
            if (sources.extended) {
                Object.entries(sources.extended).forEach(([sourceName, sourceData]) => {
                    console.log(`📊 Extended source ${sourceName}:`, {
                        success: sourceData?.success,
                        hasData: !!sourceData?.data,
                        error: sourceData?.error
                    });
                    
                    if (!sourceStats[sourceName]) {
                        sourceStats[sourceName] = {
                            count: 0,
                            successful: 0,
                            failed: 0
                        };
                    }
                    
                    if (sourceData && sourceData.success && sourceData.data) {
                        sourceStats[sourceName].successful++;
                        
                        const resultCount = this.countSourceResults(sourceName, sourceData.data);
                        sourceStats[sourceName].count += resultCount;
                        totalResults += resultCount;
                    } else {
                        sourceStats[sourceName].failed++;
                    }
                });
            }
        });
        
        if (Object.keys(sourceStats).length > 0) {
            const coreAPIs = ['clinicaltrials', 'clinical_trials', 'pubmed', 'pmc', 'pmc_bioc'];
            const coreSources = [];
            const extendedSources = [];
            
            Object.entries(sourceStats).forEach(([sourceName, stats]) => {
                if (coreAPIs.includes(sourceName)) {
                    coreSources.push([sourceName, stats]);
                } else {
                    extendedSources.push([sourceName, stats]);
                }
            });
            
            coreSources.sort((a, b) => b[1].count - a[1].count);
            extendedSources.sort((a, b) => b[1].count - a[1].count);
            
            html += `<div class="source-stats-container">`;
            
            if (coreSources.length > 0) {
                html += `
                    <h4 style="margin-top: 20px; margin-bottom: 12px; color: #333;">📚 Core Sources</h4>
                    <div class="source-stats-grid">
                `;
                
                coreSources.forEach(([sourceName, stats]) => {
                    const apiInfo = this.getAPIInfo(sourceName);
                    const displayName = apiInfo ? apiInfo.name : sourceName;
                    const successRate = stats.successful > 0 ? 
                        Math.round((stats.successful / (stats.successful + stats.failed)) * 100) : 0;
                    
                    html += `
                        <div class="source-stat-item">
                            <div class="source-stat-header">
                                <span class="source-stat-name">${this.escapeHtml(displayName)}</span>
                                <span class="source-stat-badge ${stats.count > 0 ? 'success' : 'empty'}">${stats.count}</span>
                            </div>
                            <div class="source-stat-details">
                                <span class="source-stat-detail">✓ ${stats.successful} successful</span>
                                ${stats.failed > 0 ? `<span class="source-stat-detail error">✗ ${stats.failed} failed</span>` : ''}
                                <span class="source-stat-detail">${successRate}% success rate</span>
                            </div>
                        </div>
                    `;
                });
                
                html += `</div>`;
            }
            
            if (extendedSources.length > 0) {
                html += `
                    <h4 style="margin-top: 30px; margin-bottom: 12px; color: #333;">🔬 Extended Sources</h4>
                    <div class="source-stats-grid">
                `;
                
                extendedSources.forEach(([sourceName, stats]) => {
                    const apiInfo = this.getAPIInfo(sourceName);
                    const displayName = apiInfo ? apiInfo.name : sourceName;
                    const successRate = stats.successful > 0 ? 
                        Math.round((stats.successful / (stats.successful + stats.failed)) * 100) : 0;
                    
                    html += `
                        <div class="source-stat-item extended-source-stat">
                            <div class="source-stat-header">
                                <span class="source-stat-name">${this.escapeHtml(displayName)}</span>
                                <span class="source-stat-badge ${stats.count > 0 ? 'success' : 'empty'}">${stats.count}</span>
                            </div>
                            <div class="source-stat-details">
                                <span class="source-stat-detail">✓ ${stats.successful} successful</span>
                                ${stats.failed > 0 ? `<span class="source-stat-detail error">✗ ${stats.failed} failed</span>` : ''}
                                <span class="source-stat-detail">${successRate}% success rate</span>
                            </div>
                        </div>
                    `;
                });
                
                html += `</div>`;
            }
            
            html += `
                <div class="total-results-banner">
                    <strong>Total Results Across All Sources:</strong> <span class="highlight-number">${totalResults}</span>
                </div>
            </div>
            `;
        }
        
        html += `</div>`;
        
        // Display individual trial cards
        data.results.forEach(trial => {
            const nctId = trial.nct_id || 'Unknown';
            const metadata = trial.metadata || {};
            const sources = trial.sources || {};
            
            const ctData = sources.clinicaltrials?.data || sources.clinical_trials?.data;
            const trialTitle = metadata.title || ctData?.brief_title || ctData?.official_title || 'Title not available';
            const trialStatus = metadata.status || ctData?.overall_status || 'Unknown';
            const trialCondition = metadata.condition || (ctData?.conditions ? ctData.conditions[0] : '') || 'N/A';
            const trialIntervention = metadata.intervention || (ctData?.interventions ? ctData.interventions[0]?.name : '') || 'N/A';
            
            let sourceCount = 0;
            Object.keys(sources).forEach(key => {
                if (key === 'extended') {
                    sourceCount += Object.keys(sources.extended).length;
                } else {
                    sourceCount++;
                }
            });

            html += `
                <div class="result-card trial-card">
                    <div class="trial-header">
                        <div>
                            <h3>${nctId}</h3>
                        </div>
                        <span class="source-count">${sourceCount} sources</span>
                    </div>
            `;
            
            // Display core sources
            Object.entries(sources).forEach(([sourceName, sourceData]) => {
                if (sourceName === 'extended') return;
                
                const apiInfo = this.getAPIInfo(sourceName);
                const apiDisplayName = apiInfo ? apiInfo.name : sourceName;
                
                if (sourceData && sourceData.success && sourceData.data) {
                    const data = sourceData.data;
                    const resultCount = this.countSourceResults(sourceName, data);
                    
                    html += `
                        <div class="source-section">
                            <div class="source-header">
                                <strong>📚 ${this.escapeHtml(apiDisplayName)}</strong>
                                <div class="source-header-right">
                                    <span class="source-count-badge">${resultCount} result${resultCount !== 1 ? 's' : ''}</span>
                                    <span class="source-status success">✓</span>
                                </div>
                            </div>
                            <div class="source-content">
                    `;
                    
                    if (sourceName === 'clinicaltrials' || sourceName === 'clinical_trials') {
                        html += `<div class="data-field">
                            <strong>NCT Number:</strong> ${nctId}
                        </div>`;
                        
                        if (trialTitle && trialCondition && trialIntervention && trialStatus) {
                            html += `<div class="data-field abstract-field">
                                <div class="trial-title-display">${this.escapeHtml(trialTitle)}</div>
                                <div class="trial-summary-item">
                                    <strong>Status:</strong> 
                                    <span class="status-badge status-${trialStatus.toLowerCase().replace(/\s+/g, '-')}">${this.escapeHtml(trialStatus)}</span>
                                </div>
                                <div class="trial-summary-item">
                                    <strong>Condition:</strong> ${this.escapeHtml(trialCondition)}
                                </div>
                                <div class="trial-summary-item">
                                    <strong>Intervention:</strong> ${this.escapeHtml(trialIntervention)}
                                </div>
                            </div>`;
                        }
                    
                    } else if (sourceName === 'pubmed') {
                        // Display search strategy
                        if (data.search_strategy) {
                            html += `<div class="search-info">
                                <span class="search-info-label">🔍 Search Strategy:</span>
                                <span class="search-info-value">${this.escapeHtml(data.search_strategy)}</span>
                            </div>`;
                        }
                        
                        // Display exact search queries with full details
                        if (data.search_queries && data.search_queries.length > 0) {
                            html += `<div class="search-info">
                                <span class="search-info-label">📝 Search Queries Executed:</span>
                                <div class="search-queries-list">
                                    ${data.search_queries.map((q, idx) => `
                                        <div class="search-query-item">
                                            <span class="query-number">${idx + 1}.</span>
                                            <code class="query-code">${this.escapeHtml(q)}</code>
                                        </div>
                                    `).join('')}
                                </div>
                            </div>`;
                        }
                        
                        // Display exact API query string if available
                        if (data.query_string) {
                            html += `<div class="search-info">
                                <span class="search-info-label">🔗 Exact API Query:</span>
                                <code class="api-query-string">${this.escapeHtml(data.queries_used)}</code>
                            </div>`;
                        }
                        
                        html += `<div class="data-field">
                            <strong>Articles Found:</strong> ${resultCount}
                        </div>`;
                        
                        // Display all PMIDs as a formatted list with links
                        if (data.pmids && data.pmids.length > 0) {
                            const uniqueId = `source-${nctId}-${sourceName}-${Date.now()}`;
                            
                            html += `<div class="data-field pmid-list-field">
                                <strong>PMIDs (${data.pmids.length} total):</strong>
                                <button class="toggle-list-btn" onclick="app.togglePMIDList('${uniqueId}-pmids')">
                                    Show All
                                </button>
                                <div id="${uniqueId}-pmids" class="pmid-list-container hidden">
                                    <div class="pmid-grid">
                                        ${data.pmids.map(pmid => `
                                            <a href="https://pubmed.ncbi.nlm.nih.gov/${pmid}/" 
                                            target="_blank" 
                                            rel="noopener noreferrer"
                                            class="pmid-link">${pmid}</a>
                                        `).join('')}
                                    </div>
                                </div>
                            </div>`;
                        }
                    } else if (sourceName === 'pmc') {
                        // Display search strategy
                        if (data.search_strategy) {
                            html += `<div class="search-info">
                                <span class="search-info-label">🔍 Search Strategy:</span>
                                <span class="search-info-value">${this.escapeHtml(data.search_strategy)}</span>
                            </div>`;
                        }
                        
                        // Display exact search queries with full details
                        if (data.search_queries && data.search_queries.length > 0) {
                            html += `<div class="search-info">
                                <span class="search-info-label">📝 Search Queries Executed:</span>
                                <div class="search-queries-list">
                                    ${data.search_queries.map((q, idx) => `
                                        <div class="search-query-item">
                                            <span class="query-number">${idx + 1}.</span>
                                            <code class="query-code">${this.escapeHtml(q)}</code>
                                        </div>
                                    `).join('')}
                                </div>
                            </div>`;
                        }
                        
                        // Display exact API query string if available
                        if (data.query_string) {
                            html += `<div class="search-info">
                                <span class="search-info-label">🔗 Exact API Query:</span>
                                <code class="api-query-string">${this.escapeHtml(data.query_string)}</code>
                            </div>`;
                        }
                        
                        // Display search parameters if available
                        if (data.search_params) {
                            html += `<div class="search-info">
                                <span class="search-info-label">⚙️ Search Parameters:</span>
                                <pre class="search-params-json">${JSON.stringify(data.search_params, null, 2)}</pre>
                            </div>`;
                        }
                        
                        html += `<div class="data-field">
                            <strong>Articles Found:</strong> ${resultCount}
                        </div>`;
                        
                        // Display PMCIDs as a formatted list with links
                        if (data.pmcids && data.pmcids.length > 0) {
                            const uniqueId = `source-${nctId}-${sourceName}-${Date.now()}`;
                            
                            html += `<div class="data-field pmid-list-field">
                                <strong>PMCIDs (${data.pmcids.length} total):</strong>
                                <button class="toggle-list-btn" onclick="app.togglePMIDList('${uniqueId}-pmcids')">
                                    Show All
                                </button>
                                <div id="${uniqueId}-pmcids" class="pmid-list-container hidden">
                                    <div class="pmid-grid">
                                        ${data.pmcids.map(pmcid => `
                                            <a href="https://www.ncbi.nlm.nih.gov/pmc/articles/${pmcid}/" 
                                            target="_blank" 
                                            rel="noopener noreferrer"
                                            class="pmid-link">${pmcid}</a>
                                        `).join('')}
                                    </div>
                                </div>
                            </div>`;
                        }
                        
                        // Also show PMIDs if available (PMC often returns both)
                        if (data.pmids && data.pmids.length > 0) {
                            const uniqueId = `source-${nctId}-${sourceName}-pmids-${Date.now()}`;
                            
                            html += `<div class="data-field pmid-list-field">
                                <strong>PMIDs (${data.pmids.length} total):</strong>
                                <button class="toggle-list-btn" onclick="app.togglePMIDList('${uniqueId}')">
                                    Show All
                                </button>
                                <div id="${uniqueId}" class="pmid-list-container hidden">
                                    <div class="pmid-grid">
                                        ${data.pmids.map(pmid => `
                                            <a href="https://pubmed.ncbi.nlm.nih.gov/${pmid}/" 
                                            target="_blank" 
                                            rel="noopener noreferrer"
                                            class="pmid-link">${pmid}</a>
                                        `).join('')}
                                    </div>
                                </div>
                            </div>`;
                        }
                    } else if (sourceName === 'pmc_bioc') {
                        if (data.conversion_performed) {
                            html += `<div class="search-info">
                                <span class="search-info-label">🔄 Conversion:</span>
                                <span class="search-info-value">PMCIDs converted to PMIDs</span>
                            </div>`;
                        }
                        
                        html += `<div class="data-field">
                            <strong>Articles Found:</strong> ${resultCount}
                        </div>`;
                        
                        if (data.pmids_used && data.pmids_used.length > 0) {
                            html += `<div class="data-field pmid-field">
                                <strong>PMIDs Fetched:</strong> 
                                <span class="id-list">${data.pmids_used.join(', ')}</span>
                            </div>`;
                        }
                        
                        if (data.errors && data.errors.length > 0) {
                            const errorsByType = {};
                            data.errors.forEach(err => {
                                const type = err.type || 'other';
                                if (!errorsByType[type]) errorsByType[type] = [];
                                errorsByType[type].push(err);
                            });
                            
                            html += `<div class="data-field error-details">
                                <strong>Errors:</strong> ${data.errors.length} article(s) could not be retrieved
                                <ul class="error-breakdown">`;
                            
                            Object.entries(errorsByType).forEach(([type, errors]) => {
                                const typeLabels = {
                                    'not_found': '📭 Not available in PubTator3 (may not be open access)',
                                    'timeout': '⏱️ Timeout',
                                    'http_error': '⚠️ HTTP Error',
                                    'exception': '❌ Exception',
                                    'other': '❓ Unknown'
                                };
                                
                                const label = typeLabels[type] || type;
                                const pmids = errors.map(e => e.pmid).join(', ');
                                
                                html += `<li>${label}: ${pmids}`;
                                
                                if (type === 'not_found' && errors[0].note) {
                                    html += `<br><small class="error-note">${this.escapeHtml(errors[0].note)}</small>`;
                                }
                                
                                html += `</li>`;
                            });
                            
                            html += `</ul></div>`;
                        }
                    }
                    
                    html += `</div></div>`;
                } else if (sourceData && sourceData.error) {
                    html += `
                        <div class="source-section">
                            <div class="source-header">
                                <strong>📚 ${this.escapeHtml(apiDisplayName)}</strong>
                                <span class="source-status error">✗</span>
                            </div>
                            <div class="source-content error">
                                ${this.escapeHtml(sourceData.error || 'Unknown error')}
                            </div>
                        </div>
                    `;
                }
            });
            
            // Display extended sources
            if (sources.extended && Object.keys(sources.extended).length > 0) {
                html += `
                    <div class="extended-sources-header">
                        <h4>🔬 Extended Sources</h4>
                    </div>
                `;
                
                Object.entries(sources.extended).forEach(([sourceName, sourceData]) => {
                    const apiInfo = this.getAPIInfo(sourceName);
                    const apiDisplayName = apiInfo ? apiInfo.name : sourceName;
                    const uniqueId = `ext-${nctId}-${sourceName}-${Date.now()}`;
                    
                    if (sourceData && sourceData.success && sourceData.data) {
                        const data = sourceData.data;
                        const resultCount = this.countSourceResults(sourceName, data);
                        
                        html += `
                            <div class="source-section extended-source">
                                <div class="source-header">
                                    <strong>🔬 ${this.escapeHtml(apiDisplayName)}</strong>
                                    <div class="source-header-right">
                                        <span class="source-count-badge">${resultCount} result${resultCount !== 1 ? 's' : ''}</span>
                                        <span class="source-status success">✓</span>
                                    </div>
                                </div>
                                <div class="source-content">
                        `;
                        
                        if (data.query) {
                            html += `<div class="search-info">
                                <span class="search-info-label">🔍 Query:</span>
                                <span class="search-info-value">"${this.escapeHtml(data.query)}"</span>
                            </div>`;
                        }
                        
                        if (data.search_terms_used && data.search_terms_used.length > 0) {
                            html += `<div class="search-info">
                                <span class="search-info-label">📝 Search Terms:</span>
                                <span class="search-info-value">${data.search_terms_used.map(t => `"${this.escapeHtml(t)}"`).join(', ')}</span>
                            </div>`;
                        }
                        
                        if (data.results && Array.isArray(data.results)) {
                            html += `<div class="data-field">
                                <strong>Results Found:</strong> ${data.results.length}
                            </div>`;
                            
                            const displayCount = Math.min(3, data.results.length);
                            const visibleResults = data.results.slice(0, displayCount);
                            const hiddenResults = data.results.slice(displayCount);
                            
                            html += `<div class="extended-results-container">`;
                            
                            visibleResults.forEach((result, idx) => {
                                html += `
                                    <div class="extended-result-item">
                                        <div class="result-number">${idx + 1}.</div>
                                        <div class="result-content">
                                            ${result.title ? `<div class="result-title">${this.escapeHtml(result.title)}</div>` : ''}
                                            ${result.snippet ? `<div class="result-snippet">${this.escapeHtml(result.snippet)}</div>` : ''}
                                            ${result.url ? `<div class="result-link"><a href="${result.url}" target="_blank" rel="noopener noreferrer">View Source →</a></div>` : ''}
                                        </div>
                                    </div>
                                `;
                            });
                            
                            html += `</div>`;
                            
                            if (hiddenResults.length > 0) {
                                html += `
                                    <button class="show-more-button" onclick="app.toggleExtendedResults('${uniqueId}-hidden')">
                                        ... and ${hiddenResults.length} more results
                                    </button>
                                    <div id="${uniqueId}-hidden" class="extended-results-container hidden">
                                `;
                                
                                hiddenResults.forEach((result, idx) => {
                                    html += `
                                        <div class="extended-result-item">
                                            <div class="result-number">${displayCount + idx + 1}.</div>
                                            <div class="result-content">
                                                ${result.title ? `<div class="result-title">${this.escapeHtml(result.title)}</div>` : ''}
                                                ${result.snippet ? `<div class="result-snippet">${this.escapeHtml(result.snippet)}</div>` : ''}
                                                ${result.url ? `<div class="result-link"><a href="${result.url}" target="_blank" rel="noopener noreferrer">View Source →</a></div>` : ''}
                                            </div>
                                        </div>
                                    `;
                                });
                                
                                html += `</div>`;
                            }
                        } else {
                            html += `<div class="data-field">
                                <strong>Status:</strong> Data retrieved successfully
                            </div>`;
                        }
                        
                        html += `</div></div>`;
                        
                    } else if (sourceData && sourceData.error) {
                        html += `
                            <div class="source-section extended-source">
                                <div class="source-header">
                                    <strong>🔬 ${this.escapeHtml(apiDisplayName)}</strong>
                                    <span class="source-status error">✗</span>
                                </div>
                                <div class="source-content error">
                                    ${this.escapeHtml(sourceData.error || 'Unknown error')}
                                </div>
                            </div>
                        `;
                    }
                });
            }
            
            html += `</div>`;
        });
        
        resultsDiv.innerHTML = html;
        
        // Show results, hide input
        inputArea.classList.add('hidden');
        resultsDiv.classList.add('active');
    },

    // ============================================================================
    // Extended Source Formatting Methods
    // ============================================================================

    formatDuckDuckGoDisplay(data) {
        let html = '';
        
        if (data.query) {
            html += `<div class="search-info">
                <span class="search-info-label">🔍 Query:</span>
                <span class="search-info-value">"${this.escapeHtml(data.query)}"</span>
            </div>`;
        }
        
        if (data.search_terms_used && data.search_terms_used.length > 0) {
            html += `<div class="search-info">
                <span class="search-info-label">📝 Search Terms:</span>
                <span class="search-info-value">${data.search_terms_used.map(t => `"${this.escapeHtml(t)}"`).join(', ')}</span>
            </div>`;
        }
        
        if (data.results && Array.isArray(data.results)) {
            html += `<div class="data-field">
                <strong>Results Found:</strong> ${data.results.length}
            </div>`;
            
            const displayCount = Math.min(3, data.results.length);
            const visibleResults = data.results.slice(0, displayCount);
            const hiddenResults = data.results.slice(displayCount);
            
            html += `<div class="extended-results-container">`;
            
            visibleResults.forEach((result, idx) => {
                html += `
                    <div class="extended-result-item">
                        <div class="result-number">${idx + 1}.</div>
                        <div class="result-content">
                            ${result.title ? `<div class="result-title">${this.escapeHtml(result.title)}</div>` : ''}
                            ${result.snippet ? `<div class="result-snippet">${this.escapeHtml(result.snippet)}</div>` : ''}
                            ${result.url ? `<div class="result-link"><a href="${result.url}" target="_blank" rel="noopener noreferrer">View Source →</a></div>` : ''}
                        </div>
                    </div>
                `;
            });
            
            html += `</div>`;
            
            if (hiddenResults.length > 0) {
                const uniqueId = `ddg-hidden-${Date.now()}`;
                html += `
                    <button class="show-more-button" onclick="app.toggleExtendedResults('${uniqueId}')">
                        ... and ${hiddenResults.length} more results
                    </button>
                    <div id="${uniqueId}" class="extended-results-container hidden">
                `;
                
                hiddenResults.forEach((result, idx) => {
                    html += `
                        <div class="extended-result-item">
                            <div class="result-number">${displayCount + idx + 1}.</div>
                            <div class="result-content">
                                ${result.title ? `<div class="result-title">${this.escapeHtml(result.title)}</div>` : ''}
                                ${result.snippet ? `<div class="result-snippet">${this.escapeHtml(result.snippet)}</div>` : ''}
                                ${result.url ? `<div class="result-link"><a href="${result.url}" target="_blank" rel="noopener noreferrer">View Source →</a></div>` : ''}
                            </div>
                        </div>
                    `;
                });
                
                html += `</div>`;
            }
        }
        
        return html;
    },

    formatOpenFDADisplay(data) {
        let html = '';
        
        if (data.query) {
            html += `<div class="search-info">
                <span class="search-info-label">🔍 Query:</span>
                <span class="search-info-value">"${this.escapeHtml(data.query)}"</span>
            </div>`;
        }
        
        if (data.results && Array.isArray(data.results)) {
            html += `<div class="data-field">
                <strong>FDA Records Found:</strong> ${data.results.length}
            </div>`;
            
            const displayCount = Math.min(3, data.results.length);
            const visibleResults = data.results.slice(0, displayCount);
            const hiddenResults = data.results.slice(displayCount);
            
            html += `<div class="extended-results-container">`;
            
            visibleResults.forEach((result, idx) => {
                html += `
                    <div class="extended-result-item">
                        <div class="result-number">${idx + 1}.</div>
                        <div class="result-content">
                            ${result.brand_name ? `<div class="result-title"><strong>Brand:</strong> ${this.escapeHtml(result.brand_name)}</div>` : ''}
                            ${result.generic_name ? `<div class="result-snippet"><strong>Generic:</strong> ${this.escapeHtml(result.generic_name)}</div>` : ''}
                            ${result.manufacturer_name ? `<div class="result-snippet"><strong>Manufacturer:</strong> ${this.escapeHtml(result.manufacturer_name)}</div>` : ''}
                            ${result.product_type ? `<div class="result-snippet"><strong>Type:</strong> ${this.escapeHtml(result.product_type)}</div>` : ''}
                        </div>
                    </div>
                `;
            });
            
            html += `</div>`;
            
            if (hiddenResults.length > 0) {
                const uniqueId = `fda-hidden-${Date.now()}`;
                html += `
                    <button class="show-more-button" onclick="app.toggleExtendedResults('${uniqueId}')">
                        ... and ${hiddenResults.length} more results
                    </button>
                    <div id="${uniqueId}" class="extended-results-container hidden">
                `;
                
                hiddenResults.forEach((result, idx) => {
                    html += `
                        <div class="extended-result-item">
                            <div class="result-number">${displayCount + idx + 1}.</div>
                            <div class="result-content">
                                ${result.brand_name ? `<div class="result-title"><strong>Brand:</strong> ${this.escapeHtml(result.brand_name)}</div>` : ''}
                                ${result.generic_name ? `<div class="result-snippet"><strong>Generic:</strong> ${this.escapeHtml(result.generic_name)}</div>` : ''}
                                ${result.manufacturer_name ? `<div class="result-snippet"><strong>Manufacturer:</strong> ${this.escapeHtml(result.manufacturer_name)}</div>` : ''}
                                ${result.product_type ? `<div class="result-snippet"><strong>Type:</strong> ${this.escapeHtml(result.product_type)}</div>` : ''}
                            </div>
                        </div>
                    `;
                });
                
                html += `</div>`;
            }
        } else {
            html += `<div class="data-field">
                <strong>Status:</strong> Data retrieved successfully
            </div>`;
        }
        
        return html;
    },

    formatGenericExtendedDisplay(data) {
        let html = '';
        
        if (data.query) {
            html += `<div class="search-info">
                <span class="search-info-label">🔍 Query:</span>
                <span class="search-info-value">"${this.escapeHtml(data.query)}"</span>
            </div>`;
        }
        
        if (data.search_terms_used && data.search_terms_used.length > 0) {
            html += `<div class="search-info">
                <span class="search-info-label">📝 Search Terms:</span>
                <span class="search-info-value">${data.search_terms_used.map(t => `"${this.escapeHtml(t)}"`).join(', ')}</span>
            </div>`;
        }
        
        if (data.results && Array.isArray(data.results)) {
            html += `<div class="data-field">
                <strong>Results Found:</strong> ${data.results.length}
            </div>`;
            
            const displayCount = Math.min(3, data.results.length);
            const visibleResults = data.results.slice(0, displayCount);
            const hiddenResults = data.results.slice(displayCount);
            
            html += `<div class="extended-results-container">`;
            
            visibleResults.forEach((result, idx) => {
                html += `
                    <div class="extended-result-item">
                        <div class="result-number">${idx + 1}.</div>
                        <div class="result-content">
                            ${result.title ? `<div class="result-title">${this.escapeHtml(result.title)}</div>` : ''}
                            ${result.snippet ? `<div class="result-snippet">${this.escapeHtml(result.snippet)}</div>` : ''}
                            ${result.url ? `<div class="result-link"><a href="${result.url}" target="_blank" rel="noopener noreferrer">View Source →</a></div>` : ''}
                        </div>
                    </div>
                `;
            });
            
            html += `</div>`;
            
            if (hiddenResults.length > 0) {
                const uniqueId = `ext-hidden-${Date.now()}`;
                html += `
                    <button class="show-more-button" onclick="app.toggleExtendedResults('${uniqueId}')">
                        ... and ${hiddenResults.length} more results
                    </button>
                    <div id="${uniqueId}" class="extended-results-container hidden">
                `;
                
                hiddenResults.forEach((result, idx) => {
                    html += `
                        <div class="extended-result-item">
                            <div class="result-number">${displayCount + idx + 1}.</div>
                            <div class="result-content">
                                ${result.title ? `<div class="result-title">${this.escapeHtml(result.title)}</div>` : ''}
                                ${result.snippet ? `<div class="result-snippet">${this.escapeHtml(result.snippet)}</div>` : ''}
                                ${result.url ? `<div class="result-link"><a href="${result.url}" target="_blank" rel="noopener noreferrer">View Source →</a></div>` : ''}
                            </div>
                        </div>
                    `;
                });
                
                html += `</div>`;
            }
        } else {
            html += `<div class="data-field">
                <strong>Status:</strong> Data retrieved successfully
            </div>`;
        }
        
        return html;
    },

    countSourceResults(sourceName, data) {
        if (!data) return 0;
        
        switch (sourceName) {
            case 'clinicaltrials':
            case 'clinical_trials':
                return 1;
            
            case 'pubmed':
                return data.pmids ? data.pmids.length : 0;
            
            case 'pmc':
                return data.pmcids ? data.pmcids.length : 0;
            
            case 'pmc_bioc':
                return data.total_fetched || 0;

            default:
                if (data.results && Array.isArray(data.results)) {
                    return data.results.length;
                }
                if (data.total_found) {
                    return data.total_found;
                }
                return 0;
        }
    },
    getAPIInfo(sourceId) {
        if (!this.apiRegistry) return null;
        
        let api = this.apiRegistry.core.find(a => a.id === sourceId);
        if (api) return api;
        
        api = this.apiRegistry.extended.find(a => a.id === sourceId);
        return api;
    },

    // =========================================================================
    // Research Assistant Mode - NCT Annotation System
    // =========================================================================

    async initializeResearchMode() {
        console.log('🚀 Initializing Research Assistant mode...');
        
        const container = document.getElementById('research-container');
        container.innerHTML = '';
        
        // Remove any existing info bar
        this.removeInfoBar();
        
        // Reset state
        this.currentModel = null;
        this.currentConversationId = null;
        
        const input = document.getElementById('research-input');
        input.disabled = true;
        input.placeholder = 'Select a model first...';
        
        const loadingId = this.addMessage('research-container', 'system', 
            '🔄 Loading available models...');
        
        try {
            // Fetch models from chat service
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
                    this.addMessage('research-container', 'error', 
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
                this.showResearchModelSelection();
                
            } else {
                const errorText = await response.text();
                console.error('❌ Failed to load models:', response.status, errorText);
                
                document.getElementById(loadingId)?.remove();
                this.addMessage('research-container', 'error', 
                    `❌ Failed to load models (HTTP ${response.status})\n\n` +
                    `The chat service may not be running properly.\n\n` +
                    `To fix:\n` +
                    `1. Restart chat service:\n` +
                    `   cd "standalone modules/chat_with_llm"\n` +
                    `   uvicorn chat_api:app --port 9003 --reload\n\n` +
                    `2. Check: curl http://localhost:9003/models\n\n` +
                    `Error: ${errorText.substring(0, 200)}`);
            }
        } catch (error) {
            console.error('❌ Exception loading models:', error);
            
            document.getElementById(loadingId)?.remove();
            this.addMessage('research-container', 'error', 
                '❌ Connection Error\n\n' +
                'Cannot connect to the chat service.\n\n' +
                'The chat service must be running on port 9003.\n\n' +
                'To start it:\n' +
                '1. Open terminal\n' +
                '2. cd amp_llm_v3/standalone\\ modules/chat_with_llm\n' +
                '3. uvicorn chat_api:app --port 9003 --reload\n\n' +
                'Then refresh this page.\n\n' +
                `Error: ${error.message}`);
        }
    },

    showResearchModelSelection() {
        console.log('📦 Showing model selection for Research Assistant');
        
        const container = document.getElementById('research-container');
        
        this.addMessage('research-container', 'system', 
            '🔬 Clinical Trial Annotation System\n\n' +
            'This tool will:\n' +
            '1. Load trial data from saved JSON files\n' +
            '2. Parse and extract relevant information\n' +
            '3. Generate structured annotation prompts\n' +
            '4. Use AI to annotate peptide clinical trials\n\n' +
            '📋 Select a model to begin:');
        
        const selectionDiv = document.createElement('div');
        selectionDiv.className = 'model-selection';
        selectionDiv.id = 'research-model-selection';
        
        this.availableModels.forEach((model) => {
            const modelName = typeof model === 'string' ? model : (model.name || String(model));
            
            console.log(`Creating button for model: ${modelName}`);
            
            const button = document.createElement('button');
            button.className = 'model-button';
            button.type = 'button';
            button.setAttribute('data-model-name', modelName);
            
            const icon = document.createElement('span');
            icon.textContent = '🤖';
            icon.style.fontSize = '1.2em';
            
            const name = document.createElement('span');
            name.textContent = modelName;
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
            
            button.onclick = function() {
                const selectedModel = this.getAttribute('data-model-name');
                console.log('🖱️  Model selected:', selectedModel);
                app.selectResearchModel(selectedModel);
            };
            
            selectionDiv.appendChild(button);
        });
        
        container.appendChild(selectionDiv);
        
        requestAnimationFrame(() => {
            container.scrollTop = container.scrollHeight;
        });
        
        console.log('✅ Model selection displayed');
    },

    async selectResearchModel(modelName) {
        console.log('🎯 Selected model for research:', modelName);
        
        this.currentModel = modelName;
        
        // Remove model selection
        const modelSelection = document.getElementById('research-model-selection');
        if (modelSelection) {
            modelSelection.remove();
        }
        
        // Create info bar
        this.ensureChatInfoBar();
        
        // Show success and instructions
        this.addMessage('research-container', 'system', 
            `✅ Model Selected: ${modelName}\n\n` +
            `📝 How to use:\n\n` +
            `1. Enter an NCT ID (e.g., NCT12345678)\n` +
            `2. System finds the JSON file from File Manager\n` +
            `3. Parses data and generates annotation prompt\n` +
            `4. ${modelName} annotates the clinical trial\n` +
            `5. Structured annotation is returned\n\n` +
            `⚠️  Important: Run NCT Lookup first!\n` +
            `The system needs trial data before it can annotate.\n\n` +
            `💡 Commands:\n` +
            `• Type an NCT ID to annotate\n` +
            `• Type "models" to switch models\n` +
            `• Type "exit" to return to menu`);
        
        // Enable input
        const input = document.getElementById('research-input');
        input.disabled = false;
        input.placeholder = 'Enter NCT ID (e.g., NCT12345678)...';
        input.focus();
        
        console.log('✅ Research Assistant ready');
    },

    async sendResearchMessage(message) {
        const trimmedMessage = message.trim();
        const command = trimmedMessage.toLowerCase();
        
        // Handle commands
        if (command === 'exit' || command === 'main menu') {
            this.showMenu();
            return;
        }
        
        if (command === 'models') {
            const container = document.getElementById('research-container');
            container.innerHTML = '';
            this.removeInfoBar();
            this.initializeResearchMode();
            return;
        }
        
        // Extract NCT ID
        const nctId = trimmedMessage.toUpperCase();
        
        // Validate NCT ID format
        if (!nctId.match(/^NCT\d{8}$/)) {
            this.addMessage('research-container', 'error', 
                '❌ Invalid NCT ID format.\n\n' +
                'Please enter in format: NCT12345678\n' +
                'Example: NCT04123456\n\n' +
                '💡 Commands:\n' +
                '• "models" - Switch models\n' +
                '• "exit" - Return to menu');
            return;
        }
        
        if (!this.currentModel) {
            this.addMessage('research-container', 'error', 
                '❌ No model selected. Please select a model first.');
            return;
        }
        
        this.addMessage('research-container', 'user', `Annotate: ${nctId}`);
        
        // Research API runs on port 9003
        const RESEARCH_API = 'http://localhost:9003';
        
        // Show initial processing message
        const processingId = this.addMessage('research-container', 'system', 
            `🔄 Processing ${nctId}...\n\n` +
            `⏳ This may take 1-3 minutes depending on whether\n` +
            `   data needs to be fetched automatically.\n\n` +
            `Steps:\n` +
            `1. Check for existing data file\n` +
            `2. Auto-fetch if needed (30-60s)\n` +
            `3. Generate annotation prompt\n` +
            `4. Send to LLM for annotation (30-90s)`);
        
        const startTime = Date.now();
        
        try {
            const response = await fetch(`${RESEARCH_API}/api/research/annotate`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    nct_id: nctId,
                    model: this.currentModel,
                    temperature: 0.15,
                    auto_fetch: true  // Enable automatic fetching
                })
            });
            
            const endTime = Date.now();
            const duration = ((endTime - startTime) / 1000).toFixed(1);
            
            document.getElementById(processingId)?.remove();
            
            if (response.ok) {
                const data = await response.json();
                
                // Show if data was auto-fetched
                let fetchNote = '';
                if (data.auto_fetched) {
                    fetchNote = `\n✨ Data was automatically fetched from NCT Lookup\n`;
                }
                
                // Display annotation result
                this.addMessage('research-container', 'assistant', 
                    `✅ Annotation Complete for ${data.nct_id}\n\n` +
                    `═══════════════════════════════════\n` +
                    `Model: ${data.model}\n` +
                    `Status: ${data.status}\n` +
                    `Processing Time: ${duration}s${fetchNote}\n` +
                    `═══════════════════════════════════\n\n` +
                    `${data.annotation}\n\n` +
                    `═══════════════════════════════════\n\n` +
                    `💾 To save this annotation:\n` +
                    `   Copy the text above or export as file\n\n` +
                    `🔄 To annotate another trial:\n` +
                    `   Enter a new NCT ID\n\n` +
                    `📊 Sources used: ${this.countSources(data.sources_used)}`);
                
                // Log sources used for debugging
                console.log('📚 Sources used for annotation:', data.sources_used);
                
                // Offer to save
                this.addMessage('research-container', 'system', 
                    `💡 Next steps:\n\n` +
                    `• Enter another NCT ID to annotate\n` +
                    `• Type "models" to switch models\n` +
                    `• Type "exit" to return to menu`);
                
            } else {
                const errorText = await response.text();
                let errorData;
                try {
                    errorData = JSON.parse(errorText);
                } catch {
                    errorData = { detail: errorText };
                }
                
                this.addMessage('research-container', 'error', 
                    `❌ Annotation Failed\n\n` +
                    `Error: ${errorData.detail}\n\n` +
                    `Possible issues:\n` +
                    `• NCT Lookup service not running (port 8000)\n` +
                    `• Invalid NCT ID or trial not found\n` +
                    `• Model ${this.currentModel} is not responding\n` +
                    `• Network connectivity issues\n\n` +
                    `Try:\n` +
                    `1. Verify NCT ID is correct\n` +
                    `2. Check if all services are running\n` +
                    `3. Try a different model`);
            }
            
        } catch (error) {
            if (document.getElementById(processingId)) {
                document.getElementById(processingId).remove();
            }
            
            this.addMessage('research-container', 'error', 
                `❌ Connection Error\n\n${error.message}\n\n` +
                `Cannot connect to Research API (port 9003).\n\n` +
                `The Research API must be running.\n\n` +
                `To start it:\n` +
                `1. Open a new terminal\n` +
                `2. cd amp_llm_v3/standalone\\ modules/llm_assistant\n` +
                `3. python -m uvicorn research_assistant_api:app --port 9003 --reload\n\n` +
                `Or use: ./start_all.sh`);
            console.error('Research API connection error:', error);
        }
    },

    countSources(sources) {
        if (!sources) return 0;
        
        let count = 0;
        
        // Count core sources
        if (sources.clinicaltrials || sources.clinical_trials) count++;
        if (sources.pubmed) count++;
        if (sources.pmc) count++;
        if (sources.pmc_bioc) count++;
        
        // Count extended sources
        if (sources.extended) {
            count += Object.keys(sources.extended).length;
        }
        
        return count;
    },

    showToast(message, type = 'success', duration = 3000) {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.innerHTML = message;
        
        document.body.appendChild(toast);
        
        requestAnimationFrame(() => {
            toast.classList.add('toast-show');
        });
        
        setTimeout(() => {
            toast.classList.remove('toast-show');
            toast.classList.add('toast-hide');
            
            setTimeout(() => {
                document.body.removeChild(toast);
            }, 300);
        }, duration);
    },

    toggleExpandedList(elementId) {
        const element = document.getElementById(elementId);
        if (element) {
            element.classList.toggle('hidden');
            const toggle = element.previousElementSibling;
            if (toggle && toggle.classList.contains('show-more-inline')) {
                const isHidden = element.classList.contains('hidden');
                const countMatch = toggle.textContent.match(/\d+/);
                const count = countMatch ? countMatch[0] : '';
                toggle.innerHTML = isHidden ? 
                    `<strong>(+${count} more)</strong>` : 
                    `<strong>(show less)</strong>`;
            }
        }
    },

    toggleExtendedResults(elementId) {
        const element = document.getElementById(elementId);
        const button = document.querySelector(`[onclick="app.toggleExtendedResults('${elementId}')"]`);
        if (element && button) {
            element.classList.toggle('hidden');
            const isHidden = element.classList.contains('hidden');
            const countMatch = button.textContent.match(/\d+/);
            const count = countMatch ? countMatch[0] : '';
            button.textContent = isHidden ? 
                `... and ${count} more results` : 
                `Show less`;
        }
    },

    togglePMIDList(elementId) {
        const element = document.getElementById(elementId);
        const button = document.querySelector(`[onclick="app.togglePMIDList('${elementId}')"]`);
        if (element && button) {
            element.classList.toggle('hidden');
            const isHidden = element.classList.contains('hidden');
            button.textContent = isHidden ? 'Show All' : 'Hide';
            
            // Smooth scroll to button if showing
            if (!isHidden) {
                button.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }
        }
    },

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    console.log('📄 DOM Content Loaded');
    app.init();
});