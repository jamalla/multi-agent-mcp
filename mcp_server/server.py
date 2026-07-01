import os
import asyncio
import httpx
from dotenv import load_dotenv
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

load_dotenv()  # local dev reads .env; on Render the env var is set in the dashboard

mcp = FastMCP("multi-source-server")


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    """Lightweight health check for hosting platforms (e.g. Render)."""
    return JSONResponse({"status": "ok"})

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


# ---------- API 1: Open-Meteo (weather) ----------

@mcp.tool()
async def weather_geocode(city: str) -> dict:
    """Find latitude/longitude for a city name."""
    async with httpx.AsyncClient() as client:
        r = await client.get(GEOCODE_URL, params={"name": city, "count": 1})
        r.raise_for_status()
        data = r.json()
    if not data.get("results"):
        return {"error": f"No location found for '{city}'"}
    top = data["results"][0]
    return {
        "name": top["name"],
        "country": top.get("country"),
        "latitude": top["latitude"],
        "longitude": top["longitude"],
    }


@mcp.tool()
async def weather_current(latitude: float, longitude: float) -> dict:
    """Get current weather for a latitude/longitude."""
    async with httpx.AsyncClient() as client:
        r = await client.get(FORECAST_URL, params={
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,wind_speed_10m,relative_humidity_2m",
        })
        r.raise_for_status()
        return r.json().get("current", {})


# ---------- API 2: CountriesNow ----------
# restcountries.com/v3.1 is deprecated; countriesnow.space is the replacement.

COUNTRIES_URL = "https://countriesnow.space/api/v0.1"


async def _fetch_info_field(field: str) -> list[dict]:
    """Fetch all countries with one selected field from the info endpoint."""
    async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
        r = await client.get(f"{COUNTRIES_URL}/countries/info", params={"returns": field})
        r.raise_for_status()
        return r.json().get("data", [])


def _find_country(records: list[dict], name: str) -> dict | None:
    name_lower = name.lower()
    return next((r for r in records if r.get("name", "").lower() == name_lower), None)


@mcp.tool()
async def country_capital(name: str) -> dict:
    """Get the capital city of a country."""
    records = await _fetch_info_field("capital")
    c = _find_country(records, name)
    if not c:
        return {"error": f"No country found for '{name}'"}
    return {"country": c["name"], "capital": c.get("capital")}


@mcp.tool()
async def country_currency(name: str) -> dict:
    """Get the currency code used in a country."""
    records = await _fetch_info_field("currency")
    c = _find_country(records, name)
    if not c:
        return {"error": f"No country found for '{name}'"}
    return {"country": c["name"], "currency": c.get("currency")}


@mcp.tool()
async def country_population(name: str) -> dict:
    """Get the most recent population figure for a country."""
    async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
        r = await client.get(f"{COUNTRIES_URL}/countries/population/q", params={"country": name})
        if r.status_code == 404:
            return {"error": f"No country found for '{name}'"}
        r.raise_for_status()
        counts = r.json().get("data", {}).get("populationCounts", [])
    if not counts:
        return {"error": "No population data available"}
    latest = max(counts, key=lambda x: x["year"])
    return {"country": name, "year": latest["year"], "population": latest["value"]}


@mcp.tool()
async def country_dial_code(name: str) -> dict:
    """Get the international dialling code for a country."""
    records = await _fetch_info_field("dialCode")
    c = _find_country(records, name)
    if not c:
        return {"error": f"No country found for '{name}'"}
    return {"country": c["name"], "dial_code": c.get("dialCode")}


@mcp.tool()
async def country_flag(name: str) -> dict:
    """Get the Unicode flag emoji for a country."""
    records = await _fetch_info_field("unicodeFlag")
    c = _find_country(records, name)
    if not c:
        return {"error": f"No country found for '{name}'"}
    return {"country": c["name"], "flag": c.get("unicodeFlag")}


# ---------- API 3: football-data.org (FIFA World Cup 2026) ----------
# Needs a free API key from football-data.org, read from FOOTBALL_API_KEY.

FOOTBALL_URL = "https://api.football-data.org/v4"
WC = "WC"  # FIFA World Cup competition code


