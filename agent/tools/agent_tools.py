from datetime import datetime

import requests
from langchain_core.tools import tool

from rag.rag_service import RagSummarizeService

rag = RagSummarizeService()

WEATHER_CODE_TEXT = {
    0: "晴",
    1: "大部晴朗",
    2: "多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "毛毛雨",
    53: "毛毛雨",
    55: "毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    80: "阵雨",
    81: "阵雨",
    82: "强阵雨",
    95: "雷暴",
    96: "冰雹雷暴",
    99: "强冰雹雷暴",
}


def _fetch_json(url: str, **params) -> dict:
    """请求公共接口并将网络或协议问题转换为工具可读错误。"""
    try:
        response = requests.get(url, params=params or None, timeout=10)
        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code}")
        return response.json()
    except (requests.RequestException, ValueError, RuntimeError) as exc:
        raise RuntimeError(f"外部服务请求失败: {exc}") from exc


@tool(description="从向量存储中检索参考资料")
def rag_summarize(query: str) -> str:
    return rag.rag_summarize(query)


@tool(description="获取指定城市的实时天气，并以消息字符串形式返回")
def get_weather(city: str) -> str:
    geocoding = _fetch_json(
        "https://geocoding-api.open-meteo.com/v1/search",
        name=city,
        count=1,
        language="zh",
        format="json",
    )
    results = geocoding.get("results")
    if not results:
        raise RuntimeError(f"无法找到城市: {city}")

    place = results[0]
    try:
        latitude = place["latitude"]
        longitude = place["longitude"]
        place_name = place["name"]
    except KeyError as exc:
        raise RuntimeError(f"城市地理编码缺少字段: {exc.args[0]}") from exc

    forecast = _fetch_json(
        "https://api.open-meteo.com/v1/forecast",
        latitude=latitude,
        longitude=longitude,
        current="temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation,weather_code",
    )
    current = forecast.get("current")
    required_fields = (
        "temperature_2m",
        "relative_humidity_2m",
        "wind_speed_10m",
        "precipitation",
        "weather_code",
    )
    if not isinstance(current, dict) or any(field not in current for field in required_fields):
        raise RuntimeError("天气服务返回的数据不完整")

    weather = WEATHER_CODE_TEXT.get(current["weather_code"], "未知天气")
    return (
        f"城市{place_name}当前天气{weather}，温度{current['temperature_2m']}℃，"
        f"空气湿度{current['relative_humidity_2m']}%，风速{current['wind_speed_10m']}km/h，"
        f"降水量{current['precipitation']}mm"
    )


@tool(description="获取用户所在城市的名称，以纯字符串形式返回")
def get_user_location() -> str:
    data = _fetch_json("https://ipwho.is/")
    if not data.get("success") or not data.get("city"):
        detail = data.get("message", "接口未返回城市")
        raise RuntimeError(f"获取用户位置失败: {detail}")
    return data["city"]





@tool(description="获取当前月份，以 YYYY-MM 形式返回")
def get_current_month() -> str:
    return datetime.now().strftime("%Y-%m")
