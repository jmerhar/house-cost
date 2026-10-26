"""The words of every notification, in each language the interface has.

A notification is written in its recipient's language: the one set on their account, else
English. Amounts and dates are written as that language writes them.
"""

from datetime import date

#: Each message's title and body, by language. Placeholders are filled in by name.
CATALOGUE: dict[str, dict[str, tuple[str, str]]] = {
    "en": {
        "new_bill": (
            "New bill: {supplier}, {amount}",
            "{person} added a bill from {supplier} dated {date}: {amount}, of which your "
            "household's share is {share}.",
        ),
        "price_change": (
            "{supplier} changed its price",
            "The {quantity} price on the bill of {date} is {new} per {unit}, compared with {old} "
            "on the bill before.",
        ),
        "contract_ends": (
            "{service} {ends} {when}",
            "{service} with {supplier} {ends} on {date}. {notice}",
        ),
        "lock_in_ends": (
            "{service}: minimum term ends {when}",
            "The minimum term of {service} with {supplier} ends on {date}; leaving after that "
            "has no penalty.",
        ),
        "missing_bill": (
            "No bill from {supplier} yet",
            "The last bill for {service} was dated {date}, and one usually comes {every}.",
        ),
        "test": ("Test notification", "Notifications from House costs reach you here."),
    },
    "pt-PT": {
        "new_bill": (
            "Nova fatura: {supplier}, {amount}",
            "{person} adicionou uma fatura de {supplier} com data de {date}: {amount}, cabendo à "
            "sua família {share}.",
        ),
        "price_change": (
            "{supplier} alterou o preço",
            "O preço da {quantity} na fatura de {date} é {new}/{unit}, face a {old}/{unit} "
            "na fatura anterior.",
        ),
        "contract_ends": (
            "O contrato de {service} {ends} {when}",
            "O contrato de {service} com {supplier} {ends} a {date}. {notice}",
        ),
        "lock_in_ends": (
            "{service}: a fidelização termina {when}",
            "A fidelização do contrato de {service} com {supplier} termina a {date}; a partir "
            "daí, pode sair sem custos.",
        ),
        "missing_bill": (
            "Ainda não chegou a fatura de {supplier}",
            "A última fatura de {service} tem data de {date} e costuma chegar uma {every}.",
        ),
        "test": ("Notificação de teste", "Vai receber aqui as notificações das Despesas da casa."),
    },
}

#: Words a message fills in that themselves depend on the language.
WORDS: dict[str, dict[str, str]] = {
    "en": {
        "electricity_kwh": "electricity",
        "water_m3": "water",
        "renews": "renews",
        "ends": "ends",
        "notice": "You must give notice of {days} to leave.",
        "notice_unknown": "Check the contract for the notice needed to leave.",
        "day": "{n} day",
        "days": "{n} days",
        "daily": "every day",
        "every": "every {n} days",
        "today": "today",
        "tomorrow": "tomorrow",
        "within": "in {n} days",
    },
    "pt-PT": {
        "electricity_kwh": "eletricidade",
        "water_m3": "água",
        "renews": "renova-se",
        "ends": "termina",
        "notice": "Para rescindir, é preciso avisar com {days} de antecedência.",
        "notice_unknown": "Confirme no contrato o pré-aviso necessário para o cancelar.",
        "day": "{n} dia",
        "days": "{n} dias",
        "daily": "por dia",
        "every": "a cada {n} dias",
        "today": "hoje",
        "tomorrow": "amanhã",
        "within": "daqui a {n} dias",
    },
}

MONTHS_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def language(chosen: str | None) -> str:
    """The catalogue's language for a person's choice, English when they have none."""
    return chosen if chosen in CATALOGUE else "en"


def money(cents: int, lang: str) -> str:
    """Cents as euros: "€1,234.56" in English, "1234,56 €" in Portuguese."""
    sign = "-" if cents < 0 else ""
    whole, fraction = divmod(abs(cents), 100)
    if lang == "pt-PT":
        return f"{sign}{whole},{fraction:02d} €"
    return f"{sign}€{whole:,}.{fraction:02d}"


def day(on: date, lang: str) -> str:
    """A date day first: "18 Oct 2026" in English, "18/10/2026" in Portuguese."""
    if lang == "pt-PT":
        return on.strftime("%d/%m/%Y")
    return f"{on.day} {MONTHS_EN[on.month - 1]} {on.year}"


def price(euros: float, lang: str) -> str:
    """A unit price to four decimals: "€0.1525" in English, "0,1525 €" in Portuguese."""
    if lang == "pt-PT":
        return f"{euros:.4f}".replace(".", ",") + " €"
    return f"€{euros:.4f}"


def days(n: int, lang: str) -> str:
    """A number of days: "1 day", "30 days"."""
    return WORDS[lang]["day" if n == 1 else "days"].format(n=n)


def every(n: int, lang: str) -> str:
    """How often something comes: "every day", "every 30 days"."""
    return WORDS[lang]["daily"] if n == 1 else WORDS[lang]["every"].format(n=n)


def notice(n: int | None, lang: str) -> str:
    """The sentence on the notice needed to leave, or on checking the contract for it."""
    if n is None:
        return WORDS[lang]["notice_unknown"]
    return WORDS[lang]["notice"].format(days=days(n, lang))


def within(n: int, lang: str) -> str:
    """When something n days ahead happens: "today", "tomorrow" or "in 7 days"."""
    if n == 0:
        return WORDS[lang]["today"]
    if n == 1:
        return WORDS[lang]["tomorrow"]
    return WORDS[lang]["within"].format(n=n)


def word(key: str, lang: str) -> str:
    """A word a message fills in, in ``lang``."""
    return WORDS[lang][key]


def render(event: str, lang: str, **values: object) -> tuple[str, str]:
    """A message's title and body in ``lang``, with its placeholders filled in."""
    title, body = CATALOGUE[lang][event]
    return title.format(**values), body.format(**values)
