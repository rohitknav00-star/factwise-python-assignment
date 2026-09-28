import json
from functools import wraps

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from exceptions import ApplicationError


def api_view(handler):
    """
    Wrap a plain function ``handler(request_body: str) -> str`` (the shape
    every UserBase/TeamBase/ProjectBoardBase method has) into a Django
    view.

    * GET requests are treated as having an empty JSON object body, so
      argument-less methods (list_users, list_teams, ...) work with a
      plain GET.
    * POST requests pass their raw body straight through as the request
      string the underlying API expects.
    * ApplicationError subclasses are turned into a JSON error body with
      the matching HTTP status code; anything else becomes a 500 so a bug
      never leaks a stack trace to the caller.
    """

    @csrf_exempt
    @wraps(handler)
    def view(request, *args, **kwargs):
        body = request.body.decode("utf-8") if request.body else "{}"
        try:
            result = handler(body)
            return HttpResponse(result, content_type="application/json")
        except ApplicationError as exc:
            return JsonResponse({"error": str(exc)}, status=exc.status_code)
        except (json.JSONDecodeError, TypeError, KeyError) as exc:
            return JsonResponse({"error": f"invalid request: {exc}"}, status=400)

    return view
