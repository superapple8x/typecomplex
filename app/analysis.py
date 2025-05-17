import nltk
import re
import math
import os # Import os
import textstat # Import textstat
from app.frequency import get_word_frequency # Import frequency function
import torch
import numpy as np
from transformers import AutoTokenizer, AutoModel
import spacy # Import spacy
import logging # Import logging
logger = logging.getLogger(__name__) # Define logger for this module
import hashlib # Import hashlib
from app import cache # Import the initialized cache object
from app import task_manager # Import task manager
import requests # For Hugging Face API calls

# --- Transformer Model Configuration ---
DEFAULT_BERT_LOCAL_MODEL_NAME = 'bert-base-uncased'
APP_BERT_LOCAL_MODEL_NAME = os.environ.get('APP_BERT_LOCAL_MODEL_NAME', DEFAULT_BERT_LOCAL_MODEL_NAME)

# Execution mode: 'local' or 'remote_hf_endpoint'
APP_BERT_EXECUTION_MODE = os.environ.get('APP_BERT_EXECUTION_MODE', 'local').lower()
APP_BERT_HF_ENDPOINT_URL = os.environ.get('APP_BERT_HF_ENDPOINT_URL', None)
APP_BERT_HF_API_TOKEN = os.environ.get('APP_BERT_HF_API_TOKEN', None)

# Global variables for tokenizer and model
tokenizer = None
model = None

def load_transformer_assets():
    """Loads the Hugging Face transformer tokenizer and, if in local mode, the model.
    
    The local model name can be configured via the APP_BERT_LOCAL_MODEL_NAME environment variable.
    The tokenizer is always loaded locally as it's needed for token-to-word mapping.
    The model is loaded locally only if APP_BERT_EXECUTION_MODE is 'local'.
    
    Returns:
        tuple: (loaded_tokenizer, loaded_model) 
               The loaded_model can be None if not in local mode or if loading fails.
    """
    global tokenizer, model # Allow modification of global vars

    loaded_tokenizer_internal = None
    loaded_model_internal = None

    print(f"Attempting to load tokenizer for model: '{APP_BERT_LOCAL_MODEL_NAME}'")
    try:
        loaded_tokenizer_internal = AutoTokenizer.from_pretrained(APP_BERT_LOCAL_MODEL_NAME)
        print(f"Successfully loaded tokenizer for '{APP_BERT_LOCAL_MODEL_NAME}'.")
    except Exception as e:
        print(f"ERROR loading tokenizer for '{APP_BERT_LOCAL_MODEL_NAME}': {e}")
        # Tokenizer is critical, so if it fails, we can't do much.
        # The global tokenizer will remain None.
        return None, None

    if APP_BERT_EXECUTION_MODE == 'local':
        print(f"BERT execution mode: 'local'. Attempting to load model: '{APP_BERT_LOCAL_MODEL_NAME}'")
        try:
            loaded_model_internal = AutoModel.from_pretrained(APP_BERT_LOCAL_MODEL_NAME)
            loaded_model_internal.eval() # Ensure model is in evaluation mode
            if torch.cuda.is_available():
                loaded_model_internal.to('cuda')
                print(f"Successfully loaded local model '{APP_BERT_LOCAL_MODEL_NAME}' to GPU.")
            else:
                print(f"Successfully loaded local model '{APP_BERT_LOCAL_MODEL_NAME}' to CPU.")
        except Exception as e:
            print(f"ERROR loading local model '{APP_BERT_LOCAL_MODEL_NAME}': {e}")
            # loaded_model_internal remains None
    elif APP_BERT_EXECUTION_MODE == 'remote_hf_endpoint':
        print(f"BERT execution mode: 'remote_hf_endpoint'. Local model will not be loaded.")
        if not APP_BERT_HF_ENDPOINT_URL or not APP_BERT_HF_API_TOKEN:
            print("WARN: Remote HF endpoint mode selected, but URL or API token is missing. BERT features will be unavailable.")
    else:
        print(f"WARN: Invalid APP_BERT_EXECUTION_MODE ('{APP_BERT_EXECUTION_MODE}'). Defaulting to no BERT features. Set to 'local' or 'remote_hf_endpoint'.")

    return loaded_tokenizer_internal, loaded_model_internal

# Initialize tokenizer and potentially model at startup
tokenizer, model = load_transformer_assets()


# --- Load spaCy Model ---
# Load spaCy English model once globally for parsing
SPACY_MODEL_NAME = 'en_core_web_sm'
try:
    nlp = spacy.load(SPACY_MODEL_NAME)
    print(f"Successfully loaded spaCy model '{SPACY_MODEL_NAME}'.")
except Exception as e:
    print(f"ERROR loading spaCy model '{SPACY_MODEL_NAME}': {e}")
    nlp = None # Indicate failure

# --- Audience Profiles ---
# Define weights, normalization constants, thresholds, and target scores per audience.
# Added 'embedding_complexity' weight and renormalized others
# --- Audience Profiles ---
# Define weights, normalization constants, thresholds, and target scores per audience.
# Added 'syntactic_complexity' and 'coreference_complexity' weights.
# Weights MUST sum to 1.0. Normalization constants are estimates and may need tuning.
AUDIENCE_PROFILES = {
    "Standard": {
        "weights": { # Reverted to initial weights (v0)
            "sentence_length": 0.18,
            "avg_word_length": 0.14,
            "avg_word_frequency": 0.14,
            "embedding_complexity": 0.12,
            "syntactic_complexity": 0.12,
            "dependency_complexity": 0.10,
            "lexical_complexity": 0.10,
            "semantic_coherence": 0.10,
            # "coreference_complexity": 0.0, # Disabled
        },
        "normalization": { # Increased ceilings to allow higher complexity scores (v2)
            "sentence_length": 30.0,
            "avg_word_length": 7.0,
            "max_log_frequency": 7.0,
            # Original Syntactic
            "max_parse_tree_depth": 20.0, # Increased
            "max_num_clauses": 7.0, # Increased
            "max_avg_dependency_length": 12.0, # Increased
            # Dependency Complexity
            "max_complex_dep_density": 0.25, # Increased
            "max_subordination_density": 0.25, # Increased
            "max_pp_density": 0.45, # Increased
            "max_pp_nesting_depth": 6.0, # Increased
            # Lexical Complexity
            "max_nominalization_density": 0.20, # Increased
            "target_content_word_ratio": 0.6, # ratio (deviation from this increases complexity)
            # Semantic Coherence
            "min_semantic_coherence": 0.5, # Reverted: Decreased (allows lower coherence before penalty)
            # Disabled
            # "max_coreferent_mentions": 5.0,
        },
        "thresholds": { # Lowered upper thresholds to classify complex sentences more easily (v2)
            "very_simple": 0.3,
            "simple": 0.5,
            "moderate": 0.75, # Lowered
            "complex": 0.95, # Lowered (Implicitly makes Very Complex start at 0.95)
        },
        "target_readability": {
            "flesch_kincaid_grade": None, # No specific target for standard
            "gunning_fog": None,
        }
    },
    "General Public": {
        "weights": { # Re-balanced for new metrics (Target: 30% new, emphasize length)
            "sentence_length": 0.25, # Reduced further
            "avg_word_length": 0.15, # Reduced further
            "avg_word_frequency": 0.10, # Reduced further
            "embedding_complexity": 0.10, # Reduced further
            "syntactic_complexity": 0.10, # Reduced further
            "dependency_complexity": 0.10, # New
            "lexical_complexity": 0.10, # New
            "semantic_coherence": 0.10, # New
            # "coreference_complexity": 0.0, # Disabled
        },
        "normalization": { # Lower tolerance for length, syntax
            "sentence_length": 25.0,
            "avg_word_length": 7.0,
            "max_log_frequency": 7.0,
            # Original Syntactic
            "max_parse_tree_depth": 12.0,
            "max_num_clauses": 4.0,
            "max_avg_dependency_length": 8.0,
             # Dependency Complexity (Slightly lower tolerance than Standard)
            "max_complex_dep_density": 0.18,
            "max_subordination_density": 0.18,
            "max_pp_density": 0.35,
            "max_pp_nesting_depth": 4.0,
            # Lexical Complexity (Slightly lower tolerance)
            "max_nominalization_density": 0.12,
            "target_content_word_ratio": 0.65, # Expect slightly simpler vocab mix
            # Semantic Coherence (Slightly higher tolerance for incoherence)
            "min_semantic_coherence": 0.55,
            # Disabled
            # "max_coreferent_mentions": 4.0,
        },
        "thresholds": { # Lower thresholds -> easier to be complex
            "very_simple": 0.25,
            "simple": 0.45,
            "moderate": 0.7,
            "complex": 1.0,
        },
        "target_readability": {
            "flesch_kincaid_grade": (8.0, 10.9),
            "gunning_fog": (10.0, 13.0),
        }
    },
    "Academic / Technical": {
        "weights": { # Re-balanced for new metrics (Target: 30% new, emphasize new metrics)
            "sentence_length": 0.10, # Reduced further
            "avg_word_length": 0.15, # Reduced further
            "avg_word_frequency": 0.15, # Reduced further
            "embedding_complexity": 0.15, # Kept higher
            "syntactic_complexity": 0.15, # Kept higher
            "dependency_complexity": 0.10, # New
            "lexical_complexity": 0.10, # New
            "semantic_coherence": 0.10, # New
            # "coreference_complexity": 0.0, # Disabled
        },
        "normalization": { # Higher tolerance
            "sentence_length": 35.0,
            "avg_word_length": 8.0,
            "max_log_frequency": 7.0,
             # Original Syntactic
            "max_parse_tree_depth": 20.0,
            "max_num_clauses": 7.0,
            "max_avg_dependency_length": 12.0,
            # Dependency Complexity (Higher tolerance)
            "max_complex_dep_density": 0.25,
            "max_subordination_density": 0.25,
            "max_pp_density": 0.45,
            "max_pp_nesting_depth": 7.0,
            # Lexical Complexity (Higher tolerance)
            "max_nominalization_density": 0.20,
            "target_content_word_ratio": 0.55, # Allow denser mix
            # Semantic Coherence (Lower tolerance for incoherence - expect more related terms)
            "min_semantic_coherence": 0.45,
            # Disabled
            # "max_coreferent_mentions": 6.0,
        },
        "thresholds": { # Higher thresholds -> harder to be complex
            "very_simple": 0.35,
            "simple": 0.6,
            "moderate": 0.9,
            "complex": 1.2,
        },
        "target_readability": {
            "flesch_kincaid_grade": (13.0, None), # 13.0 or higher
            "gunning_fog": (15.0, None), # 15.0 or higher
        }
    }
    # Add more profiles like "Young Adult", "Expert" here if needed
}

