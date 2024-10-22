import pyttsx3
import threading
import queue
import time
import logging

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

class EventRef:
    def __init__(self):
        self._event = threading.Event()

    def set(self):
        self._event.set()

    def clear(self):
        self._event.clear()

    def is_set(self):
        return self._event.is_set()

    def wait(self, timeout=None):
        return self._event.wait(timeout)

class ThreadSafeSpeechEngine:
    def __init__(self):
        try:
            logging.info("Initializing pyttsx3 engine")
            self.engine = pyttsx3.init("nsss")
            logging.info("pyttsx3 engine initialized successfully")
        except Exception as e:
            logging.error(f"Failed to initialize pyttsx3 engine: {e}")
            exit(1)

        self.lock = threading.Lock()
        self.speech_queue = queue.Queue()
        self.is_running = False
        self.utterance_completed = EventRef()
        self.engine.connect('started-utterance', self.on_start_utterance)
        self.engine.connect('finished-utterance', self.on_finish_utterance)
        self.engine_thread = None

    def on_start_utterance(self, name):
        logging.debug(f"Started utterance: {name}")
        self.utterance_completed.clear()

    def on_finish_utterance(self, name, completed):
        logging.debug(f"Finished utterance: {name}, completed: {completed}")
        self.utterance_completed.set()

    def say(self, text):
        """ Adds a text string to the speech queue. """
        logging.info(f"Queueing: {text}")
        self.speech_queue.put(text)

    def process_speech_queue(self):
        """ Process the speech queue using the engine's internal loop. """
        while self.is_running or not self.speech_queue.empty():
            try:
                text = self.speech_queue.get(block=False)
                with self.lock:
                    logging.debug(f"Speaking: {text}")
                    self.engine.say(text, text)
                self.speech_queue.task_done()
            except queue.Empty:
                time.sleep(0.1)  # Short sleep to prevent busy waiting
            except Exception as e:
                logging.error(f"Error during speech processing: {e}")

    def run(self):
        """ Starts the speech engine processing loop. """
        self.is_running = True
        self.process_speech_queue()

    def start(self):
        """ Starts the speech engine in a separate thread. """
        self.engine_thread = threading.Thread(target=self.run, daemon=True)
        self.engine_thread.start()

    def stop(self):
        """ Stops the speech engine loop gracefully. """
        self.is_running = False
        self.engine.runAndWait()
        logging.info("Stopping speech engine...")
        if self.engine_thread:
            self.engine_thread.join(timeout=5)
        self.engine.stop()

def main():
    speech_engine = ThreadSafeSpeechEngine()

    speech_engine.start()

    for i in range(5):
        text = f"This is test number {i+1}"
        speech_engine.say(text)
        time.sleep(0.1)

    speech_engine.speech_queue.join()

    time.sleep(1)

    logging.info("All speech tasks completed.")
    speech_engine.stop()

if __name__ == "__main__":
    main()
