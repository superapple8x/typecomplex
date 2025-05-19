// Libraries Quill and tippy are loaded globally via <script> tags in index.html
// We might still need to import Tippy's CSS if not using a CDN or pre-built bundle with CSS.
// Let's assume for now the CSS is handled or we'll add a separate <link> tag if needed.

// --- Utility: Debounce ---
function debounce(func, wait) {
    let timeout;
    const debounced = function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
    // Add a cancel method
    debounced.cancel = () => {
        clearTimeout(timeout);
    };
    return debounced; // Return the function with the cancel method attached
}

document.addEventListener('DOMContentLoaded', () => {
    // --- Global variables to store rate limits ---
    let currentRateLimitInfo = { 
        total_limits: {fast: 10, better: 5, best: 2, llm_synonym: 5, llm_rewrite: 5 }, // Add new defaults
        remaining_counts: {fast: 0, better: 0, best: 0, llm_synonym: 0, llm_rewrite: 0 } // Add new defaults
    }; 

    // --- Function to fetch and apply rate limits ---
    async function fetchAndApplyRateLimits() {
        try {
            const response = await fetch('/api/get_rate_limits');
            if (!response.ok) {
                console.error('Failed to fetch rate limits:', response.status);
                // Fallback to defaults on error
                currentRateLimitInfo = { 
                    total_limits: {fast: 10, better: 5, best: 2, llm_synonym: 5, llm_rewrite: 5},
                    remaining_counts: {fast: 0, better: 0, best: 0, llm_synonym: 0, llm_rewrite: 0}
                };
                // Still try to update UI with these potentially zeroed-out fallbacks
                updateAnalysisModeOptionText();
                updatePdfAnalysisModeOptionText();
                updateSynonymTooltipRateLimitDisplay(); // Call new function
                updateRewriteButtonRateLimitDisplay(); // Call new function
                return;
            }
            currentRateLimitInfo = await response.json();
            console.log('Fetched rate limit info:', currentRateLimitInfo);
            updateAnalysisModeOptionText();
            updatePdfAnalysisModeOptionText();
            updateSynonymTooltipRateLimitDisplay(); // Call new function
            updateRewriteButtonRateLimitDisplay(); // Call new function
        } catch (error) {
            console.error('Error fetching rate limits:', error);
            currentRateLimitInfo = { 
                total_limits: {fast: 10, better: 5, best: 2, llm_synonym: 5, llm_rewrite: 5},
                remaining_counts: {fast: 0, better: 0, best: 0, llm_synonym: 0, llm_rewrite: 0}
            };
            // Attempt to update UI even with fallbacks
            updateAnalysisModeOptionText();
            updatePdfAnalysisModeOptionText();
            updateSynonymTooltipRateLimitDisplay(); 
            updateRewriteButtonRateLimitDisplay(); 
        }
    }

    // --- Function to update text for main analysis mode options ---
    function updateAnalysisModeOptionText() {
        const analysisModeOptionElements = document.querySelectorAll('#analysis-options-menu .analysis-mode-option');
        analysisModeOptionElements.forEach(option => {
            const mode = option.dataset.mode;
            if (mode && currentRateLimitInfo.total_limits[mode] !== undefined && currentRateLimitInfo.remaining_counts[mode] !== undefined) {
                const total = currentRateLimitInfo.total_limits[mode];
                const remaining = currentRateLimitInfo.remaining_counts[mode];
                const originalText = option.textContent.replace(/\s*\(.*\)/, '').replace(/Remaining:/gi, '').trim();
                option.textContent = `${originalText} (${remaining}/${total} remaining)`;
                
                option.classList.remove('text-red-500', 'font-semibold'); // Clear previous styling
                if (remaining <= 0) {
                    option.classList.add('text-red-500', 'font-semibold');
                }
            }
        });
    }

    // --- Function to update text for PDF analysis mode options ---
    function updatePdfAnalysisModeOptionText() {
        const pdfModeOptionElements = document.querySelectorAll('#pdf-analysis-mode-options a');
        pdfModeOptionElements.forEach(optionLink => {
            const mode = optionLink.dataset.value;
            if (mode && currentRateLimitInfo.total_limits[mode] !== undefined && currentRateLimitInfo.remaining_counts[mode] !== undefined) {
                const total = currentRateLimitInfo.total_limits[mode];
                const remaining = currentRateLimitInfo.remaining_counts[mode];
                let modeText = optionLink.textContent.trim();
                modeText = modeText.replace(/\s*\(\d+\/\d+\s*remaining\)/i, '').replace(/\s*\(\d+\/day\)/i, '').trim(); // Clear old formats
                
                optionLink.textContent = `${modeText} (${remaining}/${total} remaining)`;
                
                optionLink.classList.remove('text-red-500', 'font-semibold'); // Clear previous styling
                if (remaining <= 0) {
                    optionLink.classList.add('text-red-500', 'font-semibold');
                }
            }
        });
    }

    // --- NEW: Function to update Synonym Tooltip with rate limit info ---
    function updateSynonymTooltipRateLimitDisplay() {
        // This is tricky because the synonym tooltip content is built dynamically.
        // We will add a placeholder in the synonym tooltip's HTML structure 
        // if contextual suggestions are enabled and then update it here.
        // For now, let's log it. We might need to adjust showSynonymTooltip.
        if (currentRateLimitInfo.total_limits.llm_synonym !== undefined) {
            const total = currentRateLimitInfo.total_limits.llm_synonym;
            const remaining = currentRateLimitInfo.remaining_counts.llm_synonym;
            console.log(`Synonym LLM Limit: ${remaining}/${total} remaining`);
            // Later: document.getElementById('synonym-llm-limit-display').textContent = `(${remaining}/${total} remaining)`;
        }
    }

    // --- NEW: Function to update Rewrite Button/UI with rate limit info ---
    function updateRewriteButtonRateLimitDisplay() {
        // Assuming there's a button or info area for rewrite suggestions.
        // Let's assume an element with id 'rewrite-suggestion-trigger' or similar.
        const rewriteTriggerElement = document.getElementById('context-menu-rewrite-btn'); // Example ID from context menu
        if (rewriteTriggerElement && currentRateLimitInfo.total_limits.llm_rewrite !== undefined) {
            const total = currentRateLimitInfo.total_limits.llm_rewrite;
            const remaining = currentRateLimitInfo.remaining_counts.llm_rewrite;
            
            let textContent = rewriteTriggerElement.textContent.replace(/\s*\(.*\)/, '').trim();
            textContent += ` (${remaining}/${total} remaining)`;
            rewriteTriggerElement.textContent = textContent;

            rewriteTriggerElement.classList.remove('text-red-500', 'font-semibold');
            if (remaining <= 0) {
                rewriteTriggerElement.classList.add('text-red-500', 'font-semibold');
                // Optionally disable the button if exhausted: rewriteTriggerElement.disabled = true;
            }
        }
    }

    // Call fetchAndApplyRateLimits when DOM is loaded
    fetchAndApplyRateLimits();

    // --- DOM References ---
    const editorContainer = document.getElementById('editor-container');
    const wordCountEl = document.getElementById('word-count');
    const sentenceCountEl = document.getElementById('sentence-count');
    const characterCountEl = document.getElementById('character-count');
    const sidebar = document.getElementById('complexity-sidebar');
    const toggleSidebarBtn = document.getElementById('toggle-sidebar-btn');
    const openSidebarBtn = document.getElementById('open-sidebar-btn');
    const complexityLevelDivs = document.querySelectorAll('#overall-complexity-meter .complexity-level');
    const complexityDescriptionEl = document.getElementById('complexity-description'); // Might be removed if not used
    const complexityPercentageEl = document.getElementById('complexity-percentage');
    const complexityLoadingEl = document.getElementById('complexity-loading');
    const analysisTimeEl = document.getElementById('analysis-time');
    const sensitivitySlider = document.getElementById('complexity-sensitivity-slider');
    const sensitivityLabel = document.getElementById('sensitivity-value-label');
    // Readability score elements
    const fleschKincaidScoreEl = document.getElementById('flesch-kincaid-score');
    const gunningFogScoreEl = document.getElementById('gunning-fog-score');
    const smogIndexScoreEl = document.getElementById('smog-index-score');
    // Visual Map container
    const documentMapContainer = document.getElementById('document-map'); // Inner container for bars
    const documentMapOuterContainer = document.getElementById('document-map-container'); // Outer container for scrolling
    // --- Target Audience / Display Options ---
    // const targetAudienceSelect = document.getElementById('target-audience-select'); // OLD SELECT ELEMENT
    const targetAudienceButton = document.getElementById('target-audience-button'); // NEW Custom Dropdown Button
    const targetAudienceSelected = document.getElementById('target-audience-selected'); // NEW Display for selected value
    const targetAudienceOptions = document.getElementById('target-audience-options'); // NEW Options container
    const toggleHighlighting = document.getElementById('toggle-highlighting');
    const toggleGoalIndicators = document.getElementById('toggle-goal-indicators');
    const fleschKincaidTargetEl = document.getElementById('flesch-kincaid-target');
    const gunningFogTargetEl = document.getElementById('gunning-fog-target');
    // --- NEW Gemini/Context Awareness Elements ---
    const contextAwarenessToggle = document.getElementById('context-awareness-toggle');
    const analysisLoadingIndicator = document.getElementById('analysis-loading-indicator'); // <<< KEPT FOR NOW, BUT WILL BE REMOVED LATER
    const analysisPhaseIndicator = document.getElementById('analysis-phase-indicator'); // <<< NEW Phase Indicator
    const goalContainer = document.getElementById('target-audience-goal-container'); // Keep container for toggle visibility
    // const goalInput = document.getElementById('target-audience-goal'); // REMOVED
    const contextAwarenessInfo = document.getElementById('context-awareness-info'); // Info icon
    // --- NEW: Analysis Control Elements (Updated) ---
    const analysisControlsContainer = document.getElementById('analysis-controls-container'); // NEW: Container div
    const analysisControlBtn = document.getElementById('analysis-control-btn'); // NEW: Main play/pause button
    const analysisExpandBtn = document.getElementById('analysis-expand-btn'); // NEW: Expand button (chevron)
    const analysisOptionsMenu = document.getElementById('analysis-options-menu'); // NEW: Dropdown menu
    const playIcon = document.getElementById('play-icon'); // Existing icon
    const pauseIcon = document.getElementById('pause-icon'); // Existing icon
    const analysisModeOptions = document.querySelectorAll('.analysis-mode-option'); // <<< NEW: Get all mode options

    // --- NEW: Left Sidebar PDF Tool DOM References (Updated for Card Layout) ---
    const pdfUploadInput = document.getElementById('pdf-upload-input');
    const pdfUploadCard = document.getElementById('pdf-upload-card');
    const pdfFileActionsCard = document.getElementById('pdf-file-actions-card');
    const pdfInfoContainer = document.getElementById('pdf-info-container'); // ADD THIS LINE
    const pdfFilenameEl = document.getElementById('pdf-filename');
    const pdfRemoveBtn = document.getElementById('pdf-remove-btn');
    const pdfActionsContainer = document.getElementById('pdf-actions-container'); // ADD THIS LINE
    const textExtractBtn = document.getElementById('text-extract-btn');
    const pdfAnalysisBtn = document.getElementById('pdf-analysis-btn');
    const pdfActionStatusEl = document.getElementById('pdf-action-status'); // Shared status element
    const pdfDownloadCard = document.getElementById('pdf-download-card');
    // --- NEW: Status elements for PDF operations (ensure these IDs exist in HTML) ---
    // const pdfExtractStatusEl = document.getElementById('pdf-extract-status'); // No longer separate
    // const pdfAnalysisStatusEl = document.getElementById('pdf-analysis-status'); // No longer separate
    const pdfDownloadContainer = document.getElementById('pdf-download-container'); // Inner container for the button, inside pdfDownloadCard
    const downloadPdfBtn = document.getElementById('download-pdf-btn');

    // --- NEW: PDF Target Audience Dropdown Elements ---
    const pdfTargetAudienceButton = document.getElementById('pdf-target-audience-button');
    const pdfTargetAudienceOptions = document.getElementById('pdf-target-audience-options');
    const pdfTargetAudienceSelected = document.getElementById('pdf-target-audience-selected');
    // --- END NEW ---

    // --- NEW: PDF Analysis Mode Dropdown Elements ---
    const pdfAnalysisModeButton = document.getElementById('pdf-analysis-mode-button');
    const pdfAnalysisModeOptions = document.getElementById('pdf-analysis-mode-options');
    const pdfAnalysisModeSelected = document.getElementById('pdf-analysis-mode-selected');
    // --- END NEW ---

    // --- NEW: PDF Overview Page Options DOM References ---
    const includeOverviewPageCheckbox = document.getElementById('include-overview-page');
    const overviewOptionsDetailsDiv = document.getElementById('overview-options-details');
    const overviewTopXCountInput = document.getElementById('overview-top-x-count');
    const overviewTopXTypeSelect = document.getElementById('overview-top-x-type');
    const overviewShowVisualMapCheckbox = document.getElementById('overview-show-visual-map');
    // --- END NEW ---

    // --- NEW: Input validation for Top X Sentences ---
    if (overviewTopXCountInput) {
        overviewTopXCountInput.addEventListener('input', function(event) {
            let value = event.target.value;
            // Remove non-numeric characters
            let numericValue = value.replace(/\D/g, '');

            if (numericValue === '') {
                event.target.value = ''; // Allow empty input or set to min, e.g., '0'
                return;
            }

            let num = parseInt(numericValue, 10);

            if (isNaN(num)) {
                event.target.value = ''; // Should not happen if only digits are allowed
                return;
            }

            // Enforce min/max
            if (num < 0) num = 0;
            if (num > 20) num = 20;

            event.target.value = num;
        });
    }
    // --- END NEW ---

    // --- NEW: Custom Overview Top X Type Dropdown Logic ---
    const overviewTopXTypeButton = document.getElementById('overview-top-x-type-button');
    const overviewTopXTypeOptions = document.getElementById('overview-top-x-type-options');
    const overviewTopXTypeSelected = document.getElementById('overview-top-x-type-selected');
    const hiddenSelectElement = document.getElementById('overview-top-x-type');

    if (overviewTopXTypeButton && overviewTopXTypeOptions && overviewTopXTypeSelected && hiddenSelectElement) {
        // Toggle options display when button is clicked
        overviewTopXTypeButton.addEventListener('click', (event) => {
            event.stopPropagation();
            overviewTopXTypeOptions.classList.toggle('hidden');
        });

        // Handle option selection
        overviewTopXTypeOptions.addEventListener('click', (event) => {
            const link = event.target.closest('a');
            if (link && link.dataset.value) {
                event.preventDefault();
                const selectedValue = link.dataset.value;
                const selectedText = link.textContent;
                
                // Update the visible text
                overviewTopXTypeSelected.textContent = selectedText;
                overviewTopXTypeSelected.dataset.value = selectedValue;
                
                // Update the hidden select for form submission
                for (let i = 0; i < hiddenSelectElement.options.length; i++) {
                    if (hiddenSelectElement.options[i].value === selectedValue) {
                        hiddenSelectElement.selectedIndex = i;
                        break;
                    }
                }
                
                overviewTopXTypeOptions.classList.add('hidden');
                console.log(`Overview Top X Type changed to: ${selectedValue}`);
            }
        });

        // Close dropdown when clicking outside
        document.addEventListener('click', (event) => {
            if (!overviewTopXTypeButton.contains(event.target) && 
                !overviewTopXTypeOptions.contains(event.target) && 
                !overviewTopXTypeOptions.classList.contains('hidden')) {
                overviewTopXTypeOptions.classList.add('hidden');
            }
        });

        // Set initial state - make sure the selected text matches the select value
        const initialValue = hiddenSelectElement.options[hiddenSelectElement.selectedIndex].value;
        const initialText = hiddenSelectElement.options[hiddenSelectElement.selectedIndex].text;
        overviewTopXTypeSelected.textContent = initialText;
        overviewTopXTypeSelected.dataset.value = initialValue;
    }
    // --- END NEW ---

    // --- NEW: Initialize PDF Analysis Mode Dropdown ---
    if (pdfAnalysisModeButton && pdfAnalysisModeOptions && pdfAnalysisModeSelected) {
        // Set initial value
        pdfAnalysisModeSelected.dataset.value = 'better';
        pdfAnalysisModeSelected.textContent = 'Better Analysis';

        // Toggle options display when button is clicked
        pdfAnalysisModeButton.addEventListener('click', (event) => {
            event.stopPropagation();
            pdfAnalysisModeOptions.classList.toggle('hidden');
        });

        // Handle option selection
        pdfAnalysisModeOptions.addEventListener('click', (event) => {
            const link = event.target.closest('a');
            if (link && link.dataset.value) {
                event.preventDefault();
                const selectedValue = link.dataset.value;
                const selectedText = link.textContent.trim();
                
                // Update the visible text
                pdfAnalysisModeSelected.textContent = selectedText;
                pdfAnalysisModeSelected.dataset.value = selectedValue;
                
                pdfAnalysisModeOptions.classList.add('hidden');
                console.log(`PDF Analysis Mode changed to: ${selectedValue}`);
            }
        });

        // Close dropdown when clicking outside
        document.addEventListener('click', (event) => {
            if (!pdfAnalysisModeButton.contains(event.target) && 
                !pdfAnalysisModeOptions.contains(event.target) && 
                !pdfAnalysisModeOptions.classList.contains('hidden')) {
                pdfAnalysisModeOptions.classList.add('hidden');
            }
        });
    }
    // --- END NEW ---

    // --- ANIMATION SETUP: Initial state for PDF cards ---
    const cardsToAnimate = [pdfUploadCard, pdfFileActionsCard, pdfDownloadCard];
    cardsToAnimate.forEach(card => {
        if (card) {
            card.classList.remove('hidden'); // Remove Tailwind's hidden if present
        }
    });

    if (pdfUploadCard) {
        pdfUploadCard.classList.add('card-active');
        pdfUploadCard.classList.remove('card-inactive');
    }
    if (pdfFileActionsCard) {
        pdfFileActionsCard.classList.add('card-inactive');
        pdfFileActionsCard.classList.remove('card-active');
    }
    if (pdfDownloadCard) {
        pdfDownloadCard.classList.add('card-inactive');
        pdfDownloadCard.classList.remove('card-active');
    }
    // --- END ANIMATION SETUP ---

    // --- NEW: PDF Target Audience Dropdown Logic ---
    if (pdfTargetAudienceButton && pdfTargetAudienceOptions && pdfTargetAudienceSelected) {
        pdfTargetAudienceButton.addEventListener('click', (event) => {
            event.stopPropagation(); // Prevent click from immediately closing via document listener
            pdfTargetAudienceOptions.classList.toggle('hidden');
        });

        pdfTargetAudienceOptions.addEventListener('click', (event) => {
            const link = event.target.closest('a');
            if (link && link.dataset.value) {
                event.preventDefault();
                const selectedValue = link.dataset.value;
                const selectedText = link.textContent;
                pdfTargetAudienceSelected.textContent = selectedText; // Show full text like "General Public (Grade 8-10)"
                // Store the actual value if needed for sending to backend later
                // We can retrieve it from pdfTargetAudienceSelected.textContent by mapping or store on dataset
                pdfTargetAudienceSelected.dataset.value = selectedValue; 
                pdfTargetAudienceOptions.classList.add('hidden');
                console.log(`PDF Target Audience changed to: ${selectedValue}`); // Debugging
            }
        });

        // Close dropdown if clicking outside
        document.addEventListener('click', (event) => {
            if (!pdfTargetAudienceButton.contains(event.target) && 
                !pdfTargetAudienceOptions.contains(event.target) && 
                !pdfTargetAudienceOptions.classList.contains('hidden')) {
                pdfTargetAudienceOptions.classList.add('hidden');
            }
        });
    }
    // --- END NEW ---

    // --- Quill Initialization ---
    // Removed the custom Attributor registration as it caused errors with global script loading.
    // We will use a standard CSS class instead.

    // REMOVED Custom Format Registration for GoalDeviationUnderline
    
    // --- LLM Enhancement Format REMOVED ---

    const quill = new Quill(editorContainer, {
        theme: 'snow', // Use the Snow theme
        modules: {
            toolbar: [ // Revised toolbar structure
                [{ 'header': [1, 2, 3, false] }],           // Group 1: Headings
                ['bold', 'italic', 'underline'],            // Group 2: Basic inline
                ['blockquote', 'code-block'],               // Group 3: Block elements (removed link)
                [{ 'list': 'ordered'}, { 'list': 'bullet' }], // Group 4: Lists
                [{ 'indent': '-1'}, { 'indent': '+1' }],      // Group 5: Indentation
                [{ 'align': [] }],                           // Group 6: Alignment
                ['clean']                                   // Group 7: Clean
                // Undo/Redo are typically handled by the history module + keyboard shortcuts
            ],
             history: { // Enable history module for undo/redo
                 delay: 1000, // Debounce time for history entries (ms)
                 maxStack: 500, // Max undo stack size
                 userOnly: true // Only track user changes
             },
            // Configure Quill's clipboard to paste plain text only
            clipboard: {
                matchVisual: false, // Recommended when using matchers
                matchers: [
                    // Match all nodes during paste
                    [Node.ELEMENT_NODE, (node, delta) => {
                        // Convert the pasted content (delta) to plain text
                        let text = '';
                        delta.ops.forEach(op => {
                            if (typeof op.insert === 'string') {
                                text += op.insert;
                            } else {
                                // Handle non-string inserts (like images, embeds) - replace with space or newline
                                text += ' '; // Or '\n' if preferred
                            }
                        });
                        // Return a new Delta containing only the plain text
                        const Delta = Quill.import('delta');
                        return new Delta().insert(text);
                    }]
                ]
            }
        },
    });
    quill.on('focus', function() {
        quill.root.setAttribute('data-placeholder', '');  // Clear placeholder on focus
    });
    
    quill.on('blur', function() {
        if (quill.getText().trim() === '') {
            quill.root.setAttribute('data-placeholder', 'Start writing here...');  // Restore placeholder if empty
        }
    });

    // --- Tippy Initialization ---
    const synonymTooltip = tippy(document.body, { // Attach to body, trigger manually
        allowHTML: true,
        trigger: 'manual',
        interactive: true,
        placement: 'bottom-start',
        appendTo: () => document.body, // Ensure it's appended to body
        content: 'Loading...', // Default content
        // Hide on click outside - SET TO FALSE to allow interaction
        hideOnClick: false, // We will hide manually in handleSynonymClick
        // We'll set reference client rect dynamically
    });

    // --- NEW: Context Menu Tooltip Initialization ---
    const contextMenuTooltip = tippy(document.body, {
        allowHTML: true,
        trigger: 'manual',
        interactive: true,
        placement: 'right-start', // Or 'bottom-start' etc.
        appendTo: () => document.body,
        content: 'Loading...',
        hideOnClick: false, // Hide manually
        theme: 'tippy-dark', // Custom theme for context menu
        // We'll set reference client rect dynamically based on click event
    });
    let currentContextMenuSentenceData = null; // Store data for the active context menu

    // --- Complexity Color Mapping (Dark Theme) ---
    const complexityBackgrounds = {
        green: 'rgba(40, 167, 69, 0.3)',
        yellow: 'rgba(255, 193, 7, 0.3)',
        orange: 'rgba(253, 126, 20, 0.3)',
        red: 'rgba(220, 53, 69, 0.3)',
        gray: 'rgba(108, 117, 125, 0.2)',
    };

    // Define background colors for map segments (Tailwind classes)
    const mapSegmentColors = {
        green: 'bg-green-500', yellow: 'bg-yellow-500', orange: 'bg-orange-500',
        red: 'bg-red-500', gray: 'bg-gray-500',
    };

    // Level descriptions and percentage mapping
    const levelDescriptions = {
        1: 'Very Simple (0-20%)',
        2: 'Simple (21-40%)',
        3: 'Moderate (41-60%)',
        4: 'Complex (61-80%)',
        5: 'Very Complex (81-100%)'
    };

    // --- State for Analysis ---
    let isAnalysisPaused = true; // <<< NEW: Analysis starts paused
    let currentAnalysisData = null; // Store the full analysis response object { results: [], overall_level: {}, readability_scores: {}, target_readability_scores: {} }
    let currentTargetAudience = 'Standard'; // Default audience, updated from select element
    let showHighlighting = true; // Default state for toggle, updated from checkbox
    let showGoalIndicators = true; // Default state for toggle, updated from checkbox
    let currentAnalysisMode = 'better'; // Default analysis mode
    let isOverallScoreOutOfBounds = false; // Track if overall score is outside target
    let currentSensitivityLevel = 3; // Default to Standard (value 3)
    let previousScores = { flesch_kincaid_grade: null, gunning_fog: null, smog_index: null }; // For animation
    // --- State for Context Awareness ---
    let contextAwarenessEnabled = false; // Default state, updated from checkbox
    // let currentGoalText = ''; // REMOVED
    let phaseIndicatorTimeout = null; // Timeout for hiding the 'complete' indicator
    // --- NEW: State for Rewrite Context ---
    let useFullRewriteContext = false; // Default to partial context for rewrites
    // --- NEW: State for Analysis Cancellation ---
    let currentAnalysisId = null; // Unique ID for the current analysis sequence
    let currentAbortController = null; // AbortController for the current analysis fetches
    let lastPasteInfo = null; // { timestamp: number, length: number } | null
    const PASTE_DELETE_THRESHOLD_MS = 1500; // Time window to detect delete after paste (1.5 seconds)
    const PASTE_LENGTH_THRESHOLD = 20; // Minimum length to consider an insert a 'paste'
    const DELETE_MATCH_RATIO = 0.8; // Delete length must be at least 80% of paste length

    let currentPdfTaskId = null; // Stores the current PDF processing task ID

    // --- NEW: PDF Task Polling Function ---
    function pollTaskStatus(taskId, operationType) {
        const statusEl = pdfActionStatusEl; // Always use the shared status element
        const buttonEl = operationType === 'extract_text' ? textExtractBtn : pdfAnalysisBtn;
        // const initialButtonText = operationType === 'extract_text' ? 'Extract Text' : 'Analyze PDF & Highlight'; // Not strictly needed if just disabling

        if (statusEl) {
            statusEl.textContent = `Monitoring ${operationType.replace('_', ' ')}... (Task ID: ${taskId})`;
            statusEl.className = 'status-text loading';
        }
        // updatePdfActionButtonsState(true); // Ensure buttons are disabled at the start of polling - this is now handled by handlePdfProcessing
        setAnalysisLoading(true, 'pdf');

        const intervalId = setInterval(() => {
            fetch(`/task_status/${taskId}`)
                .then(response => {
                    if (!response.ok) {
                        throw new Error('Network response was not ok when checking task status.');
                    }
                    return response.json();
                })
                .then(data => {
                    // Ensure setAnalysisLoading(false, 'pdf') is called even if errors occur in UI updates
                    // by putting the main state processing in a try block and setAnalysisLoading in a finally.
                    // However, setAnalysisLoading should only be false if the task is terminal (SUCCESS/FAILURE)
                    // or if polling itself errors out.
                    
                    if (data.state === 'SUCCESS') {
                        clearInterval(intervalId); // Stop polling
                        try {
                            if (statusEl) {
                                statusEl.textContent = data.status_message || `${operationType.replace('_', ' ')} completed successfully.`;
                                statusEl.className = 'status-text success';
                            }
                            updatePdfActionButtonsState(false); // Re-enable all PDF action buttons

                            if (operationType === 'extract_text' && data.result && data.result.extracted_text) {
                                quill.setText(data.result.extracted_text);
                            } else if (operationType === 'full_analysis' && data.result) {
                                currentPdfTaskId = taskId; //  <--- Fix: Ensure currentPdfTaskId is set for download
                                // For full_analysis, the main action is enabling download.
                                // Other UI updates (like scores, map, or editor content) would depend on 
                                // how 'full_analysis' data from data.result is meant to be used by the frontend.
                                console.log('PDF Full Analysis Result:', data.result); 
                                if (data.result.highlighted_pdf_filename) {
                                    console.log("Full analysis successful, enabling download card for:", data.result.highlighted_pdf_filename);
                                    pdfDownloadCard.classList.remove('card-inactive');
                                    pdfDownloadCard.classList.add('card-active');
                                } else {
                                    console.warn("Full analysis successful, but no highlighted PDF filename received.");
                                    pdfDownloadCard.classList.add('card-inactive');
                                    pdfDownloadCard.classList.remove('card-active');
                                }
                            }
                        } catch (uiError) {
                            console.error(`Error updating UI after task success (${operationType}):`, uiError);
                            if (statusEl) { // Still try to set a generic error message on UI error
                                statusEl.textContent = `Error updating UI for ${operationType}. Check console.`;
                                statusEl.className = 'status-text error';
                            }
                        } finally {
                            setAnalysisLoading(false, 'pdf'); // Ensure loading is stopped
                        }
                    } else if (data.state === 'FAILURE') {
                        clearInterval(intervalId); // Stop polling
                        try {
                            if (statusEl) {
                                statusEl.textContent = data.error_details || data.status_message || `An error occurred during ${operationType.replace('_', ' ')}.`;
                                statusEl.className = 'status-text error';
                            }
                            updatePdfActionButtonsState(false); // Re-enable all PDF action buttons
                        } finally {
                            setAnalysisLoading(false, 'pdf'); // Ensure loading is stopped
                        }
                    } else if (data.state === 'PROGRESS') {
                        if (statusEl) {
                            statusEl.textContent = data.status_message || `Processing ${operationType.replace('_', ' ')}...`;
                            // If you have specific progress percentage or steps in data.meta:
                            // e.g., if (data.meta && data.meta.progress) statusEl.textContent += ` (${data.meta.progress}%)`;
                        }
                    } else if (data.state === 'PENDING') {
                         if (statusEl) {
                            statusEl.textContent = data.status_message || `Task for ${operationType.replace('_', ' ')} is pending...`;
                        }
                    } // Other states like PENDING, RETRY don't necessarily stop the main loading indicator
                })
                .catch(error => {
                    console.error('Polling error:', error);
                    clearInterval(intervalId);
                    if (statusEl) {
                        statusEl.textContent = 'Error checking task status. Check console.';
                        statusEl.className = 'status-text error';
                    }
                    updatePdfActionButtonsState(false); // Re-enable all PDF action buttons
                    setAnalysisLoading(false, 'pdf'); // Stop loading on polling error
                });
        }, 2000); // Poll every 2 seconds
    }

    // --- NEW: Left Sidebar PDF Tool Event Handlers ---
    // Ensure all new card elements are checked in the initial if
    if (pdfUploadCard && pdfFileActionsCard && pdfDownloadCard && pdfRemoveBtn && pdfUploadInput && pdfInfoContainer && pdfFilenameEl && pdfActionsContainer && textExtractBtn && pdfAnalysisBtn && pdfDownloadContainer && downloadPdfBtn) {
        
        function showUploadState() {
            // pdfUploadCard.classList.remove('hidden');
            pdfUploadCard.classList.add('card-active');
            pdfUploadCard.classList.remove('card-inactive');

            // pdfFileActionsCard.classList.add('hidden');
            pdfFileActionsCard.classList.add('card-inactive');
            pdfFileActionsCard.classList.remove('card-active');

            // pdfDownloadCard.classList.add('hidden'); // Hide the entire download card
            pdfDownloadCard.classList.add('card-inactive');
            pdfDownloadCard.classList.remove('card-active');
            
            pdfFilenameEl.textContent = 'No file selected.';
            if(pdfUploadInput) pdfUploadInput.value = ''; // Clear file input
            if(pdfActionStatusEl) pdfActionStatusEl.textContent = '';
            // if(pdfDownloadStatusEl) pdfDownloadStatusEl.textContent = ''; // This element was removed
            currentPdfTaskId = null;
            textExtractBtn.disabled = false;
            pdfAnalysisBtn.disabled = false;
        }

        pdfUploadInput.addEventListener('change', (event) => {
            const file = event.target.files[0];
            if (file) {
                currentPdfFile = file; // Correctly assign the selected file to the outer scope variable
                pdfFilenameEl.textContent = file.name;
                
                pdfUploadCard.classList.add('card-inactive');
                pdfUploadCard.classList.remove('card-active');

                pdfFileActionsCard.classList.add('card-active');
                pdfFileActionsCard.classList.remove('card-inactive');

                pdfDownloadCard.classList.add('card-inactive');
                pdfDownloadCard.classList.remove('card-active');

                console.log('PDF Selected:', file.name);
                currentPdfTaskId = null;
                if(pdfActionStatusEl) {
                    pdfActionStatusEl.textContent = '';
                    pdfActionStatusEl.className = 'status-text'; // Reset status style
                }
                textExtractBtn.disabled = false;
                pdfAnalysisBtn.disabled = false;
            } else {
                showUploadState(); // Revert to upload state if no file is chosen
            }
        });

        pdfRemoveBtn.addEventListener('click', () => {
            showUploadState();
            console.log('PDF Removed. UI reset to upload state.');
        });

        downloadPdfBtn.addEventListener('click', () => {
            if (currentPdfTaskId) { // Use the stored task ID from the completed analysis task
                console.log('"Download Analyzed PDF" clicked for task ID:', currentPdfTaskId);
                window.open(`/download_highlighted_pdf/${currentPdfTaskId}`, '_blank');
            } else {
                alert('No analyzed PDF available for download. Please analyze a PDF first.');
            }
        });
    } else {
        console.warn('One or more PDF tool DOM elements are missing. PDF functionality may not work.');
    }


    // --- Stats Calculation ---
    function updateStats() {
        // console.log("updateStats called"); // DEBUG
        const text = quill.getText();
        const trimmedText = text.trim();
        // console.log("Text length:", text.length, "Trimmed text:", trimmedText.substring(0, 50) + "..."); // DEBUG

        // Word Count (simple split)
        const words = trimmedText ? trimmedText.split(/\s+/) : [];
        // console.log("Word count element:", wordCountEl); // DEBUG
        if (wordCountEl) wordCountEl.textContent = words.length;
        // console.log("Calculated words:", words.length); // DEBUG

        // Character Count
        const charCount = text.length > 0 ? text.length - 1 : 0;
        // console.log("Character count element:", characterCountEl); // DEBUG
        if (characterCountEl) characterCountEl.textContent = charCount;
        // console.log("Calculated characters:", charCount); // DEBUG

        // Sentence Count (simple regex - adjust if more complex rules needed)
        // Match '.', '?', '!' possibly followed by whitespace and not preceded by another punctuation
        const sentences = trimmedText ? trimmedText.match(/[^.!?]+[.!?]+/g) : [];
        const sentenceCount = sentences ? sentences.length : 0;
        // console.log("Sentence count element:", sentenceCountEl); // DEBUG
        if (sentenceCountEl) sentenceCountEl.textContent = sentenceCount;
        // console.log("Calculated sentences:", sentenceCount); // DEBUG
    }

    // --- Complexity Meter Update ---
// --- Helper function to format target ranges ---
function formatTargetRange(targetTuple) { // NEW
    if (!targetTuple) return '';
    const [min, max] = targetTuple;
    if (min !== null && max !== null) {
        // Check for single value range
        if (min === max) return `(Target: ${min})`;
        return `(Target: ${min}-${max})`;
    } else if (min !== null) {
        return `(Target: ${min}+)`;
    } else if (max !== null) {
        return `(Target: <= ${max})`; // Less common case
    }
    return '';
}

// --- Update Readability Scores (Handles calculated + target display) ---
function updateReadabilityScores(analysisData) {
    const calculatedScores = analysisData?.readability_scores || {};
    const targetScores = analysisData?.target_readability_scores || {};

    // Update calculated scores
    updateScoreElement(fleschKincaidScoreEl, calculatedScores.flesch_kincaid_grade, 'flesch_kincaid_grade');
    updateScoreElement(gunningFogScoreEl, calculatedScores.gunning_fog, 'gunning_fog');
    updateScoreElement(smogIndexScoreEl, calculatedScores.smog_index, 'smog_index');

    // --- Update Target Text Content (Always update text if data exists) ---
    const fkTargetText = formatTargetRange(targetScores?.flesch_kincaid_grade);
    const gfTargetText = formatTargetRange(targetScores?.gunning_fog);

    if (fleschKincaidTargetEl) {
        fleschKincaidTargetEl.textContent = fkTargetText;
        // Visibility is handled by the toggle listener and initial state
    }
    if (gunningFogTargetEl) {
        gunningFogTargetEl.textContent = gfTargetText;
        // Visibility is handled by the toggle listener and initial state
    }
    // --- End Update Target Text ---

    // Visibility is handled by the toggle listener and initial setup
}


// --- Complexity Meter Update (Modified) ---
function updateComplexityMeter(analysisData) { // Modified to accept full data
    const levelData = analysisData?.overall_level; // Get level from full data
        const defaultColor = 'bg-gray-600';
        const levelColors = {
            1: 'bg-green-500',
            2: 'bg-lime-500',
            3: 'bg-yellow-500',
            4: 'bg-orange-500',
            5: 'bg-red-500'
        };

        const currentLevel = levelData ? levelData.level : 0;
        const description = levelData ? levelData.description : 'Enter text to analyze';

        // Calculate percentage (20% per level)
        const percentage = currentLevel * 20;
        if (complexityPercentageEl) {
            complexityPercentageEl.textContent = `${percentage}%`;
        }

        complexityLevelDivs.forEach(div => {
            const divLevel = parseInt(div.dataset.level, 10);
            div.classList.remove(...Object.values(levelColors), defaultColor);

            if (divLevel <= currentLevel) {
                div.classList.add(levelColors[divLevel]);
            } else {
                div.classList.add(defaultColor);
            }
        });

        // Removed the line that updated complexityDescriptionEl.textContent - static labels handle this.

        // --- Target Marker Logic --- (Moved to applyGoalIndicatorVisibility)
        // const meterContainer = document.getElementById('overall-complexity-meter');
        // if (meterContainer) {
        //     // Apply/remove class based on current toggle state
        //     meterContainer.classList.toggle('show-goal-indicator', showGoalIndicators);
        //     // CSS needs to handle the display based on this class
        // }
        // --- End Target Marker Logic ---
    }

    // --- NEW Helper: Check if overall scores are out of bounds ---
    function checkIfOutOfBounds(calculatedScores, targetScores) {
        if (!calculatedScores || !targetScores) return false;

        let isOut = false;

        // Check Flesch-Kincaid Grade
        const fkTarget = targetScores.flesch_kincaid_grade;
        const fkScore = calculatedScores.flesch_kincaid_grade;
        if (fkTarget && fkScore !== null) {
            const [min, max] = fkTarget;
            if (min !== null && fkScore < min) isOut = true;
            if (max !== null && fkScore > max) isOut = true;
        }

        // Check Gunning Fog (if not already out)
        const gfTarget = targetScores.gunning_fog;
        const gfScore = calculatedScores.gunning_fog;
        if (!isOut && gfTarget && gfScore !== null) {
            const [min, max] = gfTarget;
            if (min !== null && gfScore < min) isOut = true;
            if (max !== null && gfScore > max) isOut = true;
        }

        // Add checks for other scores (e.g., SMOG) here if needed

        return isOut;
    }


    // --- Readability Score Calculation ---
    function calculateReadabilityScore(text) {
        if (!text.trim()) return '-';

        // Simple Flesch-Kincaid approximation
        const words = text.trim().split(/\s+/);
        const sentences = text.trim().match(/[^.!?]+[.!?]+/g) || [];
        const syllables = words.reduce((count, word) => count + Math.max(1, word.length / 3), 0);

        if (sentences.length === 0 || words.length === 0) return '-';

        const score = 206.835 - 1.015 * (words.length / sentences.length) - 84.6 * (syllables / words.length);
        return Math.round(score);
    }
 
    // --- NEW: Phase Indicator Management ---
    const phaseIndicatorClasses = {
        idle: ['hidden'],
        fast: ['bg-cyan-500', 'animate-pulse'], // Cyan, pulsing (Sequential sentence analysis)
        full: ['bg-yellow-500', 'animate-pulse'], // Yellow, pulsing (Fetching overall analysis data)
        processing_overall: ['bg-magenta-500', 'animate-pulse'], // Magenta, pulsing (Processing overall data for sidebar)
        complete: ['bg-green-500'], // Green, static (briefly shown when all analysis is complete)
        error: ['bg-red-500'], // Red, static
    };
 
    function updatePhaseIndicator(state) {
        if (!analysisPhaseIndicator) return;
 
        // Clear previous timeout if any
        if (phaseIndicatorTimeout) {
            clearTimeout(phaseIndicatorTimeout);
            phaseIndicatorTimeout = null;
        }
 
        // Remove all state classes and hidden
        analysisPhaseIndicator.classList.remove(
            ...Object.values(phaseIndicatorClasses).flat(),
            'hidden'
        );
 
        if (state === 'idle') {
            analysisPhaseIndicator.classList.add('hidden');
        } else if (phaseIndicatorClasses[state]) {
            analysisPhaseIndicator.classList.add(...phaseIndicatorClasses[state]);
            analysisPhaseIndicator.classList.remove('hidden'); // Ensure visible
 
            // Set title for tooltip
            let title = 'Analysis Phase';
            if (state === 'fast') title = 'Fast Analysis Running...';
            else if (state === 'full') title = 'Fetching Overall Analysis Data...'; // Updated title
            else if (state === 'processing_overall') title = 'Processing Overall Analysis...'; // New title
            else if (state === 'complete') title = 'Analysis Complete';
            else if (state === 'error') title = 'Analysis Error';
            analysisPhaseIndicator.setAttribute('title', title);
 
            // Special handling for 'complete': hide after a delay
            if (state === 'complete') {
                phaseIndicatorTimeout = setTimeout(() => {
                    updatePhaseIndicator('idle'); // Go back to idle state
                }, 1500); // Hide after 1.5 seconds
            }
        } else {
            console.warn("Unknown phase indicator state:", state);
            analysisPhaseIndicator.classList.add('hidden'); // Hide if unknown state
        }
    }
 
    // --- Analysis & Highlighting (Modified for Phase Indicator & Mode) ---
    async function analyzeAndHighlight(forceHighlightUpdate = false, mode = 'full') { // Added mode parameter
        // Override default mode with the current global mode if not forcing highlight update
        // When forceHighlightUpdate is true, we are typically just re-rendering with existing data,
        // so the mode of that existing data should be preserved.
        const effectiveMode = forceHighlightUpdate ? mode : currentAnalysisMode;
        console.log(`%c[analyzeAndHighlight] Called. Initial mode: ${mode}, Effective mode: ${effectiveMode}`, 'color: blue'); // DEBUG
        const text = quill.getText();
        const startTime = performance.now();
        const audience = currentTargetAudience; // Use state variable

        let itemsForHighlightingAndMap = []; // Declare at the top and initialize

        if (!text.trim()) {
            quill.formatText(0, quill.getLength(), 'background', false, 'api'); // Clear highlights
            quill.formatText(0, quill.getLength(), 'underline', false, 'api'); // Clear underlines
            currentAnalysisData = null; // Clear full data
            isOverallScoreOutOfBounds = false; // Reset out of bounds flag
            updateComplexityMeter(null); // Reset meter
            updateReadabilityScores(null); // Clear scores and targets
            // updateDocumentMap(null); // OLD WAY: updateDocumentMap will be called below with empty items
            if (analysisTimeEl) analysisTimeEl.textContent = '0ms';
            updatePhaseIndicator('idle'); // Set indicator to idle
            // Call highlighting and map update with empty items before returning
            applyStatisticalHighlighting(itemsForHighlightingAndMap); // itemsForHighlightingAndMap is []
            updateDocumentMap({ results: itemsForHighlightingAndMap }); // Pass { results: [] }
            return;
        }

        // Only fetch new analysis if not forcing highlight update
        if (!forceHighlightUpdate) {
            updatePhaseIndicator('full'); // <<< SET Phase Indicator to 'full' (Yellow)
            const requestBody = {
                text: text,
                target_audience: audience,
                context_awareness_enabled: contextAwarenessEnabled,
                mode: effectiveMode // <<< USE effectiveMode
            };
            console.log("[analyzeAndHighlight] Sending analysis request:", requestBody);

            try {
                if (currentAbortController) {
                    console.log("analyzeAndHighlight: Aborting previous analysis ID:", currentAnalysisId);
                    currentAbortController.abort();
                }
                currentAnalysisId = crypto.randomUUID();
                currentAbortController = new AbortController();
                requestBody.analysisId = currentAnalysisId;
                const signal = currentAbortController.signal;
                console.log("analyzeAndHighlight: Starting analysis ID:", currentAnalysisId);

                const response = await fetch('/analyze', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(requestBody),
                    signal: signal
                });

                if (!response.ok) {
                    let errorMsg = `HTTP error! status: ${response.status}`;
                    // If it's a 429 (Rate Limit Exceeded), the message is already specific
                    // Otherwise, try to parse JSON error from backend
                    if (response.status !== 429) {
                        try {
                            const errorData = await response.json();
                            errorMsg = errorData.error || errorMsg;
                        } catch (e) { /* Ignore parsing error */ }
                    }
                    throw new Error(errorMsg); // Will be caught below
                }

                // If successful analysis (not 429), refresh rate limits
                fetchAndApplyRateLimits(); 

                const data = await response.json();
                currentAnalysisData = data; // Store the FULL response
                console.log("Received analysis response:", currentAnalysisData); // DEBUG

                // --- Normalization logic MOVED to after this if/else block ---

                const endTime = performance.now();
                const analysisTime = Math.round(endTime - startTime);
                updateComplexityMeter(currentAnalysisData);
                updateReadabilityScores(currentAnalysisData);
                if (analysisTimeEl) analysisTimeEl.textContent = `${analysisTime}ms`;
                isOverallScoreOutOfBounds = checkIfOutOfBounds(
                    currentAnalysisData?.readability_scores,
                    currentAnalysisData?.target_readability_scores
                );
                applyGoalIndicatorVisibility();

            } catch (error) {
                if (error.name === 'AbortError') {
                    console.log('Analysis fetch aborted (analyzeAndHighlight). ID:', requestBody.analysisId);
                    // currentAnalysisData might be stale or null, itemsForHighlightingAndMap will be derived from it
                    // applyStatisticalHighlighting and updateDocumentMap will be called in the outer scope
                    // Ensure UI reflects that analysis is now paused/idle due to abort
                    if (!isAnalysisPaused) { // If it was running and got aborted
                        isAnalysisPaused = true;
                        updateAnalysisButtonState();
                        updatePhaseIndicator('idle');
                    }
                    return; 
                }
                console.error('Error fetching analysis:', error);
                currentAnalysisData = null;
                isOverallScoreOutOfBounds = false;
                updateComplexityMeter(null);
                updateReadabilityScores(null);
                if (analysisTimeEl) analysisTimeEl.textContent = 'Error';
                updatePhaseIndicator('error');
                // Ensure UI reflects that analysis is now paused/idle due to error
                isAnalysisPaused = true;
                updateAnalysisButtonState();
            } finally {
                const wasAborted = currentAbortController?.signal.aborted ?? false;
                if (!wasAborted) {
                    if (!currentAnalysisData && !isOverallScoreOutOfBounds) {
                        // Error state already set by catch block, which also sets isAnalysisPaused = true
                    } else if (text.trim()) {
                        updatePhaseIndicator('complete');
                        isAnalysisPaused = true; // << SET PAUSED ON COMPLETION
                        updateAnalysisButtonState(); // << UPDATE BUTTON
                    } else {
                        updatePhaseIndicator('idle');
                        isAnalysisPaused = true; // << SET PAUSED (e.g. if text was cleared)
                        updateAnalysisButtonState(); // << UPDATE BUTTON
                    }
                    currentAnalysisId = null;
                    currentAbortController = null;
                } else {
                     console.log("analyzeAndHighlight finally: Analysis was aborted, not setting complete/idle.");
                     // isAnalysisPaused and button state should have been handled by the AbortError catch block
                }
            }
        }
        // If forceHighlightUpdate = true, currentAnalysisData from a previous call is used.

        // --- Normalize the source of sentence-level data for highlighting and map ---
        // This block now runs after currentAnalysisData is settled (either new, existing, or null)
        if (currentAnalysisData && Array.isArray(currentAnalysisData.sentences)) {
            itemsForHighlightingAndMap = currentAnalysisData.sentences;
        } else if (currentAnalysisData && Array.isArray(currentAnalysisData.results)) {
            // Fallback for older structures or other potential analysis types that might use a 'results' key.
            itemsForHighlightingAndMap = currentAnalysisData.results;
            console.warn("[analyzeAndHighlight] Used 'results' array as fallback. 'sentences' array was missing or invalid in currentAnalysisData.");
        } else if (currentAnalysisData) {
            // Data exists, but neither .sentences nor .results is a valid array.
            console.warn("[analyzeAndHighlight] Neither 'sentences' nor 'results' array is valid in currentAnalysisData. Highlighting may not work as expected.");
            // itemsForHighlightingAndMap remains empty if initialized as such
        } else {
             console.warn("[analyzeAndHighlight] No currentAnalysisData available to derive itemsForHighlightingAndMap.");
             // itemsForHighlightingAndMap remains empty if initialized as such
        }

        // Apply highlighting and update the document map using the derived items.
        applyStatisticalHighlighting(itemsForHighlightingAndMap);

        const mapData = currentAnalysisData ? { ...currentAnalysisData, results: itemsForHighlightingAndMap } : { results: [] };
        updateDocumentMap(mapData);
    }


    // --- Helper function to update score with animation ---
    // --- Helper function to update score with animation ---
    // (This remains largely the same, used by updateReadabilityScores)
    function updateScoreElement(element, newScore, scoreKey) {
        const currentScore = newScore !== null ? newScore : 'N/A';
        const previousScore = previousScores[scoreKey] !== null ? previousScores[scoreKey] : 'N/A';

        if (element && currentScore !== previousScore) {
            element.classList.add('score-updating'); // For CSS animation
            element.textContent = currentScore;
            previousScores[scoreKey] = newScore;
            setTimeout(() => {
                if (element) element.classList.remove('score-updating');
            }, 300); // Match CSS transition duration
        } else if (element && element.textContent !== String(currentScore)) { // Ensure comparison is string-based if needed
             // If score hasn't changed but text is wrong (e.g., initial load or 'Error'), update without animation
             element.textContent = currentScore;
             previousScores[scoreKey] = newScore; // Ensure previous score is stored
        }
    }

    // --- Analysis & Highlighting --- // <<< REDUNDANT DEFINITION COMMENTED OUT
    /*
    async function analyzeAndHighlight(forceHighlightUpdate = false) {
        const text = quill.getText();
        const startTime = performance.now();

        if (!text.trim()) {
            quill.formatText(0, quill.getLength(), 'background', false, 'api');
            currentAnalysisResults = [];
            updateComplexityMeter(null);
            // Reset individual scores using the helper function
            updateScoreElement(fleschKincaidScoreEl, null, 'flesch_kincaid_grade');
            updateScoreElement(gunningFogScoreEl, null, 'gunning_fog');
            updateScoreElement(smogIndexScoreEl, null, 'smog_index');
            // if (readabilityScoreEl) readabilityScoreEl.textContent = '-'; // Removed
            if (analysisTimeEl) analysisTimeEl.textContent = '0ms';
            // Clear highlighting if text is empty
        applyHighlighting([]); // Call with empty results to clear formats
        updateDocumentMap([]); // Clear the map as well
        return;
    }

        // Only fetch new analysis if not forcing highlight update
        if (!forceHighlightUpdate) {
            // Show loading state
            if (complexityLoadingEl) complexityLoadingEl.classList.remove('hidden');
            // REMOVED: Update individual score placeholders to '...'

            try {
                const response = await fetch('/analyze', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text: text }),
                });

                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

                const data = await response.json();
                currentAnalysisResults = data.results || []; // Store new results

                // Calculate metrics
                const endTime = performance.now();
                const analysisTime = Math.round(endTime - startTime);

                // Update UI parts that depend on new analysis
                updateComplexityMeter(data.overall_level);
                // Update individual readability scores using the helper function
                const scores = data.readability_scores || {};
                updateScoreElement(fleschKincaidScoreEl, scores.flesch_kincaid_grade, 'flesch_kincaid_grade');
                updateScoreElement(gunningFogScoreEl, scores.gunning_fog, 'gunning_fog');
                updateScoreElement(smogIndexScoreEl, scores.smog_index, 'smog_index');

                if (analysisTimeEl) analysisTimeEl.textContent = `${analysisTime}ms`;

            } catch (error) {
                console.error('Error fetching analysis:', error);
                updateComplexityMeter({level: 0, description: "Analysis Error"});
                // Update individual scores on error using the helper function
                updateScoreElement(fleschKincaidScoreEl, 'Error', 'flesch_kincaid_grade'); // Pass 'Error' as string
                updateScoreElement(gunningFogScoreEl, 'Error', 'gunning_fog');
                updateScoreElement(smogIndexScoreEl, 'Error', 'smog_index');

                if (analysisTimeEl) analysisTimeEl.textContent = 'Error';
                currentAnalysisResults = []; // Clear results on error
                updateDocumentMap([]); // Clear map on error
            } finally {
                if (complexityLoadingEl) complexityLoadingEl.classList.add('hidden');
            }
        }

        // Always apply highlighting based on current results and target audience
        // applyHighlighting(currentAnalysisResults); // This call was inside the commented block
    }
    */
    // --- Dynamic Color Calculation based on Sensitivity ---
    function getDynamicHighlightColor(score, sensitivityLevel) {
        // Define base thresholds (Standard Sensitivity - Level 3)
        let thresholds = {
            green: 0.4, // Score below this is green
            yellow: 0.7, // Score below this is yellow
            orange: 1.0, // Score below this is orange (else red)
        };

        // Adjust thresholds based on sensitivity
        // Sensitivity 1 (Very Lenient) -> Higher thresholds
        // Sensitivity 5 (Very Strict) -> Lower thresholds
        // We adjust by a factor, e.g., 0.15 per level difference from standard (3) - Increased from 0.1
        const adjustmentFactor = (3 - sensitivityLevel) * 0.15; // Positive for lenient, negative for strict

        thresholds.green += adjustmentFactor;
        thresholds.yellow += adjustmentFactor;
        thresholds.orange += adjustmentFactor;

        // Determine color based on adjusted thresholds
        if (score < thresholds.green) {
            return "green";
        } else if (score < thresholds.yellow) {
            return "yellow";
        } else if (score < thresholds.orange) {
            return "orange";
        } else {
            return "red";
        }
    }


    // --- Apply Statistical Highlighting (Renamed from applyHighlighting) ---
    function applyStatisticalHighlighting(results) {
        const docLength = quill.getLength();
        console.log(`%c[Highlighting] Starting final application. Quill length: ${docLength}. Received ${results?.length ?? 0} results.`, 'color: purple'); // Log start and Quill length
        // Clear only statistical highlights (background, standard underline)
        console.log("[Highlighting] Clearing existing background/underline formats...");
        quill.formatText(0, docLength, 'background', false, 'api');
        quill.formatText(0, docLength, 'underline', false, 'api');
        console.log("[Highlighting] Formats cleared.");

        // Check statistical highlighting toggle state
        if (!showHighlighting) {
            console.log("[Highlighting] Highlighting disabled, skipping application."); // Log disabled state
            return; // Exit if statistical highlighting is turned off
        }

        if (!results || results.length === 0) { // Check if results exist
             console.log("[Highlighting] No results to apply."); // Log no results
             return;
        }


        // Determine deviation direction for goal indicator logic (remains the same)
        let deviationDirection = null; // "high" (too complex), "low" (too simple), or null
        if (isOverallScoreOutOfBounds && currentAnalysisData && currentAnalysisData.readability_scores && currentAnalysisData.target_readability_scores) {
            // We'll use Flesch-Kincaid as the main reference (could be improved to use all)
            const fkScore = currentAnalysisData.readability_scores.flesch_kincaid_grade;
            const fkTarget = currentAnalysisData.target_readability_scores.flesch_kincaid_grade;
            if (fkScore !== null && fkTarget) {
                const [min, max] = fkTarget;
                if (max !== null && fkScore > max) deviationDirection = "high";
                else if (min !== null && fkScore < min) deviationDirection = "low";
                // Debug log for deviation direction
                console.log(`[Goal Indicator] Flesch-Kincaid: score=${fkScore}, target=[${min},${max}], deviationDirection=${deviationDirection}, isOverallScoreOutOfBounds=${isOverallScoreOutOfBounds}`);
            } else {
                console.log(`[Goal Indicator] Flesch-Kincaid: score=${fkScore}, target=${fkTarget}, deviationDirection=${deviationDirection}, isOverallScoreOutOfBounds=${isOverallScoreOutOfBounds}`);
            }
        } else {
            console.log(`[Goal Indicator] Not out of bounds or missing data. isOverallScoreOutOfBounds=${isOverallScoreOutOfBounds}`);
        }

        results.forEach(result => {
            const score = result.score; // Get score from backend result
            const color = getDynamicHighlightColor(score, currentSensitivityLevel); // Calculate color dynamically based on sensitivity
            const bgColor = complexityBackgrounds[color] || complexityBackgrounds['gray'];
            const startIndex = result.start; // Use start index from backend
            const endIndex = result.end;     // Use end index from backend
            const length = endIndex - startIndex; // Calculate length

            // --- DETAILED LOGGING ---
            console.log(`[Highlighting] Processing result ${result.index}: start=${startIndex}, end=${endIndex}, length=${length}, score=${score?.toFixed(3)}, color=${color}`);
            // --- END LOGGING ---

            // --- Boundary Check ---
            if (startIndex + length > docLength) {
                 console.warn(`[Highlighting] Skipping result ${result.index}: Calculated range [${startIndex}, ${length}] exceeds Quill length ${docLength}.`);
                 return; // Use return to skip this iteration in forEach
            }
            // --- End Boundary Check ---


            if (startIndex !== undefined && length > 0) {
                // Apply background color directly (removed setTimeout/wave effect)
                if (showHighlighting) { // Check again inside loop
                    try {
                        // console.log(`[Highlighting] Applying background ${bgColor} to range [${startIndex}, ${length}]`); // Log application (optional)
                        quill.formatText(startIndex, length, 'background', bgColor, 'api');
                    } catch (e) {
                         console.error(`[Highlighting] Error applying background for index ${result.index}:`, e);
                    }
                }

                // Check conditions for underline directly
                let shouldApplyUnderline = false;
                if (showGoalIndicators && isOverallScoreOutOfBounds) {
                    if (deviationDirection === "high" && (color === "red" || color === "orange")) {
                        shouldApplyUnderline = true;
                    } else if (deviationDirection === "low" && color === "green") {
                        shouldApplyUnderline = true;
                    }
                }

                // Apply standard underline format directly if needed
                try {
                    if (shouldApplyUnderline) {
                        // console.log(`[Highlighting] Applying underline to range [${startIndex}, ${length}]`); // Log application (optional)
                        quill.formatText(startIndex, length, 'underline', true, 'api');
                    } else {
                        // Explicitly remove underline if conditions are not met (important for clearing)
                        // console.log(`[Highlighting] Ensuring NO underline for range [${startIndex}, ${length}]`); // Log removal (can be verbose)
                        quill.formatText(startIndex, length, 'underline', false, 'api');
                    }
                } catch (e) {
                     console.error(`[Highlighting] Error applying underline for index ${result.index}:`, e);
                }

                 // --- Log applied formats for problematic indices ---
                 if (result.index >= 18) { // Check formats for last sentences
                     try {
                         const formats = quill.getFormat(startIndex, length);
                         console.log(`[Highlighting] Formats retrieved for index ${result.index} [${startIndex}, ${length}]:`, formats);
                     } catch (e) {
                          console.error(`[Highlighting] Error retrieving formats for index ${result.index}:`, e);
                     }
                 }
                 // --- End Log applied formats ---

            } else {
                 console.warn(`[Highlighting] Invalid indices or length for result ${result.index}: start=${startIndex}, end=${endIndex}, length=${length}. Skipping format.`); // Log skip
            }
        });
        console.log("%c[Highlighting] Finished final application.", 'color: purple'); // Log end
    }

    // --- LLM Enhancement Functions REMOVED ---

    // --- Visual Document Map Update ---
    // --- Visual Document Map Update (Modified) ---
    function updateDocumentMap(analysisData) { // Modified to accept full data
        const results = analysisData?.results || []; // Get results or default to empty array
        const barCount = results.length;
        const barWidth = 8; // px - Should match CSS
        const barGap = 1;  // px - Corresponds to gap-px

        // --- REMOVED: Conditional Overflow and Width logic applied to inner container ---
        // The outer container (#document-map-container) now handles overflow via CSS class.

        // Clear existing map (keep this)
        if (!documentMapContainer) return; // Keep check for inner container
        documentMapContainer.innerHTML = ''; // Clear previous map segments and lines

        // --- Target Line Logic --- (Moved to applyGoalIndicatorVisibility)
        // if (documentMapContainer) {
        //      // Apply/remove class based on current toggle state
        //     documentMapContainer.classList.toggle('show-goal-indicator', showGoalIndicators);
        //      // CSS needs to handle the display based on this class
        //      // TODO: Add CSS rules for .document-map.show-goal-indicator::before or similar
        // }
        // --- End Target Line Logic ---

        if (!results || results.length === 0) { // Use the 'results' variable defined above
            // documentMapContainer.textContent = 'No text to map.'; // Optional message
            return; // Exit if no results
        }

        results.forEach((result, idx) => { // Use the 'results' variable defined above
             if (result.index === undefined || result.score === undefined) {
                 console.warn(`Skipping map segment for result index ${idx} due to missing index or score.`);
                 return; // Skip this iteration if data is missing
             }
            const segment = document.createElement('div');
            segment.classList.add('map-segment'); // Base class for styling

            segment.dataset.sentenceIndex = result.index; // For linking

            // Calculate height (scale score to percentage, with min/max)
            const heightPercent = Math.min(100, Math.max(5, (result.score || 0) * 60 + 5)); // Example scaling
            segment.style.height = `${heightPercent}%`;

            // Determine color based on score and sensitivity
            const colorName = getDynamicHighlightColor(result.score, currentSensitivityLevel);
            const colorClass = mapSegmentColors[colorName] || mapSegmentColors['gray'];
            segment.classList.add(colorClass);

            segment.title = `Sentence ${result.index + 1}: Score ${result.score.toFixed(2)}`; // Tooltip

            documentMapContainer.appendChild(segment);
        });
    }


    // --- NEW: Function to Apply Goal Indicator Visibility ---
    function applyGoalIndicatorVisibility() {
        // Toggle visibility of target score text elements
        if (fleschKincaidTargetEl) {
            fleschKincaidTargetEl.style.display = showGoalIndicators ? 'inline' : 'none';
        }
        if (gunningFogTargetEl) {
            gunningFogTargetEl.style.display = showGoalIndicators ? 'inline' : 'none';
        }

        // Toggle class on meter container
        const meterContainer = document.getElementById('overall-complexity-meter');
        if (meterContainer) {
            meterContainer.classList.toggle('show-goal-indicator', showGoalIndicators);
        }

        // Toggle class on document map container
        if (documentMapContainer) {
            documentMapContainer.classList.toggle('show-goal-indicator', showGoalIndicators);
        }
    }


    // --- Synonym Tooltip ---
    // Store the current selection range when showing the tooltip
    let currentSynonymRange = null;

    // Function to handle clicking a synonym
    function handleSynonymClick(event) {
        const targetLi = event.target.closest('li.synonym-item');
        if (!targetLi) return;

        const synonym = targetLi.dataset.synonym;
        const index = parseInt(targetLi.dataset.rangeIndex, 10);
        const length = parseInt(targetLi.dataset.rangeLength, 10);

        // Ensure Quill and Delta are available
        if (typeof Quill === 'undefined' || !quill) {
            console.error("Quill instance not found.");
            return;
        }
        const Delta = Quill.import('delta');
        if (!Delta) {
             console.error("Quill Delta not found.");
             return;
        }


        if (synonym && !isNaN(index) && !isNaN(length)) {
            // Ensure editor has focus BEFORE operating
            quill.focus();

            // Perform the replacement using Delta
            // Use 'user' source to ensure text-change event fires if needed
            quill.updateContents(new Delta()
                .retain(index) // Go to the start index
                .delete(length) // Delete the original word
                .insert(synonym), // Insert the synonym
            'user');

            // Set cursor position *after* the inserted synonym
            // We need to wait briefly for the update to process before setting selection
            setTimeout(() => {
                 quill.setSelection(index + synonym.length, 0, 'silent'); // Place cursor after inserted word
            }, 0);


            synonymTooltip.hide();
            currentSynonymRange = null; // Clear the range state
        } else {
             console.error("Invalid data for synonym replacement:", { synonym, index, length });
        }
    }

    // --- Delegated Event Listener for Synonym Clicks ---
    // Attach ONE listener to the body to handle clicks on any synonym item
    document.body.addEventListener('click', (event) => {
        // Check if the click happened on a synonym item within an active tippy tooltip
        const targetLi = event.target.closest('li.synonym-item');
        // Check if the parent tooltip element exists and is visible
        const tooltipElement = targetLi?.closest('.tippy-box');

        if (targetLi && tooltipElement && tooltipElement.style.visibility !== 'hidden') {
            // If it's a valid click on a synonym in the tooltip, handle it
            handleSynonymClick(event);
        } else if (synonymTooltip.state.isVisible && !event.target.closest('.tippy-box')) {
            // If the tooltip is visible and the click was OUTSIDE any tippy box, hide it
            synonymTooltip.hide();
            currentSynonymRange = null;
        }
    });


    async function showSynonymTooltip(range) {
        currentSynonymRange = range; // Store the range

        if (!range || range.length === 0) {
            synonymTooltip.hide();
            currentSynonymRange = null;
            return;
        }

        const selectedText = quill.getText(range.index, range.length).trim();

        // Basic check if it's likely a single word
        if (!selectedText || selectedText.includes(' ') || !/^[a-zA-Z]+$/.test(selectedText)) {
             synonymTooltip.hide();
             currentSynonymRange = null;
             return;
        }

        // --- Positioning: Use Browser Selection API ---
        let referenceBounds = null; // Declare only once
        const domSelection = window.getSelection();
        if (domSelection && domSelection.rangeCount > 0) {
            const domRange = domSelection.getRangeAt(0);
            referenceBounds = domRange.getBoundingClientRect();
        } else {
             // Fallback or error if no selection range found
             console.warn("Could not get DOM selection range for tooltip positioning.");
             referenceBounds = quill.getBounds(range.index, range.length); // Fallback to Quill bounds
        }
        // --- End Positioning ---


        if (!referenceBounds) { // Check if we have bounds
             console.error("Could not get bounds for tooltip positioning."); // DEBUG
             synonymTooltip.hide();
             currentSynonymRange = null;
             return;
        }


        // Update tooltip position reference and show loading state
        const tooltipContentId = `synonym-tooltip-content-${Date.now()}`; // Keep unique ID for content updates
        synonymTooltip.setProps({
            getReferenceClientRect: () => referenceBounds, // Use calculated bounds
            placement: 'bottom-start', // Reset placement
            content: `<div id="${tooltipContentId}" class="p-1 text-xs dark:text-gray-200">Loading synonyms...</div>`
            // REMOVED onShow/onHide callbacks for listener management
        });
        console.log("Synonym Tooltip: Showing with loading content. Instance:", synonymTooltip); // DEBUG
        synonymTooltip.show(); // Reverted: Removed setTimeout
        console.log("Synonym Tooltip: Called show(). Is visible:", synonymTooltip.state.isVisible); // DEBUG

        // --- Find Sentence Context ---
        let sentenceContext = '';
        if (currentAnalysisData && currentAnalysisData.results) {
            // Find the sentence result that contains the current range index
            const sentenceResult = currentAnalysisData.results.find(res =>
                range.index >= res.start && range.index < res.end
            );
            if (sentenceResult) {
                sentenceContext = sentenceResult.sentence;
            } else {
                console.warn("Could not find sentence context for synonym request.");
                // --- Improved Fallback ---
                const fullText = quill.getText();
                const windowSize = 150; // Characters before/after selection index
                const contextStart = Math.max(0, range.index - windowSize);
                const contextEnd = Math.min(fullText.length, range.index + range.length + windowSize);
                sentenceContext = fullText.substring(contextStart, contextEnd);
                // Basic sentence boundary approximation (optional refinement)
                const firstSentenceEnd = sentenceContext.search(/[.!?]/);
                if (firstSentenceEnd > -1 && contextStart > 0) { // Try to start from beginning of sentence if possible
                    sentenceContext = sentenceContext.substring(sentenceContext.substring(0, range.index - contextStart).lastIndexOf(/[.!?]/) + 1);
                }
                console.log("Fallback context:", sentenceContext); // DEBUG
            }
        }
        // --- End Find Sentence Context ---


        try {
            // --- Prepare request body with context ---
            const requestBody = {
                word: selectedText,
                sentence_context: sentenceContext, // Add sentence context
                target_audience: currentTargetAudience, // Add current audience profile
                context_awareness_enabled: contextAwarenessEnabled // Add toggle state
            };
            // console.log("Sending synonym request:", requestBody); // DEBUG

            const response = await fetch('/synonyms', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestBody), // Use updated body
            });

            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const data = await response.json(); // Expect { ranked_synonyms: [], llm_recommendation: {} | null } // Updated expected key

            // Build tooltip content with consistent styling
            let contentHTML = `
                <div id="${tooltipContentId}"
                     class="p-3 text-sm text-[var(--text-primary)] bg-[var(--sidebar-bg)] max-h-60 overflow-y-auto
                            border border-[rgba(108,111,147,0.2)] rounded-[var(--border-radius)]
                            shadow-[0_4px_20px_rgba(0,0,0,0.15)] backdrop-blur-[10px]
                            max-w-xs transition-all duration-[var(--transition-speed)]">
            `;
            const rankedSynonyms = data.ranked_synonyms || [];
            const llmRec = data.llm_recommendation;
            const llmSynonymTotal = currentRateLimitInfo.total_limits.llm_synonym || 5;
            const llmSynonymRemaining = currentRateLimitInfo.remaining_counts.llm_synonym !== undefined ? currentRateLimitInfo.remaining_counts.llm_synonym : llmSynonymTotal;

            if (rankedSynonyms.length > 0) {
                contentHTML += `
                    <strong class="block mb-2 text-base font-semibold text-[var(--accent-blue)]">
                        Synonyms for "${selectedText}"
                    </strong>
                    <ul class="list-none p-0 m-0 mb-2 space-y-1">`;

                const rankClasses = {
                    1: 'bg-[var(--accent-green)] hover:opacity-90',
                    2: 'bg-[#34d399] hover:opacity-90',
                    3: 'bg-[var(--accent-yellow)] hover:opacity-90',
                    4: 'bg-[var(--accent-red)] hover:opacity-90',
                    5: 'bg-[#ef4444] hover:opacity-90'
                };
                const badgeBaseClass = 'inline-flex items-center justify-center w-5 h-5 mr-2 text-xs font-bold text-white rounded-[4px] transition-all duration-[var(--transition-speed)]';
                const listItemBaseClass = 'synonym-item flex items-center p-2 rounded-[6px] cursor-pointer hover:bg-[rgba(108,111,147,0.1)] transition-all duration-[var(--transition-speed)]';

                rankedSynonyms.forEach(syn => {
                    const rankClass = rankClasses[syn.rank] || 'bg-gray-500 hover:bg-gray-400';
                    contentHTML += `<li class="${listItemBaseClass}"
                                        data-synonym="${syn.word}"
                                        data-range-index="${range.index}"
                                        data-range-length="${range.length}">
                                      <span class="${badgeBaseClass} ${rankClass}">${syn.rank}</span>
                                      <span>${syn.word}</span>
                                    </li>`;
                });
                contentHTML += `</ul>`;

                if (contextAwarenessEnabled) { // Only show LLM section if context awareness is on
                    contentHTML += `<hr class="border-gray-600 my-1">`; 
                    let limitText = `(${llmSynonymRemaining}/${llmSynonymTotal} remaining)`;
                    let limitColor = 'text-gray-400';
                    if (llmSynonymRemaining <= 0) {
                        limitColor = 'text-red-500 font-semibold';
                    }
                    contentHTML += `<div class="text-purple-300 text-xs font-semibold mb-0.5 flex justify-between">Contextual Suggestion <span id="synonym-llm-limit-display" class="${limitColor} text-xs ml-2">${limitText}</span></div>`;
                    
                    if (llmRec && !llmRec.error && llmRec.recommendation && llmRec.recommendation.length > 0) {
                        contentHTML += `<div class="text-gray-300 text-xs mb-1">"${llmRec.recommendation.join('" or "')}"</div>`; 
                        if (llmRec.reasoning) { 
                            contentHTML += `<div class="text-gray-400 text-xs italic">Reason: ${llmRec.reasoning}</div>`; 
                        }
                    } else if (llmRec && llmRec.error) { 
                        contentHTML += `<div class="text-red-400 text-xs">${llmRec.error}</div>`; 
                    } else if (currentRateLimitInfo.remaining_counts.llm_synonym <=0 && contextAwarenessEnabled) {
                         contentHTML += `<div class="text-red-400 text-xs">Contextual suggestion rate limit exceeded. Please try again later.</div>`;
                    }else {
                         contentHTML += `<div class="text-gray-500 text-xs italic">No specific contextual suggestion available.</div>`;
                    }
                }
            } else {
                contentHTML += `No synonyms found for "${selectedText}".`;
            }
            contentHTML += `</div>`; // Close tooltip container

            // Set the final content with consistent styling
            synonymTooltip.setContent(contentHTML);

        } catch (error) {
            console.error('Error fetching synonyms:', error);
            // Update content within the existing container structure
             synonymTooltip.setContent(`<div id="${tooltipContentId}" class="p-2 text-sm text-red-400 bg-gray-800 border border-gray-700 rounded shadow-lg">Error loading synonyms.</div>`);
        }
    }

    // --- Initialize Status Bar Tooltips ---
    function initTooltips() {
        tippy('.has-tooltip', {
            theme: 'dark', // Use 'dark' or your preferred theme
            placement: 'top',
            arrow: true,
            delay: [100, 0],
        });
    }

    // --- Event Listeners ---
    // Define debounced function just before use
    const debouncedAnalyzeAndHighlight = debounce(analyzeAndHighlight, 750);

    // --- NEW: Helper Function to Cancel Current Analysis ---
    function cancelCurrentAnalysis() {
        console.log(`%cCancel requested. Current ID: ${currentAnalysisId}`, 'color: orange;');
        // 1. Cancel pending debounced call (important for typing)
        debouncedAnalyzeSequentially.cancel();

        // 2. Abort ongoing fetch requests
        if (currentAbortController) {
            console.log(`Aborting fetch for ID: ${currentAnalysisId}`);
            currentAbortController.abort();
            currentAbortController = null; // Clear controller after aborting
        }

        // 3. Notify backend to cancel (if an ID exists)
        if (currentAnalysisId) {
            const idToCancel = currentAnalysisId; // Capture ID before clearing
            currentAnalysisId = null; // Clear ID immediately
            console.log(`Sending backend cancellation for ID: ${idToCancel}`);
            fetch('/cancel_analysis', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ analysisId: idToCancel }),
                // keepalive: true // Consider if needed
            })
            .then(response => response.json())
            .then(data => console.log('Backend cancellation response:', data))
            .catch(err => console.error('Error sending backend cancellation:', err));
        } else {
            console.log("No current analysis ID to send cancellation for.");
        }

        // 4. Reset paste tracking state (might be relevant if pause happens during paste-delete window)
        lastPasteInfo = null;

        // 5. Update UI (e.g., set phase to idle) - This might be done by the caller
        updatePhaseIndicator('idle');
        isSequentialAnalysisRunning = false; // Reset sequential flag if it was running
    }


    // --- Sequential Analysis Function (Modified for Mode) ---
    let isSequentialAnalysisRunning = false; // Flag to prevent overlap
    async function analyzeSequentially(text, audience, contextAwarenessEnabled, mode = 'full') { // Added mode parameter
        // Always use the currentAnalysisMode if no specific mode is passed,
        // or if the passed mode is the default 'full', prefer currentAnalysisMode.
        const effectiveMode = (mode === 'full' && currentAnalysisMode) ? currentAnalysisMode : (mode || currentAnalysisMode || 'best');
        isSequentialAnalysisRunning = true; // Set flag when starting
        console.log(`%c[analyzeSequentially] Called. Initial mode: ${mode}, Effective mode: ${effectiveMode}`, 'color: green');
        // --- Abort previous analysis if any ---
        if (currentAbortController) {
            console.log(`[Seq] Aborting previous analysis ID: ${currentAnalysisId} (requested mode: ${mode})`); // DEBUG
            currentAbortController.abort();
            // Note: isSequentialAnalysisRunning flag might still be true briefly,
            // but the new AbortController should prevent interference.
        }
        // --- Setup new analysis tracking ---
        currentAnalysisId = crypto.randomUUID();
        currentAbortController = new AbortController();
        const analysisId = currentAnalysisId; // Local copy for this run
        const signal = currentAbortController.signal;
        console.log("[Seq] Starting analysis ID:", analysisId);


        // if (isSequentialAnalysisRunning) {
        //     console.log("[Seq] Analysis already running, skipping new request.");
        //     return; // Keep this check? Maybe not needed with AbortController
        // }
        // Cancel any pending standard analysis before starting sequential
        debouncedAnalyzeAndHighlight.cancel();
        isSequentialAnalysisRunning = true; // Still useful to prevent *starting* multiple streams?
        // console.log("Starting sequential analysis..."); // Redundant with ID log
        // if (complexityLoadingEl) complexityLoadingEl.classList.remove('hidden'); // REMOVE old loading bar
        updatePhaseIndicator('fast'); // <<< SET Phase Indicator to 'fast' (Cyan)

        // --- REMOVED: Clear existing highlights and enhancements before sequential analysis ---
        // quill.formatText(0, quill.getLength(), 'background', false, 'api');
        // quill.formatText(0, quill.getLength(), 'underline', false, 'api');
        // clearLlmEnhancements();
        // --- REMOVED: Clear the document map as well ---
        // if (documentMapContainer) documentMapContainer.innerHTML = '';
        // --- REMOVED: Reset overall complexity meter and scores ---
        // updateComplexityMeter(null); // Reset meter
        // updateReadabilityScores(null); // Reset scores


        const requestBody = {
            text: text,
            target_audience: audience,
            context_awareness_enabled: contextAwarenessEnabled,
            analysisId: analysisId, // <<< Add analysisId
            // Mode is NOT sent to /analyze_sequential itself, only to the final /analyze call
        };
        console.log("[Seq] Sending sequential request (body excludes mode):", requestBody); // DEBUG

        let sequentialStreamCompleted = false; // Flag to track if stream finished ok

        try {
            const response = await fetch('/analyze_sequential', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestBody),
                signal: signal // <<< Pass abort signal
            });

            if (!response.ok) {
                let errorMsg = `HTTP error! status: ${response.status}`;
                try {
                    const errorData = await response.json();
                    errorMsg = errorData.error || errorMsg;
                } catch (e) { /* Ignore parsing error */ }
                throw new Error(errorMsg);
            }

            const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
            let buffer = '';
            const sentenceResults = []; // Store results for final overall calculation
            let loopIterations = 0; // DEBUG

            console.log("[Seq] Starting while(true) loop for stream processing."); 
            while (true) {
                loopIterations++; 
                console.log(`[Seq] Loop iteration: ${loopIterations}. Top of loop.`); // DEBUG
                
                if (signal.aborted) {
                    console.log(`[Seq] Abort detected (ID: ${analysisId}). Iteration: ${loopIterations}.`); 
                    throw new DOMException('Aborted by user', 'AbortError'); 
                }

                console.log(`[Seq] Iteration: ${loopIterations}. About to call reader.read().`); // DEBUG
                const { value, done } = await reader.read();
                console.log(`[Seq] Iteration: ${loopIterations}. reader.read() returned. done=${done}, value type=${typeof value}, value length=${value?.length ?? 'N/A'}.`); // DEBUG

                if (done) {
                    console.log(`[Seq] Stream reported done. Iteration: ${loopIterations}.`); 
                    sequentialStreamCompleted = true; 
                    break; 
                }

                buffer += value;
                // Process lines from the buffer
                const lines = buffer.split('\n');
                buffer = lines.pop(); // Keep the last incomplete line in buffer

                for (const line of lines) {
                    if (line.trim()) {
                        try {
                            const sentenceResult = JSON.parse(line);
                            // --- Check for cancellation message from stream ---
                            if (sentenceResult.status === 'cancelled') {
                                console.log(`[Seq] Cancellation signal received from stream (ID: ${analysisId}).`);
                                // Potentially update UI to reflect cancellation more clearly
                                throw new DOMException('Cancelled by backend', 'AbortError'); // Treat as abort
                            }
                            console.log(`[Seq] Received sentence ${sentenceResult.index}:`, sentenceResult); // DEBUG

                            // Store the result
                            sentenceResults.push(sentenceResult);

                            // Apply statistical highlighting for the sentence (Incremental Application)
                            if (showHighlighting && sentenceResult.score !== undefined) {
                                const color = getDynamicHighlightColor(sentenceResult.score, currentSensitivityLevel);
                                const bgColor = complexityBackgrounds[color] || complexityBackgrounds['gray'];
                                const startIndex = sentenceResult.start;
                                const endIndex = sentenceResult.end;
                                const length = endIndex - startIndex;
                                if (startIndex !== undefined && length > 0) {
                                    console.log(`[Seq] Applying background ${color} to sentence ${sentenceResult.index} [${startIndex}-${endIndex}]`); // DEBUG
                                    quill.formatText(startIndex, length, 'background', bgColor, 'api');
                                    console.log(`[Seq] Applied background for sentence ${sentenceResult.index}`); // DEBUG

                                    // Underline is NOT applied incrementally here to avoid flickering.
                                    // It will be applied correctly in the final pass.
                                } else {
                                     console.warn(`[Seq] Invalid indices for sequential highlighting: start=${startIndex}, end=${endIndex}`);
                                }
                            }

                            // Apply LLM enhancement highlighting if enabled - REMOVED

                            // Incrementally update the visual document map
                            if (documentMapContainer && sentenceResult.score !== undefined) {
                                console.log(`[Seq] Updating map for sentence ${sentenceResult.index}`); // DEBUG
                                const segment = document.createElement('div');
                                segment.classList.add('map-segment');
                                segment.dataset.sentenceIndex = sentenceResult.index;

                                const heightPercent = Math.min(100, Math.max(5, (sentenceResult.score || 0) * 60 + 5));
                                segment.style.height = `${heightPercent}%`;

                                const colorName = getDynamicHighlightColor(sentenceResult.score, currentSensitivityLevel);
                                const colorClass = mapSegmentColors[colorName] || mapSegmentColors['gray'];
                                segment.classList.add(colorClass);

                                segment.title = `Sentence ${sentenceResult.index + 1}: Score ${sentenceResult.score.toFixed(2)}`;

                                documentMapContainer.appendChild(segment);
                                // Re-apply goal indicator visibility class to the map container
                                applyGoalIndicatorVisibility();
                            }

                            // REMOVED artificial delay


                        } catch (parseError) {
                            console.error('[Seq] Error parsing streamed JSON:', parseError, 'Line:', line);
                        }
                    }
                }
            } // End while loop

            console.log(`[Seq] Exited while(true) loop. Iterations: ${loopIterations}. sequentialStreamCompleted: ${sequentialStreamCompleted}`); // DEBUG
            
            if (buffer.trim()) {
                 console.log("[Seq] Processing remaining buffer content after loop."); // DEBUG
                 try {
                    const sentenceResult = JSON.parse(buffer);
                    console.log("[Seq] Received final buffer result:", sentenceResult); // DEBUG
                    sentenceResults.push(sentenceResult);
                    // Apply highlighting and map update for the last sentence if needed
                    if (showHighlighting && sentenceResult.score !== undefined) {
                       const color = getDynamicHighlightColor(sentenceResult.score, currentSensitivityLevel);
                       const bgColor = complexityBackgrounds[color] || complexityBackgrounds['gray'];
                       const startIndex = sentenceResult.start;
                       const endIndex = sentenceResult.end;
                       const length = endIndex - startIndex;
                       if (startIndex !== undefined && length > 0) {
                            console.log(`[Seq] Applying background ${color} to FINAL sentence ${sentenceResult.index} [${startIndex}-${endIndex}]`); // DEBUG
                           quill.formatText(startIndex, length, 'background', bgColor, 'api');
                       }
                    }
                    // Apply LLM enhancement highlighting if enabled - REMOVED

                      if (documentMapContainer && sentenceResult.score !== undefined) {
                          console.log(`[Seq] Updating map for FINAL sentence ${sentenceResult.index}`); // DEBUG
                        const segment = document.createElement('div');
                        segment.classList.add('map-segment');
                        segment.dataset.sentenceIndex = sentenceResult.index;

                        const heightPercent = Math.min(100, Math.max(5, (sentenceResult.score || 0) * 60 + 5));
                        segment.style.height = `${heightPercent}%`;

                        const colorName = getDynamicHighlightColor(sentenceResult.score, currentSensitivityLevel);
                        const colorClass = mapSegmentColors[colorName] || mapSegmentColors['gray'];
                        segment.classList.add(colorClass);

                        segment.title = `Sentence ${sentenceResult.index + 1}: Score ${sentenceResult.score.toFixed(2)}`;

                        documentMapContainer.appendChild(segment);
                         applyGoalIndicatorVisibility();
                    }

                 } catch (parseError) {
                    console.error('[Seq] Error parsing remaining buffer JSON:', parseError, 'Buffer:', buffer);
                 }
            } else {
                console.log("[Seq] No remaining buffer content after loop."); // DEBUG
            }

            console.log("[Seq] Sequential analysis stream finished. (This is the line before final fetch check)"); // DEBUG

            // --- Perform Final Overall Analysis Update (only if stream completed and not aborted) ---
            if (sequentialStreamCompleted && !signal.aborted) {
                console.log(`[Seq] Fetching final overall analysis (ID: ${analysisId})...`); 
                updatePhaseIndicator('full'); // <<< SET Phase Indicator to 'full' (Yellow) - Indicates fetching

                if (signal.aborted) {
                     console.log(`[Seq] Abort detected before final /analyze fetch (ID: ${analysisId}).`);
                     throw new DOMException('Aborted by user', 'AbortError');
                }

                const finalRequestBody = {
                    text: text, 
                    target_audience: audience, 
                    context_awareness_enabled: contextAwarenessEnabled, 
                    analysisId: analysisId, 
                    mode: effectiveMode 
                };
                console.log(`[Seq] Sending final /analyze request (ID: ${analysisId}, mode: ${effectiveMode}):`, finalRequestBody);
                const finalAnalysisResponse = await fetch('/analyze', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(finalRequestBody), 
                    signal: signal 
                });

                updatePhaseIndicator('processing_overall');

                if (!finalAnalysisResponse.ok) {
                      updatePhaseIndicator('error'); 
                      let errorMsg = `HTTP error! status: ${finalAnalysisResponse.status} during final analysis.`;
                      // If 429, message from backend is already specific in error.error
                      if (finalAnalysisResponse.status !== 429) {
                        try {
                           const errorData = await finalAnalysisResponse.json();
                          errorMsg = errorData.error || errorMsg;
                       } catch (e) { /* Ignore parsing error */ }
                      }
                     console.error('Error fetching final analysis:', errorMsg);
                     updateComplexityMeter({level: 0, description: "Final analysis error"});
                     updateReadabilityScores({readability_scores: null, target_readability_scores: currentAnalysisData?.target_readability_scores});
                     // Refresh limits even on error, in case a slot was consumed before error (e.g. backend logic error after rate check)
                     // However, 429 specifically means no slot was consumed by *this* request.
                     if (finalAnalysisResponse.status !== 429) {
                        fetchAndApplyRateLimits();
                     }

             } else {
                    const finalAnalysisData = await finalAnalysisResponse.json();
                    
                    // ADDED: Refresh rate limits after successful final /analyze call in sequential
                    if (finalAnalysisResponse.status !== 429) { // Should not be 429 if response.ok was true
                        fetchAndApplyRateLimits();
                    }

                    if (finalAnalysisData?.overall_level?.description === "Analysis cancelled") {
                         console.log(`[Seq] Final /analyze call returned cancelled status (ID: ${analysisId}).`);
                         // Update UI to reflect cancellation
                         updateComplexityMeter(finalAnalysisData.overall_level);
                         updateReadabilityScores(null); // Clear scores
                         // clearLlmEnhancements(); // Call REMOVED
                         if (analysisTimeEl) analysisTimeEl.textContent = 'Cancelled';
                         if (documentMapContainer) documentMapContainer.innerHTML = ''; // Clear map
                         // Throw abort error to prevent 'complete' state in finally
                         throw new DOMException('Cancelled by backend', 'AbortError');
                    } else {
                        currentAnalysisData = finalAnalysisData; // Update stored analysis data with full results
                        console.log("Received final analysis data:", currentAnalysisData); // DEBUG

                        updateComplexityMeter(currentAnalysisData);
                        updateReadabilityScores(currentAnalysisData);

                        // --- Normalize data for final highlighting and map ---
                        let itemsForFinalHighlightingAndMap = [];
                        if (currentAnalysisData) {
                            // Prioritize .sentences if it's an array, as final /analyze calls (even for "fast" mode)
                            // seem to return detailed sentence data in the .sentences field.
                            if (Array.isArray(currentAnalysisData.sentences)) {
                                itemsForFinalHighlightingAndMap = currentAnalysisData.sentences;
                            } else if (Array.isArray(currentAnalysisData.results)) { // Fallback to .results if .sentences isn't there
                                itemsForFinalHighlightingAndMap = currentAnalysisData.results;
                            } else {
                                console.warn(`[Seq-Final] Neither 'sentences' nor 'results' array is valid in the final analysis data (mode: ${currentAnalysisData.mode}).`);
                            }
                        }
                        // --- End normalization ---

                        // Re-apply highlighting and map to ensure underlines and final state are correct
                        applyStatisticalHighlighting(itemsForFinalHighlightingAndMap); // Use normalized items
                        const finalMapData = currentAnalysisData ? { ...currentAnalysisData, results: itemsForFinalHighlightingAndMap } : { results: [] };
                        updateDocumentMap(finalMapData); // Use normalized items for map

                         isOverallScoreOutOfBounds = checkIfOutOfBounds(
                            currentAnalysisData?.readability_scores,
                            currentAnalysisData?.target_readability_scores
                        );
                         applyGoalIndicatorVisibility(); // Ensure goal indicators are correctly applied based on final state

                         // Re-apply LLM enhancements based on final data - REMOVED
                    }
                }
            } else if (signal.aborted) {
                 console.log(`[Seq] Skipping final /analyze call because analysis was aborted (ID: ${analysisId}).`);
            } else {
                 console.log(`[Seq] Skipping final /analyze call because sequential stream did not complete successfully (ID: ${analysisId}).`);
                 // Potentially set an error state if stream failed without abort
                 if (!signal.aborted) { // Only set error if not aborted
                     updatePhaseIndicator('error');
                 }
            }


        } catch (error) {
             if (error.name === 'AbortError') {
                 console.log(`Sequential analysis fetch aborted or cancelled by backend (ID: ${analysisId}).`);
                 updatePhaseIndicator('idle'); 
                 if (!isAnalysisPaused) { // If it was running and got aborted
                    isAnalysisPaused = true;
                    updateAnalysisButtonState();
                 }
             } else {
                 console.error('Error during sequential analysis:', error);
                 updateComplexityMeter({level: 0, description: "Sequential analysis error"});
                 updateReadabilityScores(null); 
                 if (analysisTimeEl) analysisTimeEl.textContent = 'Error';
                 if (documentMapContainer) documentMapContainer.innerHTML = ''; 
                 updatePhaseIndicator('error'); 
                 isAnalysisPaused = true; // << SET PAUSED ON ERROR
                 updateAnalysisButtonState(); // << UPDATE BUTTON
             }
        } finally {
            isSequentialAnalysisRunning = false; 

            const wasAborted = currentAbortController?.signal.aborted ?? false; 

            if (!wasAborted && currentAnalysisData && text.trim()) { 
                 updatePhaseIndicator('complete'); 
                 isAnalysisPaused = true; // << SET PAUSED ON COMPLETION
                 updateAnalysisButtonState(); // << UPDATE BUTTON
            } else if (!wasAborted && !text.trim()) {
                 updatePhaseIndicator('idle'); 
                 isAnalysisPaused = true; // << SET PAUSED (e.g. if text cleared)
                 updateAnalysisButtonState(); // << UPDATE BUTTON
            } else if (wasAborted && !isAnalysisPaused) {
                 // If aborted, and it wasn't already paused by the AbortError catch block
                 isAnalysisPaused = true;
                 updateAnalysisButtonState();
            }
            
            if (analysisId === currentAnalysisId) { 
                 currentAnalysisId = null;
                 currentAbortController = null;
                 console.log(`[Seq] Cleared tracking for analysis ID: ${analysisId}`);
            } else {
                 console.log(`[Seq] Finally block for ${analysisId}, but current tracked ID is ${currentAnalysisId}. Not clearing.`);
            }
        }
    }

    // --- Paste Event Listener ---
    // Add a listener to the editor container for paste events
    // Custom paste handler removed - Quill's configured clipboard module handles plain text pasting now.


    // Define debounced sequential analysis function
    const debouncedAnalyzeSequentially = debounce(analyzeSequentially, 750);
 
    // --- Text Change Listener ---
    quill.on('text-change', (delta, oldDelta, source) => {
        if (source === 'user') {
            updateStats(); // Update word/sentence/char counts on any user change

            const ops = delta.ops;
            let isSignificantChange = false;
            let isPaste = false;
            let insertedText = '';
            let deleteLength = 0;

            if (ops && ops.length === 1) {
                if (ops[0].insert && ops[0].insert.length > 1) {
                    isSignificantChange = true;
                    insertedText = ops[0].insert;
                    if (ops[0].insert.length >= PASTE_LENGTH_THRESHOLD) {
                        isPaste = true;
                        lastPasteInfo = { timestamp: Date.now(), length: ops[0].insert.length };
                        console.log(`Paste detected: length ${lastPasteInfo.length}`);
                    }
                } else if (ops[0].delete && ops[0].delete > 1) {
                    isSignificantChange = true;
                    deleteLength = ops[0].delete;
                } 
            } else if (ops && ops.length > 1) { 
                isSignificantChange = true;
                ops.forEach(op => {
                    if (op.insert) insertedText += op.insert;
                    if (op.delete) deleteLength += op.delete;
                });
                if (insertedText.length >= PASTE_LENGTH_THRESHOLD) {
                    isPaste = true;
                    lastPasteInfo = { timestamp: Date.now(), length: insertedText.length };
                    console.log(`Multi-op paste detected: length ${lastPasteInfo.length}`);
                }
            }

            // --- Paste-delete detection to cancel an ONGOING analysis ---
            if (isSignificantChange && lastPasteInfo && deleteLength > 0 && !isAnalysisPaused) { 
                const timeDiff = Date.now() - lastPasteInfo.timestamp;
                const lengthRatio = deleteLength / lastPasteInfo.length;
                console.log(`Delete detected: length ${deleteLength}, time since paste: ${timeDiff}ms, paste length: ${lastPasteInfo.length}, ratio: ${lengthRatio.toFixed(2)}`);

                if (timeDiff < PASTE_DELETE_THRESHOLD_MS && lengthRatio >= DELETE_MATCH_RATIO) {
                    console.log(`%cPaste-delete detected during active analysis! Cancelling analysis ID: ${currentAnalysisId}`, 'color: orange; font-weight: bold;');
                    cancelCurrentAnalysis(); // This will also set isAnalysisPaused = true and update button state indirectly if analysis was running.
                }
            }
            lastPasteInfo = isPaste ? lastPasteInfo : null;

            // --- Optional: Initial analysis on significant paste when PAUSED ---
            if (false && isPaste && isAnalysisPaused && insertedText.length > PASTE_LENGTH_THRESHOLD) {
                console.log("%cSignificant paste detected while paused. Triggering initial analysis...", 'color: blueviolet');
                isAnalysisPaused = false; // Temporarily unpause
                updateAnalysisButtonState(); // Show it's running
                
                const currentText = quill.getText();
                const contextEnabled = contextAwarenessToggle ? contextAwarenessToggle.checked : false;
                // Analysis will auto-pause on completion due to changes in analyzeAndHighlight/analyzeSequentially
                if (currentAnalysisMode === 'fast') {
                    analyzeSequentially(currentText, currentTargetAudience, contextEnabled, 'fast');
                } else { 
                    analyzeAndHighlight(false, currentAnalysisMode);
                }
            } 
            // --- REMOVED: Automatic re-analysis on general significant text changes ---
            /*
            if (isSignificantChange && !isAnalysisPaused && !cancelled) { // 'cancelled' was for paste-delete
                console.log(`%cSignificant text change detected (source: ${source}). Triggering analysis with mode: ${currentAnalysisMode}.`, 'color: orange');
                const currentText = quill.getText();
                const contextEnabled = contextAwarenessToggle ? contextAwarenessToggle.checked : false;

                if (currentAnalysisMode === 'fast') {
                    debouncedAnalyzeSequentially(currentText, currentTargetAudience, contextEnabled, 'fast');
                } else { // 'better' or 'best'
                    debouncedAnalyzeAndHighlight(false, currentAnalysisMode);
                }
            } else if (source === 'user' && !isSignificantChange && !isAnalysisPaused && !cancelled) {
                // console.log("Minor text change, only updating stats.");
            }
            */
        }
    });

    // --- Selection Change Listener (for Synonyms) ---
    quill.on('selection-change', (range, oldRange, source) => {
        // We only care about user-driven selection changes for triggering the tooltip
        if (source === 'user') {
            if (range && range.length > 0) {
                // Text is selected, show the tooltip
                // Add a small debounce here to prevent flickering
                debouncedShowSynonymTooltip(range); // Use a debounced version
            } else if (!range || range.length === 0) {
                // Selection cleared or lost focus, hide the tooltip
                // Cancel any pending debounced show calls
                debouncedShowSynonymTooltip.cancel(); // Cancel pending show
                if (synonymTooltip.state.isVisible) {
                    synonymTooltip.hide();
                    currentSynonymRange = null; // Clear stored range
                }
            }
        } else if ((!range || range.length === 0) && synonymTooltip.state.isVisible) {
            // Also hide if selection is cleared programmatically (source === 'api' or 'silent')
            // Cancel any pending debounced show calls
            debouncedShowSynonymTooltip.cancel(); // Cancel pending show
            synonymTooltip.hide();
            currentSynonymRange = null;
        }
    });

    // Define a debounced version of showSynonymTooltip
    const debouncedShowSynonymTooltip = debounce(showSynonymTooltip, 50); // 50ms debounce

    // --- NEW: Custom Target Audience Dropdown Listeners ---
    if (targetAudienceButton && targetAudienceSelected && targetAudienceOptions) {
        // 1. Toggle options list visibility on button click
        targetAudienceButton.addEventListener('click', (event) => {
            event.stopPropagation(); // Prevent click from immediately closing via document listener
            targetAudienceOptions.classList.toggle('hidden');
        });

        // 2. Handle option selection (delegated listener on options container)
        targetAudienceOptions.addEventListener('click', (event) => {
            const link = event.target.closest('a');
            if (link && link.dataset.value) {
                event.preventDefault(); // Prevent default link navigation
                const newValue = link.dataset.value;
                const newText = link.textContent;

                // Update display and state
                targetAudienceSelected.textContent = newText;
                currentTargetAudience = newValue;

                // Hide options list
                targetAudienceOptions.classList.add('hidden');

                console.log(`Target Audience changed to: ${currentTargetAudience}`); // DEBUG

                // Trigger re-analysis if not paused
                if (!isAnalysisPaused) {
                    analyzeAndHighlight(false); // Use standard full analysis
                } else {
                    console.log("Audience changed: Analysis paused, skipping trigger.");
                }
            }
        });

        // 3. Close dropdown when clicking outside
        document.addEventListener('click', (event) => {
            if (!targetAudienceButton.contains(event.target) && !targetAudienceOptions.contains(event.target)) {
                targetAudienceOptions.classList.add('hidden');
            }
        });

        // Set initial state from the default display value (optional, could also read from button text)
        currentTargetAudience = targetAudienceSelected.textContent || 'Standard'; // Fallback

    } else {
        console.warn("Custom target audience dropdown elements not found.");
    }
    // --- END NEW Custom Dropdown Listeners ---

    // OLD Target Audience Select Listener (Commented out/Removed)
    /*
    if (targetAudienceSelect) {
        targetAudienceSelect.addEventListener('change', (event) => {
            currentTargetAudience = event.target.value;
            if (!isAnalysisPaused) {
                analyzeAndHighlight(false);
            } else {
                 console.log("Audience changed: Analysis paused, skipping trigger.");
            }
        });
        currentTargetAudience = targetAudienceSelect.value; // Initial state
    } else {
        console.warn("Target audience select element not found.");
    }
    */

    // Toggle Statistical Highlighting Listener
    if (toggleHighlighting) {
        toggleHighlighting.addEventListener('change', (event) => {
            showHighlighting = event.target.checked;
            // Immediately apply/remove statistical highlighting based on current data
            applyStatisticalHighlighting(currentAnalysisData?.results || []);
        });
        showHighlighting = toggleHighlighting.checked; // Initial state
    } else {
         console.warn("Toggle statistical highlighting element not found.");
         showHighlighting = true; // Default
    }

    // Toggle Goal Indicators Listener
    if (toggleGoalIndicators) {
        // Set initial state from checkbox value on load FIRST
        showGoalIndicators = toggleGoalIndicators.checked;

        toggleGoalIndicators.addEventListener('change', (event) => {
            showGoalIndicators = event.target.checked;
            applyGoalIndicatorVisibility(); // Apply visibility changes
            // Re-apply statistical highlighting to add/remove underlines based on current data
            applyStatisticalHighlighting(currentAnalysisData?.results || []);
        });
        // Initial state set above
    } else {
        console.warn("Toggle goal indicators element not found.");
        showGoalIndicators = true; // Default
    }
 
    // --- NEW: Rewrite Context Toggle Listener ---
    const rewriteContextToggle = document.getElementById('rewrite-context-toggle');
    if (rewriteContextToggle) {
        // Initial state from checkbox (assuming default is unchecked/false)
        useFullRewriteContext = rewriteContextToggle.checked;
        console.log(`Initial Rewrite Context Mode: ${useFullRewriteContext ? 'Full' : 'Partial'}`); // DEBUG
 
        rewriteContextToggle.addEventListener('change', (event) => {
            useFullRewriteContext = event.target.checked;
            console.log(`Rewrite Context Mode changed to: ${useFullRewriteContext ? 'Full' : 'Partial'}`); // DEBUG
            // No re-analysis needed, this only affects future rewrite requests
        });
    } else {
        console.warn("Rewrite context toggle element (#rewrite-context-toggle) not found.");
        useFullRewriteContext = false; // Default if element is missing
    }
    // --- END NEW ---
 
    // --- Context Awareness Toggle Listener ---
    if (contextAwarenessToggle && goalContainer) { // Removed goalInput from check
        // Initial state setup
        contextAwarenessEnabled = contextAwarenessToggle.checked;
        // Hide the container itself if the toggle is off initially
        goalContainer.style.display = contextAwarenessEnabled ? 'block' : 'none';
        // goalInput.disabled = !contextAwarenessEnabled; // REMOVED
        // currentGoalText = goalInput.value; // REMOVED

        contextAwarenessToggle.addEventListener('change', (event) => {
            contextAwarenessEnabled = event.target.checked;
            // Hide the container itself if the toggle is off
            goalContainer.style.display = contextAwarenessEnabled ? 'block' : 'none';
            // goalInput.disabled = !contextAwarenessEnabled; // REMOVED
            console.log(`Context Awareness Toggled: ${contextAwarenessEnabled}`); // DEBUG

            // Trigger a re-analysis when toggled to apply/clear enhancements
            // Use standard analysis for toggle changes
            // Only trigger if analysis is not paused
            if (!isAnalysisPaused) { // <<< ADDED PAUSE CHECK
                 analyzeAndHighlight(false); // Use standard full analysis here
            } else {
                 console.log("Context Awareness toggled: Analysis paused, skipping trigger.");
            }

            // Explicitly clear enhancements if toggled OFF - REMOVED (no longer applying enhancements)
        });

        // REMOVED goalInput listener

    } else {
        console.error("Context awareness toggle or container element not found!"); // Updated error message
    }

    // --- Complexity Sensitivity Slider Listener ---
    if (sensitivitySlider) { // Removed check for sensitivityLabel
        // Initial state update on load
        const initialSliderValue = parseInt(sensitivitySlider.value, 10);
        currentSensitivityLevel = initialSliderValue; // Ensure state matches initial value

        sensitivitySlider.addEventListener('input', (event) => {
            const newLevel = parseInt(event.target.value, 10);
            currentSensitivityLevel = newLevel;
            // Removed label update: sensitivityLabel.textContent = `Level ${newLevel}: ${getSensitivityDescription(newLevel)}`;
            console.log(`Sensitivity changed to: ${currentSensitivityLevel}`); // DEBUG

            // Re-apply highlighting and map colors based on the new sensitivity
            // Only do this if we have existing analysis data to work with
            if (currentAnalysisData) {
                console.log("Re-applying visuals with new sensitivity..."); // DEBUG
                // Ensure these functions use the updated currentSensitivityLevel
                applyStatisticalHighlighting(currentAnalysisData.results || []);
                updateDocumentMap(currentAnalysisData);
            } else {
                 console.log("No current analysis data, skipping visual update on sensitivity change."); // DEBUG
            }
        });
    } else {
        console.warn("Complexity sensitivity slider element not found."); // Updated warning message
    }
    // --- End Complexity Sensitivity Slider Listener ---


    // Add Tooltip for Context Awareness Info Icon (Updated Content)
    if (contextAwarenessInfo && typeof tippy === 'function') {
        tippy(contextAwarenessInfo, {
            content: `<div class='text-left p-1 max-w-xs'>
                        <strong class='block mb-1 text-gray-100'>Context Awareness (via DeepSeek)</strong>
                        <p class='text-xs text-gray-300 mb-1'>When enabled, uses the configured LLM (currently DeepSeek) to enhance synonym suggestions based on the selected 'Target Audience' profile.</p>
                        <ul class='list-disc list-inside text-xs space-y-0.5 text-gray-400'>
                            <li>Recommends the most suitable synonym from the provided list based on sentence context and audience profile.</li>
                        </ul>
                        <p class='text-xs text-gray-500 mt-1'>Requires a configured DeepSeek API Key and may incur costs.</p>
                      </div>`,
            allowHTML: true,
            placement: 'top-start',
            theme: 'tippy-dark',
        });
    }


    // --- Initial Load ---
    updateStats();
    applyGoalIndicatorVisibility(); // Apply initial visibility
    // Initial analysis call (will now include context awareness state if enabled by default)
    // Use standard analysis on initial load
    // Only trigger if analysis is not paused initially (it starts paused, so this won't run)
    if (!isAnalysisPaused) { // <<< ADDED PAUSE CHECK
        setTimeout(() => analyzeAndHighlight(false), 100); // Use standard full analysis here
    } else {
        console.log("Initial load: Analysis starts paused.");
        // Ensure UI reflects paused state (e.g., meter empty, scores empty)
        updateComplexityMeter(null);
        updateReadabilityScores(null);
        updateDocumentMap(null);
        updatePhaseIndicator('idle'); // Ensure indicator is idle
    }


    // --- NEW: Analysis Control Listeners (Replaces old toggle listener) ---
    // Functions for specific analysis modes
    function startFastAnalysisOnly() {
        console.log("%cTriggering Fast Analysis Only...", 'color: orange; font-weight: bold;');
        if (isAnalysisPaused) { // Ensure we only start if paused
            isAnalysisPaused = false;
            updateAnalysisButtonState(); // Update UI immediately
            const currentText = quill.getText();
            const contextEnabled = contextAwarenessToggle ? contextAwarenessToggle.checked : false;
            // Call sequential analysis, explicitly passing 'fast' mode for the *final* /analyze call
            analyzeSequentially(currentText, currentTargetAudience, contextEnabled, 'fast');
        } else {
            console.warn("Fast Analysis Only requested but analysis is already running.");
        }
    }

    function startFullAnalysisOnly() {
        console.log("%cTriggering Full Analysis Only...", 'color: purple; font-weight: bold;');
         if (isAnalysisPaused) { // Ensure we only start if paused
            isAnalysisPaused = false;
            updateAnalysisButtonState(); // Update UI immediately
            // Call the standard full analysis function directly, skipping sequential streaming
            // Pass 'full' mode explicitly (or rely on default)
            analyzeAndHighlight(false, 'full');
        } else {
            console.warn("Full Analysis Only requested but analysis is already running.");
        }
    }

    // Helper to update button/icon visibility based on isAnalysisPaused
    function updateAnalysisButtonState() {
        // Only update elements confirmed to exist
        if (!analysisControlBtn || !playIcon || !pauseIcon) return;

        playIcon.classList.toggle('hidden', !isAnalysisPaused);
        pauseIcon.classList.toggle('hidden', isAnalysisPaused);
        // analysisControlsContainer.classList.toggle('analysis-paused', isAnalysisPaused); // Keep class if needed for styling paused state

        if (isAnalysisPaused) {
            analysisControlBtn.setAttribute('title', 'Start Analysis');
            // Ensure menu is hidden when state changes (running or paused)
            if (analysisOptionsMenu) analysisOptionsMenu.classList.add('hidden');
            if (analysisControlsContainer) analysisControlsContainer.classList.remove('options-visible');
        } else {
            analysisControlBtn.setAttribute('title', 'Pause Analysis');
            // Ensure menu is hidden when state changes (running or paused)
            if (analysisOptionsMenu) analysisOptionsMenu.classList.add('hidden');
            if (analysisControlsContainer) analysisControlsContainer.classList.remove('options-visible');
        }
        // NOTE: analysisExpandBtn visibility is no longer managed here as it's always visible in split button design.
    }


    // Main Play/Pause Button Listener
    if (analysisControlBtn && playIcon && pauseIcon) {
        analysisControlBtn.addEventListener('click', () => {
            isAnalysisPaused = !isAnalysisPaused; // Toggle the state

            updateAnalysisButtonState(); // Update UI elements

            if (isAnalysisPaused) {
                console.log("Analysis Paused (via main button).");
                cancelCurrentAnalysis(); // Cancel any ongoing analysis
            } else {
                console.log(`Analysis Resumed (via main button - mode: ${currentAnalysisMode}).`);
                const currentText = quill.getText();
                const contextEnabled = contextAwarenessToggle ? contextAwarenessToggle.checked : false;
                if (currentAnalysisMode === 'fast') {
                    analyzeSequentially(currentText, currentTargetAudience, contextEnabled, 'fast');
                } else { // 'better' or 'best'
                    analyzeAndHighlight(false, currentAnalysisMode);
                }
            }
        });
    } else {
        console.error("Analysis control button or icons not found!");
    }

    // Expand Button Listener
    if (analysisExpandBtn && analysisOptionsMenu && analysisControlsContainer) {
        analysisExpandBtn.addEventListener('click', (event) => {
            event.stopPropagation(); // Prevent click from closing menu immediately via document listener
            analysisOptionsMenu.classList.toggle('hidden');
            analysisControlsContainer.classList.toggle('options-visible');
        });
    } else {
         console.error("Analysis expand button or options menu not found!");
    }

    // Options Menu Listener (Delegated)
    if (analysisOptionsMenu && analysisControlsContainer) {
        analysisOptionsMenu.addEventListener('click', (event) => {
            const link = event.target.closest('a[data-action]');
            if (link) {
                event.preventDefault();
                const action = link.dataset.action;

                // Hide menu immediately
                analysisOptionsMenu.classList.add('hidden');
                analysisControlsContainer.classList.remove('options-visible');

                if (action === 'fast-only') {
                    startFastAnalysisOnly();
                } else if (action === 'full-only') {
                    startFullAnalysisOnly();
                }
            }
        });

        // Close dropdown when clicking outside
        document.addEventListener('click', (event) => {
            if (!analysisControlsContainer.contains(event.target) && !analysisOptionsMenu.classList.contains('hidden')) {
                 analysisOptionsMenu.classList.add('hidden');
                 analysisControlsContainer.classList.remove('options-visible');
            }
        });

    } else {
         console.error("Analysis options menu not found!");
    }

    // --- Initial State Setup ---
    updateAnalysisButtonState(); // Set initial button state based on isAnalysisPaused (defaults to true)


    // --- Sidebar Toggle Logic ---
    function closeSidebar() {
        if (sidebar && openSidebarBtn) {
            sidebar.classList.remove('right-sidebar-state-open');
            sidebar.classList.add('right-sidebar-state-closed');
            openSidebarBtn.classList.remove('hidden');
        }
    }

    function openSidebar() {
        if (sidebar && openSidebarBtn) {
            sidebar.classList.remove('right-sidebar-state-closed');
            sidebar.classList.add('right-sidebar-state-open');
            openSidebarBtn.classList.add('hidden');
        }
    }

    function closeLeftSidebar() {
        if (leftSidebar && openLeftSidebarBtn) {
            leftSidebar.classList.remove('left-sidebar-state-open');
            leftSidebar.classList.add('left-sidebar-state-closed');
            openLeftSidebarBtn.classList.remove('hidden');
        }
    }

    function openLeftSidebar() {
        if (leftSidebar && openLeftSidebarBtn) {
            leftSidebar.classList.remove('left-sidebar-state-closed');
            leftSidebar.classList.add('left-sidebar-state-open');
            openLeftSidebarBtn.classList.add('hidden');
        }
    }

    if (toggleSidebarBtn) {
        toggleSidebarBtn.addEventListener('click', closeSidebar);
    }

    if (openSidebarBtn) {
        openSidebarBtn.addEventListener('click', openSidebar);
    }

    // Ensure sidebar is open by default
    if (sidebar) {
        sidebar.classList.add('right-sidebar-state-open');
        if (openSidebarBtn) openSidebarBtn.classList.add('hidden');
    }


    // --- Visual Map Hover Listeners ---
    if (documentMapContainer) {
        documentMapContainer.addEventListener('mouseover', (event) => {
            const segment = event.target.closest('.map-segment');
            if (!segment || !segment.dataset.sentenceIndex) return;

            const sentenceIndex = parseInt(segment.dataset.sentenceIndex, 10);
            // Need to get the sentence result from the stored data (currentAnalysisData)
            const result = currentAnalysisData?.results?.[sentenceIndex]; // Safely access results

            if (result && result.start !== undefined && result.end !== undefined) {
                const length = result.end - result.start;
                if (length > 0) {
                    // Apply a temporary highlight class using inline style for simplicity
                    // quill.formatText(result.start, length, 'class', 'highlight-map-hover', 'api');
                    quill.formatText(result.start, length, 'background', 'rgba(255, 255, 0, 0.3)', 'api'); // Temporary yellow highlight
                }
            }
        });

        documentMapContainer.addEventListener('mouseout', (event) => {
            const segment = event.target.closest('.map-segment');
            if (!segment || !segment.dataset.sentenceIndex) return;

            const sentenceIndex = parseInt(segment.dataset.sentenceIndex, 10);
             // Need to get the sentence result from the stored data (currentAnalysisData)
            const result = currentAnalysisData?.results?.[sentenceIndex]; // Safely access results

            if (result && result.start !== undefined && result.end !== undefined) {
                const length = result.end - result.start;
                if (length > 0) {
                    // Remove the temporary highlight by re-applying the original statistical highlight
                    // This avoids clearing Gemini highlights accidentally
                    // quill.formatText(result.start, length, 'class', false, 'api');
                    const originalColorName = getDynamicHighlightColor(result.score, currentSensitivityLevel);
                    const originalBgColor = complexityBackgrounds[originalColorName] || complexityBackgrounds['gray'];
                    // Only re-apply background if statistical highlighting is enabled
                    if (showHighlighting) {
                        quill.formatText(result.start, length, 'background', originalBgColor, 'api');
                    } else {
                        quill.formatText(result.start, length, 'background', false, 'api'); // Clear if highlighting is off
                    }
                    // Also need to consider Gemini highlights here if they overlap... this gets complex.
                    // For now, the temporary highlight might overwrite Gemini, and mouseout restores statistical.
                }
            }
        });

        // Add click listener to select text in editor
        documentMapContainer.addEventListener('click', (event) => {
            const segment = event.target.closest('.map-segment');
            if (!segment || !segment.dataset.sentenceIndex) return;

            const sentenceIndex = parseInt(segment.dataset.sentenceIndex, 10);
             // Need to get the sentence result from the stored data (currentAnalysisData)
            const result = currentAnalysisData?.results?.[sentenceIndex]; // Safely access results

            if (result && result.start !== undefined && result.end !== undefined) {
                const length = result.end - result.start;
                if (length > 0) {
                    // Set Quill's selection to highlight the sentence
                    quill.setSelection(result.start, length, 'user');
                    // Optional: Scroll the editor to the selection
                    quill.scrollIntoView();
                }
            }
        });
    }

    // --- Context Menu Event Listener REMOVED ---


    // --- Expose resources for rewrite_handler.js ---
    window.typecomplexApp = {
        quill: quill,
        contextMenuTooltip: contextMenuTooltip,
        getCurrentAnalysisData: () => currentAnalysisData,
        getCurrentTargetAudience: () => currentTargetAudience,
        getUseFullRewriteContext: () => useFullRewriteContext,
        // Expose helper for getting bounds if needed by rewrite handler
        getQuillBounds: (index, length) => quill.getBounds(index, length),
        // --- NEW: Expose function to trigger analysis ---
        triggerAnalysis: () => {
            console.log("External triggerAnalysis called."); // DEBUG
            if (isAnalysisPaused) {
                console.log("Analysis is paused, triggerAnalysis ignored.");
                return; // Don't trigger if paused
            }
            const currentText = quill.getText();
            const audience = currentTargetAudience;
            const contextEnabled = contextAwarenessToggle ? contextAwarenessToggle.checked : false;
            // Use the debounced sequential analysis (default 'full' mode)
            debouncedAnalyzeSequentially(currentText, audience, contextEnabled);
        },
        // NEW: Function to call after a rewrite attempt to refresh limits
        refreshRateLimitsAfterRewrite: () => {
            fetchAndApplyRateLimits();
        }
    };
    console.log("typecomplexApp object exposed on window."); // DEBUG

    // --- NEW: Left Sidebar Collapse Logic ---
    const leftSidebar = document.getElementById('left-sidebar');
    const toggleLeftSidebarBtn = document.getElementById('toggle-left-sidebar-btn');
    const openLeftSidebarBtn = document.getElementById('open-left-sidebar-btn');
    const mainContentArea = document.getElementById('main-content'); // Assuming your main content area has an ID like 'main-content'

    function openLeftSidebar() {
        if (leftSidebar && openLeftSidebarBtn && toggleLeftSidebarBtn) {
            leftSidebar.classList.remove('left-sidebar-state-closed');
            leftSidebar.classList.add('left-sidebar-state-open');
            openLeftSidebarBtn.classList.add('hidden');
            toggleLeftSidebarBtn.classList.remove('hidden');
            // Optional: Adjust main content margin if it was pushed
            if (mainContentArea) {
                // mainContentArea.style.marginLeft = '18.4rem'; // Or whatever the open width is
            }
        }
    }

    function closeLeftSidebar() {
        if (leftSidebar && openLeftSidebarBtn && toggleLeftSidebarBtn) {
            leftSidebar.classList.remove('left-sidebar-state-open');
            leftSidebar.classList.add('left-sidebar-state-closed');
            toggleLeftSidebarBtn.classList.add('hidden');
            // Delay showing the open button until transition is somewhat complete
            setTimeout(() => {
                if (openLeftSidebarBtn) openLeftSidebarBtn.classList.remove('hidden');
            }, 200); // Slightly less than transition to feel responsive
             // Optional: Adjust main content margin if it was pushed
            if (mainContentArea) {
                // mainContentArea.style.marginLeft = '0';
            }
        }
    }

    if (toggleLeftSidebarBtn) {
        toggleLeftSidebarBtn.addEventListener('click', closeLeftSidebar);
    }

    if (openLeftSidebarBtn) {
        openLeftSidebarBtn.addEventListener('click', openLeftSidebar);
    }

    // Initial state: Ensure sidebar is open by default unless a class is already set by server/HTML
    if (leftSidebar && !leftSidebar.classList.contains('left-sidebar-state-closed') && !leftSidebar.classList.contains('left-sidebar-state-open')) {
        leftSidebar.classList.add('left-sidebar-state-open');
        if(toggleLeftSidebarBtn) toggleLeftSidebarBtn.classList.remove('hidden');
        if(openLeftSidebarBtn) openLeftSidebarBtn.classList.add('hidden');
    } else if (leftSidebar && leftSidebar.classList.contains('left-sidebar-state-closed')){
        // If it's meant to start closed
        if(toggleLeftSidebarBtn) toggleLeftSidebarBtn.classList.add('hidden');
        if(openLeftSidebarBtn) openLeftSidebarBtn.classList.remove('hidden');
    } else {
        // It starts open, ensure buttons are correct
        if(toggleLeftSidebarBtn) toggleLeftSidebarBtn.classList.remove('hidden');
        if(openLeftSidebarBtn) openLeftSidebarBtn.classList.add('hidden');
    }
    // --- END Left Sidebar Collapse Logic ---

    function setAnalysisLoading(isLoading, type = 'editor') { // type can be 'editor' or 'pdf'
        const editorIndicator = document.getElementById('analysis-loading-indicator');
        const pdfStatusElement = document.getElementById('pdf-action-status'); // Use this for PDF loading text
        const complexityLoadingBar = document.getElementById('complexity-loading'); // General loading bar in sidebar

        // Get reference to PDF target audience button for disabling
        const pdfAudienceButton = document.getElementById('pdf-target-audience-button');
        const pdfAnalysisModeButton = document.getElementById('pdf-analysis-mode-button'); // NEW: Get analysis mode button

        if (type === 'editor' && editorIndicator) {
            editorIndicator.classList.toggle('hidden', !isLoading);
        } else if (type === 'pdf' && pdfStatusElement) {
            // For PDF, we use the status text element.
        }

        if (complexityLoadingBar) {
            complexityLoadingBar.classList.toggle('hidden', !isLoading);
        }

        // Disable/Enable relevant buttons during analysis
        if (analysisControlBtn) analysisControlBtn.disabled = isLoading;
        if (analysisExpandBtn) analysisExpandBtn.disabled = isLoading;
        if (targetAudienceButton) targetAudienceButton.disabled = isLoading; // Main editor audience button
        // PDF buttons
        if (textExtractBtn) textExtractBtn.disabled = isLoading;
        if (pdfAnalysisBtn) pdfAnalysisBtn.disabled = isLoading;
        
        // Extra handling for PDF audience button - ensure it gets proper styling when disabled
        if (pdfAudienceButton) {
            pdfAudienceButton.disabled = isLoading;
        }

        // NEW: Handle PDF analysis mode button state
        if (pdfAnalysisModeButton) {
            pdfAnalysisModeButton.disabled = isLoading;
        }
    }

    // --- Function to update all UI elements based on analysis data (Modified) ---
    // ... existing code ...

    // --- PDF Handling Logic ---
    let currentPdfFile = null;
    let currentPdfAnalysisTaskId = null;
    let currentPdfExtractTaskId = null;

    // Function to update PDF action buttons state
    function updatePdfActionButtonsState(isProcessing) {
        if (textExtractBtn) textExtractBtn.disabled = isProcessing;
        if (pdfAnalysisBtn) pdfAnalysisBtn.disabled = isProcessing;
        // Optionally, disable remove button during processing too
        if (pdfRemoveBtn) pdfRemoveBtn.disabled = isProcessing; 
    }

    // Combined function to handle PDF upload and processing initiation
    async function handlePdfProcessing(actionType) {
        if (!currentPdfFile) {
            console.error('No PDF file selected for processing.');
            updatePdfStatus('No PDF file selected.', 'error', actionType);
            return;
        }

        const formData = new FormData();
        formData.append('file', currentPdfFile); // <<< CHANGED 'pdf-file' to 'file'
        formData.append('action', actionType);
        // Get target audience for PDF from the UI
        const selectedPdfAudience = pdfTargetAudienceSelected.dataset.value || 'Standard';
        formData.append('target_audience', selectedPdfAudience);

        // Get analysis mode from the UI
        const selectedPdfAnalysisMode = pdfAnalysisModeSelected.dataset.value || 'better';
        formData.append('analysis_mode', selectedPdfAnalysisMode);

        // Append PDF Overview Page Options
        if (includeOverviewPageCheckbox) {
            formData.append('include_overview_page', includeOverviewPageCheckbox.checked ? 'true' : 'false');
        }
        if (overviewTopXCountInput) {
            formData.append('overview_top_x_count', overviewTopXCountInput.value);
        }
        if (overviewTopXTypeSelect) {
            formData.append('overview_top_x_type', overviewTopXTypeSelect.value);
        }
        if (overviewShowVisualMapCheckbox) {
            formData.append('overview_show_visual_map', overviewShowVisualMapCheckbox.checked ? 'true' : 'false');
        }

        updatePdfStatus(`Starting ${actionType.replace('_', ' ')}...`, 'loading', actionType);
        updatePdfActionButtonsState(true);
        setAnalysisLoading(true, 'pdf'); // Generic PDF loading indicator

        try {
            const response = await fetch('/upload_pdf', {
                method: 'POST',
                body: formData,
            });

            const result = await response.json();

            if (response.ok && result.task_id) {
                updatePdfStatus(`${actionType.replace('_', ' ')} started. Monitoring progress...`, 'info', actionType);
                if (actionType === 'full_analysis') {
                    currentPdfAnalysisTaskId = result.task_id;
                    // No longer show download card immediately, wait for task completion
                    // showCard(pdfDownloadCard, [pdfUploadCard, pdfFileActionsCard]); 
                } else if (actionType === 'extract_text') {
                    currentPdfExtractTaskId = result.task_id;
                }
                pollTaskStatus(result.task_id, actionType); // Start polling for this specific action
            } else {
                // If the error is 429, the backend might send it. Otherwise, general error.
                if (response.status === 429 && result.error) {
                     updatePdfStatus(result.error, 'error', actionType);
                } else {
                    throw new Error(result.error || `Failed to start ${actionType}`);
                }
            }
        } catch (error) {
            console.error(`Error during ${actionType}:`, error);
            updatePdfStatus(`Error: ${error.message}`, 'error', actionType);
            updatePdfActionButtonsState(false);
            setAnalysisLoading(false, 'pdf');
        }
    }

    if (textExtractBtn) {
        textExtractBtn.addEventListener('click', () => {
            handlePdfProcessing('extract_text');
        });
    }

    if (pdfAnalysisBtn) {
        pdfAnalysisBtn.addEventListener('click', () => {
            handlePdfProcessing('full_analysis');
        });
    }

    // --- NEW: Event Listener for Overview Page Options Toggle ---
    if (includeOverviewPageCheckbox && overviewOptionsDetailsDiv) {
        const overviewInputsToToggle = [
            overviewTopXCountInput,
            overviewTopXTypeSelect,
            overviewShowVisualMapCheckbox
        ];

        function toggleOverviewOptions() {
            const isEnabled = includeOverviewPageCheckbox.checked;
            overviewOptionsDetailsDiv.classList.toggle('opacity-50', !isEnabled);
            overviewOptionsDetailsDiv.classList.toggle('pointer-events-none', !isEnabled);
            overviewInputsToToggle.forEach(input => {
                if (input) {
                    input.disabled = !isEnabled;
                    
                    // Handle our hidden select + custom dropdown button
                    if (input.id === 'overview-top-x-type') {
                        // Also update the custom button
                        const customButton = document.getElementById('overview-top-x-type-button');
                        
                        if (customButton) {
                            customButton.disabled = !isEnabled;
                            
                            if (!isEnabled) {
                                customButton.classList.add('opacity-70', 'cursor-not-allowed');
                                customButton.style.backgroundColor = 'var(--input-bg)';
                                customButton.style.color = 'var(--text-secondary)';
                                customButton.style.border = '1px solid var(--border-color)';
                            } else {
                                customButton.classList.remove('opacity-70', 'cursor-not-allowed');
                                customButton.style.backgroundColor = '';
                                customButton.style.color = '';
                                customButton.style.border = '';
                            }
                        }
                    }
                }
            });
        }
        // Initial call to set state based on default checkbox state
        toggleOverviewOptions(); 
        includeOverviewPageCheckbox.addEventListener('change', toggleOverviewOptions);
    }
    // --- END NEW ---

    function updatePdfStatus(message, type = 'info', actionType = 'general') { // type: info, error, success, loading
        // ... existing code ...
    }

    // Function to clear all PDF related state
    function clearPdfFileState() {
        console.log('Clearing PDF file state...');
        if(currentPdfFile) {
            console.log('Clearing current PDF file for a new upload.');
            currentPdfFile = null;
        }
        pdfFilenameEl.textContent = 'No file selected.';
        if(pdfUploadInput) pdfUploadInput.value = ''; // Clear file input
        if(pdfActionStatusEl) pdfActionStatusEl.textContent = '';
        currentPdfTaskId = null;
        textExtractBtn.disabled = false;
        pdfAnalysisBtn.disabled = false;
        pdfDownloadCard.classList.add('card-inactive');
        pdfDownloadCard.classList.remove('card-active');
        updatePdfActionButtonsState(false); // Re-enable buttons
    }

    // Event listener for PDF file selection
    if (pdfUploadInput) {
        pdfUploadInput.addEventListener('change', (event) => {
            const file = event.target.files[0];
            if (file) {
                currentPdfFile = file; // Store the selected file
                console.log('PDF Selected:', file.name);
                currentPdfTaskId = null; // Reset task ID for the new file
                // Clear any previous status messages from the shared status element
                if (pdfActionStatusEl) {
                    pdfActionStatusEl.textContent = '';
                    pdfActionStatusEl.className = 'status-text'; // Reset status style
                }
                textExtractBtn.disabled = false;
                pdfAnalysisBtn.disabled = false;
                pdfDownloadCard.classList.add('card-inactive');
                pdfDownloadCard.classList.remove('card-active');
                pdfFilenameEl.textContent = file.name;
                pdfUploadCard.classList.remove('card-active');
                pdfUploadCard.classList.add('card-inactive');
                pdfFileActionsCard.classList.remove('hidden');
                pdfFileActionsCard.classList.add('card-active');
                updatePdfActionButtonsState(false); // Ensure buttons are enabled for the new file
            } else {
                clearPdfFileState(); // If no file (e.g., dialog cancelled), clear state
            }
        });
    }

    // --- NEW: Event Listeners for Analysis Mode Selection ---
    if (analysisModeOptions && analysisOptionsMenu && analysisExpandBtn) {
        analysisModeOptions.forEach(option => {
            option.addEventListener('click', (event) => {
                event.preventDefault();
                const selectedMode = option.getAttribute('data-mode');
                if (selectedMode) {
                    currentAnalysisMode = selectedMode;
                    console.log(`Analysis mode changed to: ${currentAnalysisMode}`);
                    analysisOptionsMenu.classList.add('hidden');
                    analysisControlsContainer.classList.remove('options-visible');

                    if (!isAnalysisPaused) {
                        console.log("Re-triggering analysis due to mode change.");
                        const currentText = quill.getText();
                        const contextEnabled = contextAwarenessToggle ? contextAwarenessToggle.checked : false;
                        if (currentAnalysisMode === 'fast') {
                            analyzeSequentially(currentText, currentTargetAudience, contextEnabled, 'fast');
                        } else { // 'better' or 'best'
                            analyzeAndHighlight(false, currentAnalysisMode);
                        }
                    }
                }
            });
        });

        // Close menu if clicking outside
        document.addEventListener('click', (event) => {
            if (analysisOptionsMenu && !analysisOptionsMenu.classList.contains('hidden') && !analysisControlsContainer.contains(event.target)) {
                analysisOptionsMenu.classList.add('hidden');
                analysisControlsContainer.classList.remove('options-visible');
            }
        });

    } else {
        console.warn("Analysis mode options or menu/button not found.");
    }

    // Function to update the main analysis button based on selected mode (optional enhancement)
    // function updateAnalysisButtonAppearance() { ... }

}); // End DOMContentLoaded


