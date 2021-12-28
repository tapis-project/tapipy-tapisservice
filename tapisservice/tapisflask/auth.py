from flask import request, g
from tapisservice.auth import add_headers, validate_request_token, resolve_tenant_id_for_request
from tapisservice.tenants import tenant_cache
from tapisservice import errors


def authn_and_authz(tenant_cache=tenant_cache, authn_callback=None, authz_callback=None):
    """All-in-one convenience function for implementing the basic Tapis authentication
    and authorization on a flask app.

    Pass authn_callback, a Python callable, to handle custom authentication mechanisms (such as nonce) when a JWT
    is not present. (Only called when JWT is not present; not called when JWT is invalid.

    Pass authz_callback, a Python callable, to do additional custom authorization
    checks within your app after the initial checks.

    Basic usage is as follows:

    import auth

    my_app = Flask(__name__)
    @my_app.before_request
    def authnz_for_my_app():
        auth.authn_and_authz()

    """
    authentication(tenant_cache, authn_callback)
    authorization(authz_callback)


def authentication(tenant_cache=tenant_cache, authn_callback=None):
    """Entry point for authentication. Use as follows:

    import auth

    my_app = Flask(__name__)
    @my_app.before_request
    def authn_for_my_app():
        auth.authentication()

    """
    add_headers(g, request)
    try:
        validate_request_token(g, tenant_cache)
    except errors.NoTokenError as e:
        if authn_callback:
            authn_callback()
            return
        else:
            raise e
    resolve_tenant_id_for_request(g, request, tenant_cache)


def authorization(authz_callback=None):
    """Entry point for authorization. Use as follows:

    import auth

    my_app = Flask(__name__)
    @my_app.before_request
    def authz_for_my_app():
        auth.authorization()

    """
    if request.method == 'OPTIONS':
        # allow all users to make OPTIONS requests
        return

    if authz_callback:
        authz_callback()