async def _football_get(path: str, params: dict | None = None) -> dict:
    """Shared helper for football-data.org calls with graceful key/limit handling.
    Retries once on a transient disconnect (the free tier sometimes drops rapid calls)."""
    key = os.getenv("FOOTBALL_API_KEY", "")
    if not key:
        return {"error": "FOOTBALL_API_KEY is not set on the server."}
    last_exc = None
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(f"{FOOTBALL_URL}{path}",
                                     headers={"X-Auth-Token": key}, params=params or {})
            if r.status_code in (401, 403):
                return {"error": "football-data.org rejected the request (invalid key or plan restriction)."}
            if r.status_code == 429:
                return {"error": "Rate limited by football-data.org (free tier is 10 requests/min); try again shortly."}
            r.raise_for_status()
            return r.json()
        except (httpx.RemoteProtocolError, httpx.ReadError, httpx.ConnectError) as e:
            last_exc = e
            await asyncio.sleep(1.5)
    return {"error": f"football-data.org connection failed after retry: {last_exc}"}


def _fmt_match(m: dict) -> dict:
    score = m.get("score", {}).get("fullTime", {})
    home, away = score.get("home"), score.get("away")
    return {
        "id": m.get("id"),
        "utcDate": m.get("utcDate"),
        "status": m.get("status"),
        "stage": m.get("stage"),
        "group": m.get("group"),
        "home": m.get("homeTeam", {}).get("name"),
        "away": m.get("awayTeam", {}).get("name"),
        "score": f"{home}-{away}" if home is not None else None,
    }


@mcp.tool()
async def worldcup_matches_upcoming(limit: int = 10) -> dict:
    """List upcoming (scheduled) FIFA World Cup matches."""
    data = await _football_get(f"/competitions/{WC}/matches", {"status": "SCHEDULED"})
    if "error" in data:
        return data
    matches = [_fmt_match(m) for m in data.get("matches", [])][:limit]
    return {"count": len(matches), "matches": matches}


@mcp.tool()
async def worldcup_match_results(limit: int = 10) -> dict:
    """List the most recent finished FIFA World Cup match results."""
    data = await _football_get(f"/competitions/{WC}/matches", {"status": "FINISHED"})
    if "error" in data:
        return data
    matches = [_fmt_match(m) for m in data.get("matches", [])][-limit:]
    return {"count": len(matches), "matches": matches}


@mcp.tool()
async def worldcup_group_standings() -> dict:
    """Get FIFA World Cup group standings (group-stage tables)."""
    data = await _football_get(f"/competitions/{WC}/standings")
    if "error" in data:
        return data
    out = []
    for grp in data.get("standings", []):
        rows = [{
            "position": t.get("position"),
            "team": t.get("team", {}).get("name"),
            "played": t.get("playedGames"),
            "points": t.get("points"),
            "goal_difference": t.get("goalDifference"),
        } for t in grp.get("table", [])]
        out.append({"group": grp.get("group") or grp.get("stage"), "table": rows})
    return {"standings": out}


@mcp.tool()
async def worldcup_teams() -> dict:
    """List the national teams in the FIFA World Cup with their ids."""
    data = await _football_get(f"/competitions/{WC}/teams")
    if "error" in data:
        return data
    teams = [{"id": t.get("id"), "name": t.get("name"), "code": t.get("tla")}
             for t in data.get("teams", [])]
    return {"count": len(teams), "teams": teams}


@mcp.tool()
async def worldcup_team_form(team_name: str, limit: int = 5) -> dict:
    """Get a national team's recent finished World Cup matches (their form), useful for predictions."""
    teams = await _football_get(f"/competitions/{WC}/teams")
    if "error" in teams:
        return teams
    match = next((t for t in teams.get("teams", [])
                  if t.get("name", "").lower() == team_name.lower()), None)
    if not match:
        return {"error": f"Team '{team_name}' not found in the World Cup."}
    data = await _football_get(f"/teams/{match['id']}/matches",
                              {"status": "FINISHED", "competitions": WC})
    if "error" in data:
        return data
    matches = [_fmt_match(m) for m in data.get("matches", [])][-limit:]
    return {"team": match["name"], "recent": matches}


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
