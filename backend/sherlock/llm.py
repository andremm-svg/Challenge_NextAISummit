"""Client Featherless (API compatibil OpenAI)."""
import os
import re

from dotenv import load_dotenv

load_dotenv()


def _strip_think(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()


class FeatherlessLLM:
    def __init__(self, model: str | None = None):
        from openai import OpenAI

        key = os.getenv("FEATHERLESS_API_KEY")
        if not key:
            raise RuntimeError("Lipseste FEATHERLESS_API_KEY in .env")
        self.client = OpenAI(base_url=os.getenv("FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1"), api_key=key, timeout=90)
        self.model = model or os.getenv("FEATHERLESS_MODEL", "Qwen/Qwen3-32B")
        self.native_tools = os.getenv("FEATHERLESS_NATIVE_TOOLS", "1") == "1"

    def complete(self, prompt: str, max_tokens: int = 600) -> str:
        r = self.client.chat.completions.create(
            model=self.model, temperature=0, max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return _strip_think(r.choices[0].message.content)

    def chat(self, messages: list, tools: list | None = None, max_tokens: int = 700):
        kwargs = dict(model=self.model, temperature=0, max_tokens=max_tokens, messages=messages)
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        r = self.client.chat.completions.create(**kwargs)
        return r.choices[0].message


def get_llm():
    """Returneaza clientul LLM sau None daca nu e configurat (modul offline)."""
    try:
        return FeatherlessLLM()
    except Exception:  # noqa: BLE001
        return None
