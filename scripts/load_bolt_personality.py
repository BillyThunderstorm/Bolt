import os
import sys
from pathlib import Path
from google import genai
from google.genai import types

def load_bolt_personality():
    """
    Points directly to the absolute path of your Bolt developer folder.
    """
    project_root = Path(__file__).resolve().parents[3]
    file_path = project_root / "Bolt_Personality.txt"
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        print(f"❌ Error: Could not find your personality file at: {file_path}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        sys.exit(1)

def run_bolt_assistant():
    bolt_instructions = load_bolt_personality()
    
    # ─── PASTE YOUR KEY INSIDE THE QUOTES BELOW ───
    my_key = os.environ.get("GEMINI_API_KEY", "")
    
    # Pass the key variable straight into the client
    client = genai.Client(api_key=my_key)
    
    config = types.GenerateContentConfig(
        system_instruction=bolt_instructions,
        temperature=0.85,
    )
    
    print("\n⚡ Bolt is online and ready to build!")
    print("Type 'exit' or 'quit' to end the session.\n")
    
    chat = client.chats.create(model="gemini-3.5-flash", config=config)
    
    while True:
        try:
            user_input = input("Billy: ")
            if user_input.lower() in ['exit', 'quit']:
                print("\n⚡ Bolt: Goodbye!")
                break
            if not user_input.strip():
                continue
                
            response = chat.send_message(user_input)
            print(f"\nBolt: {response.text}\n")
            
        except KeyboardInterrupt:
            print("\n⚡ Bolt: Exiting safely!")
            sys.exit(0)
        except Exception as e:
            print(f"\n❌ Chat error: {e}\n")

if __name__ == "__main__":
    run_bolt_assistant()