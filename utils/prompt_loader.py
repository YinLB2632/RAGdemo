from utils.config_handler import prompts_conf
from utils.logger_handler import logger
from utils.path_tool import get_abs_path


def _load_prompt(config_key: str) -> str:
    try:
        prompt_path = get_abs_path(prompts_conf[config_key])
    except KeyError as exc:
        logger.error(f"提示词配置中缺少 {config_key}")
        raise

    try:
        with open(prompt_path, "r", encoding="utf-8") as file:
            return file.read()
    except OSError as exc:
        logger.error(f"读取提示词失败：{exc}")
        raise


def load_system_prompts() -> str:
    return _load_prompt("main_prompt_path")


def load_rag_prompts() -> str:
    return _load_prompt("rag_summarize_prompt_path")
