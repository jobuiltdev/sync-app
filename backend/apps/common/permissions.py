"""Shared authorization primitives."""

from typing import TYPE_CHECKING, Any, cast

from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

if TYPE_CHECKING:
    from apps.accounts.models import User


def authenticated_user(request: Request) -> User:
    """Narrows request.user to the concrete User.

    Every caller sits behind IsAuthenticated, so the anonymous case is already
    unreachable. This states that for the type checker rather than adding a runtime
    branch that could never be taken and would never be tested.
    """
    return cast("User", request.user)


class IsOwner(BasePermission):
    """Allows access only to the user an object belongs to.

    Object permissions are a second line, not the first. Views scope their queryset
    to the requesting user, so a stranger's object is a 404 rather than a 403 and
    the API does not confirm that the id exists. This catches anything that reaches
    an object by another route.
    """

    owner_field = "user"

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        owner = getattr(obj, getattr(view, "owner_field", self.owner_field), None)
        return owner is not None and owner == request.user
