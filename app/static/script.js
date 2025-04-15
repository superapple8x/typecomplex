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
    // --- Target Audience / Display Options ---
    const targetAudienceSelect = document.getElementById('target-audience-select');
    const toggleHighlighting = document.getElementById('toggle-highlighting');
    const toggleGoalIndicators = document.getElementById('toggle-goal-indicators');
    const fleschKincaidTargetEl = document.getElementById('flesch-kincaid-target');
    const gunningFogTargetEl = document.getElementById('gunning-fog-target');
    // --- NEW Gemini/Context Awareness Elements ---
    const contextAwarenessToggle = document.getElementById('context-awareness-toggle');
    const goalContainer = document.getElementById('target-audience-goal-container');
    const goalInput = document.getElementById('target-audience-goal');
    const contextAwarenessInfo = document.getElementById('context-awareness-info'); // Info icon

    // --- Quill Initialization ---
    // Removed the custom Attributor registration as it caused errors with global script loading.
    // We will use a standard CSS class instead.

    // REMOVED Custom Format Registration for GoalDeviationUnderline


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
    let isOverallScoreOutOfBounds = false; // Track if overall score is outside target
    let currentSensitivityLevel = 3; // Default to Standard (value 3)
    const sensitivityLabels = { 1: "V. Lenient", 2: "Lenient", 3: "Standard", 4: "Strict", 5: "V. Strict" };
    let previousScores = { flesch_kincaid_grade: null, gunning_fog: null, smog_index: null }; // For animation
    // --- NEW State for Context Awareness ---
    let contextAwarenessEnabled = false; // Default state, updated from checkbox
    let currentGoalText = ''; // Store the goal text

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

    // --- Analysis & Highlighting ---
    // --- Analysis & Highlighting (Modified) ---
    async function analyzeAndHighlight(forceHighlightUpdate = false) {
        const text = quill.getText();
        const startTime = performance.now();

        // Get current audience from state (updated by event listener)
        const audience = currentTargetAudience; // Use state variable

        if (!text.trim()) {
            quill.formatText(0, quill.getLength(), 'background', false, 'api'); // Clear highlights
            quill.formatText(0, quill.getLength(), 'underline', false, 'api'); // Clear underlines
            currentAnalysisData = null; // Clear full data
            isOverallScoreOutOfBounds = false; // Reset out of bounds flag
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

            // --- Prepare request body ---
            const requestBody = {
                text: text,
                target_audience: audience, // For statistical analysis
                context_awareness_enabled: contextAwarenessEnabled, // Send toggle state
                target_audience_goal: contextAwarenessEnabled ? currentGoalText : '' // Send goal only if enabled
            };
            console.log("Sending analysis request:", requestBody); // DEBUG

            try {
                const response = await fetch('/analyze', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(requestBody), // Use prepared body
                });

                if (!response.ok) {
                    // Try to get error message from response body
                    let errorMsg = `HTTP error! status: ${response.status}`;
                    try {
                        const errorData = await response.json();
                        errorMsg = errorData.error || errorMsg;
                    } catch (e) { /* Ignore parsing error */ }
                    throw new Error(errorMsg);
                }

                const data = await response.json();
                currentAnalysisData = data; // Store the FULL response
                console.log("Received analysis response:", currentAnalysisData); // DEBUG

                // Calculate metrics
                const endTime = performance.now();
                const analysisTime = Math.round(endTime - startTime);

                // Update UI using the full data object
                updateComplexityMeter(currentAnalysisData); // Pass full data (handles meter levels)
                updateReadabilityScores(currentAnalysisData); // Pass full data (handles score text)
                if (analysisTimeEl) analysisTimeEl.textContent = `${analysisTime}ms`;

                // --- NEW: Check if overall score is out of bounds ---
                isOverallScoreOutOfBounds = checkIfOutOfBounds(
                    currentAnalysisData?.readability_scores,
                    currentAnalysisData?.target_readability_scores
                );
                // console.log("Overall Score Out Of Bounds:", isOverallScoreOutOfBounds); // DEBUG

                // --- Explicitly apply visibility state AFTER data is processed ---
                applyGoalIndicatorVisibility();

                // --- Process Gemini Results (if available) ---
                if (currentAnalysisData && currentAnalysisData.gemini_analysis) {
                    console.log("Processing Gemini analysis results...");
                    applyGeminiHighlights(currentAnalysisData.gemini_analysis);
                    // TODO: Implement displayGeminiSynonyms(currentAnalysisData.gemini_analysis);
                } else {
                    // Clear any previous Gemini highlights if none were returned this time
                    clearGeminiHighlights();
                    console.log("No Gemini analysis results in response.");
                }
                // --- End Process Gemini Results ---

            } catch (error) {
                console.error('Error fetching analysis:', error);
                currentAnalysisData = null; // Clear data on error
                isOverallScoreOutOfBounds = false; // Reset flag on error
                updateComplexityMeter(null); // Reset meter
                updateReadabilityScores(null); // Reset scores
                clearGeminiHighlights(); // Clear Gemini highlights on error
                if (analysisTimeEl) analysisTimeEl.textContent = 'Error';
                // Map will be cleared in the finally block's updateDocumentMap call
            } finally {
                if (complexityLoadingEl) complexityLoadingEl.classList.add('hidden');
            }
        }

        // Apply statistical highlighting and update map based on potentially updated currentAnalysisData
        applyStatisticalHighlighting(currentAnalysisData?.results || []); // Renamed function
        updateDocumentMap(currentAnalysisData);
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
        // Clear only statistical highlights (background, standard underline)
        // Assume Gemini highlights use different formats/classes
        quill.formatText(0, quill.getLength(), 'background', false, 'api');
        quill.formatText(0, quill.getLength(), 'underline', false, 'api');
        // Consider clearing specific classes if needed, but avoid clearing Gemini classes

        // Check statistical highlighting toggle state
        if (!showHighlighting) {
            return; // Exit if statistical highlighting is turned off
        }

        if (!results) return; // Check if results exist

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

            if (startIndex !== undefined && length > 0) {
                // 1. Apply background color
                quill.formatText(startIndex, length, 'background', bgColor, 'api');

                // 2. Check conditions for underline
                let shouldApplyUnderline = false;
                if (showGoalIndicators && isOverallScoreOutOfBounds) {
                    if (deviationDirection === "high" && (color === "red" || color === "orange")) {
                        shouldApplyUnderline = true;
                    } else if (deviationDirection === "low" && color === "green") {
                        shouldApplyUnderline = true;
                    }
                }

                // --- DEBUGGING LOG ---
                if (result.index === 0) {
                    console.log(`Sentence ${result.index}: showGoalIndicators=${showGoalIndicators}, isOverallScoreOutOfBounds=${isOverallScoreOutOfBounds}, color=${color}, deviationDirection=${deviationDirection}, shouldApplyUnderline=${shouldApplyUnderline}`);
                }
                // --- END DEBUGGING LOG ---

                // Apply standard underline format if needed (remains the same)
                if (shouldApplyUnderline) {
                    quill.formatText(startIndex, length, 'underline', true, 'api');
                }
            } else {
                 console.warn(`Invalid indices received for statistical sentence analysis: start=${startIndex}, end=${endIndex}`);
            }
        });
    }

    // --- NEW: Apply Gemini Highlighting ---
    function applyGeminiHighlights(geminiData) {
        if (!geminiData) return;

        // Clear previous Gemini highlights (use specific formats/classes)
        clearGeminiHighlights(); // Call helper to clear

        // Example: Apply highlights for deviations (e.g., wavy red underline)
        if (geminiData.deviations && Array.isArray(geminiData.deviations)) {
            geminiData.deviations.forEach(deviation => {
                if (deviation.start !== undefined && deviation.end !== undefined) {
                    const length = deviation.end - deviation.start;
                    if (length > 0) {
                        // Apply a custom format or class for Gemini deviations
                        // Option 1: Use a custom blot (requires Quill modification)
                        // Option 2: Use inline style (less clean)
                        // Option 3: Use a CSS class (cleanest if CSS is set up)
                        // quill.formatText(deviation.start, length, 'gemini-deviation', true, 'api');
                        // For now, let's use a distinct background color as a placeholder
                        quill.formatText(deviation.start, length, 'background', 'rgba(255, 0, 0, 0.2)', 'api'); // Light red background
                        // Add tooltip with reason?
                        // quill.formatText(deviation.start, length, 'tooltip', deviation.reason, 'api'); // Needs custom tooltip blot
                        console.log(`Highlighting deviation: [${deviation.start}-${deviation.end}] Reason: ${deviation.reason}`);
                    }
                }
            });
        }

        // Example: Apply highlights for complexity mismatches (e.g., wavy blue underline)
        if (geminiData.complexity_mismatches && Array.isArray(geminiData.complexity_mismatches)) {
            geminiData.complexity_mismatches.forEach(mismatch => {
                 if (mismatch.start !== undefined && mismatch.end !== undefined) {
                    const length = mismatch.end - mismatch.start;
                    if (length > 0) {
                        // Apply a different format/class
                        // quill.formatText(mismatch.start, length, 'gemini-complexity', true, 'api');
                        quill.formatText(mismatch.start, length, 'background', 'rgba(0, 0, 255, 0.15)', 'api'); // Light blue background
                        console.log(`Highlighting complexity mismatch: [${mismatch.start}-${mismatch.end}] Reason: ${mismatch.reason}`);
                    }
                }
            });
        }

        // TODO: Handle Gemini synonyms - maybe add markers or integrate with tooltip
    }

    // --- NEW: Clear Gemini Highlighting ---
    function clearGeminiHighlights() {
        // Clear the specific formats/classes used by applyGeminiHighlights
        // quill.formatText(0, quill.getLength(), 'gemini-deviation', false, 'api');
        // quill.formatText(0, quill.getLength(), 'gemini-complexity', false, 'api');
        // For the placeholder backgrounds:
        // This is tricky as it might clear statistical highlights too if not careful.
        // A better approach is needed, perhaps using specific CSS classes via custom blots.
        // For now, we might accept that turning off Gemini clears all backgrounds.
        // Or, re-apply statistical highlights *after* clearing Gemini ones.
        console.log("Clearing Gemini highlights (placeholder - may need refinement)");
        // Let's assume for now re-applying statistical highlights handles this overlap.
    }

    // --- Visual Document Map Update ---
    // --- Visual Document Map Update (Modified) ---
    function updateDocumentMap(analysisData) { // Modified to accept full data
        const results = analysisData?.results; // Get results array from full data

        if (!documentMapContainer) return;
        documentMapContainer.innerHTML = ''; // Clear previous map segments and lines

        // --- Target Line Logic --- (Moved to applyGoalIndicatorVisibility)
        // if (documentMapContainer) {
        //      // Apply/remove class based on current toggle state
        //     documentMapContainer.classList.toggle('show-goal-indicator', showGoalIndicators);
        //      // CSS needs to handle the display based on this class
        //      // TODO: Add CSS rules for .document-map.show-goal-indicator::before or similar
        // }
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
        updateSensitivityLabel(parseInt(sensitivitySlider.value, 10)); // Initial label
        sensitivitySlider.addEventListener('input', (event) => {
            const newLevel = parseInt(event.target.value, 10);
            currentSensitivityLevel = newLevel;
            updateSensitivityLabel(newLevel);
            // Re-apply statistical highlighting based on new sensitivity
            applyStatisticalHighlighting(currentAnalysisData?.results || []);
            // Re-apply Gemini highlights (if any) - they aren't sensitivity-dependent currently
            applyGeminiHighlights(currentAnalysisData?.gemini_analysis);
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

    // --- Event Listeners ---

    // Define debounced function for analysis
    const debouncedAnalyze = debounce(() => analyzeAndHighlight(false), 750);
    // Define debounced function specifically for goal input changes
    const debouncedGoalAnalyze = debounce(() => {
        if (contextAwarenessEnabled) { // Only analyze if toggle is on
            analyzeAndHighlight(false);
        }
    }, 750);


    quill.on('text-change', (delta, oldDelta, source) => {
        if (source === 'user') {
            updateStats();
            debouncedAnalyze(); // Use the general debounced function
        }
    });

    // Target Audience Select Listener
    if (targetAudienceSelect) {
        targetAudienceSelect.addEventListener('change', (event) => {
            currentTargetAudience = event.target.value;
            analyzeAndHighlight(false); // Re-analyze with new audience profile
        });
        currentTargetAudience = targetAudienceSelect.value; // Initial state
    } else {
        console.warn("Target audience select element not found.");
    }

    // Toggle Statistical Highlighting Listener
    if (toggleHighlighting) {
        toggleHighlighting.addEventListener('change', (event) => {
            showHighlighting = event.target.checked;
            // Immediately apply/remove statistical highlighting
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
            // Re-apply statistical highlighting to add/remove underlines
            applyStatisticalHighlighting(currentAnalysisData?.results || []);
        });
        // Initial state set above
    } else {
        console.warn("Toggle goal indicators element not found.");
        showGoalIndicators = true; // Default
    }

    // --- NEW Context Awareness Listeners ---
    if (contextAwarenessToggle && goalContainer && goalInput) {
        // Initial state setup
        contextAwarenessEnabled = contextAwarenessToggle.checked;
        goalContainer.style.display = contextAwarenessEnabled ? 'block' : 'none';
        goalInput.disabled = !contextAwarenessEnabled;
        currentGoalText = goalInput.value; // Store initial goal text

        contextAwarenessToggle.addEventListener('change', (event) => {
            contextAwarenessEnabled = event.target.checked;
            goalContainer.style.display = contextAwarenessEnabled ? 'block' : 'none';
            goalInput.disabled = !contextAwarenessEnabled;
            console.log(`Context Awareness Toggled: ${contextAwarenessEnabled}`); // DEBUG

            if (contextAwarenessEnabled) {
                // Trigger analysis if enabled and goal text exists
                if (currentGoalText.trim()) {
                    analyzeAndHighlight(false);
                }
            } else {
                // Clear Gemini highlights and potentially re-apply statistical ones
                clearGeminiHighlights();
                applyStatisticalHighlighting(currentAnalysisData?.results || []);
                // Optionally clear the goal input?
                // goalInput.value = '';
                // currentGoalText = '';
            }
        });

        goalInput.addEventListener('input', (event) => {
            currentGoalText = event.target.value;
            // Use the specific debounced function for goal input
            debouncedGoalAnalyze();
        });

    } else {
        console.error("Context awareness toggle, container, or input element not found!");
    }

    // Add Tooltip for Context Awareness Info Icon
    if (contextAwarenessInfo && typeof tippy === 'function') {
        tippy(contextAwarenessInfo, {
            content: `<div class='text-left p-1 max-w-xs'>
                        <strong class='block mb-1 text-gray-100'>Context Awareness (via Gemini)</strong>
                        <p class='text-xs text-gray-300 mb-1'>When enabled, uses Google's Gemini AI to analyze the text based on your 'Target Audience Goal'.</p>
                        <ul class='list-disc list-inside text-xs space-y-0.5 text-gray-400'>
                            <li>Suggests context-aware synonyms.</li>
                            <li>Highlights sentences deviating from the goal (tone, style).</li>
                            <li>Highlights sentences too simple/complex for the goal.</li>
                        </ul>
                        <p class='text-xs text-gray-500 mt-1'>Requires a configured API Key and may incur costs.</p>
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
    setTimeout(() => analyzeAndHighlight(false), 100);

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

}); // End DOMContentLoaded
