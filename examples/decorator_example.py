"""
Example using the @record decorator for zero-config recording.
"""

from epi_recorder import record


@record
def main():
    """
    This function is automatically recorded.
    Output file is auto-generated in ./epi-recordings/
    """
    print("Running decorated function...")
    
    # Your code here
    numbers = [1, 2, 3, 4, 5]
    total = sum(numbers)
    
    print(f"Sum of {numbers} = {total}")
    print("Function complete!")
    
    return total


if __name__ == "__main__":
    result = main()
    print(f"\nResult: {result}")
    print("Check ./epi-recordings/ for the .epi file!")


