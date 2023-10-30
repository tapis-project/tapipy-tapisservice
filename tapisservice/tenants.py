import datetime
from tapipy.tapis import Tapis, TapisResult
from tapisservice.config import conf
from tapisservice import errors
from tapisservice.logs import get_logger
logger = get_logger(__name__)


class TenantCache(object):
    """
    Class for managing the tenants available in the tenants registry, including metadata associated with the tenant.
    """
    def __init__(self):
        self.primary_site = None
        self.service_running_at_primary_site = None
        # this timedelta determines how frequently the code will refresh the tenants_cashe, looking for updates
        # to the tenant definition. note that this configuration guarantees it will not refresh any MORE often than
        # the configuration -- it only refreshes when it encoutners a tenant it does not recognize or it fails
        # to validate the signature of an access token
        self.update_tenant_cache_timedelta = datetime.timedelta(seconds=90)
        self.tenants = self.get_tenants()

    def extend_tenant(self, t):
        """
        Method to add additional attributes to tenant object that are specific to a single service, such as the private
        keys for the Tokens API or the LDAP passwords for the authenticator. The service should implement this mwthod
        :param t:
        :return:
        """
        return t

    def get_tenants(self):
        """
        Retrieve the set of tenants and associated data that this service instance is serving requests for.
        :return:
        tenants: dict =  {tenant_id1: tenant_obj1, tenant_id2: tenant_obj2, ...}
        """
        logger.debug("top of get_tenants()")
        # if this is the first time we are calling get_tenants, set the service_running_at_primary_site attribute.
        if not hasattr(self, "service_running_at_primary_site"):
            self.service_running_at_primary_site = False
        # the tenants service is a special case, as it must be a) configured to serve all tenants and b) actually
        # maintains the list of tenants in its own DB. in this case, we call a special method to use the tenants service
        # code that makes direct db access to get necessary data.
        if conf.service_name == 'tenants':
            self.service_running_at_primary_site = True
            self.last_tenants_cache_update = datetime.datetime.now()
            result = self.get_tenants_for_tenants_api()
            # Convert to dict {tenant_id: tenant_obj, ...}
            result = {tn.tenant_id: tn for tn in result}
            return result
        else:
            logger.debug("this is not the tenants service; calling tenants API to get sites and tenants...")
            # if this case, this is not the tenants service, so we will try to get
            # the list of tenants by making API calls to the tenants service.
            # NOTE: we intentionally create a new Tapis client with *no authentication* so that we can call the Tenants
            # API even _before_ the SK is started up. If we pass a JWT, the Tenants will try to validate it as part of
            # handling our request, and this validation will fail if SK is not available.
            t = Tapis(base_url=conf.primary_site_admin_tenant_base_url)
            try:
                self.last_tenants_cache_update = datetime.datetime.now()
                tenants = t.tenants.list_tenants()
                sites = t.tenants.list_sites()
            except Exception as e:
                msg = f"Got an exception trying to get the list of sites and tenants. Exception: {e}"
                logger.error(msg)
                raise errors.BaseTapisError("Unable to retrieve sites and tenants from the Tenants API.")
            for t in tenants:
                self.extend_tenant(t)
                for s in sites:
                    if hasattr(s, "primary") and s.primary:
                        self.primary_site = s
                        if s.site_id == conf.service_site_id:
                            self.service_running_at_primary_site = True
                    if s.site_id == t.site_id:
                        t.site = s
            # Convert to dict {tenant_id: tenant_obj, ...}
            tenants = {tn.tenant_id: tn for tn in tenants}
            return tenants

    def get_tenants_for_tenants_api(self):
        """
        This method computes the tenants and sites for the tenants service only. Note that the tenants service is a
        special case because it must retrieve the sites and tenants from its own DB, not from
        """
        logger.debug("this is the tenants service, pulling sites and tenants from db...")
        # NOTE: only in the case of the tenants service will we be able to import this function; so this import needs to
        # stay guarded in this method.
        if not conf.service_name == 'tenants':
            raise errors.BaseTapisError("get_tenants_for_tenants_api called by a service other than tenants.")
        from service.models import get_tenants as tenants_api_get_tenants
        from service.models import get_sites as tenants_api_get_sites
        # in the case where the tenants api migrations are running, this call will fail with a
        # sqlalchemy.exc.ProgrammingError because the tenants table will not exist yet.
        tenants = []
        result = []
        logger.info("calling the tenants api's get_sites() function...")
        try:
            sites = tenants_api_get_sites()
        except Exception as e:
            logger.info(
                "WARNING - got an exception trying to compute the sites.. "
                "this better be the tenants migration container.")
            return tenants
        logger.info("calling the tenants api's get_tenants() function...")
        try:
            tenants = tenants_api_get_tenants()
        except Exception as e:
            logger.info(
                "WARNING - got an exception trying to compute the tenants.. "
                "this better be the tenants migration container.")
            return tenants
        # for each tenant, look up its corresponding site record and save it on the tenant record--
        for t in tenants:
            # Remove datetime objects --
            t.pop('create_time')
            t.pop('last_update_time')
            # convert the tenants to TapisResult objects, and then append the sites object.
            tn = TapisResult(**t)
            for s in sites:
                if 'primary' in s.keys() and s['primary']:
                    self.primary_site = TapisResult(**s)
                if s['site_id'] == tn.site_id:
                    tn.site = TapisResult(**s)
                    result.append(tn)
                    break
        return result

    def reload_tenants(self):
        self.tenants = self.get_tenants()

    def get_tenant_config(self, tenant_id=None, url=None):
        """
        Return the config for a specific tenant_id from the tenants config based on either a tenant_id or a URL.
        One or the other (but not both) must be passed.
        :param tenant_id: (str) The tenant_id to match.
        :param url: (str) The URL to use to match.
        :return:
        """
        def find_tenant_from_id():
            logger.debug(f"top of find_tenant_from_id for tenant_id: {tenant_id}")
            # tenants is a dict
            tenant = self.tenants.get(tenant_id)
            if tenant:
                logger.debug(f"found tenant {tenant_id}")
                return tenant
            logger.info(f"did not find tenant: {tenant_id}. self.tenants: {self.tenants.keys()}")
            return None

        def find_tenant_from_url():
            # tenants is a dict
            for tenant in self.tenants.values():
                if tenant.base_url in url:
                    return tenant
                base_url_at_primary_site = self.get_base_url_for_tenant_primary_site(tenant.tenant_id)
                if base_url_at_primary_site in url:
                    return tenant
            return None

        logger.debug(f"top of get_tenant_config; called with tenant_id: {tenant_id}; url: {url}")
        # allow for local development by checking for localhost:500 in the url; note: using 500, NOT 5000 since services
        # might be running on different 500x ports locally, e.g., 5000, 5001, 5002, etc..
        if url and 'http://localhost:500' in url:
            logger.debug("http://localhost:500 in url; resolving tenant id to dev.")
            tenant_id = 'dev'
        if tenant_id:
            logger.debug(f"looking for tenant with tenant_id: {tenant_id}")
            t = find_tenant_from_id()
        elif url:
            logger.debug(f"looking for tenant with url {url}")
            # convert URL from http:// to https://
            if url.startswith('http://'):
                logger.debug("url started with http://; stripping and replacing with https")
                url = url[len('http://'):]
                url = 'https://{}'.format(url)
            logger.debug(f"looking for tenant with URL: {url}")
            t = find_tenant_from_url()
        else:
            raise errors.BaseTapisError("Invalid call to get_tenant_config; either tenant_id or url must be passed.")
        if t:
            return t
        # try one reload and then give up -
        logger.debug(f"did not find tenant; going to reload tenants.")
        self.reload_tenants()
        if tenant_id:
            t = find_tenant_from_id()
        elif url:
            t = find_tenant_from_url()
        if t:
            return t
        raise errors.BaseTapisError("invalid tenant id.")

    def get_base_url_admin_tenant_primary_site(self):
        """
        Returns the base URL for the admin tenants of the primary site.
        :return:
        """
        admin_tenant_id = self.primary_site.site_admin_tenant_id
        return self.get_tenant_config(tenant_id=admin_tenant_id).base_url

    def get_site_and_base_url_for_service_request(self, tenant_id, service):
        """
        Returns the site_id and base_url that should be used for a service request based on the tenant_id and the
        service to which the request is targeting.

        `tenant_id` should be the tenant that the object(s) of the request live in (i.e., the value of the
        X-Tapis-Tenant header).  Note that in the case of service=tenants, the value of tenant_id id now
        well defined and is ignored.

        `service` should be the service being requested (e.g., apps, files, sk, tenants, etc.)

        """
        logger.debug(f"top of get_site_and_base_url_for_service_request() for tenant_id: {tenant_id} and service: {service}")
        site_id_for_request = None
        base_url = None
        # requests to the tenants service should always go to the primary site
        if service == 'tenants':
            site_id_for_request = self.primary_site.site_id
            base_url =self.get_base_url_admin_tenant_primary_site()
            logger.debug(f"call to tenants API, returning site_id: {site_id_for_request}; base url: {base_url}")
            return site_id_for_request, base_url

        # the SK and token services always use the same site as the site the service is running on --
        tenant_config = self.get_tenant_config(tenant_id=tenant_id)
        if service == 'sk' or service == 'security' or service == 'tokens':
            site_id_for_request = conf.service_site_id
            # if the site_id for the service is the same as the site_id for the request, use the tenant URL:
            if conf.service_site_id == tenant_config.site_id:
                base_url = tenant_config.base_url
                logger.debug(f"service '{service}' is SK or tokens and tenant's site was the same as the "
                             f"configured site; returning site_id: {site_id_for_request}; base_url: {base_url}")
                return site_id_for_request, base_url
            else:
                # otherwise, we use the primary site (NOTE: if we are here, the configured site_id is different from the
                # tenant's owning site. this only happens when the running service is at the primary site; services at
                # associate sites never handle requests for tenants they do not own.
                site_id_for_request = self.primary_site.site_id
                base_url = self.get_base_url_for_tenant_primary_site(tenant_id)
                logger.debug(f'request for {tenant_id} and {service}; returning site_id: {site_id_for_request}; '
                             f'base URL: {base_url}')
                return site_id_for_request, base_url
        # if the service is hosted by the site, we use the base_url associated with the tenant --
        try:
            # get the services hosted by the owning site of the tenant
            site_services = tenant_config.site.services
        except AttributeError:
            logger.info("tenant_config had no site or services; setting site_service to [].")
            site_services = []
        if service in site_services:
            site_id_for_request = conf.service_site_id
            base_url = tenant_config.base_url
            logger.debug(f"service {service} was hosted at site; returning site_id: {site_id_for_request}; "
                         f"tenant's base_url: {base_url}")
            return site_id_for_request, base_url
        # otherwise, we use the primary site
        site_id_for_request = self.primary_site.site_id
        base_url = self.get_base_url_for_tenant_primary_site(tenant_id)
        logger.debug(f'request was for {tenant_id} and {service}; returning site_id: {site_id_for_request};'
                     f'base URL: {base_url}')
        return site_id_for_request, base_url

    def get_base_url_for_tenant_primary_site(self, tenant_id):
        """
        Compute the base_url at the primary site for a tenant owned by an associate site.
        """
        try:
            base_url_template = self.primary_site.tenant_base_url_template
        except AttributeError:
            raise errors.BaseTapisError(
                f"Could not compute the base_url for tenant {tenant_id} at the primary site."
                f"The primary site was missing the tenant_base_url_template attribute.")
        return base_url_template.replace('${tenant_id}', tenant_id)

    def get_site_admin_tenants_for_service(self):
        """
        Get all tenants for which this service might need to interact with.
        """
        # services running at the primary site must interact with all sites, so this list comprehension
        # just pulls out the tenant's that are admin tenant id's for some site.
        logger.debug("top of get_site_admin_tenants_for_service")
        if self.service_running_at_primary_site:
            admin_tenants = [tn.tenant_id for tn in self.tenants.values() if tn.tenant_id == tn.site.site_admin_tenant_id]
        # otherwise, this service is running at an associate site, so it only needs itself and the primary site.
        else:
            admin_tenants = [conf.service_tenant_id]
            for tn in self.tenants.values():
                if tn.tenant_id == tn.site.site_admin_tenant_id and hasattr(tn.site, 'primary') and tn.site.primary:
                    admin_tenants.append(tn.tenant_id)
        logger.debug(f"site admin tenants for service: {admin_tenants}")
        return admin_tenants


tenant_cache = TenantCache()