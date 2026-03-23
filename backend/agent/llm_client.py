# backend/agent/llm_client.py
# Abstract Async Wrapper for LLM interactions.

import json
import asyncio
from typing import Dict, Any, Optional
from loguru import logger
from google import genai
from google.genai import types
import anthropic

from config.settings import settings

class AIClient:
    """
    Centralized client for interacting with LLM providers.
    Automatically formats responses into structured JSON dicts.
    """
    def __init__(self):
        self.provider = settings.default_ai_model.value
        self.gemini_client = None
        self.anthropic_client = None
        
        if "gemini" in self.provider.lower():
            if not settings.gemini_api_key:
                logger.warning("Gemini API key not found. LLM calls will fail.")
            else:
                self.gemini_client = genai.Client(api_key=settings.gemini_api_key.get_secret_value())
                self.model_name = "gemini-flash-latest" # Use working flash model
        elif "claude" in self.provider.lower():
            if not settings.anthropic_api_key:
                logger.warning("Anthropic API key not found. LLM calls will fail.")
            else:
                self.anthropic_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key.get_secret_value())
                self.model_name = "claude-3-5-sonnet-20241022"

    async def analyze_market(self, system_prompt: str, user_prompt: str) -> Optional[Dict[str, Any]]:
        """
        Sends the market context to the configured LLM and enforces a JSON return.
        """
        try:
            if self.gemini_client:
                return await self._call_gemini(system_prompt, user_prompt)
            elif self.anthropic_client:
                return await self._call_anthropic(system_prompt, user_prompt)
            else:
                logger.error("No LLM clients initialized.")
                return None
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            return None

    async def _call_gemini(self, system_prompt: str, user_prompt: str) -> Optional[Dict[str, Any]]:
        # google-genai client wrapper
        # The gemini client's generate_content doesn't have an async version in standard genai yet without specific async client, 
        # so we'll wrap the sync call in asyncio.to_thread to prevent blocking the event loop.
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.1,  # Low temperature for deterministic trading rules
            response_mime_type="application/json",
        )
        
        def _sync_call():
            return self.gemini_client.models.generate_content(
                model=self.model_name,
                contents=user_prompt,
                config=config,
            )
            
        response = await asyncio.to_thread(_sync_call)
        
        if not response.text:
            return None
            
        try:
            # Clean up potential markdown formatting
            text = response.text.strip()
            if text.startswith("```json"):
                text = text.replace("```json", "", 1)
            if text.endswith("```"):
                text = text.rsplit("```", 1)[0]
            text = text.strip()

            # Extract the JSON object robustly using brace matching
            # This handles cases where LLM adds trailing braces or extra text
            start = text.find("{")
            if start == -1:
                logger.error("No JSON object found in Gemini response")
                return None
            
            depth = 0
            end = start
            for i, ch in enumerate(text[start:], start):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            
            json_str = text[start:end + 1]
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini JSON: {e}\nRaw output: {response.text}")
            return None


    async def _call_anthropic(self, system_prompt: str, user_prompt: str) -> Optional[Dict[str, Any]]:
        response = await self.anthropic_client.messages.create(
            model=self.model_name,
            max_tokens=1000,
            temperature=0.1,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": user_prompt + "\n\nProvide ONLY valid JSON output."
                }
            ]
        )
        
        text = response.content[0].text
        try:
            # Clean up potential markdown formatting
            text = text.strip()
            if text.startswith("```json"):
                text = text.replace("```json", "", 1)
            if text.endswith("```"):
                text = text.rsplit("```", 1)[0]
                
            return json.loads(text.strip())
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Claude JSON: {e}\nRaw output: {text}")
            return None
