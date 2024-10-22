from pynput import keyboard
import subprocess
import time
from threading import Event, Thread
import requests
import json

# Global debug flag
DEBUG = True
API_URL = "http://localhost:8080/completion"
MAX_TOKENS = 500

def log(message):
    """Print debug messages if DEBUG is True"""
    if DEBUG:
        print(message)

class TextReader:
    def __init__(self):
        log("Initializing Text-to-Speech Service...")
        
        # Create an event to manage speech state
        self.speaking = Event()
        self.should_stop = Event()
        
        # Keys tracking
        self.keys_pressed = set()
        
        # Test the speech
        self.speak("System ready", test=True)
        log("Initialization complete!")

    def generate_summary(self, text):
        """Generate a summary using the llama.cpp API"""
        prompt = f"""<|system|>
You are a helpful AI assistant that provides concise summaries.
<|end|>
<|user|>
Provide a brief, clear summary of the following text in 2-3 sentences, give a more detailed summary or explanation for code that is more than 10 lines:

{text}
<|end|>
<|assistant|>"""

        payload = {
            "prompt": prompt,
            "n_predict": MAX_TOKENS,
            "stream": True
        }
        headers = {
            "Content-Type": "application/json"
        }

        summary = ""
        try:
            with requests.post(API_URL, data=json.dumps(payload), headers=headers, stream=True) as response:
                if response.status_code == 200:
                    log("Successfully connected to LLM API")
                    for line in response.iter_lines():
                        if line:
                            try:
                                decoded_line = line.decode('utf-8')
                                if decoded_line.startswith('data: '):
                                    data = json.loads(decoded_line[6:])
                                    if 'content' in data:
                                        summary += data['content']
                            except json.JSONDecodeError:
                                log(f"Failed to decode JSON: {decoded_line}")
                else:
                    log(f"API request failed with status code: {response.status_code}")
                    return f"Error: Could not generate summary. Status code: {response.status_code}"
        except requests.RequestException as e:
            log(f"Request failed: {e}")
            return "Error: Failed to connect to the LLM API. Please check if the server is running."

        return summary.strip()

    def speak(self, text, test=False):
        """Speak text using macOS say command with Samantha voice"""
        if not text or not text.strip():
            return
            
        if self.speaking.is_set():
            log("Already speaking, canceling current speech...")
            subprocess.run(['killall', 'say'])
            time.sleep(0.1)
            
        try:
            self.speaking.set()
            text = text.strip().replace('"', '\\"')  # Escape quotes
            log(f"Speaking: {text[:100]}...")
            
            # Use normal speed for test message, fast speed for actual content
            rate_param = [] if test else ['-r', '300']
            
            # Start speech in background using Samantha voice
            process = subprocess.Popen(['say', '-v', 'Samantha'] + rate_param + [text])
            
            def wait_for_speech():
                process.wait()
                self.speaking.clear()
                log("Finished speaking")
                
            Thread(target=wait_for_speech, daemon=True).start()
            
        except Exception as e:
            log(f"Error speaking text: {e}")
            self.speaking.clear()

    def get_selected_text(self):
        """Get selected text using pbpaste"""
        try:
            # Simulate Cmd+C to copy selected text
            kb = keyboard.Controller()
            with kb.pressed(keyboard.Key.cmd):
                kb.tap('c')
            time.sleep(0.1)
            
            result = subprocess.run(['pbpaste'], capture_output=True, text=True)
            text = result.stdout.strip()
            
            if text:
                log(f"\nCaptured text: {text[:100]}...")
                return text
            else:
                log("No text captured")
                return None
            
        except Exception as e:
            log(f"Error getting selected text: {e}")
            return None

    def on_press(self, key):
        try:
            # Add pressed key to set
            self.keys_pressed.add(key)
            
            # Check for Cmd+Shift+S (summarize)
            if (keyboard.Key.cmd in self.keys_pressed and 
                keyboard.Key.shift in self.keys_pressed and 
                hasattr(key, 'char') and key.char == 's'):
                
                log("Summarize hotkey detected!")
                text = self.get_selected_text()
                if text:
                    log("Generating summary...")
                    summary = self.generate_summary(text)
                    log(f"Summary generated: {summary}")
                    self.speak(summary)
                else:
                    log("No text selected")
            
            # Check for Cmd+Shift+E (quit)
            elif (keyboard.Key.cmd in self.keys_pressed and 
                  keyboard.Key.shift in self.keys_pressed and 
                  hasattr(key, 'char') and key.char == 'e'):
                log("Quit hotkey detected!")
                subprocess.run(['killall', 'say'])
                self.should_stop.set()
                return False
                
        except Exception as e:
            log(f"Error in key handler: {e}")
            
        return True

    def on_release(self, key):
        try:
            self.keys_pressed.discard(key)
        except Exception as e:
            log(f"Error in release handler: {e}")

    def run(self):
        print("\n=== Text-to-Speech Service with LLM Summarization Started ===")
        print("Shortcuts:")
        print("Select text: Automatically reads the selection")
        print("Cmd+Shift+S: Summarize selected text")
        print("Cmd+Shift+E: Quit")
        print("\nSpeech is set to 300 words per minute")
        print("Waiting for keyboard events...\n")
        
        with keyboard.Listener(on_press=self.on_press, 
                             on_release=self.on_release) as listener:
            listener.join()
        
        print("\nService stopped")

if __name__ == "__main__":
    try:
        reader = TextReader()
        reader.run()
    except Exception as e:
        print(f"Fatal error: {e}")
        raise
