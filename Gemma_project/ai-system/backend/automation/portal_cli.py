"""
portal_cli.py — Standalone CLI diagnostic tool for the Riphah admission portal.

Run from the project root:
    python -m backend.automation.portal_cli [--headless] [--email x] [--password y]

Shows every browser action with detailed logs:
    [STEP 1] Opening login page ...
    [FIELD]  Detected input: name='email' type='email' placeholder='Email'
    [FILL]   input[name='email'] ← user@example.com
    [CLICK]  button:has-text('Login')
    [PAGE]   After Login → https://admissions.riphah.edu.pk/.../Student/application/List
    [INFO]   Dashboard title: Manage Applications
"""

import argparse
import json
import sys
import time
from typing import Optional

PORTAL_BASE  = "https://admissions.riphah.edu.pk/riphah_demo/public"
LOGIN_URL    = f"{PORTAL_BASE}/"
REG_URL      = f"{PORTAL_BASE}/account-registration"
APP_URL      = f"{PORTAL_BASE}/Student/application"
NAV_TIMEOUT  = 30_000   # ms
SHORT        = 3_000    # ms

# ── ANSI colour helpers ──────────────────────────────────────────────────────
def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m"

def info(msg):    print(_c("36", f"[INFO ] {msg}"))
def step(n, msg): print(_c("32;1", f"[STEP {n}] {msg}"))
def field(msg):   print(_c("33", f"[FIELD] {msg}"))
def fill(msg):    print(_c("34", f"[FILL ] {msg}"))
def click(msg):   print(_c("35", f"[CLICK] {msg}"))
def page_log(msg):print(_c("36;1", f"[PAGE ] {msg}"))
def warn(msg):    print(_c("33;1", f"[WARN ] {msg}"))
def error(msg):   print(_c("31;1", f"[ERROR] {msg}"))
def ok(msg):      print(_c("32", f"[OK   ] {msg}"))


# ── DOM snapshot helper ──────────────────────────────────────────────────────
_SNAPSHOT_JS = """() => {
    const vis = e => e.offsetWidth > 0 && e.offsetHeight > 0;
    const lbl = el => {
        if (el.id) {
            const l = document.querySelector("label[for='" + el.id + "']");
            if (l) return l.innerText.trim();
        }
        return el.getAttribute("aria-label") || el.placeholder || el.name || "";
    };
    const s = e => {
        if (e.name) return e.tagName.toLowerCase() + "[name='" + e.name + "']";
        if (e.id)   return e.tagName.toLowerCase() + "#" + e.id;
        return e.tagName.toLowerCase();
    };
    return {
        url:   location.href,
        title: document.title,
        body:  document.body.innerText.slice(0, 600),
        inputs: Array.from(document.querySelectorAll("input"))
            .filter(e => vis(e) && e.type !== "hidden")
            .map(e => ({sel: s(e), type: e.type, name: e.name, id: e.id,
                         placeholder: e.placeholder, label: lbl(e), required: e.required})),
        selects: Array.from(document.querySelectorAll("select")).filter(vis).map(e => ({
            sel: s(e), name: e.name, id: e.id, label: lbl(e),
            options: Array.from(e.options).map(o => ({val: o.value, text: o.text.trim()}))
        })),
        buttons: Array.from(document.querySelectorAll("button,[type=submit]"))
            .filter(vis).map(b => b.innerText.trim()).filter(t => t),
        links: Array.from(document.querySelectorAll("a[href]"))
            .filter(e => vis(e) && e.innerText.trim())
            .slice(0, 15).map(e => ({text: e.innerText.trim(), href: e.href}))
    };
}"""


def snapshot(page) -> dict:
    try:
        return page.evaluate(_SNAPSHOT_JS)
    except Exception as exc:
        return {"url": page.url, "title": "", "body": "", "inputs": [],
                "selects": [], "buttons": [], "links": [], "_err": str(exc)}


def dump_dom(dom: dict):
    info(f"URL   : {dom.get('url')}")
    info(f"Title : {dom.get('title')}")
    for inp in dom.get("inputs", []):
        field(f"INPUT  sel={inp['sel']:40s} type={inp['type']:10s} label='{inp.get('label','')}' required={inp.get('required')}")
    for sel in dom.get("selects", []):
        opts = ", ".join(f"{o['val']}={o['text']}" for o in sel.get("options", [])[:5])
        field(f"SELECT sel={sel['sel']:40s} label='{sel.get('label','')}' opts=[{opts}...]")
    for btn in dom.get("buttons", []):
        field(f"BUTTON text='{btn}'")
    for lnk in dom.get("links", []):
        field(f"LINK   text='{lnk['text']}' href={lnk['href']}")


