#!/usr/bin/env python3
"""
Test script to verify DSPy setup for content creation assistant
"""

import dspy

def main():
    print("Testing DSPy setup for content creation assistant...")
    
    # Configure local LLM via Ollama
    lm = dspy.LM(
        model="ollama/gemma4:latest",  # You can change to qwen3.6 or deepseek-r1
        api_base="http://localhost:11434",
        api_key="ollama"  # Ollama doesn't actually validate the key
    )
    dspy.settings.configure(lm=lm)
    
    print(f"Using model: gemma4:latest via Ollama at http://localhost:11434")
    
    # Define a simple signature for content ideation
    class ContentIdeas(dspy.Signature):
        """Generate content ideas for a given niche and trend"""
        niche = dspy.InputField(desc="Content niche (e.g., tech reviews, gaming, skincare)")
        trend = dspy.InputField(desc="Current trend or topic in that niche")
        ideas = dspy.OutputField(desc="3 specific content ideas combining niche and trend")
    
    # Create the predictor
    idea_generator = dspy.Predict(ContentIdeas)
    
    # Test cases for your different niches
    test_cases = [
        {
            "niche": "tech reviews",
            "trend": "AI-powered gaming accessories"
        },
        {
            "niche": "skincare",
            "trend": "AI skin analysis apps"
        },
        {
            "niche": "live streaming",
            "trend": "virtual set technology"
        },
        {
            "niche": "AI development",
            "trend": "open source LLMs for content creation"
        }
    ]
    
    print("\n" + "="*50)
    print("Testing content idea generation:")
    print("="*50)
    
    for i, case in enumerate(test_cases, 1):
        print(f"\nTest {i}: {case['niche']} + {case['trend']}")
        print("-" * 40)
        
        try:
            result = idea_generator(
                niche=case["niche"],
                trend=case["trend"]
            )
            print(result.ideas)
        except Exception as e:
            print(f"Error: {e}")
            print("Tip: Make sure Ollama is running and the model is available")
    
    print("\n" + "="*50)
    print("Test complete!")
    print("If you see coherent ideas above, your setup is working.")
    print("Next steps:")
    print("1. Try different models (qwen3.6, deepseek-r1)")
    print("2. Create more specific signatures for your needs")
    print("3. Build a content planning pipeline")
    print("4. Add retrieval using your existing notes")
    print("="*50)

if __name__ == "__main__":
    main()