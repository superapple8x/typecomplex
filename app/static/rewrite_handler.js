document.addEventListener('DOMContentLoaded', () => {
    // Check if the main app object is available
    if (!window.typecomplexApp || !window.typecomplexApp.quill) {
        console.error("Rewrite Handler: Main application resources (window.typecomplexApp) not found. Ensure script.js loads first and exposes resources.");
        return;
    }

    const quill = window.typecomplexApp.quill;
    const contextMenuTooltip = window.typecomplexApp.contextMenuTooltip; // Use the shared tooltip instance

    // Helper function to find sentence data at a given index
    function findSentenceAtQuillIndex(index) {
        const analysisData = window.typecomplexApp.getCurrentAnalysisData();
        if (!analysisData || !analysisData.results) {
            return null;
        }
        return analysisData.results.find(res => index >= res.start && index < res.end);
    }

    // Helper function to get context based on mode
    function getContextForRewrite(sentenceResult, useFullContext) {
        if (useFullContext) {
            return quill.getText(); // Return full document text
        } else {
            // Partial context: Use the sentence text itself for now
            // Could be expanded later to include surrounding sentences if needed
            return sentenceResult.sentence;
        }
    }

    // Helper function to format the API response for the tooltip
    function formatRewriteResponse(data) {
        if (!data) return "<div class='p-2 text-sm text-red-400'>Error: Invalid response data.</div>";
        if (data.error) return `<div class='p-2 text-sm text-red-400'>Error: ${data.error}</div>`;

        let html = `<div class='p-3 text-sm text-[var(--text-primary)] bg-[var(--sidebar-bg)] max-w-md
                           border border-[rgba(108,111,147,0.2)] rounded-[var(--border-radius)]
                           shadow-[0_4px_20px_rgba(0,0,0,0.15)] backdrop-blur-[10px]'>`;

        if (data.is_sufficient) {
            html += `<strong class='block mb-1 text-green-400'>Suggestion:</strong>`;
            html += `<p class='mb-2 text-gray-300'>${data.feedback || 'The original sentence is suitable.'}</p>`;
        } else {
            html += `<strong class='block mb-1 text-yellow-400'>Suggestion:</strong>`;
            if (data.feedback) {
                html += `<p class='mb-1 text-gray-400 italic'>Feedback: ${data.feedback}</p>`;
            }
            if (data.suggestion) {
                html += `<p class='mb-2 p-2 bg-[rgba(0,0,0,0.2)] rounded text-gray-200'>${data.suggestion}</p>`;
            } else {
                 html += `<p class='mb-2 text-gray-400 italic'>No specific rewrite suggested, but feedback provided above.</p>`;
            }
            if (data.reasoning) {
                html += `<p class='text-xs text-gray-500'>Reasoning: ${data.reasoning}</p>`;
            }
        }
        html += `</div>`;
        return html;
    }

    // --- Right-Click (Context Menu) Listener ---
    quill.root.addEventListener('contextmenu', async (event) => {
        event.preventDefault(); // Prevent the default browser context menu

        // Get Quill index from click position
        // This might need refinement depending on browser compatibility
        let index;
        if (document.caretPositionFromPoint) {
            const range = document.caretPositionFromPoint(event.clientX, event.clientY);
            index = range.offset;
            // Adjust index based on the container offset if necessary (complex)
            // For simplicity, let's assume the offset is relative to the start of the text node
            // We might need Quill's own methods if this isn't reliable
            const leaf = quill.getLeaf(index)[0];
            if (leaf) {
                 index = quill.getIndex(leaf) + range.offset; // Try to get absolute index
            } else {
                 console.warn("Rewrite Handler: Could not find leaf at click position.");
                 // Fallback: Get selection index if text is selected
                 const selection = quill.getSelection();
                 if (selection) {
                     index = selection.index;
                 } else {
                     contextMenuTooltip.hide(); // Hide if we can't determine position
                     return;
                 }
            }

        } else { // Fallback for browsers without caretPositionFromPoint
             const selection = quill.getSelection();
             if (selection) {
                 index = selection.index; // Use selection start if available
             } else {
                 console.warn("Rewrite Handler: Cannot determine click index (caretPositionFromPoint not supported and no selection).");
                 contextMenuTooltip.hide();
                 return;
             }
        }

        console.log(`Rewrite Handler: Right-click detected at approximate index: ${index}`); // DEBUG

        // Find the sentence data corresponding to the click index
        const sentenceResult = findSentenceAtQuillIndex(index);

        if (!sentenceResult) {
            console.log("Rewrite Handler: No sentence found at click index."); // DEBUG
            contextMenuTooltip.hide(); // Hide if click wasn't on a known sentence
            return;
        }

        console.log("Rewrite Handler: Found sentence:", sentenceResult); // DEBUG

        // Gather data for the API call
        const sentenceText = sentenceResult.sentence;
        const complexityScore = sentenceResult.score;
        const targetAudience = window.typecomplexApp.getCurrentTargetAudience();
        const useFullContext = window.typecomplexApp.getUseFullRewriteContext();
        const surroundingContext = getContextForRewrite(sentenceResult, useFullContext);

        // --- Show Loading Tooltip ---
        // Get bounds relative to the viewport for positioning
        const clickBounds = {
            top: event.clientY,
            bottom: event.clientY,
            left: event.clientX,
            right: event.clientX,
            width: 0,
            height: 0,
        };

        contextMenuTooltip.setProps({
            getReferenceClientRect: () => clickBounds,
            placement: 'right-start', // Or adjust as needed
            content: "<div class='p-2 text-sm text-gray-400'>Loading rewrite suggestion...</div>"
        });
        contextMenuTooltip.show();

        // --- API Call ---
        try {
            const response = await fetch('/rewrite_suggestion', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    sentence_text: sentenceText,
                    surrounding_context: surroundingContext,
                    target_audience: targetAudience,
                    complexity_score: complexityScore
                }),
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || `HTTP error! status: ${response.status}`);
            }

            // Update tooltip with formatted results
            contextMenuTooltip.setContent(formatRewriteResponse(data));

        } catch (error) {
            console.error('Rewrite Handler: Error fetching rewrite suggestion:', error);
            contextMenuTooltip.setContent(`<div class='p-2 text-sm text-red-400'>Error: ${error.message}</div>`);
        }
    });

    // --- Tooltip Dismissal Listener ---
    // Hide the context menu tooltip when clicking anywhere outside of it
    document.addEventListener('click', (event) => {
        if (contextMenuTooltip.state.isVisible) {
            const tooltipElement = contextMenuTooltip.popperInstance ? contextMenuTooltip.popperInstance.popper : null;
            // Check if the click was outside the tooltip itself
            if (tooltipElement && !tooltipElement.contains(event.target)) {
                 // Also check if the click wasn't on the original trigger element (though tricky with contextmenu)
                 // For simplicity, just hide if click is outside the tooltip popper
                 contextMenuTooltip.hide();
            }
        }
    }, true); // Use capture phase to catch clicks early

    console.log("Rewrite Handler: Initialized successfully."); // DEBUG
});