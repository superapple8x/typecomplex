import os
import openai  # Use the OpenAI library for DeepSeek compatibility
import json
import logging
from typing import Optional, Tuple
# Import AUDIENCE_PROFILES to get profile details
from app.analysis import AUDIENCE_PROFILES
from app.api_keys import ApiKeyStore

# Configure logging (avoid DEBUG for production; and never log secrets)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- DeepSeek API Configuration ---
base_url = "https://api.deepseek.com/v1"  # OpenAI-compatible endpoint
model_name = "deepseek-chat"  # Or "deepseek-reasoner" if needed

_client: Optional[openai.OpenAI] = None
_keystore = ApiKeyStore()


def reset_client() -> None:
    """Reset the cached OpenAI-compatible client (after key changes)."""
    global _client
    _client = None


def ensure_client() -> Optional[openai.OpenAI]:
    """Return a cached OpenAI-compatible client, creating it from stored key if needed."""
    global _client
    if _client is not None:
        return _client
    api_key = _keystore.get_key()
    if not api_key:
        logging.warning("DeepSeek API key not set. AI features are unavailable.")
        return None
    try:
        _client = openai.OpenAI(api_key=api_key, base_url=base_url)
        return _client
    except Exception as e:
        logging.error(f"Failed to initialize DeepSeek client: {e}")
        _client = None
        return None


def test_key_connectivity() -> Tuple[bool, str]:
    """Test current stored key without sending user content. Returns (ok, normalized_error)."""
    client = ensure_client()
    if client is None:
        return (False, 'api_key_missing')
    try:
        # Prefer a metadata endpoint that carries no user content
        client.models.list()
        return (True, '')
    except openai.AuthenticationError:
        return (False, 'invalid_key')
    except openai.RateLimitError:
        return (False, 'rate_limit')
    except openai.APIError:
        return (False, 'server_error')
    except Exception:
        # Network or unexpected
        return (False, 'network')

# --- Helper Function for API Calls ---
def _call_deepseek_api(prompt: str):
    """Internal helper to make DeepSeek API call and handle response parsing/errors."""
    client = ensure_client()
    if client is None:
        logging.error("DeepSeek client not initialized (missing/invalid API key). Skipping DeepSeek call.")
        return {"error": "api_client_unavailable"}

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
        return {"error": "Authentication Error: Invalid API Key?"}
    except openai.RateLimitError as e:
        logging.error(f"DeepSeek API Rate Limit Exceeded: {e}", exc_info=True)
        return {"error": f"Rate Limit Error: {e}"}
    except Exception as e:
        # Handle other potential errors
        logging.error(f"An unexpected error occurred during DeepSeek API call: {e}", exc_info=True)
        return {"error": f"API call failed: {e}"}


# --- Function to Enhance Sentence Complexity Analysis (REMOVED as it was unused) ---

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

