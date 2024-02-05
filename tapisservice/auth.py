import base64
import json
from lib2to3.pgen2 import token
import re
from Crypto.PublicKey import RSA
from Crypto.Hash import SHA256
import datetime
import jwt
from tapipy.tapis import Tapis

from tapisservice import errors
from tapisservice.tenants import tenant_cache
from tapisservice.config import conf
from tapisservice.logs import get_logger
logger = get_logger(__name__)



def get_service_tapis_client(tenant_id=None,
                             base_url=None,
                             jwt=None,
                             resource_set='tapipy', #todo -- change back to resource_set='tapipy'
                             custom_spec_dict=None,
                             download_latest_specs=False,
                             tenants=None,
                             access_token_ttl=None,
                             generate_tokens=True):
    """
    Returns a Tapis client for the service using the service's configuration. If tenant_id is not passed, uses the first
    tenant in the service's tenants configuration.
    :param tenant_id: (str) The tenant_id associated with the tenant to configure the client with.
    :param base_url: (str) The base URL for the tenant to configure the client with.
    :return: (tapipy.tapis.Tapis) A Tapipy client object.
    """
    # if there is no base_url the primary_site_admin_tenant_base_url configured for the service:
    if not base_url:
        base_url = conf.primary_site_admin_tenant_base_url
    if not tenant_id:
        tenant_id = conf.service_tenant_id
    if not tenants:
        # the following would work to reference this module's tenants object, but we'll choose to raise
        # an error instead; it could be that
        # tenants = sys.modules[__name__].tenants
        raise errors.BaseTapisError("As a Tapis service, passing in the appropriate tenants manager object"
                                    "is required.")
    t = Tapis(base_url=base_url,
              tenant_id=tenant_id,
              username=conf.service_name,
              account_type='service',
              service_password=conf.service_password,
              jwt=jwt,
              resource_set=resource_set,
              custom_spec_dict=custom_spec_dict,
              download_latest_specs=download_latest_specs,
              tenants=tenants,
              plugins=["tapisservice"],
              is_tapis_service=True)
    if generate_tokens:
        logger.debug("tapis service client constructed, now getting tokens.")
        if access_token_ttl:
            t.get_tokens(access_token_ttl=access_token_ttl)
        else:
            t.get_tokens()
    logger.debug("got tokens, returning tapipy client.")
    return t


def get_service_tokens(self, **kwargs):
    """
    Calls the Tapis Tokens API to get access and refresh tokens for a service and set them on the client.
    :return:
    """
    if not 'username' in kwargs:
        username = self.username
    else:
        username = kwargs['username']
    # tapis services manage a set ot tokens, one for each of the tenants for which we need to interact with.
    self.service_tokens = {}
    # if the caller passed a tenant_id explicitly, we just use that
    if 'tenant_id' in kwargs:
        self.service_tokens = {kwargs['tenant_id']: {}}
    # otherwise, we compute all the tenant's that this service could need to interact with.
    else:
        try:
            self.service_tokens = {t: {} for t in self.tenant_cache.get_site_admin_tenants_for_service()}
        except AttributeError:
            raise errors.BaseTapisError("Unable to retrieve target tenants for a service. Are you really a Tapis "
                                        "service? Did you pass in your Tenants manager instance?")
    if 'access_token_ttl' not in kwargs:
        # default to a 24 hour access token -
        access_token_ttl = 86400
    else:
        access_token_ttl = kwargs['access_token_ttl']
    if 'refresh_token_ttl' not in kwargs:
        # default to 1 year refresh token -
        refresh_token_ttl = 3153600000
    else:
        refresh_token_ttl = kwargs['refresh_token_ttl']
    for tenant_id in self.service_tokens.keys():
        logger.debug(f"attempting to generate token for tenant {tenant_id}")
        try:
            target_site_id = self.tenant_cache.get_tenant_config(tenant_id=tenant_id).site_id
        except Exception as e:
            raise errors.BaseTapisError(f"Got exception computing target site id; e:{e}")
        try:
            tokens = self.tokens.create_token(token_username=username,
                                              token_tenant_id=self.tenant_id,
                                              account_type=self.account_type,
                                              access_token_ttl=access_token_ttl,
                                              generate_refresh_token=True,
                                              refresh_token_ttl=refresh_token_ttl,
                                              target_site_id=target_site_id,
                                              _tapis_set_x_headers_from_service=True)
        except Exception as e:
            raise errors.BaseTapisError(f"Could not generate service tokens for service: {username};\n"
                                           f"exception: {e};\n"
                                           f"function args:\n"
                                           f"token_username: {self.username};\n "
                                           f"account_type: {self.account_type};\n "
                                           f"target_site_id: {target_site_id};\n "
                                           f"request url: {e.request.url}; \n "
                                           f"headers: {e.request.headers}")
        logger.debug(f"generate token for tenant {tenant_id} successfully.")
        self.service_tokens[tenant_id] = {'access_token': self.add_claims_to_token(tokens.access_token),
                                          'refresh_token': tokens.refresh_token}


