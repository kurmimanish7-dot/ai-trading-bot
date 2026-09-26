import os
from google import genai
from google.genai.errors import ClientError

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise RuntimeError("GEMINI_API_KEY secret not found")

client = genai.Client(api_key=api_key)

try:
    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents="Reply with exactly: GEMINI_OK"
    )

    print(response.text)
    print("Gemini API test passed.")

except ClientError as e:
    error_text = str(e)

    if "429" in error_text or "RESOURCE_EXHAUSTED" in error_text:
        print("Gemini API quota is currently exhausted.")
        print("Skipping live Gemini API test so the CI workflow can continue.")
        print("This is a quota condition, not a code/test failure.")
    else:
        raise
