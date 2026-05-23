"""
Command router for the PC AI Assistant.

Parses natural-language commands and dispatches them to the correct
portal automation action.  Each action is run synchronously (sync_playwright)
so no event loop is needed from the caller.

Supported commands (examples):
    open admissions portal
    diagnose portal
    login to riphah admissions
    register on riphah
    apply for admission / fill application form
    check application status
    help / commands
    quit / exit
"""

import sys


# ── ANSI colour helpers (mirror portal_cli.py) ───────────────────────────────
def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m"

def _info(msg):  print(_c("36",   f"[INFO ] {msg}"))
def _ok(msg):    print(_c("32",   f"[OK   ] {msg}"))
def _warn(msg):  print(_c("33;1", f"[WARN ] {msg}"))
def _error(msg): print(_c("31;1", f"[ERROR] {msg}"))
def _step(msg):  print(_c("32;1", f"[STEP ] {msg}"))


# ── Intent classifier ─────────────────────────────────────────────────────────

_INTENTS = {
    "open_portal": [
        "open admissions portal", "open portal", "go to admissions",
        "launch portal", "visit riphah", "open riphah",
    ],
    "diagnose": [
        "diagnose portal", "inspect portal", "scan portal",
        "check portal", "analyze portal", "debug portal",
    ],
    "login": [
        "login", "log in", "sign in", "riphah login",
        "login to riphah", "log into portal", "authenticate",
    ],
    "register": [
        "register", "create account", "sign up", "new account",
        "registration", "create portal account",
    ],
    "apply": [
        "apply for admission", "fill application", "submit application",
        "apply now", "fill form", "complete application", "apply",
    ],
    "status": [
        "check status", "application status", "check application",
        "my application", "track application",
    ],
    "help": ["help", "commands", "what can you do", "options", "?"],
}


def _classify(text: str) -> str:
    lower = text.lower().strip()
    for intent, phrases in _INTENTS.items():
        if any(p in lower for p in phrases):
            return intent
    return "unknown"


# ── Prompt helpers ────────────────────────────────────────────────────────────

def _prompt_credentials() -> tuple[str, str]:
    email    = input("  Portal email:    ").strip()
    password = input("  Portal password: ").strip()
    return email, password


def _prompt_applicant_data() -> dict:
    print("\n  ── PERSONAL INFORMATION ───────────────────────────────────────────")
    full_name       = input("  First + Last Name (as on CNIC) *: ").strip()
    middle_name     = input("  Middle Name (optional):           ").strip()
    father_name     = input("  Father's Full Name             *: ").strip()
    cnic            = input("  CNIC / B-Form No (xxxxx-xxxxxxx-x) *: ").strip()
    dob             = input("  Date of Birth (DD/MM/YYYY)     *: ").strip()
    gender          = input("  Gender (Male/Female)           *: ").strip() or "Male"

    print("\n  ── CONTACT INFORMATION ────────────────────────────────────────────")
    email           = input("  Email address                  *: ").strip()
    phone           = input("  Mobile No (e.g. 03001234567)  *: ").strip()
    alternate_phone = input("  Alternate / WhatsApp No        *: ").strip() or phone

    print("\n  ── ADDRESS ────────────────────────────────────────────────────────")
    address         = input("  Current Residential Address    *: ").strip()
    city            = input("  City                           *: ").strip()

    print("\n  ── ACADEMIC INFORMATION ───────────────────────────────────────────")
    last_institute  = input("  College / Last Institute       *: ").strip()
    matric_marks    = input("  Matric / O-Level Marks or %      : ").strip()
    inter_marks     = input("  Intermediate / A-Level Marks or %: ").strip()
    entry_test      = input("  Entry Test Score (MDCAT/ECAT/NAT): ").strip()

    print("\n  ── PROGRAM SELECTION ──────────────────────────────────────────────")
    campus          = input("  Campus (Islamabad/Lahore/Malakand) *: ").strip() or "Islamabad"
    level           = input("  Level (Undergraduate/MS/PhD/Diploma) *: ").strip() or "Undergraduate"
    program         = input("  Program Preference 1           *: ").strip()
    program2        = input("  Program Preference 2 (optional)  : ").strip()
    program3        = input("  Program Preference 3 (optional)  : ").strip()
    program4        = input("  Program Preference 4 (optional)  : ").strip()

    print("\n  ── OTHER ──────────────────────────────────────────────────────────")
    heard_from      = input("  How did you hear about Riphah?\n"
                            "  (Facebook/Instagram/Newspaper/Friend or Family/YouTube/Google/Poster) *: "
                            ).strip() or "Friend or Family"

    return {
        # Identity
        "full_name":       full_name,
        "middle_name":     middle_name,
        "father_name":     father_name,
        "cnic":            cnic,
        "dob":             dob,
        "gender":          gender,
        "nationality":     "Pakistan",
        # Contact
        "email":           email,
        "phone":           phone,
        "alternate_phone": alternate_phone,
        # Address
        "address":         address,
        "city":            city,
        # Academic
        "last_institute":  last_institute,
        "matric_marks":    matric_marks,
        "inter_marks":     inter_marks,
        "entry_test":      entry_test,
        # Program
        "campus":          campus,
        "level":           level,
        "program":         program,
        "program2":        program2,
        "program3":        program3,
        "program4":        program4,
        # Other
        "heard_from":      heard_from,
    }


