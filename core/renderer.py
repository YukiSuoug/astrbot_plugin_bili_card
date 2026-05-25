"""卡片渲染器模块 - PIL实现"""
import io
import os
import asyncio
from typing import Optional

import aiohttp
from PIL import Image, ImageDraw, ImageFont

from .api import VideoInfo, Comment
from .utils import format_number, format_duration, truncate_text

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESOURCE_DIR = os.path.join(PLUGIN_DIR, "resources")
FONT_DIR = os.path.join(RESOURCE_DIR, "fonts")

# 字体下载地址（Noto Sans SC - Google开源字体）
FONT_URL = "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/SimplifiedChinese/NotoSansSC-Regular.otl"
FONT_BOLD_URL = "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/SimplifiedChinese/NotoSansSC-Bold.otl"

# 颜色定义
COLORS = {
    "bg_primary": "#FFFFFF",
    "bg_secondary": "#F5F5F5",
    "text_primary": "#212121",
    "text_secondary": "#757575",
    "text_link": "#00A1D6",
    "bili_pink": "#FB7299",
    "bili_blue": "#00A1D6",
    "border": "#E0E0E0",
    "stat_like": "#FF6699",
    "stat_coin": "#FEB147",
    "stat_fav": "#97CAFC",
    "stat_share": "#77DD77",
    "cover_bg": "#E8E8E8",
}


def hex_to_rgb(hex_color: str) -> tuple:
    """将十六进制颜色转换为RGB元组"""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


