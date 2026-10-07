"""Privacy, terms and support pages for the hosted evidence connector.

A ChatGPT app submission needs a published privacy policy and a support contact. These
pages state only what the server actually does, and read their numbers from the code so the
text cannot drift from the behaviour. The operator should have them reviewed by counsel and
set EPI_SUPPORT_EMAIL (and optionally EPI_OPERATOR_NAME) before submitting.
"""

from __future__ import annotations

import html
import os

_CSS = (
    "body{font-family:system-ui,sans-serif;max-width:44em;margin:2.5em auto;padding:0 1em;line-height:1.6;"
    "color:#1b1f23;background:#fff}h1{font-size:1.6em}h2{font-size:1.15em;margin-top:1.6em}"
    "code{background:#f4f6f8;padding:.1em .3em}.meta{color:#5b6570;font-size:.9em}"
    "@media (prefers-color-scheme:dark){body{background:#14171a;color:#e6e8ea}code{background:#222830}"
    ".meta{color:#9aa4ae}a{color:#7db7ff}}"
)
UPDATED = "2026-10-07"


def operator() -> str:
    return (os.environ.get("EPI_OPERATOR_NAME") or "EPI Labs").strip()


def contact() -> str:
    """Support contact: an email when configured, otherwise the public site."""
    email = (os.environ.get("EPI_SUPPORT_EMAIL") or "").strip()
    return email or "https://epilabs.org"


def _contact_html() -> str:
    c = contact()
    href = f"mailto:{c}" if "@" in c else c
    return f'<a href="{html.escape(href, quote=True)}">{html.escape(c)}</a>'


def _page(title: str, body: str) -> str:
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>{html.escape(title)}</title><style>{_CSS}</style></head><body>"
        f"<h1>{html.escape(title)}</h1><p class=meta>{html.escape(operator())} · updated {UPDATED}</p>{body}"
        '<p class=meta><a href="/privacy">Privacy</a> · <a href="/terms">Terms</a> · '
        '<a href="/support">Support</a></p></body></html>'
    )


def _hours() -> int:
    from epi_mcp.tools import DOWNLOAD_TTL_SECONDS

    return DOWNLOAD_TTL_SECONDS // 3600


def privacy_html() -> str:
    h = _hours()
    return _page(
        "Privacy policy: EPI Evidence Sealer",
        f"""
<p>EPI Evidence Sealer turns a conversation or an agent run that <strong>you ask it to seal</strong>
into a signed, tamper-evident file. This page says what it receives, what it does with it and
how to reach us. Questions: {_contact_html()}.</p>

<h2>What we receive</h2>
<ul>
<li><strong>The content you ask to seal:</strong> the messages, tool calls and file names or hashes
the chat assistant sends when you ask it to seal a conversation, or the text or export file you
upload at <code>/seal</code>. We receive what the assistant sends when you ask it to seal; we do not
receive your other conversations.</li>
<li><strong>Sign-in details, if you choose to sign in:</strong> with GitHub we receive your public
username and an account number; your verified email only if you tick the box. With another
identity provider we receive the account's issuer and identifier, and the verified email only if you
tick the box. Approving without signing in gives you a random pseudonym and we learn nothing about you.</li>
<li><strong>Technical data:</strong> your IP address, used to rate-limit sealing from the public page. It is
kept in memory for up to one hour. Our hosting provider may keep ordinary server logs.</li>
</ul>

<h2>What we do with it</h2>
<ul>
<li>We build the sealed <code>.epi</code> file, sign it, and keep it so you can open or download it.
<strong>We delete the file {h} hours after sealing.</strong> Download it if you want to keep it.</li>
<li>The view and download links contain a random secret and stop working after {h} hours. Anyone who has
the link can open the file until then, so treat the link like the conversation itself.</li>
<li>To add a trusted time to the file we send a <em>hash</em> of the file's list (not the content) to a public
timestamp service (FreeTSA, <code>freetsa.org</code>).</li>
<li>We do not sell your content, use it for advertising, or use it to train models.</li>
<li>Passwords, keys and other people's personal data should not be sealed. The assistant is instructed to
replace them with <code>[REDACTED]</code>, but you are responsible for what you ask it to seal.</li>
</ul>

<h2>Who else is involved</h2>
<ul>
<li>Our hosting provider (Render) runs the server.</li>
<li>GitHub or your identity provider, only if you choose to sign in.</li>
<li>FreeTSA, which receives only the hash described above.</li>
</ul>

<h2>Your choices</h2>
<ul>
<li>Seal nothing: the service only acts when you ask. Use pseudonymous approval to stay anonymous.</li>
<li>Delete early: write to {_contact_html()} with the artifact id and we will remove the file.
Otherwise it is deleted automatically after {h} hours.</li>
<li>Ask what we hold about you, or ask us to delete it, at the same address.</li>
</ul>

<h2>Security</h2>
<p>Connections use HTTPS. Sealed files are signed so any later change is detectable, and links are
unguessable and expire. No system is perfectly secure; do not seal anything you could not accept being
exposed during the {h}-hour window.</p>

<h2>Children</h2>
<p>The service is not directed to children under 13 (or the age required in your country).</p>

<h2>Changes</h2>
<p>If this policy changes, the date above changes. Material changes are noted on <a href="https://epilabs.org">epilabs.org</a>.</p>
""",
    )


