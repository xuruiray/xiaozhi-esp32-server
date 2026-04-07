import os
import yaml
import asyncio
import aiohttp
import json
from urllib.parse import urlparse, parse_qs
from config.logger import setup_logging
from config.config_loader import get_project_dir
from plugins_func.register import register_function, ToolType, ActionResponse, Action
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.connection import ConnectionHandler

TAG = __name__
logger = setup_logging()

REGISTER_VOICEPRINT_DESC = {
    "type": "function",
    "function": {
        "name": "register_voiceprint",
        "description": (
            "注册当前说话人的声纹。当用户要求注册声纹、记住声音、"
            "或说'我叫XXX，帮我注册声纹'、'记住我的声音'时调用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "说话人的名字",
                },
                "description": {
                    "type": "string",
                    "description": "对说话人的简短描述，如果用户没说可以留空",
                },
            },
            "required": ["name"],
        },
    },
}


def update_config_speakers(speaker_id: str, name: str, description: str):
    config_path = get_project_dir() + "data/.config.yaml"
    entry = f"{speaker_id},{name},{description}"
    if not os.path.exists(config_path):
        return
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    vp = data.setdefault("voiceprint", {})
    speakers = vp.setdefault("speakers", [])
    speakers = [s for s in speakers if not s.startswith(f"{speaker_id},")]
    speakers.append(entry)
    vp["speakers"] = speakers
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
    logger.bind(tag=TAG).info(f"Config updated: added speaker {entry}")


async def do_voiceprint_register(conn: "ConnectionHandler", wav_data: bytes, reg_info: dict):
    name = reg_info.get("name", "")
    description = reg_info.get("description", "")
    speaker_id = name

    vp_config = conn.config.get("voiceprint", {})
    vp_url = vp_config.get("url", "")
    if not vp_url:
        logger.bind(tag=TAG).error("voiceprint url not configured")
        return False, "声纹服务未配置"

    parsed = urlparse(vp_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    api_key = parse_qs(parsed.query).get("key", [""])[0]

    try:
        form = aiohttp.FormData()
        form.add_field("speaker_id", speaker_id)
        form.add_field("file", wav_data, filename="audio.wav", content_type="audio/wav")
        headers = {"Authorization": f"Bearer {api_key}"}
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(f"{base_url}/voiceprint/register", headers=headers, data=form) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.bind(tag=TAG).error(f"Voiceprint register API error {resp.status}: {body}")
                    return False, f"注册失败: {body}"
    except Exception as e:
        logger.bind(tag=TAG).error(f"Voiceprint register request failed: {e}")
        return False, f"注册请求失败: {e}"

    try:
        update_config_speakers(speaker_id, name, description or "")
    except Exception as e:
        logger.bind(tag=TAG).error(f"Config update failed: {e}")

    logger.bind(tag=TAG).info(f"Voiceprint registered: {name} ({speaker_id})")
    return True, f"{name}的声纹注册成功啦"


@register_function("register_voiceprint", REGISTER_VOICEPRINT_DESC, ToolType.SYSTEM_CTL)
def register_voiceprint(conn: "ConnectionHandler", name: str = "", description: str = ""):
    if not name:
        return ActionResponse(
            action=Action.RESPONSE,
            result="缺少名字",
            response="你叫什么名字呀？告诉我名字我才能注册声纹哦",
        )

    conn.voiceprint_register_pending = {
        "name": name,
        "description": description or "",
    }
    logger.bind(tag=TAG).info(f"Voiceprint registration pending for: {name}")

    return ActionResponse(
        action=Action.RESPONSE,
        result=f"等待{name}录入声纹",
        response=f"好的{name}，请你现在说一段话，大概五到十秒就行，我来录入你的声纹",
    )