# --- NEW: Function to Get Rewrite Suggestions ---
def get_rewrite_suggestion(sentence_text: str, surrounding_context: str, target_audience_profile: str, complexity_analysis_details: dict):
    """
    Uses DeepSeek to provide feedback and optionally a rewrite suggestion for a sentence,
    considering its context, complexity score, and the target audience.

    Args:
        sentence_text: The specific sentence to analyze.
        surrounding_context: The text surrounding the sentence (can be partial or full document).
        target_audience_profile: Name of the target audience profile.
        complexity_analysis_details: Dictionary containing the sentence's complexity score and contributing factors.

    Returns:
        A dictionary with feedback, suggestion, reasoning, and sufficiency flag, or an error dictionary.
    """
    if not sentence_text or not surrounding_context or not target_audience_profile or not complexity_analysis_details:
        return {"error": "Missing required input for rewrite suggestion"}

    # Fetch profile details for the prompt (reuse logic from recommend_synonym)
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

    logging.info(f"Requesting DeepSeek rewrite suggestion for profile: {target_audience_profile}")

    # Determine context type for the prompt
    context_type = "Full Document Context" if len(surrounding_context) > len(sentence_text) * 1.5 else "Sentence Context" # Simple heuristic

    prompt = f"""
The user wants feedback and potentially a rewrite suggestion for the following sentence:
--- SENTENCE ---
{sentence_text}
--- END SENTENCE ---

The target audience is {profile_description}.

Here is the surrounding context ({context_type}):
--- CONTEXT ---
{surrounding_context}
--- END CONTEXT ---

Our system calculated the following complexity metrics for this sentence:
- Overall Complexity Score: {complexity_analysis_details.get('score', 'N/A'):.2f} (Higher means more complex)
- Sentence Length Factor: {complexity_analysis_details.get('length_factor', 'N/A'):.2f}
- Average Word Length Factor: {complexity_analysis_details.get('word_len_factor', 'N/A'):.2f}
- Word Rarity (Frequency) Factor: {complexity_analysis_details.get('frequency_factor', 'N/A'):.2f} (Higher values indicate rarer words)
- Contextual Word Usage (Embedding Variance): {complexity_analysis_details.get('embedding_factor', 'N/A'):.2f} (If applicable; higher = more varied/uncommon semantic contexts)
- Syntactic Structure Complexity Factor: {complexity_analysis_details.get('syntactic_factor', 'N/A'):.2f} (Reflects parse tree depth, clauses, etc.)
- Grammatical Dependency Complexity Factor: {complexity_analysis_details.get('dependency_factor', 'N/A'):.2f} (Measures complexity of word relationships)
- Lexical Choice Complexity Factor: {complexity_analysis_details.get('lexical_factor', 'N/A'):.2f} (Considers nominalizations, content word ratio)
- Semantic Coherence Factor: {complexity_analysis_details.get('semantic_coherence_factor', 'N/A'):.2f} (Higher values indicate lower coherence, contributing to complexity)
(Note: 'N/A' or 0.0 for a factor may mean it wasn't computed or didn't contribute significantly in the current analysis mode.)

Analyze the provided sentence based on its detailed complexity metrics, the surrounding context, and the target audience ({profile_description}).
Provide constructive feedback. If the sentence could be improved for the target audience (e.g., clarity, engagement, tone, simplicity/sophistication), suggest a rewritten version. If the original sentence is already sufficient and well-suited, acknowledge that.

Provide the analysis in JSON format with the following keys:
1.  "status": (string) The overall assessment status. Must be one of: "Good", "Consider changing", or "Needs improvement". Base this on whether the sentence is suitable ("Good"), could be slightly improved ("Consider changing"), or needs rewriting for clarity/audience fit ("Needs improvement").
2.  "feedback": (string) Constructive feedback on the original sentence's suitability for the audience and context, explaining the status, referencing specific complexity factors where relevant.
3.  "suggestion": (string or null) The rewritten sentence suggestion, or null if the original is sufficient or no improvement is suggested (status "Good"). A suggestion should usually be provided if status is "Consider changing" or "Needs improvement".
4.  "reasoning": (string) A brief explanation for the feedback and suggestion (or lack thereof), linking it to the audience, context, complexity metrics, and the assigned status.

Output only the JSON object.
"""
    # Update the system prompt for the helper function if needed, or adjust here
    # For now, using the existing system prompt in _call_deepseek_api
    return _call_deepseek_api(prompt)


# Example usage (for testing) - Updated for DeepSeek
if __name__ == '__main__':
    # --- Complexity Enhancement Test REMOVED ---

    print("\n--- Testing Synonym Recommendation (DeepSeek) ---")
    test_orig_word = "effectuates"
    test_context = "Subsequently, the system effectuates data assimilation."
    test_syn_list = [{"word": "performs", "rank": 1}, {"word": "executes", "rank": 2}, {"word": "implements", "rank": 3}, {"word": "accomplishes", "rank": 4}]
    # test_profile needs to be defined, e.g., "Standard" for testing
    test_profile = "Standard" 
    if ensure_client():
        synonym_rec = recommend_synonym(test_orig_word, test_context, test_syn_list, test_profile)
        print(f"Recommendation for '{test_orig_word}' in context (Profile: {test_profile}):")
        print(f"Options: {test_syn_list}")
        print(json.dumps(synonym_rec, indent=2))

        print("\n--- Testing Rewrite Suggestion (DeepSeek) ---")
        test_sentence = "The aforementioned conglomeration of disparate entities effectuated a paradigm shift."
        test_surrounding_context = "Initial reports were divergent. The aforementioned conglomeration of disparate entities effectuated a paradigm shift. Subsequent analyses concurred."
        # Example complexity_analysis_details (ensure all keys from the prompt are present)
        test_complexity_details = {
            'score': 0.85,
            'length_factor': 0.7,
            'word_len_factor': 0.9,
            'frequency_factor': 0.8,
            'embedding_factor': 0.6, # Example, might be 0.0 if not in full mode
            'syntactic_factor': 0.75,
            'dependency_factor': 0.65,
            'lexical_factor': 0.9,
            'semantic_coherence_factor': 0.3 # Example, lower is more coherent
        }
        rewrite_sugg = get_rewrite_suggestion(test_sentence, test_surrounding_context, test_profile, test_complexity_details)
        print(f"Rewrite suggestion for sentence (Profile: {test_profile}):")
        print(f"Original: {test_sentence}")
        print(f"Complexity Details: {test_complexity_details}")
        print(json.dumps(rewrite_sugg, indent=2))
    else:
        print("Skipping DeepSeek tests: DeepSeek client not configured (set API key via settings endpoint).")
