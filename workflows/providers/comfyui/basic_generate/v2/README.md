# basic_generate / v2

W4.0 默认文生图 binding。

- 模型：Qwen-Image 2.1 UC Q4 GGUF + qwen3vl_8b_w4a8（CPU）+ texture-fix VAE + turbo8 LoRA + f23gg LoRA
- 默认：832×1216 / 12 步 / cfg 1.0 / euler simple
- 与 v1 的差异：VAE 换成 texture-fix 解码器；默认步数 8 → 12
- v1 已冻结，历史 Job 只按自身 hash 续跑
