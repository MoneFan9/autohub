from .roles import is_agency_member, is_owner


def roles(request):
    user = request.user
    return {"is_agency": is_agency_member(user), "is_owner": is_owner(user)}
