#!/usr/bin/env python3
import openai
import os
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

if OPENROUTER_API_KEY:
    print(f"{__name__} OPENROUTER_API_KEY found!")
else:
    print(f"{__name__} driver requires environment variable OPENROUTER_API_KEY be set. Closing...")


def _make_client():
    return openai.OpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
    )


class Interpreter():
    def __init__(self):
        self.model = "openrouter/auto"           # <----------- The model you want to use (OpenRouter model string)

        self.hot_load = True                   # <----------- API-based, always True
        self.temperature = 0.7
        self.top_p = 1.0

        self.fab_driver = True                 # <----------- Paired with a Fabricator in this driver
        self.context_length = 4000             # <----------- Soft context limit hint for the caller

    def create_chat(self, input):
        self.system_messages = input
        client = _make_client()

        response = client.chat.completions.create(
            model=self.model,
            messages=self.system_messages,
            temperature=self.temperature,
            top_p=self.top_p,
            stream=False,
        )

        try:
            interpreter_response = response.choices[0].message.content
        except KeyError:
            interpreter_response = ""
        except Exception as e:
            print(e)
            exit()

        return interpreter_response


class Fabricator():
    def __init__(self):
        self.model = "openrouter/auto"           # <----------- The model you want to use (OpenRouter model string)

        self.hot_load = True                   # <----------- API-based, always True
        self.temperature = 1.0
        self.top_p = 0.4
        self.context_length = 16000            # <----------- Soft context limit hint for the caller

    def fabricate(self, input):
        self.system_messages = input
        print(f"INPUT TO FAB:\n\n{input}")
        client = _make_client()

        response = client.chat.completions.create(
            model=self.model,
            messages=self.system_messages,
            temperature=self.temperature,
            top_p=self.top_p,
            stream=False,
        )

        try:
            fabricator_response = response.choices[0].message.content
        except KeyError:
            fabricator_response = ""
        except Exception as e:
            print(e)
            exit()

        return fabricator_response


if __name__ == "__main__":
    print("Testing OpenRouter connection...")

    test_messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Reply to confirm the API is functioning."},
    ]

    interp = Interpreter()
    result = interp.create_chat(test_messages)
    print(f"Interpreter response: {result}")

    fab = Fabricator()
    result = fab.fabricate(test_messages)
    print(f"Fabricator response: {result}")
