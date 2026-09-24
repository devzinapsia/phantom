import logging

import requests

from odoo import _

_logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30
AUTH_ACTION = "autentificar"
INVOICE_ACTION = "Consultar_Transacciones_Facturacion"
RECEIPT_ACTION = "Consultar_Transacciones_Pagos"


class PhantomAPIError(Exception):
    """Raised for any Phantom API failure. Messages never include the
    configured password, so they are safe to show in the UI or in a
    notification.
    """


class PhantomAPIClient:
    """Thin REST client for Phantom's real-world "API CRM" endpoint.

    Confirmed against a working example provided by Phantom support (the
    generic PDF manual's own PHP example is incomplete: it builds a query
    string via http_build_query() but never actually sends it, and never
    mentions the 'action' parameter authentication needs). Every call is
    a POST with the same parameters duplicated in both the URL query
    string and a JSON body -- redundant, but that is what the confirmed
    working example does, so it is replicated exactly rather than
    "simplified" on an assumption.

    Not an Odoo model: it only needs one company's own URL/user/password,
    passed in explicitly by the caller, and has no state Odoo needs to
    persist between calls.
    """

    def __init__(self, url, api_user, password, timeout=DEFAULT_TIMEOUT):
        # Note: the parameter is named 'api_user', not 'user' -- Odoo's
        # lazy _() inspects the calling frame's locals for a variable
        # literally named 'user' to guess a res.users id for translation,
        # and int()s it; a local 'user' holding an API username string
        # here would make any _() call elsewhere in this stack raise.
        if not url or not api_user or not password:
            raise PhantomAPIError(
                _("Phantom API URL, user and password must all be configured.")
            )
        self.url = url
        self.api_user = api_user
        self.password = password
        self.timeout = timeout
        self.token = None

    def _post(self, query_params, json_body):
        try:
            response = requests.post(
                self.url, params=query_params, json=json_body, timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise PhantomAPIError(
                _("Could not reach Phantom at %(url)s: %(error)s", url=self.url, error=str(exc))
            ) from exc
        try:
            return response.json()
        except ValueError as exc:
            raise PhantomAPIError(
                _("Phantom returned a non-JSON response from %(url)s.", url=self.url)
            ) from exc

    def authenticate(self):
        """Obtain and store an auth token, valid for 10 minutes per the
        Phantom API manual.
        """
        creds = {"api_user": self.api_user, "api_pass": self.password}
        data = self._post({"action": AUTH_ACTION, **creds}, creds)
        token = data.get("token") if isinstance(data, dict) else None
        if not token:
            raise PhantomAPIError(
                _(
                    "Phantom authentication failed for user %(api_user)s: no "
                    "token returned. Check the API user/password.",
                    api_user=self.api_user,
                )
            )
        self.token = token
        return token

    def _query(self, action, desde=None, hasta=None, fecha_filtrar=1):
        if not self.token:
            self.authenticate()
        params = {"token": self.token, "action": action, "FechaFiltrar": fecha_filtrar}
        if desde:
            params["desde"] = desde
        if hasta:
            params["hasta"] = hasta
        data = self._post(params, {"token": self.token})
        if isinstance(data, dict) and not data:
            # Some Phantom deployments return {} instead of [] for an
            # empty result set.
            return []
        if not isinstance(data, list):
            raise PhantomAPIError(
                _("Unexpected response shape from Phantom for '%(action)s'.", action=action)
            )
        return data

    def query_invoices(self, desde=None, hasta=None, fecha_filtrar=1):
        return self._query(INVOICE_ACTION, desde=desde, hasta=hasta, fecha_filtrar=fecha_filtrar)

    def query_receipts(self, desde=None, hasta=None, fecha_filtrar=1):
        return self._query(RECEIPT_ACTION, desde=desde, hasta=hasta, fecha_filtrar=fecha_filtrar)
