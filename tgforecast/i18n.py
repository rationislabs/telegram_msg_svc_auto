"""Every word a visitor reads, in five languages. Pure tables. English matches stage 1's channel
post word for word; weather words follow the WMO code names Open-Meteo documents. Italian, French
and Spanish want a native speaker's read before the bot goes public."""

from __future__ import annotations

from datetime import date

LANGS = ("en", "de", "it", "fr", "es")

# (now, week, help) per language. Telegram commands: a-z, 0-9, _ only.
COMMANDS: dict[str, tuple[str, str, str]] = {
    "en": ("now", "week", "help"),
    "de": ("jetzt", "woche", "hilfe"),
    "it": ("ora", "settimana", "aiuto"),
    "fr": ("maintenant", "semaine", "aide"),
    "es": ("ahora", "semana", "ayuda"),
}

CREDITS = (
    '<a href="https://open-meteo.com/">Weather data by Open-Meteo.com</a> · '
    'places from <a href="https://www.geonames.org/">GeoNames</a>'
)

S: dict[str, dict[str, str]] = {
    "en": {
        "date_long": "{weekday} {day} {month}",
        "week_day": "{wd} {day}",
        "rain_chance": "rain chance {p} %",
        "wind_up_to": "wind up to {v} {unit}",
        "dry": "Dry all day",
        "rain_window": "Rain likely {start}–{stop}",
        "midnight": "midnight",
        "air_none": "Air: no reading today",
        "air": "Air: up to AQI {aqi} · {band}",
        "tomorrow": "Tomorrow: {low}–{high} {unit}, {outlook}",
        "showers": "showers likely ({p} %)",
        "unknown": "Unknown",
        "week_title": "{label} · next 7 days",
        "week_line": "{day} · {emoji} {low}–{high} {unit} · rain {p} % · wind {w} {wunit}",
        "chart_temp": "Temperature ({unit})",
        "chart_rain": "Chance of rain (%)",
        "chart_range": "Low and high ({unit})",
        "unknown_place": "I don't know a place called '{name}'.",
        "outage": "The weather service isn't answering right now — try again in a minute.",
        "throttled": "Too many questions — wait a minute.",
        "bad_city": "That doesn't look like a city. Try: /now Vienna",
        "crash": "Something went wrong — try again.",
        "too_many": "Up to 5 cities at once, separated by ;",
        "about_short": "Weather for any city: today with a chart, or the next 7 days. Nothing about you is stored.",
        "cmd_now": "Today's weather for a city",
        "cmd_week": "The next 7 days for a city",
        "cmd_help": "How to use this bot",
        "help": (
            "Weather for any city, from Open-Meteo.\n\n"
            "/now Vienna — today, with a chart\n"
            "/week Paris, Texas — the next 7 days\n"
            "/now Vienna; Graz — several cities at once (up to 5)\n"
            "Add °F for Fahrenheit. In a private chat you can also just type a city.\n\n"
            "The first reply after a pause can take about a minute: the bot wakes up first.\n"
            "No messages or ids are stored."
        ),
    },
    "de": {
        "date_long": "{weekday}, {day}. {month}",
        "week_day": "{wd} {day}.",
        "rain_chance": "Regenrisiko {p} %",
        "wind_up_to": "Wind bis {v} {unit}",
        "dry": "Den ganzen Tag trocken",
        "rain_window": "Regen wahrscheinlich {start}–{stop}",
        "midnight": "Mitternacht",
        "air_none": "Luft: heute kein Messwert",
        "air": "Luft: bis AQI {aqi} · {band}",
        "tomorrow": "Morgen: {low}–{high} {unit}, {outlook}",
        "showers": "Schauer wahrscheinlich ({p} %)",
        "unknown": "Unbekannt",
        "week_title": "{label} · die nächsten 7 Tage",
        "week_line": "{day} · {emoji} {low}–{high} {unit} · Regen {p} % · Wind {w} {wunit}",
        "chart_temp": "Temperatur ({unit})",
        "chart_rain": "Regenrisiko (%)",
        "chart_range": "Tiefst- und Höchstwert ({unit})",
        "unknown_place": "Ich kenne keinen Ort namens „{name}“.",
        "outage": "Der Wetterdienst antwortet gerade nicht – versuch es in einer Minute noch einmal.",
        "throttled": "Zu viele Fragen – warte eine Minute.",
        "bad_city": "Das sieht nicht nach einem Ort aus. Versuch: /jetzt Wien",
        "crash": "Da ist etwas schiefgegangen – versuch es noch einmal.",
        "too_many": "Bis zu 5 Orte auf einmal, getrennt durch ;",
        "about_short": "Wetter für jeden Ort: heute mit Diagramm oder die nächsten 7 Tage. Über dich wird nichts gespeichert.",
        "cmd_now": "Das Wetter heute für einen Ort",
        "cmd_week": "Die nächsten 7 Tage für einen Ort",
        "cmd_help": "So funktioniert der Bot",
        "help": (
            "Wetter für jeden Ort, von Open-Meteo.\n\n"
            "/jetzt Wien — heute, mit Diagramm\n"
            "/woche Paris, Texas — die nächsten 7 Tage\n"
            "/jetzt Wien; Graz — mehrere Orte auf einmal (bis zu 5)\n"
            "Mit °F gibt es Fahrenheit. Im privaten Chat genügt auch einfach ein Ortsname.\n\n"
            "Die erste Antwort nach einer Pause kann etwa eine Minute dauern: Der Bot wacht erst auf.\n"
            "Es werden keine Nachrichten oder IDs gespeichert."
        ),
    },
    "it": {
        "date_long": "{weekday} {day} {month}",
        "week_day": "{wd} {day}",
        "rain_chance": "probabilità di pioggia {p}%",
        "wind_up_to": "vento fino a {v} {unit}",
        "dry": "Asciutto tutto il giorno",
        "rain_window": "Pioggia probabile {start}–{stop}",
        "midnight": "mezzanotte",
        "air_none": "Aria: nessun dato oggi",
        "air": "Aria: fino a un AQI di {aqi} · {band}",
        "tomorrow": "Domani: {low}–{high} {unit}, {outlook}",
        "showers": "rovesci probabili ({p}%)",
        "unknown": "Sconosciuto",
        "week_title": "{label} · prossimi 7 giorni",
        "week_line": "{day} · {emoji} {low}–{high} {unit} · pioggia {p}% · vento {w} {wunit}",
        "chart_temp": "Temperatura ({unit})",
        "chart_rain": "Probabilità di pioggia (%)",
        "chart_range": "Minima e massima ({unit})",
        "unknown_place": "Non conosco nessun luogo chiamato «{name}».",
        "outage": "Il servizio meteo non risponde in questo momento: riprova tra un minuto.",
        "throttled": "Troppe domande: aspetta un minuto.",
        "bad_city": "Non sembra una città. Prova: /ora Roma",
        "crash": "Qualcosa è andato storto: riprova.",
        "too_many": "Al massimo 5 città alla volta, separate da ;",
        "about_short": "Il meteo di qualsiasi città: oggi con un grafico o i prossimi 7 giorni. Non viene salvato nulla su di te.",
        "cmd_now": "Il meteo di oggi per una città",
        "cmd_week": "I prossimi 7 giorni per una città",
        "cmd_help": "Come usare il bot",
        "help": (
            "Il meteo di qualsiasi città, con i dati di Open-Meteo.\n\n"
            "/ora Roma — oggi, con un grafico\n"
            "/settimana Paris, Texas — i prossimi 7 giorni\n"
            "/ora Roma; Milano — più città insieme (fino a 5)\n"
            "Aggiungi °F per i gradi Fahrenheit. In una chat privata puoi anche scrivere solo "
            "il nome di una città.\n\n"
            "La prima risposta dopo una pausa può richiedere circa un minuto: il bot deve prima "
            "svegliarsi.\n"
            "Nessun messaggio o ID viene salvato."
        ),
    },
    "fr": {
        "date_long": "{weekday} {day} {month}",
        "week_day": "{wd} {day}",
        "rain_chance": "risque de pluie {p} %",
        "wind_up_to": "vent jusqu'à {v} {unit}",
        "dry": "Sec toute la journée",
        "rain_window": "Pluie probable {start}–{stop}",
        "midnight": "minuit",
        "air_none": "Air : pas de mesure aujourd'hui",
        "air": "Air : jusqu'à un IQA de {aqi} · {band}",
        "tomorrow": "Demain : {low}–{high} {unit}, {outlook}",
        "showers": "averses probables ({p} %)",
        "unknown": "Inconnu",
        "week_title": "{label} · 7 prochains jours",
        "week_line": "{day} · {emoji} {low}–{high} {unit} · pluie {p} % · vent {w} {wunit}",
        "chart_temp": "Température ({unit})",
        "chart_rain": "Risque de pluie (%)",
        "chart_range": "Min. et max. ({unit})",
        "unknown_place": "Je ne connais pas de lieu appelé « {name} ».",
        "outage": "Le service météo ne répond pas pour le moment — réessayez dans une minute.",
        "throttled": "Trop de questions — attendez une minute.",
        "bad_city": "Cela ne ressemble pas à une ville. Essayez : /maintenant Paris",
        "crash": "Une erreur s'est produite — réessayez.",
        "too_many": "Jusqu'à 5 villes à la fois, séparées par ;",
        "about_short": "La météo de n'importe quelle ville : aujourd'hui avec un graphique ou les 7 prochains jours. Rien n'est conservé.",
        "cmd_now": "La météo du jour pour une ville",
        "cmd_week": "Les 7 prochains jours pour une ville",
        "cmd_help": "Comment utiliser ce bot",
        "help": (
            "La météo de n'importe quelle ville, avec les données d'Open-Meteo.\n\n"
            "/maintenant Paris — aujourd'hui, avec un graphique\n"
            "/semaine Paris, Texas — les 7 prochains jours\n"
            "/maintenant Paris; Lyon — plusieurs villes à la fois (jusqu'à 5)\n"
            "Ajoutez °F pour un affichage en Fahrenheit. En discussion privée, vous pouvez aussi "
            "simplement écrire le nom d'une ville.\n\n"
            "La première réponse après une pause peut prendre environ une minute : le bot doit "
            "d'abord se réveiller.\n"
            "Aucun message ni identifiant n'est conservé."
        ),
    },
    "es": {
        "date_long": "{weekday} {day} de {month}",
        "week_day": "{wd} {day}",
        "rain_chance": "probabilidad de lluvia {p} %",
        "wind_up_to": "viento de hasta {v} {unit}",
        "dry": "Seco todo el día",
        "rain_window": "Lluvia probable {start}–{stop}",
        "midnight": "medianoche",
        "air_none": "Aire: sin datos hoy",
        "air": "Aire: hasta un ICA de {aqi} · {band}",
        "tomorrow": "Mañana: {low}–{high} {unit}, {outlook}",
        "showers": "chubascos probables ({p} %)",
        "unknown": "Desconocido",
        "week_title": "{label} · próximos 7 días",
        "week_line": "{day} · {emoji} {low}–{high} {unit} · lluvia {p} % · viento {w} {wunit}",
        "chart_temp": "Temperatura ({unit})",
        "chart_rain": "Probabilidad de lluvia (%)",
        "chart_range": "Mínima y máxima ({unit})",
        "unknown_place": "No conozco ningún lugar llamado «{name}».",
        "outage": "El servicio meteorológico no responde ahora mismo; inténtalo de nuevo en un minuto.",
        "throttled": "Demasiadas preguntas: espera un minuto.",
        "bad_city": "Eso no parece una ciudad. Prueba: /ahora Madrid",
        "crash": "Algo salió mal; inténtalo de nuevo.",
        "too_many": "Hasta 5 ciudades a la vez, separadas por ;",
        "about_short": "El tiempo de cualquier ciudad: hoy con un gráfico o los próximos 7 días. No se guarda nada sobre ti.",
        "cmd_now": "El tiempo de hoy para una ciudad",
        "cmd_week": "Los próximos 7 días para una ciudad",
        "cmd_help": "Cómo usar este bot",
        "help": (
            "El tiempo de cualquier ciudad, con datos de Open-Meteo.\n\n"
            "/ahora Madrid — hoy, con un gráfico\n"
            "/semana Paris, Texas — los próximos 7 días\n"
            "/ahora Madrid; Sevilla — varias ciudades a la vez (hasta 5)\n"
            "Añade °F para grados Fahrenheit. En un chat privado también basta con escribir "
            "el nombre de una ciudad.\n\n"
            "La primera respuesta tras una pausa puede tardar alrededor de un minuto: el bot "
            "tiene que despertarse primero.\n"
            "No se guarda ningún mensaje ni identificador."
        ),
    },
}

