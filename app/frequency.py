import pandas as pd
import os

# Global variable to hold the frequency data Series
# We use a Series (word as index, count as value) for fast lookups
_frequency_data = None
# Define the path relative to the app's root directory
_DATA_FILE_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'ngram_freq.csv')

def load_frequency_data(filepath=_DATA_FILE_PATH):
    """
    Loads the word frequency data from the specified CSV file into a pandas Series.
    Sets the 'word' column as the index for efficient lookups.
    """
    global _frequency_data
    try:
        print(f"Loading frequency data from: {filepath}")
        # Read the CSV file
        df = pd.read_csv(filepath)

        # Ensure column names are correct (adjust if necessary based on actual file)
        if 'word' not in df.columns or 'count' not in df.columns:
            raise ValueError("CSV must contain 'word' and 'count' columns.")

        # Convert words to lowercase for case-insensitive lookup
        df['word'] = df['word'].str.lower()

        # Set the 'word' column as the index
        # drop=True removes the 'word' column after setting it as index
        # inplace=True modifies the DataFrame directly
        df.set_index('word', inplace=True, drop=True)

        # Convert the DataFrame (with only the 'count' column remaining) into a Series
        # This maps word (index) to count (value)
        _frequency_data = df['count']

        # Optional: Convert counts to numeric, coercing errors (though they should be numbers)
        _frequency_data = pd.to_numeric(_frequency_data, errors='coerce').fillna(0)

        print(f"Successfully loaded {_frequency_data.shape[0]} words.")

    except FileNotFoundError:
        print(f"Error: Frequency data file not found at {filepath}")
        # Depending on requirements, you might want to raise the error
        # or handle it by setting _frequency_data to an empty Series or None
        _frequency_data = pd.Series(dtype=int) # Empty series
    except Exception as e:
        print(f"Error loading frequency data: {e}")
        _frequency_data = pd.Series(dtype=int) # Empty series on other errors

def get_word_frequency(word):
    """
    Retrieves the frequency count for a given word.
    Returns 0 if the word is not found or if data hasn't been loaded.
    """
    global _frequency_data
    if _frequency_data is None:
        print("Warning: Frequency data not loaded. Call load_frequency_data() first.")
        # Attempt to load data if not already loaded
        load_frequency_data()
        if _frequency_data is None: # Check again if loading failed
             return 0

    # Perform case-insensitive lookup
    lookup_word = word.lower()

    # Use .get() for efficient lookup with a default value if key is not found
    return int(_frequency_data.get(lookup_word, 0))

# Load the data when the module is first imported
# This ensures data is ready when the app starts
# Note: This might add a delay to application startup depending on file size.
# Consider lazy loading if startup time becomes an issue.
load_frequency_data()

# Example usage (for testing purposes)
if __name__ == '__main__':
    print(f"Frequency of 'the': {get_word_frequency('the')}")
    print(f"Frequency of 'aardvark': {get_word_frequency('aardvark')}") # Likely low or 0
    print(f"Frequency of 'nonexistentwordxyz': {get_word_frequency('nonexistentwordxyz')}")