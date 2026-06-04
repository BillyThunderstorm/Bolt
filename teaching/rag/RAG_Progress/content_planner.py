#!/usr/bin/env python3
"""
Content Planning System - Step 2: Structured Content Planning
Builds on the basic idea generation to create detailed content plans
"""

import dspy

def setup_model(model_name="gemma4:latest"):
    """Configure the DSPy language model"""
    lm = dspy.LM(
        model=f"ollama/{model_name}",
        api_base="http://localhost:11434",
        api_key="ollama"
    )
    dspy.settings.configure(lm=lm)
    return lm

def test_content_planner():
    """Test a structured content planner that creates detailed outlines"""
    
    print("Testing Content Planner - Creating structured content outlines")
    print("=" * 60)
    
    # Setup model
    setup_model("gemma4:latest")  # Fastest option for testing
    
    # Define a detailed signature for content planning
    class ContentPlan(dspy.Signature):
        """Create a detailed content plan for a specific niche and topic"""
        niche = dspy.InputField(desc="Content niche: tech reviews, gaming, skincare, streaming, or AI development")
        topic = dspy.InputField(desc="Specific topic or product to cover")
        audience = dspy.InputField(desc="Target audience: beginners, intermediate, experts, or general")
        format_type = dspy.InputField(desc="Content format: YouTube video, TikTok, blog post, livestream, or Twitter thread")
        
        # Output fields for structured planning
        hook = dspy.OutputField(desc="Opening hook to grab attention (1-2 sentences)")
        key_points = dspy.OutputField(desc="3-5 main points to cover, each with a brief description")
        structure = dspy.OutputField(desc="Suggested structure/format with timing or sections")
        engagement_tips = dspy.OutputField(desc="Specific tips to increase audience engagement")
        call_to_action = dspy.OutputField(desc="Clear call-to-action for viewers/readers")
    
    # Create the planner
    planner = dspy.ChainOfThought(ContentPlan)
    
    # Test cases covering your different content areas
    test_cases = [
        {
            "niche": "tech reviews",
            "topic": "AI-powered noise cancelling headphones for gamers",
            "audience": "intermediate gamers who stream",
            "format_type": "YouTube video"
        },
        {
            "niche": "skincare",
            "topic": "vitamin C serum for sensitive skin",
            "audience": "beginners to skincare",
            "format_type": "TikTok series (3 parts)"
        },
        {
            "niche": "AI development",
            "topic": "fine-tuning LLMs for content generation",
            "audience": "developers with some ML experience",
            "format_type": "blog post with code examples"
        }
    ]
    
    print("\nGenerating detailed content plans:")
    print("=" * 60)
    
    for i, case in enumerate(test_cases, 1):
        print(f"\n--- Plan {i}: {case['niche']} ---")
        print(f"Topic: {case['topic']}")
        print(f"Audience: {case['audience']}")
        print(f"Format: {case['format_type']}")
        print("-" * 40)
        
        try:
            result = planner(
                niche=case["niche"],
                topic=case["topic"],
                audience=case["audience"],
                format_type=case["format_type"]
            )
            
            print(f"🎣 Hook: {result.hook}")
            print(f"\n📌 Key Points:")
            print(result.key_points)
            print(f"\n🏗️ Structure: {result.structure}")
            print(f"\n💡 Engagement Tips: {result.engagement_tips}")
            print(f"\n📣 Call to Action: {result.call_to_action}")
            
        except Exception as e:
            print(f"Error: {e}")
    
    print("\n" + "=" * 60)
    print("Content Planner test complete!")
    print("Next steps could include:")
    print("1. Creating templates for different content formats")
    print("2. Adding research/data gathering steps")
    print("3. Building a review generation system")
    print("4. Implementing feedback loops for improvement")
    print("=" * 60)

if __name__ == "__main__":
    test_content_planner()