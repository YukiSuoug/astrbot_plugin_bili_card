"""工具函数模块"""
import re
from datetime import datetime
from typing import Optional


def format_number(num: int) -> str:
    """格式化数字显示（如 12345 -> 1.2万）"""
    if num >= 100000000:
        return f"{num / 100000000:.1f}亿"
    elif num >= 10000:
        return f"{num / 10000:.1f}万"
    else:
        return str(num)


def format_duration(seconds: int) -> str:
    """格式化视频时长（秒 -> HH:MM:SS 或 MM:SS）"""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_time(timestamp: int) -> str:
    """格式化时间戳"""
    dt = datetime.fromtimestamp(timestamp)
    return dt.strftime("%Y-%m-%d %H:%M")


def truncate_text(text: str, max_length: int = 100) -> str:
    """截断文本"""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


def extract_bv_id(text: str) -> Optional[str]:
    """从文本中提取BV号"""
    pattern = r'(BV[a-zA-Z0-9]{10})'
    match = re.search(pattern, text)
    return match.group(1) if match else None


def extract_av_id(text: str) -> Optional[int]:
    """从文本中提取AV号"""
    pattern = r'(?:av|AV)(\d+)'
    match = re.search(pattern, text)
    return int(match.group(1)) if match else None


def clean_html_tags(text: str) -> str:
    """清理HTML标签"""
    clean = re.compile('<.*?>')
    return re.sub(clean, '', text)


def get_emoji_tag(emoji_name: str) -> str:
    """获取表情标签（用于QQ消息）"""
    emoji_map = {
        "点赞": "[CQ:face,id=66]",
        "投币": "[CQ:face,id=181]",
        "收藏": "[CQ:face,id=319]",
        "分享": "[CQ:face,id=182]",
    }
    return emoji_map.get(emoji_name, "")
