"""
portal_explorer.py — Pre-flight deep exploration of the Riphah admission portal.

Runs ONCE before any user data is collected.  Discovers:
  • Login-form CSS selectors  (grouped by parent <form>, not flat DOM)
  • Registration-form CSS selectors and field→data_key mapping
  • Whether the portal needs email / OTP verification after signup
  • Navigation hints for the post-login admission form

The result is stored in the workflow cache (3-day TTL inside portal_schemas.json).
Subsequent sessions load from cache in < 1 second — no re-exploration needed.
"""

import asyncio
import json
import os
import re
import threading
import time
from typing import Optional

PORTAL_URL          = os.getenv("RIPHAH_PORTAL_URL", "https://admissions.riphah.edu.pk/riphah_demo/public/")
NAV_TIMEOUT         = 25_000   # ms
SHORT_TIMEOUT       = 2_000    # ms
EXPLORE_TIMEOUT_SEC = 35       # hard wall-clock timeout for sync wrapper

# ---------------------------------------------------------------------------
# Fallback field list used when the portal is unreachable
# ---------------------------------------------------------------------------

DEFAULT_DATA_FIELDS = [
    {"key": "full_name",       "label": "Full Name (as on CNIC)",                "type": "text",     "required": True},
    {"key": "father_name",     "label": "Father's Full Name",                     "type": "text",     "required": True},
    {"key": "cnic",            "label": "CNIC / B-Form Number",                   "type": "text",     "required": True},
    {"key": "dob",             "label": "Date of Birth (DD/MM/YYYY)",             "type": "date",     "required": True},
    {"key": "gender",          "label": "Gender",                                 "type": "select",   "required": True,
     "options": ["Male", "Female", "Other"]},
    {"key": "email",           "label": "Email Address (will be used to create your portal account)", "type": "email", "required": True},
    {"key": "portal_password", "label": "Choose a Portal Password (min 8 chars — you'll use this to log in later)", "type": "password", "required": True},
    {"key": "phone",           "label": "Phone Number",                           "type": "phone",    "required": True},
    {"key": "program",         "label": "Program Applying For",                   "type": "text",     "required": True},
    {"key": "campus",          "label": "Preferred Campus",                       "type": "text",     "required": True},
    {"key": "matric_marks",    "label": "Matric / O-Level Marks or %",            "type": "text",     "required": True},
    {"key": "inter_marks",     "label": "Intermediate / A-Level Marks or %",      "type": "text",     "required": True},
    {"key": "entry_test",      "label": "Entry Test Score (MDCAT / ECAT / NAT)",  "type": "text",     "required": True},
    {"key": "address",         "label": "Complete Home Address",                   "type": "text",     "required": True},
]

DEFAULT_DOCS = ["cnic", "photo", "matric_certificate", "inter_certificate"]


# ---------------------------------------------------------------------------
# PortalExplorer
# ---------------------------------------------------------------------------

