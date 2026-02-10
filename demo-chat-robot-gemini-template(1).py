from autobahn.twisted.component import Component, run
from twisted.internet.defer import inlineCallbacks
from autobahn.twisted.util import sleep
from google import genai
from google.genai import types
from alpha_mini_rug.speech_to_text import SpeechToText
from alpha_mini_rug import smart_questions
import os
import numpy as np

# Setting the API KEY
chatbot = genai.Client()

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
- If your guess is incorrect, ask the user for another clue. Never start guesseing without being given another clue from the user.

After the end of the round, congratulate the user and do not ask to play another round. 
In your congratulation ALWAYS include the exact statement "Good job!".

You respond in a very brief, conversational, approachable and friendly style.
Don’t focus on long explanations, focus on natural spoken interaction.

Limit your answers to three sentences.
Use short spoken sentences suitable for a robot voice.

BLOCK 3: ADDITIONAL INSTRUCTIONS

If the conversation slows down, suggest continuing the game or starting a new word.
Always keep the interaction playful, clear and easy to follow.
"""

chat = chatbot.chats.create(
    model="gemini-2.5-flash-lite",
    config=types.GenerateContentConfig(system_instruction=SYSTEM_STYLE),
)
# You should configure a system_instruction somewhere here...

# Setting up google speech to text
audio_processor = SpeechToText()

# Set up parameters for STT
audio_processor.silence_time = 1
audio_processor.silence_threshold2 = 200
audio_processor.logging = False


@inlineCallbacks
def single_game_WOW(session, role):

    print("starting game")

    response = chat.send_message(f"I want to play as a {role}")

    yield session.call("rie.dialogue.say", text=response.text)

    yield session.subscribe(
        audio_processor.listen_continues, "rom.sensor.hearing.stream"
    )
    yield session.call("rom.sensor.hearing.stream")

    print("starting loop")

    while True:
        if not audio_processor.new_words:
            yield sleep(0.5)
            print("recording")
        else:
            words = audio_processor.give_me_words()
            query = words[-1][0]  # change to pass more info to google AI
            print(query)
            # Talk to the chatbot
            response = chat.send_message(query)
            print(response.text)
            audio_processor.do_speech = False
            yield session.call("rie.dialogue.say", text=response.text)
            audio_processor.do_speech = True
            if "Good job!" in (response.text or ""):
                break
        audio_processor.loop()
    yield session.call("rom.sensor.hearing.close")


@inlineCallbacks
def main(session, details):

    # Setup language
    yield session.call("rie.dialogue.config.language", lang="en")

    yield session.call("rom.optional.behavior.play", name="BlocklyStand")

    # Describe the game and rules
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
            "no": ["no", "never", "nah"],
        }
        answer = yield smart_questions(
            session,
            question="That was fun. Do you want to play another round?",
            answer_dictionary=possible_choices,
        )
        if answer != "yes":
            break

            # Describe the game and rules
        yield session.call("rie.dialogue.say", text="Gooood boy.")

    yield session.call(
        "rie.dialogue.say", text="Alright! It was delightful. See ya big dawg."
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
    realm="rie.698b2514946951d690d12eb3",
)

wamp.on_join(main)

if __name__ == "__main__":
    run([wamp])
