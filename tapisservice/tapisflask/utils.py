import os
import traceback

# import flask.ext.restful.reqparse as reqparse
from flask import jsonify, request
from werkzeug.exceptions import ClientDisconnected
from flask_restful import Api, reqparse
import sqlalchemy
import yaml

from openapi_core import Spec
from tapisservice.config import conf
from tapisservice.errors import BaseTapisError
from tapisservice.logs import get_logger
logger = get_logger(__name__)

TAG = conf.version

spec_path = os.environ.get("TAPIS_API_SPEC_PATH", '/home/tapis/service/resources/openapi_v3.yml')
try:
    spec = Spec.from_file_path(spec_path)
except Exception as e:
    msg = f"Could not find/parse API spec file at path: {spec_path}; additional information: {e}"
    print(msg)
    raise BaseTapisError(msg)

flask_errors_dict = {
    'MethodNotAllowed': {
        'message': "Invalid HTTP method on requested resource.",
        'status': "error",
        'version': conf.version
    },
}

### This changes resulting obj from obj = openapi_request_validator.validate(spec, request) to not be frozen.
### This rewrites DataClassFactory so that when it makes the validated Dataclass it's not frozen.
from openapi_core.extensions.models.factories import DataClassFactory
from openapi_core.extensions.models.types import Field
from typing import Iterable, Type, Any
from dataclasses import make_dataclass
def new_create(
    self,
    fields: Iterable[Field],
    name: str = "Model",
) -> Type[Any]:
    return make_dataclass(name, fields, frozen=False) #<-- only change is frozen=False
DataClassFactory.create = new_create


class RequestParser(reqparse.RequestParser):
    """Wrap reqparse to raise APIException."""

    def parse_args(self, *args, **kwargs):
        try:
            return super(RequestParser, self).parse_args(*args, **kwargs)
        except ClientDisconnected as exc:
            raise BaseTapisError(exc.data['message'], 400)


class TapisApi(Api):
    """General flask_restful Api subclass for all the Tapis APIs."""
    pass


def pretty_print(request):
    """Return whether or not to pretty print based on request"""
    if hasattr(request.args.get('pretty'), 'upper') and request.args.get('pretty').upper() == 'TRUE':
        return True
    return False

def ok(result, msg="The request was successful", request=request, metadata={}):
    if not isinstance(metadata, dict):
        raise TypeError("Got exception formatting response. Metadata should be dict.")
    d = {'result': result,
         'status': 'success',
         'version': TAG,
         'message': msg,
         'metadata': metadata}
    return jsonify(d)

def error(result=None, msg="Error processing the request.", metadata={}):
    if not isinstance(metadata, dict):
        raise TypeError("Got exception formatting response. Metadata should be dict.")
    d = {'result': result,
         'status': 'error',
         'version': TAG,
         'message': msg,
         'metadata': metadata}
    return jsonify(d)

def handle_error(exc):
    if conf.show_traceback:
        logger.debug(f"building traceback for exception...")
        logger.debug(f"the type of exc is: {type(exc)}")
        try:
            raise exc
        except Exception:
            logger.debug("caught the re-raised exception.")
            try:
                msg = traceback.format_exc()
                logger.debug(f"got a msg variable; msg: {msg}")
            except Exception as e:
                logger.error(f"Got exception trying to format the exception! e: {e}")

    if isinstance(exc, BaseTapisError):
        response = error(msg=exc.msg)
        response.status_code = exc.code
        return response
    else:
        response = error(msg='Unrecognized exception type: {}. Exception: {}'.format(type(exc), exc))
        response.status_code = 500
        return response

def get_message_from_sql_exc(e):
    """
    Attempts to process a sqlalchemy exception and return a human-readable message.
    :param e: An sqlalchemy exception
    :return: (str) A human-readable messages.
    """
    logger.debug(f"Got exception trying to add tenant object to db; dir(e): {dir(e)}")
    logger.debug(f"_message: {e._message()}; ******detail: {e.detail}")
    try:
        msg = e._message().split('DETAIL:')[1].strip()
    except Exception as exp:
        logger.debug(f"Got exception trying to parse the sqlalchema message; falling back to _message(). exp: {exp}")
        try:
            msg = e._message()
        except Exception as exp2:
            logger.debug(f"Got exception just trying to use the _message() function. exp2: {exp2}")
            msg = "No extra details available."
    if isinstance(e, sqlalchemy.exc.IntegrityError):
        msg = f"This change would violate uniqueness constraints. Details: {msg}"
    return msg
