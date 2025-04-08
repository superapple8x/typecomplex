import nltk
import re

# Ensure NLTK data is available (punkt for tokenization)
try:
    nltk.data.find('tokenizers/punkt')
except nltk.downloader.DownloadError:
    print("NLTK 'punkt' tokenizer not found. Please run the download step again.")
    # Depending on the environment, you might raise an error or exit
    # For now, we'll let it potentially fail later if punkt is truly missing.
    pass

def calculate_complexity(sentence):
    """
    Calculates a basic complexity score for a single sentence.
    Considers sentence length and average word length.
    Returns a score (float) and a color category (string).
    """
    # Tokenize into words, removing punctuation
    words = [word.lower() for word in nltk.word_tokenize(sentence) if word.isalnum()]

    if not words:
        return 0.0, "gray" # Handle empty sentences or sentences with only punctuation

    sentence_length = len(words)
    total_word_length = sum(len(word) for word in words)
    average_word_length = total_word_length / sentence_length if sentence_length > 0 else 0

    # Simple scoring formula (can be refined)
    # Normalize factors slightly - adjust weights as needed
    length_factor = sentence_length / 30  # Assume ~30 words is a moderately long sentence
    word_len_factor = average_word_length / 7 # Assume ~7 chars is a moderately long average word

    # Combine factors (e.g., weighted average)
    score = (length_factor * 0.6) + (word_len_factor * 0.4)

    # Determine color based on score thresholds (adjust as needed)
    if score < 0.4:
        color = "green"
    elif score < 0.7:
        color = "yellow"
    elif score < 1.0:
        color = "orange"
    else:
        color = "red"

    # Clamp score to a reasonable range if needed, e.g., 0.0 to potentially > 1.0
    # For simplicity, we'll return the raw score for now.
    return round(score, 3), color


def get_overall_complexity_level(score):
    """Maps an overall score to a level, description, and color class."""
    if score < 0.3:
        return {"level": 1, "description": "Very Simple", "color_class": "bg-green-500"}
    elif score < 0.5:
        return {"level": 2, "description": "Simple", "color_class": "bg-lime-500"}
    elif score < 0.8:
        return {"level": 3, "description": "Moderate", "color_class": "bg-yellow-500"}
    elif score < 1.1:
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