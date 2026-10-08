"""
copilot.py — "Ask the CRM": plain-English questions answered ONLY from live data, and drafts that a
person sends.

How it answers (no guessing):
  1. The question is matched to one of a fixed set of read-only data tools (who to call, hot leads,
     pipeline, learning loop, A/B tests, CRM impact, revenue, campaigns, one lead). Keyword rules do
     this; with GEMINI_API_KEY set, Gemini picks the tool when the rules are unsure.
  2. The tool reads the live databases and returns its numbers plus where they came from.
  3. The answer is written from those numbers by a template. With Gemini, Gemini may re-phrase it —
     but if its text contains any number that is not in the tool's output, its text is thrown away and
     the template answer is used. So every number shown comes from the data.
  4. Drafts (an email to a lead, an A/B test plan) are only drafts: nothing is sent. A person opens
     them in the lead page / A/B test page and presses send.
Every question, the tools used and the answer are logged (copilot_log).
"""
import json
import os
import re
from datetime import datetime, timedelta

import gemini

DEMO = "@demo.xeducation.test"

SUGGESTIONS = [
    "Who should we call today?",
    "Which leads are most likely to buy?",
    "How is the pipeline looking?",
    "Is the learning loop fooling itself?",
    "How are the A/B tests doing?",
    "Is the CRM actually making a difference?",
    "How much did we sell in the last 30 days?",
    "Draft an A/B test for a better subject line",
]

TOOLS = {
    "call_list": "Open call tasks chosen by the next-best-action engine, highest expected extra profit first",
    "hot_leads": "Leads most likely to buy (not customers yet)",
    "pipeline": "Leads per lifecycle stage and the expected value of the open pipeline",
    "learning": "The latest learning-loop run and its honest check on the untouched control group",
    "ab_tests": "A/B tests (running and final) and adopted winners",
    "impact": "People the CRM worked on vs the 5% control group it never contacts",
    "revenue": "Purchases, revenue and discounts in a period",
    "campaigns": "Campaigns and their effect vs their random holdout",
    "lead": "One lead: score, reasons, recommended next step, what-if path",
    "draft_email": "Draft an email to one lead (not sent)",
    "draft_ab_test": "Draft an A/B test plan (not created until a person does it)",
    "help": "What I can answer",
}

RULES = [  # (intent, regex) — first match wins; drafts before look-ups
    ("draft_ab_test", r"\b(draft|plan|design|create|set ?up|suggest|propose)\b.*\b(a/?b|ab test|experiment|test)\b|\b(a/?b|ab) test\b.*\b(draft|plan|design|idea)"),
    ("draft_email", r"\b(draft|write|compose|prepare)\b.*\b(e-?mail|mail|message)\b"),
    ("call_list", r"\b(call|calls|phone|ring|dial)\b"),
    ("learning", r"\b(learn|learning|retrain|re-train|fool|honest|model|loop|control group check)\b"),
    ("ab_tests", r"\b(a/?b|ab test|experiment|variant|winner|adopt)\w*"),
    ("impact", r"\b(impact|difference|worth it|working|incremental|lift|without the crm|control group)\b"),
    ("revenue", r"\b(revenue|sales|sold|sell|purchase|purchases|earn|earned|money|income|bought)\b"),
    ("campaigns", r"\bcampaign"),
    ("pipeline", r"\b(pipeline|stage|stages|funnel|board|mql|sql)\b"),
    ("hot_leads", r"\b(hot|best|top|likely|ready|warm|priorit)\w*\b.*\b(lead|leads|people|learners|buy)\b|\bwho (will|is going to|might) buy\b"),
    ("help", r"\b(help|what can you|how do i use)\b"),
]


def _num(x, d=0):
    return f"{x:,.{d}f}" if x is not None else "—"


def _pct(x, d=1):
    return f"{x * 100:.{d}f}%" if x is not None else "—"


def _inr(x):
    return f"₹{x:,.0f}" if x is not None else "—"


def _first(name):
    return (name or "").split()[0] if name else "there"


