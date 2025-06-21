import os
from langchain_anthropic import ChatAnthropic
from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate
from typing import List, Dict, Any
import base64

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
llm = ChatAnthropic(model="claude-3-5-sonnet-latest")

EMAIL_ANALYSIS_PROMPT = (
    "The following text is an order, cancellation, or refund email encoded in Base64 from a Shopify customer. "
    "Please check if the order ID field exists and is correct. If the email is correct, then output the necessary string formatted as JSON. "
    "The JSON string should include order_id, type (either cancel or refund), status (1 if correct, otherwise 0), and msg "
    "(a message requesting the order ID if the email is incorrect; if the email is correct, msg should be null). "
    "I need only the JSON output:\n\n"
    "{email_contents}"
)

prompt_template = PromptTemplate(
    input_variables=["email_contents"],
    template=EMAIL_ANALYSIS_PROMPT
)

async def analyze_emails_with_ai(message: Dict[str, Any]):
    """
    Args:
        message: A Message object or dict, which has a 'messages' field containing ChatEntry dicts.
    Returns:
        List of AI JSON outputs, one per entry.
    """
    # Extract and base64 encode all message contents
    entries = message.get("messages", [])
    results = []
    for entry in entries:
        content = entry.get("content", "")
        # base64 encode the email body
        encoded_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        # Prepare the prompt
        prompt = prompt_template.format(email_contents=encoded_content)
        # Call the LLM synchronously (langchain-anthropic currently does not support async)
        result = llm.invoke(prompt)
        # Just return the LLM's output (should be JSON)
        results.append({
            "entry_id": entry.get("metadata", {}).get("gmail_id"),  # or another unique key if not gmail
            "response": result.content
        })
    return results