import os
import google.generativeai as genai
from dotenv import load_dotenv
import json
import logging
# Import AUDIENCE_PROFILES to get profile details
from app.analysis import AUDIENCE_PROFILES

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables from .env file
load_dotenv()

# --- Gemini API Configuration ---
api_key = os.getenv("GEMINI_API_KEY")
model = None # Initialize model variable

if not api_key:
    logging.error("GEMINI_API_KEY not found in environment variables. Please set it in a .env file.")
    # Configure with a dummy key to avoid crashing other parts if API key is missing
    try:
        genai.configure(api_key="DUMMY_KEY_FOR_INITIALIZATION")
    except Exception as e:
        logging.error(f"Error configuring Gemini with dummy key: {e}")
else:
    try:
        genai.configure(api_key=api_key)
        # Initialize the Generative Model
        # Using a model known for instruction following and JSON output is good.
        model = genai.GenerativeModel('gemini-1.5-flash') # Or 'gemini-pro'
        logging.info("Gemini model initialized successfully.")
    except Exception as e:
        logging.error(f"Failed to initialize Gemini model with API key: {e}")
        model = None # Ensure model is None if initialization fails

# --- Helper Function for API Calls ---
def _call_gemini_api(prompt: str):
    """Internal helper to make API call and handle basic response parsing/errors."""
    if not api_key or api_key == "DUMMY_KEY_FOR_INITIALIZATION":
        logging.warning("Gemini API key is missing or invalid. Skipping Gemini call.")
        return {"error": "API key missing or invalid"}
    if not model:
        logging.error("Gemini model not initialized. Skipping Gemini call.")
        return {"error": "Model not initialized"}

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
            generation_config=genai.types.GenerationConfig(temperature=0.5)
        )
        logging.info("Received response from Gemini API.")

        # Check for safety blocks or empty response
        if not response.candidates:
             logging.warning("Gemini response blocked or empty. No candidates found.")
             return {"error": "Response blocked or empty"}

        # Extract and clean JSON response
        try:
            raw_json_response = response.text
            cleaned_json_response = raw_json_response.strip().strip('```json').strip('```').strip()
            analysis_results = json.loads(cleaned_json_response)
            logging.info("Successfully parsed Gemini JSON response.")
            return analysis_results
        except (ValueError, AttributeError) as e: # Handle block reason or missing 'text'
            logging.warning(f"Gemini response might be blocked or format error: {e}")
            block_reason = "Unknown"
            try: # Try to get block reason if available
                if response.prompt_feedback and response.prompt_feedback.block_reason:
                    block_reason = response.prompt_feedback.block_reason.name
            except Exception: pass # Ignore errors getting block reason
            return {"error": f"Response blocked or format error (Reason: {block_reason})"}
        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse Gemini response as JSON: {e}")
            logging.debug(f"Raw Gemini response:\n{raw_json_response}")
            return {"error": "Failed to parse response JSON"}

    except Exception as e:
        logging.error(f"An error occurred during Gemini API call or processing: {e}", exc_info=True)
        return {"error": f"API call failed: {e}"}

# --- Function to Enhance Sentence Complexity Analysis ---
def enhance_sentence_complexity(sentence: str, statistical_score: float, target_audience_profile: str):
    """
    Uses Gemini to provide contextual feedback on a sentence's complexity,
    considering its statistical score and the target audience profile.

    Args:
        sentence: The sentence text.
        statistical_score: The pre-calculated statistical complexity score.
        target_audience_profile: Name of the target audience profile.

    Returns:
        A dictionary with LLM feedback (e.g., adjusted assessment, reason, suggestion)
        or an error dictionary.
        Example: {"assessment": "Slightly too complex", "reason": "Uses jargon 'effectuates'", "suggestion": "Consider replacing 'effectuates' with 'performs'"}
    """
    if not sentence or not sentence.strip():
        return {"error": "Input sentence is empty"}

    # Fetch profile details for the prompt
    profile_details = AUDIENCE_PROFILES.get(target_audience_profile)
    if not profile_details:
        profile_description = f"a '{target_audience_profile}' audience"
    else:
        # Construct a description string (similar to previous version)
        target_readability = profile_details.get('target_readability', {})
        fk_target = target_readability.get('flesch_kincaid_grade')
        gf_target = target_readability.get('gunning_fog')
        readability_info = []
        if fk_target: readability_info.append(f"target Flesch-Kincaid Grade: {fk_target[0]}{f'-{fk_target[1]}' if fk_target[1] else '+'}")
        if gf_target: readability_info.append(f"target Gunning Fog: {gf_target[0]}{f'-{gf_target[1]}' if gf_target[1] else '+'}")
        profile_description = f"a '{target_audience_profile}' audience"
        if readability_info: profile_description += f" (aiming for {', '.join(readability_info)})"

    logging.info(f"Requesting Gemini complexity enhancement for profile: {target_audience_profile}")

    prompt = f"""
Analyze the following sentence considering the target audience is {profile_description}.
A statistical analysis already assigned this sentence a complexity score of {statistical_score:.3f} (higher means more complex based on length, word frequency etc.).

Sentence:
---
{sentence}
---

Based *only* on the sentence text and the target audience profile ({profile_description}), provide a brief contextual assessment of its suitability. Consider tone, style, jargon, and complexity nuances beyond the statistical score.

Provide the analysis in JSON format with the following keys:
1.  "contextual_assessment": A brief phrase describing the sentence's suitability for the audience (e.g., "Appropriate", "Slightly too complex", "Tone mismatch", "Too simplistic", "Contains jargon").
2.  "reasoning": A short explanation for your assessment, referencing specific words or phrases if applicable.
3.  "suggestion": If the assessment is not "Appropriate", provide a concrete rewrite suggestion for the sentence to better align it with the target audience. Otherwise, provide an empty string.

Output only the JSON object.
"""
    return _call_gemini_api(prompt)


