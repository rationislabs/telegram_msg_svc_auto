import pytest

from tgforecast.ask import Ask, parse

BOT = "WeatherAnswerBot"


@pytest.mark.parametrize(
    "text, lc, private, want",
    [
        ("/start", "en", True, Ask("help", "en")),
        ("/help", "de", True, Ask("help", "de")),
        ("/hilfe", "en", True, Ask("help", "de")),
        ("/aiuto", None, True, Ask("help", "it")),
        ("/aide", None, True, Ask("help", "fr")),
        ("/ayuda", None, True, Ask("help", "es")),
        ("/now Graz", "en", True, Ask("now", "en", "Graz")),
        ("/now Graz", "de-AT", True, Ask("now", "de", "Graz")),
        ("Graz", "en", True, Ask("now", "en", "Graz")),
        ("  graz  ", "en", True, Ask("now", "en", "graz")),
        ("Graz", "en", False, None),  # plain text in a group: not ours
        ("/week Graz", "en", True, Ask("week", "en", "Graz")),
        ("/jetzt Wien", "en", True, Ask("now", "de", "Wien")),
        ("/woche Wien", "fr", True, Ask("week", "de", "Wien")),
        ("/ora Roma", None, True, Ask("now", "it", "Roma")),
        ("/settimana Roma", None, True, Ask("week", "it", "Roma")),
        ("/maintenant Lyon", None, True, Ask("now", "fr", "Lyon")),
        ("/semaine Lyon", None, True, Ask("week", "fr", "Lyon")),
        ("/ahora Madrid", None, True, Ask("now", "es", "Madrid")),
        ("/semana Madrid", None, True, Ask("week", "es", "Madrid")),
        ("/NOW Graz", "en", True, Ask("now", "en", "Graz")),
        ("/now Miami °F", "en", True, Ask("now", "en", "Miami", units="imperial")),
        ("/week miami imperial", "en", True, Ask("week", "en", "miami", units="imperial")),
        ("/now Miami F", "en", True, Ask("now", "en", "Miami", units="imperial")),
        ("/now Miami FAHRENHEIT", "en", True, Ask("now", "en", "Miami", units="imperial")),
        ("/now Vienna °C", "en", True, Ask("now", "en", "Vienna")),
        ("/now Vienna metric", "en", True, Ask("now", "en", "Vienna")),
        ("/now Madrid ºF", "es", True, Ask("now", "es", "Madrid", units="imperial")),
        ("/now °C", "en", True, Ask("help", "en")),
        ("/now Paris, Texas", "en", True, Ask("now", "en", "Paris", "Texas")),
        ("/now Paris, Texas °F", "en", True, Ask("now", "en", "Paris", "Texas", "imperial")),
        ("/now New York", "en", True, Ask("now", "en", "New York")),
        ("/now@WeatherAnswerBot Graz", "en", False, Ask("now", "en", "Graz")),
        ("/now@weatheranswerbot Graz", "en", False, Ask("now", "en", "Graz")),
        ("/now@OtherBot Graz", "en", False, None),
        ("/now Graz", "en", False, Ask("now", "en", "Graz")),
        ("/now", "en", True, Ask("help", "en")),
        ("/jetzt", "en", True, Ask("help", "de")),
        ("/now °F", "en", True, Ask("help", "en")),
        ("/now 12345", "en", True, Ask("bad", "en")),
        ("/now " + "a" * 101, "en", True, Ask("bad", "en")),
        ("/now , Texas", "en", True, Ask("bad", "en")),
        ("/now Москва", "ru", True, Ask("now", "en", "Москва")),
        ("東京", "ja", True, Ask("now", "en", "東京")),
        ("/unknown", "en", True, Ask("help", "en")),
        ("/unknown", "en", False, None),
        ("/", "en", True, Ask("help", "en")),
        ("", "en", True, None),
        ("   ", "en", True, None),
        ("/now\nGraz", "en", True, Ask("now", "en", "Graz")),
    ],
)
def test_parse(text, lc, private, want):
    assert parse(text, lc, private, BOT) == want
