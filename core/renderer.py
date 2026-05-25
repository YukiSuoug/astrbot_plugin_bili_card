"""卡片渲染器模块 - PIL实现"""
import io
import os
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from .api import VideoInfo, Comment
from .utils import format_number, format_duration, truncate_text

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESOURCE_DIR = os.path.join(PLUGIN_DIR, "resources")

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
}


class PILRenderer:
    """PIL卡片渲染器"""

    def __init__(self):
        self._font_cache = {}

    def _get_font(self, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        """获取字体（带缓存）"""
        key = (size, bold)
        if key not in self._font_cache:
            # 尝试加载系统字体
            font_paths = [
                "C:/Windows/Fonts/msyh.ttc",  # Windows微软雅黑
                "C:/Windows/Fonts/simhei.ttf",  # Windows黑体
                "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",  # Linux文泉驿
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Linux DejaVu
            ]
            font = None
            for font_path in font_paths:
                if os.path.exists(font_path):
                    try:
                        font = ImageFont.truetype(font_path, size)
                        break
                    except Exception:
                        continue
            if font is None:
                font = ImageFont.load_default()
            self._font_cache[key] = font
        return self._font_cache[key]

    async def render_card(
        self,
        video_info: VideoInfo,
        show_stats: bool = True,
        show_comments: bool = True,
        max_comments: int = 3,
    ) -> bytes:
        """渲染视频卡片，返回PNG图片字节"""
        # 卡片尺寸
        card_width = 800
        padding = 20
        cover_height = 300

        # 计算内容高度
        title_height = 60
        info_height = 40
        stats_height = 50 if show_stats else 0
        comments_height = 0
        if show_comments and video_info.comments:
            comments_height = min(len(video_info.comments), max_comments) * 60 + 40

        total_height = (
            padding * 2
            + cover_height
            + 10
            + title_height
            + info_height
            + stats_height
            + comments_height
            + 20
        )

        # 创建图片
        img = Image.new("RGB", (card_width, total_height), COLORS["bg_primary"])
        draw = ImageDraw.Draw(img)

        y_offset = padding

        # 绘制封面（灰色占位）
        cover_rect = [padding, y_offset, card_width - padding, y_offset + cover_height]
        draw.rounded_rectangle(cover_rect, radius=12, fill="#E8E8E8")
        # 这里可以异步下载封面并粘贴，暂时使用占位符
        self._draw_cover_placeholder(draw, cover_rect)
        y_offset += cover_height + 10

        # 绘制标题
        title_font = self._get_font(24, bold=True)
        title = truncate_text(video_info.title, 35)
        draw.text((padding, y_offset), title, fill=COLORS["text_primary"], font=title_font)
        y_offset += title_height

        # 绘制UP主信息
        info_font = self._get_font(16)
        up_text = f"UP主: {video_info.up_name}"
        draw.text((padding, y_offset), up_text, fill=COLORS["text_secondary"], font=info_font)

        # 时长和分区
        duration_text = format_duration(video_info.duration)
        tname_text = video_info.tname if video_info.tname else ""
        right_text = f"{tname_text}  |  {duration_text}"
        right_bbox = draw.textbbox((0, 0), right_text, font=info_font)
        right_width = right_bbox[2] - right_bbox[0]
        draw.text(
            (card_width - padding - right_width, y_offset),
            right_text,
            fill=COLORS["text_secondary"],
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

        # 转换为字节
        buffer = io.BytesIO()
        img.save(buffer, format="PNG", quality=95)
        return buffer.getvalue()

    def _draw_cover_placeholder(self, draw: ImageDraw.Draw, rect: list):
        """绘制封面占位符"""
        # 绘制一个简单的播放按钮图标
        cx = (rect[0] + rect[2]) // 2
        cy = (rect[1] + rect[3]) // 2
        # 绘制三角形播放按钮
        triangle_size = 40
        triangle = [
            (cx - triangle_size // 2, cy - triangle_size // 2),
            (cx - triangle_size // 2, cy + triangle_size // 2),
            (cx + triangle_size // 2, cy),
        ]
        draw.polygon(triangle, fill="#FFFFFF80")

    def _draw_stats(
        self,
        draw: ImageDraw.Draw,
        video_info: VideoInfo,
        padding: int,
        y_offset: int,
        card_width: int,
    ) -> int:
        """绘制统计数据"""
        stat_font = self._get_font(14)

        stats = [
            (f"▶ {format_number(video_info.view_count)}", COLORS["text_secondary"]),
            (f"❤ {format_number(video_info.like_count)}", COLORS["stat_like"]),
            (f"🪙 {format_number(video_info.coin_count)}", COLORS["stat_coin"]),
            (f"⭐ {format_number(video_info.favorite_count)}", COLORS["stat_fav"]),
            (f"↗ {format_number(video_info.share_count)}", COLORS["stat_share"]),
        ]

        # 计算总宽度
        total_width = 0
        for text, _ in stats:
            bbox = draw.textbbox((0, 0), text, font=stat_font)
            total_width += bbox[2] - bbox[0] + 30

        # 居中绘制
        start_x = (card_width - total_width) // 2
        x = start_x
        for text, color in stats:
            draw.text((x, y_offset + 10), text, fill=color, font=stat_font)
            bbox = draw.textbbox((0, 0), text, font=stat_font)
            x += bbox[2] - bbox[0] + 30

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
        comment_title_font = self._get_font(16, bold=True)
        draw.text(
            (padding, y_offset),
            "热门评论",
            fill=COLORS["text_primary"],
            font=comment_title_font,
        )
        y_offset += 30

        # 分割线
        draw.line(
            [(padding, y_offset), (card_width - padding, y_offset)],
            fill=COLORS["border"],
            width=1,
        )
        y_offset += 10

        comment_font = self._get_font(14)
        comment_user_font = self._get_font(13, bold=True)

        for comment in comments:
            # 用户名
            draw.text(
                (padding, y_offset),
                comment.user_name,
                fill=COLORS["bili_blue"],
                font=comment_user_font,
            )
            y_offset += 20

            # 评论内容（截断）
            content = truncate_text(comment.content, 50)
            draw.text(
                (padding + 10, y_offset),
                content,
                fill=COLORS["text_primary"],
                font=comment_font,
            )
            y_offset += 20

            # 点赞数
            like_text = f"👍 {format_number(comment.like_count)}"
            draw.text(
                (padding + 10, y_offset),
                like_text,
                fill=COLORS["text_secondary"],
                font=comment_font,
            )
            y_offset += 30

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

        stats_html = ""
        if show_stats:
            stats_html = f"""
            <div class="stats">
                <span class="stat">▶ {format_number(video_info.view_count)}</span>
                <span class="stat like">❤ {format_number(video_info.like_count)}</span>
                <span class="stat coin">🪙 {format_number(video_info.coin_count)}</span>
                <span class="stat fav">⭐ {format_number(video_info.favorite_count)}</span>
                <span class="stat share">↗ {format_number(video_info.share_count)}</span>
            </div>
            """

        comments_html = ""
        if show_comments and video_info.comments:
            comments_items = ""
            for comment in video_info.comments[:max_comments]:
                comments_items += f"""
                <div class="comment">
                    <span class="comment-user">{comment.user_name}</span>
                    <p class="comment-content">{truncate_text(comment.content, 50)}</p>
                    <span class="comment-like">👍 {format_number(comment.like_count)}</span>
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
                body {{
                    margin: 0;
                    padding: 20px;
                    background: #FFFFFF;
                    font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
                }}
                #card {{
                    width: 800px;
                    background: #FFFFFF;
                    border-radius: 12px;
                    overflow: hidden;
                }}
                .cover {{
                    width: 100%;
                    height: 300px;
                    background: #E8E8E8;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    border-radius: 12px;
                }}
                .cover::after {{
                    content: "▶";
                    font-size: 48px;
                    color: rgba(255,255,255,0.8);
                }}
                .title {{
                    font-size: 24px;
                    font-weight: bold;
                    color: #212121;
                    margin: 15px 0;
                }}
                .info {{
                    display: flex;
                    justify-content: space-between;
                    color: #757575;
                    font-size: 14px;
                    margin-bottom: 15px;
                }}
                .stats {{
                    display: flex;
                    justify-content: center;
                    gap: 25px;
                    margin: 15px 0;
                    font-size: 14px;
                }}
                .stat {{ color: #757575; }}
                .stat.like {{ color: #FF6699; }}
                .stat.coin {{ color: #FEB147; }}
                .stat.fav {{ color: #97CAFC; }}
                .stat.share {{ color: #77DD77; }}
                .comments-section {{
                    margin-top: 20px;
                }}
                .comments-section h3 {{
                    color: #212121;
                    font-size: 16px;
                    margin: 0 0 10px 0;
                }}
                .comments-section hr {{
                    border: none;
                    border-top: 1px solid #E0E0E0;
                    margin: 10px 0;
                }}
                .comment {{
                    margin: 10px 0;
                    padding: 10px;
                }}
                .comment-user {{
                    color: #00A1D6;
                    font-weight: bold;
                    font-size: 13px;
                }}
                .comment-content {{
                    color: #212121;
                    font-size: 14px;
                    margin: 5px 0 5px 10px;
                }}
                .comment-like {{
                    color: #757575;
                    font-size: 12px;
                    margin-left: 10px;
                }}
            </style>
        </head>
        <body>
            <div id="card">
                <div class="cover"></div>
                <div class="title">{truncate_text(video_info.title, 35)}</div>
                <div class="info">
                    <span>UP主: {video_info.up_name}</span>
                    <span>{video_info.tname}  |  {format_duration(video_info.duration)}</span>
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
