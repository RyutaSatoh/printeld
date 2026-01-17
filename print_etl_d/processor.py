import os
import time
import json
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from dotenv import load_dotenv
from loguru import logger

from print_etl_d.config import ProfileConfig, SystemConfig
from print_etl_d.schema_builder import build_json_schema

# Load environment variables
load_dotenv()

class ProcessorError(Exception):
    """Base exception for processor errors."""
    pass

class RetryableError(ProcessorError):
    """Error that warrants a retry."""
    pass

class LLMProcessor:
    def __init__(self, system_config: SystemConfig):
        self.config = system_config
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            logger.warning("GEMINI_API_KEY not found in environment variables.")

        genai.configure(api_key=api_key)

        self.model_name = system_config.gemini_model

    async def process_file(self, file_path: Path, profile: ProfileConfig) -> Dict[str, Any]:
        """
        Process a file using Gemini API to extract data based on the profile.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        logger.info(f"Processing file: {file_path} with profile: {profile.name}")

        # 1. Upload file
        uploaded_file = await self._upload_file(file_path)

        try:
            # 2. Build Schema and Configuration
            schema = build_json_schema(profile.fields)

            generation_config = {
                "temperature": 0.1,
                "response_mime_type": "application/json",
                "response_schema": schema
            }

            model = genai.GenerativeModel(
                model_name=self.model_name,
                generation_config=generation_config
            )

            # 3. Construct Prompt
            from datetime import datetime
            today = datetime.now().strftime("%Y-%m-%d")

            prompt = f"""
            You are an expert document parser.
            Today's date is {today}. 
            Please extract the following information from the provided document.
            If the year, month, or day is missing or ambiguous in the document, please infer it based on today's date ({today}).

            Context/Description: {profile.description}

            Strictly follow the JSON schema provided.
            """

            # 4. Generate Content with Retries
            result = await self._generate_with_retry(model, prompt, uploaded_file)

            return result

        finally:
            # Cleanup: Delete the file from Gemini to save storage/privacy
            # Note: File API usage usually requires cleanup.
            try:
                uploaded_file.delete()
                logger.debug(f"Deleted remote file: {uploaded_file.name}")
            except Exception as e:
                logger.warning(f"Failed to delete remote file: {e}")

    async def _upload_file(self, path: Path):
        """Uploads file to Gemini File API."""
        logger.debug(f"Uploading {path} to Gemini...")
        try:
            # The synchronous upload_file is wrapped in executor if needed, 
            # but for now we call it directly as it's an IO bound operation 
            # that we might want to offload if blocking the event loop is an issue.
            # verify path is valid
            file_ref = genai.upload_file(path)

            # Wait for processing to complete
            while file_ref.state.name == "PROCESSING":
                logger.debug("Waiting for file processing...")
                await asyncio.sleep(1)
                file_ref = genai.get_file(file_ref.name)

            if file_ref.state.name == "FAILED":
                raise ProcessorError("File processing failed on Gemini side.")

            logger.debug(f"File uploaded: {file_ref.name}")
            return file_ref

        except Exception as e:
            logger.error(f"Upload failed: {e}")
            raise ProcessorError(f"Upload failed: {e}")

    async def _generate_with_retry(self, model, prompt, content, max_retries=3) -> Dict[str, Any]:
        """Call generate_content_async with exponential backoff."""
        delay = 1.0

        for attempt in range(max_retries):
            try:
                response = await model.generate_content_async([prompt, content])

                # Check for valid JSON
                try:
                    return json.loads(response.text)
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON received on attempt {attempt+1}")
                    if attempt == max_retries - 1:
                        raise ProcessorError("Failed to parse JSON response from LLM.")
                except ValueError as ve: # response.text might fail if blocked
                    logger.warning(f"Response blocked or empty on attempt {attempt+1}: {ve}")
                    if attempt == max_retries - 1:
                        raise ProcessorError(f"LLM generation failed: {ve}")

            except Exception as e:
                logger.warning(f"Attempt {attempt+1} failed: {e}")
                if attempt == max_retries - 1:
                    raise RetryableError(f"Max retries reached: {e}")

            await asyncio.sleep(delay)
            delay *= 2  # Exponential backoff

        raise ProcessorError("Unknown error in generation loop.")

