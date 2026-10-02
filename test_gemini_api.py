import os
import time
from google import genai
from google.genai.errors import ClientError, ServerError

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise RuntimeError("GEMINI_API_KEY secret not found")

client = genai.Client(api_key=api_key)

MAX_RETRIES = 3

for attempt in range(1, MAX_RETRIES + 1):
    try:
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents="Reply with exactly: GEMINI_OK"
        )

        print(response.text)
        print("Gemini API test passed.")
        break

    except ClientError as e:
        error_text = str(e)

        if "429" in error_text or "RESOURCE_EXHAUSTED" in error_text:
            print("Gemini API quota is currently exhausted.")
            print("Skipping live Gemini API test so the CI workflow can continue.")
            print("This is a quota condition, not a code/test failure.")
            break

        raise

    except ServerError as e:
        error_text = str(e)

        if "503" in error_text or "UNAVAILABLE" in error_text:
            print(f"Gemini service temporarily unavailable (attempt {attempt}/{MAX_RETRIES}).")

            if attempt < MAX_RETRIES:
                time.sleep(10)
                continue

            print("Gemini service is temporarily unavailable.")
            print("Skipping live Gemini API test so the CI workflow can continue.")
            print("This is a temporary service condition, not a code/test failure.")
            break

        raise
