import requests
import json
import pyttsx3
import logging
from logging.handlers import RotatingFileHandler
import re
import time
import threading
import queue
import pyautogui
import pytesseract
from PIL import Image
import os
import subprocess
from datetime import datetime

# Set up logging
log_file = 'productivity_assistant.log'
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(threadName)s - %(levelname)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)

# Add file handler
file_handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=3)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(threadName)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

# Constants
API_URL = "http://localhost:8080/completion"
MAX_TOKENS = 500
CHECK_INTERVAL = 300  # 5 minutes
CHUNK_SIZE = 250
SPEECH_RATE = 300

class ThreadSafeSpeechEngine:
    def __init__(self):
        self.engine = None
        self.lock = threading.Lock()
        self.speech_queue = queue.Queue()
        self.is_running = False
        self.engine_thread = None

    def initialize(self):
        with self.lock:
            if self.engine is None:
                try:
                    logging.info("Initializing pyttsx3 engine")
                    self.engine = pyttsx3.init()
                    self.engine.startLoop(False)  # Start the event loop in non-blocking mode
                    logging.info("pyttsx3 engine initialized successfully")
                except Exception as e:
                    logging.error(f"Failed to initialize pyttsx3 engine: {e}")
                    raise

    def say(self, text):
        self.speech_queue.put(text)
        if not self.is_running:
            self.start()

    def process_speech_queue(self):
        while self.is_running or not self.speech_queue.empty():
            try:
                text = self.speech_queue.get(timeout=1)
                with self.lock:
                    if self.engine:
                        logging.debug(f"Speaking: {text[:50]}...")  # Log first 50 chars
                        self.engine.say(text)
                        # while self.engine.isBusy():
                        for i in range(105):
                            self.engine.iterate()
                            time.sleep(0.1)
                self.speech_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logging.error(f"Error during speech processing: {e}")

    def start(self):
        if not self.is_running:
            self.is_running = True
            self.engine_thread = threading.Thread(target=self.process_speech_queue)
            self.engine_thread.start()

    def stop(self):
        self.is_running = False
        if self.engine_thread:
            self.engine_thread.join()
        with self.lock:
            if self.engine:
                self.engine.endLoop()
                self.engine.stop()
                self.engine = None

    def set_property(self, name, value):
        with self.lock:
            if self.engine:
                self.engine.setProperty(name, value)

class TesseractNotFoundError(Exception):
    """Custom exception for when Tesseract is not found."""
    pass

