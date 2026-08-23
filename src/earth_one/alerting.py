
from __future__ import annotations

"""Earth One v2.1 autonomous alerting.

The monitoring engine produces machine-readable outcomes; this module turns
those outcomes into human alerts. It supports:
- SMTP email
- severity routing
- concise subject/body generation
- attachment support
- no silent success
- dry-run mode

Credentials are read only from environment variables:
EARTH_ONE_SMTP_HOST
EARTH_ONE_SMTP_PORT
EARTH_ONE_SMTP_USERNAME
EARTH_ONE_SMTP_PASSWORD
EARTH_ONE_ALERT_FROM
EARTH_ONE_ALERT_TO
"""

from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Iterable, Any
import json
import mimetypes
import os
import smtplib
import ssl


@dataclass(frozen=True)
class Alert:
    severity: str
    title: str
    summary: str
    details: dict[str, Any]
    attachments: tuple[str, ...] = ()

    def subject(self, system="Earth One") -> str:
        return f"[{system}][{self.severity.upper()}] {self.title}"

    def body(self) -> str:
        lines=[self.summary,"","Details:"]
        for k,v in self.details.items():
            lines.append(f"- {k}: {v}")
        return "\n".join(lines)


class SMTPAlertSender:
    def __init__(self):
        from .runtime_config import load_env_file
        load_env_file()
        self.host=os.getenv("EARTH_ONE_SMTP_HOST")
        self.port=int(os.getenv("EARTH_ONE_SMTP_PORT","465"))
        self.username=os.getenv("EARTH_ONE_SMTP_USERNAME")
        self.password=os.getenv("EARTH_ONE_SMTP_PASSWORD")
        self.sender=os.getenv("EARTH_ONE_ALERT_FROM")
        self.recipient=os.getenv("EARTH_ONE_ALERT_TO")
        missing=[k for k,v in {
            "EARTH_ONE_SMTP_HOST":self.host,
            "EARTH_ONE_SMTP_USERNAME":self.username,
            "EARTH_ONE_SMTP_PASSWORD":self.password,
            "EARTH_ONE_ALERT_FROM":self.sender,
            "EARTH_ONE_ALERT_TO":self.recipient,
        }.items() if not v]
        if missing:
            raise RuntimeError(f"Missing alert configuration: {', '.join(missing)}")

    def send(self, alert: Alert, dry_run: bool=False) -> dict[str, Any]:
        msg=EmailMessage()
        msg["Subject"]=alert.subject()
        msg["From"]=self.sender
        msg["To"]=self.recipient
        msg.set_content(alert.body())

        for path in alert.attachments:
            p=Path(path)
            if not p.exists():
                raise FileNotFoundError(p)
            data=p.read_bytes()
            ctype,_=mimetypes.guess_type(p.name)
            if ctype:
                maintype,subtype=ctype.split("/",1)
            else:
                maintype,subtype="application","octet-stream"
            msg.add_attachment(data,maintype=maintype,subtype=subtype,filename=p.name)

        if dry_run:
            return {
                "status":"DRY_RUN",
                "subject":msg["Subject"],
                "recipient":msg["To"],
                "attachments":[Path(x).name for x in alert.attachments],
            }

        if self.port == 465:
            context=ssl.create_default_context()
            with smtplib.SMTP_SSL(self.host,self.port,context=context,timeout=30) as server:
                server.login(self.username,self.password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(self.host,self.port,timeout=30) as server:
                server.starttls(context=ssl.create_default_context())
                server.login(self.username,self.password)
                server.send_message(msg)
        return {
            "status":"SENT",
            "subject":msg["Subject"],
            "recipient":msg["To"],
            "attachments":[Path(x).name for x in alert.attachments],
        }


def alert_from_execution(result: dict[str, Any]) -> Alert:
    summary=result.get("summary",{})
    failed=summary.get("FAILED",0)
    succeeded=summary.get("SUCCEEDED",0)
    planned=summary.get("PLANNED",0)
    if failed:
        severity="critical"
        title=f"{failed} monitoring job(s) failed"
        text="Earth One completed an execution cycle with failures. Investigation is required."
    elif planned:
        severity="info"
        title=f"{planned} monitoring job(s) planned"
        text="Earth One created an execution plan. No live processing was executed."
    else:
        severity="success"
        title=f"Monitoring cycle completed: {succeeded} job(s)"
        text="Earth One completed the monitoring cycle successfully."
    return Alert(
        severity=severity,
        title=title,
        summary=text,
        details={
            "succeeded":succeeded,
            "failed":failed,
            "planned":planned,
            "total":result.get("jobs_submitted"),
        },
    )


def alert_from_finding(
    finding_title: str,
    summary: str,
    details: dict[str, Any],
    attachments: Iterable[str]=(),
) -> Alert:
    return Alert(
        severity="finding",
        title=finding_title,
        summary=summary,
        details=details,
        attachments=tuple(attachments),
    )
