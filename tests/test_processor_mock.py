import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio
from pathlib import Path
from print_etl_d.processor import LLMProcessor
from print_etl_d.config import SystemConfig, ProfileConfig, FieldDefinition

class TestLLMProcessor(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.system_config = SystemConfig(
            watch_dir=Path("./scans"),
            processed_dir=Path("./processed"),
            error_dir=Path("./error"),
            gemini_model="gemini-1.5-flash"
        )
        self.profile = ProfileConfig(
            name="test_profile",
            match_pattern="*.pdf",
            description="Test Profile",
            fields={
                "test_field": FieldDefinition(type="string", description="Test Description")
            }
        )

    def setUp(self):
        pass

    @patch("print_etl_d.processor.genai")
    async def test_process_file_success(self, mock_genai):
        # Setup mocks
        mock_model = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model

        # Mock file upload
        mock_file_ref = MagicMock()
        mock_file_ref.name = "files/123"
        mock_file_ref.state.name = "ACTIVE"
        mock_genai.upload_file.return_value = mock_file_ref
        mock_genai.get_file.return_value = mock_file_ref

        # Mock generation response
        mock_response = MagicMock()
        mock_response.text = '{"test_field": "extracted_value"}'

        # Async mock for generate_content_async
        future = asyncio.Future()
        future.set_result(mock_response)
        mock_model.generate_content_async.return_value = future

        # Run processor
        processor = LLMProcessor(self.system_config)

        # We need to mock path.exists() to return True
        with patch("pathlib.Path.exists", return_value=True):
            result = await processor.process_file(Path("dummy.pdf"), self.profile)

        self.assertEqual(result["test_field"], "extracted_value")
        mock_genai.upload_file.assert_called_once()
        mock_model.generate_content_async.assert_called_once()
        # Verify file deletion was attempted
        mock_file_ref.delete.assert_called_once()

    @patch("print_etl_d.processor.genai")
    async def test_process_file_retry_json_error(self, mock_genai):
        # Setup mocks
        mock_model = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model

        mock_file_ref = MagicMock()
        mock_file_ref.state.name = "ACTIVE"
        mock_genai.upload_file.return_value = mock_file_ref
        mock_genai.get_file.return_value = mock_file_ref

        # Mock generation response: Fail twice then succeed
        bad_response = MagicMock()
        bad_response.text = "Not JSON"

        good_response = MagicMock()
        good_response.text = '{"test_field": "retry_success"}'

        future1 = asyncio.Future()
        future1.set_result(bad_response)

        future2 = asyncio.Future()
        future2.set_result(bad_response)

        future3 = asyncio.Future()
        future3.set_result(good_response)

        mock_model.generate_content_async.side_effect = [future1, future2, future3]

        processor = LLMProcessor(self.system_config)

        with patch("pathlib.Path.exists", return_value=True):
            result = await processor.process_file(Path("dummy.pdf"), self.profile)

        self.assertEqual(result["test_field"], "retry_success")
        self.assertEqual(mock_model.generate_content_async.call_count, 3)

if __name__ == "__main__":
    unittest.main()
