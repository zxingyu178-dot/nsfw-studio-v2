# anime_generate / v14

v13 同底模 + Hires 1.5x 二次采样。

- ImageScaleBy(lanczos) → VAEEncode → 二采 12 步 denoise 0.4（dpmpp_2m/karras/cfg5）；
- 输出 1248×1824，单张约 65s（模型常驻）；
- 当前推荐使用 v15（多模型/采样参数）。
