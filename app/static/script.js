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
    const complexityDescriptionEl = document.getElementById('complexity-description');
    const complexityPercentageEl = document.getElementById('complexity-percentage');
    const complexityLoadingEl = document.getElementById('complexity-loading');
    // const readabilityScoreEl = document.getElementById('readability-score'); // Removed - replaced by individual scores
    const analysisTimeEl = document.getElementById('analysis-time');
    const sensitivitySlider = document.getElementById('complexity-sensitivity-slider'); // Changed from select to slider
    const sensitivityLabel = document.getElementById('sensitivity-value-label'); // Added label reference
    // New elements for individual readability scores
    const fleschKincaidScoreEl = document.getElementById('flesch-kincaid-score');
    const gunningFogScoreEl = document.getElementById('gunning-fog-score');
    const smogIndexScoreEl = document.getElementById('smog-index-score');
    // Visual Map container
    const documentMapContainer = document.getElementById('document-map');

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
    let currentAnalysisResults = []; // Store results to map sentences
    let currentSensitivityLevel = 3; // Default to Standard (value 3)
    const sensitivityLabels = { // Map values to labels
        1: "V. Lenient",
        2: "Lenient",
        3: "Standard",
        4: "Strict",
        5: "V. Strict"
    };
    let previousScores = { // Store previous scores for animation
        flesch_kincaid_grade: null,
        gunning_fog: null,
        smog_index: null,
    };

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
    function updateComplexityMeter(levelData) {
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

        // Removed the line that updated complexityDescriptionEl.textContent
        // The static labels in HTML now handle this.
        // We keep the element in case we want to display other status messages later.
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
    async function analyzeAndHighlight(forceHighlightUpdate = false) {
        const text = quill.getText();
        const startTime = performance.now();

        if (!text.trim()) {
            quill.formatText(0, quill.getLength(), 'background', false, 'api');
            currentAnalysisResults = [];
            updateComplexityMeter(null);
            // Reset individual scores
            if (fleschKincaidScoreEl) fleschKincaidScoreEl.textContent = '-';
            if (gunningFogScoreEl) gunningFogScoreEl.textContent = '-';
            if (smogIndexScoreEl) smogIndexScoreEl.textContent = '-';
            // if (readabilityScoreEl) readabilityScoreEl.textContent = '-'; // Removed
            if (analysisTimeEl) analysisTimeEl.textContent = '0ms';
            // Clear highlighting if text is empty
            applyHighlighting([]); // Call with empty results to clear formats
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
                // Update individual readability scores from backend data
                const scores = data.readability_scores || {};
                if (fleschKincaidScoreEl) fleschKincaidScoreEl.textContent = scores.flesch_kincaid_grade !== null ? scores.flesch_kincaid_grade : 'N/A';
                if (gunningFogScoreEl) gunningFogScoreEl.textContent = scores.gunning_fog !== null ? scores.gunning_fog : 'N/A';
                if (smogIndexScoreEl) smogIndexScoreEl.textContent = scores.smog_index !== null ? scores.smog_index : 'N/A';
                // if (readabilityScoreEl) readabilityScoreEl.textContent = calculateReadabilityScore(text); // Removed old calculation
                if (analysisTimeEl) analysisTimeEl.textContent = `${analysisTime}ms`;

            } catch (error) {
                console.error('Error fetching analysis:', error);
                updateComplexityMeter({level: 0, description: "Analysis Error"});
                // Update individual scores on error
                if (fleschKincaidScoreEl) fleschKincaidScoreEl.textContent = 'Error';
                if (gunningFogScoreEl) gunningFogScoreEl.textContent = 'Error';
                if (smogIndexScoreEl) smogIndexScoreEl.textContent = 'Error';
                // if (readabilityScoreEl) readabilityScoreEl.textContent = 'Error'; // Removed
                if (analysisTimeEl) analysisTimeEl.textContent = 'Error';
                currentAnalysisResults = []; // Clear results on error
            } finally {
                if (complexityLoadingEl) complexityLoadingEl.classList.add('hidden');
            }
        }

        // Always apply highlighting based on current results and target audience
        applyHighlighting(currentAnalysisResults); // Ensure highlighting is called

        // Update the visual document map *after* results are potentially fetched/updated
        console.log("Calling updateDocumentMap with results:", currentAnalysisResults); // DEBUG
        updateDocumentMap(currentAnalysisResults);
    }

    // --- Helper function to update score with animation ---
    function updateScoreElement(element, newScore, scoreKey) {
        const currentScore = newScore !== null ? newScore : 'N/A';
        const previousScore = previousScores[scoreKey] !== null ? previousScores[scoreKey] : 'N/A';

        if (element && currentScore !== previousScore) {
            // Add class to trigger animation (defined in CSS)
            element.classList.add('score-updating');
            // Update text content
            element.textContent = currentScore;
            // Store the new score
            previousScores[scoreKey] = newScore;
            // Remove the class after animation duration (e.g., 300ms)
            setTimeout(() => {
                if (element) { // Check if element still exists
                     element.classList.remove('score-updating');
                }
            }, 300); // Match CSS transition duration
        } else if (element && element.textContent !== currentScore) {
             // If score hasn't changed but text is wrong (e.g., initial load), update without animation
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


    function applyHighlighting(results) {
        // Clear previous background formatting first
        // Note: Formatting with 'class': false might remove ALL classes.
        // A safer approach might involve getting existing formats, but let's try this first.
        // Clear previous background formatting first
        // console.log("Clearing previous background format..."); // DEBUG
        quill.formatText(0, quill.getLength(), 'background', false, 'api');
        // Also clear any lingering 'sentence-deviates' class if it exists from previous runs
        quill.formatText(0, quill.getLength(), 'class', false, 'api');
        // console.log(`Applying highlighting for sensitivity level: ${currentSensitivityLevel}`); // DEBUG

        results.forEach(result => {
            const score = result.score; // Get score from backend result
            const color = getDynamicHighlightColor(score, currentSensitivityLevel); // Calculate color dynamically
            const bgColor = complexityBackgrounds[color] || complexityBackgrounds['gray'];
            const startIndex = result.start; // Use start index from backend
            const endIndex = result.end;     // Use end index from backend
            const length = endIndex - startIndex; // Calculate length

            if (startIndex !== undefined && length > 0) {
                // Apply background color using indices
                quill.formatText(startIndex, length, 'background', bgColor, 'api');

                // --- REMOVED Deviation Logic ---
                // const deviation = sentenceLevel - currentTargetAudienceLevel;
                // if (deviation >= 2) {
                //     quill.formatText(startIndex, length, 'class', 'sentence-deviates', 'api');
                // } else {
                //     quill.formatText(startIndex, length, 'class', false, 'api');
                // }
                // --- End REMOVED Deviation Logic ---

            } else {
                 // Log if indices are missing or invalid
                 console.warn(`Invalid indices received for sentence analysis: start=${startIndex}, end=${endIndex}`);
            }
            // No longer need currentIndex tracking with indexOf
        });
    }

    // --- Visual Document Map Update ---
    function updateDocumentMap(results) {
        console.log("updateDocumentMap received results:", results); // DEBUG
        if (!documentMapContainer) {
            console.error("Document map container not found!"); // DEBUG
            return;
        }

        // Clear previous map segments
        documentMapContainer.innerHTML = '';

        if (!results || results.length === 0) {
            // Optionally display a message or leave it empty
            // documentMapContainer.textContent = 'No text to map.';
            return;
        }

        // Define background colors for map segments (Tailwind classes)
        const mapSegmentColors = {
            green: 'bg-green-500',
            yellow: 'bg-yellow-500',
            orange: 'bg-orange-500',
            red: 'bg-red-500',
            gray: 'bg-gray-500', // Fallback
        };

        console.log(`Processing ${results.length} results for document map.`); // DEBUG
        results.forEach((result, idx) => {
             console.log(`Creating segment for result index ${idx}:`, result); // DEBUG
             if (result.index === undefined || result.score === undefined) {
                 console.warn(`Skipping result at index ${idx} due to missing index or score.`); // DEBUG
                 return; // Skip this iteration if data is missing
             }
            const segment = document.createElement('div');
            segment.classList.add('map-segment'); // Base class for styling (flex-grow, transition)

            // Set sentence index for linking
            segment.dataset.sentenceIndex = result.index;

            // Calculate height (e.g., scale score to percentage, with min/max)
            // Score range might be 0 to ~1.5+. Let's map it to 5% - 100% height.
            const heightPercent = Math.min(100, Math.max(5, (result.score || 0) * 60 + 5));
            segment.style.height = `${heightPercent}%`;

            // Determine color based on score and sensitivity
            const colorName = getDynamicHighlightColor(result.score, currentSensitivityLevel);
            const colorClass = mapSegmentColors[colorName] || mapSegmentColors['gray'];
            segment.classList.add(colorClass);

            // Add tooltip showing the score (optional)
            segment.title = `Sentence ${result.index + 1}: Score ${result.score.toFixed(2)}`;

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

    // Initialize tooltips after DOM is ready
    setTimeout(initTooltips, 500);

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

    // --- Initial Load ---
    updateStats();
    // Analyze any initial content (if editor is pre-filled)
    // analyzeAndHighlight(); // Maybe call this after a short delay? Or rely on first text-change?
    // Let's call it initially to handle potential pre-filled content
     setTimeout(analyzeAndHighlight, 100); // Small delay to ensure Quill is fully ready

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
            const result = currentAnalysisResults[sentenceIndex];

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
            const result = currentAnalysisResults[sentenceIndex];

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
    }

}); // End DOMContentLoaded
