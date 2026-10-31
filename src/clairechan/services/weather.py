""" The weather of a city, from Open-Meteo, which needs no key. """
# Imports
import json
import urllib.error
import urllib.parse
import urllib.request

from stouputils.typing import JsonDict

from clairechan.i18n import tr

# Constants
GEOCODING: str = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST: str = "https://api.open-meteo.com/v1/forecast"
CONDITIONS: dict[str, dict[int, str]] = {
	"en": {
		0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast", 45: "fog", 48: "freezing fog",
		51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 61: "light rain", 63: "rain", 65: "heavy rain",
		71: "light snow", 73: "snow", 75: "heavy snow", 80: "showers", 81: "showers", 82: "heavy showers",
		95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with hail",
	},
	"fr": {
		0: "ciel dégagé", 1: "plutôt dégagé", 2: "partiellement nuageux", 3: "couvert", 45: "brouillard", 48: "brouillard givrant",
		51: "bruine légère", 53: "bruine", 55: "forte bruine", 61: "pluie faible", 63: "pluie", 65: "forte pluie",
		71: "neige faible", 73: "neige", 75: "forte neige", 80: "averses", 81: "averses", 82: "fortes averses",
		95: "orage", 96: "orage avec grêle", 99: "orage avec grêle",
	},
}
""" The WMO weather codes Open-Meteo reports, in words, by language. """


# Functions
def forecast(city: str) -> str:
	""" The weather now and for the day in the first city called `city`. """
	language = tr("en", "fr")
	try:
		places = get(GEOCODING, {"name": city, "count": 1, "language": language}).get("results")
		if not places:
			return tr(f"I can't find the city {city}.", f"Je ne trouve pas la ville {city}.")
		place = places[0]
		weather = get(FORECAST, {
			"latitude": place["latitude"], "longitude": place["longitude"], "timezone": "auto", "forecast_days": 1,
			"current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
			"daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
		})
	except urllib.error.URLError:
		return tr("I can't reach the weather service.", "Je n'arrive pas à joindre le service météo.")

	now, day = weather["current"], weather["daily"]
	sky = CONDITIONS[language].get(now["weather_code"], tr("changeable weather", "temps variable"))
	temperature, felt, wind = f"{now['temperature_2m']:.0f}", f"{now['apparent_temperature']:.0f}", f"{now['wind_speed_10m']:.0f}"
	low, high = f"{day['temperature_2m_min'][0]:.0f}", f"{day['temperature_2m_max'][0]:.0f}"
	rain = day["precipitation_probability_max"][0]
	return tr(
		f"{place['name']}: {sky}, {temperature} °C (feels like {felt}), wind {wind} km/h. "
		f"Today between {low} and {high} °C, {rain}% chance of rain.",
		f"{place['name']} : {sky}, {temperature} °C (ressenti {felt}), vent {wind} km/h. "
		f"Aujourd'hui entre {low} et {high} °C, {rain} % de risque de pluie.",
	)


def get(url: str, query: JsonDict) -> JsonDict:
	with urllib.request.urlopen(f"{url}?{urllib.parse.urlencode(query)}", timeout=10) as response:
		return json.load(response)