# WMO codes; English lives in summary.WEATHER next to the emoji.
WEATHER_TEXT: dict[str, dict[int, str]] = {
    "de": {
        0: "Klar",
        1: "Überwiegend klar",
        2: "Teilweise bewölkt",
        3: "Bedeckt",
        45: "Nebel",
        48: "Gefrierender Nebel",
        51: "Leichter Nieselregen",
        53: "Nieselregen",
        55: "Starker Nieselregen",
        56: "Leichter gefrierender Nieselregen",
        57: "Gefrierender Nieselregen",
        61: "Leichter Regen",
        63: "Regen",
        65: "Starker Regen",
        66: "Leichter gefrierender Regen",
        67: "Gefrierender Regen",
        71: "Leichter Schneefall",
        73: "Schneefall",
        75: "Starker Schneefall",
        77: "Schneegriesel",
        80: "Leichte Schauer",
        81: "Schauer",
        82: "Heftige Schauer",
        85: "Leichte Schneeschauer",
        86: "Schneeschauer",
        95: "Gewitter",
        96: "Gewitter mit Hagel",
        99: "Gewitter mit starkem Hagel",
    },
    "it": {
        0: "Sereno",
        1: "Prevalentemente sereno",
        2: "Parzialmente nuvoloso",
        3: "Coperto",
        45: "Nebbia",
        48: "Nebbia gelata",
        51: "Pioviggine leggera",
        53: "Pioviggine",
        55: "Pioviggine intensa",
        56: "Pioviggine gelata leggera",
        57: "Pioviggine gelata",
        61: "Pioggia leggera",
        63: "Pioggia",
        65: "Pioggia forte",
        66: "Pioggia gelata leggera",
        67: "Pioggia gelata",
        71: "Neve leggera",
        73: "Neve",
        75: "Neve forte",
        77: "Neve granulosa",
        80: "Rovesci leggeri",
        81: "Rovesci",
        82: "Rovesci violenti",
        85: "Rovesci di neve leggeri",
        86: "Rovesci di neve",
        95: "Temporale",
        96: "Temporale con grandine",
        99: "Temporale con forte grandine",
    },
    "fr": {
        0: "Ciel dégagé",
        1: "Plutôt dégagé",
        2: "Partiellement nuageux",
        3: "Couvert",
        45: "Brouillard",
        48: "Brouillard givrant",
        51: "Bruine légère",
        53: "Bruine",
        55: "Forte bruine",
        56: "Bruine verglaçante légère",
        57: "Bruine verglaçante",
        61: "Pluie légère",
        63: "Pluie",
        65: "Forte pluie",
        66: "Pluie verglaçante légère",
        67: "Pluie verglaçante",
        71: "Neige légère",
        73: "Neige",
        75: "Neige forte",
        77: "Neige en grains",
        80: "Averses légères",
        81: "Averses",
        82: "Averses violentes",
        85: "Averses de neige légères",
        86: "Averses de neige",
        95: "Orage",
        96: "Orage avec grêle",
        99: "Orage avec forte grêle",
    },
    "es": {
        0: "Despejado",
        1: "Mayormente despejado",
        2: "Parcialmente nublado",
        3: "Cubierto",
        45: "Niebla",
        48: "Niebla helada",
        51: "Llovizna ligera",
        53: "Llovizna",
        55: "Llovizna intensa",
        56: "Llovizna helada ligera",
        57: "Llovizna helada",
        61: "Lluvia ligera",
        63: "Lluvia",
        65: "Lluvia intensa",
        66: "Lluvia helada ligera",
        67: "Lluvia helada",
        71: "Nevada ligera",
        73: "Nevada",
        75: "Nevada intensa",
        77: "Nieve granulada",
        80: "Chubascos ligeros",
        81: "Chubascos",
        82: "Chubascos violentos",
        85: "Chubascos de nieve ligeros",
        86: "Chubascos de nieve",
        95: "Tormenta",
        96: "Tormenta con granizo",
        99: "Tormenta con granizo fuerte",
    },
}

