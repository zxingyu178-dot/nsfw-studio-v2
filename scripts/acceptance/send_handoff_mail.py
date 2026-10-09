"""阶段交付邮件：Source/Handoff ZIP 附件发送 + IMAP SHA-256 复核（长期工具，Phase 7 Task1 迁移）。

- 凭据只在运行时从 hermes secrets.env 读取，禁止输出原文；
- 附件用 MIMEApplication + Content-Disposition: attachment（hermes send_mail.py 的 MIMEImage
  对 zip 会静默丢附件——禁止复用）；
- 发送后用 IMAP 重新下载附件并比对 SHA-256，确证投递。

用法（项目根目录）：
    .venv/Scripts/python scripts/acceptance/send_handoff_mail.py \
        --phase Phase7 \
        --source handoff/NSFW_Studio_Phase7_Source.zip \
        --handoff handoff/NSFW_Studio_Phase7_Handoff.zip \
        --subject-file temp/phase7_mail_subject.txt \
        --body-file temp/phase7_mail_body.txt [--dry-run]
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

PROJECT_ROOT = Path(__file__).resolve().parents[2]
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


def read_text_argument(*, inline: str | None, file_path: str | None, label: str) -> str:
    if inline:
        return inline
    if file_path:
        path = Path(file_path)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path.read_text(encoding="utf-8")
    raise SystemExit(f"[FAIL] 必须提供 --{label} 或 --{label}-file")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", required=True, help="阶段标识（同时用于 IMAP 复核过滤，如 Phase7）")
    parser.add_argument("--source", required=True, help="Source ZIP 路径（相对项目根目录或绝对路径）")
    parser.add_argument("--handoff", required=True, help="Handoff ZIP 路径（相对项目根目录或绝对路径）")
    parser.add_argument("--subject", default=None, help="邮件主题（与 --subject-file 二选一）")
    parser.add_argument("--subject-file", default=None, help="邮件主题文件（UTF-8）")
    parser.add_argument("--body-file", default=None, help="邮件正文文件（UTF-8）")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    def resolve(path_text: str) -> Path:
        path = Path(path_text)
        return path if path.is_absolute() else PROJECT_ROOT / path

    attachments = [resolve(args.source), resolve(args.handoff)]
    for path in attachments:
        if not path.is_file():
            print(f"[FAIL] 附件不存在: {path}")
            return 2

    secrets = load_secrets()
    sender = secrets["QQ_SENDER"]
    auth_code = secrets["QQ_AUTH_CODE"]
    receiver = os.environ.get("QQ_RECEIVER") or secrets.get("QQ_RECEIVER") or sender
    smtp_server = secrets.get("QQ_SMTP_SERVER", "smtp.qq.com")
    smtp_port = int(secrets.get("QQ_SMTP_PORT", "465"))

    subject = read_text_argument(
        inline=args.subject, file_path=args.subject_file, label="subject"
    ).strip()
    body = read_text_argument(inline=None, file_path=args.body_file, label="body")

    message = MIMEMultipart()
    message["From"] = sender
    message["To"] = receiver
    message["Subject"] = Header(subject, "utf-8")
    message.attach(MIMEText(body, "plain", "utf-8"))
    for path in attachments:
        part = MIMEApplication(path.read_bytes(), _subtype="zip")
        part.add_header("Content-Disposition", "attachment", filename=path.name)
        message.attach(part)

    print(f"[..] 阶段: {args.phase}  主题: {subject}")
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
                    if args.phase not in subject_text:
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