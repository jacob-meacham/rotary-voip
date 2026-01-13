"""Tests for the allowlist API endpoints."""

from unittest.mock import MagicMock, Mock

import pytest
from fastapi.testclient import TestClient

from rotary_phone.call_manager import CallManager, PhoneState
from rotary_phone.config import ConfigManager
from rotary_phone.web.app import create_app
from rotary_phone.web.models import _is_valid_phone_pattern


@pytest.fixture
def config_file(tmp_path):
    """Create a temporary config file."""
    config_content = """
sip:
  server: "test.voip.ms"
  username: "test"
  password: "test123"
  port: 5060

timing:
  inter_digit_timeout: 2.0
  ring_duration: 2.0
  ring_pause: 4.0

audio:
  ring_sound: "sounds/ring.wav"
  dial_tone: "sounds/dialtone.wav"

allowlist:
  - "*"
"""
    config_path = tmp_path / "config.yml"
    config_path.write_text(config_content)
    return str(config_path)


@pytest.fixture
def mock_call_manager():
    """Create a mock CallManager."""
    mock = MagicMock(spec=CallManager)
    mock.get_state.return_value = PhoneState.IDLE
    mock.get_dialed_number.return_value = None
    mock.get_error_message.return_value = None
    return mock


@pytest.fixture
def test_client(config_file, mock_call_manager):
    """Create a test client for the FastAPI app."""
    config_manager = ConfigManager(user_config_path=config_file)
    app = create_app(
        call_manager=mock_call_manager,
        config_manager=config_manager,
        config_path=config_file,
    )
    return TestClient(app)


class TestGetAllowlist:
    """Tests for GET /api/allowlist."""

    def test_get_allowlist_with_wildcard(self, test_client):
        """Test getting allowlist when allow all is enabled."""
        response = test_client.get("/api/allowlist")
        assert response.status_code == 200
        data = response.json()
        assert data["allowlist"] == ["*"]
        assert data["allow_all"] is True

    def test_get_allowlist_with_specific_numbers(self, tmp_path, mock_call_manager):
        """Test getting allowlist with specific numbers."""
        # Create config with specific numbers
        config_content = """
sip:
  server: "test.voip.ms"
  username: "test"
  password: "test123"
  port: 5060

timing:
  inter_digit_timeout: 2.0
  ring_duration: 2.0
  ring_pause: 4.0

audio:
  ring_sound: "sounds/ring.wav"
  dial_tone: "sounds/dialtone.wav"

allowlist:
  - "+12065551234"
  - "911"
"""
        config_path = tmp_path / "config.yml"
        config_path.write_text(config_content)

        config_manager = ConfigManager(user_config_path=str(config_path))
        app = create_app(
            call_manager=mock_call_manager,
            config_manager=config_manager,
            config_path=str(config_path),
        )
        client = TestClient(app)

        response = client.get("/api/allowlist")
        assert response.status_code == 200
        data = response.json()
        assert data["allowlist"] == ["+12065551234", "911"]
        assert data["allow_all"] is False


class TestUpdateAllowlist:
    """Tests for PUT /api/allowlist."""

    def test_update_to_allow_all(self, test_client, config_file):
        """Test updating allowlist to allow all numbers."""
        response = test_client.put(
            "/api/allowlist",
            json={"allowlist": ["*"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["allow_all"] is True

        # Verify it was saved
        response = test_client.get("/api/allowlist")
        assert response.json()["allow_all"] is True

    def test_update_with_specific_numbers(self, test_client, config_file):
        """Test updating allowlist with specific phone numbers."""
        response = test_client.put(
            "/api/allowlist",
            json={"allowlist": ["+12065551234", "+18005551212", "911"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["allowlist"] == ["+12065551234", "+18005551212", "911"]
        assert data["allow_all"] is False

    def test_update_with_empty_list(self, test_client, config_file):
        """Test updating allowlist to empty (block all)."""
        response = test_client.put(
            "/api/allowlist",
            json={"allowlist": []},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["allowlist"] == []
        assert data["allow_all"] is False

    def test_update_with_invalid_json(self, test_client):
        """Test updating with invalid JSON."""
        response = test_client.put(
            "/api/allowlist",
            content="not valid json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400
        assert "Invalid JSON" in response.json()["detail"]

    def test_update_without_allowlist_field(self, test_client):
        """Test updating without the allowlist field."""
        response = test_client.put(
            "/api/allowlist",
            json={"something_else": []},
        )
        assert response.status_code == 400
        assert "Missing 'allowlist' field" in response.json()["detail"]

    def test_update_with_non_array(self, test_client):
        """Test updating with non-array allowlist."""
        response = test_client.put(
            "/api/allowlist",
            json={"allowlist": "not an array"},
        )
        assert response.status_code == 400
        assert "'allowlist' must be an array" in response.json()["detail"]

    def test_update_with_non_string_entry(self, test_client):
        """Test updating with non-string entry in allowlist."""
        response = test_client.put(
            "/api/allowlist",
            json={"allowlist": [123, "+12065551234"]},
        )
        assert response.status_code == 400
        assert "must be a string" in response.json()["detail"]

    def test_update_with_invalid_phone_pattern(self, test_client):
        """Test updating with invalid phone pattern."""
        response = test_client.put(
            "/api/allowlist",
            json={"allowlist": ["not-a-phone-number!!"]},
        )
        assert response.status_code == 400
        assert "Invalid phone pattern" in response.json()["detail"]


class TestPhonePatternValidation:
    """Tests for the _is_valid_phone_pattern function."""

    def test_valid_international_format(self):
        """Test valid international phone numbers."""
        assert _is_valid_phone_pattern("+12065551234") is True
        assert _is_valid_phone_pattern("+442071234567") is True
        assert _is_valid_phone_pattern("+1") is False  # Too short (only country code)
        # Note: +12 is technically valid as it has + and 2 digits (country + area start)
        # We accept minimal international format to support various countries
        assert _is_valid_phone_pattern("+12") is True  # Minimum valid international

    def test_valid_plain_digits(self):
        """Test valid plain digit numbers."""
        assert _is_valid_phone_pattern("911") is True
        assert _is_valid_phone_pattern("2065551234") is True
        assert _is_valid_phone_pattern("18005551212") is True

    def test_valid_with_separators(self):
        """Test numbers with common separators."""
        assert _is_valid_phone_pattern("206-555-1234") is True
        assert _is_valid_phone_pattern("(206) 555-1234") is True
        assert _is_valid_phone_pattern("+1 206 555 1234") is True

    def test_invalid_patterns(self):
        """Test invalid phone patterns."""
        assert _is_valid_phone_pattern("") is False
        assert _is_valid_phone_pattern("abc") is False
        assert _is_valid_phone_pattern("hello123") is False
        assert _is_valid_phone_pattern("+") is False
        assert _is_valid_phone_pattern("12-ab-34") is False
