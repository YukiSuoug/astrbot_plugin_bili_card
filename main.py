"""B站链接解析与卡片渲染插件 - 主入口"""
import asyncio
from typing import Optional

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api import logger

from .core.api import BiliAPI, VideoInfo
from .core.parser import MessageParser
from .core.renderer import get_renderer


class BilibiliCardPlugin(Star):
    """B站卡片解析插件"""

    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.api: Optional[BiliAPI] = None
        self.parser: Optional[MessageParser] = None
        self.renderer = None
        self._init_lock = asyncio.Lock()

    async def _ensure_initialized(self):
        """延迟初始化（避免启动时占用资源）"""
        if self.api is not None:
            return

        async with self._init_lock:
            if self.api is not None:
                return

            cookie = self.config.get("bili_cookie", "")
            self.api = BiliAPI(cookie=cookie)
            self.parser = MessageParser(self.api)

            engine = self.config.get("render_engine", "pil")
            self.renderer = get_renderer(engine)

            logger.info(f"[BiliCard] 插件初始化完成，渲染引擎: {engine}")

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """监听所有消息"""
        await self._ensure_initialized()

        message = event.message_str
        if not message:
            return

        # 快速检查是否包含B站内容
        if not self.parser.is_bilibili_message(message):
            return

        logger.debug(f"[BiliCard] 检测到B站内容: {message[:100]}")

        try:
            # 解析消息
            result = await self.parser.parse_message(message)

            if not result.success or not result.video_info:
                if result.error:
                    logger.warning(f"[BiliCard] 解析失败: {result.error}")
                return

            video_info = result.video_info
            logger.info(f"[BiliCard] 解析成功: {video_info.title}")

            # 获取评论（如果需要）
            if self.config.get("show_comments", True):
                max_comments = self.config.get("max_comments", 3)
                if max_comments > 0:
                    video_info.comments = await self.api.get_comments(
                        video_info.aid, page_size=max_comments
                    )

            # 生成卡片图片
            if self.config.get("enable_image_render", True):
                try:
                    image_bytes = await self.renderer.render_card(
                        video_info,
                        show_stats=self.config.get("show_stats", True),
                        show_comments=self.config.get("show_comments", True),
                        max_comments=self.config.get("max_comments", 3),
                    )
                    yield event.image_result(image_bytes)
                except Exception as e:
                    logger.error(f"[BiliCard] 渲染卡片失败: {e}", exc_info=True)
                    # 降级为文本发送
                    text = self._format_text_summary(video_info)
                    yield event.plain_result(text)

            # 发送视频直链
            if self.config.get("enable_video_send", False):
                url = f"https://www.bilibili.com/video/{video_info.bvid}"
                yield event.plain_result(f"🔗 {url}")

        except Exception as e:
            logger.error(f"[BiliCard] 处理异常: {e}", exc_info=True)

    def _format_text_summary(self, video_info: VideoInfo) -> str:
        """格式化文本摘要（降级方案）"""
        from .core.utils import format_number, format_duration

        lines = [
            f"📺 {video_info.title}",
            f"👤 UP主: {video_info.up_name}",
            f"⏱ 时长: {format_duration(video_info.duration)}",
        ]

        if self.config.get("show_stats", True):
            lines.append(
                f"❤ {format_number(video_info.like_count)}  "
                f"🪙 {format_number(video_info.coin_count)}  "
                f"⭐ {format_number(video_info.favorite_count)}"
            )

        if video_info.comments and self.config.get("show_comments", True):
            lines.append("")
            lines.append("💬 热门评论:")
            for comment in video_info.comments[:3]:
                lines.append(f"  {comment.user_name}: {comment.content[:50]}")

        return "\n".join(lines)

    async def terminate(self):
        """插件卸载/停用时调用"""
        if self.api:
            await self.api.close()
        if self.renderer and hasattr(self.renderer, 'close'):
            await self.renderer.close()
        logger.info("[BiliCard] 插件已停止")