def refresh_service_tokens(self, tenant_id):
    """
    Use the refresh token operation for tokens of type "service".
    """
    refresh_token = self.service_tokens[tenant_id]['refresh_token'].refresh_token
    tokens = self.tokens.refresh_token(refresh_token=refresh_token, _tapis_set_x_headers_from_service=True)
    self.service_tokens[tenant_id]['access_token'] = self.add_claims_to_token(tokens.access_token)
    self.service_tokens[tenant_id]['refresh_token'] = tokens.refresh_token
    return tokens.access_token


def set_refresh_token(self, token):
    """
    Set the refresh token to be used in this session.
    :param token: (TapisResult) A TapisResult object returned using the t.tokens.create_token() method.
    :return:
    """

    def _expires_in():
        return self.refresh_token.expires_at - datetime.datetime.now(datetime.timezone.utc)

    self.refresh_token = token
    try:
        self.refresh_token.claims = self.validate_token(self.refresh_token.refresh_token)
        self.refresh_token.original_ttl = self.refresh_token.expires_in
        self.refresh_token.expires_in = _expires_in
        self.refresh_token.expires_at = datetime.datetime.fromtimestamp(self.refresh_token.claims['exp'],
                                                                        datetime.timezone.utc)
    except:
        pass


def preprocess_service_request(operation, prepared_request, **kwargs):
    """
    This function is called whenever a tapis.<resource>.<operation> is invoked (i.e, when the __call__ method executes) 
    before tapipy sends the request to the Tapis API server.
    
    operation: the Operation object being invoked.
    prepared_request: the requests.PreparedRequest object created by the tapipy library
    kwargs: the kwargs passed to the __call__ function.

    This function makes the following updates to the prepared_request object:
    1. It sets the base URL for the request. 
    2. It sets the X-Tapis-Token header to the appropriate service token.
    3. It sets the X-Tapis-Tenant and X-Tapis-User headers.
    """
    logger.debug(f"top of preprocess_service_request for operation: {operation.http_method.upper()}: {operation.path_name}")
    # for service requests, we must determine which site to use for the request. there are 3 cases.
    # first, the caller can explicitly set the _tapis_set_x_headers_from_service variable. this instructs the library
    # to use the service's site and name for setting the X-Tapis-Tenant and User headers when making the request.
    if '_tapis_set_x_headers_from_service' in kwargs and kwargs['_tapis_set_x_headers_from_service']:
        # in this case, we assume the tenant for the request is the admin tenant of the site the service belongs to.
        request_tenant_id = conf.service_tenant_id
        request_x_tapis_user = conf.service_name
        site_id, base_url = operation.tapis_client.tenant_cache.get_site_and_base_url_for_service_request(request_tenant_id, 
                                                                                                    operation.resource_name)
    # otherwise, if the _x_tapis_tenant and _x_tapis_user have been explicitly set, we use those to determine the site.
    elif '_x_tapis_tenant' in kwargs and '_x_tapis_user' in kwargs:
        request_tenant_id = kwargs['_x_tapis_tenant']
        request_x_tapis_user = kwargs['_x_tapis_user']
        site_id, base_url = operation.tapis_client.tenant_cache.get_site_and_base_url_for_service_request(request_tenant_id, 
        operation.resource_name)
    # next we'll look for "defaults" on the client.
    elif hasattr(operation.tapis_client, 'x_tenant_id') and hasattr(operation.tapis_client, 'x_username'):
        request_tenant_id = operation.tapis_client.x_tenant_id
        request_x_tapis_user = operation.tapis_client.x_username
        site_id, base_url = operation.tapis_client.tenant_cache.get_site_and_base_url_for_service_request(request_tenant_id, 
        operation.resource_name)        
    # finally, we look for a request object in the request_thread_local that could have these 
    else:
        if conf.python_framework_type == 'flask':
            logger.debug("looking on the flask thread local to determine the X-Tapis-* headers ")
            
            from tapisservice.tapisflask import request_thread_local
            try:
                request_tenant_id = request_thread_local.request_tenant_id
            except RuntimeError:
                msg = "Couldn't determine how to set the X-Tapis-Tenant and User headers. This is probably a flask service running "\
                "outside of the request context. Consider setting _tapis_set_x_headers_from_service or set the "\
                    "_x_tapis_tenant and _x_tapis_user parameters."
                raise errors.BaseTapisError(msg)
            # always use x_tapis_user, if set:
            if hasattr(request_thread_local, 'x_tapis_user') and request_thread_local.x_tapis_user:
                request_x_tapis_user = request_thread_local.x_tapis_user
            # if x_tapis_user was not set, then we look for the `username` attr on the request_thread_local. this attr 
            # gets set based on the access token.
            elif hasattr(request_thread_local, 'username') and request_thread_local.username:
                request_x_tapis_user = request_thread_local.username
            # finally, if we don't have an x_tapis_user header OR a token, we look for a kwarg _x_tapis_user
            elif '_x_tapis_user' in kwargs.keys():
                request_x_tapis_user = kwargs.get('_x_tapis_user')
            else:
                request_x_tapis_user = conf.service_name
            site_id, base_url = operation.tapis_client.tenant_cache.get_site_and_base_url_for_service_request(request_tenant_id, 
                                                                                                    operation.resource_name)

        elif conf.python_framework_type == 'django':
            msg = """Did not find `_tapis_set_x_headers_from_service` or `_x_tapis_tenant` and `_x_tapis_user` in kwargs; 
            Automatic derivation of these properties is currently only supported for APIs written in flask. 
            If your API is written in flask, be sure to set conf.python_framework_type == flask."""
            raise errors.BaseTapisError(msg)
        else:
            msg = """Did not find `_tapis_set_x_headers_from_service` or `_x_tapis_tenant` and `_x_tapis_user` in kwargs; 
            Automatic derivation of these properties is currently only supported for APIs written in flask. 
            If your API is written in flask, be sure to set conf.python_framework_type == flask."""
            raise errors.BaseTapisError(msg)
    
    # modify the request base url --
    # the original base URL is the URL up to the '/v3/'
    orig_base_url = prepared_request.url.split('/v3')[0]
    prepared_request.url = prepared_request.url.replace(orig_base_url, base_url)
    logger.debug(f"final URL: {prepared_request.url}")

    # modify the X-Tapis-Tenant and X-Tapis-User request headers ---
    prepared_request.headers['X-Tapis-Tenant'] = request_tenant_id
    prepared_request.headers['X-Tapis-User'] = request_x_tapis_user

    # set the X-Tapis-Token header -----
    # the tenant_id for the request could be a user tenant (e.g., "tacc" or "dev") but the
    # service tokens are stored by admin tenant, so we need to get the admin tenant for the
    # owning site of the tenant.
    for tn in operation.tapis_client.tenant_cache.tenants.values(): # tenant_cache is a dict
        if tn.site.site_id == site_id:
            request_site_admin_tenant_id = tn.site.site_admin_tenant_id
    logger.debug(f"site admin tenant for the request: {request_site_admin_tenant_id}")
    # service_tokens may be defined but still be empty dictionaries... this __call__ could be to get
    # the service's first set of tokens.
    if request_site_admin_tenant_id in operation.tapis_client.service_tokens.keys() \
            and 'access_token' in operation.tapis_client.service_tokens[request_site_admin_tenant_id].keys():
        try:
            access_token = operation.tapis_client.service_tokens[request_site_admin_tenant_id]['access_token']
            jwt_str = access_token.access_token
            prepared_request.headers['X-Tapis-Token']= jwt_str
            # also remove the basic auth header; we shouldn't send both
            prepared_request.headers.pop('Authorization', None)
        except (KeyError, TypeError):
            raise errors.BaseTapisError(f"Did not find service tokens for "
                                        f"tenant {request_site_admin_tenant_id};")
        
        # The remaining code is to check whether the token has expired and refresh if necessary
        # if the access token doesn't have an expires_in attribute, there isn't much we can do.
        if not hasattr(access_token, "expires_in"):
            #  tokens created by and for the Tokens API itself do not have an expired_in attr; they are
            #  service.models.TapisAccessToken type
            try: 
                if operation.tapis_client.username == 'tokens':
                    return
            except:
                pass
            # it is expected that some tokens, including will be raw string types or 
            if not type(access_token) == str:
                logger.warn(f"The access token didn't have an expired_in attr and was not a string type. type was: {type(access_token)}")
            logger.debug("returning from preprocess_service_request without checking for the need to refresh.")
            return
        # check the time remaining on the access token ---        
        
        logger.debug("checking to see if we need to refresh the service token...")
        try:
            time_remaining = access_token.expires_in()
            # if the access token is about to expire, try to use refresh, unless this is a call to
                # refresh (otherwise this would never terminate!)
            if datetime.timedelta(seconds=5) > time_remaining:
                if (operation.resource_name == 'tokens' and operation.operation_id == 'refresh_token')\
                        or (operation.resource_name == 'authenticator' and operation.operation_id == 'create_token'):
                    pass
                else:
                    logger.info("service tokens expired, attempting to refresh service tokens.")
                    access_token = operation.tapis_client.refresh_service_tokens(tenant_id=request_site_admin_tenant_id)
                    logger.info("service tokens refreshed successfully.")
                    prepared_request.headers['X-Tapis-Token']= access_token.access_token
                    # also remove the basic auth header; we shouldn't send both
                    prepared_request.headers.pop('Authorization', None)
        except Exception as e:
            # if we couldn't refresh the token for whatever reason, we will still try the request...
            logger.error(f"Got an exception trying to refresh the service token; will proceed with trying the request. exception: {e}")
    else:
        # not having a token is not an issue if this is a request to generate a token --
        if '/v3/tokens' not in prepared_request.url:
            logger.warning(f"Not able to set the access token; service token keys: {operation.tapis_client.service_tokens.keys()}")
            if request_site_admin_tenant_id in operation.tapis_client.service_tokens.keys():
                logger.warning(f"key existed; value: {operation.tapis_client.service_tokens[request_site_admin_tenant_id]}")
    logger.debug("returning from preprocess_service_request")
            

