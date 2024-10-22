from pynput import keyboard
import subprocess
import time
from threading import Event, Thread
import requests
import json
import os
from dotenv import load_dotenv

# Load environment variables for API key
load_dotenv()

# Global settings
DEBUG = True
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
API_URL = "https://api.openai.com/v1/chat/completions"
MODEL_NAME = "gpt-4o-mini"  # Updated model name

def log(message):
    """Print debug messages if DEBUG is True"""
    if DEBUG:
        print(message)

class TextReader:
    def __init__(self):
        log("Initializing Text-to-Speech Service...")
        
        if not OPENAI_API_KEY:
            raise ValueError("OpenAI API key not found. Please set OPENAI_API_KEY in your .env file")
        
        self.speaking = Event()
        self.should_stop = Event()
        self.keys_pressed = set()
        
        # Test the speech
        self.speak("System ready", test=True)
        log("Initialization complete!")

    def generate_summary(self, text):
        """Generate a summary using GPT-4O Mini"""
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # Simplified prompt for quick responses
        payload = {
    "model": MODEL_NAME,
    "messages": [
        {
            "role": "system",
            "content": """You are an expert analyst and educator who provides clear, insightful explanations. Follow these guidelines:

For Code:
- First briefly state what the code does in one sentence
- Explain the key components and their interactions
- Highlight important functions, patterns, or algorithms used
- Point out any notable optimizations or potential issues
- If there are any best practices or design patterns, mention them
- Keep explanations technical but accessible

For Text:
- Provide a clear, concise summary of the main points
- Identify key themes, arguments, or concepts
- Highlight any important relationships or implications
- Extract actionable insights or conclusions
- Maintain the original tone and context

Always prioritize clarity and precision. If the content contains errors or potential improvements, note them briefly. Format complex information in a structured way."""
        },
        {
            "role": "user",
            "content": text
        }
    ],
    "temperature": 0.3,
    "max_tokens": 150  # Increased for more detailed explanations
}
        try:
            response = requests.post(API_URL, headers=headers, json=payload)
            
            if response.status_code == 200:
                result = response.json()
                summary = result['choices'][0]['message']['content'].strip()
                return summary
            else:
                error_msg = f"API error {response.status_code}"
                if response.json().get('error'):
                    error_msg += f": {response.json()['error'].get('message', '')}"
                log(error_msg)
                return f"Error generating summary. {error_msg}"
                
        except requests.RequestException as e:
            log(f"Request failed: {e}")
            return "Connection error. Check your internet connection."
        except Exception as e:
            log(f"Error: {e}")
            return "Error generating summary."

    def speak(self, text, test=False):
        """Speak text using macOS say command with Samantha voice"""
        if not text or not text.strip():
            return
            
        if self.speaking.is_set():
            log("Canceling current speech...")
            subprocess.run(['killall', 'say'])
            time.sleep(0.1)
            
        try:
            self.speaking.set()
            text = text.strip().replace('"', '\\"')
            log(f"Speaking: {text[:100]}...")
            
            rate_param = [] if test else ['-r', '300']
            process = subprocess.Popen(['say', '-v', 'Samantha'] + rate_param + [text])
            
            def wait_for_speech():
                process.wait()
                self.speaking.clear()
                log("Speech finished")
                
            Thread(target=wait_for_speech, daemon=True).start()
            
        except Exception as e:
            log(f"Speech error: {e}")
            self.speaking.clear()

    def get_selected_text(self):
        """Get selected text using pbpaste"""
        try:
            kb = keyboard.Controller()
            with kb.pressed(keyboard.Key.cmd):
                kb.tap('c')
            time.sleep(0.1)
            
            result = subprocess.run(['pbpaste'], capture_output=True, text=True)
            text = result.stdout.strip()
            
            if text:
                log(f"Selected text: {text[:100]}...")
                return text
            else:
                log("No text selected")
                return None
            
        except Exception as e:
            log(f"Selection error: {e}")
            return None

    def on_press(self, key):
        try:
            self.keys_pressed.add(key)
            
            # Summarize (Cmd+Shift+S)
            if (keyboard.Key.cmd in self.keys_pressed and 
                keyboard.Key.shift in self.keys_pressed and 
                hasattr(key, 'char') and key.char == 's'):
                
                text = self.get_selected_text()
                if text:
                    self.speak("Summarizing...")
                    summary = self.generate_summary(text)
                    self.speak(summary)
                else:
                    log("Nothing selected")
            
            # Quit (Cmd+Shift+E)
            elif (keyboard.Key.cmd in self.keys_pressed and 
                  keyboard.Key.shift in self.keys_pressed and 
                  hasattr(key, 'char') and key.char == 'e'):
                subprocess.run(['killall', 'say'])
                self.should_stop.set()
                return False
                
        except Exception as e:
            log(f"Keyboard error: {e}")
            
        return True

    def on_release(self, key):
        try:
            self.keys_pressed.discard(key)
        except Exception as e:
            log(f"Release error: {e}")

    def run(self):
        print("\n=== Text-to-Speech Service with GPT-4O Mini ===")
        print("Shortcuts:")
        print("Cmd+Shift+S: Summarize selected text")
        print("Cmd+Shift+E: Quit")
        print(f"\nUsing {MODEL_NAME} for quick summaries")
        print("Speech rate: 300 words per minute")
        print("\nReady for input...\n")
        
        with keyboard.Listener(on_press=self.on_press, 
                             on_release=self.on_release) as listener:
            listener.join()
        
        print("\nService stopped")

if __name__ == "__main__":
    try:
        reader = TextReader()
        reader.run()
    except ValueError as e:
        print(f"Setup error: {e}")
    except Exception as e:
        print(f"Fatal error: {e}")
        raise
