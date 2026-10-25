"""Fournisseurs de paiement. V1 : FakeProvider. V2 : StripeProvider (PaymentIntent capture_method=manual pour la caution)."""
import uuid

from django.conf import settings


class PaymentDeclined(Exception):
    pass


class FakeProvider:
    name = "fake"
    # Jeton « tok_declined » ou « <moyen>_declined » : paiement refusé (tests et démo).
    DECLINED_TOKEN = "tok_declined"

    def _declined(self, token):
        return token == self.DECLINED_TOKEN or token.endswith("_declined")

    def _ref(self, prefix):
        return f"{prefix}_{uuid.uuid4().hex[:16]}"

    def charge(self, amount, token):
        if self._declined(token):
            raise PaymentDeclined("Paiement refusé.")
        return self._ref("ch")

    def hold(self, amount, token):
        if self._declined(token):
            raise PaymentDeclined("Paiement refusé.")
        return self._ref("pi")

    def release(self, hold_ref):
        return self._ref("rel")

    def refund(self, charge_ref, amount):
        return self._ref("re")


def get_provider():
    providers = {"fake": FakeProvider}
    return providers[settings.PAYMENT_PROVIDER]()