# Ensure weights sum to 1.0 for all profiles (adjust if needed)
for profile_name, profile_data in AUDIENCE_PROFILES.items():
    # Ensure weights sum to 1.0 after manual adjustment
    total_weight = sum(profile_data['weights'].values())
    if not math.isclose(total_weight, 1.0, abs_tol=1e-5): # Use tolerance for float comparison
        print(f"ERROR: Weights for profile '{profile_name}' do not sum to 1.0 after re-balancing (sum={total_weight:.4f}). Check configuration.")
        # Optionally raise an error or attempt normalization again, but manual check is better.
        # factor = 1.0 / total_weight
        # for key in profile_data['weights']:
        #     profile_data['weights'][key] *= factor

# --- Fast Mode Weights ---
# Independent weights used only when mode='fast'
FAST_MODE_WEIGHTS = {
    "sentence_length": 0.40,
    "avg_word_length": 0.30,
    "avg_word_frequency": 0.30, # Corresponds to 'word rarity'
}

# --- NLTK Data Check and Tokenizer Initialization ---
# NLTK data path is usually handled automatically.
# Removed Linux-specific path: '/home/pepperoni/nltk_data'

# Try loading directly first
sentence_tokenizer = None # Initialize
try:
    sentence_tokenizer = nltk.data.load('tokenizers/punkt/english.pickle')
    print("Successfully loaded 'punkt' tokenizer.")
except LookupError:
    print("NLTK 'punkt' tokenizer not found via load. Attempting download...")
    try:
        nltk.download('punkt') # Download without quiet=True for more info
        print("Download attempted. Trying to load again...")
        # Re-attempt loading after download
        sentence_tokenizer = nltk.data.load('tokenizers/punkt/english.pickle')
        print("Successfully loaded 'punkt' after download.")
    except Exception as e:
        # Catch errors during download or the second load attempt
        print(f"Failed to download or load 'punkt' after download attempt: {e}")
        # sentence_tokenizer remains None
except Exception as e: # Catch other potential loading errors
    print(f"An unexpected error occurred loading 'punkt': {e}")
    # sentence_tokenizer remains None

# Check if tokenizer loaded successfully before proceeding
if sentence_tokenizer is None:
    print("ERROR: Could not initialize sentence tokenizer. Analysis may fail.")
    # Depending on requirements, might raise an error or exit


def _get_hidden_states_from_remote_hf_endpoint(sentence_text: str, endpoint_url: str, api_token: str, local_tokenizer_for_validation) -> np.ndarray | None:
    """
    Calls a Hugging Face Inference Endpoint for feature extraction to get token embeddings.
    Validates that the number of tokens from the remote endpoint matches the local tokenizer.
    """
    if not endpoint_url or not api_token:
        print("WARN: Hugging Face endpoint URL or API token not provided for remote inference.")
        return None

    headers = {"Authorization": f"Bearer {api_token}"}
    # Payload for feature-extraction task typically expects "inputs"
    # "options: {"wait_for_model": True}" is good for serverless endpoints that might cold start
    payload = {"inputs": sentence_text, "options": {"wait_for_model": True}}
    
    print(f"Calling Hugging Face Inference Endpoint for embeddings: {endpoint_url}")
    try:
        response = requests.post(endpoint_url, headers=headers, json=payload, timeout=60) # 60s timeout
        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
        
        # The response for feature extraction is typically a list of embeddings (list of lists of floats)
        # or a nested list if multiple sentences were sent (we send one here).
        # Example: [[emb_token1], [emb_token2], ...]
        remote_embeddings_list = response.json()

        if not remote_embeddings_list or not isinstance(remote_embeddings_list, list):
            print(f"ERROR: Unexpected response format from HF endpoint. Expected list of embeddings. Got: {remote_embeddings_list}")
            return None
        
        # If the endpoint processes a single string and returns a list of embeddings (one per token for that string)
        # This is the common case for feature extraction endpoints.
        if isinstance(remote_embeddings_list[0], list) and isinstance(remote_embeddings_list[0][0], float):
            # This means remote_embeddings_list is like [[t1_e1, t1_e2,...], [t2_e1, t2_e2,...], ...]
            embeddings_np = np.array(remote_embeddings_list) # Shape: (num_tokens, hidden_size)
        else:
            print(f"ERROR: Unexpected embedding format in HF endpoint response. Expected list of lists of floats. Got: {remote_embeddings_list[0]}")
            return None

        # Validate token count against local tokenizer for the same sentence text
        # This is crucial for the existing token-to-word mapping logic.
        with torch.no_grad(): # Tokenization doesn't need gradients
            local_inputs = local_tokenizer_for_validation(sentence_text, return_tensors="pt", truncation=True, padding="longest")
        expected_num_tokens = local_inputs['input_ids'].shape[1]
        
        if embeddings_np.shape[0] != expected_num_tokens:
            print(f"WARN: Token count mismatch between remote HF endpoint ({embeddings_np.shape[0]}) and local tokenizer ({expected_num_tokens}) for sentence: '{sentence_text[:50]}...'. This may affect embedding mapping.")
            # Decide on handling: return None, or try to use it anyway (risky). For now, let's be strict.
            # This could happen if the remote endpoint uses a different model version or different default tokenization params.
            # The user *must* ensure the HF endpoint uses the *exact same model/tokenizer* as APP_BERT_LOCAL_MODEL_NAME
            # return None 
            # Loosening the check for now, but this is a potential point of failure if models diverge.
            # The downstream code will likely fail if the number of embeddings doesn't match the number of tokens
            # expected by the token_to_word_mapping logic. Best to ensure models are identical.

        print(f"Successfully received {embeddings_np.shape[0]} embeddings of dimension {embeddings_np.shape[1]} from remote endpoint.")
        return embeddings_np

    except requests.exceptions.Timeout:
        print(f"ERROR: Timeout calling Hugging Face endpoint: {endpoint_url}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Request to Hugging Face endpoint failed: {e}")
        if hasattr(e, 'response') and e.response is not None:
            try:
                print(f"HF Endpoint Response Content: {e.response.text}")
            except Exception:
                print("HF Endpoint Response Content: <Could not decode>")
        return None
    except Exception as e: # Catch any other errors, like JSON parsing
        print(f"ERROR: Failed to process response from Hugging Face endpoint: {e}")
        return None


