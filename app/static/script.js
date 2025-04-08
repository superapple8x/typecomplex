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
    // const overallComplexityScoreEl = document.getElementById('overall-complexity-score'); // No longer used
    const complexityLevelDivs = document.querySelectorAll('#overall-complexity-meter .complexity-level');
    const complexityDescriptionEl = document.getElementById('complexity-description');

    // --- Quill Initialization ---
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
        // Hide on click outside
        hideOnClick: true, // 'toggle' might be better depending on UX preference
        // We'll set reference client rect dynamically
    });

    // --- Complexity Color Mapping (Dark Theme) ---
    // Using semi-transparent background colors suitable for dark editor
    const complexityBackgrounds = {
        green: 'rgba(40, 167, 69, 0.3)',   // Semi-transparent green
        yellow: 'rgba(255, 193, 7, 0.3)',  // Semi-transparent yellow
        orange: 'rgba(253, 126, 20, 0.3)', // Semi-transparent orange
        red: 'rgba(220, 53, 69, 0.3)',    // Semi-transparent red
        gray: 'rgba(108, 117, 125, 0.2)', // Semi-transparent gray
    };

    // --- State for Analysis ---
    let currentAnalysisResults = []; // Store results to map sentences

    // --- Stats Calculation ---
    function updateStats() {
        console.log("updateStats called"); // DEBUG
        const text = quill.getText();
        const trimmedText = text.trim();
        console.log("Text length:", text.length, "Trimmed text:", trimmedText.substring(0, 50) + "..."); // DEBUG

        // Word Count (simple split)
        const words = trimmedText ? trimmedText.split(/\s+/) : [];
        console.log("Word count element:", wordCountEl); // DEBUG
        if (wordCountEl) wordCountEl.textContent = words.length;
        console.log("Calculated words:", words.length); // DEBUG

        // Character Count
        const charCount = text.length > 0 ? text.length - 1 : 0;
        console.log("Character count element:", characterCountEl); // DEBUG
        if (characterCountEl) characterCountEl.textContent = charCount;
        console.log("Calculated characters:", charCount); // DEBUG

        // Sentence Count (simple regex - adjust if more complex rules needed)
        // Match '.', '?', '!' possibly followed by whitespace and not preceded by another punctuation
        const sentences = trimmedText ? trimmedText.match(/[^.!?]+[.!?]+/g) : [];
        const sentenceCount = sentences ? sentences.length : 0;
        console.log("Sentence count element:", sentenceCountEl); // DEBUG
        if (sentenceCountEl) sentenceCountEl.textContent = sentenceCount;
        console.log("Calculated sentences:", sentenceCount); // DEBUG
    }

    // --- Complexity Meter Update ---
    function updateComplexityMeter(levelData) {
        const defaultColor = 'bg-gray-600'; // Default color for inactive levels
        const levelColors = { // Map each level to its specific color
            1: 'bg-green-500',
            2: 'bg-lime-500',
            3: 'bg-yellow-500',
            4: 'bg-orange-500',
            5: 'bg-red-500'
        };

        const currentLevel = levelData ? levelData.level : 0;
        const description = levelData ? levelData.description : 'Enter text to analyze';

        complexityLevelDivs.forEach(div => {
            const divLevel = parseInt(div.dataset.level, 10);
            // Remove all potential color classes first to reset
            div.classList.remove(...Object.values(levelColors), defaultColor);

            // Apply the correct color based on whether this level is active
            // Apply the correct color based on whether this level is active
            let colorToAdd = defaultColor; // Start with default
            if (divLevel <= currentLevel) {
                // If active, use the color specific to this div's level
                colorToAdd = levelColors[divLevel];
            } else {
                // Apply the inactive color
            }
            div.classList.add(colorToAdd);
        });

        if (complexityDescriptionEl) {
            complexityDescriptionEl.textContent = description;
        }
    }

    // --- Analysis & Highlighting ---
    async function analyzeAndHighlight() {
        const text = quill.getText();
        if (!text.trim()) {
            // Clear formatting if text is empty
            quill.formatText(0, quill.getLength(), 'background', false, 'api');
            currentAnalysisResults = [];
            // Reset complexity meter to default state
            updateComplexityMeter(null); // Pass null or a default object
            return;
        }

        try {
            const response = await fetch('/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: text }),
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            currentAnalysisResults = data.results || [];

            // Apply sentence highlighting
            applyHighlighting(currentAnalysisResults);

            // Update overall complexity meter display
            updateComplexityMeter(data.overall_level);

        } catch (error) {
            console.error('Error fetching analysis:', error);
            // Optionally show an error state in the UI (e.g., update meter description)
            updateComplexityMeter({level: 0, description: "Analysis Error", color_class: "bg-red-700"});
        }
    }

    function applyHighlighting(results) {
        // Clear previous background formatting first
        quill.formatText(0, quill.getLength(), 'background', false, 'api'); // 'api' source prevents adding to undo stack

        const editorText = quill.getText();
        let currentIndex = 0;

        results.forEach(result => {
            const sentenceText = result.sentence;
            const color = result.color;
            const bgColor = complexityBackgrounds[color] || complexityBackgrounds['gray'];

            // Find the sentence in the current editor text
            // This assumes sentences from backend match substrings in editor text
            const startIndex = editorText.indexOf(sentenceText, currentIndex);

            if (startIndex !== -1) {
                const length = sentenceText.length;
                // Apply background color using inline style formatting
                quill.formatText(startIndex, length, 'background', bgColor, 'api');
                currentIndex = startIndex + length; // Move search position forward
            } else {
                console.warn(`Could not find sentence in editor: "${sentenceText.substring(0, 30)}..."`);
            }
        });
    }

    // Debounced version for performance
    const debouncedAnalyzeAndHighlight = debounce(analyzeAndHighlight, 750); // Adjust delay as needed (ms)

    // --- Synonym Tooltip ---
    async function showSynonymTooltip(range) {
        if (!range || range.length === 0) {
            synonymTooltip.hide();
            return;
        }

        const selectedText = quill.getText(range.index, range.length).trim();

        // Basic check if it's likely a single word
        if (!selectedText || selectedText.includes(' ') || !/^[a-zA-Z]+$/.test(selectedText)) {
             synonymTooltip.hide();
             return;
        }

        const bounds = quill.getBounds(range.index, range.length);
        if (!bounds) {
             synonymTooltip.hide();
             return;
        }

        // Update tooltip position reference and show loading state
        synonymTooltip.setProps({
            getReferenceClientRect: () => bounds,
            content: 'Loading synonyms...',
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

            // Build tooltip content
            let contentHTML = `<div class="p-1 text-xs dark:text-gray-200">`;
            if (data.synonyms && data.synonyms.length > 0) {
                contentHTML += `<strong class="block mb-1">Synonyms for "${selectedText}"</strong>`;
                contentHTML += `<ul class="list-none p-0 m-0">`;

                const rankClasses = {
                    1: 'bg-green-600', 2: 'bg-lime-600', 3: 'bg-yellow-600',
                    4: 'bg-orange-600', 5: 'bg-red-600',
                };
                const badgeBaseClass = 'inline-block w-4 h-4 mr-1.5 text-xs font-bold text-white rounded-sm text-center leading-4';

                data.synonyms.forEach(syn => {
                    const rankClass = rankClasses[syn.rank] || 'bg-gray-500';
                    contentHTML += `<li class="mb-0.5"><span class="${badgeBaseClass} ${rankClass}">${syn.rank}</span>${syn.word}</li>`;
                });
                contentHTML += `</ul>`;
            } else {
                contentHTML += `No synonyms found for "${selectedText}".`;
            }
            contentHTML += `</div>`;

            synonymTooltip.setContent(contentHTML);

        } catch (error) {
            console.error('Error fetching synonyms:', error);
            synonymTooltip.setContent(`<div class="p-1 text-xs text-red-500">Error loading synonyms.</div>`);
        }
    }

    // --- Event Listeners ---
    quill.on('text-change', (delta, oldDelta, source) => {
        if (source === 'user') {
            updateStats();
            debouncedAnalyzeAndHighlight();
        }
    });

    quill.on('selection-change', (range, oldRange, source) => {
        if (source === 'user') {
            if (range && range.length > 0) {
                // Delay slightly to allow selection to finalize
                setTimeout(() => showSynonymTooltip(quill.getSelection()), 50);
            } else {
                synonymTooltip.hide();
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

}); // End DOMContentLoaded