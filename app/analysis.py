import nltk
import re
import math
from app.frequency import get_word_frequency # Import frequency function

# --- Constants for Scoring and Levels ---

# Weights for complexity factors
WEIGHT_SENTENCE_LENGTH = 0.4
WEIGHT_AVG_WORD_LENGTH = 0.3
WEIGHT_AVG_WORD_FREQUENCY = 0.3 # New weight for frequency

# Normalization denominators (adjust based on expected ranges)
NORMALIZATION_SENTENCE_LENGTH = 30.0
NORMALIZATION_AVG_WORD_LENGTH = 7.0
# Max expected frequency (adjust based on your corpus, e.g., 'the' might be very high)
# We use log frequency to compress the range. Add 1 to avoid log(0).
# Let's estimate a max frequency count for normalization purposes. This might need tuning.
# If 'the' has freq 1,000,000, log10(1,000,001) is ~6.
# If a rare word has freq 1, log10(2) is ~0.3.
# We want low frequency (high complexity) to result in a higher score component.
# So, we can use (max_log_freq - log_freq) / max_log_freq
MAX_LOG_FREQUENCY = 7.0 # Adjust this based on your data (log10 of max expected count + 1)

# Sentence complexity score thresholds for color coding
SCORE_THRESHOLD_GREEN = 0.4
SCORE_THRESHOLD_YELLOW = 0.7
SCORE_THRESHOLD_ORANGE = 1.0

# Overall complexity score thresholds for levels
OVERALL_SCORE_THRESHOLD_VERY_SIMPLE = 0.3
OVERALL_SCORE_THRESHOLD_SIMPLE = 0.5
OVERALL_SCORE_THRESHOLD_MODERATE = 0.8
OVERALL_SCORE_THRESHOLD_COMPLEX = 1.1

# --- NLTK Data Check ---
try:
    nltk.data.find('tokenizers/punkt')
except nltk.downloader.DownloadError:
    print("NLTK 'punkt' tokenizer not found. Please run the download step again.")
    # Depending on the environment, you might raise an error or exit
    # For now, we'll let it potentially fail later if punkt is truly missing.
    pass


def calculate_complexity(sentence):
    """
    Calculates a complexity score for a single sentence.
    Considers sentence length, average word length, and average word frequency.
    Returns a score (float) and a color category (string).
    """
    # Tokenize into words, removing punctuation
    words = [word.lower() for word in nltk.word_tokenize(sentence) if word.isalnum()]

    if not words:
        return 0.0, "gray" # Handle empty sentences or sentences with only punctuation

    sentence_length = len(words)
    total_word_length = sum(len(word) for word in words)
    average_word_length = total_word_length / sentence_length if sentence_length > 0 else 0

    # --- Calculate Frequency Score ---
    total_log_freq_score = 0
    words_with_freq = 0
    for word in words:
        freq = get_word_frequency(word)
        if freq > 0: # Only consider words found in the frequency list
            # Use log frequency to compress the scale. Add 1 to handle freq=0 (though we filter > 0)
            log_freq = math.log10(freq + 1)
            # Score: Higher score for lower frequency. Normalize against max expected log freq.
            # Ensure score is between 0 and 1.
            freq_score = max(0, (MAX_LOG_FREQUENCY - log_freq)) / MAX_LOG_FREQUENCY
            total_log_freq_score += freq_score
            words_with_freq += 1

    average_frequency_score = total_log_freq_score / words_with_freq if words_with_freq > 0 else 0

    # --- Normalize Factors ---
    length_factor = min(sentence_length / NORMALIZATION_SENTENCE_LENGTH, 1.5) # Cap factor to avoid extreme influence
    word_len_factor = min(average_word_length / NORMALIZATION_AVG_WORD_LENGTH, 1.5) # Cap factor
    # Frequency factor is already normalized between 0 and 1 (higher score = lower frequency = more complex)
    frequency_factor = average_frequency_score

    # --- Combine Factors using Weights ---
    score = (length_factor * WEIGHT_SENTENCE_LENGTH) + \
            (word_len_factor * WEIGHT_AVG_WORD_LENGTH) + \
            (frequency_factor * WEIGHT_AVG_WORD_FREQUENCY)

    # --- Determine Color based on Score Thresholds ---
    if score < SCORE_THRESHOLD_GREEN:
        color = "green"
    elif score < SCORE_THRESHOLD_YELLOW:
        color = "yellow"
    elif score < SCORE_THRESHOLD_ORANGE:
        color = "orange"
    else:
        color = "red"

    # Clamp score to a reasonable range if needed, e.g., 0.0 to potentially > 1.0
    # For simplicity, we'll return the raw score for now.
    return round(score, 3), color