def _get_contextual_embedding_complexity(sentence, words_for_stats):
    """
    Calculates complexity based on contextual word embeddings using transformers
    (variance from sentence mean).
    Higher score means words are used in more varied/distant contexts.
    Embeddings can be fetched locally or from a remote Hugging Face Inference Endpoint.
    Returns a dictionary containing:
        - 'factor': Score between 0 and 1 (or None if model failed).
        - 'embeddings': Numpy array of averaged word embeddings.
        - 'token_map': List mapping transformer token indices to original word indices.
    """
    # Tokenizer is always assumed to be loaded locally
    if not tokenizer:
        print("WARN: Tokenizer not available. Cannot calculate embedding complexity.")
        return {'factor': None, 'embeddings': None, 'token_map': None}

    # Tokenize the input sentence using the local tokenizer.
    # The resulting `inputs['input_ids']` are crucial for the token-to-word mapping logic later.
    # Padding to longest is fine here as we process one sentence at a time.
    inputs = tokenizer(sentence, return_tensors="pt", truncation=True, padding="longest")
    
    # Move tokenized inputs to GPU if local model will be used and GPU is available
    inputs_on_device = inputs
    if APP_BERT_EXECUTION_MODE == 'local' and model and torch.cuda.is_available():
        inputs_on_device = {k: v.to('cuda') for k, v in inputs.items()}

    last_hidden_states_np = None

    if APP_BERT_EXECUTION_MODE == 'remote_hf_endpoint':
        if APP_BERT_HF_ENDPOINT_URL and APP_BERT_HF_API_TOKEN:
            print(f"Fetching embeddings via remote HF endpoint: {APP_BERT_HF_ENDPOINT_URL}")
            last_hidden_states_np = _get_hidden_states_from_remote_hf_endpoint(
                sentence, 
                APP_BERT_HF_ENDPOINT_URL, 
                APP_BERT_HF_API_TOKEN,
                tokenizer # Pass local tokenizer for validation within the remote fetch function
            )
            if last_hidden_states_np is None:
                print("WARN: Failed to get embeddings from remote HF endpoint. Embedding complexity will be None.")
                # Fallback to local if desired and model is available? For now, if remote fails, it fails.
                # To enable fallback:
                # if model:
                #    print("WARN: Falling back to local model for embeddings.")
                #    APP_BERT_EXECUTION_MODE = 'local' # Temporarily switch for this call
                # else:
                #    return {'factor': None, 'embeddings': None, 'token_map': None}
                return {'factor': None, 'embeddings': None, 'token_map': None} # No fallback for now
        else:
            print("WARN: Remote HF endpoint mode selected, but URL or API token missing. Cannot get remote embeddings.")
            return {'factor': None, 'embeddings': None, 'token_map': None}

    # This 'elif' ensures local execution if mode is 'local' OR if remote was intended but failed and a fallback was implemented above.
    # For now, it's a strict 'elif' APP_BERT_EXECUTION_MODE == 'local':
    elif APP_BERT_EXECUTION_MODE == 'local':
        if not model:
            print("WARN: Local BERT model not available (execution mode is 'local' but model failed to load). Cannot calculate embedding complexity.")
            return {'factor': None, 'embeddings': None, 'token_map': None}
        
        print("Calculating embeddings locally.")
        with torch.no_grad():
            outputs = model(**inputs_on_device, output_hidden_states=True)
        
        # Use the last hidden state (embeddings for each token)
        # Shape: (batch_size, sequence_length, hidden_size)
        # Squeeze out batch_dim (as we process one sentence), move to CPU, convert to numpy
        last_hidden_states_np = outputs.hidden_states[-1].squeeze(0).cpu().numpy()
    
    else: # Should not happen if config is 'local' or 'remote_hf_endpoint'
        print(f"WARN: Invalid APP_BERT_EXECUTION_MODE ('{APP_BERT_EXECUTION_MODE}') in _get_contextual_embedding_complexity. Cannot get embeddings.")
        return {'factor': None, 'embeddings': None, 'token_map': None}

    if last_hidden_states_np is None:
         # This case should ideally be caught by earlier checks, but as a safeguard:
        print("WARN: last_hidden_states_np is None before mapping. Embedding complexity calculation cannot proceed.")
        return {'factor': None, 'embeddings': None, 'token_map': None}

    # --- Map token embeddings back to original words ---
    # This part uses the `inputs` from the LOCAL tokenizer and `last_hidden_states_np`
    # which could be from local model or remote endpoint.
    # Crucially, `inputs['input_ids']` determines the tokens we iterate over for mapping.
    # The number of rows in `last_hidden_states_np` (num_tokens) MUST match `inputs['input_ids'].shape[1]`.
    
    # Validate shapes before proceeding to map (critical if remote embeddings were fetched)
    num_tokens_from_local_tokenizer = inputs['input_ids'].shape[1]
    num_embeddings_received = last_hidden_states_np.shape[0]

    if num_embeddings_received != num_tokens_from_local_tokenizer:
        print(f"CRITICAL ERROR: Mismatch between local tokenizer's token count ({num_tokens_from_local_tokenizer}) and received embeddings count ({num_embeddings_received}) for sentence: '{sentence[:50]}...'. Cannot reliably map embeddings.")
        # This is a fatal error for this function if counts don't match.
        return {'factor': None, 'embeddings': None, 'token_map': None}
        
    token_to_word_mapping = []
    current_word_index = -1
    for i, token_id in enumerate(inputs['input_ids'].squeeze(0).tolist()):
        token_str = tokenizer.decode([token_id])
        # Check if it's a special token (like [CLS], [SEP], [PAD])
        if token_str in tokenizer.all_special_tokens:
            token_to_word_mapping.append(-1) # Mark as not belonging to a word
            continue
        # Check if it's a subword continuation (BERT uses ##)
        if token_str.startswith("##"):
            if current_word_index != -1:
                 token_to_word_mapping.append(current_word_index)
            else: # Should not happen if tokenization is correct
                 token_to_word_mapping.append(-1)
        else:
            # Start of a new word - find the corresponding word in our 'words_for_stats' list
            # This simple alignment might break with complex punctuation/tokenization mismatches
            current_word_index += 1
            # Ensure we don't go out of bounds if tokenization yields more words than stats list
            if current_word_index < len(words_for_stats):
                 token_to_word_mapping.append(current_word_index)
            else:
                 token_to_word_mapping.append(-1) # Mark as invalid alignment

    # Aggregate embeddings for each word
    word_embeddings = {}
    token_counts = {}
    for i, word_idx in enumerate(token_to_word_mapping):
        # Ensure index is valid and within the bounds of words_for_stats
        if word_idx != -1 and word_idx < len(words_for_stats):
            embedding = last_hidden_states_np[i] 
            if word_idx not in word_embeddings:
                word_embeddings[word_idx] = np.zeros_like(embedding)
                token_counts[word_idx] = 0
            word_embeddings[word_idx] += embedding
            token_counts[word_idx] += 1

    # Average the embeddings for words split into multiple tokens
    averaged_word_embeddings = []
    valid_word_indices = sorted(word_embeddings.keys())
    for word_idx in valid_word_indices:
        if token_counts[word_idx] > 0:
            averaged_word_embeddings.append(word_embeddings[word_idx] / token_counts[word_idx])

    if not averaged_word_embeddings:
        print("WARN: Could not extract valid word embeddings.")
        # Return None for embeddings if failed
        return {'factor': 0.0, 'embeddings': None, 'token_map': token_to_word_mapping}

    # --- Calculate Contextual Deviation ---
    embeddings_matrix = np.array(averaged_word_embeddings)
    # Calculate the mean embedding (centroid) for the sentence
    mean_embedding = np.mean(embeddings_matrix, axis=0)

    # Calculate cosine distance of each word embedding from the mean
    # Cosine distance = 1 - cosine similarity
    distances = []
    # Normalize embeddings for cosine similarity calculation
    norm_mean = mean_embedding / np.linalg.norm(mean_embedding)
    for emb in embeddings_matrix:
        norm_emb = emb / np.linalg.norm(emb)
        # Cosine similarity
        similarity = np.dot(norm_emb, norm_mean)
        # Clamp similarity to [-1, 1] due to potential floating point errors
        similarity = np.clip(similarity, -1.0, 1.0)
        # Cosine distance
        distance = 1.0 - similarity
        distances.append(distance)

    # Average distance represents the embedding complexity factor
    # Higher average distance means words are semantically further from the sentence's core meaning
    # Normalize the average distance to be roughly between 0 and 1
    # Cosine distance is already [0, 2]. Dividing by 2 scales it to [0, 1].
    avg_distance = np.mean(distances) if distances else 0.0
    embedding_complexity_factor = avg_distance / 2.0

    # Ensure the factor is clamped between 0 and 1
    embedding_complexity_factor = max(0.0, min(1.0, embedding_complexity_factor))

    # Add confirmation log message
    print(f"DEBUG: Calculated embedding complexity factor: {embedding_complexity_factor:.4f} for sentence: '{sentence[:50]}...' (Mode: {APP_BERT_EXECUTION_MODE})")

    # Return factor, embeddings matrix, and token map
    return {
        'factor': embedding_complexity_factor,
        'embeddings': embeddings_matrix,
        'token_map': token_to_word_mapping
    }


def _get_syntactic_features(spacy_sentence):
    """
    Extracts syntactic features from a spaCy sentence.
    Returns a dictionary of features.
    """
    if not spacy_sentence:
        return {
            "parse_tree_depth": 0,
            "num_clauses": 0,
            "avg_dependency_length": 0.0,
            "has_passive_voice": 0,
        }

    # Parse Tree Depth (max depth of dependency tree)
    # This is a simplified approach; a more robust method might traverse the tree
    parse_tree_depth = 0
    for token in spacy_sentence:
        depth = 0
        ancestor = token
        while ancestor.head != ancestor:
            depth += 1
            ancestor = ancestor.head
        parse_tree_depth = max(parse_tree_depth, depth)

    # Number of Clauses (estimation based on verbs or conjunctions)
    # A simple heuristic: count finite verbs or coordinating conjunctions
    num_clauses = 0
    for token in spacy_sentence:
        # Count finite verbs (VB, VBD, VBG, VBN, VBP, VBZ)
        if token.pos_ == "VERB" and token.tag_ in ["VB", "VBD", "VBG", "VBN", "VBP", "VBZ"]:
             num_clauses += 1
        # Or count coordinating conjunctions (CC) as potential clause separators
        # if token.pos_ == "CC":
        #     num_clauses += 1
    # Ensure at least one clause if there's a verb
    if num_clauses == 0 and any(token.pos_ == "VERB" for token in spacy_sentence):
         num_clauses = 1
    num_clauses = max(1, num_clauses) # Assume at least one clause per sentence

    # Average Dependency Length
    total_dep_length = 0
    num_dependencies = 0
    for token in spacy_sentence:
        if token.head != token: # Exclude the root
            total_dep_length += abs(token.i - token.head.i)
            num_dependencies += 1
    avg_dependency_length = total_dep_length / num_dependencies if num_dependencies > 0 else 0.0

    # Passive Voice Detection (simplified)
    # Look for 'auxpass' dependency (e.g., "was eaten")
    has_passive_voice = 0
    for token in spacy_sentence:
        if token.dep_ == "auxpass":
            has_passive_voice = 1
            break

    return {
        "parse_tree_depth": parse_tree_depth,
        "num_clauses": num_clauses,
        "avg_dependency_length": avg_dependency_length,
        "has_passive_voice": has_passive_voice,
    }

