#!/usr/bin/env python3
"""
Run all EPI Recorder demos
"""

import subprocess
import sys
from pathlib import Path

def run_command(command, description):
    """Run a command and print its output"""
    print(f"\n{'='*60}")
    print(f"🏃 Running: {description}")
    print(f"{'='*60}")
    print(f"Command: {command}\n")
    
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        print(f"Exit code: {result.returncode}")
        return result.returncode == 0
    except Exception as e:
        print(f"Error running command: {e}")
        return False

def main():
    """Run all demo scripts"""
    print("🚀 EPI Recorder Complete Demo Suite")
    print("=" * 50)
    
    # Get the current directory
    current_dir = Path.cwd()
    print(f"Working directory: {current_dir}")
    
    # Run the complete example
    success1 = run_command(
        "python complete_example.py",
        "Complete Example (Simulated AI Workflow)"
    )
    
    # Verify the complete example
    if Path("my_complete_example.epi").exists():
        success2 = run_command(
            "python -m epi_cli.main verify my_complete_example.epi",
            "Verification of Complete Example"
        )
    else:
        print("⚠️  my_complete_example.epi not found, skipping verification")
        success2 = True
    
    # Run the OpenAI example
    success3 = run_command(
        "python openai_example.py",
        "OpenAI Example (Simulated)"
    )
    
    # Verify the OpenAI example
    if Path("openai_example.epi").exists():
        success4 = run_command(
            "python -m epi_cli.main verify openai_example.epi",
            "Verification of OpenAI Example"
        )
    else:
        print("⚠️  openai_example.epi not found, skipping verification")
        success4 = True
    
    # Summary
    print(f"\n{'='*60}")
    print("🏁 DEMO SUITE COMPLETE")
    print(f"{'='*60}")
    
    all_success = success1 and success2 and success3 and success4
    
    if all_success:
        print("✅ All demos completed successfully!")
        print("\n📁 Generated files:")
        if Path("my_complete_example.epi").exists():
            print("   - my_complete_example.epi")
        if Path("openai_example.epi").exists():
            print("   - openai_example.epi")
        print("\n📋 To view the results:")
        print("   epi view my_complete_example.epi")
        print("   epi view openai_example.epi")
    else:
        print("❌ Some demos failed. Check the output above.")
    
    print("\n📖 Check these files for more information:")
    print("   - STEP_BY_STEP_GUIDE.md")
    print("   - EPI_RECORDER_DEMO_SUMMARY.md")
    print("   - complete_example.py")
    print("   - openai_example.py")

if __name__ == "__main__":
    main()