class PortalExplorer:
    """
    Visits the Riphah portal homepage (and optionally the registration page)
    and extracts a structured workflow schema without any login credentials.
    """

    def __init__(self):
        self._pw      = None
        self._browser = None
        self.page     = None
        self.log: list[str] = []

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def _info(self, msg: str):
        self.log.append(msg)
        print(f"[Explorer] {msg}")

    async def _start(self):
        from playwright.async_api import async_playwright
        self._pw      = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=True)
        ctx = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )
        self.page = await ctx.new_page()
        self.page.set_default_timeout(SHORT_TIMEOUT)

    async def _stop(self):
        try:
            if self._browser:
                await self._browser.close()
            if self._pw:
                await self._pw.stop()
        except Exception:
            pass

    async def _go(self, url: str):
        await self.page.goto(url, timeout=NAV_TIMEOUT, wait_until="domcontentloaded")
        await self.page.wait_for_timeout(1200)

    # ── DOM snapshot — groups inputs by parent <form> ────────────────────────

    async def _snapshot(self) -> dict:
        """
        Returns:
          url, title, body_text — page metadata
          forms   — list of {id, heading, submit_text, inputs, selects, file_inputs}
          links   — all visible anchor tags
          buttons — all visible buttons (flat, for navigation detection)
        """
        try:
            return await self.page.evaluate(r"""() => {
                const vis  = e => e.offsetWidth > 0 && e.offsetHeight > 0;
                const lbl  = el => {
                    if (el.id) {
                        const l = document.querySelector('label[for="' + el.id + '"]');
                        if (l) return l.innerText.trim().slice(0, 80);
                    }
                    return el.getAttribute('aria-label') || el.placeholder || el.name || '';
                };
                const csel = e => {
                    if (e.name)        return e.tagName.toLowerCase() + '[name="' + e.name + '"]';
                    if (e.id)          return e.tagName.toLowerCase() + '#' + e.id;
                    if (e.placeholder) return e.tagName.toLowerCase() + '[placeholder="' + e.placeholder + '"]';
                    return '';
                };
                const mapInp = e => ({
                    sel: csel(e), type: e.type, name: e.name, id: e.id,
                    placeholder: e.placeholder, label: lbl(e), required: e.required
                });

                // Group by parent <form>
                const forms = Array.from(document.querySelectorAll('form')).map(form => {
                    const container = form.closest('[class*="card"],[class*="box"],[class*="panel"],section') || form;
                    const heading   = container.querySelector('h1,h2,h3,h4,h5,legend,p.title,p.subtitle')
                                              ?.innerText?.trim() || '';
                    const allBtns   = Array.from(form.querySelectorAll('button,[type=submit]')).filter(vis);
                    return {
                        id:          form.id || '',
                        action:      form.getAttribute('action') || '',
                        heading:     heading,
                        submit_text: allBtns.map(b => b.innerText.trim().slice(0, 60)).join(' | '),
                        inputs:      Array.from(form.querySelectorAll('input')).filter(vis).map(mapInp),
                        selects:     Array.from(form.querySelectorAll('select')).filter(vis).map(e => ({
                                         sel: csel(e), name: e.name, id: e.id, label: lbl(e),
                                         options: Array.from(e.options).slice(0, 25).map(o => ({
                                             value: o.value, text: o.text.trim()
                                         }))
                                     })),
                        textareas:   Array.from(form.querySelectorAll('textarea')).filter(vis).map(e => ({
                                         sel: csel(e), name: e.name, id: e.id, label: lbl(e),
                                         placeholder: e.placeholder
                                     })),
                        file_inputs: Array.from(form.querySelectorAll('input[type=file]')).filter(vis).map(e => ({
                                         sel: csel(e), name: e.name, id: e.id, label: lbl(e),
                                         accept: e.accept
                                     })),
                    };
                });

                return {
                    url:        window.location.href,
                    title:      document.title,
                    body_text:  document.body.innerText.slice(0, 2500),
                    forms:      forms,
                    links:      Array.from(document.querySelectorAll('a[href]'))
                                    .filter(e => vis(e) && e.innerText.trim())
                                    .map(e => ({ text: e.innerText.trim().slice(0, 80), href: e.href }))
                                    .slice(0, 50),
                    buttons:    Array.from(document.querySelectorAll('button,[type=submit],[role=button]'))
                                    .filter(vis)
                                    .map(e => ({ text: e.innerText.trim().slice(0, 80) })),
                };
            }""")
        except Exception:
            return {"url": "", "title": "", "body_text": "", "forms": [], "links": [], "buttons": []}

    # ── Click helper ─────────────────────────────────────────────────────────

    async def _click_first(self, candidates: list[str]) -> bool:
        for text in candidates:
            for fn in [
                lambda t=text: self.page.get_by_role("button", name=t, exact=False).first.click(timeout=SHORT_TIMEOUT),
                lambda t=text: self.page.get_by_role("link",   name=t, exact=False).first.click(timeout=SHORT_TIMEOUT),
                lambda t=text: self.page.get_by_text(t, exact=False).first.click(timeout=SHORT_TIMEOUT),
            ]:
                try:
                    await fn()
                    await self.page.wait_for_timeout(1200)
                    return True
                except Exception:
                    continue
        return False

    # ── Field-purpose inference ──────────────────────────────────────────────

    def _identify_field_purpose(self, field: dict) -> Optional[str]:
        """
        Map a single form field to a data_key.
        Returns None when the purpose cannot be determined with confidence.
        """
        ftype = field.get("type", "text")
        text  = " ".join([
            field.get("label", ""),
            field.get("placeholder", ""),
            field.get("name", ""),
        ]).lower()

        # Password — check confirm variant first (more specific)
        if ftype == "password" or "password" in text:
            if any(kw in text for kw in ["confirm", "confirmation", "repeat", "retype", "re-enter", "re_enter"]):
                return "portal_password_confirm"
            return "portal_password"

        if ftype == "email" or "email" in text:
            return "email"

        if any(kw in text for kw in ["cnic", "national id", "national identity", "nic", "b-form", "bform"]):
            return "cnic"

        if any(kw in text for kw in ["phone", "mobile", "cell", "contact no", "contact number", "tel"]):
            return "phone"

        # Father / guardian before generic name
        if any(kw in text for kw in ["father", "guardian", "parent"]):
            return "father_name"

        if any(kw in text for kw in ["name", "applicant"]) and ftype not in ("password",):
            return "full_name"

        if any(kw in text for kw in ["dob", "birth", "date of birth", "birth date"]):
            return "dob"

        return None  # unmapped — logged, never silently discarded

    def _map_form_fields(self, fields: list) -> tuple[dict, list]:
        """
        Return (field_map: {data_key -> css_selector}, unmapped: [raw field dicts]).
        Skips hidden/submit/button/file inputs.
        Takes first discovered selector per data_key (no overwrite).
        """
        field_map: dict[str, str] = {}
        unmapped: list            = []
        skip_types = {"hidden", "submit", "button", "image", "checkbox", "radio", "file"}

        for f in fields:
            if not f.get("sel") or f.get("type", "text") in skip_types:
                continue
            purpose = self._identify_field_purpose(f)
            if purpose:
                if purpose not in field_map:
                    field_map[purpose] = f["sel"]
            else:
                unmapped.append({"sel": f["sel"], "type": f.get("type",""), "label": f.get("label",""), "placeholder": f.get("placeholder",""), "name": f.get("name","")})

        return field_map, unmapped

    def _find_by_keywords(self, fields: list, keywords: list) -> Optional[dict]:
        """Find first field whose label/placeholder/name contains any keyword."""
        for f in fields:
            text = (f.get("label","") + " " + f.get("placeholder","") + " " + f.get("name","")).lower()
            if any(kw in text for kw in keywords):
                return f
        return None

    # ── Form classification ───────────────────────────────────────────────────

    def _classify_forms(self, forms: list) -> tuple[Optional[dict], Optional[dict]]:
        """
        Separate login form from registration form on the same page.
        Both may appear on the Riphah homepage.

        Returns (login_form_dict, registration_form_dict).
        Either may be None if not found.
        """
        login_form = None
        reg_form   = None

        def _has_pw(form):
            return any(i.get("type") == "password" for i in form.get("inputs", []))

        def _has_email(form):
            return any(
                i.get("type") == "email" or "email" in (i.get("name","") + i.get("placeholder","")).lower()
                for i in form.get("inputs", [])
            )

        def _has_confirm(form):
            return any(
                any(kw in (i.get("placeholder","") + i.get("name","")).lower()
                    for kw in ["confirm", "confirmation", "repeat"])
                for i in form.get("inputs", [])
            )

        def _has_cnic(form):
            return any(
                any(kw in (i.get("placeholder","") + i.get("name","")).lower()
                    for kw in ["cnic", "national id", "nic"])
                for i in form.get("inputs", [])
            )

        def _reg_heading(form):
            heading     = (form.get("heading","") + " " + form.get("submit_text","")).lower()
            return any(kw in heading for kw in ["register","create","sign up","new","account"])

        for form in forms:
            if not _has_pw(form):
                continue
            # Registration heuristic: confirm field OR CNIC field OR register-keyword OR ≥4 visible inputs
            visible_inputs = [i for i in form.get("inputs",[]) if i.get("type","") not in ("hidden",)]
            is_reg = (
                _has_confirm(form)
                or _has_cnic(form)
                or _reg_heading(form)
                or len(visible_inputs) >= 4
            )
            if is_reg:
                reg_form = form
            elif _has_email(form):
                login_form = form

        # If one form was missed, try by elimination
        if reg_form and not login_form:
            for form in forms:
                if form is reg_form:
                    continue
                if _has_pw(form) and _has_email(form):
                    login_form = form
                    break

        if not login_form and not reg_form and len(forms) >= 2:
            # Last resort: shorter form = login, longer = registration
            sorted_f   = sorted(forms, key=lambda f: len(f.get("inputs", [])))
            login_form = sorted_f[0]
            reg_form   = sorted_f[-1]

        return login_form, reg_form

    # ── Build login_form schema ───────────────────────────────────────────────

    def _build_login_schema(self, login_form: Optional[dict]) -> dict:
        if not login_form:
            return {}
        inputs = login_form.get("inputs", [])
        email_f = self._find_by_keywords(inputs, ["email"])
        pw_f    = next((i for i in inputs if i.get("type") == "password"), None)
        submit  = login_form.get("submit_text", "").split("|")[0].strip() or "Login"
        return {
            "email_sel":    email_f["sel"] if email_f else None,
            "password_sel": pw_f["sel"]    if pw_f    else None,
            "submit_text":  submit,
        }

    # ── Build registration schema ─────────────────────────────────────────────

    def _build_registration_schema(self, reg_form: Optional[dict], reg_url: str = "") -> dict:
        if not reg_form:
            return {"url": reg_url, "field_map": {}, "submit_text": None, "unmapped_fields": []}
        all_fields  = reg_form.get("inputs", []) + reg_form.get("textareas", [])
        field_map, unmapped = self._map_form_fields(all_fields)
        submit_text = reg_form.get("submit_text", "").split("|")[0].strip() or None
        return {
            "url":            reg_url or "",
            "field_map":      field_map,
            "submit_text":    submit_text,
            "unmapped_fields": unmapped,
            "all_buttons":    reg_form.get("submit_text",""),
        }

    # ── Verification detection ────────────────────────────────────────────────

    async def _detect_verification(self) -> dict:
        """
        Read the current page body and classify whether the portal
        requires email verification or OTP after registration.
        Returns {"type": "none"|"email"|"otp"|"unknown"}
        """
        try:
            body = (await self.page.inner_text("body")).lower()
        except Exception:
            return {"type": "unknown"}

        otp_signals   = ["otp","one-time password","verification code","sms code","enter code"]
        email_signals = ["verify your email","verification email","check your email",
                         "confirm your email","activate your account","email sent"]
        ok_signals    = ["welcome","dashboard","apply online","my applications",
                         "congratulations","start application"]

        if any(s in body for s in otp_signals):
            return {"type": "otp"}
        if any(s in body for s in email_signals):
            return {"type": "email"}
        if any(s in body for s in ok_signals):
            return {"type": "none"}
        return {"type": "unknown"}

    # ── Explore registration page (if separate URL) ───────────────────────────

    async def _explore_registration_page(self, portal_url: str, register_link: Optional[dict]) -> dict:
        """
        If the registration form is on a separate page, navigate there and
        build a richer schema.  Returns schema dict (same shape as _build_registration_schema).
        """
        target_url = (register_link or {}).get("href", "")
        portal_clean = portal_url.rstrip("/")

        navigated = False
        if target_url and target_url.rstrip("/") not in (portal_clean, portal_clean + "/", ""):
            try:
                await self._go(target_url)
                navigated = True
            except Exception:
                pass

        if not navigated:
            clicked = await self._click_first(
                ["Create an Account", "Create Account", "Register", "Sign Up", "New User", "New Applicant"]
            )
            if not clicked:
                self._info("Could not navigate to separate registration page")
                return {"url": "", "field_map": {}, "submit_text": None, "unmapped_fields": []}

        await self.page.wait_for_timeout(800)
        dom   = await self._snapshot()
        forms = dom.get("forms", [])

        _, reg_form = self._classify_forms(forms)
        if not reg_form and forms:
            reg_form = forms[0]  # best-effort fallback

        schema = self._build_registration_schema(reg_form, dom.get("url", ""))
        self._info(f"Separate reg page: {len(schema['field_map'])} mapped, "
                   f"{len(schema['unmapped_fields'])} unmapped")
        return schema

    # ── Main entry point ──────────────────────────────────────────────────────

    async def explore(self, portal_url: str) -> dict:
        """
        Full portal exploration.  Returns a workflow schema dict suitable
        for caching and use by AdmissionPortalAgent.
        """
        self._info(f"Starting exploration: {portal_url}")
        try:
            await self._start()
            await self._go(portal_url)

            dom   = await self._snapshot()
            forms = dom.get("forms", [])
            links = dom.get("links", [])

            self._info(f"Homepage: '{dom.get('title','')}' — {len(forms)} forms detected")

            # Classify forms on homepage
            login_form, reg_form = self._classify_forms(forms)
            self._info(
                f"Classified: login={'yes' if login_form else 'no'}, "
                f"reg={'yes' if reg_form else 'no (may be separate page)'}"
            )

            # Build login schema
            login_schema = self._build_login_schema(login_form)
            self._info(f"Login schema: email_sel={login_schema.get('email_sel')}, "
                       f"pw_sel={login_schema.get('password_sel')}, "
                       f"submit='{login_schema.get('submit_text')}'")

            # Find registration link for separate-page portals
            register_link = None
            for link in links:
                if any(kw in link["text"].lower() for kw in
                       ["create", "register", "sign up", "new user", "new applicant"]):
                    register_link = link
                    break

            # Registration schema
            if reg_form:
                # Registration form is already on the homepage
                reg_schema = self._build_registration_schema(reg_form, portal_url)
                self._info(f"Registration on homepage: {list(reg_schema['field_map'].keys())}")
            else:
                # Registration is on a separate page
                self._info("Registration appears to be on a separate page — navigating...")
                reg_schema = await self._explore_registration_page(portal_url, register_link)

            # Verification detection (best-effort from current page state)
            verification = await self._detect_verification()
            self._info(f"Verification hint: {verification['type']}")

            schema = {
                "portal_url":         portal_url,
                "explored_at":        time.strftime("%Y-%m-%dT%H:%M:%S"),
                "scan_failed":        False,
                "login_form":         login_schema,
                "registration":       reg_schema,
                "verification":       verification,
                "data_fields":        DEFAULT_DATA_FIELDS,
                "required_documents": DEFAULT_DOCS,
                "exploration_log":    self.log,
            }
            self._info(f"Exploration complete — login={bool(login_schema.get('email_sel'))}, "
                       f"reg_fields={list(reg_schema['field_map'].keys())}")
            return schema

        except Exception as e:
            self._info(f"Exploration failed: {e}")
            return {
                "portal_url":         portal_url,
                "explored_at":        time.strftime("%Y-%m-%dT%H:%M:%S"),
                "scan_failed":        True,
                "error":              str(e),
                "login_form":         {},
                "registration":       {"url": "", "field_map": {}, "submit_text": None, "unmapped_fields": []},
                "verification":       {"type": "unknown"},
                "data_fields":        DEFAULT_DATA_FIELDS,
                "required_documents": DEFAULT_DOCS,
                "exploration_log":    self.log,
            }
        finally:
            await self._stop()