# --- New Metric Helper Functions ---

def _get_dependency_metrics(spacy_sentence):
    """
    Calculates deeper syntactic metrics based on dependency parse.
    Returns a dictionary of raw scores (counts or depths).
    Normalization should happen in the main calculate_complexity function.
    """
    num_tokens = len(spacy_sentence)
    if num_tokens == 0:
        return {
            "complex_dep_count": 0,
            "subordination_count": 0,
            "pp_count": 0,
            "max_pp_nesting_depth": 0,
        }

    complex_dep_count = 0
    subordination_count = 0
    pp_count = 0
    max_pp_nesting_depth = 0
    complex_deps = {'csubj', 'advcl', 'acl'}
    subord_deps = {'mark', 'advcl', 'acl'} # Using deps for clauses, plus 'mark'

    for token in spacy_sentence:
        # 1. Density of Specific Complex Dependency Relations
        if token.dep_ in complex_deps:
            complex_dep_count += 1

        # 2. Subordination Index (Simplified)
        if token.dep_ in subord_deps:
             # Count verbs heading subordinate clauses or subordinating conjunctions
             if token.dep_ == 'mark' or (token.dep_ in {'advcl', 'acl'} and token.pos_ == 'VERB'):
                 subordination_count += 1

        # 3. Prepositional Phrase (PP) Density / Nesting Depth
        is_pp_related = token.dep_ == 'pobj' or token.head.pos_ == 'ADP'
        if is_pp_related:
            pp_count += 1
            # Calculate Nesting Depth
            current_depth = 0
            ancestor = token
            while ancestor.head != ancestor:
                # Check if the head is also part of a PP structure
                # (Simplification: check if head is ADP or its dep is pobj/prep)
                if ancestor.head.pos_ == 'ADP' or ancestor.head.dep_ in {'pobj', 'prep'}:
                     current_depth += 1
                else:
                    # Stop climbing if the chain breaks (e.g., head is verb)
                    # This prevents counting depth across unrelated PPs attached to the same verb.
                    # More sophisticated logic could check if the head is the *object* of another prep.
                    break
                ancestor = ancestor.head
            max_pp_nesting_depth = max(max_pp_nesting_depth, current_depth)

    # Return raw counts/depths. Normalization (e.g., by num_tokens) happens later.
    return {
        "complex_dep_count": complex_dep_count,
        "subordination_count": subordination_count,
        "pp_count": pp_count,
        "max_pp_nesting_depth": max_pp_nesting_depth,
    }


def _get_lexical_metrics(spacy_sentence):
    """
    Calculates lexical/morphological metrics.
    Returns a dictionary of raw scores/ratios.
    """
    num_tokens = len(spacy_sentence)
    if num_tokens == 0:
        return {
            "nominalization_count": 0,
            "content_word_ratio": 0.0,
        }

    nominalization_count = 0
    content_word_count = 0
    function_word_count = 0
    # Common nominalizing suffixes (simplified list, can be expanded)
    nom_suffixes = ('tion', 'ment', 'ness', 'ity', 'ance', 'ence', 'ism', 'ist')
    content_pos = {'NOUN', 'VERB', 'ADJ', 'ADV'}
    function_pos = {'ADP', 'AUX', 'CONJ', 'DET', 'PART', 'PRON', 'SCONJ', 'PUNCT', 'SPACE', 'SYM', 'X'} # Include PUNCT/SPACE etc. as non-content

    for token in spacy_sentence:
        # 1. Nominalization Density (Suffix check method)
        if token.pos_ == 'NOUN' and token.text.lower().endswith(nom_suffixes):
            nominalization_count += 1

        # 2. Ratio of Content Words to Function Words
        if token.pos_ in content_pos:
            content_word_count += 1
        # Consider everything else (including punctuation, spaces if not filtered) as function/non-content
        elif token.pos_ in function_pos or token.is_punct or token.is_space:
             function_word_count += 1
        # Note: Some tokens might not fall into either category if POS tags are unusual.

    total_words = content_word_count + function_word_count
    content_word_ratio = content_word_count / total_words if total_words > 0 else 0.0

    # Return raw count and ratio. Normalization happens later.
    return {
        "nominalization_count": nominalization_count,
        "content_word_ratio": content_word_ratio,
    }


def _get_semantic_coherence(spacy_sentence, averaged_word_embeddings, token_to_word_mapping, words_for_stats):
    """
    Calculates intra-sentence semantic coherence using BERT embeddings.
    Lower average similarity between adjacent content words suggests lower coherence.
    Requires pre-calculated embeddings and the mapping from transformer tokens to words.
    (No changes needed here as it relies on `averaged_word_embeddings` from `_get_contextual_embedding_complexity`)
    Returns the average cosine similarity (float).
    """
    if averaged_word_embeddings is None or averaged_word_embeddings.size == 0:
        return 0.0 # Cannot calculate without embeddings

    content_pos = {'NOUN', 'VERB', 'ADJ', 'ADV'}
    content_word_indices = []
    content_word_embeddings = []

    # Find indices and embeddings of content words in the original sentence order
    word_idx_to_embedding = {i: emb for i, emb in enumerate(averaged_word_embeddings)}

    current_word_idx = -1
    processed_indices = set() # Track word indices already added

    # Iterate through spaCy tokens to maintain sentence order and identify content words
    for token in spacy_sentence:
        # Find the corresponding original word index using a simplified alignment
        # This assumes spaCy tokenization roughly aligns with the words used for BERT
        # A more robust approach might use character offsets if available
        found_match = False
        temp_idx = current_word_idx + 1 # Look ahead
        # This alignment is heuristic and might fail with complex tokenization differences
        if temp_idx < len(words_for_stats) and token.text.lower() == words_for_stats[temp_idx].lower():
             current_word_idx = temp_idx
             found_match = True

        if found_match and token.pos_ in content_pos and current_word_idx in word_idx_to_embedding and current_word_idx not in processed_indices:
             content_word_indices.append(current_word_idx)
             content_word_embeddings.append(word_idx_to_embedding[current_word_idx])
             processed_indices.add(current_word_idx)


    if len(content_word_embeddings) < 2:
        return 1.0 # If less than 2 content words, coherence is trivially high (or undefined)

    # Calculate cosine similarity between adjacent content word embeddings
    similarities = []
    for i in range(len(content_word_embeddings) - 1):
        emb1 = content_word_embeddings[i]
        emb2 = content_word_embeddings[i+1]

        norm1 = np.linalg.norm(emb1)
        norm2 = np.linalg.norm(emb2)

        if norm1 > 0 and norm2 > 0:
            similarity = np.dot(emb1, emb2) / (norm1 * norm2)
            # Clamp similarity to [-1, 1] due to potential floating point errors
            similarity = np.clip(similarity, -1.0, 1.0)
            similarities.append(similarity)

    # Average similarity represents coherence
    avg_similarity = np.mean(similarities) if similarities else 1.0 # Default to high coherence if no pairs

    # Higher score = more coherent. We might invert this later if needed for complexity score.
    return avg_similarity


