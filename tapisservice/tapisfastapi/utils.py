import os
import traceback

from contextvars import ContextVar, Token
from typing import Any, Dict
from starlette.types import ASGIApp, Receive, Scope, Send

from tapisservice.config import conf
from tapisservice.errors import BaseTapisError
from tapisservice.logs import get_logger
logger = get_logger(__name__)

TAG = conf.version

def ok(result, msg="The request was successful", metadata={}):
    if not isinstance(metadata, dict):
        raise TypeError("Got exception formatting response. Metadata should be dict.")
    d = {'result': result,
         'status': 'success',
         'version': TAG,
         'message': msg,
         'metadata': metadata}
    return d

def error(result=None, msg="Error processing the request.", metadata={}):
    if not isinstance(metadata, dict):
        raise TypeError("Got exception formatting response. Metadata should be dict.")
    d = {'result': result,
         'status': 'error',
         'version': TAG,
         'message': msg,
         'metadata': metadata}
    return d

class Globals:
    """
    Class required to setup GlobalsMiddleware
    """
    __slots__ = ("_vars", "_reset_tokens")

    _vars: Dict[str, ContextVar]
    _reset_tokens: Dict[str, Token]

    def __init__(self) -> None:
        object.__setattr__(self, '_vars', {})
        object.__setattr__(self, '_reset_tokens', {})

    def reset(self) -> None:
        for _name, var in self._vars.items():
            try:
                var.reset(self._reset_tokens[_name])
            # ValueError will be thrown if the reset() happens in
            # a different context compared to the original set().
            # Then just set to None for this new context.
            except ValueError:
                var.set(None)

    def _ensure_var(self, item: str) -> None:
        if item not in self._vars:
            self._vars[item] = ContextVar(f"globals:{item}", default=None)
            self._reset_tokens[item] = self._vars[item].set(None)

    def __getattr__(self, item: str) -> Any:
        self._ensure_var(item)
        return self._vars[item].get()

    def __setattr__(self, item: str, value: Any) -> None:
        self._ensure_var(item)
        self._vars[item].set(value)

class GlobalsMiddleware:
    """
    https://gist.github.com/ddanier/ead419826ac6c3d75c96f9d89bea9bd0
    This allows to use global variables inside the FastAPI application using async mode.

    # Usage:
    import g
    g.foo = "bar
    print(g.foo) # prints 'bar'
    print(g.notset) # prints None

    # Setup - Add the `GlobalsMiddleware` to your app:
    api = FastAPI(title="kgservice",
                  debug=False,
                  exception_handlers={Exception: error_handler},
                  middleware=[
                    Middleware(GlobalsMiddleware),
                    Middleware(TapisMiddleware)
                  ])
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        g.reset()
        await self.app(scope, receive, send)

g = Globals()
