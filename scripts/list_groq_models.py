"""Print the chat models currently active on your Groq account."""
import os

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

client = Groq(api_key=os.environ["GROQ_API_KEY"])
models = sorted(client.models.list().data, key=lambda m: m.id)

print(f"{'MODEL ID':<50} {'CONTEXT':>8}  OWNER")
for m in models:
    print(f"{m.id:<50} {str(getattr(m, 'context_window', '?')):>8}  {m.owned_by}")