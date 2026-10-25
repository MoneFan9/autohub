"""Fournisseurs de paiement.

Tant qu'aucun agrégateur n'est branché, FakeProvider reproduit les parcours les plus courants :

- Mobile Money (Airtel Money, Moov Money) : « demande de paiement » (request to pay). La plateforme envoie
  une demande au numéro du client, qui la valide sur son téléphone avec son code secret ; la plateforme
  interroge ensuite le statut (ou reçoit une notification). Un numéro finissant par 0000 simule un refus.
- Carte bancaire : paiement immédiat (en production, page de paiement hébergée du prestataire).
  4000 0000 0000 0002 simule un refus.
"""
import uuid

from django.conf import settings


class PaymentDeclined(Exception):
    pass


class FakeProvider:
    name = "fake"
    DECLINED_TOKEN = "tok_declined"

    def _ref(self, prefix):
        return f"{prefix}_{uuid.uuid4().hex[:16]}"

    def _declined(self, token):
        return token == self.DECLINED_TOKEN or token.endswith("_declined")

    # Paiement immédiat (carte, jetons de test)
    def charge(self, amount, token):
        if self._declined(token):
            raise PaymentDeclined("Paiement refusé.")
        return self._ref("ch")

    def refund(self, charge_ref, amount):
        return self._ref("re")

    # Mobile Money : demande de paiement puis statut
    def request_payment(self, amount, msisdn, method):
        return self._ref(f"{method}_req")

    def payment_status(self, ref, msisdn):
        digits = "".join(c for c in msisdn if c.isdigit())
        return "failed" if digits.endswith("0000") else "succeeded"


def get_provider():
    providers = {"fake": FakeProvider}
    return providers[settings.PAYMENT_PROVIDER]()