def add_headers(request_thread_local, request):
    """
    Adds the standard Tapis headers to the request thread local.

    Requires the library to pass a `request` object with the `headers` attribute; i.e., `request.headers` should be the 
    headers sent on the request.

    :return:
    """
    # the actual access token -
    request_thread_local.x_tapis_token = request.headers.get('X-Tapis-Token')

    # the tenant associated with the subject of the request; used, for instance, when the subject is different
    # from the subject in the actual access_token (for example, when the access_token represents a service account).
    request_thread_local.x_tapis_tenant = request.headers.get('X-Tapis-Tenant')

    # the user associated with the subject of the request. Similar to x_tapis_tenant, this is used, for instance, when
    # the subject is different from the subject in the actual access_token (for example, when the access_token
    # represents a service account).
    request_thread_local.x_tapis_user = request.headers.get('X-Tapis-User')

    # a hash of the original user's access token. this can be used, for instance, to check if the original user's
    # access token has been revoked.
    request_thread_local.x_tapis_user_token_hash = request.headers.get('X-Tapis-User-Token-Hash')


def resolve_tenant_id_for_request(request_thread_local, request, tenant_cache=tenant_cache):
    """
    Resolves the tenant associated with the request and sets it on the request_thread_local.request_tenant_id variable.
    Additionally, sets the request_thread_local.request_tenant_base_url variable in the process. Returns the
    request_tenant_id (string).
    
    request should be the request object for the incoming request. at a minimum it should have the following:
      * request.headers - the headers of the request, as a dictionary-like object.
      * request.base_url - the base URL for the request which should include the domain (e.g., localhost or dev.tapis.io).
    request_base_url should be the base URL on the request object. for example, in the flask framework, it is the
    flask.request.base_url attribute. We assume it includes the protocol ('http://' or 'https://') as well as the port
    (e.g., ':5000') if included in the actual request.

    The high-level algorithm is as follows:

    1) If the X-Tapis-Tenant header is set in the request, this is the tenant_id for the request;
    If the X-Tapis-Token is provided in this case, it must be a service token. The Tapis service should validate
    aspects of service token usage by calling the validate_request_token() function.
    2) If the X-Tapis-Tenant header is not set, then the base_url for this request dictates the tenant_id. There
    are two sub-cases:
      2a) The base_url is the tenant's base URL, in which case the base_url will be in the tenant list,
      2b) The base_url is the tenant's primary-site URL (this is the case when the associate site has forwarded
          a request to the primary site) in which case the base_url will be of the form <tenant_id>.tapis.io
      cf., https://confluence.tacc.utexas.edu/display/CIC/Authentication+Subsystem
    :return:
    """
    logger.debug("top of resolve_tenant_id_for_request")
    add_headers(request_thread_local, request)
    # if the x_tapis_tenant header was set, then this must be a request from a service account. in this case, the
    # request_tenant_id will in general not match the tapis/tenant_id claim in the service token.
    if request_thread_local.x_tapis_tenant:
        # if a token was also set, we need to do additional checks
        if request_thread_local.x_tapis_token:
            logger.debug("found x_tapis_tenant and x_tapis_token on the request_thread_local object.")
            # need to check token is a service token
            if not hasattr(request_thread_local, 'token_claims'):
                logger.error(f"Did not find token_claims attribute on request_thread_local; attrs: {dir(request_thread_local)}")
            if not request_thread_local.token_claims.get('tapis/account_type') == 'service':
                raise errors.PermissionsError('Setting X-Tapis-Tenant header and X-Tapis-Token requires a service token.')
        
        # validation has passed, so set the request tenant_id to the x_tapis_tenant:
        request_thread_local.request_tenant_id = request_thread_local.x_tapis_tenant
        request_tenant = tenant_cache.get_tenant_config(tenant_id=request_thread_local.request_tenant_id)
        request_thread_local.request_tenant_base_url = request_tenant.base_url
        # todo -- compute and set g.request_site_id
        return request_thread_local.request_tenant_id
    # in all other cases, the request's tenant_id is based on the base URL of the request:
    logger.debug(f"computing base_url based on the URL of the request: {request.base_url}")
    # the request_baseurl includes the protocol, port (if present) and contains the url path; examples:
    #  http://localhost:5000/v3/oauth2/tenant;
    #  https://dev.develop.tapis.io/v3/oauth2/tenant
    # in the local development case, the base URL (e.g., localhost:5000, 172.17.0.1, dev_base_url conf var)
    # cannot be used to resolve the tenant id so instead we use the tenant_id claim within the x-tapis-token:
    dev_request_url = conf.get("dev_request_url", "dev://request_url")
    if 'http://172.17.0.1:' in request.base_url or 'http://localhost:' in request.base_url or dev_request_url in request.base_url:
        logger.debug(f"found 172.17.0.1, localhost, or {dev_request_url} in base_url")
        # some services, such as authenticator, have endpoints that do not receive tokens. in the local development
        # case for these endpoints, we don't have a lot of good options -- we can't use the base URL or the token
        # to determine the tenant, so we just set it to the "dev" tenant.
        if not hasattr(request_thread_local, 'token_claims'):
            logger.warn("did not find a token_claims attribute in local development case. Can't use the URL, can't"
                        "use the token. We have no option but to set the tenant to dev!!")
            request_thread_local.request_tenant_id = 'dev'
            request_thread_local.request_tenant_base_url = 'http://dev.develop.tapis.io'
            return request_thread_local.request_tenant_id
        request_tenant = tenant_cache.get_tenant_config(tenant_id=request_thread_local.token_claims.get('tapis/tenant_id'))
        request_thread_local.request_tenant_id = request_tenant.tenant_id
        request_thread_local.request_tenant_base_url = request_tenant.base_url
        # todo -- compute and set request_thread_local.request_site_id
        return request_thread_local.request_tenant_id
    # otherwise we are not in the local development case, so use the request's base URL to determine the tenant id
    # and make sure that tenant_id matches the tenant_id claim in the token.
    request_tenant = tenant_cache.get_tenant_config(url=request.base_url)
    request_thread_local.request_tenant_id = request_tenant.tenant_id
    request_thread_local.request_tenant_base_url = request_tenant.base_url
    # todo -- compute and set request_thread_local.request_site_id
    # we need to check that the request's tenant_id matches the tenant_id in the token:
    if request_thread_local.x_tapis_token:
        logger.debug("found x_tapis_token on g; making sure tenant claim inside token matches that of the base URL.")
        if not hasattr(request_thread_local, "token_claims"):
            logger.error(f"request_thread_local missing token_claims! attrs: {dir(request_thread_local)}")
        token_tenant_id = request_thread_local.token_claims.get('tapis/tenant_id')
        if not token_tenant_id == request_thread_local.request_tenant_id:
            raise errors.PermissionsError(f'The tenant_id claim in the token, '
                                          f'{token_tenant_id} does not match the URL tenant, {request_thread_local.request_tenant_id}.')
    logger.debug(f"resolve_tenant_id_for_request returning {request_thread_local.request_tenant_id}")
    return request_thread_local.request_tenant_id


