from .roles import is_owner, is_seller, seller_of


def roles(request):
    user = request.user
    return {"is_seller": is_seller(user), "is_owner": is_owner(user), "my_seller": seller_of(user)}
