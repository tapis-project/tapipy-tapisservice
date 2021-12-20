
class BaseTapisError(Exception):
    """
    Base Tapis error class. All Error types should descend from this class.
    """
    def __init__(self, msg=None, code=400):
        """
        Create a new TapisError object.
        :param msg: (str) A helpful string
        :param code: (int) The HTTP return code that should be returned
        """
        self.msg = msg
        self.code = code


class ServiceConfigError(BaseTapisError):
    """Error parsing service configuration."""
    pass


class NoTokenError(BaseTapisError):
    """No access token passed in the request."""
    pass


class AuthenticationError(BaseTapisError):
    """Error validating access token."""
    pass


class PermissionsError(BaseTapisError):
    """Error checking permissions or insufficient permissions needed to perform the action."""
    pass

class DAOError(BaseTapisError):
    """General error accessing or serializing database objects."""
    pass

class ResourceError(BaseTapisError):
    """General error in the API resource layer."""
    pass