"""
hello_llm.py — Quick test to verify Docker container and Anthropic API work

Run this inside the container to verify everything is connected:
    python3 hello_llm.py

You should see a response from Claude about LLMs.
"""

import os
import sys

def test_imports():
    """Verify key packages are installed"""
    print("Testing imports...")
    try:
        import torch
        print(f"  ✓ PyTorch {torch.__version__}")
    except ImportError as e:
        print(f"  ✗ PyTorch: {e}")
        return False
    
    try:
        import numpy as np
        print(f"  ✓ NumPy {np.__version__}")
    except ImportError as e:
        print(f"  ✗ NumPy: {e}")
        return False
    
    try:
        import anthropic
        print(f"  ✓ Anthropic SDK available")
    except ImportError as e:
        print(f"  ✗ Anthropic: {e}")
        return False
    
    return True

def test_anthropic_api():
    """Test connection to Claude API"""
    print("\nTesting Anthropic API connection...")
    
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("  ✗ ANTHROPIC_API_KEY not set")
        return False
    
    print("  ✓ API key found")
    
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
        
        message = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=256,
            messages=[
                {
                    "role": "user",
                    "content": "Briefly explain what 'from scratch' means when building LLMs. Keep it to 2-3 sentences."
                }
            ]
        )
        
        print("  ✓ API call successful!")
        print(f"\nClaude's response:\n{message.content[0].text}\n")
        return True
    
    except Exception as e:
        print(f"  ✗ API error: {e}")
        return False

def main():
    print("=" * 60)
    print("LLM_From_Scratch Docker Container — Hello Test")
    print("=" * 60)
    
    imports_ok = test_imports()
    api_ok = test_anthropic_api()
    
    print("=" * 60)
    if imports_ok and api_ok:
        print("✓ All tests passed! Your sandbox is ready for experiments.")
        print("\nNext steps:")
        print("  1. Create a new .py file in this folder")
        print("  2. Import torch, numpy, anthropic as needed")
        print("  3. Run it with: python3 your_script.py")
    else:
        print("✗ Some tests failed. Check the output above.")
    print("=" * 60)

if __name__ == "__main__":
    main()
