from functools import wraps
from inspect import isawaitable
from typing import (
    Callable,
    Optional,
    Type,
    Union,
    get_args,
    get_type_hints,
    get_origin,
)

from pydantic import ValidationError
from sanic import Request, json
from sanic.exceptions import SanicException

from sanic_ext.exceptions import InitError

from .setup import do_validation, generate_schema


def validate(
    json: Optional[Union[Callable[[Request], bool], Type[object]]] = None,
    form: Optional[Union[Callable[[Request], bool], Type[object]]] = None,
    query: Optional[Union[Callable[[Request], bool], Type[object]]] = None,
    body_argument: str = "body",
    query_argument: str = "query",
):

    schemas = {
        key: generate_schema(param)
        for key, param in (
            ("json", json),
            ("form", form),
            ("query", query),
        )
    }

    if json and form:
        raise InitError("Cannot define both a form and json route validator")

    def decorator(f):
        @wraps(f)
        async def decorated_function(*args, **kwargs):

            if args and isinstance(args[0], Request):
                request: Request = args[0]
            elif len(args) > 1:
                request: Request = args[1]
            else:
                raise SanicException("Request could not be found")

            if schemas["json"]:
                await do_validation(
                    model=json,
                    data=request.json,
                    schema=schemas["json"],
                    request=request,
                    kwargs=kwargs,
                    body_argument=body_argument,
                    allow_multiple=False,
                    allow_coerce=False,
                )
            elif schemas["form"]:
                await do_validation(
                    model=form,
                    data=request.form,
                    schema=schemas["form"],
                    request=request,
                    kwargs=kwargs,
                    body_argument=body_argument,
                    allow_multiple=True,
                    allow_coerce=False,
                )
            elif schemas["query"]:
                await do_validation(
                    model=query,
                    data=request.args,
                    schema=schemas["query"],
                    request=request,
                    kwargs=kwargs,
                    body_argument=query_argument,
                    allow_multiple=True,
                    allow_coerce=True,
                )
            retval = f(*args, **kwargs)
            if isawaitable(retval):
                retval = await retval
            return retval

        return decorated_function

    return decorator


ARRAY_TYPES = {list, tuple}


def has_array_type(hint_value):
    list_args = get_args(hint_value)
    if not list_args:
        return

    for args in list_args:
        if get_origin(args) in ARRAY_TYPES:
            return True


def clean_data(schema, raw_data):
    hints = get_type_hints(schema)
    data = {}

    for hint_key, hint_value in hints.items():
        is_array = has_array_type(hint_value)
        if is_array:
            value = raw_data.getlist(hint_key)
        else:
            value = raw_data.get(hint_key)

        data[hint_key] = value

    return data


def validate_schema(
        body: Optional[Union[Callable[[Request], bool], Type[object]]] = None,
        query: Optional[Union[Callable[[Request], bool], Type[object]]] = None
):
    """
    Simple validation
    """

    def decorator(f):
        @wraps(f)
        async def decorated_function(*args, **kwargs):
            if args and isinstance(args[0], Request):
                request: Request = args[0]
            elif len(args) > 1:
                request: Request = args[1]
            else:
                raise SanicException("Request could not be found")

            try:
                context = {
                    "request": request,
                }
                if query:
                    cleaned_data = clean_data(
                        query,
                        request.args,
                    )
                    cleaned_data["context"] = context
                    kwargs["query"] = query(
                        **cleaned_data,
                    )
                if body:
                    cleaned_data = clean_data(
                        body,
                        request.form,
                    )

                    if kwargs.get("query"):
                        context["query"] = kwargs["query"]

                    cleaned_data["context"] = context
                    kwargs["body"] = body(**cleaned_data)
            except ValidationError as err:
                return json(
                    {
                        "detail": {
                            error["loc"][0]: error["msg"] for error in err.errors()
                        }
                    },
                    status=400
                )
            retval = f(*args, **kwargs)
            if isawaitable(retval):
                retval = await retval
            return retval

        return decorated_function

    return decorator
