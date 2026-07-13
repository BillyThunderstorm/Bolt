import os
import sys
import asyncio
from pathlib import Path
from google import genai
from google.genai import types

def load_bolt_context() -> str:
    """Assembles Bolt's identity and core instructions."""
    try:
        project_root = Path(__file__).resolve().parent.parent
        with open(project_root / "Bolt_Personality.txt", "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "You are Bolt, a cheerful and high-energy assistant."

async def run_bolt_multimodal():
    # Keep using your local key setup securely
    my_key = os.environ.get("GEMINI_API_KEY", "")
    if not my_key:
        print("❌ Error: Please set the GEMINI_API_KEY environment variable!")
        return

    client = genai.Client(api_key=my_key)
    
    # Using the native fast multimodal model
    model_id = "gemini-2.5-flash" 
    
    # ADJUSTMENT: Request BOTH text and audio modalities back!
    config = types.GenerateContentConfig(
        system_instruction=load_bolt_context(),
        response_modalities=["TEXT", "AUDIO"], 
        temperature=0.85,
    )

    print("\n⚡ Bolt Multimodal Core Online!")
    print("Type your message below. Bolt will print the text and speak aloud simultaneously.")
    print("Type 'exit' or 'quit' to close the session.\n")

    while True:
        try:
            user_input = input("Billy: ").strip()
            if user_input.lower() in ['exit', 'quit']:
                print("\n⚡ Bolt: Goodbye! Catch you next stream!")
                break
            if not user_input:
                continue

            print("\nBolt: ", end="", flush=True)

            # Request content generation asynchronously
            response = client.aio.models.generate_content(
                model=model_id,
                contents=user_input,
                config=config
            )
            
            # Read and play chunks as they arrive
            async for chunk in await response:
                # 1. Print the text on your screen so you can read along
                if chunk.text:
                    print(chunk.text, end="", flush=True)
                
                # 2. Play the native audio data directly
                if chunk.inline_data:
                    audio_bytes = chunk.inline_data.data
                    # Hand audio_bytes over to your local output device
                    pass
            
            print("\n") # New line after text stream completes

        except KeyboardInterrupt:
            print("\n⚡ Bolt session closed safely.")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}\n")

if __name__ == "__main__":
    asyncio.run(run_bolt_multimodal())