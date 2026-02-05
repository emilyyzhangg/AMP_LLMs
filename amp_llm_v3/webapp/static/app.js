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
    annotationModeSelected: false,  // Track annotation mode selection
    annotationOutputFormat: 'llm_optimized',  // 'json' or 'llm_optimized' - format for LLM input
    annotationEmailNotify: false,  // Whether to send email notification on completion
    annotationNotifyEmail: '',  // Email address for notification
    emailConfigured: false,  // Whether email is configured on server
    modelParameters: null,  // Cached model parameters from API
    customModelParams: {},  // User-modified parameter values
    nctResults: null,
    selectedFile: null,
    selectedCSVFile: null,  // Track selected CSV file for batch annotation
    files: [],
    availableModels: [],
    availableThemes: [],

    // Session-based chat storage (per model)
    sessionChats: {},

    // Jobs management
    jobsPollingInterval: null,
    jobsPanelOpen: false,

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
    // Jobs Management
    // =========================================================================

    async showJobsPanel() {
        this.jobsPanelOpen = true;
        document.getElementById('jobs-modal')?.classList.remove('hidden');
        await this.refreshJobs();
    },

    hideJobsPanel() {
        this.jobsPanelOpen = false;
        document.getElementById('jobs-modal')?.classList.add('hidden');
    },

    async refreshJobs() {
        const jobsList = document.getElementById('jobs-list');
        if (!jobsList) return;

        jobsList.innerHTML = '<div class="loading">Loading jobs...</div>';

        try {
            const response = await fetch(`${this.API_BASE}/api/chat/jobs`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();
            this.renderJobsList(data.jobs || []);
            this.updateJobsBadge(data.active || 0);

        } catch (error) {
            console.error('Failed to fetch jobs:', error);
            jobsList.innerHTML = `
                <div class="no-jobs">
                    <div class="no-jobs-icon">⚠️</div>
                    <p>Failed to load jobs</p>
                    <p style="font-size: 12px;">${error.message}</p>
                </div>
            `;
        }
    },

    renderJobsList(jobs) {
        const jobsList = document.getElementById('jobs-list');
        if (!jobsList) return;

        // Check if there are any completed/failed jobs
        const hasCompletedJobs = jobs.some(j => j.status === 'completed' || j.status === 'failed');

        // Show/hide clear button
        const clearBtn = document.getElementById('clear-completed-btn');
        if (clearBtn) {
            clearBtn.classList.toggle('hidden', !hasCompletedJobs);
        }

        if (jobs.length === 0) {
            jobsList.innerHTML = `
                <div class="no-jobs">
                    <div class="no-jobs-icon">📋</div>
                    <p>No annotation jobs</p>
                    <p style="font-size: 12px;">Jobs will appear here when you start annotating</p>
                </div>
            `;
            return;
        }

        jobsList.innerHTML = jobs.map(job => {
            const isActive = job.status === 'processing' || job.status === 'pending';
            const isCompleted = job.status === 'completed';
            const isFailed = job.status === 'failed';
            const elapsed = this.formatElapsedTime(job.elapsed_seconds);
            const startedAt = this.formatJobDateTime(job.created_at);

            // Status icon based on job state
            const statusIcon = isCompleted ? '✅' : isFailed ? '❌' : isActive ? '⏳' : '📋';
            const statusClass = isCompleted ? 'completed' : isFailed ? 'failed' : job.status;

            return `
                <div class="job-card ${statusClass}">
                    <div class="job-header">
                        <span class="job-id">${statusIcon} Job: ${job.job_id.substring(0, 8)}...</span>
                        <span class="job-status ${statusClass}">${job.status.toUpperCase()}</span>
                    </div>

                    <div class="job-details">
                        <div class="job-detail"><strong>Model:</strong> ${job.model || 'Unknown'}</div>
                        <div class="job-detail"><strong>Trials:</strong> ${job.processed_trials}/${job.total_trials}</div>
                        <div class="job-detail"><strong>Source:</strong> ${job.original_filename || 'Manual'}</div>
                        <div class="job-detail"><strong>Started:</strong> ${startedAt}</div>
                        <div class="job-detail"><strong>Elapsed:</strong> ${elapsed}</div>
                        ${job.notification_email ? `<div class="job-detail"><strong>Email:</strong> ${job.notification_email}</div>` : ''}
                        ${job.current_nct ? `<div class="job-detail"><strong>Current:</strong> ${job.current_nct}</div>` : ''}
                    </div>

                    ${job.total_trials > 0 ? `
                        <div class="job-progress-bar">
                            <div class="job-progress-fill ${statusClass}" style="width: ${job.percent_complete}%"></div>
                        </div>
                    ` : ''}

                    <div style="font-size: 12px; color: var(--text-secondary); margin-bottom: 12px;">
                        ${job.progress || 'Queued'}
                    </div>

                    <div class="job-actions">
                        ${isActive ? `
                            <button class="btn-cancel" onclick="app.cancelJob('${job.job_id}')">
                                🛑 Cancel Job
                            </button>
                        ` : ''}
                        ${isCompleted ? `
                            <button class="btn-download" onclick="window.open('${this.API_BASE}/api/chat/download/${job.job_id}', '_blank')">
                                📥 Download CSV
                            </button>
                        ` : ''}
                    </div>
                </div>
            `;
        }).join('');
    },

    formatElapsedTime(seconds) {
        if (seconds < 60) return `${seconds}s`;
        if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
        const hours = Math.floor(seconds / 3600);
        const mins = Math.floor((seconds % 3600) / 60);
        return `${hours}h ${mins}m`;
    },

    formatJobDateTime(isoString) {
        if (!isoString) return 'Unknown';
        const date = new Date(isoString);
        return date.toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
            year: 'numeric',
            hour: 'numeric',
            minute: '2-digit',
            hour12: true
        });
    },

    async cancelJob(jobId) {
        if (!confirm(`Cancel job ${jobId.substring(0, 8)}...?\n\nThis will stop the annotation process.`)) {
            return;
        }

        try {
            const response = await fetch(`${this.API_BASE}/api/chat/jobs/${jobId}`, {
                method: 'DELETE'
            });

            if (response.ok) {
                const result = await response.json();
                console.log('Job cancelled:', result);
                await this.refreshJobs();
            } else {
                const error = await response.text();
                alert(`Failed to cancel job: ${error}`);
            }
        } catch (error) {
            console.error('Failed to cancel job:', error);
            alert(`Error cancelling job: ${error.message}`);
        }
    },

    async clearCompletedJobs() {
        try {
            const response = await fetch(`${this.API_BASE}/api/chat/jobs/completed`, {
                method: 'DELETE'
            });

            if (response.ok) {
                const result = await response.json();
                console.log('Cleared completed jobs:', result);
                await this.refreshJobs();
            } else {
                const error = await response.text();
                alert(`Failed to clear jobs: ${error}`);
            }
        } catch (error) {
            console.error('Failed to clear completed jobs:', error);
            alert(`Error clearing jobs: ${error.message}`);
        }
    },

    updateJobsBadge(activeCount) {
        const badges = document.querySelectorAll('.jobs-badge');
        badges.forEach(badge => {
            if (activeCount > 0) {
                badge.textContent = activeCount;
                badge.classList.remove('hidden');
            } else {
                badge.classList.add('hidden');
            }
        });
    },

    startJobsPolling() {
        // Poll for job updates every 10 seconds
        if (this.jobsPollingInterval) {
            clearInterval(this.jobsPollingInterval);
        }

        // Initial fetch
        this.fetchJobCount();

        this.jobsPollingInterval = setInterval(() => {
            this.fetchJobCount();
        }, 10000);
    },

    async fetchJobCount() {
        try {
            const response = await fetch(`${this.API_BASE}/api/chat/jobs`);
            if (response.ok) {
                const data = await response.json();
                this.updateJobsBadge(data.active || 0);

                // If jobs panel is open, refresh the list
                if (this.jobsPanelOpen) {
                    this.renderJobsList(data.jobs || []);
                }
            }
        } catch (error) {
            // Silently fail - just for badge updates
            console.debug('Jobs poll failed:', error);
        }
    },

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

        // Start polling for job updates
        this.startJobsPolling();
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
            // In annotation mode, allow going back to settings/presets
            if (this.annotationModeSelected) {
                backButton.textContent = '← Back to Settings';
                backButton.onclick = () => {
                    if (this.currentModel) {
                        this.saveCurrentChat();
                    }

                    this.currentConversationId = null;
                    this.currentModel = null;
                    // Keep annotationModeSelected true so we go back to parameters, not mode selection

                    const container = document.getElementById('chat-container');
                    container.innerHTML = '';

                    this.removeInfoBar();
                    this.showModelParametersConfig(); // Go back to parameters config

                    const input = document.getElementById('chat-input');
                    input.disabled = true;
                    input.placeholder = 'Configure settings and select a model...';

                    this.updateBackButton();
                };
            } else {
                backButton.textContent = '← Back to Models';
                backButton.onclick = () => {
                    if (this.currentModel) {
                        this.saveCurrentChat();
                    }

                    this.currentConversationId = null;
                    this.currentModel = null;

                    // Reset annotation mode selection for fresh start
                    this.annotationModeSelected = false;

                    const container = document.getElementById('chat-container');
                    container.innerHTML = '';

                    this.removeInfoBar();
                    this.showModelSelection();

                    const input = document.getElementById('chat-input');
                    input.disabled = true;
                    input.placeholder = 'Select a model to start chatting...';

                    this.updateBackButton();
                };
            }
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
        
        // Reset annotation mode selection
        this.annotationModeSelected = false;
        
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

                // Add cloud models (OpenRouter)
                const cloudModels = [
                    { name: 'nemotron', cloud: true, label: '☁️ Nemotron (Cloud)' },
                    { name: 'nemotron-free', cloud: true, label: '☁️ Nemotron Free (Cloud)' }
                ];
                cloudModels.forEach(cm => {
                    // Check if not already in list
                    const exists = this.availableModels.some(m => 
                        (typeof m === 'string' ? m : m.name) === cm.name
                    );
                    if (!exists) {
                        this.availableModels.push(cm.name);
                    }
                });
                console.log('☁️ Added cloud models:', cloudModels.map(m => m.name));

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
                'The chat service must be running on port 9001.\n\n' +
                'To start it:\n' +
                '1. Open terminal\n' +
                '2. cd amp_llm_v3/standalone\\ modules/chat_with_llm\n' +
                '3. uvicorn chat_api:app --port 9001 --reload\n\n' +
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

        // Settings button for annotation mode - allows changing presets
        const settingsButton = (this.currentConversationId && this.annotationModeSelected) ?
            `<button class="settings-btn" onclick="app.showModelParametersModal()">⚙️ Settings</button>` : '';

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
            ${settingsButton}
            ${clearButton}
        `;

        console.log('✅ Info bar updated');
    },

    async showModelParametersModal() {
        console.log('Opening model parameters modal');

        // Fetch parameters if not already loaded
        if (!this.modelParameters) {
            await this.fetchModelParameters();
        }

        if (!this.modelParameters) {
            alert('Could not load model parameters');
            return;
        }

        // Create modal overlay
        const modalOverlay = document.createElement('div');
        modalOverlay.className = 'params-modal-overlay';
        modalOverlay.id = 'params-modal-overlay';
        modalOverlay.onclick = (e) => {
            if (e.target === modalOverlay) this.hideModelParametersModal();
        };

        // Create modal content
        const modalContent = document.createElement('div');
        modalContent.className = 'params-modal-content';
        modalContent.innerHTML = `
            <div class="params-modal-header">
                <h3>Model Parameters</h3>
                <button class="params-modal-close" onclick="app.hideModelParametersModal()">&times;</button>
            </div>
            <div class="params-modal-body">
                ${this.buildParameterControlsHTMLCompact()}
            </div>
        `;

        modalOverlay.appendChild(modalContent);
        document.body.appendChild(modalOverlay);

        // Attach event listeners
        this.attachParameterEventListenersModal();
    },

    hideModelParametersModal() {
        const modal = document.getElementById('params-modal-overlay');
        if (modal) modal.remove();
    },

    buildParameterControlsHTMLCompact() {
        const params = this.modelParameters.parameters;
        const presets = this.modelParameters.presets;

        let html = `<div class="preset-buttons-modal">`;
        for (const [key, preset] of Object.entries(presets)) {
            html += `<button class="preset-btn-modal" data-preset="${key}" title="${preset.description}">${preset.name}</button>`;
        }
        html += `</div>`;

        for (const [paramName, param] of Object.entries(params)) {
            const currentValue = this.customModelParams?.[paramName] ?? param.value;
            const isInteger = paramName === 'top_k' || paramName === 'num_ctx' || paramName === 'num_predict';
            const displayValue = isInteger ? Math.round(currentValue) : currentValue.toFixed(2);

            html += `
                <div class="param-group-modal">
                    <div class="param-label-row-modal">
                        <span class="param-label-modal">${param.name}</span>
                        <span class="param-value-modal" id="modal-value-${paramName}">${displayValue}</span>
                    </div>
                    <input type="range" class="param-slider-modal" id="modal-slider-${paramName}"
                           min="${param.min}" max="${param.max}" step="${param.step}" value="${currentValue}"
                           data-param="${paramName}" data-is-integer="${isInteger}">
                </div>
            `;
        }

        html += `<button class="params-apply-btn" onclick="app.hideModelParametersModal()">Apply & Close</button>`;

        return html;
    },

    attachParameterEventListenersModal() {
        // Preset buttons
        document.querySelectorAll('.preset-btn-modal').forEach(btn => {
            btn.addEventListener('click', async () => {
                const presetName = btn.dataset.preset;
                const result = await this.applyModelPreset(presetName);
                if (result) {
                    // Update modal sliders
                    for (const [paramName, value] of Object.entries(result.current)) {
                        const slider = document.getElementById(`modal-slider-${paramName}`);
                        const display = document.getElementById(`modal-value-${paramName}`);
                        if (slider) slider.value = value;
                        if (display) {
                            const isInteger = paramName === 'top_k' || paramName === 'num_ctx' || paramName === 'num_predict';
                            display.textContent = isInteger ? Math.round(value) : value.toFixed(2);
                        }
                    }
                }
            });
        });

        // Sliders
        document.querySelectorAll('.param-slider-modal').forEach(slider => {
            slider.addEventListener('input', (e) => {
                const paramName = e.target.dataset.param;
                const isInteger = e.target.dataset.isInteger === 'true';
                let value = parseFloat(e.target.value);
                if (isInteger) value = Math.round(value);

                const display = document.getElementById(`modal-value-${paramName}`);
                if (display) display.textContent = isInteger ? value : value.toFixed(2);
            });

            slider.addEventListener('change', async (e) => {
                const paramName = e.target.dataset.param;
                const isInteger = e.target.dataset.isInteger === 'true';
                let value = parseFloat(e.target.value);
                if (isInteger) value = Math.round(value);
                await this.updateModelParameter(paramName, value);
            });
        });
    },

    showModelSelection() {
        console.log('📦 Showing model selection');
        console.log('📊 Available models:', this.availableModels);
        console.log('📊 Current mode:', this.currentMode);
        console.log('📊 annotationModeSelected:', this.annotationModeSelected);
        
        const container = document.getElementById('chat-container');
        
        // STEP 1: Show annotation mode selection first (only for chat mode)
        if (this.currentMode === 'chat' && !this.annotationModeSelected) {
            console.log('✅ Showing annotation mode selection screen');
            this.addMessage('chat-container', 'system', 
                '🤖 Welcome to Chat Mode!\n\n' +
                'Please choose your chat type:');
            
            const annotationSelectionDiv = document.createElement('div');
            annotationSelectionDiv.className = 'model-selection';
            annotationSelectionDiv.id = 'annotation-mode-selection';
            
            // Regular chat button
            const regularButton = document.createElement('button');
            regularButton.className = 'model-button';
            regularButton.type = 'button';
            regularButton.innerHTML = `
                <span style="font-size: 1.2em;">💬</span>
                <span style="flex: 1; text-align: left; margin-left: 10px;">
                    <strong>Regular Chat</strong><br>
                    <small style="color: #666;">Conversational AI chat</small>
                </span>
                <span style="color: #666; font-size: 0.9em;">→</span>
            `;
            regularButton.onclick = () => {
                console.log('✅ Regular chat mode selected');
                this.annotationModeSelected = false;
                document.getElementById('annotation-mode-selection')?.remove();
                this.showModelSelectionStep2();
            };
            
            // Annotation mode button
            const annotationButton = document.createElement('button');
            annotationButton.className = 'model-button';
            annotationButton.type = 'button';
            annotationButton.innerHTML = `
                <span style="font-size: 1.2em;">🔬</span>
                <span style="flex: 1; text-align: left; margin-left: 10px;">
                    <strong>Annotation Mode</strong><br>
                    <small style="color: #666;">Annotate clinical trials with NCT IDs</small>
                </span>
                <span style="color: #666; font-size: 0.9em;">→</span>
            `;
            annotationButton.onclick = () => {
                console.log('✅ Annotation mode selected, showing format options');
                this.annotationModeSelected = true;
                document.getElementById('annotation-mode-selection')?.remove();
                this.showOutputFormatSelection();
            };

            annotationSelectionDiv.appendChild(regularButton);
            annotationSelectionDiv.appendChild(annotationButton);
            container.appendChild(annotationSelectionDiv);
            
            requestAnimationFrame(() => {
                container.scrollTop = container.scrollHeight;
            });
            
            this.updateBackButton();
            console.log('✅ Annotation mode selection displayed');
            return;
        }
        
        // If not chat mode or already selected, go directly to model selection
        this.showModelSelectionStep2();
    },
    
    showModelSelectionStep2() {
        console.log('📦 Showing model selection (Step 2)');
        
        const container = document.getElementById('chat-container');
        
        let modeInfo = '';
        if (this.currentMode === 'chat') {
            if (this.annotationModeSelected) {
                const formatLabel = this.annotationOutputFormat === 'llm_optimized' ?
                    '⚡ LLM-Optimized' : '📄 Full JSON';
                modeInfo = `\n\n🔬 Mode: Clinical Trial Annotation\n📊 Data Format: ${formatLabel}`;
            } else {
                modeInfo = '\n\n💬 Mode: Regular Chat';
            }
        }
        
        this.addMessage('chat-container', 'system', 
            `Select a model to start:${modeInfo}`);
        
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

    showOutputFormatSelection() {
        console.log('📦 Showing output format selection for annotation mode');

        const container = document.getElementById('chat-container');

        this.addMessage('chat-container', 'system',
            '🔬 Annotation Mode Selected\n\n' +
            'Choose the data format to feed to the LLM:\n\n' +
            '• **LLM-Optimized**: Structured, condensed format with tool hints\n' +
            '• **Full JSON**: Complete raw data from all sources');

        const formatSelectionDiv = document.createElement('div');
        formatSelectionDiv.className = 'model-selection';
        formatSelectionDiv.id = 'format-selection';

        // LLM-Optimized format button (recommended)
        const llmOptButton = document.createElement('button');
        llmOptButton.className = 'model-button';
        llmOptButton.type = 'button';
        llmOptButton.innerHTML = `
            <span style="font-size: 1.2em;">⚡</span>
            <span style="flex: 1; text-align: left; margin-left: 10px;">
                <strong>LLM-Optimized (Recommended)</strong><br>
                <small style="color: #666;">Condensed, structured format with action hints</small>
            </span>
            <span style="color: #666; font-size: 0.9em;">→</span>
        `;
        llmOptButton.onclick = () => {
            console.log('✅ LLM-Optimized format selected');
            this.annotationOutputFormat = 'llm_optimized';
            document.getElementById('format-selection')?.remove();
            this.showModelParametersConfig();  // Show parameters before model selection
        };

        // Full JSON format button
        const jsonButton = document.createElement('button');
        jsonButton.className = 'model-button';
        jsonButton.type = 'button';
        jsonButton.innerHTML = `
            <span style="font-size: 1.2em;">📄</span>
            <span style="flex: 1; text-align: left; margin-left: 10px;">
                <strong>Full JSON</strong><br>
                <small style="color: #666;">Complete raw data from all sources</small>
            </span>
            <span style="color: #666; font-size: 0.9em;">→</span>
        `;
        jsonButton.onclick = () => {
            console.log('✅ Full JSON format selected');
            this.annotationOutputFormat = 'json';
            document.getElementById('format-selection')?.remove();
            this.showModelParametersConfig();  // Show parameters before model selection
        };

        formatSelectionDiv.appendChild(llmOptButton);
        formatSelectionDiv.appendChild(jsonButton);
        container.appendChild(formatSelectionDiv);

        requestAnimationFrame(() => {
            container.scrollTop = container.scrollHeight;
        });

        this.updateBackButton();
        console.log('✅ Output format selection displayed');
    },

    // =========================================================================
    // Model Parameters Configuration
    // =========================================================================

    async fetchModelParameters() {
        try {
            const response = await fetch(`${this.API_BASE}/api/chat/model-parameters`);
            if (response.ok) {
                this.modelParameters = await response.json();
                console.log('✅ Loaded model parameters:', Object.keys(this.modelParameters.parameters));
                return this.modelParameters;
            }
        } catch (error) {
            console.error('Failed to fetch model parameters:', error);
        }
        return null;
    },

    async fetchEmailConfig() {
        try {
            const response = await fetch(`${this.API_BASE}/api/chat/email-config`);
            if (response.ok) {
                const config = await response.json();
                this.emailConfigured = config.configured;
                console.log('📧 Email configured:', this.emailConfigured);
                return config;
            }
        } catch (error) {
            console.error('Failed to fetch email config:', error);
        }
        return { configured: false };
    },

    async applyModelPreset(presetName) {
        try {
            const response = await fetch(`${this.API_BASE}/api/chat/model-parameters/preset/${presetName}`, {
                method: 'POST'
            });
            if (response.ok) {
                const result = await response.json();
                this.customModelParams = result.current;
                console.log(`✅ Applied preset: ${presetName}`);
                return result;
            }
        } catch (error) {
            console.error('Failed to apply preset:', error);
        }
        return null;
    },

    async updateModelParameter(paramName, value) {
        try {
            const body = {};
            body[paramName] = value;

            const response = await fetch(`${this.API_BASE}/api/chat/model-parameters`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });

            if (response.ok) {
                const result = await response.json();
                this.customModelParams = result.current;
                console.log(`✅ Updated ${paramName}:`, value);
                return result;
            }
        } catch (error) {
            console.error(`Failed to update ${paramName}:`, error);
        }
        return null;
    },

    async resetModelParameters() {
        try {
            const response = await fetch(`${this.API_BASE}/api/chat/model-parameters/reset`, {
                method: 'POST'
            });
            if (response.ok) {
                const result = await response.json();
                this.customModelParams = result.current;
                console.log('✅ Reset parameters to defaults');
                return result;
            }
        } catch (error) {
            console.error('Failed to reset parameters:', error);
        }
        return null;
    },

    async showModelParametersConfig() {
        console.log('⚙️ Showing model parameters configuration');

        // Fetch parameters and email config in parallel
        const [paramsResult, emailResult] = await Promise.all([
            this.modelParameters ? Promise.resolve(this.modelParameters) : this.fetchModelParameters(),
            this.fetchEmailConfig()
        ]);

        if (!this.modelParameters) {
            console.warn('Could not load model parameters, skipping to model selection');
            this.showModelSelectionStep2();
            return;
        }

        const container = document.getElementById('chat-container');

        this.addMessage('chat-container', 'system',
            '⚙️ **Model Parameters** (Optional)\n\n' +
            'Adjust LLM generation parameters or use a preset.\n' +
            'Hover over each parameter for detailed explanations.');

        const configDiv = document.createElement('div');
        configDiv.className = 'model-params-config';
        configDiv.id = 'model-params-container';
        configDiv.innerHTML = this.buildParameterControlsHTML();

        container.appendChild(configDiv);

        // Attach event listeners
        this.attachParameterEventListeners();

        requestAnimationFrame(() => {
            container.scrollTop = container.scrollHeight;
        });

        this.updateBackButton();
        console.log('✅ Model parameters configuration displayed');
    },

    buildParameterControlsHTML() {
        const params = this.modelParameters.parameters;
        const presets = this.modelParameters.presets;

        let html = `
            <style>
                .model-params-config {
                    background: var(--bg-secondary, #1a1a2e);
                    border-radius: 12px;
                    padding: 20px;
                    margin: 10px 0;
                }
                .params-header {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 15px;
                    flex-wrap: wrap;
                    gap: 10px;
                }
                .params-title {
                    font-size: 1.1em;
                    font-weight: bold;
                    color: var(--primary-color, #1BEB49);
                }
                .preset-buttons {
                    display: flex;
                    gap: 8px;
                    flex-wrap: wrap;
                }
                .preset-btn {
                    padding: 6px 12px;
                    border-radius: 6px;
                    border: 1px solid var(--border-color, #333);
                    background: var(--bg-primary, #0d0d1a);
                    color: var(--text-color, #e0e0e0);
                    cursor: pointer;
                    font-size: 0.85em;
                    transition: all 0.2s;
                }
                .preset-btn:hover {
                    background: var(--primary-color, #1BEB49);
                    color: #000;
                }
                .param-group {
                    margin-bottom: 18px;
                    position: relative;
                }
                .param-label-row {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 6px;
                }
                .param-label {
                    font-weight: 600;
                    color: var(--text-color, #e0e0e0);
                    display: flex;
                    align-items: center;
                    gap: 6px;
                }
                .param-value-display {
                    font-family: monospace;
                    background: var(--bg-primary, #0d0d1a);
                    padding: 2px 8px;
                    border-radius: 4px;
                    min-width: 60px;
                    text-align: center;
                }
                .param-slider {
                    width: 100%;
                    height: 6px;
                    border-radius: 3px;
                    background: var(--bg-primary, #0d0d1a);
                    -webkit-appearance: none;
                    cursor: pointer;
                }
                .param-slider::-webkit-slider-thumb {
                    -webkit-appearance: none;
                    width: 18px;
                    height: 18px;
                    border-radius: 50%;
                    background: var(--primary-color, #1BEB49);
                    cursor: pointer;
                    box-shadow: 0 2px 6px rgba(0,0,0,0.3);
                }
                .param-slider::-moz-range-thumb {
                    width: 18px;
                    height: 18px;
                    border-radius: 50%;
                    background: var(--primary-color, #1BEB49);
                    cursor: pointer;
                    border: none;
                }
                .help-icon {
                    display: inline-flex;
                    align-items: center;
                    justify-content: center;
                    width: 18px;
                    height: 18px;
                    border-radius: 50%;
                    background: var(--secondary-color, #0E1F81);
                    color: white;
                    font-size: 11px;
                    font-weight: bold;
                    cursor: help;
                    position: relative;
                }
                .tooltip {
                    visibility: hidden;
                    opacity: 0;
                    position: absolute;
                    bottom: 100%;
                    left: 0;
                    width: 350px;
                    background: var(--bg-primary, #0d0d1a);
                    border: 1px solid var(--border-color, #333);
                    border-radius: 8px;
                    padding: 12px;
                    z-index: 1000;
                    box-shadow: 0 4px 20px rgba(0,0,0,0.4);
                    transition: opacity 0.2s, visibility 0.2s;
                    margin-bottom: 8px;
                }
                .help-icon:hover .tooltip,
                .param-group:hover .tooltip {
                    visibility: visible;
                    opacity: 1;
                }
                .tooltip-title {
                    font-weight: bold;
                    color: var(--primary-color, #1BEB49);
                    margin-bottom: 8px;
                    font-size: 0.95em;
                }
                .tooltip-desc {
                    color: var(--text-color, #e0e0e0);
                    font-size: 0.85em;
                    line-height: 1.4;
                    margin-bottom: 10px;
                }
                .tooltip-effects {
                    background: rgba(0,0,0,0.3);
                    border-radius: 6px;
                    padding: 8px;
                    margin-bottom: 8px;
                }
                .tooltip-effect {
                    font-size: 0.8em;
                    margin-bottom: 6px;
                    padding-left: 8px;
                    border-left: 2px solid var(--secondary-color, #0E1F81);
                }
                .tooltip-effect-label {
                    font-weight: 600;
                    color: var(--accent-color, #FFA400);
                }
                .tooltip-recommendation {
                    font-size: 0.8em;
                    color: var(--primary-color, #1BEB49);
                    font-style: italic;
                    padding-top: 6px;
                    border-top: 1px solid var(--border-color, #333);
                }
                .params-actions {
                    display: flex;
                    gap: 10px;
                    margin-top: 20px;
                    padding-top: 15px;
                    border-top: 1px solid var(--border-color, #333);
                }
                .params-action-btn {
                    flex: 1;
                    padding: 12px 20px;
                    border-radius: 8px;
                    border: none;
                    cursor: pointer;
                    font-weight: 600;
                    transition: all 0.2s;
                }
                .params-action-btn.primary {
                    background: var(--primary-color, #1BEB49);
                    color: #000;
                }
                .params-action-btn.secondary {
                    background: var(--bg-primary, #0d0d1a);
                    color: var(--text-color, #e0e0e0);
                    border: 1px solid var(--border-color, #333);
                }
                .params-action-btn:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
                }
            </style>

            <div class="params-header">
                <span class="params-title">⚙️ Generation Parameters</span>
                <div class="preset-buttons">
                    ${Object.entries(presets).map(([key, preset]) => `
                        <button class="preset-btn" data-preset="${key}" title="${preset.description}">
                            ${preset.name}
                        </button>
                    `).join('')}
                </div>
            </div>
        `;

        // Build parameter sliders
        for (const [paramName, param] of Object.entries(params)) {
            const currentValue = this.customModelParams[paramName] ?? param.value;
            const isInteger = paramName === 'top_k' || paramName === 'num_ctx' || paramName === 'num_predict';

            html += `
                <div class="param-group" data-param="${paramName}">
                    <div class="tooltip">
                        <div class="tooltip-title">${param.name}</div>
                        <div class="tooltip-desc">${param.description}</div>
                        <div class="tooltip-effects">
                            <div class="tooltip-effect">
                                <span class="tooltip-effect-label">📉 Low values:</span><br>
                                ${param.effect_low}
                            </div>
                            <div class="tooltip-effect">
                                <span class="tooltip-effect-label">📈 High values:</span><br>
                                ${param.effect_high}
                            </div>
                        </div>
                        <div class="tooltip-recommendation">💡 ${param.recommendation}</div>
                    </div>
                    <div class="param-label-row">
                        <span class="param-label">
                            ${param.name}
                            <span class="help-icon">?</span>
                        </span>
                        <span class="param-value-display" id="value-${paramName}">${isInteger ? Math.round(currentValue) : currentValue.toFixed(2)}</span>
                    </div>
                    <input type="range"
                           class="param-slider"
                           id="slider-${paramName}"
                           min="${param.min}"
                           max="${param.max}"
                           step="${param.step}"
                           value="${currentValue}"
                           data-param="${paramName}"
                           data-is-integer="${isInteger}">
                </div>
            `;
        }

        // Email notification option (only show if email is configured)
        if (this.emailConfigured) {
            html += `
                <div class="email-notification-section" style="margin-top: 20px; padding: 15px; background: var(--bg-primary, #0d0d1a); border-radius: 8px; border: 1px solid var(--border-color, #333);">
                    <div style="display: flex; align-items: center; gap: 12px;">
                        <input type="checkbox"
                               id="email-notify-checkbox"
                               style="width: 18px; height: 18px; cursor: pointer; accent-color: var(--primary-color, #1BEB49);"
                               ${this.annotationEmailNotify ? 'checked' : ''}>
                        <label for="email-notify-checkbox" style="cursor: pointer; flex: 1;">
                            <strong>📧 Email me when annotation completes</strong>
                            <br><small style="color: #888;">Get notified even if you navigate away from this page</small>
                        </label>
                    </div>
                    <div id="email-input-container" style="margin-top: 12px; display: ${this.annotationEmailNotify ? 'block' : 'none'};">
                        <input type="email"
                               id="notification-email-input"
                               placeholder="your.email@example.com"
                               value="${this.annotationNotifyEmail}"
                               style="width: 100%; padding: 10px 12px; border-radius: 6px; border: 1px solid var(--border-color, #333); background: var(--bg-secondary, #1a1a2e); color: var(--text-color, #e0e0e0); font-size: 14px;">
                    </div>
                </div>
            `;
        }

        // Action buttons
        html += `
            <div class="params-actions">
                <button class="params-action-btn secondary" id="reset-params-btn">
                    🔄 Reset to Defaults
                </button>
                <button class="params-action-btn primary" id="continue-to-model-btn">
                    Continue to Model Selection →
                </button>
            </div>
        `;

        return html;
    },

    attachParameterEventListeners() {
        // Preset buttons
        document.querySelectorAll('.preset-btn').forEach(btn => {
            btn.addEventListener('click', async () => {
                const presetName = btn.dataset.preset;
                const result = await this.applyModelPreset(presetName);
                if (result) {
                    // Update all sliders to show new values
                    this.updateParameterSliders(result.current);
                }
            });
        });

        // Parameter sliders
        document.querySelectorAll('.param-slider').forEach(slider => {
            slider.addEventListener('input', (e) => {
                const paramName = e.target.dataset.param;
                const isInteger = e.target.dataset.isInteger === 'true';
                let value = parseFloat(e.target.value);
                if (isInteger) value = Math.round(value);

                // Update display immediately
                const display = document.getElementById(`value-${paramName}`);
                if (display) {
                    display.textContent = isInteger ? value : value.toFixed(2);
                }
            });

            slider.addEventListener('change', async (e) => {
                const paramName = e.target.dataset.param;
                const isInteger = e.target.dataset.isInteger === 'true';
                let value = parseFloat(e.target.value);
                if (isInteger) value = Math.round(value);

                // Send update to API
                await this.updateModelParameter(paramName, value);
            });
        });

        // Reset button
        document.getElementById('reset-params-btn')?.addEventListener('click', async () => {
            const result = await this.resetModelParameters();
            if (result) {
                this.updateParameterSliders(result.current);
            }
        });

        // Email notification checkbox
        document.getElementById('email-notify-checkbox')?.addEventListener('change', (e) => {
            this.annotationEmailNotify = e.target.checked;
            const emailInputContainer = document.getElementById('email-input-container');
            if (emailInputContainer) {
                emailInputContainer.style.display = this.annotationEmailNotify ? 'block' : 'none';
            }
            console.log('📧 Email notification:', this.annotationEmailNotify ? 'enabled' : 'disabled');
        });

        // Email input
        document.getElementById('notification-email-input')?.addEventListener('input', (e) => {
            this.annotationNotifyEmail = e.target.value;
        });

        // Continue button
        document.getElementById('continue-to-model-btn')?.addEventListener('click', () => {
            // Validate email if notification is enabled
            if (this.annotationEmailNotify && this.annotationNotifyEmail) {
                const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
                if (!emailRegex.test(this.annotationNotifyEmail)) {
                    alert('Please enter a valid email address for notifications.');
                    return;
                }
            }
            document.getElementById('model-params-container')?.remove();
            this.showModelSelectionStep2();
        });
    },

    updateParameterSliders(params) {
        for (const [paramName, value] of Object.entries(params)) {
            const slider = document.getElementById(`slider-${paramName}`);
            const display = document.getElementById(`value-${paramName}`);

            if (slider) {
                slider.value = value;
            }
            if (display) {
                const isInteger = paramName === 'top_k' || paramName === 'num_ctx' || paramName === 'num_predict';
                display.textContent = isInteger ? Math.round(value) : value.toFixed(2);
            }
        }
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
        
        // Clear CSV file selection
        this.selectedCSVFile = null;
        
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
        console.log('📊 Current mode:', this.currentMode);
        console.log('📊 annotationModeSelected:', this.annotationModeSelected);
        
        // Check if annotation mode is enabled (from stored selection)
        let annotationMode = false;
        if (this.currentMode === 'chat' && this.annotationModeSelected) {
            annotationMode = true;
            console.log('🔬 Annotation mode ENABLED:', annotationMode);
        } else {
            console.log('💬 Regular chat mode (annotationModeSelected=' + this.annotationModeSelected + ')');
        }
        
        const hasSavedChat = this.sessionChats[modelName] && 
                            this.sessionChats[modelName].messages.length > 0;
        
        if (hasSavedChat && !annotationMode) {
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
            // DEBUG: Log exactly what we're sending
            const requestBody = { 
                model: modelName,
                annotation_mode: annotationMode
            };
            console.log('📤 Sending /chat/init request:');
            console.log('   URL:', `${this.API_BASE}/chat/init`);
            console.log('   Body:', JSON.stringify(requestBody));
            console.log('   annotation_mode value:', annotationMode);
            console.log('   annotation_mode type:', typeof annotationMode);
            
            const response = await fetch(`${this.API_BASE}/chat/init`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.apiKey}`
                },
                body: JSON.stringify(requestBody)
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
                console.log('🔬 Annotation mode active:', annotationMode);
                
                // Store annotation mode in session
                this.sessionChats[modelName] = {
                    conversationId: this.currentConversationId,
                    messages: [],
                    annotationMode: annotationMode
                };
                
                this.ensureChatInfoBar();

                document.getElementById(loadingId)?.remove();
                const modelSelection = document.getElementById('model-selection-container');
                if (modelSelection) {
                    modelSelection.remove();
                }
                
                let welcomeMsg = `✅ Connected to ${modelName}`;
                if (annotationMode) {
                    welcomeMsg += '\n\n🔬 Annotation Mode Active\n\n' +
                                '📝 **Option 1: Enter NCT IDs manually**\n' +
                                'Type NCT IDs in the chat box (comma, space, or newline separated).\n' +
                                'Example: NCT12345678, NCT87654321\n\n' +
                                '📄 **Option 2: Upload CSV file**\n' +
                                'Click the "Upload CSV" button below to batch annotate.\n\n' +
                                '💡 Commands:\n' +
                                '• Type "exit" to select a different model\n' +
                                '• Click "Clear Chat" to reset';
                    
                    // Show CSV upload UI after a small delay
                    setTimeout(() => this.showCSVUploadUI(), 100);
                } else {
                    welcomeMsg += '\n\n💡 Commands:\n• Type "exit" to select a different model\n• Type "main menu" to return to home\n• Click "Clear Chat" to reset conversation';
                }
                
                this.addMessage('chat-container', 'system', welcomeMsg);
                
                const input = document.getElementById('chat-input');
                input.disabled = false;
                
                if (annotationMode) {
                    input.placeholder = 'Enter NCT IDs (comma, space, or newline separated)...';
                } else {
                    input.placeholder = 'Type your message...';
                }
                
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
                `Make sure the chat service is running on port 9001.`);
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
            
            // Reset annotation mode selection for fresh start
            this.annotationModeSelected = false;
            
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
        
        // Check if annotation mode is active
        const isAnnotationMode = this.sessionChats[this.currentModel]?.annotationMode || false;
        
        if (isAnnotationMode) {
            // ANNOTATION MODE - Parse NCT IDs and call annotation endpoint
            console.log('🔬 Annotation mode: Processing NCT IDs');
            
            // Extract NCT IDs from message
            const nctPattern = /NCT\d{8}/gi;
            const nctIds = message.match(nctPattern);
            
            if (!nctIds || nctIds.length === 0) {
                this.addMessage('chat-container', 'error',
                    '❌ No valid NCT IDs found\n\n' +
                    'Please enter NCT IDs in the format: NCT12345678\n' +
                    'You can enter multiple IDs separated by commas, spaces, or newlines.\n\n' +
                    'Examples:\n' +
                    '  • NCT03936426, NCT04123456\n' +
                    '  • NCT03936426 NCT04123456\n' +
                    '  • One per line');
                return;
            }
            
            // Normalize NCT IDs to uppercase
            const normalizedNctIds = nctIds.map(id => id.toUpperCase());
            
            console.log(`📝 Extracted ${normalizedNctIds.length} NCT IDs:`, normalizedNctIds);
            
            this.addMessage('chat-container', 'user', `Annotate: ${normalizedNctIds.join(', ')}`);
            
            // Call the annotation function (which uses the runner service)
            await this.annotateTrials(normalizedNctIds);
            
        } else {
            // REGULAR CHAT MODE
            console.log('💬 Regular chat mode: Sending message');
            
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
        }
    },

    // =========================================================================
    // Annotation Mode - Trial Annotation
    // =========================================================================

    async annotateTrials(nctIds) {
        console.log(`🔬 Starting async annotation for ${nctIds.length} trial(s):`, nctIds);
        console.log('📊 Current conversation ID:', this.currentConversationId);
        console.log('📊 Current model:', this.currentModel);

        if (!this.currentConversationId) {
            this.addMessage('chat-container', 'error',
                '❌ No active conversation!\n\n' +
                'Please try:\n' +
                '1. Reload the page\n' +
                '2. Click "Chat with LLM" again\n' +
                '3. Select annotation mode\n' +
                '4. Select a model');
            return;
        }

        // Note: User message already shown by handleAnnotationInput()

        // Show processing message with progress bar
        const processingId = this.addMessage('chat-container', 'system',
            `🔄 Starting annotation for ${nctIds.length} clinical trial(s)...\n\n` +
            `⏳ Submitting job to server...`);

        // Helper to update the processing message
        const updateProcessingMsg = (msg) => {
            const el = document.getElementById(processingId);
            if (el) {
                const contentEl = el.querySelector('.message-content');
                if (contentEl) {
                    contentEl.innerHTML = this.formatMessage(msg);
                }
            }
        };

        // Start a timer to show elapsed time during submission
        const submitStartTime = Date.now();
        const submitTimer = setInterval(() => {
            const elapsed = Math.round((Date.now() - submitStartTime) / 1000);
            updateProcessingMsg(
                `🔄 Starting annotation for ${nctIds.length} clinical trial(s)...\n\n` +
                `⏳ Connecting to annotation service... (${elapsed}s)\n\n` +
                `_Waiting for server response..._`
            );
        }, 1000);

        try {
            console.log('📤 Sending async annotation request');
            console.log('📊 Output format:', this.annotationOutputFormat);

            // Build request body
            const requestBody = {
                conversation_id: this.currentConversationId,
                nct_ids: nctIds,
                output_format: this.annotationOutputFormat,
                temperature: 0.15
            };

            // Add email notification if enabled
            if (this.annotationEmailNotify && this.annotationNotifyEmail) {
                requestBody.notification_email = this.annotationNotifyEmail;
                console.log('📧 Email notification will be sent to:', this.annotationNotifyEmail);
            }

            // Start async job with timeout
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 30000); // 30 second timeout

            const response = await fetch(`${this.API_BASE}/chat/annotate`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.apiKey}`
                },
                body: JSON.stringify(requestBody),
                signal: controller.signal
            });

            clearTimeout(timeoutId);
            clearInterval(submitTimer);

            if (response.ok) {
                const data = await response.json();
                console.log('✅ Job started:', data);

                if (data.job_id) {
                    // Update message to show job started
                    updateProcessingMsg(
                        `🔄 **Annotation Job Started**\n\n` +
                        `Job ID: \`${data.job_id.substring(0, 8)}...\`\n\n` +
                        `⏳ Initializing processing pipeline...`
                    );
                    // Poll for status with progress updates
                    await this.pollAnnotationStatus(data.job_id, processingId, nctIds.join(', '), nctIds.length);
                } else {
                    document.getElementById(processingId)?.remove();
                    this.addMessage('chat-container', 'error', '❌ No job ID returned from server');
                }
            } else {
                clearInterval(submitTimer);
                const errorText = await response.text();
                document.getElementById(processingId)?.remove();
                this.addMessage('chat-container', 'error', `❌ Failed to start annotation job\n\nError: ${errorText}`);
            }

        } catch (error) {
            clearInterval(submitTimer);
            document.getElementById(processingId)?.remove();
            console.error('❌ Annotation error:', error);

            if (error.name === 'AbortError') {
                this.addMessage('chat-container', 'error',
                    `❌ Request Timeout\n\n` +
                    `The server took too long to respond.\n\n` +
                    `This could mean:\n` +
                    `• The annotation service is overloaded\n` +
                    `• Network connectivity issues\n\n` +
                    `Try again or check services: \`./services.sh status\``);
            } else {
                this.addMessage('chat-container', 'error',
                    `❌ Connection Error\n\n` +
                    `${error.message}\n\n` +
                    `Cannot connect to Chat Service.\n\n` +
                    `Check services: ./services.sh status`);
            }
        }
    },

    async pollAnnotationStatus(jobId, processingId, nctIdsStr, totalTrials) {
        console.log(`📊 Polling status for job ${jobId}`);
        const startTime = Date.now();
        const maxPollTime = 30 * 60 * 1000; // 30 minutes max
        const pollInterval = 2000; // 2 seconds
        let consecutiveErrors = 0;
        const maxConsecutiveErrors = 5;

        while (true) {
            try {
                const response = await fetch(`${this.API_BASE}/chat/annotate-csv-status/${jobId}`, {
                    headers: { 'Authorization': `Bearer ${this.apiKey}` }
                });

                if (!response.ok) {
                    throw new Error(`Status check failed: ${response.status}`);
                }

                const status = await response.json();
                console.log('📊 Job status:', status);
                consecutiveErrors = 0; // Reset error count on success

                // Update progress message
                const elapsed = Math.round((Date.now() - startTime) / 1000);
                const percent = status.percent_complete || 0;
                const progressBar = this.buildProgressBar(percent);

                // Build step indicator
                const stepLabels = {
                    'initializing': '⏳ Initializing...',
                    'fetching': '📥 Fetching trial data...',
                    'processing': '⚙️ Processing (parse → prompt → LLM)...',
                    'completed': '✅ Trial complete',
                    'generating_csv': '📄 Generating CSV output...',
                    '': '🔄 Processing...'
                };
                const currentStep = stepLabels[status.current_step] || stepLabels[''];
                const currentNct = status.current_nct ? `\n**Current Trial:** ${status.current_nct}` : '';

                const processingEl = document.getElementById(processingId);
                if (processingEl) {
                    const contentEl = processingEl.querySelector('.message-content');
                    if (contentEl) {
                        contentEl.innerHTML = this.formatMessage(
                            `🔄 **Annotating ${totalTrials} trial(s)**\n\n` +
                            `${progressBar}\n\n` +
                            `**Progress:** ${status.processed_trials || 0} of ${totalTrials} complete (${percent}%)${currentNct}\n` +
                            `**Step:** ${currentStep}\n` +
                            `**Status:** ${status.progress || 'Processing...'}\n` +
                            `**Elapsed:** ${elapsed}s\n\n` +
                            `_You can close this window - the job will continue in the background._`
                        );
                    }
                }

                // Check completion states
                if (status.status === 'completed') {
                    document.getElementById(processingId)?.remove();
                    this.handleAnnotationComplete(status, nctIdsStr, totalTrials);
                    return;
                }

                if (status.status === 'failed') {
                    document.getElementById(processingId)?.remove();
                    this.addMessage('chat-container', 'error',
                        `❌ Annotation Failed\n\nError: ${status.error || 'Unknown error'}`);
                    return;
                }

                // Check timeout
                if (Date.now() - startTime > maxPollTime) {
                    document.getElementById(processingId)?.remove();
                    this.addMessage('chat-container', 'error',
                        `⚠️ Job is taking longer than expected.\n\n` +
                        `Job ID: ${jobId}\n` +
                        `The job is still running in the background.\n` +
                        `${this.annotationEmailNotify ? '📧 You will receive an email when it completes.' : ''}`);
                    return;
                }

                // Wait before next poll
                await new Promise(resolve => setTimeout(resolve, pollInterval));

            } catch (error) {
                console.error('Poll error:', error);
                consecutiveErrors++;

                // Update UI to show connection issue
                const processingEl = document.getElementById(processingId);
                if (processingEl) {
                    const contentEl = processingEl.querySelector('.message-content');
                    const elapsed = Math.round((Date.now() - startTime) / 1000);
                    if (contentEl) {
                        contentEl.innerHTML = this.formatMessage(
                            `🔄 **Annotating ${totalTrials} trial(s)**\n\n` +
                            `⚠️ **Connection issue** - retrying... (attempt ${consecutiveErrors}/${maxConsecutiveErrors})\n\n` +
                            `**Elapsed:** ${elapsed}s\n\n` +
                            `_The job continues in the background even if connection is lost._`
                        );
                    }
                }

                // Give up after too many consecutive errors
                if (consecutiveErrors >= maxConsecutiveErrors) {
                    document.getElementById(processingId)?.remove();
                    this.addMessage('chat-container', 'error',
                        `⚠️ Lost connection to server\n\n` +
                        `Job ID: \`${jobId}\`\n\n` +
                        `The job may still be running in the background.\n` +
                        `${this.annotationEmailNotify ? '📧 You will receive an email when it completes.' : 'Refresh the page to check status.'}`);
                    return;
                }

                await new Promise(resolve => setTimeout(resolve, pollInterval * 2));
            }
        }
    },

    handleAnnotationComplete(status, nctIdsStr, totalTrials) {
        const result = status.result || {};
        const successful = result.successful || 0;
        const failed = result.failed || 0;
        const duration = result.total_time_seconds || 0;

        let resultMessage = `✅ Annotation Complete\n\n` +
            `═══════════════════════════════════════════\n` +
            `📊 Total NCT IDs: ${totalTrials}\n` +
            `✓ Successful: ${successful}\n` +
            `✗ Failed: ${failed}\n` +
            `⏱ Processing Time: ${duration}s\n` +
            `═══════════════════════════════════════════\n\n`;

        // Add annotation text if available
        if (result.annotation_text) {
            resultMessage += result.annotation_text + '\n\n';
        }

        resultMessage += `💡 Next:\n` +
            `  • Enter more NCT IDs to annotate\n` +
            `  • Type "exit" to select a different model\n` +
            `  • Click "Clear Chat" to reset`;

        this.addMessage('chat-container', 'assistant', resultMessage);

        // Add download button
        if (result.download_url) {
            let downloadUrl = result.download_url;
            if (downloadUrl.startsWith('/')) {
                downloadUrl = `${this.API_BASE}${downloadUrl}`;
            }
            this.addDownloadButton(downloadUrl, result.csv_filename || 'annotations.csv');
        }

        // Store in session
        if (!this.sessionChats[this.currentModel]) {
            this.sessionChats[this.currentModel] = {
                conversationId: this.currentConversationId,
                messages: [],
                annotationMode: true
            };
        }

        this.sessionChats[this.currentModel].messages.push({
            role: 'user',
            content: `Annotate: ${nctIdsStr}`
        });

        this.sessionChats[this.currentModel].messages.push({
            role: 'assistant',
            content: resultMessage
        });
    },

    buildProgressBar(percent) {
        const filled = Math.round(percent / 5);
        const empty = 20 - filled;
        return `[${'█'.repeat(filled)}${'░'.repeat(empty)}] ${percent}%`;
    },

    // =========================================================================
    // CSV Upload Functionality
    // =========================================================================

    showCSVUploadUI() {
        // Remove any existing CSV upload UI
        document.getElementById('csv-upload-container')?.remove();
        
        const container = document.getElementById('chat-container');
        
        const csvUploadDiv = document.createElement('div');
        csvUploadDiv.id = 'csv-upload-container';
        csvUploadDiv.className = 'csv-upload-container';
        csvUploadDiv.innerHTML = `
            <div class="csv-upload-icon">📄</div>
            <div class="csv-upload-text">Upload CSV for Batch Annotation</div>
            <div class="csv-upload-subtext">CSV can have NCT IDs in any column - they will be auto-detected</div>
            
            <input type="file" id="csv-file-input" class="csv-file-input" accept=".csv,.txt">
            
            <button type="button" class="csv-upload-btn" onclick="app.triggerCSVFileSelect()">
                <span class="csv-upload-btn-icon">📤</span>
                <span>Choose CSV File</span>
            </button>
            
            <div id="csv-file-selected" class="csv-file-selected" style="display: none;">
                <span id="csv-file-name" class="csv-file-name"></span>
                <span id="csv-file-size" class="csv-file-size"></span>
                <button type="button" class="csv-file-remove" onclick="app.clearCSVFile()">✕</button>
            </div>
            
            <div style="margin-top: 15px;">
                <button type="button" id="csv-submit-btn" class="submit-csv-btn" onclick="app.uploadCSVForAnnotation()" style="display: none;">
                    <span>🔬</span>
                    <span>Start Batch Annotation</span>
                </button>
            </div>
        `;
        
        container.appendChild(csvUploadDiv);
        
        // Set up file input change handler
        const fileInput = document.getElementById('csv-file-input');
        fileInput.addEventListener('change', (e) => this.handleCSVFileSelect(e));
        
        // Set up drag and drop
        csvUploadDiv.addEventListener('dragover', (e) => {
            e.preventDefault();
            csvUploadDiv.classList.add('drag-over');
        });
        
        csvUploadDiv.addEventListener('dragleave', (e) => {
            e.preventDefault();
            csvUploadDiv.classList.remove('drag-over');
        });
        
        csvUploadDiv.addEventListener('drop', (e) => {
            e.preventDefault();
            csvUploadDiv.classList.remove('drag-over');
            
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                const file = files[0];
                if (file.name.endsWith('.csv') || file.name.endsWith('.txt')) {
                    this.selectedCSVFile = file;
                    this.showSelectedCSVFile(file);
                } else {
                    this.addMessage('chat-container', 'error', '❌ Please upload a CSV or TXT file');
                }
            }
        });
        
        // Scroll to show the upload UI
        requestAnimationFrame(() => {
            container.scrollTop = container.scrollHeight;
        });
    },
    
    triggerCSVFileSelect() {
        document.getElementById('csv-file-input')?.click();
    },
    
    handleCSVFileSelect(event) {
        const file = event.target.files[0];
        if (file) {
            this.selectedCSVFile = file;
            this.showSelectedCSVFile(file);
        }
    },
    
    showSelectedCSVFile(file) {
        const selectedDiv = document.getElementById('csv-file-selected');
        const nameSpan = document.getElementById('csv-file-name');
        const sizeSpan = document.getElementById('csv-file-size');
        const submitBtn = document.getElementById('csv-submit-btn');
        
        if (selectedDiv && nameSpan && sizeSpan) {
            nameSpan.textContent = file.name;
            sizeSpan.textContent = `(${(file.size / 1024).toFixed(1)} KB)`;
            selectedDiv.style.display = 'flex';
            submitBtn.style.display = 'inline-flex';
        }
    },
    
    clearCSVFile() {
        this.selectedCSVFile = null;
        
        const fileInput = document.getElementById('csv-file-input');
        if (fileInput) fileInput.value = '';
        
        const selectedDiv = document.getElementById('csv-file-selected');
        if (selectedDiv) selectedDiv.style.display = 'none';
        
        const submitBtn = document.getElementById('csv-submit-btn');
        if (submitBtn) submitBtn.style.display = 'none';
    },
    
    async uploadCSVForAnnotation() {
        if (!this.selectedCSVFile) {
            this.addMessage('chat-container', 'error', '❌ No CSV file selected');
            return;
        }
        
        if (!this.currentConversationId) {
            this.addMessage('chat-container', 'error', '❌ No active conversation. Please select a model first.');
            return;
        }
        
        const file = this.selectedCSVFile;
        const fileName = file.name;
        
        console.log(`📤 Uploading CSV for annotation: ${fileName}`);
        
        // Hide upload UI and show processing message
        document.getElementById('csv-upload-container').style.display = 'none';
        
        this.addMessage('chat-container', 'user', `📄 Upload CSV: ${fileName}`);
        
        const processingId = this.addMessage('chat-container', 'system', 
            `🔄 Starting CSV annotation: ${fileName}\n\n` +
            `⏳ Submitting job...`);
        
        try {
            const formData = new FormData();
            formData.append('file', file);
            
            const params = new URLSearchParams({
                conversation_id: this.currentConversationId,
                model: this.currentModel,
                temperature: '0.15'
            });

            // Add email notification if enabled
            if (this.annotationEmailNotify && this.annotationNotifyEmail) {
                params.set('notification_email', this.annotationNotifyEmail);
                console.log('📧 Email notification will be sent to:', this.annotationNotifyEmail);
            }

            const url = `${this.API_BASE}/chat/annotate-csv?${params}`;
            console.log(`📤 Sending CSV to: ${url}`);
            
            const response = await fetch(url, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${this.apiKey}` },
                body: formData
            });
            
            if (response.ok) {
                const data = await response.json();
                console.log('✅ Job response:', data);
                
                if (data.job_id) {
                    // Async mode - poll for status with progress bar
                    await this.pollCSVAnnotationStatus(data.job_id, processingId, fileName, data.total || 0);
                } else {
                    // Sync response (fallback)
                    document.getElementById(processingId)?.remove();
                    this.handleCSVAnnotationResult(data, fileName);
                }
            } else {
                const errorText = await response.text();
                document.getElementById(processingId)?.remove();
                this.addMessage('chat-container', 'error', `❌ CSV Annotation Failed\n\nError: ${errorText}`);
                document.getElementById('csv-upload-container').style.display = 'block';
            }
        } catch (error) {
            document.getElementById(processingId)?.remove();
            this.addMessage('chat-container', 'error', `❌ Connection Error\n\n${error.message}`);
            document.getElementById('csv-upload-container').style.display = 'block';
        }
    },
    
    updateProcessingMessage(messageId, newContent) {
        const msgElement = document.getElementById(messageId);
        if (msgElement) {
            const contentDiv = msgElement.querySelector('.message-content');
            if (contentDiv) contentDiv.textContent = newContent;
        }
    },
    
    async pollCSVAnnotationStatus(jobId, processingId, fileName, totalTrials = 0) {
        const pollInterval = 3000;
        const maxPolls = 600;
        let pollCount = 0;
        const startTime = Date.now();
        
        // Create progress bar UI
        this.createProgressBar(processingId, fileName, totalTrials);
        
        const poll = async () => {
            try {
                const response = await fetch(`${this.API_BASE}/chat/annotate-csv-status/${jobId}`, {
                    headers: { 'Authorization': `Bearer ${this.apiKey}` }
                });
                
                if (!response.ok) throw new Error(`Status check failed: ${response.status}`);
                
                const status = await response.json();
                console.log(`📊 Job status:`, status);
                
                // Update progress bar
                const elapsed = Math.round((Date.now() - startTime) / 1000);
                this.updateProgressBar(processingId, status, elapsed);
                
                if (status.status === 'completed') {
                    this.completeProgressBar(processingId);
                    setTimeout(() => {
                        document.getElementById(processingId)?.remove();
                        this.handleCSVAnnotationResult(status.result, fileName);
                    }, 1000);
                } else if (status.status === 'failed') {
                    this.failProgressBar(processingId, status.error);
                    setTimeout(() => {
                        document.getElementById(processingId)?.remove();
                        this.addMessage('chat-container', 'error', `❌ Annotation Failed\n\n${status.error || 'Unknown error'}`);
                        document.getElementById('csv-upload-container').style.display = 'block';
                    }, 2000);
                } else {
                    pollCount++;
                    if (pollCount < maxPolls) setTimeout(poll, pollInterval);
                }
            } catch (error) {
                console.warn(`Poll error (attempt ${pollCount}):`, error);
                pollCount++;
                if (pollCount < maxPolls) setTimeout(poll, pollInterval);
            }
        };
        
        setTimeout(poll, pollInterval);
    },

    createProgressBar(containerId, fileName, totalTrials) {
        const container = document.getElementById(containerId);
        if (!container) return;
        
        const contentDiv = container.querySelector('.content');
        if (!contentDiv) return;
        
        contentDiv.innerHTML = `
            <div class="csv-progress-container" id="progress-${containerId}">
                <div class="csv-progress-header">
                    <div class="csv-progress-title">
                        <span class="spinner"></span>
                        Processing: ${this.escapeHtml(fileName)}
                    </div>
                    <div class="csv-progress-stats">
                        <span class="current" id="progress-current-${containerId}">0</span>
                        <span>/</span>
                        <span class="total" id="progress-total-${containerId}">${totalTrials || '?'}</span>
                        <span>trials</span>
                    </div>
                </div>
                <div class="csv-progress-bar-container">
                    <div class="csv-progress-bar" id="progress-bar-${containerId}" style="width: 0%">
                        <span class="csv-progress-percent" id="progress-percent-${containerId}">0%</span>
                    </div>
                </div>
                <div class="csv-progress-info">
                    <div class="csv-progress-status">
                        <span class="status-icon">🔄</span>
                        <span id="progress-status-${containerId}">Initializing...</span>
                    </div>
                    <div class="csv-progress-elapsed">
                        <span id="progress-elapsed-${containerId}">0:00</span>
                    </div>
                </div>
            </div>
        `;
    },

    updateProgressBar(containerId, status, elapsedSeconds) {
        const processed = status.processed_trials || 0;
        const total = status.total_trials || 0;
        const progress = status.progress || 'Processing...';
        
        const totalEl = document.getElementById(`progress-total-${containerId}`);
        if (totalEl && total > 0) totalEl.textContent = total;
        
        const currentEl = document.getElementById(`progress-current-${containerId}`);
        if (currentEl) currentEl.textContent = processed;
        
        const percent = total > 0 ? Math.round((processed / total) * 100) : 0;
        
        const barEl = document.getElementById(`progress-bar-${containerId}`);
        if (barEl) barEl.style.width = `${percent}%`;
        
        const percentEl = document.getElementById(`progress-percent-${containerId}`);
        if (percentEl) percentEl.textContent = `${percent}%`;
        
        const statusEl = document.getElementById(`progress-status-${containerId}`);
        if (statusEl) statusEl.textContent = progress;
        
        const elapsedEl = document.getElementById(`progress-elapsed-${containerId}`);
        if (elapsedEl) {
            const mins = Math.floor(elapsedSeconds / 60);
            const secs = elapsedSeconds % 60;
            elapsedEl.textContent = `${mins}:${secs.toString().padStart(2, '0')}`;
        }
    },

    completeProgressBar(containerId) {
        const progressContainer = document.getElementById(`progress-${containerId}`);
        if (progressContainer) progressContainer.classList.add('completed');
        
        const barEl = document.getElementById(`progress-bar-${containerId}`);
        if (barEl) barEl.style.width = '100%';
        
        const percentEl = document.getElementById(`progress-percent-${containerId}`);
        if (percentEl) percentEl.textContent = '100%';
        
        const statusEl = document.getElementById(`progress-status-${containerId}`);
        if (statusEl) statusEl.textContent = 'Complete!';
    },

    failProgressBar(containerId, errorMessage) {
        const progressContainer = document.getElementById(`progress-${containerId}`);
        if (progressContainer) progressContainer.classList.add('failed');
        
        const statusEl = document.getElementById(`progress-status-${containerId}`);
        if (statusEl) statusEl.textContent = errorMessage || 'Failed';
    },
        
    handleCSVAnnotationResult(data, fileName) {
        let errorSummary = '';
        if (data.errors && data.errors.length > 0) {
            errorSummary = '\n\n⚠️ Errors:\n';
            data.errors.slice(0, 5).forEach(err => {
                errorSummary += `  • ${err.nct_id}: ${err.error}\n`;
            });
        }
        
        let downloadUrl = data.download_url;
        if (downloadUrl && downloadUrl.startsWith('/')) {
            downloadUrl = `${this.API_BASE}${downloadUrl}`;
        }
        
        const resultMessage = `✅ CSV Annotation Complete\n\n` +
            `═══════════════════════════════════════════\n` +
            `📄 Input File: ${fileName}\n` +
            `📊 Total NCT IDs: ${data.total}\n` +
            `✓ Successful: ${data.successful}\n` +
            `✗ Failed: ${data.failed}\n` +
            `⏱ Processing Time: ${data.total_time_seconds}s\n` +
            `═══════════════════════════════════════════${errorSummary}\n\n` +
            `💡 Click the download button below to get your CSV`;
        
        this.addMessage('chat-container', 'assistant', resultMessage);
        
        if (downloadUrl) {
            this.addDownloadButton(downloadUrl, data.csv_filename || 'annotations.csv');
        }
        
        setTimeout(() => {
            this.clearCSVFile();
            document.getElementById('csv-upload-container').style.display = 'block';
        }, 500);
    },
    
    addDownloadButton(url, filename) {
        const container = document.getElementById('chat-container');
        
        const downloadDiv = document.createElement('div');
        downloadDiv.className = 'csv-download-section success-pulse';
        downloadDiv.innerHTML = `
            <div class="csv-download-icon">✅</div>
            <div class="csv-download-title">Annotated CSV Ready!</div>
            <div class="csv-download-info">${filename}</div>
            <a href="${url}" download="${filename}" class="csv-download-btn" target="_blank">
                <span class="csv-download-btn-icon">📥</span>
                <span>Download CSV</span>
            </a>
        `;
        
        container.appendChild(downloadDiv);
        
        requestAnimationFrame(() => {
            container.scrollTop = container.scrollHeight;
        });
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
                const isCSV = file.type === 'csv' || file.name.endsWith('.csv');
                const isAnnotation = file.source === 'annotations';
                const icon = isCSV ? '📊' : '📄';
                const typeLabel = isAnnotation ? '<span class="file-type-badge annotation">Annotation</span>' : '';

                html += `
                    <div class="file-card ${isAnnotation ? 'annotation-file' : ''}">
                        <div class="file-card-icon">${icon}</div>
                        <div class="file-card-name">${this.escapeHtml(file.name)}${typeLabel}</div>
                        <div class="file-card-meta">Size: ${file.size}</div>
                        <div class="file-card-meta">Modified: ${file.modified}</div>
                        <div class="file-card-actions">
                            ${isCSV ? `
                                <button class="file-card-btn download" onclick="app.downloadFile('${this.escapeHtml(file.name)}', '${file.source || 'output'}')">
                                    📥 Download
                                </button>
                                <button class="file-card-btn view" onclick="app.viewCSVFile('${this.escapeHtml(file.name)}', '${file.source || 'output'}')">
                                    👁 View
                                </button>
                            ` : `
                                <button class="file-card-btn load" onclick="app.loadFileIntoChat('${this.escapeHtml(file.name)}')">
                                    📂 Load into Chat
                                </button>
                            `}
                            <button class="file-card-btn delete" onclick="app.deleteFile('${this.escapeHtml(file.name)}', '${file.source || 'output'}')">
                                🗑️ Delete
                            </button>
                        </div>
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

    downloadFile(filename, source = 'output') {
        const url = `${this.API_BASE}/files/download/${encodeURIComponent(filename)}?source=${source}`;
        window.open(url, '_blank');
    },

    async deleteFile(filename, source = 'output') {
        if (!confirm(`Delete "${filename}"?\n\nThis action cannot be undone.`)) {
            return;
        }

        try {
            const response = await fetch(
                `${this.API_BASE}/files/delete/${encodeURIComponent(filename)}?source=${source}`,
                {
                    method: 'DELETE',
                    headers: { 'Authorization': `Bearer ${this.apiKey}` }
                }
            );

            if (response.ok) {
                console.log(`✅ Deleted file: ${filename}`);
                // Reload the file list
                await this.loadFiles();
            } else {
                const error = await response.text();
                alert(`Failed to delete file: ${error}`);
            }
        } catch (error) {
            console.error('Failed to delete file:', error);
            alert(`Error deleting file: ${error.message}`);
        }
    },

    async viewCSVFile(filename, source = 'output') {
        try {
            const response = await fetch(
                `${this.API_BASE}/files/content/${encodeURIComponent(filename)}?source=${source}`,
                { headers: { 'Authorization': `Bearer ${this.apiKey}` } }
            );

            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const data = await response.json();

            // Show in a modal or new view
            this.showCSVViewer(filename, data.content);

        } catch (error) {
            alert('Error viewing file: ' + error.message);
        }
    },

    showCSVViewer(filename, content) {
        // Parse CSV and show in a table
        const lines = content.split('\n');
        const isMetadataLine = (line) => line.startsWith('#');

        // Separate metadata and data
        const metadata = [];
        const dataLines = [];

        for (const line of lines) {
            if (isMetadataLine(line)) {
                metadata.push(line.substring(1).trim()); // Remove # prefix
            } else if (line.trim()) {
                dataLines.push(line);
            }
        }

        // Parse CSV data (simple parser)
        const parseCSVLine = (line) => {
            const result = [];
            let current = '';
            let inQuotes = false;
            for (let i = 0; i < line.length; i++) {
                const char = line[i];
                if (char === '"') {
                    inQuotes = !inQuotes;
                } else if (char === ',' && !inQuotes) {
                    result.push(current.trim());
                    current = '';
                } else {
                    current += char;
                }
            }
            result.push(current.trim());
            return result;
        };

        const headers = dataLines.length > 0 ? parseCSVLine(dataLines[0]) : [];
        const rows = dataLines.slice(1).map(parseCSVLine);

        // Create modal content
        let html = `
            <div class="csv-viewer-modal">
                <div class="csv-viewer-header">
                    <h3>📊 ${this.escapeHtml(filename)}</h3>
                    <button onclick="this.closest('.csv-viewer-modal').remove()">×</button>
                </div>
                ${metadata.length > 0 ? `
                    <div class="csv-metadata">
                        <details>
                            <summary>📋 Metadata (${metadata.length} lines)</summary>
                            <pre>${metadata.join('\n')}</pre>
                        </details>
                    </div>
                ` : ''}
                <div class="csv-table-container">
                    <table class="csv-table">
                        <thead>
                            <tr>${headers.map(h => `<th>${this.escapeHtml(h)}</th>`).join('')}</tr>
                        </thead>
                        <tbody>
                            ${rows.slice(0, 100).map(row => `
                                <tr>${row.map(cell => `<td>${this.escapeHtml(cell.substring(0, 200))}${cell.length > 200 ? '...' : ''}</td>`).join('')}</tr>
                            `).join('')}
                        </tbody>
                    </table>
                    ${rows.length > 100 ? `<p class="csv-truncated">Showing first 100 of ${rows.length} rows</p>` : ''}
                </div>
            </div>
        `;

        // Add modal to page
        const modal = document.createElement('div');
        modal.className = 'csv-viewer-overlay';
        modal.innerHTML = html;
        modal.onclick = (e) => { if (e.target === modal) modal.remove(); };
        document.body.appendChild(modal);
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

    async handleResearchInput(input) {
        input = input.trim();
        
        if (!input) return;
        
        // Command handling
        if (input.toLowerCase() === 'exit') {
            this.showMenu();
            return;
        }
        
        if (input.toLowerCase() === 'models') {
            await this.selectModel('research');
            return;
        }
        
        if (!this.currentModel) {
            this.addMessage('research-container', 'error', 
                '⚠️  Please select a model first\n\n' +
                'Type "models" to see available models');
            return;
        }
        
        // Parse NCT IDs (comma-separated)
        const nctIds = input.split(',')
            .map(id => id.trim().toUpperCase())
            .filter(id => id.startsWith('NCT'));
        
        if (nctIds.length === 0) {
            this.addMessage('research-container', 'error', 
                '⚠️  Invalid NCT ID format\n\n' +
                'Enter one or more NCT IDs:\n' +
                '  Single: NCT12345678\n' +
                '  Multiple: NCT12345678, NCT87654321, NCT11111111\n\n' +
                'Commands:\n' +
                '  models - Change model\n' +
                '  exit - Return to menu');
            return;
        }
        
        // Initialize annotation conversation if needed
        if (!this.currentConversationId) {
            try {
                const response = await fetch(`${this.API_BASE}/chat/init`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        model: this.currentModel,
                        annotation_mode: true
                    })
                });
                
                if (response.ok) {
                    const data = await response.json();
                    this.currentConversationId = data.conversation_id;
                    console.log('✅ Annotation conversation initialized:', this.currentConversationId);
                } else {
                    throw new Error('Failed to initialize annotation conversation');
                }
            } catch (error) {
                this.addMessage('research-container', 'error', 
                    `❌ Failed to initialize\n\n${error.message}\n\n` +
                    `Ensure Chat Service (port 9001) is running.`);
                return;
            }
        }
        
        // Show processing message
        const processingId = this.addMessage('research-container', 'system', 
            `🔬 Annotating ${nctIds.length} trial${nctIds.length > 1 ? 's' : ''}...\n\n` +
            `NCT IDs: ${nctIds.join(', ')}\n\n` +
            `Steps:\n` +
            `1. Runner checks for existing JSON files\n` +
            `2. Auto-fetches missing data (if needed)\n` +
            `3. Generates annotations with LLM\n\n` +
            `⏳ This may take 1-3 minutes...`);
        
        const startTime = Date.now();
        
        try {
            const response = await fetch(`${this.API_BASE}/chat/message`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    conversation_id: this.currentConversationId,
                    message: "Annotate trials",
                    nct_ids: nctIds,
                    temperature: 0.15
                })
            });
            
            const endTime = Date.now();
            const duration = ((endTime - startTime) / 1000).toFixed(1);
            
            // Remove processing message
            const processingElement = document.getElementById(processingId);
            if (processingElement) {
                processingElement.remove();
            }
            
            if (response.ok) {
                const data = await response.json();
                
                // Display annotation results
                this.addMessage('research-container', 'assistant', 
                    `✅ Annotation Complete\n\n` +
                    `═══════════════════════════════════════════\n` +
                    `Trials Annotated: ${nctIds.length}\n` +
                    `Model: ${data.model}\n` +
                    `Processing Time: ${duration}s\n` +
                    `═══════════════════════════════════════════\n\n` +
                    `${data.message.content}\n\n` +
                    `═══════════════════════════════════════════\n\n` +
                    `💡 Next:\n` +
                    `  • Enter more NCT IDs to annotate\n` +
                    `  • Type "models" to change model\n` +
                    `  • Type "exit" to return to menu`);
                
                // Store in session
                if (!this.sessionChats[this.currentModel]) {
                    this.sessionChats[this.currentModel] = {
                        conversationId: this.currentConversationId,
                        messages: [],
                        annotationMode: true
                    };
                }
                
                this.sessionChats[this.currentModel].messages.push({
                    role: 'user',
                    content: `Annotate: ${nctIds.join(', ')}`
                });
                
                this.sessionChats[this.currentModel].messages.push({
                    role: 'assistant',
                    content: data.message.content
                });
                
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
                    `Possible Issues:\n` +
                    `• Invalid NCT ID(s)\n` +
                    `• Runner Service (port 9003) not running\n` +
                    `• NCT Lookup (port 9002) not available\n` +
                    `• Chat Service (port 9001) error\n` +
                    `• Model ${this.currentModel} not responding\n\n` +
                    `Troubleshooting:\n` +
                    `1. Verify NCT IDs are correct\n` +
                    `2. Check services: ./services.sh status\n` +
                    `3. View logs: ./services.sh logs all\n` +
                    `4. Try: ./start_all_services.sh`);
            }
            
        } catch (error) {
            // Remove processing message if still there
            const processingElement = document.getElementById(processingId);
            if (processingElement) {
                processingElement.remove();
            }
            
            this.addMessage('research-container', 'error', 
                `❌ Connection Error\n\n` +
                `${error.message}\n\n` +
                `Cannot connect to Chat Service (port 9001).\n\n` +
                `Required Services:\n` +
                `• Chat Service (9001) - Main annotation service\n` +
                `• Runner Service (9003) - File manager\n` +
                `• NCT Service (9002) - Data fetching\n\n` +
                `Start all services:\n` +
                `  cd ~/amp_llm_v3\n` +
                `  ./start_all_services.sh\n\n` +
                `Check status:\n` +
                `  ./services.sh status`);
            
            console.error('❌ Annotation error:', error);
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