# European AQI bands, in summary.AQI_EDGES order, then the open top band.
AQI_NAMES: dict[str, tuple[str, ...]] = {
    "en": ("Good", "Fair", "Moderate", "Poor", "Very poor", "Extremely poor"),
    "de": ("Sehr gut", "Gut", "Mäßig", "Schlecht", "Sehr schlecht", "Extrem schlecht"),
    "it": ("Buona", "Discreta", "Moderata", "Scadente", "Molto scadente", "Estremamente scadente"),
    "fr": ("Bon", "Moyen", "Dégradé", "Mauvais", "Très mauvais", "Extrêmement mauvais"),
    "es": (
        "Buena",
        "Razonablemente buena",
        "Regular",
        "Desfavorable",
        "Muy desfavorable",
        "Extremadamente desfavorable",
    ),
}

WEEKDAYS: dict[str, tuple[str, ...]] = {
    "en": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
    "de": ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"),
    "it": ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"),
    "fr": ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"),
    "es": ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"),
}

WEEKDAYS_SHORT: dict[str, tuple[str, ...]] = {
    "en": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
    "de": ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"),
    "it": ("lun", "mar", "mer", "gio", "ven", "sab", "dom"),
    "fr": ("lun", "mar", "mer", "jeu", "ven", "sam", "dim"),
    "es": ("lun", "mar", "mié", "jue", "vie", "sáb", "dom"),
}

