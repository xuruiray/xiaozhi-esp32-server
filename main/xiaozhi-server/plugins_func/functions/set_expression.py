import json
import asyncio
from config.logger import setup_logging
from plugins_func.register import register_function, ToolType, ActionResponse, Action
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.connection import ConnectionHandler

TAG = __name__
logger = setup_logging()

EXPRESSION_MAP = {
    "happy": "🙂",
    "laughing": "😆",
    "funny": "😂",
    "sad": "😔",
    "crying": "😭",
    "angry": "😠",
    "surprised": "😲",
    "shocked": "😱",
    "thinking": "🤔",
    "loving": "😍",
    "embarrassed": "😳",
    "cool": "😎",
    "winking": "😉",
    "sleepy": "😴",
    "neutral": "😶",
    "silly": "😜",
    "confused": "🙄",
    "relaxed": "😌",
    "confident": "😏",
    "kissy": "😘",
}

SET_EXPRESSION_FUNCTION_DESC = {
    "type": "function",
    "function": {
        "name": "set_expression",
        "description": (
            "控制设备屏幕显示的动画表情。当用户要求你做表情、换个表情、"
            "或者对话场景适合展示特定情绪时调用。"
            "可用的表情: happy, laughing, funny, sad, crying, angry, "
            "surprised, shocked, thinking, loving, embarrassed, cool, "
            "winking, sleepy, neutral, silly, confused, relaxed, confident, kissy"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "emotion": {
                    "type": "string",
                    "description": "表情名称，如 happy, sad, thinking, loving 等",
                }
            },
            "required": ["emotion"],
        },
    },
}


@register_function("set_expression", SET_EXPRESSION_FUNCTION_DESC, ToolType.SYSTEM_CTL)
def set_expression(conn: "ConnectionHandler", emotion: str = "happy"):
    emotion = emotion.lower().strip()
    if emotion not in EXPRESSION_MAP:
        emotion = "happy"

    emoji = EXPRESSION_MAP[emotion]

    try:
        asyncio.run_coroutine_threadsafe(
            conn.websocket.send(
                json.dumps(
                    {
                        "type": "llm",
                        "text": emoji,
                        "emotion": emotion,
                        "session_id": conn.session_id,
                    }
                )
            ),
            conn.loop,
        ).result(timeout=5)
        logger.bind(tag=TAG).info(f"Set expression: {emotion} {emoji}")
        return ActionResponse(
            action=Action.RESPONSE,
            result=f"已切换表情为{emotion}",
            response=f"好的，已经换成{emotion}表情啦",
        )
    except Exception as e:
        logger.bind(tag=TAG).error(f"Set expression failed: {e}")
        return ActionResponse(
            action=Action.RESPONSE,
            result="表情切换失败",
            response="哎呀，表情切换失败了",
        )
