import copy
import json
import os
import platform
import random
import re
import subprocess
import tempfile
import time
import urllib.parse
import webbrowser

import speech_recognition as sr
import pyttsx3
try:
    import requests
except ImportError:
    requests = None
try:
    from gtts import gTTS
    from playsound import playsound
except ImportError:
    gTTS = None
    playsound = None


WAKE_WORDS = {"hey sucu", "hey suku", "hey suck", "hey siri", "Hey suki", "suqqu"}
PROMPT_TEXT = "What do you want?"
ACKNOWLEDGMENTS = [
    "Alright, sure.",
    "Ok.",
    "Got it.",
    "Sounds good.",
    "Sure.",
    "Whatever you want.",
]
VOICE_PREFERENCES = [
    "Samantha",
    "Ava",
    "Victoria",
    "Zira",
    "David",
]
USE_AI_VOICE = True
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
ALIASES_PATH = os.path.join(os.path.dirname(__file__), "app_aliases.json")
DEFAULT_ALIASES = {
    "darwin": {
        "google": "Google Chrome",
        "chrome": "Google Chrome",
        "google chrome": "Google Chrome",
        "vs code": "Visual Studio Code",
        "vscode": "Visual Studio Code",
        "visual studio code": "Visual Studio Code",
        "safari": "Safari",
        "notes": "Notes",
        "calculator": "Calculator",
    },
    "windows": {
        "google": "chrome",
        "chrome": "chrome",
        "google chrome": "chrome",
        "vs code": "Visual Studio Code",
        "vscode": "Visual Studio Code",
        "visual studio code": "Visual Studio Code",
        "edge": "msedge",
        "notepad": "notepad",
        "calculator": "calc",
    },
}


def speak(engine: pyttsx3.Engine, text: str) -> None:
    try:
        engine.stop()
    except Exception:
        pass
    if USE_AI_VOICE and ELEVENLABS_API_KEY and requests:
        try:
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
            headers = {
                "xi-api-key": ELEVENLABS_API_KEY,
                "accept": "audio/mpeg",
                "content-type": "application/json",
            }
            payload = {
                "text": text,
                "model_id": "eleven_monolingual_v1",
                "voice_settings": {"stability": 0.4, "similarity_boost": 0.75},
            }
            response = requests.post(url, json=payload, headers=headers, timeout=20)
            response.raise_for_status()
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                path = tmp.name
                tmp.write(response.content)
            if playsound:
                playsound(path)
            else:
                raise RuntimeError("playsound is required for ElevenLabs audio playback.")
        except Exception:
            engine.say(text)
            engine.runAndWait()
        finally:
            if "path" in locals() and os.path.exists(path):
                os.remove(path)
        return
    if USE_AI_VOICE and gTTS and playsound:
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                path = tmp.name
            gTTS(text=text, lang="en").save(path)
            playsound(path)
        except Exception:
            engine.say(text)
            engine.runAndWait()
        finally:
            if "path" in locals() and os.path.exists(path):
                os.remove(path)
        return
    engine.say(text)
    engine.runAndWait()


def is_url(text: str) -> bool:
    if text.startswith(("http://", "https://")):
        return True
    return bool(re.search(r"\b[a-z0-9-]+\.(com|org|net|io|edu|gov|ai|app|dev)\b", text))


def normalize_url(text: str) -> str:
    if text.startswith(("http://", "https://")):
        return text
    return f"https://{text}"


def open_website(target: str, aliases: dict[str, dict[str, str]]) -> None:
    url = normalize_url(target)
    system = platform.system().lower()
    browser_name = resolve_app_name("google", system, aliases)
    try:
        if system == "darwin":
            subprocess.Popen(["open", "-a", browser_name, url])
            return
        if system == "windows":
            subprocess.Popen(["cmd", "/c", "start", "", browser_name, url], shell=False)
            return
    except Exception:
        pass
    webbrowser.open(url)


def open_web_search(query: str) -> None:
    encoded = urllib.parse.quote_plus(query)
    webbrowser.open(f"https://www.google.com/search?q={encoded}")


