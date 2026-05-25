"""消息解析与路由模块"""
import json
import re
from dataclasses import dataclass
from typing import Optional

from .api import BiliAPI, BiliParser, VideoInfo


@dataclass
class ParseResult:
    """解析结果"""
    success: bool = False
    video_info: Optional[VideoInfo] = None
    source_type: str = ""  # bv, av, url, short_url, miniapp, card
    raw_text: str = ""
    error: str = ""


class MessageParser:
    """消息解析器"""

    # BV号正则
    BV_PATTERN = re.compile(r'(BV[a-zA-Z0-9]{10})')
    # AV号正则
    AV_PATTERN = re.compile(r'(?:av|AV)(\d+)')
    # B站链接正则
    BILI_URL_PATTERN = re.compile(
        r'https?://(?:www\.)?bilibili\.com/video/(?:BV[a-zA-Z0-9]{10}|av\d+)[^\s]*'
    )
    # 短链接正则
    SHORT_URL_PATTERN = re.compile(r'https?://b23\.tv/[a-zA-Z0-9]+')
    # QQ小程序中的B站链接
    MINIAPP_QQDOCURL = re.compile(r'"qqdocurl"\s*:\s*"(https?://[^"]+)"')
    MINIAPP_JUMPURL = re.compile(r'"jumpUrl"\s*:\s*"(https?://[^"]+)"')

    def __init__(self, api: BiliAPI):
        self.api = api
        self.bili_parser = BiliParser(api)

    async def parse_message(self, message: str) -> ParseResult:
        """解析消息，提取B站视频信息"""
        result = ParseResult(raw_text=message)

        # 1. 尝试解析JSON（QQ卡片消息）
        if message.strip().startswith('{'):
            video_info = await self._try_parse_json(message)
            if video_info:
                result.success = True
                result.video_info = video_info
                result.source_type = "card"
                return result

        # 2. 尝试提取BV号
        bv_match = self.BV_PATTERN.search(message)
        if bv_match:
            try:
                video_info = await self.api.get_video_info_by_bvid(bv_match.group(1))
                result.success = True
                result.video_info = video_info
                result.source_type = "bv"
                return result
            except Exception as e:
                result.error = str(e)

        # 3. 尝试提取AV号
        av_match = self.AV_PATTERN.search(message)
        if av_match:
            try:
                video_info = await self.api.get_video_info_by_aid(int(av_match.group(1)))
                result.success = True
                result.video_info = video_info
                result.source_type = "av"
                return result
            except Exception as e:
                result.error = str(e)

        # 4. 尝试提取短链接
        short_match = self.SHORT_URL_PATTERN.search(message)
        if short_match:
            try:
                full_url = await self.api.resolve_short_url(short_match.group(0))
                video_info = await self._parse_url(full_url)
                if video_info:
                    result.success = True
                    result.video_info = video_info
                    result.source_type = "short_url"
                    return result
            except Exception as e:
                result.error = str(e)

        # 5. 尝试提取普通链接
        url_match = self.BILI_URL_PATTERN.search(message)
        if url_match:
            try:
                video_info = await self._parse_url(url_match.group(0))
                if video_info:
                    result.success = True
                    result.video_info = video_info
                    result.source_type = "url"
                    return result
            except Exception as e:
                result.error = str(e)

        return result

    async def _try_parse_json(self, text: str) -> Optional[VideoInfo]:
        """尝试从JSON中解析"""
        try:
            data = json.loads(text)

            # QQ小程序格式
            if "meta" in data:
                detail = data.get("meta", {}).get("detail_1", {})
                url = detail.get("qqdocurl", "")
                if not url:
                    url = detail.get("jumpUrl", "")
                if url and ("bilibili.com" in url or "b23.tv" in url):
                    return await self._resolve_and_parse(url)

            # 其他JSON格式
            if "detail" in data:
                url = data["detail"].get("qqdocurl", "")
                if url and ("bilibili.com" in url or "b23.tv" in url):
                    return await self._resolve_and_parse(url)

        except (json.JSONDecodeError, KeyError, TypeError):
            pass

        return None

    async def _resolve_and_parse(self, url: str) -> Optional[VideoInfo]:
        """解析短链接并获取视频信息"""
        if "b23.tv" in url:
            url = await self.api.resolve_short_url(url)
        return await self._parse_url(url)

    async def _parse_url(self, url: str) -> Optional[VideoInfo]:
        """从URL中解析视频信息"""
        bv_match = self.BV_PATTERN.search(url)
        if bv_match:
            return await self.api.get_video_info_by_bvid(bv_match.group(1))

        av_match = self.AV_PATTERN.search(url)
        if av_match:
            return await self.api.get_video_info_by_aid(int(av_match.group(1)))

        return None

    def is_bilibili_message(self, message: str) -> bool:
        """快速判断消息是否包含B站内容（不发送请求）"""
        if self.BV_PATTERN.search(message):
            return True
        if self.AV_PATTERN.search(message):
            return True
        if self.SHORT_URL_PATTERN.search(message):
            return True
        if self.BILI_URL_PATTERN.search(message):
            return True
        if '"qqdocurl"' in message and ('bilibili.com' in message or 'b23.tv' in message):
            return True
        return False