def validate_request_token(request_thread_local, tenant_cache=tenant_cache):
    """
    Attempts to validate the Tapis access token in the request based on the public key and signature in the JWT.
    This function raises
        - NoTokenError - if no token is present in the request.
        - AuthenticationError - if validation is not successful.
    :param tenants: The service's tenants object.
    :return:
    """
    logger.debug(f"top of validate_request_token; thread_local attrs: {dir(request_thread_local)}")
    if not hasattr(request_thread_local, 'x_tapis_token'):
        raise errors.NoTokenError("No access token found in the request.")
    claims = validate_token(request_thread_local.x_tapis_token, tenant_cache)
    # set basic variables on the flask thread-local
    request_thread_local.token_claims = claims
    request_thread_local.username = claims.get('tapis/username')
    # We initialize request_username to look at token username. We overwrite this if it's a service account
    # later by setting the var equal to request_thread_local.x_tapis_user. Services should use this variable
    # to process request with correct username.
    request_thread_local.request_username = claims.get('tapis/username')
    request_thread_local.tenant_id = claims.get('tapis/tenant_id')
    request_thread_local.account_type = claims.get('tapis/account_type')
    request_thread_local.delegation = claims.get('tapis/delegation')
    # service tokens have some extra checks:
    if claims.get('tapis/account_type') == 'service':
        request_thread_local.site_id = claims.get('tapis/target_site_id')
        service_token_checks(request_thread_local, claims, tenant_cache)
        # Overwrite request_username with x_tapis_user which is set using `_x_tapis_user` headers by service
        request_thread_local.request_username = request_thread_local.x_tapis_user
    # user tokens must *not* set the X-Tapis-Tenant and X-Tapis_user headers
    else:
        try:
            if request_thread_local.x_tapis_tenant or request_thread_local.x_tapis_user:
                raise errors.AuthenticationError("Invalid request; cannot set OBO headers with a user token.")
        except AttributeError:
            pass