def calculate_complexity(spacy_sentence, doc, profile, mode='full', analysis_id=None): # Added analysis_id
    """
    Calculates a complexity score for a single sentence based on the provided profile.
    Considers sentence length, average word length, average word frequency,
    contextual embedding complexity, syntactic features, and coreference features.
    Calculation of expensive features is conditional based on the 'mode' parameter.
    Returns a score (float).
    
    Args:
        spacy_sentence: Either a spaCy Span/Doc object or a string
        doc: A spaCy Doc object for context (can be None)
        profile: The audience profile dictionary with weights and normalization values
        mode: 'full' or 'fast' mode for complexity calculation
        analysis_id: Optional ID for progress tracking
    """
    # Handle string input: convert to a format we can work with
    if isinstance(spacy_sentence, str):
        sentence_text = spacy_sentence
        
        # For basic analysis, tokenize the string using nltk if available
        try:
            import nltk
            words_for_stats = [word.lower() for word in nltk.word_tokenize(sentence_text) 
                              if word.isalpha()]
        except:
            # Fallback if nltk not available: simple split and filter
            words_for_stats = [word.lower() for word in sentence_text.split() 
                              if word.isalpha()]
        
        # We'll need this for logging output
        if not hasattr(spacy_sentence, 'text'):
            spacy_sentence_text = sentence_text
    else:
        # Original behavior for spaCy objects
        sentence_text = spacy_sentence.text
        spacy_sentence_text = sentence_text
        
        # Use spaCy tokens for consistency
        words_for_stats = [token.text.lower() for token in spacy_sentence if token.is_alpha]

    # Use profile-specific constants
    weights = profile['weights']
    norm = profile['normalization']

    if not words_for_stats:
        return 0.0 # Handle empty sentences

    # --- Statistical Factors (Always calculated) ---
    sentence_length = len(words_for_stats)
    total_word_length = sum(len(word) for word in words_for_stats)
    average_word_length = total_word_length / sentence_length if sentence_length > 0 else 0

    # --- Frequency Factor Calculation (Revised to handle unknown words) ---
    # Revision Goal: Ensure words not found in the frequency list (likely rare or technical)
    # contribute maximum complexity (score=1.0) to the frequency factor, instead of being ignored.
    # The final average is calculated over ALL words in the sentence.
    total_freq_score_adjusted = 0
    num_words_total = len(words_for_stats)
    max_log_freq = norm['max_log_frequency']

    if num_words_total > 0:
        words_with_freq = 0
        total_log_freq_score_known = 0
        for word in words_for_stats:
            freq = get_word_frequency(word)
            if freq > 0:
                log_freq = math.log10(freq + 1)
                # Higher score for rarer words (lower log_freq)
                freq_score = max(0.0, min(1.0, (max_log_freq - log_freq) / max_log_freq)) # Ensure 0-1 range
                total_log_freq_score_known += freq_score
                words_with_freq += 1
            # else: word is unknown (freq=0)

        # Assign max complexity score (1.0) to unknown words
        num_unknown_words = num_words_total - words_with_freq
        total_freq_score_adjusted = total_log_freq_score_known + (num_unknown_words * 1.0)

        # Average over ALL words
        average_frequency_score = total_freq_score_adjusted / num_words_total
    else:
        average_frequency_score = 0.0
    # --- End Revised Frequency Calculation ---

    # Remove capping at 1.5 to allow extreme lengths to contribute more
    length_factor = sentence_length / norm['sentence_length']
    word_len_factor = average_word_length / norm['avg_word_length']
    frequency_factor = average_frequency_score # Now correctly handles unknown words

    # --- Conditional Expensive Factors ---
    embedding_factor = 0.0 # BERT variance
    syntactic_factor = 0.0 # Original syntactic features
    dependency_factor = 0.0 # New dependency metrics
    lexical_factor = 0.0 # New lexical metrics
    semantic_coherence_factor = 0.0 # New semantic coherence metric
    # coreferent_mentions_factor = 0.0 # Disabled

    # Initialize variables to store intermediate results needed across calculations
    embeddings_matrix = None
    token_map = None
    
    # Get total tokens - need special handling for string input
    if isinstance(spacy_sentence, str):
        num_tokens = len(words_for_stats)  # Approximate for string input
    else:
        num_tokens = len(spacy_sentence)   # Exact for spaCy object


    if mode == 'full':
        # --- Check for cancellation before expensive calculations ---
        if analysis_id and task_manager.is_cancelled(analysis_id):
            logging.info(f"Task {analysis_id}: Cancelled before expensive calculations for sentence: '{spacy_sentence_text[:50]}...'")
            return 0.0 # Return neutral score if cancelled here

        # For string input in full mode, we need spaCy processing for advanced metrics
        # If spacy_sentence is a string and nlp is available, process it
        if isinstance(spacy_sentence, str) and nlp:
            spacy_sentence = nlp(sentence_text)  # Convert to spaCy Doc
            # Update num_tokens now that we have a spaCy object
            num_tokens = len(spacy_sentence)

        # Skip advanced metrics if we don't have a spaCy object at this point
        if not isinstance(spacy_sentence, str):
            # --- 1. Contextual Embedding Factor (Variance) & Get Embeddings ---
            embedding_result = _get_contextual_embedding_complexity(sentence_text, words_for_stats)
            embedding_factor = embedding_result.get('factor', 0.0) if embedding_result else 0.0
            embeddings_matrix = embedding_result.get('embeddings')
            token_map = embedding_result.get('token_map')

            # --- 2. Original Syntactic Features ---
            syntactic_features = _get_syntactic_features(spacy_sentence)
            # Normalize original syntactic features
            parse_tree_depth_factor = min(syntactic_features.get('parse_tree_depth', 0) / norm.get('max_parse_tree_depth', 15.0), 1.5)
            num_clauses_factor = min(syntactic_features.get('num_clauses', 0) / norm.get('max_num_clauses', 5.0), 1.5)
            avg_dep_length_factor = min(syntactic_features.get('avg_dependency_length', 0.0) / norm.get('max_avg_dependency_length', 10.0), 1.5)
            passive_voice_factor = syntactic_features.get('has_passive_voice', 0) # Binary (0 or 1)
            # Combine original syntactic factors
            syntactic_weight = weights.get('syntactic_complexity', 0)
            if syntactic_weight > 0:
                 syntactic_factor = (parse_tree_depth_factor + num_clauses_factor + avg_dep_length_factor + passive_voice_factor) / 4.0
                 syntactic_factor = max(0.0, min(1.0, syntactic_factor)) # Clamp to 0-1
            else:
                 syntactic_factor = 0.0
            logging.debug(f"Task {analysis_id}: Original Syntactic Features: {syntactic_features}, Combined Factor: {syntactic_factor:.3f}")

            # --- 3. Dependency Complexity Features ---
            dependency_metrics = _get_dependency_metrics(spacy_sentence)
            # Normalize dependency metrics (calculate densities first)
            complex_dep_density = dependency_metrics.get('complex_dep_count', 0) / num_tokens if num_tokens > 0 else 0
            subordination_density = dependency_metrics.get('subordination_count', 0) / num_tokens if num_tokens > 0 else 0
            pp_density = dependency_metrics.get('pp_count', 0) / num_tokens if num_tokens > 0 else 0
            pp_nesting_depth = dependency_metrics.get('max_pp_nesting_depth', 0)

            complex_dep_factor = min(complex_dep_density / norm.get('max_complex_dep_density', 0.2), 1.5)
            subordination_factor = min(subordination_density / norm.get('max_subordination_density', 0.2), 1.5)
            pp_density_factor = min(pp_density / norm.get('max_pp_density', 0.4), 1.5)
            pp_nesting_factor = min(pp_nesting_depth / norm.get('max_pp_nesting_depth', 5.0), 1.5)
            # Combine dependency factors (average)
            dependency_weight = weights.get('dependency_complexity', 0)
            if dependency_weight > 0:
                dependency_factor = (complex_dep_factor + subordination_factor + pp_density_factor + pp_nesting_factor) / 4.0
                dependency_factor = max(0.0, min(1.0, dependency_factor)) # Clamp to 0-1
            else:
                dependency_factor = 0.0
            logging.debug(f"Task {analysis_id}: Dependency Metrics: {dependency_metrics}, Combined Factor: {dependency_factor:.3f}")


            # --- 4. Lexical Complexity Features ---
            lexical_metrics = _get_lexical_metrics(spacy_sentence)
            # Normalize lexical metrics
            nominalization_density = lexical_metrics.get('nominalization_count', 0) / num_tokens if num_tokens > 0 else 0
            content_ratio = lexical_metrics.get('content_word_ratio', 0.0)

            nominalization_factor = min(nominalization_density / norm.get('max_nominalization_density', 0.15), 1.5)
            # Content ratio: Higher deviation from target = higher complexity factor
            target_ratio = norm.get('target_content_word_ratio', 0.6)
            # Normalize deviation: max deviation is max(target_ratio, 1-target_ratio)
            max_deviation = max(target_ratio, 1.0 - target_ratio)
            content_ratio_deviation = abs(content_ratio - target_ratio)
            content_ratio_factor = min(content_ratio_deviation / max_deviation, 1.0) if max_deviation > 0 else 0.0

            # Combine lexical factors (average)
            lexical_weight = weights.get('lexical_complexity', 0)
            if lexical_weight > 0:
                lexical_factor = (nominalization_factor + content_ratio_factor) / 2.0
                lexical_factor = max(0.0, min(1.0, lexical_factor)) # Clamp to 0-1
            else:
                lexical_factor = 0.0
            logging.debug(f"Task {analysis_id}: Lexical Metrics: {lexical_metrics}, Combined Factor: {lexical_factor:.3f}")

            # --- 5. Semantic Coherence Factor ---
            # Requires embeddings_matrix and token_map from step 1
            raw_coherence_score = _get_semantic_coherence(spacy_sentence, embeddings_matrix, token_map, words_for_stats)
            # Normalize coherence: Lower score = higher complexity factor
            min_coherence = norm.get('min_semantic_coherence', 0.5)
            # Factor = how much the score is *below* the minimum threshold
            # Scale it to 0-1 range. If score > min_coherence, factor is 0.
            semantic_coherence_factor = max(0.0, (min_coherence - raw_coherence_score)) / min_coherence if min_coherence > 0 else 0.0
            semantic_coherence_factor = max(0.0, min(1.0, semantic_coherence_factor)) # Clamp 0-1
            logging.debug(f"Task {analysis_id}: Semantic Coherence Score: {raw_coherence_score:.3f}, Factor: {semantic_coherence_factor:.3f}")


    # --- Combine Factors using Weights based on Mode ---
    if mode == 'fast':
        # Use independent FAST_MODE_WEIGHTS
        score = (length_factor * FAST_MODE_WEIGHTS.get('sentence_length', 0)) + \
                (word_len_factor * FAST_MODE_WEIGHTS.get('avg_word_length', 0)) + \
                (frequency_factor * FAST_MODE_WEIGHTS.get('avg_word_frequency', 0))
        logging.debug(f"Task {analysis_id}: Calculated Score (fast mode using FAST_MODE_WEIGHTS): {score:.3f} for sentence: '{spacy_sentence_text[:50]}...'")
    elif mode == 'full':
        # Use profile weights from AUDIENCE_PROFILES for full analysis
        # Use .get() for weights to avoid KeyError if a profile is missing a new weight
        score = (length_factor * weights.get('sentence_length', 0)) + \
                (word_len_factor * weights.get('avg_word_length', 0)) + \
                (frequency_factor * weights.get('avg_word_frequency', 0)) + \
                (embedding_factor * weights.get('embedding_complexity', 0)) + \
                (syntactic_factor * weights.get('syntactic_complexity', 0)) + \
                (dependency_factor * weights.get('dependency_complexity', 0)) + \
                (lexical_factor * weights.get('lexical_complexity', 0)) + \
                (semantic_coherence_factor * weights.get('semantic_coherence', 0))
                # (coreferent_mentions_factor * weights.get('coreference_complexity', 0)) # Disabled
        logging.debug(f"Task {analysis_id}: Calculated Score (full mode using profile weights): {score:.3f} for sentence: '{spacy_sentence_text[:50]}...'")

        # --- Log individual normalized factors for debugging ---
        factors_log = {
            "sentence_start": spacy_sentence_text[:30], # Identify sentence
            "length_factor": length_factor,
            "word_len_factor": word_len_factor,
            "frequency_factor": frequency_factor,
            "embedding_factor": embedding_factor,
            "syntactic_factor": syntactic_factor,
            "dependency_factor": dependency_factor,
            "lexical_factor": lexical_factor,
            "semantic_coherence_factor": semantic_coherence_factor
        }
        # Use info level for easier visibility during debugging
        logging.info(f"Task {analysis_id}: DEBUG FACTORS (Full Mode): {factors_log}")
        # --- End Logging ---

    else:
        # Fallback or error handling if mode is invalid
        logging.warning(f"Task {analysis_id}: Invalid mode '{mode}' provided to calculate_complexity. Defaulting score to 0.0.")
        score = 0.0

    # The max possible score will need re-evaluation with new factors, especially for 'full' mode.
    # The thresholds in AUDIENCE_PROFILES might need adjustment based on observed score ranges from 'full' mode.

    return round(score, 3) # Ensure calculate_complexity returns only the float score

