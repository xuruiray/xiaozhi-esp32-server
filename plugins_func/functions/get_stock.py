import requests
from config.logger import setup_logging
from plugins_func.register import register_function, ToolType, ActionResponse, Action
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.connection import ConnectionHandler

TAG = __name__
logger = setup_logging()

POPULAR_SYMBOLS = {
    "苹果": "AAPL", "谷歌": "GOOGL", "微软": "MSFT", "亚马逊": "AMZN",
    "特斯拉": "TSLA", "英伟达": "NVDA", "Meta": "META", "奈飞": "NFLX",
    "台积电": "TSM", "阿里巴巴": "BABA", "拼多多": "PDD", "京东": "JD",
    "百度": "BIDU", "网易": "NTES", "腾讯": "TCEHY", "比亚迪": "BYDDY",
    "蔚来": "NIO", "小鹏": "XPEV", "理想": "LI",
}

GET_STOCK_FUNCTION_DESC = {
    "type": "function",
    "function": {
        "name": "get_stock",
        "description": (
            "查询美股实时行情或获取市场新闻。"
            "用户说股票名或代码时查行情，如'苹果股价'、'TSLA多少钱'。"
            "用户说'市场新闻'、'财经新闻'时获取新闻。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "股票代码或中文名，如AAPL、苹果、特斯拉。查新闻时留空",
                },
                "action": {
                    "type": "string",
                    "description": "操作类型：quote（查行情）或 news（查新闻），默认quote",
                },
            },
            "required": [],
        },
    },
}


def _finnhub_get(path, params, api_key):
    params["token"] = api_key
    try:
        r = requests.get(f"https://finnhub.io/api/v1{path}", params=params, timeout=10)
        if r.status_code != 200:
            logger.bind(tag=TAG).error(f"Finnhub API {r.status_code}: {r.text[:100]}")
            return None
        return r.json()
    except Exception as e:
        logger.bind(tag=TAG).error(f"Finnhub request failed: {e}")
        return None


def _resolve_symbol(symbol):
    if not symbol:
        return None
    symbol = symbol.strip()
    if symbol.upper() in [v for v in POPULAR_SYMBOLS.values()]:
        return symbol.upper()
    if symbol in POPULAR_SYMBOLS:
        return POPULAR_SYMBOLS[symbol]
    return symbol.upper()


@register_function("get_stock", GET_STOCK_FUNCTION_DESC, ToolType.SYSTEM_CTL)
def get_stock(conn: "ConnectionHandler", symbol: str = None, action: str = "quote"):
    api_key = conn.config.get("plugins", {}).get("get_stock", {}).get(
        "api_key", ""
    )

    if action == "news" or (not symbol and action != "quote"):
        data = _finnhub_get("/news", {"category": "general"}, api_key)
        if not data or len(data) == 0:
            return ActionResponse(Action.REQLLM, "暂时无法获取市场新闻", None)

        import random
        items = random.sample(data, min(3, len(data)))
        report = "最新市场新闻：\n"
        for item in items:
            report += f"- {item.get('headline', '')}\n"
        return ActionResponse(Action.REQLLM, report, None)

    resolved = _resolve_symbol(symbol)
    if not resolved:
        return ActionResponse(Action.REQLLM, "请告诉我要查询的股票名称或代码", None)

    quote = _finnhub_get("/quote", {"symbol": resolved}, api_key)
    if not quote or quote.get("c", 0) == 0:
        return ActionResponse(Action.REQLLM, f"未找到 {symbol} 的行情数据，请确认股票代码", None)

    profile = _finnhub_get("/stock/profile2", {"symbol": resolved}, api_key)
    name = profile.get("name", resolved) if profile else resolved

    price = quote["c"]
    change = quote["d"]
    change_pct = quote["dp"]
    high = quote["h"]
    low = quote["l"]
    prev_close = quote["pc"]
    direction = "涨" if change >= 0 else "跌"

    report = (
        f"{name}（{resolved}）当前价格{price:.2f}美元，"
        f"今日{direction}{abs(change):.2f}美元，幅度{abs(change_pct):.2f}%，"
        f"最高{high:.2f}，最低{low:.2f}，昨收{prev_close:.2f}。"
        f"请用口语化的方式播报，不要使用任何符号标记。"
    )
    return ActionResponse(Action.REQLLM, report, None)