# --- Function to Recommend Synonyms Contextually ---
def recommend_synonym(original_word: str, sentence_context: str, ranked_synonyms_list: list, target_audience_profile: str):
    """
    Uses Gemini to recommend the best synonym(s) from a pre-ranked list,
    considering the sentence context and target audience profile.

    Args:
        original_word: The word the user wants synonyms for.
        sentence_context: The full sentence containing the original word.
        ranked_synonyms_list: List of dictionaries from get_ranked_synonyms [{"word": str, "rank": int}].
        target_audience_profile: Name of the target audience profile.

    Returns:
        A dictionary with the LLM's recommendation and reasoning, or an error dictionary.
        Example: {"recommendation": ["use", "apply"], "reasoning": "'Utilize' is too formal for General Public; 'use' or 'apply' fit the context better."}
    """
    if not original_word or not sentence_context or not ranked_synonyms_list:
        return {"error": "Missing required input for synonym recommendation"}

    # Fetch profile details for the prompt (similar logic as above)
    profile_details = AUDIENCE_PROFILES.get(target_audience_profile)
    if not profile_details:
        profile_description = f"a '{target_audience_profile}' audience"
    else:
        target_readability = profile_details.get('target_readability', {})
        fk_target = target_readability.get('flesch_kincaid_grade')
        gf_target = target_readability.get('gunning_fog')
        readability_info = []
        if fk_target: readability_info.append(f"target Flesch-Kincaid Grade: {fk_target[0]}{f'-{fk_target[1]}' if fk_target[1] else '+'}")
        if gf_target: readability_info.append(f"target Gunning Fog: {gf_target[0]}{f'-{gf_target[1]}' if gf_target[1] else '+'}")
        profile_description = f"a '{target_audience_profile}' audience"
        if readability_info: profile_description += f" (aiming for {', '.join(readability_info)})"

    logging.info(f"Requesting Gemini synonym recommendation for profile: {target_audience_profile}")

    # Format the synonym list for the prompt
    synonym_options = ", ".join([f"'{s['word']}' (rank {s['rank']})" for s in ranked_synonyms_list])

    prompt = f"""
The user wants a synonym for the word "{original_word}" in the following sentence:
---
{sentence_context}
---

The target audience is {profile_description}.

An internal algorithm provided the following potential synonyms, ranked by general frequency (1=most common, 5=least common):
{synonym_options}

Considering the specific sentence context and the target audience ({profile_description}), which synonym(s) from the provided list would be the *most suitable replacement* for "{original_word}" in this sentence?

Provide the analysis in JSON format with the following keys:
1.  "recommendation": A list containing the single best synonym string from the provided list. If multiple are equally good, list up to two. If none from the list are suitable, provide an empty list.
2.  "reasoning": A brief explanation for your choice(s), explaining why it fits the context and audience better than the original word or other options. If none are suitable, explain why.

Output only the JSON object.
"""
    return _call_gemini_api(prompt)


# Example usage (for testing) - Update these later if needed
if __name__ == '__main__':
    print("--- Testing Complexity Enhancement ---")
    test_sentence = "Subsequently, the system effectuates data assimilation."
    test_score = 0.95
    test_profile = "General Public"
    if api_key and api_key != "DUMMY_KEY_FOR_INITIALIZATION" and model:
        complexity_feedback = enhance_sentence_complexity(test_sentence, test_score, test_profile)
        print(f"Feedback for '{test_sentence}' (Score: {test_score}, Profile: {test_profile}):")
        print(json.dumps(complexity_feedback, indent=2))
    else:
        print("Skipping complexity test: API key or model not configured.")

    print("\n--- Testing Synonym Recommendation ---")
    test_orig_word = "effectuates"
    test_context = "Subsequently, the system effectuates data assimilation."
    test_syn_list = [{"word": "performs", "rank": 1}, {"word": "executes", "rank": 2}, {"word": "implements", "rank": 3}, {"word": "accomplishes", "rank": 4}]
    if api_key and api_key != "DUMMY_KEY_FOR_INITIALIZATION" and model:
        synonym_rec = recommend_synonym(test_orig_word, test_context, test_syn_list, test_profile)
        print(f"Recommendation for '{test_orig_word}' in context (Profile: {test_profile}):")
        print(f"Options: {test_syn_list}")
        print(json.dumps(synonym_rec, indent=2))
    else:
         print("Skipping synonym test: API key or model not configured.")
