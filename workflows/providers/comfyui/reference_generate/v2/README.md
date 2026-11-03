# reference_generate / v2

W4.0 默认参考图生成 binding，基于冻结的 v1。

- 模型：Qwen-Image 2.1 UC Q4 GGUF + qwen3vl_8b_w4a8 + texture-fix VAE
- 默认：25 步 / cfg 1.0 / euler simple / denoise 1.0
- 参考图输入结构与数量上限（1..16）不变
- 与 v1 的差异仅为 VAE 换成 texture-fix 解码器
