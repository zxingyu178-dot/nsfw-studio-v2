"""生成实验输入图（Phase 5.1 Task11）——需用 ComfyUI venv（有 PIL）。

结构鲜明的合成图（768x768）：大面积纯色几何结构 + 全局条带，
用于判断 Img2Img 输出是否真的保留输入图结构（而不是退化成文生图）。

用法（ComfyUI venv）：
    D:/AIHome_2.0_L1_L2/projects/comfyui/venv/Scripts/python.exe make_input.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT_DIR = Path(__file__).parent / "inputs"
SIZE = 768


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (SIZE, SIZE), (188, 210, 226))  # 浅灰蓝背景
    draw = ImageDraw.Draw(image)

    # 全局条带（结构锚点 1）：横贯全宽的绿色横带
    draw.rectangle([0, 96, SIZE, 150], fill=(70, 160, 90))
    # 大红色圆（结构锚点 2）：左侧主体
    draw.ellipse([70, 250, 430, 610], fill=(198, 60, 55))
    # 深蓝方块（结构锚点 3）：右下
    draw.rectangle([440, 420, 700, 690], fill=(45, 70, 150))
    # 黄色三角（结构锚点 4）：右上
    draw.polygon([(560, 170), (730, 340), (470, 340)], fill=(230, 190, 60))
    # 白色小圆（结构锚点 5）：左下角
    draw.ellipse([90, 640, 190, 740], fill=(240, 240, 240))

    path = OUT_DIR / "structure_test_768.png"
    image.save(path)
    print(f"[OK] 输入图已生成: {path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()