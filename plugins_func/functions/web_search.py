import requests
import re
from config.logger import setup_logging
from plugins_func.register import register_function, ToolType, ActionResponse, Action
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.connection import ConnectionHandler

TAG = __name__
logger = setup_logging()

WEB_SEARCH_FUNCTION_DESC = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "搜索互联网获取实时信息。当用户询问你不知道的事实、最新事件、"
            "实时数据或任何需要联网查询的问题时调用。"
            "例如：'XXX是谁'、'最近有什么大事'、'某某事件怎么回事'"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词",
                },
            },
            "required": ["query"],
        },
    },
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def _search_bocha(query, api_key):
    try:
        r = requests.post(
            "https://api.bochaai.com/v1/web-search",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"query": query, "count": 5, "summary": True},
            timeout=10,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        results = []
        for item in data.get("webPages", {}).get("value", [])[:5]:
            title = item.get("name", "")
            snippet = item.get("summary") or item.get("snippet", "")
            if title:
                results.append(f"{title}: {snippet}")
        return results if results else None
    except Exception as e:
        logger.bind(tag=TAG).debug(f"Bocha search failed: {e}")
        return None


def _search_sogou(query):
    try:
        r = requests.get(
            "https://www.sogou.com/web",
            params={"query": query},
            headers=HEADERS,
            timeout=10,
        )
        if r.status_code != 200:
            return None
        pattern = (
            r'<h3[^>]*>(.*?)</h3>.*?'
            r'(?:<p[^>]*class="[^"]*str[^"]*"[^>]*>|<div[^>]*class="[^"]*space-txt[^"]*"[^>]*>)'
            r'(.*?)</(?:p|div)>'
        )
        items = re.findall(pattern, r.text, re.DOTALL)
        results = []
        for title_html, snippet_html in items[:5]:
            title = re.sub(r'<[^>]+>', '', title_html).strip()
            snippet = re.sub(r'<[^>]+>', '', snippet_html).strip()
            if title and len(title) > 2:
                results.append(f"{title}: {snippet}")
        return results if results else None
    except Exception as e:
        logger.bind(tag=TAG).debug(f"Sogou search failed: {e}")
        return None


@register_function("web_search", WEB_SEARCH_FUNCTION_DESC, ToolType.SYSTEM_CTL)
def web_search(conn: "ConnectionHandler", query: str = ""):
    if not query:
        return ActionResponse(Action.REQLLM, "请告诉我要搜索什么", None)

    search_config = conn.config.get("plugins", {}).get("web_search", {})
    bocha_key = search_config.get("bocha_api_key", "")

    results = None
    source = ""

    if bocha_key:
        results = _search_bocha(query, bocha_key)
        source = "博查"

    if not results:
        results = _search_sogou(query)
        source = "搜狗"

    if not results:
        return ActionResponse(Action.REQLLM, f"搜索'{query}'未找到相关结果", None)

    report = f"搜索'{query}'的结果（来源：{source}）：\n"
    for i, item in enumerate(results, 1):
        report += f"{i}. {item}\n"
    report += "\n请根据以上搜索结果，用自然口语化的方式回答用户的问题。"

    logger.bind(tag=TAG).info(f"Web search: query='{query}', source={source}, results={len(results)}")
    return ActionResponse(Action.REQLLM, report, None)