def insecure_decode_jwt_to_claims(token):
    """
    Returns the claims associated with a token WITHOUT checking the signature.
    """
    # JWT is 3 parts delineated by '.' character
    parts = token.split('.')
    # should be three parts
    if not len(parts) == 3:
        raise errors.BaseTapisError(f"Invalid JWT format; did not get 3 parts got: {len(parts)}.")
    # convert part 1 to bytes and add additional padding; see this issue: 
    # https://stackoverflow.com/questions/2941995/python-ignore-incorrect-padding-error-when-base64-decoding
    part_bytes = parts[1].encode()
    part_bytes = part_bytes + b'=='
    # try to base64 decode the middle part after adding padding; the decode returns `data` as bytes
    try:
        data = base64.b64decode(part_bytes)
    except Exception as e:
        raise errors.BaseTapisError(f"could not b64 decode the data; exception: {e}")
    try:
        claims = json.loads(data)
    except Exception as e:
        raise errors.BaseTapisError(f"Could not serialize the bytes data; exception: {e}")
    return claims


def validate_token(token, tenant_cache=tenant_cache):
    """
    Stand-alone function to validate a Tapis token. 
    :param token: The token to validate
    :param tenant_cache: The service's tenant_cache object with tenant configs; Should be an instance of TenantCache.
    :return: 
    """
    # first, decode the token data to determine the tenant associated with the token. We are not able to
    # check the signature until we know which tenant, and thus, which public key, to use for validation.
    logger.debug("top of validate_token")
    if not token:
        raise errors.NoTokenError("No Tapis access token found in the request.")
    try:
        data = insecure_decode_jwt_to_claims(token)
    except Exception as e:
        logger.debug(f"got exception trying to parse data from the access_token jwt; exception: {e}")
        raise errors.AuthenticationError("Could not parse the Tapis access token.")
    logger.debug(f"got data from token: {data}")
    # get the tenant out of the jwt payload and get associated public key
    try:
        token_tenant_id = data['tapis/tenant_id']
    except KeyError:
        raise errors.AuthenticationError("Unable to process Tapis token; could not parse the tenant_id. It is possible "
                                         "the token is in a format no longer supported by the platform.")
    try:
        token_tenant = tenant_cache.get_tenant_config(tenant_id=token_tenant_id)
        public_key_str = token_tenant.public_key
    except errors.BaseTapisError:
        logger.error(f"Did not find the public key for tenant_id {token_tenant_id} in the tenant configs.")
        raise errors.AuthenticationError("Unable to process Tapis token; unexpected tenant_id.")
    except AttributeError:
        raise errors.AuthenticationError("Unable to process Tapis token; no public key associated with the "
                                         "tenant_id.")
    if not public_key_str:
        raise errors.AuthenticationError("Could not find the public key for the tenant_id associated with the tenant.")
    # check signature and decode
    tries = 0
    while tries < 2:
        tries = tries + 1
        try:
            claims = jwt.decode(token, public_key_str, algorithms=["RS256"])
        except Exception as e:
            # if we get an exception decoding it could be that the tenant's public key has changed (i.e., that
            # the public key in out tenant_cache is stale. if we haven't updated the tenant_cache in the last
            # update_tenant_cache_timedelta then go ahead and update and try the decode again.
            if ( (datetime.datetime.now() > tenant_cache.last_tenants_cache_update + tenant_cache.update_tenant_cache_timedelta)
                    and tries == 1):
                tenant_cache.get_tenants()
                continue
            # otherwise, we were using a recent public key, so just fail out.
            logger.debug(f"Got exception trying to decode token; exception: {e}")
            raise errors.AuthenticationError("Invalid Tapis token.")
    # if the token is a service token (i.e., this is a service to service request), do additional checks:
    return claims


