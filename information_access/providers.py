"""Small native REST adapters. No tools, caching, SDK retries, or shared chats."""

from dataclasses import dataclass
import json
import os
import re
import urllib.error
import urllib.request


class ProviderError(RuntimeError):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.http_status = status


def post_json(url, body, headers, timeout):
    request = urllib.request.Request(url, json.dumps(body).encode(),
        {"Content-Type": "application/json", **headers}, method="POST")
    # urllib does not automatically retry POSTs. Never log headers or API keys.
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        raise ProviderError(f"Provider HTTP {exc.code}", exc.code) from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise ProviderError(f"Transport or JSON failure: {type(exc).__name__}") from None


def parse_choice(text):
    """Read one terminal JSON answer, optionally after unstructured explanation.

    The answer must start on its own line. Other JSON fragments, extra fields,
    duplicate keys and trailing prose remain invalid. Never consult the gold.
    """
    text = text.strip()
    start = re.search(r"(?m)^[ \t]*(?=\{|```)", text)
    if start is None or any(marker in text[:start.start()] for marker in ("{", "}", "```")):
        return None
    text = text[start.start():].strip()
    fence = re.fullmatch(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()

    def unique(pairs):
        result = {}
        for key, val in pairs:
            if key in result:
                raise ValueError("Duplicate key")
            result[key] = val
        return result

    try:
        result = json.loads(text, object_pairs_hook=unique)
    except (ValueError, TypeError):
        return None
    if (isinstance(result, dict) and set(result) == {"choice"}
            and result["choice"] in ("X", "Y")):
        return result["choice"]
    return None


def token_int(value):
    return value if type(value) is int and value >= 0 else None


@dataclass
class Result:
    status: str
    choice: str | None
    text: str
    stop: str | None
    input_tokens: int | None
    output_tokens: int | None
    raw: dict


def _decode(provider, raw):
    inp = out = None
    if provider == "anthropic":
        stop = raw.get("stop_reason")
        text = "".join(b.get("text", "") for b in raw.get("content", []) if b.get("type") == "text")
        usage = raw.get("usage", {})
        inp, out = token_int(usage.get("input_tokens")), token_int(usage.get("output_tokens"))
        # No cache creation was requested; include unexpected cache usage conservatively.
        if inp is not None:
            inp += sum(token_int(usage.get(k, 0)) or 0 for k in
                       ("cache_creation_input_tokens", "cache_read_input_tokens"))
        status = "valid" if stop == "end_turn" else "incomplete_response"
        if stop == "max_tokens":
            status = "truncated"
        elif stop == "refusal":
            status = "blocked"
    elif provider == "gemini":
        candidates = raw.get("candidates", [])
        candidate = candidates[0] if len(candidates) == 1 else {}
        stop = candidate.get("finishReason")
        text = "".join(p.get("text", "") for p in candidate.get("content", {}).get("parts", [])
                       if not p.get("thought", False))
        usage = raw.get("usageMetadata", {})
        inp = token_int(usage.get("promptTokenCount"))
        # totalTokenCount includes hidden reasoning; using total-input prevents omission.
        total = token_int(usage.get("totalTokenCount"))
        if total is not None and inp is not None and total >= inp:
            out = total - inp
            listed = (token_int(usage.get("candidatesTokenCount")) or 0) + (token_int(usage.get("thoughtsTokenCount")) or 0)
            out = max(out, listed)
        status = "valid" if stop == "STOP" else "incomplete_response"
        if stop == "MAX_TOKENS":
            status = "truncated"
        elif stop in ("SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII") or raw.get("promptFeedback", {}).get("blockReason"):
            status = "blocked"
    else:
        raise ValueError("Unsupported provider")
    choice = parse_choice(text) if status == "valid" else None
    if status == "valid" and choice is None:
        status = "invalid_format"
    return Result(status, choice, text, stop, inp, out, raw)


def decode(provider, raw):
    if provider not in ("anthropic", "gemini"):
        raise ValueError("Unsupported provider")
    try:
        return _decode(provider, raw)
    except (AttributeError, TypeError, KeyError):
        # Preserve unexpected provider payloads for inspection, never infer an answer.
        return Result("malformed_response", None, "", None, None, None, raw)


class NativeProvider:
    def __init__(self, model, config, transport=post_json):
        self.model, self.config, self.transport = model, config, transport
        provider = model["provider"]
        key_name = {"anthropic": "ANTHROPIC_API_KEY", "gemini": "GEMINI_API_KEY"}[provider]
        key = os.environ.get(key_name)
        if not key:
            raise ValueError(f"Set {key_name} before a paid run")
        self.headers = ({"x-api-key": key, "anthropic-version": "2023-06-01"}
                        if provider == "anthropic" else {"x-goog-api-key": key})
        self.base = ("https://api.anthropic.com/v1/messages" if provider == "anthropic" else
                     f"https://generativelanguage.googleapis.com/v1beta/models/{model['model']}")

    def body(self, prompt, count=False):
        if self.model["provider"] == "anthropic":
            body = {"model": self.model["model"], "messages": [{"role": "user", "content": prompt}]}
            if not count:
                body.update(max_tokens=self.config["max_output_tokens"], thinking={"type": "adaptive"},
                            output_config={"effort": self.model["effort"]})
        else:
            body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
            if not count:
                body["generationConfig"] = {"maxOutputTokens": self.config["max_output_tokens"],
                                           "thinkingConfig": {"thinkingLevel": self.model["effort"]}}
        return body

    def count(self, prompt):
        anthropic = self.model["provider"] == "anthropic"
        suffix = "/count_tokens" if anthropic else ":countTokens"
        raw = self.transport(self.base + suffix, self.body(prompt, count=True), self.headers,
                             self.config["timeout_seconds"])
        count = token_int(raw.get("input_tokens" if anthropic else "totalTokens"))
        if count is None:
            raise ProviderError("Token counter returned no valid count; no generation sent")
        return count

    def generate(self, prompt):
        suffix = "" if self.model["provider"] == "anthropic" else ":generateContent"
        raw = self.transport(self.base + suffix, self.body(prompt), self.headers,
                             self.config["timeout_seconds"])
        return decode(self.model["provider"], raw)
