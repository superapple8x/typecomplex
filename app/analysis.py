import nltk
import re
import math
import textstat # Import textstat
from app.frequency import get_word_frequency # Import frequency function
import torch
import numpy as np
from transformers import AutoTokenizer, AutoModel

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


# --- Audience Profiles ---
# Define weights, normalization constants, thresholds, and target scores per audience.
# Added 'embedding_complexity' weight and renormalized others
AUDIENCE_PROFILES = {
    "Standard": {
        "weights": {
            "sentence_length": 0.32, # 0.4 * 0.8
            "avg_word_length": 0.24, # 0.3 * 0.8
            "avg_word_frequency": 0.24, # 0.3 * 0.8
            "embedding_complexity": 0.2,
        },
        "normalization": {
            "sentence_length": 30.0,
            "avg_word_length": 7.0,
            "max_log_frequency": 7.0,
        },
        "thresholds": { # Overall complexity level thresholds
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
        "weights": { # Emphasize length more, frequency less
            "sentence_length": 0.40, # 0.5 * 0.8
            "avg_word_length": 0.24, # 0.3 * 0.8
            "avg_word_frequency": 0.16, # 0.2 * 0.8
            "embedding_complexity": 0.2,
        },
        "normalization": { # Lower tolerance for length
            "sentence_length": 25.0,
            "avg_word_length": 7.0,
            "max_log_frequency": 7.0,
        },
        "thresholds": { # Lower thresholds -> easier to be complex
            "very_simple": 0.25,
            "simple": 0.45,
            "moderate": 0.7, # Lowered from standard 0.8
            "complex": 1.0, # Lowered from standard 1.1
        },
        "target_readability": {
            "flesch_kincaid_grade": (8.0, 10.9),
            "gunning_fog": (10.0, 13.0),
        }
    },
    "Academic / Technical": {
        "weights": { # Emphasize word length/frequency more, length less
            "sentence_length": 0.24, # 0.3 * 0.8
            "avg_word_length": 0.32, # 0.4 * 0.8
            "avg_word_frequency": 0.24, # 0.3 * 0.8
            "embedding_complexity": 0.2,
        },
        "normalization": { # Higher tolerance
            "sentence_length": 35.0,
            "avg_word_length": 8.0,
            "max_log_frequency": 7.0,
        },
        "thresholds": { # Higher thresholds -> harder to be complex
            "very_simple": 0.35,
            "simple": 0.6,
            "moderate": 0.9, # Higher than standard 0.8
            "complex": 1.2, # Higher than standard 1.1
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


def calculate_complexity(sentence, profile):
    """
    Calculates a complexity score for a single sentence based on the provided profile.
    Considers sentence length, average word length, average word frequency,
    and contextual embedding complexity.
    Returns a score (float).
    """
    # Use profile-specific constants
    weights = profile['weights']
    norm = profile['normalization']

    # --- Basic Tokenization (for statistical measures) ---
    # Keep this simple tokenization for length/word stats as before
    words_for_stats = [word.lower() for word in nltk.word_tokenize(sentence) if word.isalnum()]

    if not words_for_stats:
        return 0.0 # Handle empty sentences

    # --- Statistical Factors ---
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

    # --- Contextual Embedding Factor ---
    # Pass the original sentence and the stat words list (for alignment reference)
    embedding_factor_raw = _get_contextual_embedding_complexity(sentence, words_for_stats)

    # If embedding calculation failed, use 0 for its contribution
    embedding_factor = embedding_factor_raw if embedding_factor_raw is not None else 0.0

    # --- Combine Factors using Weights ---
    score = (length_factor * weights['sentence_length']) + \
            (word_len_factor * weights['avg_word_length']) + \
            (frequency_factor * weights['avg_word_frequency']) + \
            (embedding_factor * weights['embedding_complexity']) # Add new factor

    # Normalize the final score? The max possible score is now sum of (max_factor * weight)
    # Max statistical score part = (1.5 * w_len) + (1.5 * w_word) + (1.0 * w_freq)
    # Max embedding score part = (1.0 * w_emb)
    # For Standard: (1.5*0.32)+(1.5*0.24)+(1.0*0.24)+(1.0*0.2) = 0.48+0.36+0.24+0.2 = 1.28
    # The thresholds might need adjustment later based on observed score ranges.

    return round(score, 3)

# Removed get_sentence_level function as level is now determined on frontend

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


def analyze_text_complexity(text, target_audience="Standard"):
    """
    Analyzes the complexity of each sentence in the input text based on target audience.
    Uses nltk for sentence segmentation using span_tokenize.
    Returns a dictionary containing:
        - 'results': A list of dictionaries (sentence, score, start, end).
        - 'overall_level': A dictionary (level, description, color_class).
        - 'readability_scores': Calculated scores.
        - 'target_readability_scores': Target scores for the audience.
    """
    # Select the profile based on target_audience, default to Standard
    profile = AUDIENCE_PROFILES.get(target_audience, AUDIENCE_PROFILES["Standard"])
    if not text or not text.strip() or not sentence_tokenizer:
        # Return default structure for empty/whitespace-only text
        return {
            "results": [],
            "overall_level": {"level": 0, "description": "Enter text to analyze", "color_class": "bg-gray-600"},
            "readability_scores": {"flesch_kincaid_grade": None, "gunning_fog": None, "smog_index": None},
            "target_readability_scores": profile['target_readability'] # Return target even if no text
        }

    # Use span_tokenize to get sentences with start/end indices
    sentence_spans = sentence_tokenizer.span_tokenize(text)

    results = []
    # Use enumerate to get index along with spans
    for i, (start, end) in enumerate(sentence_spans):
        original_sentence = text[start:end] # Extract sentence using spans
        if not original_sentence.strip(): # Check if sentence is just whitespace
             continue

        # Calculate complexity based on a cleaned version for metrics
        cleaned_for_calc = re.sub(r'\s+', ' ', original_sentence).strip()
        # Pass the selected profile to calculate_complexity
        score = calculate_complexity(cleaned_for_calc, profile)
        # level = get_sentence_level(score) # Level now determined on frontend

        # Return the ORIGINAL sentence string, score, and indices
        results.append({
            "sentence": original_sentence, # Keep for potential debugging/display
            "score": score,
            # "color": color, # Color now determined on frontend
            # "level": level, # Level now determined on frontend
            "start": start, # Add start index
            "end": end,     # Add end index
            "index": i      # Add sentence index
        })

    # Calculate overall score (average of sentence scores)
    total_score = sum(r['score'] for r in results)
    num_sentences = len(results)
    overall_score = round(total_score / num_sentences, 3) if num_sentences > 0 else 0.0

    # Get the complexity level details based on the average score
    # Pass the selected profile to get_overall_complexity_level
    overall_level_details = get_overall_complexity_level(overall_score, profile)

    # --- Calculate Standard Readability Scores ---
    # (Readability calculation remains the same, independent of profile for now)
    try:
        flesch_kincaid_grade = round(textstat.flesch_kincaid_grade(text), 1)
        gunning_fog = round(textstat.gunning_fog(text), 1)
        smog_index = round(textstat.smog_index(text), 1)
        # Add more scores if needed, e.g., textstat.flesch_reading_ease(text)
    except Exception as e:
        # Handle potential errors in textstat calculation (e.g., text too short)
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
            # Add other scores here if calculated
        },
        "target_readability_scores": profile['target_readability'] # Include target scores
    }

# Example usage (for testing purposes)
if __name__ == '__main__':
    test_text = """
    This is a simple sentence. It should be green.
    This sentence, however, is potentially a little bit longer and might perhaps score slightly higher, maybe yellow.
    Subsequently, utilizing considerably more sophisticated vocabulary and constructing elongated phrasal structures inevitably escalates the calculated complexity assessment towards the orange or even red spectrum.
    What about this one?
    """
    print("--- Analysis for General Public ---")
    analysis_results_gp = analyze_text_complexity(test_text, target_audience="General Public")
    print(f"Overall Level: {analysis_results_gp['overall_level']['level']} ({analysis_results_gp['overall_level']['description']})")
    if analysis_results_gp.get('readability_scores'):
        print("Readability Scores:")
        for name, score in analysis_results_gp['readability_scores'].items():
            target = analysis_results_gp['target_readability_scores'].get(name)
            target_str = f"(Target: {target[0]}-{target[1]})" if target and target[1] else f"(Target: {target[0]}+)" if target else ""
            print(f"  {name}: {score} {target_str}")
    print("\nSentence Analysis:")
    for result in analysis_results_gp['results']:
        print(f"Score: {result['score']:.3f} | Indices: {result['start']}-{result['end']} | Sentence: {result['sentence']}")

    print("\n--- Analysis for Academic / Technical ---")
    analysis_results_acad = analyze_text_complexity(test_text, target_audience="Academic / Technical")
    print(f"Overall Level: {analysis_results_acad['overall_level']['level']} ({analysis_results_acad['overall_level']['description']})")
    if analysis_results_acad.get('readability_scores'):
        print("Readability Scores:")
        for name, score in analysis_results_acad['readability_scores'].items():
            target = analysis_results_acad['target_readability_scores'].get(name)
            target_str = f"(Target: {target[0]}-{target[1]})" if target and target[1] else f"(Target: {target[0]}+)" if target else ""
            print(f"  {name}: {score} {target_str}")
    print("\nSentence Analysis:")
    for result in analysis_results_acad['results']:
        print(f"Score: {result['score']:.3f} | Indices: {result['start']}-{result['end']} | Sentence: {result['sentence']}")
