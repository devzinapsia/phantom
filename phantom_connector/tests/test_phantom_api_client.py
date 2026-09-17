from unittest.mock import MagicMock, patch

from odoo.tests.common import TransactionCase

from odoo.addons.phantom_connector.models.phantom_api_client import (
    PhantomAPIClient,
    PhantomAPIError,
)


class TestPhantomAPIClient(TransactionCase):
    """No HTTP call ever hits the real Phantom server: requests.get is
    always mocked.
    """

    @patch("odoo.addons.phantom_connector.models.phantom_api_client.requests.get")
    def test_authenticate_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {"token": "abc123"}
        mock_get.return_value = mock_response

        client = PhantomAPIClient("http://phantom.example/api", "api_user", "api_pass")
        token = client.authenticate()

        self.assertEqual(token, "abc123")
        self.assertEqual(client.token, "abc123")
        mock_get.assert_called_once()
        called_params = mock_get.call_args.kwargs["params"]
        self.assertEqual(called_params["api_user"], "api_user")
        self.assertEqual(called_params["api_pass"], "api_pass")

    @patch("odoo.addons.phantom_connector.models.phantom_api_client.requests.get")
    def test_authenticate_failure_no_token(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {}
        mock_get.return_value = mock_response

        client = PhantomAPIClient("http://phantom.example/api", "api_user", "wrong_pass")
        with self.assertRaises(PhantomAPIError):
            client.authenticate()

    def test_missing_credentials_raises_before_any_call(self):
        with self.assertRaises(PhantomAPIError):
            PhantomAPIClient("http://phantom.example/api", "", "")

    @patch("odoo.addons.phantom_connector.models.phantom_api_client.requests.get")
    def test_query_invoices_uses_stored_token(self, mock_get):
        auth_response = MagicMock()
        auth_response.json.return_value = {"token": "abc123"}
        query_response = MagicMock()
        query_response.json.return_value = [{"IDT": "1"}]
        mock_get.side_effect = [auth_response, query_response]

        client = PhantomAPIClient("http://phantom.example/api", "api_user", "api_pass")
        rows = client.query_invoices(desde="2026-09-01", hasta="2026-09-30")

        self.assertEqual(rows, [{"IDT": "1"}])
        query_call_params = mock_get.call_args.kwargs["params"]
        self.assertEqual(query_call_params["token"], "abc123")
        self.assertEqual(query_call_params["action"], "Consultar_Transacciones_Facturacion")
        self.assertEqual(query_call_params["FechaFiltrar"], 1)