class PILRenderer:
    """PIL卡片渲染器"""

    def __init__(self):
        self._font_cache = {}
        self._font_ready = False
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _ensure_fonts(self):
        """确保字体文件存在"""
        if self._font_ready:
            return

        os.makedirs(FONT_DIR, exist_ok=True)

        font_path = os.path.join(FONT_DIR, "NotoSansSC-Regular.otl")
        font_bold_path = os.path.join(FONT_DIR, "NotoSansSC-Bold.otl")

        if not os.path.exists(font_path):
            await self._download_font(FONT_URL, font_path)
        if not os.path.exists(font_bold_path):
            await self._download_font(FONT_BOLD_URL, font_bold_path)

        self._font_ready = True

    async def _download_font(self, url: str, save_path: str):
        """下载字体文件"""
        try:
            session = await self._get_session()
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                if resp.status == 200:
                    with open(save_path, 'wb') as f:
                        f.write(await resp.read())
                    print(f"[BiliCard] 字体下载成功: {save_path}")
                else:
                    print(f"[BiliCard] 字体下载失败: HTTP {resp.status}")
        except Exception as e:
            print(f"[BiliCard] 字体下载异常: {e}")

    def _get_font(self, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        """获取字体（带缓存）"""
        key = (size, bold)
        if key not in self._font_cache:
            font = None

            # 优先使用下载的字体
            if bold:
                font_path = os.path.join(FONT_DIR, "NotoSansSC-Bold.otl")
            else:
                font_path = os.path.join(FONT_DIR, "NotoSansSC-Regular.otl")

            if os.path.exists(font_path):
                try:
                    font = ImageFont.truetype(font_path, size)
                except Exception:
                    pass

            # 备选：系统字体
            if font is None:
                system_fonts = [
                    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                    "C:/Windows/Fonts/msyh.ttc",
                    "C:/Windows/Fonts/simhei.ttf",
                ]
                for fp in system_fonts:
                    if os.path.exists(fp):
                        try:
                            font = ImageFont.truetype(fp, size)
                            break
                        except Exception:
                            continue

            # 最后使用默认字体
            if font is None:
                font = ImageFont.load_default()

            self._font_cache[key] = font

        return self._font_cache[key]

    async def _download_image(self, url: str) -> Optional[bytes]:
        """下载图片"""
        try:
            session = await self._get_session()
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://www.bilibili.com",
            }
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    return await resp.read()
        except Exception:
            pass
        return None

    def _fit_image(self, img: Image.Image, target_width: int, target_height: int) -> Image.Image:
        """将图片裁剪/缩放以适应目标尺寸（居中裁剪）"""
        img_ratio = img.width / img.height
        target_ratio = target_width / target_height

        if img_ratio > target_ratio:
            # 图片更宽，按高度缩放后裁剪宽度
            new_height = target_height
            new_width = int(new_height * img_ratio)
        else:
            # 图片更高，按宽度缩放后裁剪高度
            new_width = target_width
            new_height = int(new_width / img_ratio)

        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # 居中裁剪
        left = (new_width - target_width) // 2
        top = (new_height - target_height) // 2
        return img.crop((left, top, left + target_width, top + target_height))

    async def render_card(
        self,
        video_info: VideoInfo,
        show_stats: bool = True,
        show_comments: bool = True,
        max_comments: int = 3,
    ) -> bytes:
        """渲染视频卡片，返回PNG图片字节"""
        # 确保字体就绪
        await self._ensure_fonts()

        # 卡片尺寸
        card_width = 800
        padding = 20
        cover_height = 340

        # 计算内容高度
        title_height = 50
        info_height = 35
        stats_height = 50 if show_stats else 0
        comments_height = 0
        if show_comments and video_info.comments:
            comments_height = min(len(video_info.comments), max_comments) * 65 + 45

        total_height = (
            padding * 2
            + cover_height
            + 15
            + title_height
            + info_height
            + stats_height
            + comments_height
            + 10
        )

        # 创建图片
        img = Image.new("RGB", (card_width, total_height), hex_to_rgb(COLORS["bg_primary"]))
        draw = ImageDraw.Draw(img)

        y_offset = padding

        # 下载并绘制封面
        cover_drawn = False
        if video_info.cover_url:
            cover_bytes = await self._download_image(video_info.cover_url)
            if cover_bytes:
                try:
                    cover_img = Image.open(io.BytesIO(cover_bytes))
                    cover_img = self._fit_image(cover_img, card_width - padding * 2, cover_height)
                    img.paste(cover_img, (padding, y_offset))
                    cover_drawn = True
                except Exception:
                    pass

        if not cover_drawn:
            # 绘制占位符
            cover_rect = [padding, y_offset, card_width - padding, y_offset + cover_height]
            draw.rounded_rectangle(cover_rect, radius=12, fill=hex_to_rgb(COLORS["cover_bg"]))
            self._draw_cover_placeholder(draw, cover_rect)

        y_offset += cover_height + 15

        # 绘制标题
        title_font = self._get_font(22, bold=True)
        title = truncate_text(video_info.title, 30)
        draw.text((padding, y_offset), title, fill=hex_to_rgb(COLORS["text_primary"]), font=title_font)
        y_offset += title_height

        # 绘制UP主信息
        info_font = self._get_font(14)
        up_text = f"UP: {video_info.up_name}"
        draw.text((padding, y_offset), up_text, fill=hex_to_rgb(COLORS["bili_blue"]), font=info_font)

        # 时长和分区
        duration_text = format_duration(video_info.duration)
        tname_text = video_info.tname if video_info.tname else ""
        right_text = f"{tname_text} | {duration_text}"
        right_bbox = draw.textbbox((0, 0), right_text, font=info_font)
        right_width = right_bbox[2] - right_bbox[0]
        draw.text(
            (card_width - padding - right_width, y_offset),
            right_text,
            fill=hex_to_rgb(COLORS["text_secondary"]),
            font=info_font,
        )
        y_offset += info_height

        # 绘制统计数据
        if show_stats:
            y_offset = self._draw_stats(draw, video_info, padding, y_offset, card_width)

        # 绘制评论
        if show_comments and video_info.comments:
            y_offset = self._draw_comments(
                draw, video_info.comments[:max_comments], padding, y_offset, card_width
            )

        # 关闭session
        if self._session and not self._session.closed:
            await self._session.close()

        # 转换为字节
        buffer = io.BytesIO()
        img.save(buffer, format="PNG", quality=95)
        return buffer.getvalue()

    def _draw_cover_placeholder(self, draw: ImageDraw.Draw, rect: list):
        """绘制封面占位符"""
        cx = (rect[0] + rect[2]) // 2
        cy = (rect[1] + rect[3]) // 2
        # 绘制圆形背景
        circle_r = 30
        draw.ellipse(
            [cx - circle_r, cy - circle_r, cx + circle_r, cy + circle_r],
            fill=hex_to_rgb("#00000040")
        )
        # 绘制三角形播放按钮
        triangle_size = 20
        triangle = [
            (cx - triangle_size // 3, cy - triangle_size // 2),
            (cx - triangle_size // 3, cy + triangle_size // 2),
            (cx + triangle_size // 2, cy),
        ]
        draw.polygon(triangle, fill=hex_to_rgb("#FFFFFF"))

    def _draw_stats(
        self,
        draw: ImageDraw.Draw,
        video_info: VideoInfo,
        padding: int,
        y_offset: int,
        card_width: int,
    ) -> int:
        """绘制统计数据"""
        stat_font = self._get_font(13)
        stat_bold_font = self._get_font(13, bold=True)

        stats = [
            (format_number(video_info.view_count), "播放", COLORS["text_secondary"]),
            (format_number(video_info.like_count), "点赞", COLORS["stat_like"]),
            (format_number(video_info.coin_count), "投币", COLORS["stat_coin"]),
            (format_number(video_info.favorite_count), "收藏", COLORS["stat_fav"]),
            (format_number(video_info.share_count), "分享", COLORS["stat_share"]),
        ]

        # 计算总宽度
        total_width = 0
        for num, label, _ in stats:
            num_bbox = draw.textbbox((0, 0), num, font=stat_bold_font)
            label_bbox = draw.textbbox((0, 0), label, font=stat_font)
            total_width += (num_bbox[2] - num_bbox[0]) + (label_bbox[2] - label_bbox[0]) + 35

        # 居中绘制
        start_x = (card_width - total_width) // 2
        x = start_x

        for num, label, color in stats:
            # 数字
            draw.text((x, y_offset + 8), num, fill=hex_to_rgb(color), font=stat_bold_font)
            num_bbox = draw.textbbox((0, 0), num, font=stat_bold_font)
            x += num_bbox[2] - num_bbox[0] + 4

            # 标签
            draw.text((x, y_offset + 10), label, fill=hex_to_rgb(COLORS["text_secondary"]), font=stat_font)
            label_bbox = draw.textbbox((0, 0), label, font=stat_font)
            x += label_bbox[2] - label_bbox[0] + 25

        return y_offset + 50

    def _draw_comments(
        self,
        draw: ImageDraw.Draw,
        comments: list[Comment],
        padding: int,
        y_offset: int,
        card_width: int,
    ) -> int:
        """绘制热门评论"""
        # 评论标题
        comment_title_font = self._get_font(15, bold=True)
        draw.text(
            (padding, y_offset),
            "热门评论",
            fill=hex_to_rgb(COLORS["text_primary"]),
            font=comment_title_font,
        )
        y_offset += 30

        # 分割线
        draw.line(
            [(padding, y_offset), (card_width - padding, y_offset)],
            fill=hex_to_rgb(COLORS["border"]),
            width=1,
        )
        y_offset += 12

        comment_font = self._get_font(13)
        comment_user_font = self._get_font(12, bold=True)

        for comment in comments:
            # 用户名
            draw.text(
                (padding + 5, y_offset),
                comment.user_name,
                fill=hex_to_rgb(COLORS["bili_blue"]),
                font=comment_user_font,
            )

            # 点赞数（右侧）
            like_text = f"{format_number(comment.like_count)} 赞"
            like_bbox = draw.textbbox((0, 0), like_text, font=comment_font)
            like_width = like_bbox[2] - like_bbox[0]
            draw.text(
                (card_width - padding - like_width - 5, y_offset),
                like_text,
                fill=hex_to_rgb(COLORS["text_secondary"]),
                font=comment_font,
            )
            y_offset += 20

            # 评论内容（截断）
            content = truncate_text(comment.content, 45)
            draw.text(
                (padding + 10, y_offset),
                content,
                fill=hex_to_rgb(COLORS["text_primary"]),
                font=comment_font,
            )
            y_offset += 35

        return y_offset


class PlaywrightRenderer:
    """Playwright卡片渲染器（高质量，内存占用较高）"""

    def __init__(self):
        self._browser = None
        self._playwright = None

    async def _ensure_browser(self):
        """确保浏览器已启动"""
        if self._browser is None:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                    '--disable-gpu',
                    '--js-flags="--max-old-space-size=128"',
                ]
            )

    async def render_card(
        self,
        video_info: VideoInfo,
        show_stats: bool = True,
        show_comments: bool = True,
        max_comments: int = 3,
    ) -> bytes:
        """渲染高质量卡片"""
        await self._ensure_browser()

        html = self._generate_html(video_info, show_stats, show_comments, max_comments)

        page = await self._browser.new_page()
        try:
            await page.set_content(html, wait_until="networkidle")
            element = await page.query_selector("#card")
            if element:
                return await element.screenshot(type="png")
            return await page.screenshot(type="png")
        finally:
            await page.close()

    def _generate_html(
        self,
        video_info: VideoInfo,
        show_stats: bool,
        show_comments: bool,
        max_comments: int,
    ) -> str:
        """生成HTML"""
        from .utils import format_number, format_duration

        cover_html = ""
        if video_info.cover_url:
            cover_html = f'<img class="cover-img" src="{video_info.cover_url}" alt="cover">'
        else:
            cover_html = '<div class="cover-placeholder">▶</div>'

        stats_html = ""
        if show_stats:
            stats_html = f"""
            <div class="stats">
                <div class="stat-item"><span class="stat-num">{format_number(video_info.view_count)}</span><span class="stat-label">播放</span></div>
                <div class="stat-item"><span class="stat-num like">{format_number(video_info.like_count)}</span><span class="stat-label">点赞</span></div>
                <div class="stat-item"><span class="stat-num coin">{format_number(video_info.coin_count)}</span><span class="stat-label">投币</span></div>
                <div class="stat-item"><span class="stat-num fav">{format_number(video_info.favorite_count)}</span><span class="stat-label">收藏</span></div>
                <div class="stat-item"><span class="stat-num share">{format_number(video_info.share_count)}</span><span class="stat-label">分享</span></div>
            </div>
            """

        comments_html = ""
        if show_comments and video_info.comments:
            comments_items = ""
            for comment in video_info.comments[:max_comments]:
                comments_items += f"""
                <div class="comment">
                    <div class="comment-header">
                        <span class="comment-user">{comment.user_name}</span>
                        <span class="comment-like">{format_number(comment.like_count)} 赞</span>
                    </div>
                    <p class="comment-content">{truncate_text(comment.content, 45)}</p>
                </div>
                """
            comments_html = f"""
            <div class="comments-section">
                <h3>热门评论</h3>
                <hr>
                {comments_items}
            </div>
            """

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                body {{
                    padding: 20px;
                    background: #FFFFFF;
                    font-family: "PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif;
                }}
                #card {{
                    width: 800px;
                    background: #FFFFFF;
                    border-radius: 12px;
                    overflow: hidden;
                }}
                .cover {{
                    width: 100%;
                    height: 340px;
                    overflow: hidden;
                    border-radius: 12px;
                    position: relative;
                }}
                .cover-img {{
                    width: 100%;
                    height: 100%;
                    object-fit: cover;
                }}
                .cover-placeholder {{
                    width: 100%;
                    height: 100%;
                    background: #E8E8E8;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-size: 48px;
                    color: rgba(255,255,255,0.8);
                }}
                .title {{
                    font-size: 22px;
                    font-weight: bold;
                    color: #212121;
                    margin: 15px 0 10px;
                    line-height: 1.4;
                }}
                .info {{
                    display: flex;
                    justify-content: space-between;
                    color: #757575;
                    font-size: 14px;
                    margin-bottom: 15px;
                }}
                .up-name {{
                    color: #00A1D6;
                    font-weight: 500;
                }}
                .stats {{
                    display: flex;
                    justify-content: center;
                    gap: 30px;
                    margin: 15px 0;
                    padding: 12px 0;
                    background: #F8F8F8;
                    border-radius: 8px;
                }}
                .stat-item {{
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    gap: 4px;
                }}
                .stat-num {{
                    font-size: 16px;
                    font-weight: bold;
                    color: #212121;
                }}
                .stat-num.like {{ color: #FF6699; }}
                .stat-num.coin {{ color: #FEB147; }}
                .stat-num.fav {{ color: #97CAFC; }}
                .stat-num.share {{ color: #77DD77; }}
                .stat-label {{
                    font-size: 12px;
                    color: #999;
                }}
                .comments-section {{
                    margin-top: 20px;
                    padding-top: 15px;
                    border-top: 1px solid #E8E8E8;
                }}
                .comments-section h3 {{
                    color: #212121;
                    font-size: 15px;
                    margin: 0 0 12px 0;
                }}
                .comment {{
                    margin: 12px 0;
                    padding: 10px 12px;
                    background: #F8F8F8;
                    border-radius: 8px;
                }}
                .comment-header {{
                    display: flex;
                    justify-content: space-between;
                    margin-bottom: 6px;
                }}
                .comment-user {{
                    color: #00A1D6;
                    font-weight: 500;
                    font-size: 13px;
                }}
                .comment-like {{
                    color: #999;
                    font-size: 12px;
                }}
                .comment-content {{
                    color: #333;
                    font-size: 14px;
                    line-height: 1.5;
                }}
            </style>
        </head>
        <body>
            <div id="card">
                <div class="cover">
                    {cover_html}
                </div>
                <div class="title">{truncate_text(video_info.title, 30)}</div>
                <div class="info">
                    <span class="up-name">UP: {video_info.up_name}</span>
                    <span>{video_info.tname} | {format_duration(video_info.duration)}</span>
                </div>
                {stats_html}
                {comments_html}
            </div>
        </body>
        </html>
        """

    async def close(self):
        """关闭浏览器"""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None


def get_renderer(engine: str = "pil"):
    """获取渲染器实例"""
    if engine == "playwright":
        return PlaywrightRenderer()
    return PILRenderer()
