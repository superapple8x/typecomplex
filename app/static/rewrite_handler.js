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
        // Base structure for the tooltip container
        let baseHtml = `<div class='rewrite-tooltip-content text-sm text-[var(--text-primary)] bg-[var(--sidebar-bg)] max-w-md
                           border border-[rgba(108,111,147,0.2)] rounded-[var(--border-radius)]
                           shadow-[0_4px_20px_rgba(0,0,0,0.15)] backdrop-blur-[10px] overflow-hidden'>`; // Added overflow-hidden

        if (!data) {
            return baseHtml + "<div class='p-3 text-sm text-red-400'>Error: Invalid response data.</div></div>";
        }
        if (data.error) {
            return baseHtml + `<div class='p-3 text-sm text-red-400'>Error: ${data.error}</div></div>`;
        }

        // Determine status variables based on data.status
        let statusBarClass = '';
        let icon = '';
        let statusColorClass = '';
        switch (data.status) {
            case 'Good':
                statusBarClass = 'status-bar-good';
                icon = '✓';
                statusColorClass = 'text-green-400';
                break;
            case 'Consider changing':
                statusBarClass = 'status-bar-consider';
                icon = '!';
                statusColorClass = 'text-yellow-400';
                break;
            case 'Needs improvement':
                statusBarClass = 'status-bar-improve';
                icon = '✗';
                statusColorClass = 'text-red-400';
                break;
            default: // Fallback for unexpected status
                statusBarClass = 'status-bar-unknown'; // You might want a default style
                icon = '?';
                statusColorClass = 'text-gray-400';
        }

        // Build HTML content
        let contentHtml = `<div class="status-bar ${statusBarClass}"></div>`; // Status bar at the top
        contentHtml += `<div class="p-3">`; // Padding container for content

        // Feedback Section
        contentHtml += `<strong class="block mb-1 ${statusColorClass}">${icon} Feedback</strong>`;
        contentHtml += `<p class="mb-2 text-gray-300">${data.feedback || 'No specific feedback provided.'}</p>`;

        // Suggestion Section (Conditional)
        if (data.suggestion) {
            contentHtml += `<hr class="tooltip-divider">`;
            contentHtml += `<strong class="block my-1">Suggestion</strong>`;
            // Use template literal for easier embedding of suggestion
            contentHtml += `<code class="block mb-2 p-2 bg-[rgba(0,0,0,0.2)] rounded text-gray-200 code-suggestion">${data.suggestion}</code>`;
        }

        // Reasoning Section (Conditional)
        if (data.reasoning) {
            contentHtml += `<hr class="tooltip-divider">`;
            contentHtml += `<strong class="block my-1">Reasoning</strong>`;
            contentHtml += `<p class="text-xs text-gray-500">${data.reasoning}</p>`;
        }

        // Action Buttons Section
        contentHtml += `<hr class="tooltip-divider">`;
        contentHtml += `<div class="flex justify-end gap-2 mt-2">`;
        // Disable Apply button if there's no suggestion
        const applyDisabled = !data.suggestion ? 'disabled' : '';
        contentHtml += `<button class="rewrite-apply-btn" ${applyDisabled}>Apply</button>`;
        contentHtml += `<button class="rewrite-dismiss-btn">✕</button>`;
        contentHtml += `</div>`; // Close button container

        contentHtml += `</div>`; // Close padding container

        return baseHtml + contentHtml + `</div>`; // Combine base and content
    }

    // --- Right-Click (Context Menu) Listener ---
    quill.root.addEventListener('contextmenu', async (event) => {
        event.preventDefault(); // Prevent the default browser context menu

        // Get Quill index from the current text cursor position or selection
              const selection = quill.getSelection(true); // true ensures we get selection even if editor isn't focused
      
              if (!selection) {
                  console.warn("Rewrite Handler: Cannot get cursor position or selection.");
                  contextMenuTooltip.hide(); // Hide if we can't determine position
                  return;
              }
      
              // Use the index where the selection starts (cursor position if length is 0)
              const index = selection.index;

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
                     // Simple loading message (no close button)
            content: `<div class='rewrite-tooltip-content p-3 text-sm text-gray-400 bg-[var(--sidebar-bg)] max-w-md
                                    border border-[rgba(108,111,147,0.2)] rounded-[var(--border-radius)] shadow-[0_4px_20px_rgba(0,0,0,0.15)] backdrop-blur-[10px]'>
                                    <div>Loading rewrite suggestion...</div></div>`
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
                     const formattedContent = formatRewriteResponse(data);
            contextMenuTooltip.setContent(formattedContent);

            // --- Add Event Listeners for Apply/Dismiss Buttons ---
            // Use setTimeout to ensure the DOM is updated before querying
            setTimeout(() => {
                const tooltipElement = contextMenuTooltip.popper; // Get the Tippy instance's popper element
                if (!tooltipElement) return;

                const applyBtn = tooltipElement.querySelector('.rewrite-apply-btn');
                const dismissBtn = tooltipElement.querySelector('.rewrite-dismiss-btn');

                if (applyBtn) {
                    applyBtn.addEventListener('click', () => {
                        if (applyBtn.disabled) return; // Don't do anything if disabled

                        const suggestion = data.suggestion;
                        if (!suggestion || !sentenceResult) return; // Safety check

                        // Calculate range of the original sentence
                        const range = { index: sentenceResult.start, length: sentenceResult.end - sentenceResult.start };

                        // Get current selection *before* replacing to potentially restore later
                        // const currentSelection = quill.getSelection(); // Might not be reliable to restore exactly

                        // Perform the replacement
                        quill.deleteText(range.index, range.length, 'user');
                        quill.insertText(range.index, suggestion, 'user');

                        // Place cursor at the end of the newly inserted text
                        quill.setSelection(range.index + suggestion.length, 0, 'user');

                        // Optional: Add a brief visual feedback (e.g., flash)
                        tooltipElement.classList.add('applied-flash');
                        setTimeout(() => tooltipElement.classList.remove('applied-flash'), 300); // Remove after 300ms

                        contextMenuTooltip.hide();
                        // Call the newly exposed function from script.js
                        if (window.typecomplexApp && typeof window.typecomplexApp.triggerAnalysis === 'function') {
                            window.typecomplexApp.triggerAnalysis(); // Re-analyze after applying change
                        } else {
                            console.error("Rewrite Handler: Could not find window.typecomplexApp.triggerAnalysis function.");
                        }
                    });
                }

                if (dismissBtn) {
                    dismissBtn.addEventListener('click', () => {
                        contextMenuTooltip.hide();
                    });
                }
            }, 0); // setTimeout 0 ensures it runs after the current execution stack

                 } catch (error) {
                     console.error('Rewrite Handler: Error fetching rewrite suggestion:', error);
                     // Format error message using the same function
                     contextMenuTooltip.setContent(formatRewriteResponse({ error: error.message }));
                     // No button listeners needed for error messages
                 }
    });

    // --- Tooltip Dismissal Listener ---
    // Hide the context menu tooltip when clicking anywhere outside of it
    document.addEventListener('click', (event) => {
    	// Use the same logic as the synonym tooltip dismissal
    	if (contextMenuTooltip.state.isVisible) {
               const target = event.target;
               const tooltipElement = contextMenuTooltip.popperInstance?.popper; // The actual tooltip DOM element
   
               // Check if the click target is the close button OR if the click is outside the tippy-box
               const isCloseButtonClick = target.classList.contains('rewrite-tooltip-close-btn');
               const isClickOutsideTippyBox = !target.closest('.tippy-box'); // Check if click is outside the main tippy container
   
               if (!isCloseButtonClick && isClickOutsideTippyBox) {
                    // Hide if the click was outside the tippy box and wasn't the close button itself
                    // (The close button's own listener handles its clicks)
                    console.log("Hiding context menu tooltip due to outside click."); // DEBUG
                    contextMenuTooltip.hide();
               } else if (isCloseButtonClick) {
                   // The close button has its own dedicated listener set via setTimeout,
                   // so we don't strictly need to do anything here, but adding a log for clarity.
                   console.log("Close button clicked (handled by its own listener)."); // DEBUG
               }
           }
    }, true); // Use capture phase to catch clicks early

    console.log("Rewrite Handler: Initialized successfully."); // DEBUG
});