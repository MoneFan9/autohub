"""Fournisseurs de paiement. V1 : FakeProvider. V2 : StripeProvider (PaymentIntent capture_method=manual pour la caution)."""
import uuid

from django.conf import settings


class PaymentDeclined(Exception):
    pass


class FakeProvider:
    name = "fake"
    # Même convention que Stripe en mode test.
    DECLINED_TOKEN = "tok_declined"

    def _ref(self, prefix):
        return f"{prefix}_{uuid.uuid4().hex[:16]}"

    def charge(self, amount, token):
        if token == self.DECLINED_TOKEN:
            raise PaymentDeclined("Carte refusée.")
        return self._ref("ch")

    def hold(self, amount, token):
        if token == self.DECLINED_TOKEN:
            raise PaymentDeclined("Carte refusée.")
        return self._ref("pi")

    def release(self, hold_ref):
        return self._ref("rel")

    def refund(self, charge_ref, amount):
        return self._ref("re")


def get_provider():
    providers = {"fake": FakeProvider}
    return providers[settings.PAYMENT_PROVIDER]()
