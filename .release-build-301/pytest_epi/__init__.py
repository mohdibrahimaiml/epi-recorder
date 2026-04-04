"""
pytest-epi: Automatic EPI evidence generation for test suites.

Usage:
    pytest --epi                       # Keep artifacts for failing tests
    pytest --epi --epi-dir ./evidence # Custom output directory
    pytest --epi --epi-on-pass        # Keep passing test artifacts too
    pytest --epi --epi-no-sign        # Skip signing
"""
