from typing import List, Dict, AsyncGenerator, Optional, Callable
import aiohttp
import json
import re
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(service="ollama")


class OllamaService:
    def __init__(self):
        logger.info("Initializing Ollama Service")
        self.base_url = settings.OLLAMA_BASE_URL
        self.chat_model = settings.OLLAMA_CHAT_MODEL
        self.reason_model = settings.OLLAMA_REASON_MODEL

    async def generate_stream(
            self,
            messages: List[Dict],
            user_id: Optional[int] = None,
            conversation_id: Optional[int] = None,
            on_complete: Optional[Callable] = None
    ) -> AsyncGenerator[str, None]:
        """流式生成回复"""
        try:
            model = self.reason_model
            logger.info(f"Using model: {model}")

            header = "### 思考过程\n\n🤔 正在深度思考…\n\n"
            safe_header = json.dumps(header, ensure_ascii=False)[1:-1]
            yield f"data: {safe_header}\n\n"

            full_response = [header]
            has_transitioned = False

            # ==========================================
            # 1. 初始化缓冲区，用于解决字符被切断的问题
            # ==========================================
            text_buffer = ""

            async with aiohttp.ClientSession() as session:
                async with session.post(
                        f"{self.base_url}/api/chat",
                        json={
                            "model": model,
                            "messages": messages,
                            "stream": True,
                            "keep_alive": -1,
                            "options": {"temperature": 0.3}
                        }
                ) as response:
                    async for line in response.content:
                        if line:
                            try:
                                line_text = line.decode('utf-8').strip()
                                if not line_text: continue
                                chunk = json.loads(line_text)
                                message = chunk.get("message", {})

                                thinking = message.get("thinking", "")
                                content = message.get("content", "")

                                # 提取当前需要处理的文本片段
                                current_text = ""
                                is_thinking = False

                                if thinking:
                                    current_text = thinking
                                    is_thinking = True
                                elif content:
                                    current_text = content
                                    is_thinking = False
                                else:
                                    continue

                                # ==========================================
                                # 2. 缓冲区拼接逻辑 (核心修复)
                                # ==========================================
                                # 将上一轮剩下的尾巴拼接到当前开头
                                if text_buffer:
                                    current_text = text_buffer + current_text
                                    text_buffer = ""  # 清空缓冲区

                                # 检查当前片段是否以 "危险字符" 结尾
                                # 如果以 \ 结尾，说明可能是 \[ 或 \( 或 \begin 被切断了
                                # 如果以 [ 结尾，说明可能是 [\begin 被切断了
                                if current_text.endswith("\\") or current_text.endswith("["):
                                    # 将最后一个字符扣留到下一轮
                                    text_buffer = current_text[-1]
                                    current_text = current_text[:-1]

                                    # 如果切掉后为空，这轮直接跳过，等待下一轮拼接
                                    if not current_text:
                                        continue

                                # ==========================================
                                # 3. LaTeX 处理逻辑
                                # ==========================================
                                def process_latex(text):
                                    text = text.replace("\\[", "\n$$\n")
                                    text = text.replace("\\]", "\n$$\n")
                                    text = text.replace("\\(", "$")
                                    text = text.replace("\\)", "$")
                                    text = re.sub(r'\[\s*\\begin', '\n$$\n\\begin', text)
                                    text = re.sub(r'(\\end\{.*?\})\s*\]', r'\1\n$$\n', text)
                                    return text

                                # 处理逻辑
                                if is_thinking:
                                    proc_text = process_latex(current_text)
                                    full_response.append(proc_text)
                                    safe_text = json.dumps(proc_text, ensure_ascii=False)[1:-1]
                                    yield f"data: {safe_text}\n\n"
                                else:
                                    # 思考结束的转换逻辑
                                    if not has_transitioned:
                                        has_transitioned = True
                                        finish_msg = "\n\n✅ 思考完成\n\n---\n\n"
                                        full_response.append(finish_msg)
                                        safe_finish = json.dumps(finish_msg, ensure_ascii=False)[1:-1]
                                        yield f"data: {safe_finish}\n\n"

                                    proc_text = process_latex(current_text)
                                    full_response.append(proc_text)
                                    safe_text = json.dumps(proc_text, ensure_ascii=False)[1:-1]
                                    yield f"data: {safe_text}\n\n"

                            except Exception as e:
                                logger.warning(f"Error parsing chunk: {e}")
                                continue

            # 循环结束后，如果缓冲区里还有剩下的字符（极其罕见，比如刚好以 \ 结尾结束对话），依然要发出去
            if text_buffer:
                safe_buffer = json.dumps(text_buffer, ensure_ascii=False)[1:-1]
                yield f"data: {safe_buffer}\n\n"
                full_response.append(text_buffer)

            if on_complete:
                await on_complete(user_id, conversation_id, messages, "".join(full_response))

        except Exception as e:
            logger.error(f"Stream generation error: {str(e)}", exc_info=True)
            err_msg = f"\n\n生成出错: {str(e)}"
            safe_err = json.dumps(err_msg, ensure_ascii=False)[1:-1]
            yield f"data: {safe_err}\n\n"
            raise