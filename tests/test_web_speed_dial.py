"""Tests for the speed dial API endpoints."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from rotary_phone.call_manager import CallManager, PhoneState
from rotary_phone.config import ConfigManager
from rotary_phone.web.app import create_app
from rotary_phone.web.models import _is_valid_speed_dial_code


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

speed_dial:
  "1": "+12065551234"
  "2": "+12065555678"

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


class TestGetSpeedDial:
    """Tests for GET /api/speed-dial."""

    def test_get_speed_dial(self, test_client):
        """Test getting speed dial configuration."""
        response = test_client.get("/api/speed-dial")
        assert response.status_code == 200
        data = response.json()
        assert "speed_dial" in data
        assert data["speed_dial"]["1"] == "+12065551234"
        assert data["speed_dial"]["2"] == "+12065555678"

    def test_get_empty_speed_dial(self, tmp_path, mock_call_manager):
        """Test getting empty speed dial configuration."""
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

        config_manager = ConfigManager(user_config_path=str(config_path))
        app = create_app(
            call_manager=mock_call_manager,
            config_manager=config_manager,
            config_path=str(config_path),
        )
        client = TestClient(app)

        response = client.get("/api/speed-dial")
        assert response.status_code == 200
        data = response.json()
        assert data["speed_dial"] == {}


class TestUpdateSpeedDial:
    """Tests for PUT /api/speed-dial."""

    def test_update_speed_dial(self, test_client, config_file):
        """Test updating speed dial configuration."""
        response = test_client.put(
            "/api/speed-dial",
            json={"speed_dial": {"1": "+18005551234", "11": "+12065559999"}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["speed_dial"]["1"] == "+18005551234"
        assert data["speed_dial"]["11"] == "+12065559999"

        # Verify it was saved
        response = test_client.get("/api/speed-dial")
        assert response.json()["speed_dial"]["11"] == "+12065559999"

    def test_update_with_empty_dict(self, test_client, config_file):
        """Test updating speed dial to empty (clear all)."""
        response = test_client.put(
            "/api/speed-dial",
            json={"speed_dial": {}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["speed_dial"] == {}

    def test_update_with_invalid_json(self, test_client):
        """Test updating with invalid JSON."""
        response = test_client.put(
            "/api/speed-dial",
            content="not valid json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400
        assert "Invalid JSON" in response.json()["detail"]

    def test_update_without_speed_dial_field(self, test_client):
        """Test updating without the speed_dial field."""
        response = test_client.put(
            "/api/speed-dial",
            json={"something_else": {}},
        )
        assert response.status_code == 400
        assert "Missing 'speed_dial' field" in response.json()["detail"]

    def test_update_with_non_object(self, test_client):
        """Test updating with non-object speed_dial."""
        response = test_client.put(
            "/api/speed-dial",
            json={"speed_dial": ["not", "an", "object"]},
        )
        assert response.status_code == 400
        assert "'speed_dial' must be an object" in response.json()["detail"]

    def test_update_with_invalid_code_letters(self, test_client):
        """Test updating with invalid code (letters)."""
        response = test_client.put(
            "/api/speed-dial",
            json={"speed_dial": {"abc": "+12065551234"}},
        )
        assert response.status_code == 400
        assert "Invalid speed dial code" in response.json()["detail"]

    def test_update_with_invalid_code_too_long(self, test_client):
        """Test updating with invalid code (too long)."""
        response = test_client.put(
            "/api/speed-dial",
            json={"speed_dial": {"123": "+12065551234"}},
        )
        assert response.status_code == 400
        assert "Invalid speed dial code" in response.json()["detail"]

    def test_update_with_invalid_phone_number(self, test_client):
        """Test updating with invalid phone number."""
        response = test_client.put(
            "/api/speed-dial",
            json={"speed_dial": {"1": "not-a-phone-number!!"}},
        )
        assert response.status_code == 400
        assert "Invalid phone number" in response.json()["detail"]


class TestAddSpeedDial:
    """Tests for POST /api/speed-dial."""

    def test_add_speed_dial(self, test_client, config_file):
        """Test adding a single speed dial entry."""
        response = test_client.post(
            "/api/speed-dial",
            json={"code": "3", "number": "+18005559999"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["code"] == "3"
        assert data["number"] == "+18005559999"

        # Verify it was saved
        response = test_client.get("/api/speed-dial")
        assert response.json()["speed_dial"]["3"] == "+18005559999"

    def test_add_speed_dial_overwrites_existing(self, test_client, config_file):
        """Test adding a speed dial overwrites existing entry."""
        response = test_client.post(
            "/api/speed-dial",
            json={"code": "1", "number": "+18009999999"},
        )
        assert response.status_code == 200

        response = test_client.get("/api/speed-dial")
        assert response.json()["speed_dial"]["1"] == "+18009999999"

    def test_add_speed_dial_missing_fields(self, test_client):
        """Test adding without required fields."""
        response = test_client.post(
            "/api/speed-dial",
            json={"code": "1"},
        )
        assert response.status_code == 400
        assert "Missing 'code' or 'number' field" in response.json()["detail"]

    def test_add_speed_dial_invalid_code(self, test_client):
        """Test adding with invalid code."""
        response = test_client.post(
            "/api/speed-dial",
            json={"code": "abc", "number": "+12065551234"},
        )
        assert response.status_code == 400
        assert "Invalid speed dial code" in response.json()["detail"]

    def test_add_speed_dial_invalid_number(self, test_client):
        """Test adding with invalid phone number."""
        response = test_client.post(
            "/api/speed-dial",
            json={"code": "1", "number": "invalid"},
        )
        assert response.status_code == 400
        assert "Invalid phone number" in response.json()["detail"]


class TestDeleteSpeedDial:
    """Tests for DELETE /api/speed-dial/{code}."""

    def test_delete_speed_dial(self, test_client, config_file):
        """Test deleting a speed dial entry."""
        response = test_client.delete("/api/speed-dial/1")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify it was removed
        response = test_client.get("/api/speed-dial")
        assert "1" not in response.json()["speed_dial"]
        assert "2" in response.json()["speed_dial"]

    def test_delete_speed_dial_not_found(self, test_client):
        """Test deleting non-existent speed dial."""
        response = test_client.delete("/api/speed-dial/99")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_delete_speed_dial_invalid_code(self, test_client):
        """Test deleting with invalid code format."""
        response = test_client.delete("/api/speed-dial/abc")
        assert response.status_code == 400
        assert "Invalid speed dial code" in response.json()["detail"]


class TestSpeedDialCodeValidation:
    """Tests for the _is_valid_speed_dial_code function."""

    def test_valid_single_digit(self):
        """Test valid single digit codes."""
        assert _is_valid_speed_dial_code("1") is True
        assert _is_valid_speed_dial_code("9") is True
        assert _is_valid_speed_dial_code("0") is True

    def test_valid_two_digit(self):
        """Test valid two digit codes."""
        assert _is_valid_speed_dial_code("11") is True
        assert _is_valid_speed_dial_code("99") is True
        assert _is_valid_speed_dial_code("01") is True

    def test_invalid_empty(self):
        """Test empty code is invalid."""
        assert _is_valid_speed_dial_code("") is False

    def test_invalid_three_digits(self):
        """Test three digit codes are invalid."""
        assert _is_valid_speed_dial_code("123") is False

    def test_invalid_letters(self):
        """Test letter codes are invalid."""
        assert _is_valid_speed_dial_code("a") is False
        assert _is_valid_speed_dial_code("ab") is False
        assert _is_valid_speed_dial_code("1a") is False
