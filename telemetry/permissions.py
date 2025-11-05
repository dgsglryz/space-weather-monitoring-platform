from rest_framework.permissions import BasePermission

class IsAdminOrOwner(BasePermission):
    def has_object_permission(self,request,view,obj):
        if request.user.is_staff:
            return True

        if hasattr(obj,'added_by_user'):
            return obj.added_by_user == request.user

        return obj.location.added_by_user == request.user

