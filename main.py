from autobahn.twisted.component import Component, run
from twisted.internet.defer import inlineCallbacks
from twisted.internet.task import LoopingCall
from autobahn.twisted.util import sleep
from google import genai
from google.genai import types
from alpha_mini_rug.speech_to_text import SpeechToText
from alpha_mini_rug import perform_movement, smart_questions
import random

# Define realm
realm = "rie.698d8f61946951d690d13aef"

# Setting the API KEY
chatbot = genai.Client(api_key="AIzaSyCHrjhm32nTd_o5Z5QoF532Irk3yiQpC6s")

# Define a system prompt passed to the LLM
SYSTEM_STYLE = """
BLOCK 1: CONTEXT

Your name is ALphaMini and you are a social robot that plays a single round of a verbal game
“With Other Words (Taboo)” with the user to help them learn english.

Your task is to maintain a natural spoken conversation while playing the game.
You must be able to take two roles: Director and Matcher.

As Director, you know a secret word and you describe it to the user without using the sepcific word or any any words that contain the given word
while guiding the user to guess it.

As Matcher, the user gives you clues and you try to guess the secret word through
short interactive dialogue.

The interaction should feel like a friendly robot conversation, focused on fun,
engagement and natural verbal exchange rather than technical explanations.


BLOCK 2: MAIN INSTRUCTIONS

The user starts by giving you a role they want to play in this round. During this round you will play the other role.

After the user's response you aknowledge the user's choice and start the round with your role.

If you are the Director:
- Describe the secret word using progressive hints (general to specific).
- Never say the secret word, any similiar words, or words that contain the secret words.
- Encourage the user to guess.

If you are the Matcher:
- Always make exactly one guess based on the user’s clues.
- Wait for the user to answer and tell you if your guess was correct
- If your guess is incorrect, ask the user for another clue. Never start guesseing without being given another clue from the user.

After the end of the round, congratulate the user and do not ask to play another round. 
In your congratulation ALWAYS include the exact statement "Nice round!".

You respond in a very brief, conversational, approachable and friendly style.
Don’t focus on long explanations, focus on natural spoken interaction.

Limit your answers to three sentences.
Use short spoken sentences suitable for a robot voice.

BLOCK 3: ADDITIONAL INSTRUCTIONS

If the conversation slows down, suggest continuing the game or starting a new word.
Always keep the interaction playful, clear and easy to follow.
"""

# Create a chat interface with a LLM model
chat = chatbot.chats.create(
    model="gemini-2.5-flash",
    config=types.GenerateContentConfig(system_instruction=SYSTEM_STYLE),
)

# Setting up google speech to text
audio_processor = SpeechToText()

# Set up parameters for STT
audio_processor.silence_time = 1
audio_processor.silence_threshold2 = 200
audio_processor.logging = False


@inlineCallbacks
def breathe(session):
    """Make the robot breathe using a periodic movement to make the robot seem alive.

    Args:
        sessions (ApplicationSession) : active WAMP session to communicate with the robot backend
    """
    try:
        # small random offsets (radians)
        a = random.uniform(-0.1, -0.04)

        # Define the breathing motion
        frames = [
            {"time": 600, "data": {"body.head.pitch": a}},
            {"time": 1600, "data": {"body.head.pitch": 0.01}},
        ]

        # Fire-and-forget (sync=False) so it doesn't block dialogue.
        # Used perform_movement to not damage the robot
        yield perform_movement(
            session=session,
            frames=frames,
            mode="linear",
            sync=False,
            force=True,
        )
    except Exception as e:
        print(f"error breathing is :{e}")


@inlineCallbacks
def arm_movement(session):
    """Make the robot move its arm using a periodic movement to make the robot seem alive.

    Args:
        sessions (ApplicationSession) : active WAMP session to communicate with the robot backend
    """
    # small random offsets (radians)
    try:
        a = random.uniform(-0.6, -0.1)

        # Define the breathing motion
        frames = [
            {
                "time": 800,
                "data": {
                    "body.arms.left.lower.roll": a,
                    "body.arms.right.lower.roll": a,
                },
            },
            {
                "time": 1200,
                "data": {
                    "body.arms.left.lower.roll": -0.01,
                    "body.arms.right.lower.roll": -0.01,
                },
            },
        ]

        # Fire-and-forget (sync=False) so it doesn't block dialogue.
        # Used perform_movement to not damage the robot
        yield perform_movement(
            session=session,
            frames=frames,
            mode="linear",
            sync=True,
            force=True,
        )
    except Exception as e:
        print(f"error is {e}")