# ---------------------------------------------------------------------------
# Sync wrapper (used by admission_workflow.py from a thread-pool context)
# ---------------------------------------------------------------------------

def explore_portal_sync(portal_url: str = PORTAL_URL, timeout_seconds: int = EXPLORE_TIMEOUT_SEC) -> dict:
    """
    Check the workflow cache first.  If fresh, return cached schema.
    Otherwise run PortalExplorer, save result to cache, and return it.
    Runs inside a daemon thread to enforce the hard timeout.
    """
    from backend.automation.schema_cache import get_workflow, save_workflow

    # Cache hit
    cached = get_workflow(portal_url)
    if cached and not cached.get("scan_failed"):
        print(f"[Explorer] Cache hit — loaded workflow schema for {portal_url}")
        return cached

    # Cache miss — run exploration
    result: dict = {}

    def _run():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result.update(loop.run_until_complete(_explore_async(portal_url)))
            loop.close()
        except Exception as e:
            print(f"[Explorer] Thread error: {e}")

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=timeout_seconds)

    if result.get("explored_at") and not result.get("scan_failed"):
        save_workflow(portal_url, result)

    if not result.get("explored_at"):
        print("[Explorer] Exploration timed out — using defaults")
        return {
            "portal_url":         portal_url,
            "explored_at":        time.strftime("%Y-%m-%dT%H:%M:%S"),
            "scan_failed":        True,
            "login_form":         {},
            "registration":       {"url": "", "field_map": {}, "submit_text": None, "unmapped_fields": []},
            "verification":       {"type": "unknown"},
            "data_fields":        DEFAULT_DATA_FIELDS,
            "required_documents": DEFAULT_DOCS,
        }

    return result


async def _explore_async(portal_url: str) -> dict:
    return await PortalExplorer().explore(portal_url)
