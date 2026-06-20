"""Application email template, token substitution, and delivery channels.

Implements Requirement 15:
- R15.1 provide an application email template containing the tokens
  ``job_title``, ``company``, and ``candidate_name``.
- R15.2 replace each token with the corresponding value when the email is
  generated (see Property 22: no unresolved placeholders remain).
- R15.3 support sending the application by email or mailto link.
- R15.4 support sending the application through in-platform delivery.
- R15.5 if the selected delivery channel is unavailable, block the send rather
  than falling back to another channel.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from urllib.parse import quote

from app.services.email import _smtp_ready, send_email

# --- Template (R15.1) -------------------------------------------------------
# The template intentionally references every token exactly by its name wrapped
# in single braces. ``render_application_email`` substitutes each one so no
# ``{token}`` marker survives (Property 22).
TOKEN_NAMES: tuple[str, ...] = ("job_title", "company", "candidate_name")

SUBJECT_TEMPLATE = "Application for {job_title} at {company}"

BODY_TEMPLATE = (
    "Hello {company} team,\n"
    "\n"
    "My name is {candidate_name} and I would like to apply for the "
    "{job_title} position at {company}.\n"
    "\n"
    "Please find my application attached. I look forward to hearing from you "
    "about the {job_title} role.\n"
    "\n"
    "Best regards,\n"
    "{candidate_name}\n"
)


class ApplicationDeliveryChannel(str, Enum):
    """Supported application delivery channels (R15.3, R15.4)."""

    email = "email"
    mailto = "mailto"
    in_platform = "in_platform"


class ChannelUnavailableError(RuntimeError):
    """Raised when the selected delivery channel is unavailable.

    The send is blocked and the system never falls back to another channel
    (R15.5).
    """

    def __init__(self, channel: ApplicationDeliveryChannel) -> None:
        self.channel = channel
        super().__init__(f"Delivery channel '{channel.value}' is unavailable; send blocked (no fallback).")


@dataclass(frozen=True)
class RenderedApplicationEmail:
    """A fully rendered application email with no unresolved tokens."""

    subject: str
    body: str

    @property
    def full_text(self) -> str:
        return f"{self.subject}\n\n{self.body}"


@dataclass(frozen=True)
class ApplicationDeliveryResult:
    """Outcome of dispatching an application through a channel."""

    channel: ApplicationDeliveryChannel
    rendered: RenderedApplicationEmail
    email_sent: bool = False
    mailto_link: str | None = None
    in_platform: bool = False


def _substitute(template: str, values: dict[str, str]) -> str:
    """Replace each ``{token}`` marker with its value.

    Uses explicit string replacement (not ``str.format``) so values that happen
    to contain brace characters cannot break rendering or re-introduce markers.
    """

    result = template
    for token in TOKEN_NAMES:
        result = result.replace("{" + token + "}", values[token])
    return result


def render_application_email(*, job_title: str, company: str, candidate_name: str) -> RenderedApplicationEmail:
    """Render the application email, substituting every token (R15.2 / Property 22).

    Each of ``job_title``, ``company`` and ``candidate_name`` is substituted into
    both the subject and the body, leaving no unresolved ``{token}`` placeholders.
    """

    values = {
        "job_title": str(job_title),
        "company": str(company),
        "candidate_name": str(candidate_name),
    }
    return RenderedApplicationEmail(
        subject=_substitute(SUBJECT_TEMPLATE, values),
        body=_substitute(BODY_TEMPLATE, values),
    )


def channel_available(channel: ApplicationDeliveryChannel) -> bool:
    """Report whether a delivery channel can currently be used (R15.5).

    - ``email`` requires a configured SMTP relay.
    - ``mailto`` builds a client-side link and is always available.
    - ``in_platform`` records the message in the platform and is always available.
    """

    if channel == ApplicationDeliveryChannel.email:
        return _smtp_ready()
    if channel in (ApplicationDeliveryChannel.mailto, ApplicationDeliveryChannel.in_platform):
        return True
    return False


def build_mailto_link(*, to_email: str, rendered: RenderedApplicationEmail) -> str:
    """Build an RFC 6068 ``mailto:`` link from a rendered email (R15.3)."""

    query = f"subject={quote(rendered.subject)}&body={quote(rendered.body)}"
    return f"mailto:{quote(to_email)}?{query}"


def send_application_email(
    *,
    channel: ApplicationDeliveryChannel,
    to_email: str,
    job_title: str,
    company: str,
    candidate_name: str,
) -> ApplicationDeliveryResult:
    """Dispatch an application through the selected channel.

    If the selected channel is unavailable the send is blocked by raising
    :class:`ChannelUnavailableError`; the function never falls back to another
    channel (R15.5).
    """

    if not channel_available(channel):
        raise ChannelUnavailableError(channel)

    rendered = render_application_email(
        job_title=job_title,
        company=company,
        candidate_name=candidate_name,
    )

    if channel == ApplicationDeliveryChannel.email:
        sent = send_email(to_email=to_email, subject=rendered.subject, text_body=rendered.body)
        if not sent:
            # SMTP became unavailable between the availability check and the send;
            # block rather than silently switching channels (R15.5).
            raise ChannelUnavailableError(channel)
        return ApplicationDeliveryResult(channel=channel, rendered=rendered, email_sent=True)

    if channel == ApplicationDeliveryChannel.mailto:
        link = build_mailto_link(to_email=to_email, rendered=rendered)
        return ApplicationDeliveryResult(channel=channel, rendered=rendered, mailto_link=link)

    # in_platform
    return ApplicationDeliveryResult(channel=channel, rendered=rendered, in_platform=True)
