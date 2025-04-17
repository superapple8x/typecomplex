import os
import openai  # Use the OpenAI library for DeepSeek compatibility
from dotenv import load_dotenv
import json
import logging
# Import AUDIENCE_PROFILES to get profile details
from app.analysis import AUDIENCE_PROFILES

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables from .env file
load_dotenv()

# --- DeepSeek API Configuration ---
api_key = os.getenv("DEEPSEEK_API_KEY")
base_url = "https://api.deepseek.com/v1" # Use v1 endpoint for OpenAI compatibility
model_name = "deepseek-chat" # Or "deepseek-reasoner" if needed

client = None # Initialize client variable

if not api_key:
    logging.error("DEEPSEEK_API_KEY not found in environment variables. Please set it in a .env file.")
else:
    try:
        client = openai.OpenAI(api_key=api_key, base_url=base_url)
        logging.info("DeepSeek client initialized successfully.")
        # Optional: Add a test call here if needed to verify connection
    except Exception as e:
        logging.error(f"Failed to initialize DeepSeek client with API key: {e}")
        client = None # Ensure client is None if initialization fails

# --- Helper Function for API Calls ---
def _call_deepseek_api(prompt: str):
    """Internal helper to make DeepSeek API call and handle response parsing/errors."""
    if not client:
        logging.error("DeepSeek client not initialized (check API key). Skipping DeepSeek call.")
        return {"error": "API client not initialized"}

    try:
        logging.info("Sending request to DeepSeek API...")
        # Use the chat completions endpoint
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are an AI assistant helping analyze text complexity and suggest synonyms. Respond ONLY with the requested JSON object."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5, # Adjust temperature as needed
            response_format={"type": "json_object"} # Request JSON output if supported by model/API version
        )
        logging.info("Received response from DeepSeek API.")

        # Extract and parse JSON response
        if response.choices and response.choices[0].message and response.choices[0].message.content:
            try:
                raw_json_response = response.choices[0].message.content
                # No need to strip ```json as we requested JSON format
                analysis_results = json.loads(raw_json_response)
                logging.info("Successfully parsed DeepSeek JSON response.")
                return analysis_results
            except json.JSONDecodeError as e:
                logging.error(f"Failed to parse DeepSeek response as JSON: {e}")
                logging.debug(f"Raw DeepSeek response content:\n{raw_json_response}")
                return {"error": "Failed to parse response JSON"}
            except Exception as e:
                 logging.error(f"Error processing DeepSeek response content: {e}", exc_info=True)
                 logging.debug(f"Raw DeepSeek response object:\n{response}")
                 return {"error": f"Error processing response: {e}"}
        else:
            logging.warning("DeepSeek response missing expected content.")
            logging.debug(f"Full DeepSeek response object:\n{response}")
            # Check for finish reason (e.g., content filter)
            finish_reason = response.choices[0].finish_reason if response.choices else "unknown"
            return {"error": f"Response missing content (Finish Reason: {finish_reason})"}

    except openai.APIError as e:
        # Handle API errors (e.g., connection, server issues)
        logging.error(f"DeepSeek API returned an API Error: {e}", exc_info=True)
        return {"error": f"API Error: {e}"}
    except openai.AuthenticationError as e:
        logging.error(f"DeepSeek API Authentication Error (check API key): {e}", exc_info=True)
        return {"error": f"Authentication Error: Invalid API Key?"}
    except openai.RateLimitError as e:
        logging.error(f"DeepSeek API Rate Limit Exceeded: {e}", exc_info=True)
        return {"error": f"Rate Limit Error: {e}"}
    except Exception as e:
        # Handle other potential errors
        logging.error(f"An unexpected error occurred during DeepSeek API call: {e}", exc_info=True)
        return {"error": f"API call failed: {e}"}


# --- Function to Enhance Sentence Complexity Analysis ---
# (Prompt remains the same as it requests JSON output)
def enhance_sentence_complexity(sentence: str, statistical_score: float, target_audience_profile: str):
    """
    Uses DeepSeek to provide contextual feedback on a sentence's complexity,
    considering its statistical score and the target audience profile.

    Args:
        sentence: The sentence text.
        statistical_score: The pre-calculated statistical complexity score.
        target_audience_profile: Name of the target audience profile.

    Returns:
        A dictionary with LLM feedback (e.g., adjusted assessment, reason, suggestion)
        or an error dictionary.
    """
    if not sentence or not sentence.strip():
        return {"error": "Input sentence is empty"}

    # Fetch profile details for the prompt (same logic as before)
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

    logging.info(f"Requesting DeepSeek complexity enhancement for profile: {target_audience_profile}")

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
    return _call_deepseek_api(prompt)


# --- Function to Recommend Synonyms Contextually ---
# (Prompt remains the same as it requests JSON output)
def recommend_synonym(original_word: str, sentence_context: str, ranked_synonyms_list: list, target_audience_profile: str):
    """
    Uses DeepSeek to recommend the best synonym(s) from a pre-ranked list,
    considering the sentence context and target audience profile.

    Args:
        original_word: The word the user wants synonyms for.
        sentence_context: The full sentence containing the original word.
        ranked_synonyms_list: List of dictionaries from get_ranked_synonyms [{"word": str, "rank": int}].
        target_audience_profile: Name of the target audience profile.

    Returns:
        A dictionary with the LLM's recommendation and reasoning, or an error dictionary.
    """
    if not original_word or not sentence_context or not ranked_synonyms_list:
        return {"error": "Missing required input for synonym recommendation"}

    # Fetch profile details for the prompt (same logic as before)
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

    logging.info(f"Requesting DeepSeek synonym recommendation for profile: {target_audience_profile}")

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
    return _call_deepseek_api(prompt)


# Example usage (for testing) - Updated for DeepSeek
if __name__ == '__main__':
    print("--- Testing Complexity Enhancement (DeepSeek) ---")
    test_sentence = "Subsequently, the system effectuates data assimilation."
    test_score = 0.95
    test_profile = "General Public"
    if client:
        complexity_feedback = enhance_sentence_complexity(test_sentence, test_score, test_profile)
        print(f"Feedback for '{test_sentence}' (Score: {test_score}, Profile: {test_profile}):")
        print(json.dumps(complexity_feedback, indent=2))
    else:
        print("Skipping complexity test: DeepSeek client not configured (check API key).")

    print("\n--- Testing Synonym Recommendation (DeepSeek) ---")
    test_orig_word = "effectuates"
    test_context = "Subsequently, the system effectuates data assimilation."
    test_syn_list = [{"word": "performs", "rank": 1}, {"word": "executes", "rank": 2}, {"word": "implements", "rank": 3}, {"word": "accomplishes", "rank": 4}]
    if client:
        synonym_rec = recommend_synonym(test_orig_word, test_context, test_syn_list, test_profile)
        print(f"Recommendation for '{test_orig_word}' in context (Profile: {test_profile}):")
        print(f"Options: {test_syn_list}")
        print(json.dumps(synonym_rec, indent=2))
    else:
         print("Skipping synonym test: DeepSeek client not configured (check API key).")
