# img2img / v3

W4.0 默认图生图 binding，基于冻结的 v2。

- 模型：Qwen-Image 2.1 UC Q4 GGUF + qwen3vl_8b_w4a8 + texture-fix VAE
- 默认：25 步 / cfg 1.0 / euler simple / denoise 0.8（输入尺寸决定输出尺寸）
- 与 v2 的差异仅为 VAE 换成 texture-fix 解码器
- v1 / v2 全部冻结，历史 Job 不受影响
