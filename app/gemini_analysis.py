import os
import google.generativeai as genai
from dotenv import load_dotenv
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables from .env file
load_dotenv()

# Configure the Gemini API client
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    logging.error("GEMINI_API_KEY not found in environment variables. Please set it in a .env file.")
    # Optionally raise an error or handle this case appropriately
    # raise ValueError("GEMINI_API_KEY not found.")
    genai.configure(api_key="DUMMY_KEY_FOR_INITIALIZATION") # Configure with a dummy key to avoid crash
else:
    genai.configure(api_key=api_key)

# Initialize the Generative Model (e.g., gemini-pro)
# Consider making the model name configurable if needed
try:
    # Use a model that supports function calling or structured output if possible
    # For text generation, 'gemini-1.5-flash' or 'gemini-pro' are good choices.
    model = genai.GenerativeModel('gemini-1.5-flash')
    logging.info("Gemini model initialized successfully.")
except Exception as e:
    logging.error(f"Failed to initialize Gemini model: {e}")
    model = None # Ensure model is None if initialization fails

def analyze_with_gemini(text: str, target_audience_goal: str):
    """
    Analyzes the text using the Gemini API based on the target audience goal.

    Args:
        text: The input text to analyze.
        target_audience_goal: A description of the target audience and goal.

    Returns:
        A dictionary containing the analysis results (synonyms, deviations, complexity)
        or None if the analysis fails or the API key is missing.
        Example structure:
        {
            "synonyms": [{"original_word": "utilize", "suggestions": ["use", "employ"], "start": 10, "end": 17, "reason": "Simpler alternative"}],
            "deviations": [{"sentence": "...", "start": 50, "end": 100, "reason": "Tone mismatch"}],
            "complexity_mismatches": [{"sentence": "...", "start": 150, "end": 200, "reason": "Too complex for target audience"}]
        }
    """
    if not api_key or api_key == "DUMMY_KEY_FOR_INITIALIZATION":
        logging.warning("Gemini API key is missing or invalid. Skipping Gemini analysis.")
        return None
    if not model:
        logging.error("Gemini model not initialized. Skipping Gemini analysis.")
        return None
    if not text or not text.strip():
        logging.warning("Input text is empty. Skipping Gemini analysis.")
        return None
    if not target_audience_goal or not target_audience_goal.strip():
        logging.warning("Target audience goal is empty. Skipping Gemini analysis.")
        return None

    logging.info(f"Starting Gemini analysis for goal: {target_audience_goal}")

    # --- Construct the Prompt ---
    # Combine requests into a single prompt for efficiency, asking for structured output.
    # We need start/end indices for highlighting, so we need to ensure Gemini provides them.
    # This might require careful prompt engineering or function calling if the model supports it well.
    # Example prompt structure (adjust based on model capabilities):
    prompt = f"""
Analyze the following text based on the target audience goal: "{target_audience_goal}".

Text:
---
{text}
---

Provide the analysis in JSON format with the following keys:
1.  "synonyms": A list of objects. Each object should represent a word in the original text that could be improved for the target audience. Include:
    *   "original_word": The word from the text.
    *   "suggestions": A list of 1-3 suitable synonym suggestions.
    *   "start": The starting character index of the original word in the text.
    *   "end": The ending character index of the original word in the text.
    *   "reason": A brief explanation why the word might be unsuitable and why the suggestions fit better.
2.  "deviations": A list of objects. Each object should represent a sentence that deviates significantly from the target audience goal (e.g., tone, style, assumed knowledge). Include:
    *   "sentence": The full sentence text.
    *   "start": The starting character index of the sentence in the text.
    *   "end": The ending character index of the sentence in the text.
    *   "reason": A brief explanation of the deviation.
3.  "complexity_mismatches": A list of objects. Each object should represent a sentence that is significantly too simple or too complex for the target audience goal. Include:
    *   "sentence": The full sentence text.
    *   "start": The starting character index of the sentence in the text.
    *   "end": The ending character index of the sentence in the text.
    *   "reason": A brief explanation (e.g., "Too complex due to jargon", "Too simple, lacks detail").

Ensure all start/end indices accurately reflect the positions in the original text provided above. If no issues are found for a category, provide an empty list for that key. Output only the JSON object.
"""

    # --- Make the API Call ---
    try:
        logging.info("Sending request to Gemini API...")
        # Configure safety settings if needed
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        ]
        response = model.generate_content(
            prompt,
            safety_settings=safety_settings,
            generation_config=genai.types.GenerationConfig(
                # candidate_count=1, # Default is 1
                # stop_sequences=['...'], # Optional stop sequences
                # max_output_tokens=..., # Optional token limit
                temperature=0.5 # Adjust temperature for creativity vs consistency
            )
        )
        logging.info("Received response from Gemini API.")

        # --- Parse the Response ---
        # Check for safety blocks or empty response
        if not response.candidates:
             logging.warning("Gemini response blocked or empty. No candidates found.")
             return {"synonyms": [], "deviations": [], "complexity_mismatches": [], "error": "Response blocked or empty"}

        # Extract the text content - handle potential errors if 'text' attribute isn't there
        try:
            raw_json_response = response.text
        except ValueError:
            # Handle cases where the response might be blocked due to safety
            logging.warning(f"Gemini response might be blocked. Prompt feedback: {response.prompt_feedback}")
            # You might want to return specific info about the block
            block_reason = "Unknown"
            if response.prompt_feedback and response.prompt_feedback.block_reason:
                block_reason = response.prompt_feedback.block_reason.name
            return {"synonyms": [], "deviations": [], "complexity_mismatches": [], "error": f"Response blocked due to {block_reason}"}
        except AttributeError:
             logging.error("Unexpected Gemini response format. 'text' attribute missing.")
             return {"synonyms": [], "deviations": [], "complexity_mismatches": [], "error": "Unexpected response format"}


        # Clean the response: Gemini might sometimes include markdown backticks
        cleaned_json_response = raw_json_response.strip().strip('```json').strip('```').strip()

        # Attempt to parse the JSON
        try:
            analysis_results = json.loads(cleaned_json_response)
            # Basic validation of the structure
            if not all(k in analysis_results for k in ["synonyms", "deviations", "complexity_mismatches"]):
                logging.warning("Gemini response JSON missing expected keys.")
                # Attempt to return partial data or indicate error
                return {"synonyms": analysis_results.get("synonyms", []),
                        "deviations": analysis_results.get("deviations", []),
                        "complexity_mismatches": analysis_results.get("complexity_mismatches", []),
                        "error": "JSON structure incomplete"}
            logging.info("Successfully parsed Gemini JSON response.")
            return analysis_results
        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse Gemini response as JSON: {e}")
            logging.debug(f"Raw Gemini response:\n{raw_json_response}")
            # Return an error structure or None
            return {"synonyms": [], "deviations": [], "complexity_mismatches": [], "error": "Failed to parse response JSON"}

    except Exception as e:
        logging.error(f"An error occurred during Gemini API call or processing: {e}")
        # Return an error structure or None
        return {"synonyms": [], "deviations": [], "complexity_mismatches": [], "error": f"API call failed: {e}"}

# Example usage (for testing)
if __name__ == '__main__':
    # Ensure you have a .env file with GEMINI_API_KEY in the project root
    test_text_example = """
    To commence, we must first instantiate the requisite operational parameters. Subsequently, the system effectuates data assimilation. This is quite easy. Finally, the derived metrics are promulgated to stakeholders. It's super important for business folks.
    """
    test_goal_example = "Explain the process clearly to a non-technical manager."

    if api_key and api_key != "DUMMY_KEY_FOR_INITIALIZATION" and model:
        print(f"--- Testing Gemini Analysis ---")
        print(f"Goal: {test_goal_example}")
        results = analyze_with_gemini(test_text_example, test_goal_example)
        if results:
            print("\nAnalysis Results:")
            print(json.dumps(results, indent=2))
        else:
            print("\nGemini analysis failed or was skipped.")
    else:
        print("\nSkipping Gemini analysis test: API key or model not configured.")
