from .models import Customer


def customer_for_user(user, data):
    """Fiche conducteur d'un membre : il la remplit et la met à jour lui-même."""
    customer, _ = Customer.objects.update_or_create(user=user, defaults={**data, "email": user.email or user.username})
    return customer