@inlineCallbacks
def single_game_WOW(session, role):
    """Play a single round of WOW game using google speech to text and a configured LLM interface.

    Args:
        sessions (ApplicationSession) : active WAMP session to communicate with the robot backend
        role (string) : the user's role in this game round
    """

    print("starting game")

    # Pass the initial role of the user to the chatbot
    response = chat.send_message(f"I want to play as a {role}")

    # Say the response starting the round
    yield session.call("rie.dialogue.say", text=response.text)

    # Start STT stream
    yield session.subscribe(
        audio_processor.listen_continues, "rom.sensor.hearing.stream"
    )
    yield session.call("rom.sensor.hearing.stream")

    audio_processor.do_speech = True

    print(audio_processor.do_speech, audio_processor.new_words)

    print("starting loop")

    # While loop to detect speech and repeatedly communicate with the LLM chatbot
    while True:
        # If the STT did not detect any new words, wait a bit to not crash the server and continue recording
        if not audio_processor.new_words:
            yield sleep(0.2)
            print("recording")
        # If there are new words, process them
        else:
            print("processing words")
            # Get the new words from the STT processor
            words = audio_processor.give_me_words()
            query = words[-1][0]  # change to pass more info to google AI
            print(query)
            # Send the detected speech to the chatbot
            response = chat.send_message(query)
            print(response.text)
            # Turn the microphone off
            audio_processor.do_speech = False
            # TTS the responce from  the LLM chatbot
            yield session.call("rie.dialogue.say", text=response.text)
            # Turn the microphone on
            audio_processor.do_speech = True
            # Detect end of round and exit the loop
            if "Nice round!" in (response.text or ""):
                break
        audio_processor.loop()
    # Turn the microphone and stream off to not register answers to smart questions
    audio_processor.do_speech = False
    yield session.call("rom.sensor.hearing.close")


@inlineCallbacks
def main(session, details):

    # Setup the robot
    yield session.call("rie.dialogue.config.language", lang="en")

    yield session.call("rom.optional.behavior.play", name="BlocklyStand")

    # Start breathing movement loop (every ~3 seconds)
    breathing_loop = LoopingCall(breathe, session)
    breathing_loop.start(3.0, now=False)

    arm_movement_loop = LoopingCall(arm_movement, session)
    arm_movement_loop.start(2.0, now=False)

    # Describe the game and rules
    yield session.call(
        "rie.dialogue.say",
        text="Hello! let's play the with other words game! In this game, there are two roles "
        "the matcher and the director. the matcher has to guess the word that the director describes. "
        "remember that the director is not allowed to use the word that is supposed to be guessed in their descriptions",
    )

    # Loop rounds until the user does not want to play again
    while True:
        # Ask for a role
        possible_roles = {
            "matcher": [
                "matcher",
                "match",
                "matcha",
                "mature",
                "masher",
                "matches",
            ],
            "director": ["director", "direct"],
        }
        role = yield smart_questions(
            session,
            question="Do you want to play as a matcher or as a director?",
            answer_dictionary=possible_roles,
        )

        # Can not understand = exit game
        if role == None:
            yield session.call(
                "rie.dialogue.say",
                text="I can not understand you. Please try running the game again.",
            )
            break

        # Start a game with a given role
        yield single_game_WOW(session, role)

        # Ask to play next round
        possible_choices = {
            "yes": ["yes", "yea", "sure", "absolutely", "okay"],
            "no": ["no"],
        }
        answer = yield smart_questions(
            session,
            question="That was fun. Do you want to play another round?",
            answer_dictionary=possible_choices,
        )
        if answer == "no":
            break

        # Utterance about next round
        yield session.call("rie.dialogue.say", text="Great! Let's play then.")

    yield session.call(
        "rie.dialogue.say", text="Alright! It was delightful. Goodbye."
    )

    # before leaving the program, we need to close the STT stream
    yield session.call("rom.sensor.hearing.close")
    # and let the robot crouch
    # THIS IS IMPORTANT, as this will turn of the robot's motors and prevent them from overheating
    # Always and your program with this
    yield session.call("rom.optional.behavior.play", name="BlocklyCrouch")
    session.leave()


wamp = Component(
    transports=[
        {
            "url": "ws://wamp.robotsindeklas.nl",
            "serializers": ["msgpack"],
            "max_retries": 0,
        }
    ],
    realm=realm,
)

wamp.on_join(main)

if __name__ == "__main__":
    run([wamp])
