"""Clientii LLM. Doi furnizori, aceeasi interfata:

  - featherless : API compatibil OpenAI (sponsor hackathon)
  - bedrock     : Claude prin Amazon Bedrock (Converse API, tool use nativ)

Alegerea se face din .env cu LLM_PROVIDER=featherless | bedrock.
Ambii expun complete(prompt) si chat(messages, tools), cu mesaje si unelte in format OpenAI,
ca agentul sa nu depinda de furnizor.
"""
import json
import os
import re
from types import SimpleNamespace

from dotenv import load_dotenv

load_dotenv()


def _strip_think(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()


class FeatherlessLLM:
    provider = "featherless"

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


class BedrockLLM:
    """Claude prin Amazon Bedrock. Credentialele se citesc automat de boto3 din .env:
    AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY (+ AWS_SESSION_TOKEN daca exista) sau
    AWS_BEARER_TOKEN_BEDROCK, plus AWS_REGION."""

    provider = "bedrock"
    native_tools = True

    def __init__(self, model: str | None = None, client=None):
        self.model = model or os.getenv("BEDROCK_MODEL_ID")
        if not self.model:
            raise RuntimeError("Lipseste BEDROCK_MODEL_ID in .env")
        if client is None:
            import boto3

            region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
            if not region:
                raise RuntimeError("Lipseste AWS_REGION in .env")
            client = boto3.client("bedrock-runtime", region_name=region)
        self.client = client

    # --- conversie OpenAI -> Bedrock Converse ---
    @staticmethod
    def _convert(messages: list) -> tuple[list, list]:
        system, out = [], []

        def push(role, blocks):
            if not blocks:
                return
            if out and out[-1]["role"] == role:  # Bedrock cere alternanta user/assistant
                out[-1]["content"].extend(blocks)
            else:
                out.append({"role": role, "content": list(blocks)})

        for m in messages:
            role, content = m["role"], m.get("content") or ""
            if role == "system":
                system.append({"text": content})
            elif role == "user":
                push("user", [{"text": content}] if content else [])
            elif role == "assistant":
                blocks = [{"text": content}] if content.strip() else []
                for tc in m.get("tool_calls") or []:
                    blocks.append({"toolUse": {"toolUseId": tc["id"], "name": tc["function"]["name"],
                                               "input": json.loads(tc["function"]["arguments"] or "{}")}})
                push("assistant", blocks)
            elif role == "tool":
                push("user", [{"toolResult": {"toolUseId": m["tool_call_id"], "content": [{"text": content}]}}])
        return system, out

    @staticmethod
    def _tool_config(tools: list) -> dict:
        return {"tools": [{"toolSpec": {"name": t["function"]["name"], "description": t["function"]["description"],
                                        "inputSchema": {"json": t["function"]["parameters"]}}} for t in tools]}

    def chat(self, messages: list, tools: list | None = None, max_tokens: int = 700):
        system, msgs = self._convert(messages)
        kwargs = dict(modelId=self.model, messages=msgs, inferenceConfig={"temperature": 0, "maxTokens": max_tokens})
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["toolConfig"] = self._tool_config(tools)
        r = self.client.converse(**kwargs)
        text, calls = [], []
        for block in r["output"]["message"]["content"]:
            if "text" in block:
                text.append(block["text"])
            elif "toolUse" in block:
                tu = block["toolUse"]
                calls.append(SimpleNamespace(id=tu["toolUseId"], function=SimpleNamespace(
                    name=tu["name"], arguments=json.dumps(tu.get("input") or {}, ensure_ascii=False))))
        return SimpleNamespace(content="\n".join(text), tool_calls=calls or None)

    def complete(self, prompt: str, max_tokens: int = 600) -> str:
        return self.chat([{"role": "user", "content": prompt}], max_tokens=max_tokens).content


def get_llm():
    """Returneaza clientul LLM ales in .env sau None daca nu e configurat (modul offline)."""
    provider = os.getenv("LLM_PROVIDER", "featherless").lower()
    try:
        return BedrockLLM() if provider == "bedrock" else FeatherlessLLM()
    except Exception as e:  # noqa: BLE001
        print(f"[Sherlock] LLM indisponibil ({provider}): {e}. Rulez offline.")
        return None
