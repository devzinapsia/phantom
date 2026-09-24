from unittest.mock import MagicMock, patch

from odoo.tests.common import TransactionCase

from odoo.addons.phantom_connector.models.phantom_api_client import (
    PhantomAPIClient,
    PhantomAPIError,
)


class TestPhantomAPIClient(TransactionCase):
    """No HTTP call ever hits the real Phantom server: requests.post is
    always mocked. Every call is a POST with params duplicated in both
    the URL query string and a JSON body -- confirmed against a working
    example from Phantom support, not the generic PDF manual (whose own
    PHP example never actually sends the parameters it builds, and never
    mentions the 'action' authentication needs).
    """

    @patch("odoo.addons.phantom_connector.models.phantom_api_client.requests.post")
    def test_authenticate_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"token": "abc123"}
        mock_post.return_value = mock_response

        client = PhantomAPIClient("http://phantom.example/api", "api_user", "api_pass")
        token = client.authenticate()

        self.assertEqual(token, "abc123")
        self.assertEqual(client.token, "abc123")
        mock_post.assert_called_once()
        called_params = mock_post.call_args.kwargs["params"]
        called_json = mock_post.call_args.kwargs["json"]
        self.assertEqual(called_params["action"], "autentificar")
        self.assertEqual(called_params["api_user"], "api_user")
        self.assertEqual(called_params["api_pass"], "api_pass")
        self.assertEqual(called_json["api_user"], "api_user")
        self.assertEqual(called_json["api_pass"], "api_pass")

    @patch("odoo.addons.phantom_connector.models.phantom_api_client.requests.post")
    def test_authenticate_failure_no_token(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {}
        mock_post.return_value = mock_response

        client = PhantomAPIClient("http://phantom.example/api", "api_user", "wrong_pass")
        with self.assertRaises(PhantomAPIError):
            client.authenticate()

    def test_missing_credentials_raises_before_any_call(self):
        with self.assertRaises(PhantomAPIError):
            PhantomAPIClient("http://phantom.example/api", "", "")

    @patch("odoo.addons.phantom_connector.models.phantom_api_client.requests.post")
    def test_query_invoices_uses_stored_token(self, mock_post):
        auth_response = MagicMock()
        auth_response.json.return_value = {"token": "abc123"}
        query_response = MagicMock()
        query_response.json.return_value = [{"IDT": "1"}]
        mock_post.side_effect = [auth_response, query_response]

        client = PhantomAPIClient("http://phantom.example/api", "api_user", "api_pass")
        rows = client.query_invoices(desde="2026-09-01", hasta="2026-09-30")

        self.assertEqual(rows, [{"IDT": "1"}])
        query_call_params = mock_post.call_args.kwargs["params"]
        query_call_json = mock_post.call_args.kwargs["json"]
        self.assertEqual(query_call_params["token"], "abc123")
        self.assertEqual(query_call_params["action"], "Consultar_Transacciones_Facturacion")
        self.assertEqual(query_call_params["FechaFiltrar"], 1)
        self.assertEqual(query_call_json["token"], "abc123")
