""" The weather of a city, from Open-Meteo, which needs no key. """
# Imports
import json
import urllib.error
import urllib.parse
import urllib.request

from stouputils.typing import JsonDict

# Constants
GEOCODING: str = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST: str = "https://api.open-meteo.com/v1/forecast"
CONDITIONS: dict[int, str] = {
	0: "ciel dégagé", 1: "plutôt dégagé", 2: "partiellement nuageux", 3: "couvert", 45: "brouillard", 48: "brouillard givrant",
	51: "bruine légère", 53: "bruine", 55: "forte bruine", 61: "pluie faible", 63: "pluie", 65: "forte pluie",
	71: "neige faible", 73: "neige", 75: "forte neige", 80: "averses", 81: "averses", 82: "fortes averses",
	95: "orage", 96: "orage avec grêle", 99: "orage avec grêle",
}
""" The WMO weather codes Open-Meteo reports, in words. """


# Functions
def forecast(city: str) -> str:
	""" The weather now and for the day in the first city called `city`. """
	try:
		places = get(GEOCODING, {"name": city, "count": 1, "language": "fr"}).get("results")
		if not places:
			return f"Je ne trouve pas la ville {city}."
		place = places[0]
		weather = get(FORECAST, {
			"latitude": place["latitude"], "longitude": place["longitude"], "timezone": "auto", "forecast_days": 1,
			"current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
			"daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
		})
	except urllib.error.URLError:
		return "Je n'arrive pas à joindre le service météo."

	now, day = weather["current"], weather["daily"]
	return (
		f"{place['name']} : {CONDITIONS.get(now['weather_code'], 'temps variable')}, {now['temperature_2m']:.0f} °C "
		f"(ressenti {now['apparent_temperature']:.0f}), vent {now['wind_speed_10m']:.0f} km/h. "
		f"Aujourd'hui entre {day['temperature_2m_min'][0]:.0f} et {day['temperature_2m_max'][0]:.0f} °C, "
		f"{day['precipitation_probability_max'][0]} % de risque de pluie."
	)


def get(url: str, query: JsonDict) -> JsonDict:
	with urllib.request.urlopen(f"{url}?{urllib.parse.urlencode(query)}", timeout=10) as response:
		return json.load(response)

