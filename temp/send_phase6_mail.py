"""Phase 6 交付邮件：Source/Handoff ZIP + 验收证据摘要，发送并 IMAP 复核（SHA-256 比对）。

- 凭据只在运行时从 hermes secrets.env 读取，禁止输出原文；
- 附件用 MIMEApplication + Content-Disposition: attachment（hermes send_mail.py 的 MIMEImage
  对 zip 会静默丢附件——禁止复用）；
- 发送后用 IMAP 重新下载附件并比对 SHA-256，确证投递。

用法：
    .venv/Scripts/python temp/send_phase6_mail.py --dry-run
    .venv/Scripts/python temp/send_phase6_mail.py
"""
from __future__ import annotations

import argparse
import email
import hashlib
import imaplib
import os
import smtplib
import time
from email.header import Header, decode_header
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SECRETS = Path(r"D:\AIHome_2.0_L1_L2\projects\hermes\config\secrets.env")


def load_secrets() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in SECRETS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip().strip("'\"")
    return values


def decode_mime(value: str) -> str:
    parts = decode_header(value or "")
    return "".join(
        part.decode(enc or "utf-8", errors="replace") if isinstance(part, bytes) else part
        for part, enc in parts
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    secrets = load_secrets()
    sender = secrets["QQ_SENDER"]
    auth_code = secrets["QQ_AUTH_CODE"]
    receiver = os.environ.get("QQ_RECEIVER") or secrets.get("QQ_RECEIVER") or sender
    smtp_server = secrets.get("QQ_SMTP_SERVER", "smtp.qq.com")
    smtp_port = int(secrets.get("QQ_SMTP_PORT", "465"))

    attachments = [
        PROJECT_ROOT / "handoff" / "NSFW_Studio_Phase6_Source.zip",
        PROJECT_ROOT / "handoff" / "NSFW_Studio_Phase6_Handoff.zip",
    ]
    for path in attachments:
        if not path.is_file():
            print(f"[FAIL] 附件不存在: {path}")
            return 2

    subject = "【NSFW Studio V2】Phase 6 交付：Pipeline 可靠性收口（v0.8.0）"
    body = (
        "Phase 6 完成（不扩模型，收口「能生成之后如何可靠继续编辑/复现/扩模块」）：\n\n"
        "A. Task1-9 全部落地（含 4 个真实缺陷修复）\n"
        "   - Image→Workbench 取「最近的生成上下文」（import→img2img→upscale 恢复 Img2Img；Seed 用该图真实 Seed）\n"
        "   - 前端工作流身份完整保留（不重建裸 upscale；双 hash + config 不丢）\n"
        "   - Recipe 固定 Seed 归一化（「使用此图 Seed」可保存配方）\n"
        "   - 移除执行重排 + PIPELINE_DUPLICATE_MODULE + 未注册 module_version 创建期拒绝\n"
        "   - availability 版本域修正；Img2Img execute Prompt 契约；generation_mode 显式化\n"
        "   - /modules 参数 Schema（ParameterSpec）+ size_mode；前端按 schema 渲染控件\n\n"
        "B. Task10 真实照片验收（4 次运行 11/11 通过）→ 默认 denoise 0.55 → 0.8\n"
        "   - 0.55 即使换场景 Prompt 也「几乎没变化」（精修档）；0.7 轻度；0.8 人物保留良好且场景级 Prompt 生效\n"
        "   - 证据 docs/evidence/phase6-img2img/（report_*.json + outputs/ + screenshots/）\n\n"
        "C. Task11 浏览器全链路（Playwright + 系统 Edge）\n"
        "   文生图 → 图库导入 → 图片生成（从图库选择）→ Img2Img+高清 → Gallery → History →\n"
        "   从 processed/upscaled 恢复工作台 → Recipe 保存/重开 → 切回文生图（截图见 Source ZIP docs/evidence/）\n\n"
        "测试：快速套件 227 passed（208 基线 + 19 新增）；前端 store 断言 11（CI test:store）；\n"
        "npm run build 通过；版本 0.8.0；tag v0.8.0。\n"
        "报告：docs/PHASE6_REPORT.md、TEST_REPORT.md、CHANGELOG/DEV_LOG/TASKS。\n"
    )

    message = MIMEMultipart()
    message["From"] = sender
    message["To"] = receiver
    message["Subject"] = Header(subject, "utf-8")
    message.attach(MIMEText(body, "plain", "utf-8"))
    for path in attachments:
        part = MIMEApplication(path.read_bytes(), _subtype="zip")
        part.add_header("Content-Disposition", "attachment", filename=path.name)
        message.attach(part)

    print(f"[..] 附件: {[p.name for p in attachments]}")
    for path in attachments:
        print(f"     {path.name}: {path.stat().st_size} bytes, sha256={sha256_file(path)[:16]}…")
    if args.dry_run:
        print("[dry-run] 不发送")
        return 0

    with smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=120) as smtp:
        smtp.login(sender, auth_code)
        smtp.sendmail(sender, [receiver], message.as_string())
    print("[OK] SMTP 发送成功，开始 IMAP 复核…")

    expected = {p.name: sha256_file(p) for p in attachments}
    deadline = time.monotonic() + 180
    verified: dict[str, str] = {}
    while time.monotonic() < deadline:
        with imaplib.IMAP4_SSL("imap.qq.com", 993) as imap:
            imap.login(sender, auth_code)
            imap.select("INBOX")
            status, data = imap.search(None, "ALL")
            if status == "OK" and data and data[0]:
                ids = data[0].split()[-10:]
                for msg_id in reversed(ids):
                    status, fetched = imap.fetch(msg_id, "(RFC822)")
                    if status != "OK" or not fetched or not fetched[0]:
                        continue
                    msg = email.message_from_bytes(fetched[0][1])
                    subject_text = decode_mime(str(msg.get("Subject", "")))
                    if "Phase 6" not in subject_text:
                        continue
                    for part in msg.walk():
                        filename = part.get_filename()
                        if not filename:
                            continue
                        payload = part.get_payload(decode=True) or b""
                        verified[filename] = hashlib.sha256(payload).hexdigest()
        if all(name in verified and verified[name] == digest for name, digest in expected.items()):
            break
        time.sleep(10)

    ok = all(name in verified and verified[name] == digest for name, digest in expected.items())
    for name, digest in expected.items():
        got = verified.get(name)
        print(f"[{'OK' if got == digest else 'MISS/DIFF'}] {name}: 收到={bool(got)} sha256_match={got == digest}")
    print("[OK] 邮件投递复核通过" if ok else "[FAIL] 附件未在收件箱全部确认")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())