def get_pub_rsa_key(pub_key):
    """
    Return the RSA public key object associated with the string `pub_key`.
    :param pub_key:
    :return:
    """
    return RSA.importKey(pub_key)

def service_token_checks(request_thread_local, claims, tenant_cache):
    """
    This function does additional checks when a service token is used to make a Tapis request.

    """
    logger.debug(f"top of service_token_checks; claims: {claims}")
    # first check that the target_site claim in the token matches this service's site_id --
    target_site_id = claims.get('tapis/target_site')
    try:
        service_site_id = conf.service_site_id
    except AttributeError:
        msg = "service configured without a site_id. Aborting."
        logger.error(msg)
        raise errors.BaseTapisError(msg)
    if not target_site_id == service_site_id:
        msg = f"token's target_site ({target_site_id}) does not match service's site_id ({service_site_id}."
        logger.info(msg)
        raise errors.AuthenticationError("Invalid service token; "
                                         "target_site claim does not match this service's site_id.")
    # check that this service should be fulfilling this request based on its site_id config --
    # the X-Tapis-* (OBO) headers are required for service requests; if it is not set, raise an error.
    if not request_thread_local.x_tapis_tenant:
        raise errors.AuthenticationError("Invalid service request; X-Tapis-Tenant header missing.")
    if not request_thread_local.x_tapis_user:
        raise errors.AuthenticationError("Invalid service request; X-Tapis-User header missing.")
    request_tenant = tenant_cache.get_tenant_config(tenant_id=request_thread_local.x_tapis_tenant)
    site_id_for_request = request_tenant.site_id
    # if the service's site_id is the same as the site for the request, the request is always allowed:
    if service_site_id == site_id_for_request:
        logger.debug("request is for the same site as the service; allowing request.")
        return True
    # otherwise, we only allow the primary site to handle requests for other sites, and only if the service is NOT
    # on the site's list of services that it runs.
    if not tenant_cache.service_running_at_primary_site:
        raise errors.AuthenticationError("Cross-site service requests are only allowed to the primary site.")
    logger.debug("this service is running at the primary site.")
    # make sure this service is not on the list of services deployed at the associate site --
    if conf.service_name in request_tenant.site.services:
        raise errors.AuthenticationError(f"The primary site does not handle requests to service {conf.service}")
    logger.debug("this service is NOT in the JWT tenant's owning site's set of services. allowing the request.")