# ── Fast fill helper ─────────────────────────────────────────────────────────

def fast_fill(page, selector: str, value: str, label: str = "") -> bool:
    try:
        page.locator(selector).fill(value, timeout=SHORT)
        fill(f"{selector:45s} ← {value[:60]!r}")
        return True
    except Exception as exc:
        warn(f"fill failed: {selector} — {exc}")
        return False


def fast_click(page, selector: str) -> bool:
    try:
        page.locator(selector).first.click(timeout=SHORT)
        click(f"{selector}")
        return True
    except Exception as exc:
        warn(f"click failed: {selector} — {exc}")
        return False


def fast_select(page, selector: str, value: str) -> bool:
    try:
        page.select_option(selector, value=value, timeout=SHORT)
        fill(f"SELECT {selector:40s} ← {value!r}")
        return True
    except Exception as exc:
        try:
            page.select_option(selector, label=value, timeout=SHORT)
            fill(f"SELECT {selector:40s} ← label={value!r}")
            return True
        except Exception:
            warn(f"select failed: {selector} val={value} — {exc}")
            return False


# ── Phase runners ─────────────────────────────────────────────────────────────

def run_login(page, email: str, password: str) -> bool:
    step(1, f"Loading login page: {LOGIN_URL}")
    page.goto(LOGIN_URL, timeout=NAV_TIMEOUT, wait_until="domcontentloaded")
    page.wait_for_timeout(800)
    dom = snapshot(page)
    page_log(f"{dom.get('title')} @ {dom.get('url')}")
    dump_dom(dom)

    step(2, "Filling login form")
    ok_e = fast_fill(page, "input[name='email']",    email,    "email")
    ok_p = fast_fill(page, "input[name='password']", password, "password")
    if not (ok_e and ok_p):
        error("Could not fill login credentials")
        return False

    step(3, "Clicking Login button")
    if not fast_click(page, "button:has-text('Login')"):
        fast_click(page, "input[type='submit']")
    page.wait_for_timeout(3000)

    dom = snapshot(page)
    page_log(f"After login → {dom.get('url')}")
    body = dom.get("body", "").lower()

    if "application" in dom.get("url", "") or "dashboard" in body or "apply" in body or "manage" in body:
        ok("Login successful")
        return True

    if "incorrect" in body or "invalid" in body or "wrong" in body:
        warn("Login credentials rejected by portal")
    else:
        warn(f"Unknown state after login. Body snippet: {dom.get('body','')[:200]}")
    return False


def run_register(page, data: dict, password: str) -> tuple[bool, str]:
    """Register a new account. Returns (success, error_message)."""
    step(4, f"Loading registration page: {REG_URL}")
    page.goto(REG_URL, timeout=NAV_TIMEOUT, wait_until="domcontentloaded")
    page.wait_for_timeout(800)
    dom = snapshot(page)
    page_log(f"{dom.get('title')} @ {dom.get('url')}")
    dump_dom(dom)

    step(5, "Filling registration form")
    # Split full_name → firstname
    full_name = data.get("full_name", data.get("firstname", "Applicant"))
    parts     = full_name.strip().split()
    firstname = parts[0] if parts else full_name

    fast_fill(page, "input[name='firstname']", firstname,            "name")
    fast_fill(page, "input[name='mobile']",    data.get("phone", "03001234567"), "mobile")
    fast_fill(page, "input[name='email']",     data.get("email", ""),            "email")
    fast_fill(page, "input[name='password']",  password,                         "password")
    fast_fill(page, "input[name='rpassword']", password,                         "confirm password")

    step(6, "Clicking Sign Up button")
    if not fast_click(page, "button:has-text('Sign Up')"):
        return False, "Sign Up button not found"
    page.wait_for_timeout(4000)

    dom  = snapshot(page)
    body = dom.get("body", "").lower()
    page_log(f"After registration → {dom.get('url')}")

    if "already" in body and ("email" in body or "registered" in body):
        warn("Email already registered — account exists, will try login")
        return True, "already_registered"

    if "verify" in body or "check your email" in body:
        return False, "email_verification_required"

    if "application" in dom.get("url","") or "dashboard" in body or "manage" in body:
        ok("Registration + auto-login succeeded")
        return True, ""

    # Assume success if we're on the login page (portal redirects there)
    if "login" in dom.get("url","") or "login" in body:
        ok("Registration submitted — redirected to login page")
        return True, ""

    return True, ""


