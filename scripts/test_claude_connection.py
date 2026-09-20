"""Phase 5: Confirm the Claude API key works and see the response shape we'll use later."""

import os

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-sonnet-5"

api_key = os.environ.get("ANTHROPIC_API_KEY")
if not api_key:
    raise SystemExit(
        "ANTHROPIC_API_KEY not found. Copy .env.example to .env and add your key."
    )

client = Anthropic(api_key=api_key)

response = client.messages.create(
    model=MODEL,
    max_tokens=100,
    messages=[
        {"role": "user", "content": "In one short sentence, what is a title order in real estate?"}
    ],
)

print("--- Response text ---")
print(response.content[0].text)

print("\n--- Usage (this is what Phase 11's observability panel will show) ---")
print(f"model: {response.model}")
print(f"input_tokens: {response.usage.input_tokens}")
print(f"output_tokens: {response.usage.output_tokens}")