def get_overall_complexity_level(score):
    """Maps an overall score to a level, description, and color class."""
    if score < OVERALL_SCORE_THRESHOLD_VERY_SIMPLE:
        return {"level": 1, "description": "Very Simple", "color_class": "bg-green-500"}
    elif score < OVERALL_SCORE_THRESHOLD_SIMPLE:
        return {"level": 2, "description": "Simple", "color_class": "bg-lime-500"}
    elif score < OVERALL_SCORE_THRESHOLD_MODERATE:
        return {"level": 3, "description": "Moderate", "color_class": "bg-yellow-500"}
    elif score < OVERALL_SCORE_THRESHOLD_COMPLEX:
        return {"level": 4, "description": "Complex", "color_class": "bg-orange-500"}
    else:
        return {"level": 5, "description": "Very Complex", "color_class": "bg-red-500"}


def analyze_text_complexity(text):
    """
    Analyzes the complexity of each sentence in the input text.
    Uses nltk for sentence segmentation.
    Returns a dictionary containing:
        - 'results': A list of dictionaries (sentence, score, color).
        - 'overall_level': A dictionary (level, description, color_class).
    """
    if not text or not text.strip():
        # Return default structure for empty/whitespace-only text
        return {
            "results": [],
            "overall_level": {"level": 0, "description": "Enter text to analyze", "color_class": "bg-gray-600"}
        }

    # Split text into sentences using NLTK
    sentences = nltk.sent_tokenize(text)

    results = []
    for sentence in sentences:
        # Keep the original sentence for accurate frontend mapping
        original_sentence = sentence
        if not original_sentence.strip(): # Check if sentence is just whitespace
             continue

        # Calculate complexity based on a cleaned version for metrics
        cleaned_for_calc = re.sub(r'\s+', ' ', original_sentence).strip()
        score, color = calculate_complexity(cleaned_for_calc)

        # Return the ORIGINAL sentence string
        results.append({
            "sentence": original_sentence,
            "score": score,
            "color": color
        })

    # Calculate overall score (average of sentence scores)
    total_score = sum(r['score'] for r in results)
    num_sentences = len(results)
    overall_score = round(total_score / num_sentences, 3) if num_sentences > 0 else 0.0

    # Get the complexity level details based on the average score
    overall_level_details = get_overall_complexity_level(overall_score)

    return {
        "results": results,
        "overall_level": overall_level_details
    }

# Example usage (for testing purposes)
if __name__ == '__main__':
    test_text = """
    This is a simple sentence. It should be green.
    This sentence, however, is potentially a little bit longer and might perhaps score slightly higher, maybe yellow.
    Subsequently, utilizing considerably more sophisticated vocabulary and constructing elongated phrasal structures inevitably escalates the calculated complexity assessment towards the orange or even red spectrum.
    What about this one?
    """
    analysis_results = analyze_text_complexity(test_text)
    print(f"Overall Level: {analysis_results['overall_level']['level']} ({analysis_results['overall_level']['description']})")
    for result in analysis_results['results']:
        print(f"[{result['color'].upper()}] Score: {result['score']:.3f} | Sentence: {result['sentence']}")
