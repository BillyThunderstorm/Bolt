#!/usr/bin/env python3
"""
Test multiple Ollama models to compare performance
"""

import dspy
import time

def test_model(model_name):
    print(f"\nTesting model: {model_name}")
    print("-" * 40)
    
    try:
        # Configure the model
        lm = dspy.LM(
            model=f"ollama/{model_name}",
            api_base="http://localhost:11434",
            api_key="ollama"
        )
        dspy.settings.configure(lm=lm)
        
        # Simple test
        class QA(dspy.Signature):
            question = dspy.InputField()
            answer = dspy.OutputField(desc="short factual answer")
        
        qa = dspy.Predict(QA)
        
        start_time = time.time()
        result = qa(question="What is the capital of Japan?")
        elapsed = time.time() - start_time
        
        print(f"Answer: {result.answer}")
        print(f"Response time: {elapsed:.2f} seconds")
        return True, result.answer, elapsed
        
    except Exception as e:
        print(f"Error with {model_name}: {e}")
        return False, str(e), 0

def main():
    print("Testing multiple Ollama models for DSPy compatibility")
    print("=" * 50)
    
    # Models you have available based on earlier check
    models = ["gemma4:latest", "qwen3.6:latest", "deepseek-r1:8b"]
    
    results = {}
    
    for model in models:
        success, answer, time_taken = test_model(model)
        results[model] = {
            'success': success,
            'answer': answer,
            'time': time_taken
        }
    
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    
    for model, result in results.items():
        status = "✓ PASS" if result['success'] else "✗ FAIL"
        print(f"{model}: {status}")
        if result['success']:
            print(f"  Answer: {result['answer']}")
            print(f"  Time: {result['time']:.2f}s")
        else:
            print(f"  Error: {result['answer']}")
        print()

if __name__ == "__main__":
    main()