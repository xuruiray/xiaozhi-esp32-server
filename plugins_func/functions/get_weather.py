import requests
from config.logger import setup_logging
from plugins_func.register import register_function, ToolType, ActionResponse, Action
from core.utils.util import get_ip_info
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.connection import ConnectionHandler

TAG = __name__
logger = setup_logging()

GET_WEATHER_FUNCTION_DESC = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": (
            "获取某个地点的天气，用户应提供一个位置，比如用户说杭州天气，参数为：杭州。"
            "如果用户说的是省份，默认用省会城市。如果用户说的不是省份或城市而是一个地名，默认用该地所在省份的省会城市。"
            "如果用户没有指明地点，说'天气怎么样'、'今天天气如何'，location参数为空"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "地点名，例如杭州。可选参数，如果不提供则不传",
                },
                "lang": {
                    "type": "string",
                    "description": "返回用户使用的语言code，例如zh/en/ja等，默认zh",
                },
            },
            "required": ["lang"],
        },
    },
}


def _api_get(api_host, path, api_key, params):
    params["key"] = api_key
    url = f"https://{api_host}{path}"
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        if data.get("code") != "200":
            err = data.get("error", {}).get("detail") or data.get("code")
            logger.bind(tag=TAG).error(f"QWeather API error: {path} -> {err}")
            return None
        return data
    except Exception as e:
        logger.bind(tag=TAG).error(f"QWeather request failed: {path} -> {e}")
        return None


def _resolve_location_id(location, api_key, api_host, lang):
    data = _api_get(api_host, "/geo/v2/city/lookup", api_key, {"location": location, "lang": lang})
    if not data:
        return None, None
    locs = data.get("location", [])
    if not locs:
        return None, None
    return locs[0].get("id"), locs[0].get("name")


@register_function("get_weather", GET_WEATHER_FUNCTION_DESC, ToolType.SYSTEM_CTL)
def get_weather(conn: "ConnectionHandler", location: str = None, lang: str = "zh"):
    from core.utils.cache.manager import cache_manager, CacheType

    weather_config = conn.config.get("plugins", {}).get("get_weather", {})
    api_host = weather_config.get("api_host", "")
    api_key = weather_config.get("api_key", "")
    default_location = weather_config.get("default_location", "广州")
    client_ip = conn.client_ip

    if not location:
        if client_ip:
            cached_ip_info = cache_manager.get(CacheType.IP_INFO, client_ip)
            if cached_ip_info:
                location = cached_ip_info.get("city")
            else:
                ip_info = get_ip_info(client_ip, logger)
                if ip_info:
                    cache_manager.set(CacheType.IP_INFO, client_ip, ip_info)
                    location = ip_info.get("city")
            if not location:
                location = default_location
        else:
            location = default_location

    weather_cache_key = f"full_weather_{location}_{lang}"
    cached = cache_manager.get(CacheType.WEATHER, weather_cache_key)
    if cached:
        return ActionResponse(Action.REQLLM, cached, None)

    loc_id, city_name = _resolve_location_id(location, api_key, api_host, lang)
    if not loc_id:
        return ActionResponse(Action.REQLLM, f"未找到城市: {location}，请确认地点是否正确", None)

    now_data = _api_get(api_host, "/v7/weather/now", api_key, {"location": loc_id, "lang": lang})
    forecast_data = _api_get(api_host, "/v7/weather/3d", api_key, {"location": loc_id, "lang": lang})

    if not now_data:
        return ActionResponse(Action.REQLLM, "获取实时天气失败", None)

    now = now_data.get("now", {})
    report = f"{city_name}当前天气: {now.get('text')}，{now.get('temp')}°C（体感{now.get('feelsLike')}°C）\n"
    report += f"湿度{now.get('humidity')}%，{now.get('windDir')}{now.get('windScale')}级\n"

    if forecast_data:
        report += "\n未来3天预报：\n"
        for d in forecast_data.get("daily", []):
            report += f"{d['fxDate']}: {d['textDay']}，{d['tempMin']}~{d['tempMax']}°C\n"

    cache_manager.set(CacheType.WEATHER, weather_cache_key, report)
    return ActionResponse(Action.REQLLM, report, None)