def normalize_alias_key(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def load_aliases() -> dict[str, dict[str, str]]:
    aliases = copy.deepcopy(DEFAULT_ALIASES)
    if not os.path.exists(ALIASES_PATH):
        return aliases
    try:
        with open(ALIASES_PATH, "r", encoding="utf-8") as handle:
            stored = json.load(handle)
        for system, mapping in stored.items():
            if isinstance(mapping, dict):
                aliases.setdefault(system, {}).update(mapping)
    except Exception:
        pass
    return aliases


def save_aliases(aliases: dict[str, dict[str, str]]) -> None:
    try:
        with open(ALIASES_PATH, "w", encoding="utf-8") as handle:
            json.dump(aliases, handle, indent=2, sort_keys=True)
    except Exception:
        pass


def resolve_app_name(target: str, system: str, aliases: dict[str, dict[str, str]]) -> str:
    key = normalize_alias_key(target)
    return aliases.get(system, {}).get(key, target)


def open_application(target: str, aliases: dict[str, dict[str, str]]) -> None:
    system = platform.system().lower()
    target = resolve_app_name(target, system, aliases)
    if system == "darwin":
        subprocess.Popen(["open", "-a", target])
        return
    if system == "windows":
        try:
            os.startfile(target)
        except OSError:
            subprocess.Popen(["cmd", "/c", "start", "", target], shell=False)
        return
    raise RuntimeError(f"Unsupported OS: {system}")


def parse_target(text: str) -> str:
    cleaned = text.strip()
    lowered = cleaned.lower()
    for phrase in ("open up ", "open ", "launch ", "go to ", "visit "):
        if phrase in lowered:
            index = lowered.rfind(phrase)
            cleaned = cleaned[index + len(phrase):].strip()
            break

    cleaned_lower = cleaned.lower()
    for stop_word in ("the ", "app ", "application ", "game ", "website "):
        if cleaned_lower.startswith(stop_word):
            cleaned = cleaned[len(stop_word):].strip()
            break
    return cleaned


def listen(
    recognizer: sr.Recognizer,
    microphone: sr.Microphone,
    phrase_time_limit: int,
    timeout: float | None = None,
) -> str | None:
    with microphone as source:
        audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
    try:
        return recognizer.recognize_google(audio)
    except sr.WaitTimeoutError:
        return None
    except sr.UnknownValueError:
        return None
    except sr.RequestError:
        return None


def handle_command(
    engine: pyttsx3.Engine,
    recognizer: sr.Recognizer,
    microphone: sr.Microphone,
    command: str,
    aliases: dict[str, dict[str, str]],
) -> bool:
    cleaned = command.strip().lower()
    if cleaned in {"stop", "exit", "quit", "stop listening", "close", "shut down"}:
        speak(engine, "Stopping now.")
        return False
    if cleaned in {"nevermind", "never mind", "cancel"}:
        speak(engine, "Okay.")
        return True
    target = parse_target(command)
    if not target:
        speak(engine, "I did not catch that.")
        return True
    if is_url(target):
        acknowledgment = random.choice(ACKNOWLEDGMENTS)
        speak(engine, f"{acknowledgment} Opening {target}.")
        open_website(target, aliases)
        return True
    try:
        acknowledgment = random.choice(ACKNOWLEDGMENTS)
        speak(engine, f"{acknowledgment} Opening {target}.")
        open_application(target, aliases)
        return True
    except Exception:
        speak(engine, "I couldn't find that application. Which app should I open instead?")
        correction = listen(recognizer, microphone, phrase_time_limit=6)
        if correction:
            system = platform.system().lower()
            aliases.setdefault(system, {})[normalize_alias_key(target)] = correction.strip()
            save_aliases(aliases)
            try:
                acknowledgment = random.choice(ACKNOWLEDGMENTS)
                speak(engine, f"{acknowledgment} Opening {correction}.")
                open_application(correction, aliases)
                return True
            except Exception:
                pass
        acknowledgment = random.choice(ACKNOWLEDGMENTS)
        speak(engine, f"{acknowledgment} Opening {target} on the web.")
        open_web_search(target)
    return True


def normalize_text(text: str) -> str:
    return re.sub(r"[^a-z0-9\s]", "", text.lower()).strip()


def configure_voice(engine: pyttsx3.Engine) -> None:
    voices = engine.getProperty("voices")
    engine.setProperty("volume", 1.0)
    for preferred in VOICE_PREFERENCES:
        for voice in voices:
            name = (voice.name or "").lower()
            voice_id = (voice.id or "").lower()
            if preferred.lower() in name or preferred.lower() in voice_id:
                engine.setProperty("voice", voice.id)
                engine.setProperty("rate", 185)
                return
    engine.setProperty("rate", 185)


def main() -> None:
    engine = pyttsx3.init()
    configure_voice(engine)
    recognizer = sr.Recognizer()
    microphone = sr.Microphone()
    aliases = load_aliases()

    recognizer.dynamic_energy_threshold = True
    with microphone as source:
        recognizer.adjust_for_ambient_noise(source, duration=1.0)
    while True:
        text = listen(recognizer, microphone, phrase_time_limit=4)
        if not text:
            continue
        print(f"Heard (wake): {text}")
        normalized = normalize_text(text)
        if any(wake in normalized for wake in WAKE_WORDS):
            speak(engine, PROMPT_TEXT)
            while True:
                command = listen(recognizer, microphone, phrase_time_limit=7, timeout=8)
                if not command:
                    break
                print(f"Heard (command): {command}")
                cleaned = command.strip().lower()
                normalized_command = normalize_text(command)
                if any(wake in normalized_command for wake in WAKE_WORDS):
                    speak(engine, PROMPT_TEXT)
                    continue
                if cleaned in {"nevermind", "never mind", "cancel"}:
                    speak(engine, "Okay.")
                    break
                if cleaned in {"stop", "exit", "quit", "stop listening", "close", "shut down"}:
                    should_continue = handle_command(engine, recognizer, microphone, command, aliases)
                    if not should_continue:
                        return
                    break
                if not any(
                    phrase in cleaned
                    for phrase in ("open up ", "open ", "launch ", "go to ", "visit ")
                ):
                    continue
                should_continue = handle_command(engine, recognizer, microphone, command, aliases)
                if not should_continue:
                    return
                break
            time.sleep(0.2)


if __name__ == "__main__":
    main()
