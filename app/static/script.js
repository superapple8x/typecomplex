// Libraries Quill and tippy are loaded globally via <script> tags in index.html
// We might still need to import Tippy's CSS if not using a CDN or pre-built bundle with CSS.
// Let's assume for now the CSS is handled or we'll add a separate <link> tag if needed.

// --- Utility: Debounce ---
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

document.addEventListener('DOMContentLoaded', () => {
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
    const documentMapContainer = document.getElementById('document-map');
    // --- NEW DOM References ---
    const targetAudienceSelect = document.getElementById('target-audience-select'); // e.g., <select id="target-audience-select">...</select>
    const toggleHighlighting = document.getElementById('toggle-highlighting');       // e.g., <input type="checkbox" id="toggle-highlighting" checked>
    const toggleGoalIndicators = document.getElementById('toggle-goal-indicators'); // e.g., <input type="checkbox" id="toggle-goal-indicators" checked>
    // Elements for displaying targets (assuming they exist or will be added in HTML)
    const fleschKincaidTargetEl = document.getElementById('flesch-kincaid-target'); // e.g., <span id="flesch-kincaid-target" class="text-xs text-gray-400 ml-1"></span>
    const gunningFogTargetEl = document.getElementById('gunning-fog-target');       // e.g., <span id="gunning-fog-target" class="text-xs text-gray-400 ml-1"></span>
    // Optional: Elements for visual indicators on meter/map (might be handled by CSS classes instead)
    // const complexityMeterTargetMarker = document.getElementById('complexity-meter-target-marker');
    // const documentMapTargetLine = document.getElementById('document-map-target-line');

    // --- Quill Initialization ---
    // Removed the custom Attributor registration as it caused errors with global script loading.
    // We will use a standard CSS class instead.

    const quill = new Quill(editorContainer, {
        theme: 'snow', // Use the Snow theme
        modules: {
            toolbar: [ // Basic toolbar, customize as needed
                ['bold', 'italic', 'underline'],
                [{ 'list': 'ordered'}, { 'list': 'bullet' }],
                ['clean'] // remove formatting button
            ]
        },
        placeholder: 'Start writing here...',
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

    // --- Complexity Color Mapping (Dark Theme) ---
    const complexityBackgrounds = {
        green: 'rgba(40, 167, 69, 0.3)',
        yellow: 'rgba(255, 193, 7, 0.3)',
        orange: 'rgba(253, 126, 20, 0.3)',
        red: 'rgba(220, 53, 69, 0.3)',
        gray: 'rgba(108, 117, 125, 0.2)',
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
    let currentAnalysisData = null; // Store the full analysis response object { results: [], overall_level: {}, readability_scores: {}, target_readability_scores: {} }
    let currentTargetAudience = 'Standard'; // Default audience, updated from select element
    let showHighlighting = true; // Default state for toggle, updated from checkbox
    let showGoalIndicators = true; // Default state for toggle, updated from checkbox
    let currentSensitivityLevel = 3; // Default to Standard (value 3)
    const sensitivityLabels = { 1: "V. Lenient", 2: "Lenient", 3: "Standard", 4: "Strict", 5: "V. Strict" };
    let previousScores = { flesch_kincaid_grade: null, gunning_fog: null, smog_index: null }; // For animation

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
function updateReadabilityScores(analysisData) { // NEW/MODIFIED
    const calculatedScores = analysisData?.readability_scores || {};
    const targetScores = analysisData?.target_readability_scores || {};

    // Update calculated scores (using existing updateScoreElement helper for potential animation)
    updateScoreElement(fleschKincaidScoreEl, calculatedScores.flesch_kincaid_grade, 'flesch_kincaid_grade');
    updateScoreElement(gunningFogScoreEl, calculatedScores.gunning_fog, 'gunning_fog');
    updateScoreElement(smogIndexScoreEl, calculatedScores.smog_index, 'smog_index');

    // Update target score display based on toggle state
    console.log(`[updateReadabilityScores] showGoalIndicators: ${showGoalIndicators}`); // DEBUG
    console.log(`[updateReadabilityScores] analysisData:`, analysisData); // DEBUG
    console.log(`[updateReadabilityScores] targetScores:`, targetScores); // DEBUG
    console.log(`[updateReadabilityScores] fleschKincaidTargetEl:`, fleschKincaidTargetEl); // DEBUG
    console.log(`[updateReadabilityScores] gunningFogTargetEl:`, gunningFogTargetEl); // DEBUG

    if (showGoalIndicators) {
        if (fleschKincaidTargetEl) {
            const fkTargetText = formatTargetRange(targetScores?.flesch_kincaid_grade); // Optional chaining
            console.log(`[updateReadabilityScores] Setting FK Target text: "${fkTargetText}"`); // DEBUG
            fleschKincaidTargetEl.textContent = fkTargetText;
            fleschKincaidTargetEl.classList.remove('hidden'); // Ensure visible
        } else {
            console.warn("[updateReadabilityScores] fleschKincaidTargetEl not found."); // DEBUG
        }
        if (gunningFogTargetEl) {
            const gfTargetText = formatTargetRange(targetScores?.gunning_fog); // Optional chaining
            console.log(`[updateReadabilityScores] Setting GF Target text: "${gfTargetText}"`); // DEBUG
            gunningFogTargetEl.textContent = gfTargetText;
            gunningFogTargetEl.classList.remove('hidden'); // Ensure visible
        } else {
            console.warn("[updateReadabilityScores] gunningFogTargetEl not found."); // DEBUG
        }
        // Add logic for SMOG target if applicable and element exists
    } else {
        // Hide target elements if toggle is off
        if (fleschKincaidTargetEl) fleschKincaidTargetEl.classList.add('hidden');
        if (gunningFogTargetEl) gunningFogTargetEl.classList.add('hidden');
        // Hide other target elements if added
    }
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

        // --- NEW: Add Target Marker Logic ---
        // Example: Add a class to the meter container if goal indicators are shown
        // This requires CSS rules for `.overall-complexity-meter.show-goal-indicator::before` or similar
        // to draw the marker/zone based on CSS variables.
        const meterContainer = document.getElementById('overall-complexity-meter'); // Assuming this ID exists on the container div
        if (meterContainer) {
            if (showGoalIndicators && analysisData?.target_readability_scores && levelData) {
                 // TODO: A more robust way to get target level range is needed.
                 // Option 1: Backend sends target level range based on profile thresholds.
                 // Option 2: Frontend approximates based on target scores (less accurate).
                 // For now, just add the class to enable CSS styling.
                 // Example placeholder logic (needs refinement):
                 // const targetFKG = analysisData.target_readability_scores.flesch_kincaid_grade;
                 // let targetMinLevel = 1, targetMaxLevel = 5;
                 // if (targetFKG) { // Very rough approximation
                 //    if (targetFKG[1] && targetFKG[1] < 11) targetMaxLevel = 3; // General Public max ~ Moderate
                 //    if (targetFKG[0] && targetFKG[0] >= 13) targetMinLevel = 4; // Academic min ~ Complex
                 // }
                 // meterContainer.style.setProperty('--target-min-percent', `${(targetMinLevel -1) * 20}%`);
                 // meterContainer.style.setProperty('--target-max-percent', `${targetMaxLevel * 20}%`);
                 meterContainer.classList.add('show-goal-indicator'); // Add class for CSS styling of marker/zone
            } else {
                 meterContainer.classList.remove('show-goal-indicator');
                 // meterContainer.style.removeProperty('--target-min-percent');
                 // meterContainer.style.removeProperty('--target-max-percent');
            }
        }
        // --- End Target Marker Logic ---
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

    // --- Analysis & Highlighting ---
    // --- Analysis & Highlighting (Modified) ---
    async function analyzeAndHighlight(forceHighlightUpdate = false) {
        const text = quill.getText();
        const startTime = performance.now();

        // Get current audience from state (updated by event listener)
        const audience = currentTargetAudience; // Use state variable

        if (!text.trim()) {
            quill.formatText(0, quill.getLength(), 'background', false, 'api'); // Clear highlights
            currentAnalysisData = null; // Clear full data
            updateComplexityMeter(null); // Reset meter
            updateReadabilityScores(null); // Clear scores and targets
            updateDocumentMap(null); // Clear map
            if (analysisTimeEl) analysisTimeEl.textContent = '0ms';
            // applyHighlighting is implicitly handled by clearing formats above and returning
            return;
        }

        // Only fetch new analysis if not forcing highlight update
        if (!forceHighlightUpdate) {
            // Show loading state
            if (complexityLoadingEl) complexityLoadingEl.classList.remove('hidden');
            // REMOVED: Update individual score placeholders to '...'
            // if (fleschKincaidScoreEl) fleschKincaidScoreEl.textContent = '...';
            // if (gunningFogScoreEl) gunningFogScoreEl.textContent = '...';
            // if (smogIndexScoreEl) smogIndexScoreEl.textContent = '...';

            try {
                const response = await fetch('/analyze', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    // Send text AND target audience
                    body: JSON.stringify({ text: text, target_audience: audience }), // MODIFIED
                });

                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

                const data = await response.json();
                currentAnalysisData = data; // Store the FULL response // MODIFIED

                // Calculate metrics
                const endTime = performance.now();
                const analysisTime = Math.round(endTime - startTime);

                // Update UI using the full data object
                updateComplexityMeter(currentAnalysisData); // MODIFIED (pass full data)
                updateReadabilityScores(currentAnalysisData); // MODIFIED (handles calculated + target)
                if (analysisTimeEl) analysisTimeEl.textContent = `${analysisTime}ms`;
            } catch (error) {
                console.error('Error fetching analysis:', error);
                currentAnalysisData = null; // Clear data on error
                updateComplexityMeter(null); // Reset meter
                updateReadabilityScores(null); // Reset scores
                if (analysisTimeEl) analysisTimeEl.textContent = 'Error';
                // Map will be cleared in the finally block's updateDocumentMap call
            } finally {
                if (complexityLoadingEl) complexityLoadingEl.classList.add('hidden');
            }
        }

        // Apply highlighting and update map based on potentially updated currentAnalysisData
        // Pass results array and the full data object if needed by sub-functions
        applyHighlighting(currentAnalysisData?.results || []); // MODIFIED (use results from full data)
        updateDocumentMap(currentAnalysisData); // MODIFIED (pass full data for potential target line)
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


    // --- Apply Highlighting (Modified) ---
    function applyHighlighting(results) {
        // Clear previous formats first
        quill.formatText(0, quill.getLength(), 'background', false, 'api');
        quill.formatText(0, quill.getLength(), 'class', false, 'api'); // Clear other classes like hover

        // --- NEW: Check toggle state ---
        if (!showHighlighting) {
            // console.log("Highlighting is OFF"); // DEBUG
            return; // Exit if highlighting is turned off
        }
        // --- End Check ---
        // console.log("Highlighting is ON, applying formats..."); // DEBUG

        if (!results) return; // Check if results exist

        results.forEach(result => {
            const score = result.score; // Get score from backend result
            const color = getDynamicHighlightColor(score, currentSensitivityLevel); // Calculate color dynamically based on sensitivity
            const bgColor = complexityBackgrounds[color] || complexityBackgrounds['gray'];
            const startIndex = result.start; // Use start index from backend
            const endIndex = result.end;     // Use end index from backend
            const length = endIndex - startIndex; // Calculate length

            if (startIndex !== undefined && length > 0) {
                // Apply background color using indices
                quill.formatText(startIndex, length, 'background', bgColor, 'api');
            } else {
                 // Log if indices are missing or invalid
                 console.warn(`Invalid indices received for sentence analysis: start=${startIndex}, end=${endIndex}`);
            }
        });
    }

    // --- Visual Document Map Update ---
    // --- Visual Document Map Update (Modified) ---
    function updateDocumentMap(analysisData) { // Modified to accept full data
        const results = analysisData?.results; // Get results array from full data

        if (!documentMapContainer) return;
        documentMapContainer.innerHTML = ''; // Clear previous map segments and lines

        // --- NEW: Add Target Line Logic ---
        // Add class to container for CSS-based styling of the line
        if (showGoalIndicators && analysisData?.target_readability_scores) {
            // TODO: Calculate the complexity score threshold corresponding to the target audience.
            // This is complex as it depends on the profile's thresholds and how they map back to scores.
            // For now, we'll just add the class and assume CSS handles the line display.
            // A simpler approach might be to use the 'moderate' threshold from the profile.
            // Example placeholder:
            // const profileThresholds = analysisData.profile?.thresholds; // Assuming backend sends profile used
            // if (profileThresholds) {
            //    const targetMaxScore = profileThresholds.moderate; // Use moderate threshold as target line?
            //    const targetLinePercent = Math.min(100, Math.max(5, (targetMaxScore || 0) * 60 + 5)); // Scale like bars
            //    documentMapContainer.style.setProperty('--target-line-percent', `${targetLinePercent}%`);
            // }
            documentMapContainer.classList.add('show-goal-indicator'); // Add class for CSS styling of line
        } else {
            documentMapContainer.classList.remove('show-goal-indicator');
            // documentMapContainer.style.removeProperty('--target-line-percent');
        }
        // --- End Target Line Logic ---

        if (!results || results.length === 0) {
            // documentMapContainer.textContent = 'No text to map.'; // Optional message
            return; // Exit if no results
        }

        // Define background colors for map segments (Tailwind classes)
        const mapSegmentColors = {
            green: 'bg-green-500', yellow: 'bg-yellow-500', orange: 'bg-orange-500',
            red: 'bg-red-500', gray: 'bg-gray-500',
        };

        results.forEach((result, idx) => {
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
        synonymTooltip.show();

        try {
            const response = await fetch('/synonyms', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ word: selectedText }),
            });

            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const data = await response.json();

            // Build tooltip content - Reduced size and click handling attributes
            let contentHTML = `<div id="${tooltipContentId}" class="p-1 text-xs dark:text-gray-200 bg-gray-800 border border-gray-700 rounded shadow-lg max-w-xs">`; // Reduced padding, text-xs
            if (data.synonyms && data.synonyms.length > 0) {
                contentHTML += `<strong class="block mb-1 text-sm font-semibold">Synonyms for "${selectedText}"</strong>`; // Reduced heading size
                contentHTML += `<ul class="list-none p-0 m-0 space-y-0.5">`; // Reduced spacing

                const rankClasses = {
                    1: 'bg-green-600 hover:bg-green-500', 2: 'bg-lime-600 hover:bg-lime-500', 3: 'bg-yellow-600 hover:bg-yellow-500',
                    4: 'bg-orange-600 hover:bg-orange-500', 5: 'bg-red-600 hover:bg-red-500',
                };
                const badgeBaseClass = 'inline-flex items-center justify-center w-4 h-4 mr-1.5 text-xs font-bold text-white rounded-sm transition-colors duration-150'; // Slightly smaller badge
                const listItemBaseClass = 'synonym-item flex items-center p-0.5 rounded cursor-pointer hover:bg-gray-700 transition-colors duration-150'; // Reduced padding

                data.synonyms.forEach(syn => {
                    const rankClass = rankClasses[syn.rank] || 'bg-gray-500 hover:bg-gray-400';
                    // Add data attributes for click handler
                    contentHTML += `<li class="${listItemBaseClass}"
                                        data-synonym="${syn.word}"
                                        data-range-index="${range.index}"
                                        data-range-length="${range.length}">
                                      <span class="${badgeBaseClass} ${rankClass}">${syn.rank}</span>
                                      <span>${syn.word}</span>
                                    </li>`;
                });
                contentHTML += `</ul>`;
            } else {
                contentHTML += `No synonyms found for "${selectedText}".`;
            }
            contentHTML += `</div>`;

            // Set the final content. The listener is attached via onShow to the popper.
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

    quill.on('text-change', (delta, oldDelta, source) => {
        if (source === 'user') {
            updateStats();
            debouncedAnalyzeAndHighlight(); // Now this should be defined
        }
    });

    // Function to update sensitivity label
    function updateSensitivityLabel(level) {
        if (sensitivityLabel) {
            sensitivityLabel.textContent = sensitivityLabels[level] || 'Unknown';
        }
    }

    // Listener for Complexity Sensitivity Slider
    if (sensitivitySlider) {
        // Set initial label text on load
        updateSensitivityLabel(parseInt(sensitivitySlider.value, 10));

        sensitivitySlider.addEventListener('input', (event) => { // Changed from 'change' to 'input'
            const newLevel = parseInt(event.target.value, 10);
            // console.log(`Complexity sensitivity changed. New selected level: ${newLevel}`); // DEBUG
            currentSensitivityLevel = newLevel;
            updateSensitivityLabel(newLevel); // Update the label text
            // Re-apply highlighting based on the new sensitivity level, without re-analyzing text
            // console.log("Forcing highlight update due to sensitivity change."); // DEBUG
            analyzeAndHighlight(true); // Pass true to force highlight update
        });
    }

    // Initialize Tippy tooltips for status bar, etc.
    setTimeout(initTooltips, 500); // Delay slightly

    quill.on('selection-change', (range, oldRange, source) => {
        if (source === 'user') {
            if (range && range.length > 0) {
                // Check if the selection is different from the one that triggered the current tooltip
                if (!currentSynonymRange || range.index !== currentSynonymRange.index || range.length !== currentSynonymRange.length) {
                    // Delay slightly to allow selection to finalize
                    setTimeout(() => {
                        const currentSelection = quill.getSelection();
                        // Double check selection still exists after delay
                        if (currentSelection && currentSelection.length > 0) {
                            showSynonymTooltip(currentSelection);
                        } else {
                            synonymTooltip.hide();
                            currentSynonymRange = null; // Clear stored range if selection disappears
                        }
                    }, 50); // Adjust delay if needed
                }
            } else {
                synonymTooltip.hide();
                currentSynonymRange = null; // Clear stored range when selection is lost
            }
        }
    });

    // --- NEW Event Listeners ---

    // Target Audience Select Listener
    if (targetAudienceSelect) {
        targetAudienceSelect.addEventListener('change', (event) => {
            currentTargetAudience = event.target.value;
            console.log(`Target audience changed to: ${currentTargetAudience}`); // DEBUG
            analyzeAndHighlight(false); // Re-analyze with new audience (force backend call)
        });
        // Set initial state from dropdown value on load
        currentTargetAudience = targetAudienceSelect.value;
    } else {
        console.warn("Target audience select element not found.");
    }

    // Toggle Highlighting Listener
    if (toggleHighlighting) {
        toggleHighlighting.addEventListener('change', (event) => {
            showHighlighting = event.target.checked;
            console.log(`Show Highlighting set to: ${showHighlighting}`); // DEBUG
            // Immediately apply/remove highlighting based on current data
            applyHighlighting(currentAnalysisData?.results || []);
        });
        // Set initial state from checkbox value on load
        showHighlighting = toggleHighlighting.checked;
    } else {
         console.warn("Toggle highlighting element not found.");
         showHighlighting = true; // Default if element missing
    }

    // Toggle Goal Indicators Listener
    if (toggleGoalIndicators) {
        toggleGoalIndicators.addEventListener('change', (event) => {
            showGoalIndicators = event.target.checked;
            console.log(`Show Goal Indicators set to: ${showGoalIndicators}`); // DEBUG
            // Immediately update UI elements that show goal indicators using current data
            updateReadabilityScores(currentAnalysisData);
            updateComplexityMeter(currentAnalysisData);
            updateDocumentMap(currentAnalysisData);
        });
        // Set initial state from checkbox value on load
        showGoalIndicators = toggleGoalIndicators.checked;
    } else {
        console.warn("Toggle goal indicators element not found.");
        showGoalIndicators = true; // Default if element missing
    }


    // --- Initial Load ---
    updateStats(); // Initial stats calculation
    // Set initial audience/toggle states (done above in listener checks)
    // Initial analysis call
    setTimeout(analyzeAndHighlight, 100); // Small delay to ensure Quill is fully ready and initial states are set

    // --- Sidebar Toggle Logic ---
    function openSidebar() {
        if (sidebar && openSidebarBtn) {
            // Use classes for state management and transitions
            sidebar.classList.remove('w-0', 'p-0', 'opacity-0', 'hidden');
            sidebar.classList.add('w-64', 'p-4', 'opacity-100');
            openSidebarBtn.classList.add('hidden');
        }
    }

    function closeSidebar() {
        if (sidebar && openSidebarBtn) {
            // Apply classes to hide and shrink
            sidebar.classList.remove('w-64', 'p-4', 'opacity-100');
            sidebar.classList.add('w-0', 'p-0', 'opacity-0');
            // Use a timeout matching the transition duration before setting hidden
            // This allows the transition to complete visually. Adjust 300ms if transition duration changes.
            setTimeout(() => {
                sidebar.classList.add('hidden');
                openSidebarBtn.classList.remove('hidden');
            }, 300); // Match transition duration in index.html (duration-300)
        }
    }

    if (toggleSidebarBtn) {
        toggleSidebarBtn.addEventListener('click', closeSidebar);
    }

    if (openSidebarBtn) {
        openSidebarBtn.addEventListener('click', openSidebar);
    }

    // Ensure sidebar is open by default on load (or closed if you prefer)
    // openSidebar(); // Uncomment if you want it open by default
    // If you want it closed by default, you might need to adjust initial classes in index.html
    // For now, assuming it starts open as per index.html structure.


    // --- Visual Map Hover Listeners ---
    if (documentMapContainer) {
        documentMapContainer.addEventListener('mouseover', (event) => {
            const segment = event.target.closest('.map-segment');
            if (!segment || !segment.dataset.sentenceIndex) return;

            const sentenceIndex = parseInt(segment.dataset.sentenceIndex, 10);
            const result = currentAnalysisData?.results[sentenceIndex]; // Use currentAnalysisData

            if (result && result.start !== undefined && result.end !== undefined) {
                const length = result.end - result.start;
                if (length > 0) {
                    // Apply a temporary highlight class
                    quill.formatText(result.start, length, 'class', 'highlight-map-hover', 'api');
                }
            }
        });

        documentMapContainer.addEventListener('mouseout', (event) => {
            const segment = event.target.closest('.map-segment');
            if (!segment || !segment.dataset.sentenceIndex) return;

            const sentenceIndex = parseInt(segment.dataset.sentenceIndex, 10);
            const result = currentAnalysisData?.results[sentenceIndex]; // Use currentAnalysisData

            if (result && result.start !== undefined && result.end !== undefined) {
                const length = result.end - result.start;
                if (length > 0) {
                    // Remove the temporary highlight class
                    // Note: Formatting with 'class': false removes ALL classes applied via formatText.
                    // If other classes were applied this way, this could be an issue.
                    // For now, assuming only 'highlight-map-hover' is applied this way temporarily.
                    quill.formatText(result.start, length, 'class', false, 'api');
                }
            }
        });

        // Add click listener to select text in editor
        documentMapContainer.addEventListener('click', (event) => {
            const segment = event.target.closest('.map-segment');
            if (!segment || !segment.dataset.sentenceIndex) return;

            const sentenceIndex = parseInt(segment.dataset.sentenceIndex, 10);
            const result = currentAnalysisData?.results[sentenceIndex]; // Use currentAnalysisData

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

}); // End DOMContentLoaded
