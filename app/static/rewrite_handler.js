document.addEventListener('DOMContentLoaded', () => {
    function initializeRewriteHandler() {
        // Check if the main app object and necessary functions/data are available
        if (!window.typecomplexApp || 
            !window.typecomplexApp.quill || 
            !window.typecomplexApp.contextMenuTooltip ||
            typeof window.typecomplexApp.getCurrentAnalysisData !== 'function' ||
            typeof window.typecomplexApp.getCurrentTargetAudience !== 'function' ||
            typeof window.typecomplexApp.getUseFullRewriteContext !== 'function') {
            console.warn("Rewrite Handler: Main application resources not yet fully available. Retrying in 100ms.");
            setTimeout(initializeRewriteHandler, 100); // Retry after a short delay
            return;
        }

        console.log("Rewrite Handler: Main application resources are available. Initializing event listeners.");

        const quill = window.typecomplexApp.quill;
        const contextMenuTooltip = window.typecomplexApp.contextMenuTooltip;

        // Helper function to find sentence data at a given index
        function findSentenceAtQuillIndex(index) {
            const analysisData = window.typecomplexApp.getCurrentAnalysisData();
            if (!analysisData || !analysisData.sentences || analysisData.sentences.length === 0) {
                return null;
            }
            return analysisData.sentences.find(res => index >= res.start && index < res.end);
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
            // Base structure for the tooltip container with max height and scrolling
            let baseHtml = `<div class='rewrite-tooltip-content text-sm text-[var(--text-primary)] bg-[var(--sidebar-bg)] max-w-md
                               border border-[rgba(108,111,147,0.2)] rounded-[var(--border-radius)]
                               shadow-[0_4px_20px_rgba(0,0,0,0.15)] backdrop-blur-[10px] overflow-y-auto
                               flex flex-col max-h-[70vh]'>`; // Set max height to 70% of viewport

            if (!data) {
                return baseHtml + "<div class='p-3 text-sm text-red-400'>Error: Invalid response data.</div></div>";
            }
            if (data.error) {
                return baseHtml + `<div class='p-3 text-sm text-red-400'>Error: ${data.error}</div></div>`;
            }

            // Enhanced status indicators
            let statusConfig = {
                'Good': {
                    barClass: 'status-bar-good',
                    icon: `<svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                            <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd" />
                          </svg>`,
                    colorClass: 'text-green-500',
                    bgClass: 'bg-green-500/10'
                },
                'Consider changing': {
                    barClass: 'status-bar-consider', 
                    icon: `<svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                            <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
                          </svg>`,
                    colorClass: 'text-yellow-500',
                    bgClass: 'bg-yellow-500/10'
                },
                'Needs improvement': {
                    barClass: 'status-bar-improve',
                    icon: `<svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                            <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd" />
                          </svg>`,
                    colorClass: 'text-red-500', 
                    bgClass: 'bg-red-500/10'
                }
            };

            const config = statusConfig[data.status] || {
                barClass: 'status-bar-unknown',
                icon: '?',
                colorClass: 'text-gray-500',
                bgClass: 'bg-gray-500/10'
            };

            // Build HTML content with scrollable section
            let contentHtml = `
                <div class="status-bar ${config.barClass}"></div>
                <div class="p-4 ${config.bgClass} rounded-t-[var(--border-radius)] shrink-0">
                    <div class="flex items-baseline gap-2">
                        <span class="inline-block tooltip-status-icon ${config.colorClass}">${config.icon}</span>
                        <h3 class="font-semibold ${config.colorClass}">${data.status}</h3>
                    </div>
                </div>
                <div class="p-4 overflow-y-auto flex-1">
            `;

            // Feedback Section
            contentHtml += `<div class="mb-3">
                <h4 class="text-sm font-medium text-[var(--text-primary)] mb-1">Feedback</h4>
                <p class="text-sm text-gray-300">${data.feedback || 'No specific feedback provided.'}</p>
            </div>`;
            contentHtml += `<p class="mb-2 text-gray-300">${data.feedback || 'No specific feedback provided.'}</p>`;

            // Suggestion Section (Conditional)
            if (data.suggestion) {
                contentHtml += `
                    <div class="mb-3">
                        <hr class="tooltip-divider my-3">
                        <h4 class="text-sm font-medium text-[var(--text-primary)] mb-2">Suggestion</h4>
                        <div class="bg-[rgba(0,0,0,0.2)] rounded p-3 border border-[rgba(108,111,147,0.1)]">
                            <pre class="text-sm font-mono text-gray-200 whitespace-pre-wrap">${data.suggestion}</pre>
                        </div>
                    </div>
                `;
            }

            // Reasoning Section (Conditional)
            if (data.reasoning) {
                contentHtml += `
                    <div class="mb-3">
                        <hr class="tooltip-divider my-3">
                        <h4 class="text-sm font-medium text-[var(--text-primary)] mb-2">Reasoning</h4>
                        <p class="text-sm text-gray-400">${data.reasoning}</p>
                    </div>
                `;
            }

            // Action Buttons Section
            contentHtml += `<hr class="tooltip-divider my-3">`;
            contentHtml += `<div class="flex justify-end gap-3 mt-4">`;
            // Disable Apply button if there's no suggestion
            const applyDisabled = !data.suggestion ? 'disabled' : '';
            contentHtml += `
                <button class="rewrite-apply-btn px-3 py-1.5 text-sm rounded-md transition-colors
                    bg-[var(--accent-blue)] text-white hover:bg-[var(--accent-blue)]/90
                    focus:outline-none focus:ring-2 focus:ring-[var(--accent-blue)] focus:ring-offset-2
                    disabled:opacity-50 disabled:cursor-not-allowed" ${applyDisabled}>
                    Apply Suggestion
                </button>
                <button class="rewrite-dismiss-btn px-3 py-1.5 text-sm rounded-md transition-colors
                    bg-gray-600 text-gray-200 hover:bg-gray-500
                    focus:outline-none focus:ring-2 focus:ring-gray-500 focus:ring-offset-2">
                    Dismiss
                </button>
            `;
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
            const analysisDataForDebug = window.typecomplexApp.getCurrentAnalysisData(); // Get data for logging
            if (analysisDataForDebug) {
                if (analysisDataForDebug.sentences && analysisDataForDebug.sentences.length > 0) {
                    console.log("Rewrite Handler: Current analysisData.sentences for matching:", 
                        JSON.stringify(analysisDataForDebug.sentences.map(r => ({start: r.start, end: r.end, sentence_preview: r.sentence.substring(0, 30)}))) 
                    );
                } else {
                    console.log("Rewrite Handler: analysisData available, but .sentences is missing, empty, or invalid.", analysisDataForDebug);
                }
            } else {
                console.log("Rewrite Handler: getCurrentAnalysisData() returned null or undefined.");
            }

            const sentenceResult = findSentenceAtQuillIndex(index);

            if (!sentenceResult) {
                console.log("Rewrite Handler: No sentence found at click index."); // DEBUG
                contextMenuTooltip.hide(); // Hide if click wasn't on a known sentence
                return;
            }

            console.log("Rewrite Handler: Found sentence:", sentenceResult); // DEBUG

            // Gather data for the API call
            const sentenceText = sentenceResult.sentence;
            const complexityDetails = sentenceResult.complexity_factors;
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
                        complexity_analysis_details: complexityDetails
                    }),
                });

                if (!response.ok) {
                    let errorMessage;
                    let errorData = null;
                    try {
                        // Attempt to parse the error response body as JSON
                        errorData = await response.json();
                    } catch (jsonParseError) {
                        console.warn("Rewrite Handler: Could not parse error response as JSON for /rewrite_suggestion:", jsonParseError);
                        // errorData remains null, logic below will use status code for message
                    }

                    if (response.status === 429) {
                        errorMessage = "LLM Rewrite suggestion exceeded"; // User's desired custom message
                    } else if (errorData && errorData.error) {
                        errorMessage = errorData.error; // Use error message from JSON response
                    } else {
                        // Fallback generic error if no specific message is found
                        errorMessage = `Error processing rewrite: Status ${response.status}`;
                    }
                    throw new Error(errorMessage);
                }

                // If response.ok, parse the JSON for the success case
                // The response body has not been read yet at this point if response.ok was true
                const data = await response.json();

                // Update tooltip with formatted results
                         const formattedContent = formatRewriteResponse(data);
                contextMenuTooltip.setContent(formattedContent);

                // Refresh rate limits as a rewrite was attempted
                if (window.typecomplexApp && typeof window.typecomplexApp.refreshRateLimitsAfterRewrite === 'function') {
                    window.typecomplexApp.refreshRateLimitsAfterRewrite();
                } else {
                    console.warn("Rewrite Handler: refreshRateLimitsAfterRewrite function not available on window.typecomplexApp.");
                }

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
                                // Add a short delay to allow Quill to process the update before re-analyzing
                                setTimeout(() => {
                                    console.log("Rewrite Handler: Triggering analysis after apply (100ms delay)."); // DEBUG
                                    window.typecomplexApp.triggerAnalysis(true); // Re-analyze after applying change, force run
                                }, 100); // 100ms delay
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
                         if (contextMenuTooltip) {
                            contextMenuTooltip.setContent(formatRewriteResponse({ error: error.message }));
                         }
                         // No button listeners needed for error messages

                        // Refresh rate limits even if an error occurred (e.g. rate limit exceeded)
                        if (window.typecomplexApp && typeof window.typecomplexApp.refreshRateLimitsAfterRewrite === 'function') {
                            window.typecomplexApp.refreshRateLimitsAfterRewrite();
                        } else {
                            console.warn("Rewrite Handler: refreshRateLimitsAfterRewrite function not available on window.typecomplexApp during error handling.");
                        }
                     }
        });

        // --- Tooltip Dismissal Listener ---
        // Hide the context menu tooltip when clicking anywhere outside of it
        document.addEventListener('click', (event) => {
        	// Use the same logic as the synonym tooltip dismissal
        	if (contextMenuTooltip && contextMenuTooltip.state.isVisible) {
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
    }

    // Start the initialization attempt
    initializeRewriteHandler();
});
