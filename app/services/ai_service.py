import os
from langchain_anthropic import ChatAnthropic
from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import List
import requests

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
llm = ChatAnthropic(model="claude-3-7-sonnet-20250219")

async def analyze_emails_with_ai(prompt: str, emails: List[str] = None):
    # Pull LangChain readme
    get_response = requests.get(
        "https://raw.githubusercontent.com/langchain-ai/langchain/master/README.md"
    )
    readme = get_response.text

    messages = [
        {
            "role": "system",
            "content": [
                {
                    "type": "text",
                    "text": "You are a technology expert.",
                },
                {
                    "type": "text",
                    "text": f"{readme}",
                    "cache_control": {"type": "ephemeral"},
                },
            ],
        },
        {
            "role": "user",
            "content": "What's LangChain, according to its README?",
        },
    ]

    response_1 = llm.invoke(messages)
    response_2 = llm.invoke(messages)

    usage_1 = response_1.usage_metadata["input_token_details"]
    usage_2 = response_2.usage_metadata["input_token_details"]

    print(f"First invocation:\n{usage_1}")
    print(f"\nSecond:\n{usage_2}")
    return "OK"