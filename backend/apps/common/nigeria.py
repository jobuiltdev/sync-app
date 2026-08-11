"""Nigerian administrative constants.

Lives in common because both a customer's address and a provider's service area
need the same list, and neither app owns it.
"""

from django.db import models


class NigerianState(models.TextChoices):
    """The 36 states plus the Federal Capital Territory.

    Stored as the readable code rather than an integer so a row is legible in the
    database and in a support conversation without a lookup table.
    """

    ABIA = "ABIA", "Abia"
    ADAMAWA = "ADAMAWA", "Adamawa"
    AKWA_IBOM = "AKWA_IBOM", "Akwa Ibom"
    ANAMBRA = "ANAMBRA", "Anambra"
    BAUCHI = "BAUCHI", "Bauchi"
    BAYELSA = "BAYELSA", "Bayelsa"
    BENUE = "BENUE", "Benue"
    BORNO = "BORNO", "Borno"
    CROSS_RIVER = "CROSS_RIVER", "Cross River"
    DELTA = "DELTA", "Delta"
    EBONYI = "EBONYI", "Ebonyi"
    EDO = "EDO", "Edo"
    EKITI = "EKITI", "Ekiti"
    ENUGU = "ENUGU", "Enugu"
    FCT = "FCT", "Federal Capital Territory"
    GOMBE = "GOMBE", "Gombe"
    IMO = "IMO", "Imo"
    JIGAWA = "JIGAWA", "Jigawa"
    KADUNA = "KADUNA", "Kaduna"
    KANO = "KANO", "Kano"
    KATSINA = "KATSINA", "Katsina"
    KEBBI = "KEBBI", "Kebbi"
    KOGI = "KOGI", "Kogi"
    KWARA = "KWARA", "Kwara"
    LAGOS = "LAGOS", "Lagos"
    NASARAWA = "NASARAWA", "Nasarawa"
    NIGER = "NIGER", "Niger"
    OGUN = "OGUN", "Ogun"
    ONDO = "ONDO", "Ondo"
    OSUN = "OSUN", "Osun"
    OYO = "OYO", "Oyo"
    PLATEAU = "PLATEAU", "Plateau"
    RIVERS = "RIVERS", "Rivers"
    SOKOTO = "SOKOTO", "Sokoto"
    TARABA = "TARABA", "Taraba"
    YOBE = "YOBE", "Yobe"
    ZAMFARA = "ZAMFARA", "Zamfara"
