from .models import Customer


class CustomerMismatch(Exception):
    pass


def customer_for_user(user, data):
    """Fiche conducteur d'un membre : il la remplit et la met à jour lui-même."""
    customer, _ = Customer.objects.update_or_create(user=user, defaults={**data, "email": user.email or user.username})
    return customer


def get_or_create_customer(data):
    """Un client existant n'est jamais modifié par un formulaire public : on vérifie son identité."""
    email = data["email"].lower()
    customer, created = Customer.objects.get_or_create(email=email, defaults={**data, "email": email})
    if not created and (customer.license_number != data["license_number"] or customer.birth_date != data["birth_date"]):
        raise CustomerMismatch("Ces informations ne correspondent pas au compte existant pour cet email.")
    return customer