# ── Action handlers ───────────────────────────────────────────────────────────

def _action_open_portal(config: dict) -> None:
    import webbrowser
    url = config.get("portal", {}).get("url", "https://admissions.riphah.edu.pk/riphah_demo/public/")
    _info(f"Opening {url} in your browser...")
    webbrowser.open(url)
    _ok("Browser launched.")


def _action_diagnose(config: dict) -> None:
    from backend.automation.portal_cli import run_diagnostic
    headless = config.get("portal", {}).get("headless", True)
    _step("Running portal diagnostic (DOM inspection)...")
    run_diagnostic(headless=headless)


def _action_login(config: dict) -> None:
    from playwright.sync_api import sync_playwright
    from backend.automation.portal_cli import LOGIN_URL, SHORT, run_login

    email, password = _prompt_credentials()
    headless = config.get("portal", {}).get("headless", True)

    _step(f"Launching browser (headless={headless})...")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        page    = browser.new_page()
        page.set_default_timeout(SHORT)
        run_login(page, email, password)
        browser.close()


def _action_register(config: dict) -> None:
    from playwright.sync_api import sync_playwright
    from backend.automation.portal_cli import SHORT, run_register

    data     = _prompt_applicant_data()
    password = input("  Set portal password: ").strip()
    headless = config.get("portal", {}).get("headless", True)

    _step(f"Launching browser (headless={headless})...")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        page    = browser.new_page()
        page.set_default_timeout(SHORT)
        run_register(page, data, password)
        browser.close()


def _action_apply(config: dict) -> None:
    from backend.automation.portal_cli import run_full_flow

    email, password = _prompt_credentials()
    data = _prompt_applicant_data()
    data["email"] = data.get("email") or email

    headless     = config.get("portal", {}).get("headless", True)
    screenshots  = config.get("portal", {}).get("screenshots", True)

    _step("Starting full admission automation flow...")
    run_full_flow(
        email=email,
        password=password,
        data=data,
        headless=headless,
        screenshot_dir=None,
    )


def _action_status(config: dict) -> None:
    import webbrowser
    base = config.get("portal", {}).get("url", "https://admissions.riphah.edu.pk/riphah_demo/public/")
    url  = base.rstrip("/") + "/Student/application/List"
    _info(f"Opening application status page: {url}")
    webbrowser.open(url)
    _ok("Browser launched — log in to check your status.")


def _action_help() -> None:
    print("\n" + _c("36;1", "Available commands:"))
    cmds = [
        ("open admissions portal",  "Open the Riphah admissions website in your browser"),
        ("diagnose portal",         "Inspect the portal DOM — lists all form fields"),
        ("login",                   "Log in to the portal with your credentials"),
        ("register",                "Create a new portal account"),
        ("apply for admission",     "Fill and submit the full application form automatically"),
        ("check application status","Open your application list in the browser"),
        ("help",                    "Show this list"),
        ("quit / exit",             "Exit the assistant"),
    ]
    for cmd, desc in cmds:
        print(f"  {_c('33', cmd):40s}  {desc}")
    print()


# ── Main router ───────────────────────────────────────────────────────────────

def route_command(text: str, config: dict) -> None:
    intent = _classify(text)
    _info(f"Command: '{text}'  →  intent: {intent}")

    try:
        if intent == "open_portal":
            _action_open_portal(config)
        elif intent == "diagnose":
            _action_diagnose(config)
        elif intent == "login":
            _action_login(config)
        elif intent == "register":
            _action_register(config)
        elif intent == "apply":
            _action_apply(config)
        elif intent == "status":
            _action_status(config)
        elif intent == "help":
            _action_help()
        else:
            _warn(f"Command not recognised. Type 'help' to see available commands.")
    except KeyboardInterrupt:
        _warn("Action cancelled.")
    except Exception as e:
        _error(f"{type(e).__name__}: {e}")
