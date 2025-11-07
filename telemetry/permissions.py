from rest_framework.permissions import BasePermission


class IsAdminOrOwner(BasePermission):
    """Permission class that allows staff or object owners.
    
    For list endpoints: allows staff and authenticated users (views must filter querysets).
    For object endpoints: checks if user is staff or owns the object.
    """
    
    def has_permission(self, request, view):
        """Check list-level permission.
        
        Allows staff and authenticated users. Views using this permission
        must filter querysets to ensure users only see their own data.
        """
        if not request.user or not request.user.is_authenticated:
            return False
        # Allow staff and authenticated users (view handles filtering)
        return True
    
    def has_object_permission(self, request, view, obj):
        """Check object-level permission.
        
        Allows staff or object owners. For objects with 'added_by_user',
        checks direct ownership. For objects with 'location', checks location ownership.
        """
        if request.user.is_staff:
            return True

        if hasattr(obj, 'added_by_user'):
            return obj.added_by_user == request.user

        return obj.location.added_by_user == request.user

