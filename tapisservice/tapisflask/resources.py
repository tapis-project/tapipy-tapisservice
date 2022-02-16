"""
Common flask resources to be available in all Tapis APIs.

Add these to your service's api.py as follows (replace "tenants" with your service name):

from common.resources import HelloResource, ReadyResource
...

# Health-checks
api.add_resource(ReadyResource, '/v3/tenants/ready')
api.add_resource(HelloResource, '/v3/tenants/hello')

"""
from flask_restful import Resource
from tapisservice import errors
from tapisservice.tapisflask import utils
from tapisservice.logs import get_logger
logger = get_logger(__name__)


class HelloResource(Resource):
    """
    Hello check.
    """
    def get(self):
        logger.debug('top of GET /hello')
        return utils.ok(result='',msg="Hello from Tapis")


class ReadyResource(Resource):
    """
    Service ready check.
    """
    def get(self):
        logger.debug('top of GET /ready')
        try:
            from service import models
        # if the service has no models at all, we assume the service is ready --
        except ImportError:
            return utils.ok(result='', msg="Service is ready.")
        # any other exception though is likely a problem with the service --
        except Exception as e:
            logger.error(f"Got exception in ready resource trying to import models; e: {e}.")
            raise errors.ResourceError(msg=f'Service not ready')
        return utils.ok(result='', msg="Service is ready.")
