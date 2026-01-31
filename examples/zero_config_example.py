"""
Example using zero-config context manager.
"""

from epi_recorder import record


def main():
    # Zero-config: no filename needed!
    with record():
        print("Recording with auto-generated filename...")
        
        # Your workflow code
        data = [10, 20, 30, 40, 50]
        average = sum(data) / len(data)
        
        print(f"Data: {data}")
        print(f"Average: {average}")
        
        print("Recording complete!")
    
    print("\nFile saved to ./epi-recordings/ with auto-generated name!")
    print("Run 'epi ls' to see it.")


if __name__ == "__main__":
    main()


