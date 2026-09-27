from rest_framework.permissions import BasePermission


class HasRole(BasePermission):
    """Allow users whose company membership has one of `roles`."""

    def __init__(self, roles):
        self.roles = roles

    def has_permission(self, request, view):
        membership = getattr(request.user, "membership", None)
        return membership is not None and membership.role in self.roles