def terms_html() -> str:
    h = _hours()
    return _page(
        "Terms of use: EPI Evidence Sealer",
        f"""
<h2>The service</h2>
<p>EPI Evidence Sealer creates signed, tamper-evident records of content you provide, and lets you
view and download them for {h} hours. It is provided as is, without warranty, and may change or be unavailable.</p>

<h2>What a seal means</h2>
<p>A seal shows that the sealed content has not changed since it was sealed. It does <strong>not</strong>
prove that the content is complete, true, or that it came from a particular AI product or person. A signature
by an unverified signer shows who held the signing key, not who they are. Do not rely on a seal as legal,
compliance or financial advice.</p>

<h2>Your responsibilities</h2>
<ul>
<li>Seal only content you have the right to share with us.</li>
<li>Do not seal passwords, access keys, or other people's personal data without a lawful basis.</li>
<li>Do not use the service to break the law, to harm others, or to overload it. We limit how often you can seal.</li>
<li>Keep your own copy: we delete files after {h} hours.</li>
</ul>

<h2>Liability</h2>
<p>To the extent the law allows, we are not liable for indirect or consequential loss, or for loss of data
we have deleted as described above. Nothing here limits liability that cannot be limited by law.</p>

<h2>Contact</h2><p>{_contact_html()}</p>
""",
    )


def support_html() -> str:
    h = _hours()
    return _page(
        "Support: EPI Evidence Sealer",
        f"""
<p>Contact: {_contact_html()}. Please include the artifact id (shown when a file is sealed) and what you saw.</p>

<h2>Common questions</h2>
<ul>
<li><strong>How do I use it?</strong> Switch the connector on in your chat and say "Seal this chat with the
EPI Evidence Sealer." You get a view link, a download link and a SHA-256.</li>
<li><strong>The link stopped working.</strong> Files are deleted {h} hours after sealing. Download yours.</li>
<li><strong>My chat assistant would not seal.</strong> Use <a href="/seal">/seal</a>: upload your chat export
zip (no connector or model involved).</li>
<li><strong>How do I check a saved file?</strong> Upload it at
<a href="https://epilabs.org/verify">epilabs.org/verify</a>, or run <code>epi verify file.epi</code>.</li>
<li><strong>Delete my data.</strong> Write to us with the artifact id, or wait {h} hours.</li>
</ul>
<p>See also the <a href="/privacy">privacy policy</a> and <a href="/terms">terms</a>.</p>
""",
    )
