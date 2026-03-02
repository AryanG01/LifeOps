from unittest.mock import patch


def test_get_token_dict_raises_when_not_connected():
    with patch("connectors.outlook.auth.get_token", return_value=None):
        from connectors.outlook.auth import get_token_dict
        try:
            get_token_dict()
            assert False, "Should have raised"
        except RuntimeError as e:
            assert "not connected" in str(e).lower()
