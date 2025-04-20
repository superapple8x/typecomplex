import nltk
import re
import math
import textstat # Import textstat
from app.frequency import get_word_frequency # Import frequency function
import torch
import numpy as np
from transformers import AutoTokenizer, AutoModel
import spacy # Import spacy
import logging # Import logging
import hashlib # Import hashlib
from app import cache # Import the initialized cache object
from app import task_manager # Import task manager

# --- Load Transformer Model ---
# Load model & tokenizer once globally
# Using a smaller BERT variant might be faster if performance is critical
MODEL_NAME = 'bert-base-uncased'
try:
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModel.from_pretrained(MODEL_NAME)
    # Ensure model is in evaluation mode
    model.eval()
    # Move model to GPU if available
    if torch.cuda.is_available():
        model.to('cuda')
    print(f"Successfully loaded transformer model '{MODEL_NAME}'.")
except Exception as e:
    print(f"ERROR loading transformer model '{MODEL_NAME}': {e}")
    # Handle error: maybe fall back to statistical analysis only?
    tokenizer = None
    model = None


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
        "weights": {
            "sentence_length": 0.25, # Reduced
            "avg_word_length": 0.20, # Reduced
            "avg_word_frequency": 0.20, # Reduced
            "embedding_complexity": 0.15, # Reduced
            "syntactic_complexity": 0.15, # New factor (avg of 4 sub-features)
            "coreference_complexity": 0.05, # New factor
        },
        "normalization": {
            "sentence_length": 30.0,
            "avg_word_length": 7.0,
            "max_log_frequency": 7.0,
            "max_parse_tree_depth": 15.0, # Estimated max depth
            "max_num_clauses": 5.0, # Estimated max clauses
            "max_avg_dependency_length": 10.0, # Estimated max avg dep length
            "max_coreferent_mentions": 5.0, # Estimated max mentions referring back
        },
        "thresholds": { # Overall complexity level thresholds (may need adjustment)
            "very_simple": 0.3,
            "simple": 0.5,
            "moderate": 0.8,
            "complex": 1.1,
        },
        "target_readability": {
            "flesch_kincaid_grade": None, # No specific target for standard
            "gunning_fog": None,
        }
    },
    "General Public": {
        "weights": { # Emphasize length more, syntax/coref less
            "sentence_length": 0.30, # Reduced
            "avg_word_length": 0.20, # Reduced
            "avg_word_frequency": 0.15, # Reduced
            "embedding_complexity": 0.15,
            "syntactic_complexity": 0.12, # Lower weight
            "coreference_complexity": 0.08, # Slightly higher weight than standard? Or lower? Let's try lower.
        },
        "normalization": { # Lower tolerance for length, syntax
            "sentence_length": 25.0,
            "avg_word_length": 7.0,
            "max_log_frequency": 7.0,
            "max_parse_tree_depth": 12.0, # Lower tolerance
            "max_num_clauses": 4.0, # Lower tolerance
            "max_avg_dependency_length": 8.0, # Lower tolerance
            "max_coreferent_mentions": 4.0, # Lower tolerance
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
        "weights": { # Emphasize word choice, syntax, coref more
            "sentence_length": 0.15, # Reduced
            "avg_word_length": 0.25, # Reduced
            "avg_word_frequency": 0.20, # Reduced
            "embedding_complexity": 0.15,
            "syntactic_complexity": 0.20, # Higher weight
            "coreference_complexity": 0.05, # Standard weight
        },
        "normalization": { # Higher tolerance
            "sentence_length": 35.0,
            "avg_word_length": 8.0,
            "max_log_frequency": 7.0,
            "max_parse_tree_depth": 20.0, # Higher tolerance
            "max_num_clauses": 7.0, # Higher tolerance
            "max_avg_dependency_length": 12.0, # Higher tolerance
            "max_coreferent_mentions": 6.0, # Higher tolerance
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
    total_weight = sum(profile_data['weights'].values())
    if not math.isclose(total_weight, 1.0):
        print(f"WARNING: Weights for profile '{profile_name}' do not sum to 1.0 (sum={total_weight}). Normalizing...")
        # Basic normalization (might need refinement depending on intent)
        factor = 1.0 / total_weight
        for key in profile_data['weights']:
            profile_data['weights'][key] *= factor


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


def _get_contextual_embedding_complexity(sentence, words):
    """
    Calculates complexity based on contextual word embeddings using transformers.
    Higher score means words are used in more varied/distant contexts within the sentence.
    Returns a score between 0 and 1 (or None if model failed).
    """
    if not model or not tokenizer:
        print("WARN: Transformer model not available for embedding complexity.")
        return None # Indicate failure

    # Prepare input for the transformer model
    inputs = tokenizer(sentence, return_tensors="pt", truncation=True, padding=True)
    # Move inputs to GPU if model is on GPU
    if torch.cuda.is_available():
        inputs = {k: v.to('cuda') for k, v in inputs.items()}

    # Get model outputs (hidden states)
    with torch.no_grad():
        outputs = model(**inputs, output_hidden_states=True)

    # Use the last hidden state (embeddings for each token)
    # Shape: (batch_size, sequence_length, hidden_size)
    last_hidden_states = outputs.hidden_states[-1].squeeze(0) # Remove batch dim

    # --- Map token embeddings back to original words ---
    # This is complex due to subword tokenization (e.g., "running" -> "run", "##ning")
    # We'll average embeddings for subwords belonging to the same original word.
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
            # Start of a new word - find the corresponding word in our 'words' list
            # This simple alignment might break with complex punctuation/tokenization mismatches
            current_word_index += 1
            token_to_word_mapping.append(current_word_index)

    # Aggregate embeddings for each word
    word_embeddings = {}
    token_counts = {}
    for i, word_idx in enumerate(token_to_word_mapping):
        if word_idx != -1 and word_idx < len(words): # Ensure index is valid
            embedding = last_hidden_states[i].cpu().numpy() # Move to CPU, convert to numpy
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
        return 0.0 # No embeddings, no complexity from this factor

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
    print(f"DEBUG: Calculated embedding complexity factor: {embedding_complexity_factor:.4f} for sentence: '{sentence[:50]}...'")

    return embedding_complexity_factor


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

def _get_coreference_features(spacy_sentence, doc):
    """
    Extracts coreference features for a spaCy sentence.
    Counts the number of mentions in the sentence that are part of a coreference chain
    and are not the representative mention of the cluster.
    Returns the count of coreferent mentions.
    """
    # Check if coreference resolution component is available and successful
    # Note: 'en_core_web_sm' might not include coref. Need a larger model like 'en_core_web_trf'
    # or a dedicated coref library like 'neuralcoref' integrated with spaCy.
    # For now, we'll assume it might be available via extensions or larger models.
    # A robust check would involve checking `nlp.pipe_names` or specific model capabilities.
    # Placeholder check:
    if not hasattr(doc._, 'coref_clusters'):
        # print("WARN: Coreference clusters not found. Ensure a model with coref capabilities is loaded (e.g., en_core_web_trf or using neuralcoref).")
        return {"coreferent_mentions_count": 0}

    coreferent_mentions_count = 0
    # Iterate through all coreference clusters in the document
    for cluster in doc._.coref_clusters:
        # Iterate through mentions in the current cluster
        for mention in cluster.mentions:
            # Check if the mention falls within the current sentence's span
            if mention.start >= spacy_sentence.start and mention.end <= spacy_sentence.end:
                # Check if this mention is NOT the representative mention of the cluster
                if mention != cluster.main:
                    coreferent_mentions_count += 1

    return {"coreferent_mentions_count": coreferent_mentions_count}


def calculate_complexity(spacy_sentence, doc, profile, mode='full', analysis_id=None): # Added analysis_id
    """
    Calculates a complexity score for a single sentence based on the provided profile.
    Considers sentence length, average word length, average word frequency,
    contextual embedding complexity, syntactic features, and coreference features.
    Calculation of expensive features is conditional based on the 'mode' parameter.
    Returns a score (float).
    """
    # Use profile-specific constants
    weights = profile['weights']
    norm = profile['normalization']

    # --- Basic Tokenization (for statistical measures) ---
    # Use spaCy tokens for consistency
    words_for_stats = [token.text.lower() for token in spacy_sentence if token.is_alpha]

    if not words_for_stats:
        return 0.0 # Handle empty sentences

    # --- Statistical Factors (Always calculated) ---
    sentence_length = len(words_for_stats)
    total_word_length = sum(len(word) for word in words_for_stats)
    average_word_length = total_word_length / sentence_length if sentence_length > 0 else 0

    total_log_freq_score = 0
    words_with_freq = 0
    max_log_freq = norm['max_log_frequency']
    for word in words_for_stats:
        freq = get_word_frequency(word)
        if freq > 0:
            log_freq = math.log10(freq + 1)
            freq_score = max(0, (max_log_freq - log_freq)) / max_log_freq
            total_log_freq_score += freq_score
            words_with_freq += 1
    average_frequency_score = total_log_freq_score / words_with_freq if words_with_freq > 0 else 0

    length_factor = min(sentence_length / norm['sentence_length'], 1.5)
    word_len_factor = min(average_word_length / norm['avg_word_length'], 1.5)
    frequency_factor = average_frequency_score # Already 0-1

    # --- Conditional Expensive Factors ---
    embedding_factor = 0.0
    syntactic_factor = 0.0
    coreferent_mentions_factor = 0.0
    syntactic_features = {} # Initialize
    coreference_features = {} # Initialize


    if mode == 'full':
        # --- Check for cancellation before expensive embedding calculation ---
        if analysis_id and task_manager.is_cancelled(analysis_id):
            logging.info(f"Task {analysis_id}: Cancelled before embedding calculation for sentence: '{spacy_sentence.text[:50]}...'")
            return 0.0 # Return neutral score if cancelled here

        # --- Contextual Embedding Factor ---
        embedding_factor_raw = _get_contextual_embedding_complexity(spacy_sentence.text, words_for_stats)
        embedding_factor = embedding_factor_raw if embedding_factor_raw is not None else 0.0

        # --- Syntactic Features ---
        syntactic_features = _get_syntactic_features(spacy_sentence)
        parse_tree_depth_factor = min(syntactic_features.get('parse_tree_depth', 0) / norm['max_parse_tree_depth'], 1.5) # Use .get for safety
        num_clauses_factor = min(syntactic_features.get('num_clauses', 0) / norm['max_num_clauses'], 1.5) # Use .get for safety
        avg_dep_length_factor = min(syntactic_features.get('avg_dependency_length', 0.0) / norm['max_avg_dependency_length'], 1.5) # Use .get for safety
        passive_voice_factor = syntactic_features.get('has_passive_voice', 0) # Binary (0 or 1), Use .get for safety

        # Combine syntactic factors (simple average for now, could be weighted)
        syntactic_weight_sum = weights.get('syntactic_complexity', 0)
        if syntactic_weight_sum > 0:
             syntactic_factor = (parse_tree_depth_factor + num_clauses_factor + avg_dep_length_factor + passive_voice_factor) / 4.0
             syntactic_factor = max(0.0, min(1.0, syntactic_factor))
        else:
             syntactic_factor = 0.0

        print(f"DEBUG: Full Analysis - Syntactic Features: {syntactic_features}")
        print(f"DEBUG: Full Analysis - Coreference Features: {coreference_features}")


    # --- Combine Factors using Weights ---
    # Use .get() for weights to avoid KeyError if a profile is missing a new weight
    # Ensure factors are used based on the mode - factors are 0.0 if not calculated in 'fast' mode
    score = (length_factor * weights.get('sentence_length', 0)) + \
            (word_len_factor * weights.get('avg_word_length', 0)) + \
            (frequency_factor * weights.get('avg_word_frequency', 0)) + \
            (embedding_factor * weights.get('embedding_complexity', 0)) + \
            (syntactic_factor * weights.get('syntactic_complexity', 0)) + \
            (coreferent_mentions_factor * weights.get('coreference_complexity', 0))

    # The max possible score will need re-evaluation with new factors.
    # The thresholds might need adjustment later based on observed score ranges.

    print(f"DEBUG: Calculated Score ({mode} mode): {score:.3f} for sentence: '{spacy_sentence.text[:50]}...'") # Updated print to use spacy_sentence.text


    return round(score, 3)

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


def analyze_single_spacy_sentence(spacy_sentence, doc, profile, sentence_index, target_audience_name, mode='full', analysis_id=None): # Added target_audience_name
    """
    Analyzes the complexity of a single spaCy sentence based on the provided profile.
    Checks cache before calculation. Stores result in cache.
    Requires the full spaCy document for coreference resolution.
    Accepts an 'analysis_id' for cancellation checks.
    Returns a dictionary containing:
        - 'sentence': The original sentence text.
        - 'score': The complexity score (float).
        - 'start': The start character index in the original text.
        - 'end': The end character index in the original text.
        - 'index': The index of the sentence in the document.
        - 'syntactic_features': Dictionary of syntactic features (may be empty in 'fast' mode).
        - 'coreference_features': Dictionary of coreference features (may be empty in 'fast' mode).
        - 'mode': The analysis mode used ('fast' or 'full').
    """
    original_sentence = spacy_sentence.text
    start = spacy_sentence.start_char
    end = spacy_sentence.end_char

    # --- Cache Check ---
    # Use sentence text + profile name + mode for a unique key
    cache_key_string = f"{original_sentence.strip()}|{target_audience_name}|{mode}"
    cache_key = hashlib.sha1(cache_key_string.encode('utf-8')).hexdigest()

    cached_result = cache.get(cache_key)
    if cached_result:
        logging.debug(f"Cache HIT for sentence index {sentence_index} (Key: {cache_key[:8]}...)")
        # Ensure the cached result has the correct index and mode, just in case
        cached_result['index'] = sentence_index
        cached_result['mode'] = mode
        return cached_result
    else:
        logging.debug(f"Cache MISS for sentence index {sentence_index} (Key: {cache_key[:8]}...)")
    # --- End Cache Check ---

    if not original_sentence.strip():
        # Return a basic result even for empty sentences if needed for sequential flow structure
         result = { # Define result dict
            "sentence": original_sentence,
            "score": 0.0,
            "start": start,
            "end": end,
            "index": sentence_index,
            "syntactic_features": {},
            "coreference_features": {},
            "mode": mode
        }
         # --- Cache Set (even for empty/basic) ---
         cache.set(cache_key, result)
         # --- End Cache Set ---
         return result


    # Calculate complexity using the spaCy sentence object, the full doc, and the mode
    score = calculate_complexity(spacy_sentence, doc, profile, mode=mode, analysis_id=analysis_id) # Pass analysis_id

    # Extract and include the new features (will be empty in 'fast' mode as handled in calculate_complexity)
    # We still include the keys for consistency, even if values are empty dicts
    syntactic_features = {} # Initialize
    coreference_features = {} # Initialize

    if mode == 'full':
         # Re-extract features here if needed for the return dictionary,
         # although calculate_complexity already did this.
         # Let's rely on calculate_complexity to return the features if needed,
         # or modify calculate_complexity to return score AND features.
         # For now, let's just return empty features in fast mode.
         # A better approach might be to have calculate_complexity return a dict of factors/features.

         # Let's modify calculate_complexity to return a dict of {score, features}
         # This requires a larger refactor. Sticking to current plan: features are empty in fast mode.
         pass # Features are handled conditionally in calculate_complexity now


    result = { # Define result dict
        "sentence": original_sentence,
        "score": score, # Score is calculated based on mode in calculate_complexity
        "start": start,
        "end": end,
        "index": sentence_index,
        "syntactic_features": {}, # Features are not returned separately in this structure
        "coreference_features": {}, # Features are not returned separately in this structure
        "mode": mode
    }

    # --- Cache Set ---
    cache.set(cache_key, result)
    logging.debug(f"Stored result in cache for sentence index {sentence_index} (Key: {cache_key[:8]}...)")
    # --- End Cache Set ---

    return result


def analyze_text_complexity(text, target_audience="Standard", mode='full', analysis_id=None): # Added analysis_id
    """
    Analyzes the complexity of each sentence in the input text based on target audience.
    Uses spaCy for sentence segmentation, parsing, and coreference resolution.
    Accepts an 'analysis_id' for cancellation checks.
    This function is now primarily for calculating overall scores and readability
    after all sentences have been analyzed (e.g., in the non-sequential flow).
    It can also be used to get all sentence results at once.

    Returns a dictionary containing:
        - 'results': A list of dictionaries (sentence, score, start, end, syntactic_features, coreference_features).
        - 'overall_level': A dictionary (level, description, color_class).
        - 'readability_scores': Calculated scores.
        - 'target_readability_scores': Target scores for the audience.
    """
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

    if not text or not text.strip() or not nlp: # Check if spaCy model loaded
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
        doc = nlp(text)
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
    # Iterate through sentences and analyze each one using the new function
    if doc.has_annotation("SENT_START"):
        for i, spacy_sentence in enumerate(doc.sents):
            # --- Check for cancellation before processing each sentence ---
            if analysis_id and task_manager.is_cancelled(analysis_id):
                logging.info(f"Analysis (ID: {analysis_id}) cancelled during sentence loop at index {i}.")
                cancelled_mid_loop = True
                break # Exit the loop

            sentence_result = analyze_single_spacy_sentence(
                spacy_sentence,
                doc,
                profile,
                i,
                target_audience_name=target_audience, # Pass target_audience name
                mode=mode,
                analysis_id=analysis_id # Pass ID
            )
            if sentence_result:
                results.append(sentence_result)

    # --- Handle Cancellation Mid-Loop ---
    if cancelled_mid_loop:
        # Return partial results but indicate cancellation in overall level
        logging.info(f"Analysis (ID: {analysis_id}) returning partial results due to cancellation.")
        return {
            "results": results, # Return results processed so far
            "overall_level": {"level": 0, "description": "Analysis cancelled", "color_class": "bg-gray-600"},
            "readability_scores": {"flesch_kincaid_grade": None, "gunning_fog": None, "smog_index": None}, # Or calculate based on partial text? For now, None.
            "target_readability_scores": profile['target_readability']
        }

    # Calculate overall score (average of sentence scores) only if results exist and not cancelled
    # This block should be at the same indentation level as the 'if cancelled_mid_loop:' block
    if results:
        total_score = sum(r['score'] for r in results)
        num_sentences = len(results)
        overall_score = round(total_score / num_sentences, 3) if num_sentences > 0 else 0.0
        overall_level_details = get_overall_complexity_level(overall_score, profile)
    else: # Handle case where text had no valid sentences after processing
         overall_score = 0.0
         overall_level_details = {"level": 0, "description": "No sentences found", "color_class": "bg-gray-600"}

    # --- Calculate Standard Readability Scores ---
    try:
        flesch_kincaid_grade = round(textstat.flesch_kincaid_grade(text), 1)
        gunning_fog = round(textstat.gunning_fog(text), 1)
        smog_index = round(textstat.smog_index(text), 1)
    except Exception as e:
        print(f"Error calculating textstat scores: {e}")
        flesch_kincaid_grade = None
        gunning_fog = None
        smog_index = None

    return {
        "results": results,
        "overall_level": overall_level_details,
        "readability_scores": {
            "flesch_kincaid_grade": flesch_kincaid_grade,
            "gunning_fog": gunning_fog,
            "smog_index": smog_index
        },
        "target_readability_scores": profile['target_readability']
    }

# Example usage (for testing purposes)
if __name__ == '__main__':
    # Add neuralcoref if available
    # try:
    #     import neuralcoref
    #     if nlp and 'neuralcoref' not in nlp.pipe_names:
    #          coref = neuralcoref.NeuralCoref(nlp.vocab)
    #          nlp.add_pipe(coref, name='neuralcoref')
    # except ImportError:
    #     print("INFO: neuralcoref not installed, coreference features will be zero.")
    #     pass

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
    for result in analysis_results_gp_simple['results']:
        print(f"Score: {result['score']:.3f} | Indices: {result['start']}-{result['end']} | Sentence: {result['sentence']}")
        print(f"  Syntactic Features: {result.get('syntactic_features', {})}")
        print(f"  Coreference Features: {result.get('coreference_features', {})}")


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
    for result in analysis_results_acad_complex['results']:
        print(f"Score: {result['score']:.3f} | Indices: {result['start']}-{result['end']} | Sentence: {result['sentence']}")
        print(f"  Syntactic Features: {result.get('syntactic_features', {})}")
        print(f"  Coreference Features: {result.get('coreference_features', {})}")

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
    for result in analysis_results_std_coref['results']:
        print(f"Score: {result['score']:.3f} | Indices: {result['start']}-{result['end']} | Sentence: {result['sentence']}")
        print(f"  Syntactic Features: {result.get('syntactic_features', {})}")
        print(f"  Coreference Features: {result.get('coreference_features', {})}")