def get_overall_complexity_level(score, profile):
    """Maps an overall score to a level, description, and color class based on the profile."""
    thresholds = profile['thresholds'] # Use profile thresholds
    if score < thresholds['very_simple']:
        return {"level": 1, "description": "Very Simple", "color_class": "bg-green-500"}
    elif score < thresholds['simple']:
        return {"level": 2, "description": "Simple", "color_class": "bg-lime-500"}
    elif score < thresholds['moderate']:
        return {"level": 3, "description": "Moderate", "color_class": "bg-yellow-500"}
    elif score < thresholds['complex']:
        return {"level": 4, "description": "Complex", "color_class": "bg-orange-500"}
    else:
        return {"level": 5, "description": "Very Complex", "color_class": "bg-red-500"}


def analyze_single_spacy_sentence(spacy_sentence_arg, doc_arg, profile, sentence_index, target_audience_name, mode='full', analysis_id=None):
    """
    Analyzes the complexity of a single spaCy sentence based on the provided profile.
    Checks cache before calculation. Stores result in cache.
    # Requires the full spaCy document for coreference resolution. # Commented out as doc might be sentence-specific
    Accepts an 'analysis_id' for cancellation checks.
    Returns a dictionary containing:
        - 'sentence': The original sentence text.
        - 'score': The complexity score (float).
        - 'start': The start character index (relative to the sentence itself if not a span from a larger doc).
        - 'end': The end character index (relative to the sentence itself if not a span from a larger doc).
        - 'index': The index of the sentence in the document.
        - 'syntactic_features': Dictionary of syntactic features (may be empty in 'fast' mode).
        # - 'coreference_features': Dictionary of coreference features (disabled).
        - 'mode': The analysis mode used ('fast' or 'full').
    Returns a dictionary like: {'result': { ... sentence data ... }, 'from_cache': bool}
    """
    # task_manager.update_progress(analysis_id, f"Analyzing sentence {sentence_index + 1}...") # Update progress REMOVED

    text_to_analyze_and_return = ""
    char_start = 0  # Default for isolated sentences or Docs
    char_end = 0    # Default for isolated sentences or Docs
    
    # This will be the object used for actual complexity calculation (Span, Doc, or str)
    spacy_object_for_calculation = spacy_sentence_arg

    if isinstance(spacy_sentence_arg, str):
        text_to_analyze_and_return = spacy_sentence_arg
        char_end = len(text_to_analyze_and_return) # char_start remains 0
        if nlp and mode != 'fast':
            # Process the string. The result is a Doc object.
            doc_from_string = nlp(text_to_analyze_and_return)
            spacy_object_for_calculation = doc_from_string
            # If doc_arg (context) was None, use this new Doc as the context.
            if doc_arg is None:
                doc_arg = doc_from_string
        # Else (not nlp or fast mode), spacy_object_for_calculation remains the string.
        
    elif hasattr(spacy_sentence_arg, 'text'): # Covers both spacy.tokens.Doc and spacy.tokens.Span
        text_to_analyze_and_return = spacy_sentence_arg.text
        spacy_object_for_calculation = spacy_sentence_arg

        if hasattr(spacy_sentence_arg, 'start_char') and hasattr(spacy_sentence_arg, 'end_char'): # It's a Span
            char_start = spacy_sentence_arg.start_char
            char_end = spacy_sentence_arg.end_char
            if doc_arg is None and hasattr(spacy_sentence_arg, 'doc'): # If it's a span, its .doc is the natural context
                doc_arg = spacy_sentence_arg.doc
        else: # It's likely a Doc (but not a string), or an object with .text but no .start_char/.end_char
            char_end = len(text_to_analyze_and_return) # char_start remains 0
            if doc_arg is None: # If it's a Doc, it's its own context
                doc_arg = spacy_sentence_arg
    else:
        # Fallback for unexpected type
        logger.warning(f"Unexpected type for spacy_sentence_arg in analyze_single_spacy_sentence: {type(spacy_sentence_arg)}. Converting to string.")
        text_to_analyze_and_return = str(spacy_sentence_arg)
        char_end = len(text_to_analyze_and_return) # char_start remains 0
        # spacy_object_for_calculation remains spacy_sentence_arg (which is now a string or original unknown type)
        # doc_arg remains as passed

    # --- Cache Check ---
    # Use sentence text + profile name + mode for a unique key
    cache_key_string = f"{text_to_analyze_and_return.strip()}|{target_audience_name}|{mode}"
    cache_key = hashlib.sha1(cache_key_string.encode('utf-8')).hexdigest()

    cached_result = cache.get(cache_key)
    if cached_result:
        logging.debug(f"Cache HIT for sentence index {sentence_index} (Key: {cache_key[:8]}...)")
        # Ensure the cached result has the correct index and mode, just in case
        cached_result['index'] = sentence_index
        cached_result['mode'] = mode
        # Update start/end and sentence text from current context (important if only text was cached previously)
        cached_result['start'] = char_start
        cached_result['end'] = char_end
        cached_result['sentence'] = text_to_analyze_and_return
        
        return {'result': cached_result, 'from_cache': True}
    else:
        logging.debug(f"Cache MISS for sentence index {sentence_index} (Key: {cache_key[:8]}...)")
    # --- End Cache Check ---

    if not text_to_analyze_and_return.strip():
        # Return a basic result even for empty sentences if needed for sequential flow structure
         result = { # Define result dict
            "sentence": text_to_analyze_and_return,
            "score": 0.0,
            "level": "No sentences found", # Consistent with other parts of the code
            "color_class": "bg-gray-600",
            "start": char_start,
            "end": char_end,
            "index": sentence_index,
            "syntactic_features": {},
            "mode": mode
        }
         # --- Cache Set (even for empty/basic) ---
         cache.set(cache_key, result)
         # --- End Cache Set ---
         # Return wrapped result for empty sentence (not from cache calculation)
         return {'result': result, 'from_cache': False}


    # Calculate complexity using the potentially processed spaCy object or string
    final_complexity_score = calculate_complexity(spacy_object_for_calculation, doc_arg, profile, mode=mode, analysis_id=analysis_id)

    # Get the descriptive level for this specific sentence using its score
    level_info = get_overall_complexity_level(final_complexity_score, profile)

    result = { 
        "sentence": text_to_analyze_and_return,  # Always use the determined original input sentence text
        "score": final_complexity_score,
        "level": level_info['description'],  # Add descriptive level string
        "color_class": level_info['color_class'], # Add color class for consistency
        "start": char_start,
        "end": char_end,
        "index": sentence_index,
        "syntactic_features": {}, # Placeholder, actual features might be added if mode=='full' logic existed here
        "mode": mode
    }

    # --- Cache Set --- 
    cache.set(cache_key, result)
    logging.debug(f"Stored result in cache for sentence index {sentence_index} (Key: {cache_key[:8]}...)")
    # --- End Cache Set ---

    # Return wrapped result indicating it was newly calculated
    return {'result': result, 'from_cache': False}


