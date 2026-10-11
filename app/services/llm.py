import time
import asyncio
from app.core.config import settings
from app.core.logger import logger

# Provider-agnostic imports
try:
    import openai
except ImportError:
    openai = None

try:
    import google.generativeai as genai
except ImportError:
    genai = None


# Persistent client pool to reuse TCP/TLS connections
_client_pool: dict = {}

def _get_pooled_client(api_key: str, base_url: str, timeout: float = 12.0):
    cache_key = f"{api_key}:{base_url}"
    if cache_key not in _client_pool:
        _client_pool[cache_key] = openai.AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout
        )
    return _client_pool[cache_key]

class LLMService:
    def __init__(self):
        # Priority: NVIDIA NIM / OpenAI > Qubrid > Gemini
        api_key = getattr(settings, "NVIDIA_API_KEY", None) or getattr(settings, "OPENAI_API_KEY", None)
        if api_key:
            if openai is None:
                raise ImportError("openai package is required for NVIDIA / OpenAI API usage.")
            base_url = getattr(settings, "OPENAI_BASE_URL", "https://integrate.api.nvidia.com/v1")
            self.client = openai.AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=30.0
            )
            self.provider = "openai"
            self.model_name = getattr(settings, "MODEL_NAME", getattr(settings, "OPENAI_MODEL_NAME", "nvidia/nemotron-3-super-120b-a12b"))
            logger.info(f"LLM Service initialized with provider: {self.provider} (endpoint: {base_url}), model: {self.model_name}")
        elif getattr(settings, "QUBRID_API_KEY", None):
            if openai is None:
                raise ImportError("openai package is required for Qubrid API usage.")
            self.client = openai.AsyncOpenAI(
                api_key=settings.QUBRID_API_KEY,
                base_url=settings.QUBRID_BASE_URL,
                timeout=60.0
            )
            self.provider = "qubrid"
            self.model_name = getattr(settings, "QUBRID_MODEL_NAME", "meta-llama/Llama-3.3-70B-Instruct")
            logger.info(f"LLM Service initialized with Qubrid provider, model: {self.model_name}")
        elif getattr(settings, "GEMINI_API_KEY", None):
            if genai is None:
                raise ImportError("google-generativeai package is required for GEMINI_API_KEY usage.")
            genai.configure(api_key=settings.GEMINI_API_KEY)
            self.provider = "gemini"
            self.model_name = getattr(settings, "GEMINI_MODEL_NAME", "gemini-2.5-flash-lite")
            safety_settings = [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ]
            self.model = genai.GenerativeModel(
                model_name=self.model_name,
                safety_settings=safety_settings
            )
            logger.info(f"LLM Service initialized with Gemini provider, model: {self.model_name}")
        else:
            logger.warning("No external LLM API key configured in settings. System will use local custom models.")
            self.provider = None
            self.model = None
            self.model_name = "local_custom_models"

    async def _call_openai_compatible(self, prompt: str, model_override: str = None) -> str:
        """Call OpenAI-compatible ChatCompletion (works for OpenAI, Ollama, Qubrid, etc.)."""
        model = model_override or self.model_name
        tokens = 1024 if "nemotron" in model.lower() else 400
        response = await self.client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=tokens,
            stream=False,
        )
        msg = response.choices[0].message
        content = msg.content
        if not content and hasattr(msg, "reasoning_content") and msg.reasoning_content:
            content = msg.reasoning_content
        return content or ""

    async def generate_response(self, prompt: str, model_name: str = None) -> str:
        if not self.provider:
            logger.error("LLM Service not configured (no API key found).")
            return "LLM Service not configured."

        selected_model = model_name or self.model_name
        logger.info(f"LLM [{self.provider}] using model [{selected_model}] generating response...")
        
        # Retry logic for rate-limit (429/503) – up to 2 attempts
        attempts = 0
        while attempts < 2:
            try:
                if self.provider in ("openai", "qubrid"):
                    res = await self._call_openai_compatible(prompt, model_override=selected_model)
                else:  # gemini
                    model_to_use = self.model
                    if model_name:
                        model_to_use = genai.GenerativeModel(
                            model_name=model_name,
                            safety_settings=[
                                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                            ]
                        )
                    
                    response = model_to_use.generate_content(prompt)
                    
                    if not response.candidates or response.candidates[0].finish_reason != 1:
                        if response.candidates and response.candidates[0].finish_reason == 3:
                            logger.warning(f"LLM response blocked by safety filters for model {selected_model}.")
                            return "Error: Response blocked by safety filters."
                        
                    res = response.text
                
                logger.info(f"LLM response received from [{selected_model}]. Snippet: {res[:50]}...")
                return res
            except Exception as e:
                err_msg = str(e).lower()
                if "429" in err_msg or "rate limit" in err_msg or "quota" in err_msg or "503" in err_msg or "resourceexhausted" in err_msg or "limit reached" in err_msg:
                    attempts += 1
                    wait = 2 ** attempts
                    logger.warning(f"LLM rate limit / resource exhaustion encountered, retrying in {wait}s (attempt {attempts})")
                    await asyncio.sleep(wait)
                    continue
                logger.error(f"LLM Error: {str(e)}")
                return f"Error generating response: {str(e)}"
        logger.error("LLM service rate limit exceeded after multiple retries.")
        return "Error: LLM service rate limit exceeded after multiple retries."

    async def generate_response_for_provider(
        self,
        prompt: str,
        provider: str = "nvidia",
        model_name: str = None,
        api_key: str = None,
        base_url: str = None,
        temperature: float = 0.0,
        max_tokens: int = 400,
        stop: list = None,
        system_prompt: str = None
    ) -> str:
        """
        Dynamically dispatches LLM calls for specific providers (local, nvidia, chatgpt, qubrid, gemini).
        Supports per-request API key injection (e.g. user-entered ChatGPT key) and system prompts.
        """
        prov = str(provider or "nvidia").lower().strip()
        if prov == "local":
            return "Local model handles query via rule engine."

        if openai is None and prov in ("nvidia", "chatgpt", "openai", "qubrid"):
            raise ImportError("openai package is required for OpenAI-compatible providers.")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # 1. NVIDIA NIM Provider
        if prov == "nvidia":
            key = api_key or getattr(settings, "NVIDIA_API_KEY", None) or getattr(settings, "OPENAI_API_KEY", None)
            if not key:
                logger.error("NVIDIA API Key not provided and not set in .env")
                return "Error: NVIDIA API Key is missing. Please configure NVIDIA_API_KEY in .env."
            url = base_url or getattr(settings, "OPENAI_BASE_URL", "https://integrate.api.nvidia.com/v1")
            model = model_name or getattr(settings, "MODEL_NAME", "nvidia/nemotron-3-super-120b-a12b")
            
            client = _get_pooled_client(api_key=key, base_url=url, timeout=25.0)
            logger.info(f"Dispatching query to NVIDIA NIM model: {model} at {url}")
            eff_max_tokens = max(max_tokens, 1024) if "nemotron" in model.lower() else max_tokens
            kwargs = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": eff_max_tokens,
                "stream": False
            }
            if stop:
                kwargs["stop"] = stop
            response = await client.chat.completions.create(**kwargs)
            msg = response.choices[0].message
            content = msg.content
            if not content and hasattr(msg, "reasoning_content") and msg.reasoning_content:
                content = msg.reasoning_content
            return content or ""

        # 2. ChatGPT / OpenAI Provider
        elif prov in ("chatgpt", "openai"):
            key = api_key or getattr(settings, "OPENAI_API_KEY", None)
            if not key:
                logger.warning("OpenAI API Key not provided for ChatGPT provider.")
                return "Error: ChatGPT / OpenAI API key is missing. Please sign in via the ChatGPT Auth modal."
            url = base_url or "https://api.openai.com/v1"
            model = model_name or "gpt-4o"

            client = _get_pooled_client(api_key=key, base_url=url, timeout=18.0)
            logger.info(f"Dispatching query to ChatGPT/OpenAI model: {model}")
            kwargs = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False
            }
            if stop:
                kwargs["stop"] = stop
            response = await client.chat.completions.create(**kwargs)
            return response.choices[0].message.content

        # 3. Qubrid Provider
        elif prov == "qubrid":
            key = api_key or getattr(settings, "QUBRID_API_KEY", None)
            if not key:
                return "Error: Qubrid API Key is missing."
            url = base_url or getattr(settings, "QUBRID_BASE_URL", "https://platform.qubrid.com/api/v1/qubridai")
            model = model_name or getattr(settings, "QUBRID_MODEL_NAME", "meta-llama/Llama-3.3-70B-Instruct")
            client = openai.AsyncOpenAI(api_key=key, base_url=url, timeout=60.0)
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=False
            )
            return response.choices[0].message.content

        # 4. Gemini Provider
        elif prov == "gemini":
            key = api_key or getattr(settings, "GEMINI_API_KEY", None)
            if not key or genai is None:
                return "Error: Google Gemini not configured."
            genai.configure(api_key=key)
            model = genai.GenerativeModel(model_name=model_name or settings.GEMINI_MODEL_NAME)
            full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
            resp = model.generate_content(full_prompt)
            return resp.text

        else:
            # Fallback to default generate_response
            return await self.generate_response(prompt, model_name=model_name)

    async def verify_chatgpt_credentials(self, api_key: str, model_name: str = "gpt-4o") -> dict:
        """Test and verify OpenAI credentials."""
        if not api_key:
            return {"success": False, "error": "API Key is required."}
        try:
            client = openai.AsyncOpenAI(api_key=api_key, base_url="https://api.openai.com/v1", timeout=15.0)
            # Lightweight verification ping
            response = await client.chat.completions.create(
                model=model_name or "gpt-4o",
                messages=[{"role": "user", "content": "Ping"}],
                max_tokens=5
            )
            return {
                "success": True,
                "model": model_name or "gpt-4o",
                "message": "Connected to OpenAI ChatGPT successfully."
            }
        except Exception as e:
            logger.error(f"ChatGPT auth verification failed: {e}")
            return {"success": False, "error": str(e)}

    async def verify_nvidia_credentials(self, api_key: str = None, model_name: str = None) -> dict:
        """Test and verify NVIDIA NIM credentials."""
        key = api_key or getattr(settings, "NVIDIA_API_KEY", None)
        if not key:
            return {"success": False, "error": "NVIDIA API Key not found."}
        model = model_name or getattr(settings, "MODEL_NAME", "nvidia/nemotron-3-super-120b-a12b")
        try:
            client = openai.AsyncOpenAI(api_key=key, base_url="https://integrate.api.nvidia.com/v1", timeout=20.0)
            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Ping"}],
                max_tokens=50
            )
            return {
                "success": True,
                "model": model,
                "message": "Connected to NVIDIA NIM successfully."
            }
        except Exception as e:
            logger.error(f"NVIDIA auth verification failed: {e}")
            return {"success": False, "error": str(e)}