def run_fill_application(page, data: dict) -> bool:
    step(7, f"Navigating to application form: {APP_URL}")
    page.goto(APP_URL, timeout=NAV_TIMEOUT, wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    dom = snapshot(page)
    page_log(f"{dom.get('title')} @ {dom.get('url')}")
    dump_dom(dom)

    step(8, "Filling personal information fields")
    # Name split
    full = data.get("full_name", "")
    parts = full.strip().split()
    fname = parts[0] if len(parts) >= 1 else full
    mname = parts[1] if len(parts) == 3 else ""
    lname = parts[-1] if len(parts) >= 2 else ""

    fast_fill(page, "input[name='fname']",         fname,                         "First Name")
    fast_fill(page, "input[name='mname']",         mname,                         "Middle Name")
    fast_fill(page, "input[name='lname']",         lname,                         "Last Name")
    fast_fill(page, "input[name='cnic']",          data.get("cnic", ""),          "CNIC")
    fast_fill(page, "input[name='dob']",           data.get("dob", ""),           "Date of Birth")
    fast_fill(page, "input[name='fathername']",    data.get("father_name", ""),   "Father Name")
    fast_fill(page, "input[name='lastinstitute']", data.get("last_institute", data.get("inter_marks", "")), "Last Institute")
    fast_fill(page, "input[name='email']",         data.get("email", ""),         "Email")
    fast_fill(page, "input[name='mobile']",        data.get("phone", ""),         "Mobile")
    fast_fill(page, "input[name='addressline1']",  data.get("address", ""),       "Address")
    fast_fill(page, "input[name='phone1']",        data.get("phone", ""),         "Phone")

    step(9, "Setting dropdown values")
    # Campus
    campus_map = {"islamabad": "3", "rawalpindi": "3", "lahore": "4", "malakand": "5"}
    campus_val = campus_map.get(data.get("campus", "").lower().split()[0], "3")
    fast_select(page, "select[name='branches_id']", campus_val)
    page.wait_for_timeout(1000)

    # Program type  (default Undergraduate)
    level_map = {"undergraduate": "2", "diploma": "3", "postgraduate": "4", "phd": "5", "doctoral": "5", "ms": "4", "mba": "4", "bs": "2", "be": "2"}
    program   = data.get("program", "").lower()
    level_val = "2"
    for kw, val in level_map.items():
        if kw in program:
            level_val = val
            break
    fast_select(page, "select[name='program_type_id']", level_val)
    page.wait_for_timeout(1500)

    # Gender
    gender_map = {"male": "Male", "female": "Female"}
    g_val = gender_map.get(data.get("gender", "").lower(), "Male")
    fast_select(page, "select[name='gender']", g_val)

    # Nationality (default Pakistan)
    fast_select(page, "select[name='nationality']", data.get("nationality", "Pakistan"))

    # City
    city = data.get("city", data.get("address", "Islamabad")).strip().split(",")[0].strip()
    fast_select(page, "select[name='city1']", city)

    # How did you hear
    fast_select(page, "select[name='aboutus']", "Friend or Family")

    step(10, "Submitting application form")
    if not fast_click(page, "button:has-text('SUBMIT')"):
        fast_click(page, "input[type='submit']")
    page.wait_for_timeout(5000)

    dom  = snapshot(page)
    body = dom.get("body", "").lower()
    page_log(f"After submit → {dom.get('url')}")

    success_signals = ["success", "submitted", "received", "thank you", "congratulation", "application id"]
    if any(s in body for s in success_signals):
        ok("Application submitted successfully")
        return True
    warn(f"Submission result unclear. Body: {dom.get('body','')[:300]}")
    return False


# ── Full flow ─────────────────────────────────────────────────────────────────

def run_full_flow(
    email: str,
    password: str,
    data: dict,
    headless: bool = True,
    screenshot_dir: Optional[str] = None,
):
    from playwright.sync_api import sync_playwright
    import os

    print("\n" + "="*70)
    print("  Riphah Admission Portal — Full Automation Diagnostic")
    print("="*70 + "\n")
    info(f"Email    : {email}")
    info(f"Password : {password[:4]}{'*'*(len(password)-4)}")
    info(f"Headless : {headless}")
    print()

    screenshots = []

    def ss(page, label: str):
        if screenshot_dir:
            os.makedirs(screenshot_dir, exist_ok=True)
            path = os.path.join(screenshot_dir, f"{int(time.time())}_{label}.png")
            try:
                page.screenshot(path=path)
                info(f"Screenshot: {path}")
                screenshots.append(path)
            except Exception:
                pass

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, slow_mo=50 if not headless else 0)
        ctx     = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        )
        page = ctx.new_page()

        try:
            # ── 1. Try login ──────────────────────────────────────────────
            logged_in = run_login(page, email, password)
            ss(page, "01_after_login")

            # ── 2. If login failed → register ─────────────────────────────
            if not logged_in:
                info("Login failed — attempting registration")
                reg_ok, reg_msg = run_register(page, data, password)
                ss(page, "02_after_register")

                if not reg_ok:
                    error(f"Registration failed: {reg_msg}")
                    browser.close()
                    return {"success": False, "message": reg_msg, "screenshots": screenshots}

                if reg_msg != "already_registered":
                    # Try login with new account
                    info("Logging in with new account...")
                    logged_in = run_login(page, email, password)
                    ss(page, "03_after_2nd_login")

                    if not logged_in:
                        warn("Login still failing after registration")
                        browser.close()
                        return {"success": False, "message": "Login failed after registration",
                                "screenshots": screenshots}
                else:
                    error("Account exists but wrong password — cannot proceed")
                    browser.close()
                    return {"success": False, "message": "Wrong password for existing account",
                            "screenshots": screenshots}

            # ── 3. Fill application ────────────────────────────────────────
            app_ok = run_fill_application(page, data)
            ss(page, "04_after_submit")

            dashboard_url = page.url
            print()
            print("="*70)
            if app_ok:
                ok("AUTOMATION COMPLETE — application submitted")
            else:
                warn("AUTOMATION DONE — submission result unclear (check screenshots)")
            info(f"Final URL : {dashboard_url}")
            info(f"Screenshots: {screenshots}")
            print("="*70 + "\n")

            browser.close()
            return {
                "success":       app_ok,
                "dashboard_url": dashboard_url,
                "screenshots":   screenshots,
                "message":       "Application submitted" if app_ok else "Submission unclear",
            }

        except Exception as exc:
            import traceback
            error(f"Fatal error: {exc}")
            traceback.print_exc()
            try:
                ss(page, "99_error")
            except Exception:
                pass
            browser.close()
            return {"success": False, "message": str(exc), "screenshots": screenshots}