def analyze_text_complexity(plain_text_for_doc_stats: str, sentences_list: list[str], target_audience="Standard", mode='full', analysis_id=None):
    """
    Analyzes text for complexity, providing an overall score, per-sentence scores,
    and readability metrics.
    Args:
        plain_text_for_doc_stats (str): The full plain text for document-level statistics.
        sentences_list (list[str]): A list of sentence strings (e.g., from PDF extraction)
                                     for per-sentence analysis. These sentences are expected
                                     to be pre-processed/normalized as needed for consistency
                                     with coordinate mapping.
        target_audience (str): The name of the audience profile to use.
        mode (str): 'full' or 'fast'.
        analysis_id (str, optional): ID for tracking progress with task_manager.
    """
    # task_manager.update_progress(analysis_id, "Starting complexity analysis...") # Update progress REMOVED

    # Select the profile based on target_audience, default to Standard
    profile = AUDIENCE_PROFILES.get(target_audience, AUDIENCE_PROFILES["Standard"])

    # --- Check for cancellation before starting ---
    if analysis_id and task_manager.is_cancelled(analysis_id):
        logging.info(f"Analysis (ID: {analysis_id}) cancelled before starting.")
        return {
            "results": [],
            "overall_level": {"level": 0, "description": "Analysis cancelled", "color_class": "bg-gray-600"},
            "readability_scores": {"flesch_kincaid_grade": None, "gunning_fog": None, "smog_index": None},
            "target_readability_scores": profile['target_readability']
        }

    if not plain_text_for_doc_stats or not sentences_list or not target_audience or not mode or not nlp: # Check if spaCy model loaded
        print("WARN: spaCy model not loaded or text is empty. Returning basic analysis.")
        return {
            "results": [],
            "overall_level": {"level": 0, "description": "Enter text to analyze (spaCy unavailable)", "color_class": "bg-gray-600"},
            "readability_scores": {"flesch_kincaid_grade": None, "gunning_fog": None, "smog_index": None},
            "target_readability_scores": profile['target_readability']
        }

    # --- Check for cancellation before potentially long spaCy processing ---
    if analysis_id and task_manager.is_cancelled(analysis_id):
        logging.info(f"Analysis (ID: {analysis_id}) cancelled before spaCy processing.")
        # Return cancelled status (consistent with check above)
        return {
            "results": [],
            "overall_level": {"level": 0, "description": "Analysis cancelled", "color_class": "bg-gray-600"},
            "readability_scores": {"flesch_kincaid_grade": None, "gunning_fog": None, "smog_index": None},
            "target_readability_scores": profile['target_readability']
        }

    # Process the entire text with spaCy once to get the document and sentences
    try:
        logging.debug(f"Task {analysis_id}: Starting spaCy processing in analyze_text_complexity.")
        doc = nlp(plain_text_for_doc_stats)
        logging.debug(f"Task {analysis_id}: Finished spaCy processing in analyze_text_complexity.")
        if not doc.has_annotation("SENT_START"):
              print("WARN: spaCy sentence segmentation failed. Cannot perform analysis.")
              # Correctly indented return block
              return {
                  "results": [],
                  "overall_level": {"level": 0, "description": "Sentence segmentation failed", "color_class": "bg-gray-600"},
                  "readability_scores": {"flesch_kincaid_grade": None, "gunning_fog": None, "smog_index": None},
                  "target_readability_scores": profile['target_readability']
              }
    except Exception as e:
        print(f"ERROR processing text with spaCy: {e}")
        return {
            "results": [],
            "overall_level": {"level": 0, "description": f"Analysis failed: {e}", "color_class": "bg-red-600"},
            "readability_scores": {"flesch_kincaid_grade": None, "gunning_fog": None, "smog_index": None},
            "target_readability_scores": profile['target_readability']
        }

    results = []
    cancelled_mid_loop = False # Flag to track cancellation during loop
    
    # Correctly get Spans or an empty list if doc is None or has no sentences
    spacy_sentences_from_doc = []
    if doc and doc.has_annotation("SENT_START"):
        spacy_sentences_from_doc = list(doc.sents)
    elif doc and not doc.has_annotation("SENT_START") and len(list(doc.sents)) > 0 : # Added this condition
        logger.warning(f"spaCy doc for (ID: {analysis_id}) produced sentences but no SENT_START annotation. Using doc.sents anyway.")
        spacy_sentences_from_doc = list(doc.sents)
    elif doc: # doc exists but no sents or no annotation
        logger.warning(f"spaCy doc for (ID: {analysis_id}) has no sentences or no SENT_START annotation.")
    # If doc is None, spacy_sentences_from_doc remains empty.

    # --- Determine which list of sentences to iterate over ---
    # ALWAYS prioritize sentences_list to maintain mapping with coordinates.
    sentences_to_iterate = sentences_list
    using_spacy_spans_directly = False # Since sentences_list contains strings

    if not sentences_list:
        logger.warning(f"analyze_text_complexity (ID: {analysis_id}): The provided sentences_list is empty.")
        if spacy_sentences_from_doc and len(spacy_sentences_from_doc) > 0:
            logger.info(f"analyze_text_complexity (ID: {analysis_id}): Falling back to spaCy's {len(spacy_sentences_from_doc)} sentences as sentences_list was empty.")
            sentences_to_iterate = spacy_sentences_from_doc
            using_spacy_spans_directly = True # Now using spaCy's spans
        else:
            logger.warning(f"analyze_text_complexity (ID: {analysis_id}): Both pre-segmented sentences_list and spaCy's segmentation are empty. No sentences to analyze.")
            # Return early if no sentences at all
            return {
                "results": [],
                "overall_level": {"level": 0, "description": "No sentences found to analyze", "color_class": "bg-gray-600"},
                "readability_scores": {"flesch_kincaid_grade": None, "gunning_fog": None, "smog_index": None},
                "target_readability_scores": profile['target_readability'],
                "total_sentences_provided": 0,
                "total_sentences_analyzed": 0
            }
    elif len(spacy_sentences_from_doc) != len(sentences_list):
        logger.warning(f"Mismatch (ID: {analysis_id}): spaCy found {len(spacy_sentences_from_doc)} sents from full text, while pre-segmented list had {len(sentences_list)}. "
                       f"Prioritizing pre-segmented list ({len(sentences_list)} sentences) to maintain coordinate mapping integrity.")
    else: # lengths are the same
        logger.info(f"analyze_text_complexity (ID: {analysis_id}): Using pre-segmented sentences_list ({len(sentences_list)} sentences). "
                    f"spaCy also found {len(spacy_sentences_from_doc)} sentences from the full text, counts match.")

    # Ensure sentences_to_iterate is not empty before proceeding to the loop
    if not sentences_to_iterate:
        logger.error(f"analyze_text_complexity (ID: {analysis_id}): sentences_to_iterate is unexpectedly empty after decision logic. Aborting analysis for this request.")
        # This case should ideally be caught by the "No sentences found to analyze" return above,
        # but as a safeguard:
        return {
            "results": [],
            "overall_level": {"level": 0, "description": "Internal error: No sentences available for loop", "color_class": "bg-red-600"},
            "readability_scores": {"flesch_kincaid_grade": None, "gunning_fog": None, "smog_index": None},
            "target_readability_scores": profile['target_readability'],
            "total_sentences_provided": len(sentences_list), # Original count
            "total_sentences_analyzed": 0
        }

    # --- Per-Sentence Analysis Loop ---
    all_sentence_results = []
    # Keep track of search position in full text for fallback mode
    current_search_offset_in_full_text = 0

    for i, sentence_obj_or_str in enumerate(sentences_to_iterate):
        if task_manager.is_cancelled(analysis_id): # Check before each sentence
            logging.info(f"Analysis (ID: {analysis_id}) cancelled during sentence loop at index {i}.")
            cancelled_mid_loop = True
            break # Exit the loop

        # Determine the mode to be passed to analyze_single_spacy_sentence, which in turn passes it to calculate_complexity.
        # This mode must be either 'full' or 'fast' for calculate_complexity.
        mode_for_sentence_calculation = 'fast' # Default to 'fast' for safety
        if mode == 'full' or mode == 'fast_final_detailed': # These parent modes require full calculation for sentences
            mode_for_sentence_calculation = 'full'
        elif mode == 'fast': # This parent mode requires fast calculation for sentences
            mode_for_sentence_calculation = 'fast'
        # Any other 'mode' value for analyze_text_complexity will result in 'fast' calculation for sentences.

        # Call analyze_single_spacy_sentence.
        # It will internally handle if sentence_obj_or_str is a Span or string for metric calculation.
        # The `doc` passed is the one from nlp(plain_text_for_doc_stats), which might be None if spaCy failed.
        # analyze_single_spacy_sentence needs to be robust to doc=None for some metrics.
        sentence_analysis_output_dict = analyze_single_spacy_sentence(
            sentence_obj_or_str,
            doc, # This is the Doc object from plain_text_for_doc_stats (or None)
            profile,
            i, # Index
            target_audience_name=target_audience,
            mode=mode_for_sentence_calculation, # Pass the corrected mode ('full' or 'fast')
            analysis_id=analysis_id
        )

        if sentence_analysis_output_dict and 'result' in sentence_analysis_output_dict:
            processed_sentence_result = sentence_analysis_output_dict['result']

            if not using_spacy_spans_directly:
                # Fallback mode: sentence_obj_or_str is a STRING.
                # Offsets from analyze_single_spacy_sentence are 0-based relative to the string itself.
                # We must correct them relative to plain_text_for_doc_stats.
                sentence_str_to_find = str(sentence_obj_or_str) # Ensure it's a string

                # Ensure the sentence text in the result is the original string from sentences_list
                processed_sentence_result['sentence'] = sentence_str_to_find
                
                try:
                    # Find the current sentence string in the full text, starting from the last offset
                    actual_start = plain_text_for_doc_stats.find(sentence_str_to_find, current_search_offset_in_full_text)
                    
                    if actual_start != -1:
                        actual_end = actual_start + len(sentence_str_to_find)
                        processed_sentence_result['start'] = actual_start
                        processed_sentence_result['end'] = actual_end
                        # Update search offset for the next iteration to ensure we find subsequent occurrences
                        current_search_offset_in_full_text = actual_end 
                    else:
                        # This is problematic: the sentence string from sentences_list was not found
                        # sequentially in plain_text_for_doc_stats.
                        # Log an error. Offsets will remain 0-based from analyze_single_spacy_sentence.
                        logger.error(
                            f"Fallback offset calculation (ID: {analysis_id}): Could not find sentence string "
                            f"'{sentence_str_to_find[:50]}...' in plain_text_for_doc_stats "
                            f"starting from offset {current_search_offset_in_full_text}. "
                            f"Using 0-based offsets for this sentence."
                        )
                        # To prevent finding earlier occurrences in next iteration if this was a fluke,
                        # advance offset by length of string anyway, though this is a heuristic.
                        current_search_offset_in_full_text += len(sentence_str_to_find)

                except Exception as e:
                    logger.error(
                        f"Fallback offset calculation (ID: {analysis_id}): Exception while finding sentence string: {e}. "
                        f"Using 0-based offsets for this sentence '{sentence_str_to_find[:50]}...'.",
                        exc_info=True
                    )
                    # Advance offset heuristically
                    current_search_offset_in_full_text += len(sentence_str_to_find)

            all_sentence_results.append(processed_sentence_result)
        else:
            logger.warning(f"Sentence analysis for obj/str (ID: {analysis_id}) '{str(sentence_obj_or_str)[:50]}...' at index {i} did not yield a valid result dict.")
            # Append a placeholder or skip? For now, skip.
            # Consider what should happen if a single sentence analysis fails.

    # --- Aggregation and Final Output ---
    if cancelled_mid_loop:
        # Return partial results but indicate cancellation in overall level
        logging.info(f"Analysis (ID: {analysis_id}) returning partial results due to cancellation.")
        return {
            "results": all_sentence_results, # Return results processed so far
            "overall_level": {"level": 0, "description": "Analysis cancelled", "color_class": "bg-gray-600"},
            "readability_scores": {"flesch_kincaid_grade": None, "gunning_fog": None, "smog_index": None}, # Or calculate based on partial text? For now, None.
            "target_readability_scores": profile['target_readability'],
            "total_sentences_provided": len(sentences_to_iterate),
            "total_sentences_analyzed": len(all_sentence_results)
        }

    # Calculate overall score (average of sentence scores) only if results exist and not cancelled
    # This block should be at the same indentation level as the 'if cancelled_mid_loop:' block
    if all_sentence_results:
        total_score = sum(r['score'] for r in all_sentence_results)
        num_sentences = len(all_sentence_results)
        overall_score = round(total_score / num_sentences, 3) if num_sentences > 0 else 0.0
        overall_level_details = get_overall_complexity_level(overall_score, profile)
    else: # Handle case where text had no valid sentences after processing
         overall_score = 0.0
         overall_level_details = {"level": 0, "description": "No sentences found", "color_class": "bg-gray-600"}

    # --- Calculate Standard Readability Scores ---
    try:
        flesch_kincaid_grade = round(textstat.flesch_kincaid_grade(plain_text_for_doc_stats), 1)
        gunning_fog = round(textstat.gunning_fog(plain_text_for_doc_stats), 1)
        smog_index = round(textstat.smog_index(plain_text_for_doc_stats), 1)
    except Exception as e:
        print(f"Error calculating textstat scores: {e}")
        flesch_kincaid_grade = None
        gunning_fog = None
        smog_index = None

    # === Logging before return ===
    logger.info(f"analyze_text_complexity: Final count of sentence results (in 'results' list var): {len(all_sentence_results)} for analysis_id: {analysis_id}")
    if all_sentence_results and len(all_sentence_results) > 0:
        try:
            sample_sentence_log = str(all_sentence_results[0])[:250] # Increased sample length
        except Exception as e_log_sample:
            sample_sentence_log = f"Error logging sample: {e_log_sample}"
        logger.info(f"analyze_text_complexity: First sentence data (sample from 'results' list var): {sample_sentence_log}...")
    elif not all_sentence_results:
        logger.warning(f"analyze_text_complexity: 'results' list is None or empty before returning for analysis_id: {analysis_id}")
    # === End Logging ===

    # Consolidate return structure: ensure 'sentences' key holds the list of sentence details.
    # The variable holding sentence details is 'results'.
    # Other overall metrics are calculated above.
    final_result = {
        "overall_score_avg": overall_score, # overall_score is calculated above
        "overall_score_median": overall_score, # Using avg for median for now, can be refined if needed
        "overall_level": overall_level_details, # overall_level_details is calculated above
        "readability_scores": {
            "flesch_kincaid_grade": flesch_kincaid_grade,
            "gunning_fog": gunning_fog,
            "smog_index": smog_index
        },
        "sentences": all_sentence_results,  # <--- Key used by tasks.py, value is the 'results' list
        "total_sentences_in_report": len(all_sentence_results) if all_sentence_results else 0,
        "target_audience_profile": target_audience,
        "target_readability_scores": profile['target_readability'], # Added from original structure
        "mode": mode,
        "analysis_id": analysis_id,
        "text_length_chars": len(plain_text_for_doc_stats),
        "text_length_words": len(plain_text_for_doc_stats.split()), # A simple word count, spaCy's might be more accurate
        "text_preview": plain_text_for_doc_stats[:100] + "..." if len(plain_text_for_doc_stats) > 100 else plain_text_for_doc_stats,
        "total_sentences_provided": len(sentences_to_iterate),
        "total_sentences_analyzed": len(all_sentence_results)
    }
    # task_manager.update_progress(analysis_id, "Complexity analysis complete.") # Final update REMOVED
    # logger.debug(f"Analysis results for audience \'{target_audience}\': {final_result}")
    return final_result

