"""
Voice command listener for the PC AI Assistant.

Uses the `SpeechRecognition` library with Google's free speech API.
If the library is not installed the function falls back to returning an
empty string so the rest of the assistant can continue with text input.

Install:  pip install SpeechRecognition pyaudio
"""

def listen_for_command(language: str = "en-US") -> str:
    """
    Listen from the microphone for one utterance and return the transcribed text.
    Returns "" if nothing was heard or if SpeechRecognition is not installed.
    """
    try:
        import speech_recognition as sr  # type: ignore
    except ImportError:
        print("[Voice] SpeechRecognition not installed — run: pip install SpeechRecognition pyaudio")
        return ""

    recognizer = sr.Recognizer()
    recognizer.pause_threshold = 1.0   # seconds of silence before stopping

    print("[Voice] Listening... (speak now)")
    try:
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio = recognizer.listen(source, timeout=8, phrase_time_limit=12)
    except sr.WaitTimeoutError:
        print("[Voice] No speech detected.")
        return ""
    except Exception as e:
        print(f"[Voice] Microphone error: {e}")
        return ""

    try:
        text = recognizer.recognize_google(audio, language=language)
        print(f"[Voice] Heard: {text}")
        return text
    except sr.UnknownValueError:
        print("[Voice] Could not understand audio.")
        return ""
    except sr.RequestError as e:
        print(f"[Voice] Google Speech API error: {e}")
        return ""