llm_service = LLMService()


def get_langchain_llm(temperature: float = 0.7, model_name: str = None):
    selected_model = model_name or getattr(settings, "MODEL_NAME", getattr(settings, "OPENAI_MODEL_NAME", "nvidia/nemotron-3-super-120b-a12b"))
    api_key = getattr(settings, "NVIDIA_API_KEY", None) or getattr(settings, "OPENAI_API_KEY", None)
    if api_key:
        from langchain_openai import ChatOpenAI
        kwargs = {
            "model": selected_model,
            "api_key": api_key,
            "temperature": temperature,
        }
        if settings.OPENAI_BASE_URL:
            kwargs["base_url"] = settings.OPENAI_BASE_URL
        return ChatOpenAI(**kwargs)
    elif getattr(settings, "GEMINI_API_KEY", None):
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=settings.GEMINI_MODEL_NAME,
            google_api_key=settings.GEMINI_API_KEY,
            temperature=temperature,
        )
    else:
        from langchain_openai import ChatOpenAI
        kwargs = {
            "model": selected_model,
            "api_key": settings.OPENAI_API_KEY or "dummy",
            "temperature": temperature,
        }
        if settings.OPENAI_BASE_URL:
            kwargs["base_url"] = settings.OPENAI_BASE_URL
        return ChatOpenAI(**kwargs)

