"""B站API封装模块"""
import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Optional

import aiohttp

from .utils import clean_html_tags


@dataclass
class VideoInfo:
    """视频信息数据类"""
    bvid: str = ""
    aid: int = 0
    title: str = ""
    desc: str = ""
    cover_url: str = ""
    duration: int = 0
    view_count: int = 0
    danmaku_count: int = 0
    like_count: int = 0
    coin_count: int = 0
    favorite_count: int = 0
    share_count: int = 0
    reply_count: int = 0
    pub_date: int = 0
    up_name: str = ""
    up_avatar: str = ""
    up_mid: int = 0
    tname: str = ""
    tags: list = field(default_factory=list)
    comments: list = field(default_factory=list)


@dataclass
class Comment:
    """评论数据类"""
    user_name: str = ""
    user_avatar: str = ""
    content: str = ""
    like_count: int = 0
    reply_count: int = 0


class BiliAPI:
    """B站API封装"""

    BASE_URL = "https://api.bilibili.com"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.bilibili.com",
    }

    def __init__(self, cookie: str = ""):
        self.cookie = cookie
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers = {**self.HEADERS}
            if self.cookie:
                headers["Cookie"] = self.cookie
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _request(self, url: str, params: dict = None) -> dict:
        """发送请求"""
        session = await self._get_session()
        try:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("code") == 0:
                        return data.get("data", {})
                    else:
                        raise Exception(f"API错误: {data.get('message', '未知错误')}")
                else:
                    raise Exception(f"HTTP错误: {resp.status}")
        except asyncio.TimeoutError:
            raise Exception("请求超时")

    async def resolve_short_url(self, short_url: str) -> str:
        """解析短链接，返回完整URL"""
        session = await self._get_session()
        try:
            async with session.get(
                short_url,
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status in (301, 302):
                    return resp.headers.get("Location", short_url)
                return short_url
        except Exception:
            return short_url

    async def get_video_info_by_bvid(self, bvid: str) -> VideoInfo:
        """通过BV号获取视频信息"""
        url = f"{self.BASE_URL}/x/web-interface/view"
        data = await self._request(url, {"bvid": bvid})
        return self._parse_video_info(data)

    async def get_video_info_by_aid(self, aid: int) -> VideoInfo:
        """通过AV号获取视频信息"""
        url = f"{self.BASE_URL}/x/web-interface/view"
        data = await self._request(url, {"aid": aid})
        return self._parse_video_info(data)

    def _parse_video_info(self, data: dict) -> VideoInfo:
        """解析视频信息"""
        stat = data.get("stat", {})
        owner = data.get("owner", {})
        return VideoInfo(
            bvid=data.get("bvid", ""),
            aid=data.get("aid", 0),
            title=data.get("title", ""),
            desc=data.get("desc", ""),
            cover_url=data.get("pic", ""),
            duration=data.get("duration", 0),
            view_count=stat.get("view", 0),
            danmaku_count=stat.get("danmaku", 0),
            like_count=stat.get("like", 0),
            coin_count=stat.get("coin", 0),
            favorite_count=stat.get("favorite", 0),
            share_count=stat.get("share", 0),
            reply_count=stat.get("reply", 0),
            pub_date=data.get("pubdate", 0),
            up_name=owner.get("name", ""),
            up_avatar=owner.get("face", ""),
            up_mid=owner.get("mid", 0),
            tname=data.get("tname", ""),
        )

    async def get_video_stat(self, aid: int) -> dict:
        """获取视频统计数据"""
        url = f"{self.BASE_URL}/x/web-interface/archive/stat"
        return await self._request(url, {"aid": aid})

    async def get_comments(self, oid: int, sort: int = 1, page_size: int = 3) -> list[Comment]:
        """获取评论列表
        sort: 0=按时间, 1=按点赞数, 2=按回复数
        """
        url = f"{self.BASE_URL}/x/v2/reply"
        params = {
            "oid": oid,
            "type": 1,  # 视频类型
            "sort": sort,
            "pn": 1,
            "ps": page_size,
        }
        try:
            data = await self._request(url, params)
            replies = data.get("replies", []) or []
            comments = []
            for reply in replies[:page_size]:
                member = reply.get("member", {})
                content_data = reply.get("content", {})
                comments.append(Comment(
                    user_name=member.get("uname", ""),
                    user_avatar=member.get("avatar", ""),
                    content=clean_html_tags(content_data.get("message", "")),
                    like_count=reply.get("like", 0),
                    reply_count=reply.get("rcount", 0),
                ))
            return comments
        except Exception:
            return []

    async def get_user_info(self, mid: int) -> dict:
        """获取用户信息"""
        url = f"{self.BASE_URL}/x/space/acc/info"
        return await self._request(url, {"mid": mid})

    async def get_video_tags(self, aid: int) -> list[str]:
        """获取视频标签"""
        url = f"{self.BASE_URL}/x/tag/archive/tags"
        try:
            data = await self._request(url, {"aid": aid})
            return [tag.get("tag_name", "") for tag in data[:5]]
        except Exception:
            return []


class BiliParser:
    """B站链接解析器"""

    # BV号正则
    BV_PATTERN = re.compile(r'(BV[a-zA-Z0-9]{10})')
    # AV号正则
    AV_PATTERN = re.compile(r'(?:av|AV)(\d+)')
    # B站链接正则
    BILI_URL_PATTERN = re.compile(
        r'https?://(?:www\.)?bilibili\.com/video/(?:BV[a-zA-Z0-9]{10}|av\d+)'
    )
    # 短链接正则
    SHORT_URL_PATTERN = re.compile(r'https?://b23\.tv/[a-zA-Z0-9]+')
    # QQ小程序中的B站链接
    MINIAPP_PATTERN = re.compile(r'"qqdocurl"\s*:\s*"(https?://[^"]+)"')

    def __init__(self, api: BiliAPI):
        self.api = api

    async def parse_from_text(self, text: str) -> Optional[VideoInfo]:
        """从文本中解析B站视频信息"""
        # 1. 尝试提取BV号
        bv_match = self.BV_PATTERN.search(text)
        if bv_match:
            return await self.api.get_video_info_by_bvid(bv_match.group(1))

        # 2. 尝试提取AV号
        av_match = self.AV_PATTERN.search(text)
        if av_match:
            return await self.api.get_video_info_by_aid(int(av_match.group(1)))

        # 3. 尝试提取短链接
        short_match = self.SHORT_URL_PATTERN.search(text)
        if short_match:
            full_url = await self.api.resolve_short_url(short_match.group(0))
            return await self._parse_url(full_url)

        # 4. 尝试提取普通链接
        url_match = self.BILI_URL_PATTERN.search(text)
        if url_match:
            return await self._parse_url(url_match.group(0))

        # 5. 尝试从QQ小程序中提取
        miniapp_match = self.MINIAPP_PATTERN.search(text)
        if miniapp_match:
            url = miniapp_match.group(1)
            if "bilibili.com" in url or "b23.tv" in url:
                if "b23.tv" in url:
                    url = await self.api.resolve_short_url(url)
                return await self._parse_url(url)

        return None

    async def parse_from_json(self, json_str: str) -> Optional[VideoInfo]:
        """从JSON消息中解析（QQ卡片消息）"""
        try:
            data = json.loads(json_str)
            # 尝试从不同字段提取URL
            url = None
            if "meta" in data:
                detail = data["meta"].get("detail_1", {})
                url = detail.get("qqdocurl", "")
            elif "detail" in data:
                url = data["detail"].get("qqdocurl", "")

            if url and ("bilibili.com" in url or "b23.tv" in url):
                if "b23.tv" in url:
                    url = await self.api.resolve_short_url(url)
                return await self._parse_url(url)
        except (json.JSONDecodeError, KeyError):
            pass
        return None

    async def _parse_url(self, url: str) -> Optional[VideoInfo]:
        """从URL中解析视频信息"""
        bv_match = self.BV_PATTERN.search(url)
        if bv_match:
            return await self.api.get_video_info_by_bvid(bv_match.group(1))

        av_match = self.AV_PATTERN.search(url)
        if av_match:
            return await self.api.get_video_info_by_aid(int(av_match.group(1)))

        return None
