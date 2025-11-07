from rest_framework.permissions import BasePermission


class IsAdminOrOwner(BasePermission):
    """Allow staff or the owning user."""
    
    def has_permission(self, request, view):
        """Allow any authenticated user; staff handled separately."""
        if not request.user or not request.user.is_authenticated:
            return False
        # Allow staff and authenticated users (view handles filtering)
        return True
    
    def has_object_permission(self, request, view, obj):
        """Allow staff or the user who owns the object."""
        if request.user.is_staff:
            return True

        if hasattr(obj, 'added_by_user'):
            return obj.added_by_user == request.user

        return obj.location.added_by_user == request.user