MONTHS: dict[str, tuple[str, ...]] = {
    "en": (
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ),
    "de": (
        "Januar",
        "Februar",
        "März",
        "April",
        "Mai",
        "Juni",
        "Juli",
        "August",
        "September",
        "Oktober",
        "November",
        "Dezember",
    ),
    "it": (
        "gennaio",
        "febbraio",
        "marzo",
        "aprile",
        "maggio",
        "giugno",
        "luglio",
        "agosto",
        "settembre",
        "ottobre",
        "novembre",
        "dicembre",
    ),
    "fr": (
        "janvier",
        "février",
        "mars",
        "avril",
        "mai",
        "juin",
        "juillet",
        "août",
        "septembre",
        "octobre",
        "novembre",
        "décembre",
    ),
    "es": (
        "enero",
        "febrero",
        "marzo",
        "abril",
        "mayo",
        "junio",
        "julio",
        "agosto",
        "septiembre",
        "octubre",
        "noviembre",
        "diciembre",
    ),
}


def pick(language_code: str | None) -> str:
    """Telegram's IETF tag ("de-AT", "es-419") → one of LANGS; anything else → English."""
    code = (language_code or "")[:2].lower()
    return code if code in LANGS else "en"


def t(lang: str, key: str, **values) -> str:
    return S[lang][key].format(**values)


def date_long(day: date, lang: str) -> str:
    return t(
        lang,
        "date_long",
        weekday=WEEKDAYS[lang][day.weekday()],
        day="1er" if lang == "fr" and day.day == 1 else day.day,
        month=MONTHS[lang][day.month - 1],
    )


def week_day(day: date, lang: str) -> str:
    return t(lang, "week_day", wd=WEEKDAYS_SHORT[lang][day.weekday()], day=day.day)


def help_text(lang: str) -> str:
    return f"{t(lang, 'help')}\n\n{CREDITS}"