# ── Diagnostic-only: just inspect pages ──────────────────────────────────────

def run_diagnostic(headless: bool = True):
    from playwright.sync_api import sync_playwright

    print("\n" + "="*70)
    print("  Riphah Portal — DOM Diagnostic (no form submission)")
    print("="*70 + "\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page    = browser.new_page()

        for url, label in [
            (LOGIN_URL, "Login / Homepage"),
            (REG_URL,   "Registration"),
        ]:
            step("→", f"{label}: {url}")
            page.goto(url, timeout=NAV_TIMEOUT, wait_until="domcontentloaded")
            page.wait_for_timeout(800)
            dom = snapshot(page)
            dump_dom(dom)
            print()

        browser.close()


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Riphah Portal Automation CLI")
    parser.add_argument("--email",    default="",    help="Portal email")
    parser.add_argument("--password", default="",    help="Portal password")
    parser.add_argument("--name",     default="Test User",  help="Applicant full name")
    parser.add_argument("--cnic",     default="61101-4531452-1", help="CNIC number")
    parser.add_argument("--phone",    default="03001234567", help="Phone number")
    parser.add_argument("--campus",   default="Islamabad",  help="Campus preference")
    parser.add_argument("--program",  default="BS Computer Science", help="Program")
    parser.add_argument("--address",  default="House 1, Street 1, Islamabad", help="Address")
    parser.add_argument("--no-headless", action="store_true", help="Show browser window")
    parser.add_argument("--diagnose", action="store_true",    help="Inspect portal DOM only (no login)")
    parser.add_argument("--screenshots", default="", help="Directory to save screenshots")
    args = parser.parse_args()

    headless = not args.no_headless

    if args.diagnose:
        run_diagnostic(headless=headless)
        sys.exit(0)

    if not args.email or not args.password:
        parser.error("--email and --password are required for full flow")

    data = {
        "full_name":   args.name,
        "email":       args.email,
        "cnic":        args.cnic,
        "phone":       args.phone,
        "campus":      args.campus,
        "program":     args.program,
        "address":     args.address,
        "gender":      "Male",
        "nationality": "Pakistan",
    }

    result = run_full_flow(
        email=args.email,
        password=args.password,
        data=data,
        headless=headless,
        screenshot_dir=args.screenshots or None,
    )
    sys.exit(0 if result.get("success") else 1)
