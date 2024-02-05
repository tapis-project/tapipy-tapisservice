__version__ = '1.6.0'

def on_tapis_client_instantiation(client, **kwargs):
    """
    Required Tapis() constructor hook for tapipy plugins.
    :param client: This Tapis() object being constructed.
    :param kwargs: All arguments passes to the contstructor.
    :return:
    """

    # NOTE: these imports are done within the on_tapis_client_instantiation function intentionally, so that they are only
    # imported when needed (i.e., when this function is called by tapipy), to reduce the required imports imposed by services
    # using this library. this helps prevent circular imports in services that need, for example, to import the config object
    # at initialization. 
    from functools import partial
    from tapisservice.auth import get_service_tokens, refresh_service_tokens, set_refresh_token, preprocess_service_request
    from tapisservice.tenants import tenant_cache

    from tapisservice.logs import get_logger
    logger = get_logger(__name__)

    # use conf to determine what type of framework is being used --
    from tapisservice.config import conf


    logger.debug("inside tapisservice.on_tapis_client_instantiation")
    if kwargs.get('is_tapis_service'):
        client.is_tapis_service = True
        client.account_type = 'service'
    else:
        client.is_tapis_service = False
    if kwargs.get('service_password'):
        client.service_password = kwargs['service_password']
    else:
        client.service_password = None
    
    # the following two parameters can be set to be used for setting headers to make requests on behalf of a different
    # tenant_id and username for all requests made by this client. Typically, these variables are not used, as the service 
    # usually needs to set these headers on a per-request basis, but it can conveneint to set them only once at the beginning when
    # writing utility programs or issuing tests in a python shell, etc.
    if kwargs.get('x_tenant_id'):
        client.x_tenant_id = kwargs['x_tenant_id']
    if kwargs.get('x_username'):
        client.x_username = kwargs.get('x_username')

    # if the tenant_cache object was not passed in, set it to the TenantCache in this repository.
    if not kwargs.get('tenants'):
        client.tenant_cache = tenant_cache

    # set various service token method on the client --
    client.get_tokens = partial(get_service_tokens, client)
    client.refresh_service_tokens = partial(refresh_service_tokens, client)
    client.set_refresh_token = partial(set_refresh_token, client)

    # set the preprocess_service_request to be a pre-request callable.
    client.plugin_on_call_pre_request_callables.append(preprocess_service_request)