class ProductivityAssistant:
    def __init__(self):
        self.speech_engine = ThreadSafeSpeechEngine()
        self.speech_engine.initialize()
        self.speech_rate = SPEECH_RATE
        self.speech_engine.set_property('rate', self.speech_rate)

    def speak_text(self, text):
        """Speak the given text using the thread-safe speech engine."""
        logger.debug(f"Queueing text to speak: {text[:50]}...")  # Log first 50 chars
        self.speech_engine.say(text)

    def initialize_speech_engine(self):
        logger.info("Initializing speech engine")
        self.speech_engine.initialize()
        self.speech_engine.set_property('rate', self.speech_rate)
        logger.info("Speech engine initialized")

    def find_tesseract_mac(self):
        """Find Tesseract executable on macOS."""
        logger.info("Searching for Tesseract executable")
        common_paths = [
            '/opt/homebrew/bin/tesseract',
            '/usr/local/bin/tesseract',
        ]
        
        for path in common_paths:
            if os.path.isfile(path):
                logger.info(f"Tesseract found at: {path}")
                return path
        
        try:
            path = subprocess.check_output(['which', 'tesseract']).decode().strip()
            logger.info(f"Tesseract found at: {path}")
            return path
        except subprocess.CalledProcessError:
            logger.error("Tesseract not found in system PATH")
            return None

    def setup_tesseract(self):
        """Set up Tesseract OCR."""
        tesseract_cmd = self.find_tesseract_mac()
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
            logger.info(f"Tesseract set up successfully at: {tesseract_cmd}")
        else:
            logger.error("Tesseract executable not found")
            raise TesseractNotFoundError("Tesseract executable not found. Please install Tesseract OCR using Homebrew.")

    def generate_text_stream(self, prompt, api_url=API_URL, max_tokens=MAX_TOKENS):
        """Generate text using the llama.cpp API and yield chunks as they arrive."""
        logger.info("Starting text generation")
        payload = {
            "prompt": prompt,
            "n_predict": max_tokens,
            "stream": True
        }
        headers = {
            "Content-Type": "application/json"
        }
        
        try:
            with requests.post(api_url, data=json.dumps(payload), headers=headers, stream=True) as response:
                if response.status_code == 200:
                    logger.info("Successfully connected to API")
                    for line in response.iter_lines():
                        if line:
                            try:
                                decoded_line = line.decode('utf-8')
                                if decoded_line.startswith('data: '):
                                    data = json.loads(decoded_line[6:])
                                    if 'content' in data:
                                        yield data['content']
                            except json.JSONDecodeError:
                                logger.error(f"Failed to decode JSON: {decoded_line}")
                else:
                    logger.error(f"API request failed with status code: {response.status_code}")
                    yield f"Error: {response.status_code}, {response.text}"
        except requests.RequestException as e:
            logger.error(f"Request failed: {e}")
            yield f"Error: Failed to connect to the API. Please check if the server is running."

    def chunk_text(self, text, chunk_size=CHUNK_SIZE):
        """Split text into chunks at sentence boundaries or after a certain length."""
        logger.debug(f"Chunking text of length {len(text)}")
        chunks = []
        current_chunk = ""
        sentences = re.split('([.!?])', text)
        for sentence in sentences:
            if len(current_chunk) + len(sentence) > chunk_size:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence
            else:
                current_chunk += sentence
        if current_chunk:
            chunks.append(current_chunk.strip())
        logger.debug(f"Text split into {len(chunks)} chunks")
        return chunks

    def take_screenshot_and_analyze(self):
        """Take a screenshot, perform OCR, and check if the content is work-related."""
        logger.info("Taking screenshot for productivity analysis")
        screenshot = pyautogui.screenshot()
        
        try:
            text = pytesseract.image_to_string(screenshot)
            logger.debug(f"OCR extracted text: {text[:100]}...")  # Log first 100 chars
            
            work_related_keywords = ['code', 'python', 'project', 'task', 'deadline', 'meeting']
            is_work_related = any(keyword in text.lower() for keyword in work_related_keywords)
            
            logger.info(f"Screenshot analysis result: work-related = {is_work_related}")
            return is_work_related
        except Exception as e:
            logger.error(f"Error in OCR processing: {e}")
            return True  # Assume work-related in case of errors

    def productivity_check_thread(self):
        """Thread function to periodically check productivity."""
        logger.info("Starting productivity check thread")
        while True:
            time.sleep(CHECK_INTERVAL)
            try:
                is_work_related = self.take_screenshot_and_analyze()
                if not is_work_related:
                    reminder = "It seems you might be distracted. Remember to focus on your work tasks."
                    logger.info("Productivity reminder triggered")
                    print("\nProductivity Reminder:", reminder)
                    self.speak_text(reminder)
            except Exception as e:
                logger.error(f"Error in productivity check: {e}")

    def handle_user_input(self):
        """Handle user input for changing speech rate."""
        user_input = input("Enter your prompt (or 'quit' to exit, 'rate' to change speech rate): ")
        logger.info(f"Received user input: {user_input[:50]}...")  # Log first 50 chars
        
        if user_input.lower() == 'quit':
            logger.info("User initiated quit")
            return False, None
        elif user_input.lower() == 'rate':
            try:
                new_rate = int(input("Enter new speech rate (words per minute): "))
                logger.info(f"Speech rate changed to {new_rate}")
                self.speech_rate = new_rate
                self.speech_engine.set_property('rate', new_rate)
                print(f"Speech rate updated to {new_rate} words per minute")
                return True, None
            except ValueError:
                logger.warning("Invalid input for speech rate")
                print("Invalid input. Please enter a number.")
                return True, None
        
        return True, user_input

    def process_response(self, response):
        """Process and queue the response from the AI for speech."""
        logger.info("Processing AI response")
        text_buffer = ""
        for chunk in response:
            print(chunk, end='', flush=True)
            text_buffer += chunk
            
            if len(text_buffer) > 150 or any(p in text_buffer for p in '.!?'):
                speech_chunks = self.chunk_text(text_buffer)
                for speech_chunk in speech_chunks[:-1]:
                    logger.debug(f"Adding to speech queue: {speech_chunk[:50]}...")  # Log first 50 chars
                    self.speak_text(speech_chunk)
                text_buffer = speech_chunks[-1] if speech_chunks else ""
        
        if text_buffer:
            logger.debug(f"Adding final buffer to speech queue: {text_buffer[:50]}...")  # Log first 50 chars
            self.speak_text(text_buffer)
        
        print("\n")
        logger.info("Finished processing AI response")

    def run(self):
        logger.info("Starting Productivity Assistant")
        try:
            self.setup_tesseract()
        except TesseractNotFoundError as e:
            logger.error(str(e))
            print("Warning: Tesseract OCR not found. Productivity checks will be disabled.")
            print("Please install Tesseract OCR using: brew install tesseract")
            return

        self.initialize_speech_engine()
        
        logger.info(f"Initial speech rate set to {self.speech_rate}")
        print(f"Current speech rate: {self.speech_rate} words per minute")
        
        productivity_thread = threading.Thread(target=self.productivity_check_thread, name="ProductivityThread")
        productivity_thread.start()
        
        conversation = [
            "<|system|>\nYou are a helpful AI assistant.<|end|>\n"
        ]
        
        while True:
            continue_loop, user_input = self.handle_user_input()
            if not continue_loop:
                break
            if user_input is None:
                continue
            
            conversation.append(f"<|user|>\n{user_input}<|end|>\n")
            conversation.append("<|assistant|>\n")
            
            full_prompt = "".join(conversation)
            
            try:
                logger.info("Generating AI response")
                response = self.generate_text_stream(full_prompt)
                self.process_response(response)
                conversation[-1] += user_input + "<|end|>\n"
            except Exception as e:
                logger.error(f"An error occurred in main loop: {e}", exc_info=True)
                print(f"An error occurred. Please check the logs for details.")

        self.speech_engine.stop()
        logger.info("Productivity Assistant shutting down")

if __name__ == "__main__":
    assistant = ProductivityAssistant()
    assistant.run()