class Copilot:
    def __init__(self, ctx):
        """ctx: uq/mq (queries), internal(path), crm_impact(), ab_tests(), adoptions(), campaigns(),
        plan(tier, metric, k, control_share, mde), generate_content(...), catalog, settings, tiers."""
        self.c = ctx
        self.uq, self.mq = ctx["uq"], ctx["mq"]

    # ── routing ─────────────────────────────────────────────────────────────
    def route(self, q):
        text = q.lower()
        email = re.search(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", q)
        if email and not re.search(r"\bdraft|write|compose", text):
            return "lead", {"query": email.group(0)}
        for intent, rx in RULES:
            if re.search(rx, text):
                args = {}
                if intent in ("draft_email",):
                    args["query"] = self._name_in(q)
                if intent == "revenue":
                    m = re.search(r"(\d+)\s*(day|days|week|weeks|month|months)", text)
                    days = 30
                    if m:
                        n = int(m.group(1))
                        days = n * (7 if m.group(2).startswith("week") else 30 if m.group(2).startswith("month") else 1)
                    elif "week" in text:
                        days = 7
                    elif "today" in text:
                        days = 1
                    args["days"] = max(1, min(days, 365))
                if intent == "draft_ab_test":
                    args["text"] = text
                return intent, args
        name = self._name_in(q)
        if name:
            return "lead", {"query": name}
        return None, {}

    def _name_in(self, q):
        """A learner's name mentioned in the question ('tell me about Riya Sharma')."""
        m = re.search(r"\b(?:about|for|to|on|is|lead)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", q)
        if not m:
            return None
        cand = m.group(1).strip()
        hit = self.uq("SELECT id FROM users WHERE name LIKE ? LIMIT 1", (f"%{cand}%",))
        return cand if hit else None

    # ── tools ───────────────────────────────────────────────────────────────
    def call_list(self, n=5):
        rows = self.uq("""SELECT t.id, t.user_id, t.lead_id, t.title, t.expected_gain, t.created_at, u.name, u.email,
                                 l.lead_score, up.phone
                          FROM sales_tasks t JOIN users u ON u.id=t.user_id LEFT JOIN leads l ON l.id=t.lead_id
                          LEFT JOIN user_profiles up ON up.user_id=t.user_id
                          WHERE t.status='open' AND t.task_type='call' ORDER BY t.expected_gain DESC""")
        cap = int(self.c["settings"].S.get("daily_call_capacity", 20))
        top = rows[:n]
        facts = {"open_calls": len(rows), "daily_capacity": cap,
                 "top": [{"name": r["name"], "lead_id": r["lead_id"], "score": round(r["lead_score"] or 0),
                          "expected_gain": round(r["expected_gain"] or 0), "simulated": (r["email"] or "").endswith(DEMO)}
                         for r in top]}
        if not rows:
            text = ("There are no open call tasks right now. Calls are created by the next-best-action engine only "
                    "when a call is expected to change the outcome enough to pay for the advisor's time.")
        else:
            lines = [f"{i + 1}. {t['name']} — score {t['score']}, expected extra profit {_inr(t['expected_gain'])}"
                     for i, t in enumerate(facts["top"])]
            text = (f"{len(rows)} open call tasks (the engine may create up to {cap} a day). Start with:\n" + "\n".join(lines))
        return text, facts, "sales_tasks (open calls) + leads", [{"type": "lead", "lead_id": t["lead_id"], "label": t["name"]}
                                                               for t in facts["top"] if t["lead_id"]]

    def hot_leads(self, n=5):
        rows = self.uq("""SELECT l.id AS lead_id, l.user_id, l.lead_score, l.recommended_action, l.course_type, u.name, u.email
                          FROM leads l JOIN users u ON u.id=l.user_id
                          WHERE l.id IN (SELECT MAX(id) FROM leads GROUP BY user_id)
                            AND l.user_id NOT IN (SELECT user_id FROM purchases)
                          ORDER BY l.lead_score DESC LIMIT ?""", (n,))
        facts = {"top": [{"name": r["name"], "lead_id": r["lead_id"], "score": round(r["lead_score"] or 0, 1),
                          "tier": r["recommended_action"], "course": r["course_type"]} for r in rows]}
        if not rows:
            return "No open leads yet.", facts, "leads (latest per person)", []
        lines = [f"{i + 1}. {t['name']} — {t['score']:.0f}% chance to buy within 14 days if we do nothing ({t['tier']}), "
                 f"{t['course'] or 'no course yet'}" for i, t in enumerate(facts["top"])]
        text = "Most likely to buy (not customers yet):\n" + "\n".join(lines)
        return text, facts, "leads (latest score per person, customers excluded)", \
            [{"type": "lead", "lead_id": t["lead_id"], "label": t["name"]} for t in facts["top"]]

    def pipeline(self):
        b = self.c["internal"]("/api/internal/pipeline?limit=1")
        cols = {c["stage"]: c for c in b["columns"]}
        open_value = sum(c["expected_value"] or 0 for s, c in cols.items() if s != "Customer")
        facts = {s: {"people": c["count"], "expected_value": c["expected_value"]} for s, c in cols.items()}
        facts["open_value"] = open_value
        parts = " · ".join(f"{s} {cols[s]['count']:,}" for s in b["stages"])
        text = (f"{parts}.\nOpen pipeline: {_inr(open_value)} expected within 14 days if we do nothing "
                f"(each lead's chance to buy × course price). The SQL column ({_num(cols['SQL']['count'])} people) is where "
                f"calls pay off most.")
        return text, facts, "pipeline board (stages from website behaviour + manual moves)", [{"type": "page", "to": "/pipeline", "label": "Open the pipeline"}]

    def learning(self):
        runs = self.uq("SELECT * FROM learning_runs WHERE status='done' ORDER BY id DESC LIMIT 1")
        if not runs:
            return ("The learning loop has not run yet: it needs at least 30 new known outcomes.", {}, "learning_runs", [])
        r = runs[0]
        lj = json.loads(r.get("learned_json") or "{}")
        ctl = lj.get("control") or {}
        pred = ctl.get("predicted") or {}
        actual = ctl.get("actual")
        facts = {"as_of": (r["as_of"] or "")[:10], "decision": r["lead_decision"], "control_people": ctl.get("people"),
                 "actual": actual, "ours": pred.get("challenger"), "naive": pred.get("naive"),
                 "naive_would_pick": bool(r.get("naive_would_pick")), "outcomes_known": r.get("outcomes_known")}
        decision = {"swapped": "replaced the model", "kept": "kept the current model",
                    "not_enough_data": "waited (not enough control-group data yet)"}.get(r["lead_decision"], r["lead_decision"])
        text = f"Latest run ({facts['as_of']}, {_num(r.get('outcomes_known'))} known outcomes): the loop {decision}."
        if actual is not None and pred.get("naive") is not None and pred.get("challenger") is not None:
            over_n = pred["naive"] / actual - 1 if actual else None
            over_o = pred["challenger"] / actual - 1 if actual else None
            text += (f"\nOn the untouched control group ({ctl.get('people')} people), {_pct(actual)} actually bought. "
                     f"Our retrain expected {_pct(pred['challenger'])}, a naive retrain {_pct(pred['naive'])} "
                     f"(it overstates by {over_n * 100:+.0f}% vs ours {over_o * 100:+.0f}%).")
            text += (" The usual check (fit on the CRM's own data) would have picked the naive model."
                     if facts["naive_would_pick"] else " The usual check would not have picked the naive model this time.")
        return text, facts, "learning_runs (latest) — honest check on the 5% control group", [{"type": "page", "to": "/learning", "label": "Open the learning loop"}]

    def ab_tests(self):
        tests = self.c["ab_tests"]()
        ad = self.c["adoptions"]()
        live = [t for t in tests if t.get("state") in ("running", "completed")]
        facts = {"tests": [{"name": t["name"], "state": t["state"], "verdict": (t.get("verdict") or {}).get("headline")}
                           for t in live[:6]],
                 "adopted": [{"email": a["variant_label"], "audience": a["audience"], "status": a["status"]} for a in ad[:4]]}
        if not live:
            text = "No A/B tests have been sent yet."
        else:
            lines = [f"• {t['name'].replace('(simulated) ', '')}: {(t.get('verdict') or {}).get('headline', t['state'])}" for t in live[:6]]
            text = "A/B tests:\n" + "\n".join(lines)
        if ad:
            text += "\nAdopted winners: " + "; ".join(
                f"'{a['variant_label']}' for {a['audience']} ({a['status']}" +
                (f": {(a.get('check') or {}).get('why')}" if a.get("check") else "") + ")" for a in ad[:3])
        return text, facts, "ab_tests + experiment_assignments + adopted_emails", [{"type": "page", "to": "/ab-tests", "label": "Open A/B tests"}]

    def impact(self):
        i = self.c["crm_impact"]()
        w, c = i["worked_on"], i["control"]
        facts = {"days": i["days"], "worked_on_rate": w["rate"], "worked_on_people": w["people"],
                 "control_rate": c["rate"], "control_people": c["people"], "lift": i.get("lift"), "lift_ci": i.get("lift_ci")}
        if not c["people"] or not w["people"]:
            return ("Not enough people yet: the comparison needs learners who signed up at least "
                    f"{i['days']} days ago in both groups.", facts, "users + purchases + 5% control group", [])
        lo, hi = i.get("lift_ci") or (None, None)
        text = (f"Of people the CRM worked on, {_pct(w['rate'])} bought within {i['days']} days of signing up "
                f"({w['people']:,} people); of the 5% it never contacts, {_pct(c['rate'])} ({c['people']:,} people). "
                f"Difference: {i['lift'] * 100:+.1f} points (95% interval {lo * 100:+.1f} to {hi * 100:+.1f}).")
        text += (" The interval is above zero: the CRM is making a real difference." if lo is not None and lo > 0 else
                 " The interval still includes zero: not proven yet (the control group is small).")
        return text, facts, "users + purchases, split by the fixed 5% control group", []

    def revenue(self, days=30):
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        rows = self.uq("""SELECT p.course_title, p.price_paid, p.discount_amount, u.email FROM purchases p
                          JOIN users u ON u.id=p.user_id WHERE p.purchased_at >= ?""", (since,))
        n = len(rows)
        rev = sum(r["price_paid"] or 0 for r in rows)
        disc = sum(r["discount_amount"] or 0 for r in rows)
        sim = sum(1 for r in rows if (r["email"] or "").endswith(DEMO))
        by = {}
        for r in rows:
            by[r["course_title"]] = by.get(r["course_title"], 0) + 1
        top = sorted(by.items(), key=lambda x: -x[1])[:3]
        facts = {"days": days, "purchases": n, "revenue": round(rev), "discounts": round(disc), "simulated": sim,
                 "top_courses": top}
        if not n:
            return f"No purchases in the last {days} days.", facts, "purchases", []
        text = (f"Last {days} days: {n:,} purchases, {_inr(rev)} revenue after {_inr(disc)} of discounts.")
        if top:
            text += " Top courses: " + ", ".join(f"{t} ({k})" for t, k in top) + "."
        if sim:
            text += f" ({sim:,} of these are simulated learners.)"
        return text, facts, "purchases", []

    def campaigns(self):
        cs = self.c["campaigns"]()
        sent = [c for c in cs if c.get("sent")][:4]
        facts = {"campaigns": [{"name": c["name"], "delivered": c.get("delivered"), "conversions": c.get("conversions"),
                                "lift": (c.get("incremental") or {}).get("lift")} for c in sent]}
        if not sent:
            return "No campaigns have been sent yet.", facts, "campaign_schedules + email_sends", []
        lines = []
        for c in sent:
            inc = c.get("incremental")
            line = f"• {c['name'].replace('(simulated) ', '')}: {c.get('delivered', 0):,} emails, {c.get('conversions', 0):,} bought"
            if inc and inc.get("lift") is not None:
                lo, hi = inc["ci"]
                line += f"; vs its holdout {inc['lift'] * 100:+.1f} points (95% interval {lo * 100:+.1f} to {hi * 100:+.1f})"
            lines.append(line)
        return "Recent campaigns:\n" + "\n".join(lines), facts, "campaign_schedules + email_sends + holdouts", \
            [{"type": "page", "to": "/campaigns", "label": "Open campaigns"}]

    def _find_lead(self, query):
        if not query:
            return None
        rows = self.uq("""SELECT l.*, u.name, u.email FROM leads l JOIN users u ON u.id=l.user_id
                          WHERE (u.email = ? OR u.name LIKE ?) AND l.id IN (SELECT MAX(id) FROM leads GROUP BY user_id)
                          ORDER BY l.id DESC LIMIT 1""", (query, f"%{query}%"))
        return rows[0] if rows else None

    def lead(self, query):
        r = self._find_lead(query)
        if not r:
            return f"I could not find a lead matching '{query}'.", {}, "users + leads", []
        factors = json.loads(r.get("score_factors") or "[]")[:3]
        nba = json.loads(r.get("nba_json") or "null") or {}
        facts = {"name": r["name"], "score": round(r["lead_score"] or 0, 1), "tier": r["recommended_action"],
                 "reasons": [f"{f['factor']} {f['impact']}" for f in factors], "next_step": nba.get("label")}
        text = (f"{r['name']}: {facts['score']:.0f}% chance to buy within 14 days if we do nothing — {r['recommended_action']}.")
        if factors:
            text += " Main reasons: " + "; ".join(f"{f['factor'].lower()} ({f['impact']})" for f in factors) + "."
        if nba.get("label"):
            text += f" Last decision: {nba['label'].lower()}" + (f" — {nba['why']}" if nba.get("why") else "") + "."
        try:
            p = self.c["internal"](f"/api/internal/paths/{r['user_id']}?depth=2")
            if p.get("summary"):
                text += f"\nWhat-if: {p['summary']}"
                facts["what_if"] = p["summary"]
        except Exception:
            pass
        return text, facts, "leads + nba_decisions + what-if paths", [{"type": "lead", "lead_id": r["id"], "label": f"Open {r['name']}"}]

    def draft_email(self, query):
        r = self._find_lead(query) if query else None
        if not r:
            return ("Tell me who the email is for, e.g. 'Draft an email to Riya Sharma' (I write drafts only; "
                    "you send them from the lead page).", {}, "users + leads", [])
        slug = r.get("course_slug")
        title = self.c["catalog"].title_of(slug, "our programmes") if slug else "our programmes"
        prof = (self.uq("SELECT current_occupation, specialization FROM user_profiles WHERE user_id=?", (r["user_id"],)) or [{}])[0]
        content = self.c["generate_content"](
            name=r["name"], occupation=prof.get("current_occupation"), specialization=prof.get("specialization"),
            course=title, action=r["recommended_action"], trigger="manual_edit", past_purchases=0,
            lead_score=r["lead_score"], course_slug=slug, offer_pct=0)
        draft = {"type": "email", "lead_id": r["id"], "to": r["name"], "subject": content["email_subject"],
                 "body": content["email_body"]}
        text = (f"Here is a draft for {r['name']} about {title}, written from the course facts (no discount — whether "
                f"to offer one is the next-best-action engine's call). Nothing has been sent: open the lead to edit and send it.")
        return text, {"lead": r["name"], "course": title}, "leads + user_profiles + course catalogue", [draft]

    def draft_ab_test(self, text=""):
        t = text or ""
        if re.search(r"subject|open|click", t):
            spec = ("Subject line: benefit vs urgency", "click",
                    "An urgency subject line gets more people to click than a benefit-led one.",
                    [("Benefit-led subject", "{first_name}, your next career step: {course}",
                      "Hi {first_name},\n\nSee how {course} fits your goals: curriculum, instructor and outcomes."),
                     ("Urgency subject", "Last seats in the {course} batch",
                      "Hi {first_name},\n\nThe next {course} batch is filling up. Reserve your seat this week.")])
        elif re.search(r"discount|coupon|offer|price", t):
            spec = ("EMI message vs refund guarantee", "purchase",
                    "Removing a doubt (refund guarantee) converts more than talking about price (EMI).",
                    [("EMI from ₹2,200/month", "{course} from ₹2,200 a month",
                      "Hi {first_name},\n\nSpread the fee of {course} over easy monthly EMIs."),
                     ("7-day refund guarantee", "Try {course} risk-free for 7 days",
                      "Hi {first_name},\n\nStart {course}; if it isn't for you, get a full refund within 7 days.")])
        elif re.search(r"mobile|short|long|length", t):
            spec = ("Short mobile email vs long email", "purchase", "A short email works better on phones.",
                    [("Long email", "Everything about {course} in one email",
                      "Hi {first_name},\n\nModules, projects, instructor, fees, EMI and outcomes of {course} in detail."),
                     ("Short mobile-first email", "{course} in 30 seconds", "Hi {first_name},\n\n{course}: 3 reasons, 1 link.")])
        else:
            spec = ("Personalised course pick vs generic newsletter", "purchase",
                    "A course picked for the learner's background converts better than a generic newsletter.",
                    [("Generic newsletter", "This month at X Education",
                      "Hi {first_name},\n\nNews, new batches and learner stories from X Education."),
                     ("Personalised course pick", "{first_name}, {course} fits your background",
                      "Hi {first_name},\n\nBased on what you looked at, {course} is the best next step for you.")])
        name, metric, hyp, variants = spec
        ab = self.c["settings"].S["ab_testing"]
        control = float(ab["control_share"]) if metric == "purchase" else 0.0
        plan = self.c["plan"]("All leads", metric, len(variants), control, float(ab["min_detectable_effect"]))
        draft = {"type": "ab_test", "name": name, "tier": "All leads", "metric": metric, "hypothesis": hyp,
                 "control_share": control, "mde": float(ab["min_detectable_effect"]),
                 "variants": [{"label": l, "subject": s, "body": b, "offer_pct": 0} for l, s, b in variants]}
        facts = {"audience": plan["audience"], "planned_per_arm": plan["planned_per_arm"],
                 "per_arm_available": plan["per_arm_available"], "enough": plan["enough"]}
        text = (f"Draft test: '{name}' ({'clicks' if metric == 'click' else 'purchases'} within 14 days"
                + (f", {control * 100:.0f}% no-email control group" if control else "") + f"). Hypothesis: {hyp}\n"
                f"Plan: {plan['planned_per_arm']:,} people per arm are needed to see a "
                f"{float(ab['min_detectable_effect']) * 100:.0f}-point lift; the audience gives {plan['per_arm_available']:,} per arm"
                + (" — enough." if plan["enough"] else " — not enough, so only bigger effects could be detected.")
                + " Nothing is created yet: open it in A/B tests, review, then create and send.")
        return text, facts, "A/B planner (sample size) + campaign audience", [draft]

    def help(self):
        text = "I answer from the CRM's live data, and I only draft — a person sends. Try:\n" + \
               "\n".join(f"• {s}" for s in SUGGESTIONS) + "\n• Tell me about <a learner's name or email>"
        return text, {}, "—", []

    # ── answering ───────────────────────────────────────────────────────────
    def ask(self, question):
        q = (question or "").strip()[:500]
        intent, args = self.route(q)
        used_gemini = False
        if intent is None and gemini.enabled():
            intent, args, used_gemini = self._gemini_route(q)
        if intent is None:
            intent, args = "help", {}
        fn = getattr(self, intent)
        try:
            text, facts, source, extras = fn(**args)
        except Exception as e:                       # a tool failing must not break the page
            text, facts, source, extras = (f"I could not read that data just now ({e.__class__.__name__}).", {}, intent, [])
        answer = text
        if gemini.enabled() and intent not in ("help", "draft_email", "draft_ab_test"):
            better = self._gemini_phrase(q, text)
            if better:
                answer, used_gemini = better, True
        drafts = [x for x in extras if x.get("type") in ("email", "ab_test")]
        links = [x for x in extras if x.get("type") in ("lead", "page")]
        out = {"question": q, "intent": intent, "answer": answer,
               "tools": [{"name": intent, "about": TOOLS.get(intent), "source": source,
                          "read_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "data": facts}],
               "drafts": drafts, "links": links, "used_gemini": used_gemini, "suggestions": SUGGESTIONS}
        try:
            self.c["log"](q, intent, json.dumps(out["tools"], default=str), answer, json.dumps(drafts, default=str), used_gemini)
        except Exception:
            pass
        return out

    # ── optional Gemini (never the source of a number) ──────────────────────────
    def _gemini_route(self, q):
        try:
            prompt = ("You route a CRM user's question to ONE tool. Tools:\n" +
                      "\n".join(f"- {k}: {v}" for k, v in TOOLS.items()) +
                      '\nReply with JSON only, e.g. {"tool": "hot_leads", "query": ""}. "query" is a learner name or '
                      f"email for the lead / draft_email tools, else empty.\nQuestion: {q}")
            raw = gemini.generate(prompt)
            m = re.search(r"\{.*\}", raw, re.S)
            d = json.loads(m.group(0)) if m else {}
            tool = d.get("tool")
            if tool not in TOOLS:
                return None, {}, True
            args = {"query": d.get("query") or None} if tool in ("lead", "draft_email") else {}
            if tool == "draft_ab_test":
                args = {"text": q.lower()}
            return tool, args, True
        except Exception as e:
            print(f"[COPILOT] Gemini routing failed: {e}")
            return None, {}, False

    def _gemini_phrase(self, q, text):
        try:
            prompt = ("Rewrite this answer to the user's question so it reads naturally and briefly. Use ONLY the "
                      "facts and numbers in the answer; do not add, round or change any number, and do not add "
                      f"advice.\nQuestion: {q}\nAnswer: {text}")
            out = (gemini.generate(prompt) or "").strip()
            nums = lambda s: {n.replace(",", "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", s)}
            if out and nums(out) <= nums(text):
                return out
            print("[COPILOT] Gemini's wording changed a number — using the template answer.")
        except Exception as e:
            print(f"[COPILOT] Gemini phrasing failed: {e}")
        return None
