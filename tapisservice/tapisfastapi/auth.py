from tapisservice.tapisfastapi.utils import g
from tapisservice.auth import add_headers as core_add_headers
from tapisservice.auth import validate_request_token as core_validate_request_token
from tapisservice.auth import resolve_tenant_id_for_request as core_resolve_tenant_id_for_request
from tapisservice.tenants import tenant_cache
from tapisservice import errors

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send


class FormattedRequest():
    def __init__(self, headers, base_url, url, method):
        self.headers = headers
        self.base_url = base_url
        self.url = url
        self.method = method


class TapisMiddleware:
    """
    All-in-one convenience Middleware for implementing the basic kgservice authentication
    and authorization on a FastApi app. Use as follows:

    # Setup:
    from auth import TapisMiddleware
    api = FastAPI(title="kgservice",
                  debug=False,
                  exception_handlers={Exception: error_handler},
                  middleware=[
                    Middleware(GlobalsMiddleware),
                    Middleware(TapisMiddleware, authorization=authorization, authentication=None)
                  ])
    """
    def __init__(self, app: ASGIApp, tenant_cache=tenant_cache, authn_callback=None, authz_callback=None) -> None:
        self.app = app
        self.authn_callback = authn_callback
        self.authz_callback = authz_callback
        self.tenant_cache = tenant_cache

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Gives request obj with headers and query, etc. https://www.starlette.io/requests/
        request = Request(scope, receive)
        # Because the docs are very non-descript:
        #request.url.components = ['http', 'localhost:8000', '/pods/hello', '', '']
        #request.url._url = http://localhost:8000/pods/hello
        #request.url.scheme = 'http'
        #request.url.hostname = 'localhost'
        #request.url.path = '/pods/hello'
        #request.url.port = '8000'
        #request.url.netloc = 'localhost:8000
        #request.base_url = 'https://localhost:8000'
        # Base url comes in format {"_url": "base_url"}, request.base_url should be str though.
        formatted_request = FormattedRequest(headers = request.headers,
                                             base_url = request.base_url._url,
                                             url = request.url,
                                             method = request.method)
        authn_and_authz(
            formatted_request,
            tenant_cache=self.tenant_cache,
            authn_callback=self.authn_callback,
            authz_callback=self.authz_callback)
        await self.app(scope, receive, send)


def authn_and_authz(request, tenant_cache=tenant_cache, authn_callback=None, authz_callback=None):
    """All-in-one convenience function for Tapis authn and authz on a fastapi app.
    Don't use this. Use the TapisMiddleware instead for FastApi.

    """
    authentication(request, tenant_cache, authn_callback)
    authorization(request, authz_callback)


def authentication(request, tenant_cache=tenant_cache, authn_callback=None):
    """Entry point for authentication.
    """
    core_add_headers(g, request)
    try:
        core_validate_request_token(g, tenant_cache)
    except errors.NoTokenError as e:
        if authn_callback:
            authn_callback(request)
            return
        else:
            raise e
    core_resolve_tenant_id_for_request(g, request, tenant_cache)


def authorization(request, authz_callback=None):
    """Entry point for authorization.
    """
    if request.method == 'OPTIONS':
        # allow all users to make OPTIONS requests
        return

    if authz_callback:
        authz_callback(request)