# Example usage (for testing purposes)
if __name__ == '__main__':
    # # Add neuralcoref if available (Disabled - not used)
    # # try:
    # #     import neuralcoref
    # #     if nlp and 'neuralcoref' not in nlp.pipe_names:
    # #          coref = neuralcoref.NeuralCoref(nlp.vocab)
    # #          nlp.add_pipe(coref, name='neuralcoref')
    # # except ImportError:
    # #     print("INFO: neuralcoref not installed, coreference features will be zero.")
    # #     pass

    test_text_simple = """
    This is a simple sentence. It should be green. The cat sat on the mat.
    """
    test_text_complex = """
    This sentence, however, is potentially a little bit longer and might perhaps score slightly higher, maybe yellow. Subsequently, utilizing considerably more sophisticated vocabulary and constructing elongated phrasal structures inevitably escalates the calculated complexity assessment towards the orange or even red spectrum.
    """
    test_text_coref = """
    John Smith went to the park. He saw Mary there. She gave him a ball. He threw it back to her.
    """

    print("--- Analysis (Simple) for General Public ---")
    analysis_results_gp_simple = analyze_text_complexity(test_text_simple, target_audience="General Public")
    print(f"Overall Level: {analysis_results_gp_simple['overall_level']['level']} ({analysis_results_gp_simple['overall_level']['description']})")
    if analysis_results_gp_simple.get('readability_scores'):
        print("Readability Scores:")
        for name, score in analysis_results_gp_simple['readability_scores'].items():
            target = analysis_results_gp_simple['target_readability_scores'].get(name)
            target_str = f"(Target: {target[0]}-{target[1]})" if target and target[1] else f"(Target: {target[0]}+)" if target else ""
            print(f"  {name}: {score} {target_str}")
    print("\nSentence Analysis:")
    for result in analysis_results_gp_simple['sentences']:
        print(f"Score: {result['score']:.3f} | Indices: {result['start']}-{result['end']} | Sentence: {result['sentence']}")
        print(f"  Syntactic Features: {result.get('syntactic_features', {})}")
        # print(f"  Coreference Features: {result.get('coreference_features', {})}") # Disabled


    print("\n--- Analysis (Complex) for Academic / Technical ---")
    analysis_results_acad_complex = analyze_text_complexity(test_text_complex, target_audience="Academic / Technical")
    print(f"Overall Level: {analysis_results_acad_complex['overall_level']['level']} ({analysis_results_acad_complex['overall_level']['description']})")
    if analysis_results_acad_complex.get('readability_scores'):
        print("Readability Scores:")
        for name, score in analysis_results_acad_complex['readability_scores'].items():
            target = analysis_results_acad_complex['target_readability_scores'].get(name)
            target_str = f"(Target: {target[0]}-{target[1]})" if target and target[1] else f"(Target: {target[0]}+)" if target else ""
            print(f"  {name}: {score} {target_str}")
    print("\nSentence Analysis:")
    for result in analysis_results_acad_complex['sentences']:
        print(f"Score: {result['score']:.3f} | Indices: {result['start']}-{result['end']} | Sentence: {result['sentence']}")
        print(f"  Syntactic Features: {result.get('syntactic_features', {})}")
        # print(f"  Coreference Features: {result.get('coreference_features', {})}") # Disabled

    print("\n--- Analysis (Coref) for Standard ---")
    analysis_results_std_coref = analyze_text_complexity(test_text_coref, target_audience="Standard")
    print(f"Overall Level: {analysis_results_std_coref['overall_level']['level']} ({analysis_results_std_coref['overall_level']['description']})")
    if analysis_results_std_coref.get('readability_scores'):
        print("Readability Scores:")
        for name, score in analysis_results_std_coref['readability_scores'].items():
            target = analysis_results_std_coref['target_readability_scores'].get(name)
            target_str = f"(Target: {target[0]}-{target[1]})" if target and target[1] else f"(Target: {target[0]}+)" if target else ""
            print(f"  {name}: {score} {target_str}")
    print("\nSentence Analysis:")
    for result in analysis_results_std_coref['sentences']:
        print(f"Score: {result['score']:.3f} | Indices: {result['start']}-{result['end']} | Sentence: {result['sentence']}")
        print(f"  Syntactic Features: {result.get('syntactic_features', {})}")
        # print(f"  Coreference Features: {result.get('coreference_features', {})}") # Disabled
