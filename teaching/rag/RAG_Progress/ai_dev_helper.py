#!/usr/bin/env python3
"""
AI Development Helper - Assists with learning AI/ML concepts, planning projects, and getting coding help.
"""

import dspy

def setup_model(model_name="gemma4:latest"):
    """Configure the DSPy language model"""
    lm = dspy.LM(
        model=f"ollama/{model_name}",
        base_url="http://localhost:11434",
        api_key="ollama"
    )
    dspy.settings.configure(lm=lm)
    return lm

def test_ai_dev_helper():
    """Test an AI development helper for learning and project guidance"""
    
    print("Testing AI Development Helper")
    print("=" * 40)
    
    # Setup model - use gemma4 for speed
    setup_model("gemma4:latest")
    
    # Define a simple helper for AI dev questions
    class AIHelper(dspy.Signature):
        """Help with AI/ML learning and development questions"""
        question = dspy.InputField(desc="Question about AI/ML concepts, implementation, or learning")
        answer = dspy.OutputField(desc="Clear, helpful explanation or guidance")
    
    # Create the helper
    helper = dspy.Predict(AIHelper)
    
    # Test questions for AI development learning
    test_questions = [
        "What's the difference between fine-tuning and RAG for LLMs?",
        "How do I start learning about transformers as a beginner?",
        "What are good first projects for someone learning LLM development?",
        "Explain LoRA in simple terms",
        "What hardware do I need to run LLMs locally?",
        "How do I evaluate if my LLM is working well for text generation?"
    ]
    
    print("\nGetting AI development help:")
    print("-" * 40)
    
    for question in test_questions:
        print(f"\n❓ Question: {question}")
        try:
            result = helper(question=question)
            print(f"💡 Answer: {result.answer}")
        except Exception as e:
            print(f"Error: {e}")
    
    print("\n" + "=" * 40)
    print("AI Development Helper test complete!")

if __name__ == "__main__":
    test_ai_dev_helper()