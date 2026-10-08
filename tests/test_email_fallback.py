"""
A live demo must not stop because Gmail or the internet is slow or down (no servers needed, works on a
copy of the database, never sends a real email):

    user-backend\\venv\\Scripts\\python.exe tests\\test_email_fallback.py

  1. a network error is reported within the timeout and pauses e-mail for 5 minutes (no 10-second wait
     per e-mail after that); a refused address or a wrong password does NOT pause the others
  2. sign-up in DEMO_MODE goes on when the code cannot be e-mailed (the code is printed in the
     user-backend window); outside demo mode it is refused and the half-made account removed
  3. checkout replies first and sends the confirmation e-mail afterwards
"""
import os
import smtplib
import sqlite3
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "user-backend")
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)
RESULTS = []


def check(name, fn):
    try:
        info = fn()
        RESULTS.append(True)
        print(f"PASS  {name}  {info or ''}", flush=True)
    except Exception as e:
        RESULTS.append(False)
        print(f"FAIL  {name}  {type(e).__name__}: {e}", flush=True)


class FakeSMTP:
    """Stands in for smtplib.SMTP_SSL: raises what the test asks for, records what was 'sent'."""
    mode, sent, timeouts = None, [], []

    def __init__(self, host, port, timeout=None):
        FakeSMTP.timeouts.append(timeout)
        if FakeSMTP.mode == "network":
            raise OSError("Network is unreachable")
        if FakeSMTP.mode == "timeout":
            raise TimeoutError("timed out")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, user, pw):
        if FakeSMTP.mode == "auth":
            raise smtplib.SMTPAuthenticationError(535, b"bad credentials")

    def sendmail(self, frm, to, msg):
        if FakeSMTP.mode == "refused":
            raise smtplib.SMTPRecipientsRefused({to: (550, b"no such user")})
        FakeSMTP.sent.append(to)


def main():
    src = os.path.join(BACKEND, "xeducation_user.db")
    tmp = tempfile.mkdtemp(prefix="xedu-mail-")
    copy = os.path.join(tmp, "db.sqlite")
    if os.path.exists(src):
        con = sqlite3.connect(src)
        con.execute(f"VACUUM INTO '{copy}'")
        con.close()
    import database as db
    db.DB_PATH = copy
    db.init_db()
    import email_service as E
    E.GMAIL_USER, E.GMAIL_PASS = "test@example.com", "app-password"     # pretend Gmail is configured
    smtplib.SMTP_SSL = FakeSMTP

    def reset(mode):
        FakeSMTP.mode, FakeSMTP.sent = mode, []
        E._paused_until["t"] = 0.0

    def timeout_set():
        reset(None)
        ok, _ = E._send("a@example.com", "s", "b")
        assert ok and FakeSMTP.timeouts[-1] == E.SMTP_TIMEOUT_SECONDS, FakeSMTP.timeouts
        return f"connects with a {E.SMTP_TIMEOUT_SECONDS}-second limit"
    check("Gmail is called with a time limit", timeout_set)

    def network_pause():
        reset("network")
        ok, msg = E._send("a@example.com", "s", "b")
        assert not ok and E._paused_until["t"] > time.time() + 200, (ok, msg)
        FakeSMTP.mode = None
        n = len(FakeSMTP.timeouts)
        ok2, msg2 = E._send("b@example.com", "s", "b")
        assert not ok2 and "paused" in msg2.lower() and len(FakeSMTP.timeouts) == n, "tried Gmail again while paused"
        return "first error pauses e-mail for 5 minutes; the next e-mail does not wait"
    check("no internet: one quick failure, then a pause", network_pause)

    def timeout_pause():
        reset("timeout")
        ok, _ = E._send("a@example.com", "s", "b")
        assert not ok and E._paused_until["t"] > time.time()
        return "a timeout counts as a network error"
    check("a timeout pauses e-mail too", timeout_pause)

    def no_pause_for_one_address():
        reset("refused")
        ok, _ = E._send("nobody@example.com", "s", "b")
        assert not ok and E._paused_until["t"] == 0.0, "one bad address paused all e-mail"
        reset("auth")
        ok, msg = E._send("a@example.com", "s", "b")
        assert not ok and "password" in msg.lower() and E._paused_until["t"] == 0.0
        return "a refused address or a wrong app password is reported, others still go out"
    check("a refused address or wrong password does not pause the rest", no_pause_for_one_address)

    def simulated_never_sent():
        reset(None)
        ok, msg = E._send("x@demo.xeducation.test", "s", "b")
        assert ok and not FakeSMTP.sent, "a simulated learner was e-mailed"
        return "…@demo.xeducation.test is never e-mailed"
    check("simulated learners are never e-mailed", simulated_never_sent)

    # sign-up with Gmail down
    import main as M
    import settings

    def signup(demo):
        reset("network")
        settings.DEMO_MODE = demo
        email = f"mailtest-{int(time.time() * 1000)}@example.com"
        try:
            r = M.signup(M.SignupRequest(name="Mail Test", email=email, password="secret-1"))
            return email, r, None
        except M.HTTPException as e:
            return email, None, e

    def demo_signup():
        email, r, err = signup(True)
        assert err is None and "window" in r["message"], (r, err)
        assert db.get_user_by_email(email), "the account was not kept"
        otp = db.fetchone("SELECT otp FROM otp_tokens WHERE email=? ORDER BY id DESC LIMIT 1", (email,))
        assert otp, "no code saved"
        return "sign-up goes on; the code is printed in the user-backend window"
    check("DEMO_MODE: sign-up works while Gmail is down", demo_signup)

    def live_signup():
        email, r, err = signup(False)
        assert err is not None and err.status_code == 500, (r, err)
        assert not db.get_user_by_email(email), "the half-made account was left behind"
        settings.DEMO_MODE = True
        return "refused with a clear error; nothing left behind"
    check("live mode: sign-up is refused cleanly while Gmail is down", live_signup)

    def checkout_reply_first():
        import inspect
        src_code = inspect.getsource(M.checkout)
        assert "background.add_task(send_purchase_confirmation_email" in src_code
        return "the confirmation e-mail is a background task, sent after the reply"
    check("checkout does not wait for Gmail", checkout_reply_first)

    ok = sum(RESULTS)
    print(f"\n{ok} of {len(RESULTS)} checks passed.")
    return 0 if ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
