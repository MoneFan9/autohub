from decimal import Decimal

from django.conf import settings

from .roles import is_owner, is_seller, seller_of


def roles(request):
    user = request.user
    pct = (Decimal(settings.PLATFORM_FEE_RATE) * 100).normalize()
    return {"is_seller": is_seller(user), "is_owner": is_owner(user), "my_seller": seller_of(user),
            "platform_fee_pct": f"{pct:f}".replace(".", ",")}
