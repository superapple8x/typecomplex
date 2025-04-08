from nltk.corpus import wordnet
from app.frequency import get_word_frequency
import math

# Ensure NLTK WordNet data is available
try:
    wordnet.ensure_loaded()
except nltk.downloader.DownloadError:
    print("NLTK 'wordnet' data not found. Please run the download step again.")
    # Handle error appropriately, maybe raise or return empty list later
    pass

def _rank_synonyms(synonyms_with_freq):
    """
    Ranks synonyms based on frequency into 5 bins (1=most common, 5=least common).
    Input: list of tuples [(synonym, frequency)]
    Output: list of dictionaries [{"word": synonym, "rank": rank}]
    """
    if not synonyms_with_freq:
        return []

    # Sort synonyms by frequency in descending order (most frequent first)
    sorted_synonyms = sorted(synonyms_with_freq, key=lambda item: item[1], reverse=True)

    num_synonyms = len(sorted_synonyms)
    ranked_list = []

    # Determine bin size (handle cases with fewer than 5 synonyms)
    # We aim for 5 bins.
    for i, (synonym, freq) in enumerate(sorted_synonyms):
        # Calculate rank based on position in the sorted list
        # Simple approach: divide into 5 quantiles
        quantile = (i / num_synonyms) * 5
        rank = math.ceil(quantile) # Map 0.0-0.99 to 1, 1.0-1.99 to 2, etc.
        # Ensure rank is at least 1 and at most 5
        rank = max(1, min(5, rank))

        ranked_list.append({"word": synonym, "rank": rank})

    # Re-sort alphabetically for consistent display, maybe? Or keep frequency sort?
    # Let's keep frequency sort for now, as it might be more useful.
    # ranked_list.sort(key=lambda item: item['word'])
    return ranked_list


def get_ranked_synonyms(word):
    """
    Finds synonyms for a word, retrieves their frequencies, and ranks them (1-5).
    Returns a list of ranked synonym dictionaries.
    """
    synonyms_found = set() # Use a set to avoid duplicates from different synsets

    # Look for synsets (sets of synonyms) containing the word
    for syn in wordnet.synsets(word):
        # Get lemmas (word forms) from the synset
        for lemma in syn.lemmas():
            synonym = lemma.name().lower().replace('_', ' ') # Get the word, lowercase, replace underscores
            # Add to set if it's not the original word and is a single word (optional filter)
            if synonym != word.lower() and ' ' not in synonym and synonym.isalpha():
                 synonyms_found.add(synonym)

    if not synonyms_found:
        return []

    # Get frequencies for found synonyms
    synonyms_with_freq = []
    for syn in synonyms_found:
        freq = get_word_frequency(syn)
        # Only include synonyms found in our frequency list
        if freq > 0:
            synonyms_with_freq.append((syn, freq))

    # Rank the synonyms based on frequency
    ranked_synonyms = _rank_synonyms(synonyms_with_freq)

    return ranked_synonyms

# Example usage (for testing purposes)
if __name__ == '__main__':
    test_word = "good"
    ranked = get_ranked_synonyms(test_word)
    print(f"Ranked synonyms for '{test_word}':")
    if ranked:
        # Sort by rank for display
        ranked.sort(key=lambda x: (x['rank'], x['word']))
        for item in ranked:
            print(f"  Rank {item['rank']}: {item['word']}")
    else:
        print("  No synonyms found or none present in frequency list.")

    test_word_complex = "ameliorate"
    ranked_complex = get_ranked_synonyms(test_word_complex)
    print(f"\nRanked synonyms for '{test_word_complex}':")
    if ranked_complex:
        ranked_complex.sort(key=lambda x: (x['rank'], x['word']))
        for item in ranked_complex:
             print(f"  Rank {item['rank']}: {item['word']}")
    else:
        print("  No synonyms found or none present in frequency list.")