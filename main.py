import os
import json
import re
from dotenv import load_dotenv
import anthropic

from agents.qualifier import build_qualifier_system
from agents.interviewer import build_interview_system
from agents.analyzer import build_analyzer_system
from agents.redteam import build_redteam_system
from agents.drafter import build_drafter_system

load_dotenv()

MODEL = "claude-opus-4-7"


def load_nis2_requirements() -> list:
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, "data", "frameworks", "nis2.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)["requirements"]


def extract_json(text: str) -> dict:
    stripped = text.strip()

    # Method 1: find first { and last }, parse between them
    start = stripped.find('{')
    end = stripped.rfind('}')
    if start != -1 and end > start:
        try:
            return json.loads(stripped[start:end + 1])
        except json.JSONDecodeError:
            pass

    # Method 2: strip markdown fences, then parse
    no_fences = re.sub(r'```(?:json)?\s*', '', stripped)
    no_fences = re.sub(r'\s*```', '', no_fences).strip()
    start = no_fences.find('{')
    end = no_fences.rfind('}')
    if start != -1 and end > start:
        try:
            return json.loads(no_fences[start:end + 1])
        except json.JSONDecodeError:
            pass

    # Method 3: regex to find JSON object pattern
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError("Could not extract JSON from model response")


def parse_after_json(text: str) -> tuple[dict | None, str]:
    """Return (parsed_dict, text_after_json_block). Used for redteam output."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            obj = json.loads(match.group())
            rest = text[match.end():].strip()
            return obj, rest
        except json.JSONDecodeError:
            pass
    return None, ""


def _chat(client: anthropic.Anthropic, system: str, messages: list, max_tokens: int = 1024) -> str:
    """Single API call, returns assistant text."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    )
    return response.content[0].text


def _get_input(prompt: str = "You: ") -> str:
    """Read a line from stdin, raise SystemExit on Ctrl-C / EOF."""
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print("\n\nExiting. Goodbye!")
        raise SystemExit(0)


def _section(title: str) -> None:
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# STAGE 1 — QUALIFIER
# ---------------------------------------------------------------------------

def run_qualifier(client: anthropic.Anthropic) -> dict:
    _section("REGULA — NIS2 Compliance Assessment")
    print("Type your answers below. Press Ctrl+C to exit.\n")

    seed = "Hello, I'd like to find out if NIS2 applies to my company."
    messages = [{"role": "user", "content": seed}]

    qualifier_system = build_qualifier_system("en")
    text = _chat(client, qualifier_system, messages)
    messages.append({"role": "assistant", "content": text})
    print(f"Regula: {text}\n")

    try:
        result = extract_json(text)
        if "applies" in result:
            return result
    except ValueError:
        pass

    while True:
        user_input = _get_input("You: ")
        if not user_input:
            continue

        messages.append({"role": "user", "content": user_input})
        text = _chat(client, qualifier_system, messages)
        messages.append({"role": "assistant", "content": text})

        try:
            result = extract_json(text)
            if "applies" in result:
                return result
        except ValueError:
            pass

        print(f"\nRegula: {text}\n")


# ---------------------------------------------------------------------------
# STAGE 2 — INTERVIEWER
# ---------------------------------------------------------------------------

COMPLETE_MARKER = "[INTERVIEW_COMPLETE]"


def run_interviewer(client: anthropic.Anthropic, qualifier_result: dict, requirements: list) -> dict:
    _section("REGULA — Compliance Interview")
    print("Answer each question in your own words. Press Ctrl+C to exit.\n")

    question_count = 0
    messages = [{"role": "user", "content": "Hi, I'm ready for the interview."}]

    system = build_interview_system(qualifier_result, requirements, question_count)
    text = _chat(client, system, messages, max_tokens=2048)
    messages.append({"role": "assistant", "content": text})

    if COMPLETE_MARKER in text:
        idx = text.find(COMPLETE_MARKER)
        try:
            return extract_json(text[idx + len(COMPLETE_MARKER):].strip())
        except ValueError:
            pass

    question_count += 1
    print(f"[Q{question_count}] Regula: {text}\n")

    while True:
        user_input = _get_input("You: ")
        if not user_input:
            continue

        messages.append({"role": "user", "content": user_input})
        system = build_interview_system(qualifier_result, requirements, question_count)

        try:
            text = _chat(client, system, messages, max_tokens=2048)
        except anthropic.APIError as e:
            print(f"\nAPI error: {e}")
            raise SystemExit(1)

        messages.append({"role": "assistant", "content": text})

        if COMPLETE_MARKER in text:
            idx = text.find(COMPLETE_MARKER)
            closing = text[:idx].strip()
            if closing:
                print(f"\nRegula: {closing}\n")
            try:
                return extract_json(text[idx + len(COMPLETE_MARKER):].strip())
            except ValueError:
                print("\nRegula: (parsing issue, continuing...)\n")
                continue

        question_count += 1
        print(f"\n[Q{question_count}] Regula: {text}\n")


# ---------------------------------------------------------------------------
# STAGE 3 — ANALYZER (automatic)
# ---------------------------------------------------------------------------

def run_analyzer(
    client: anthropic.Anthropic,
    interview_result: dict,
    requirements: list,
    language: str,
) -> dict:
    _section("REGULA — Running Gap Analysis...")
    print("Analyzing your findings — this takes a moment.\n")

    system = build_analyzer_system(interview_result, requirements, language)
    messages = [{"role": "user", "content": "Please analyze these interview findings and produce the complete gap analysis."}]

    try:
        text = _chat(client, system, messages, max_tokens=4096)
    except anthropic.APIError as e:
        print(f"\nAPI error during analysis: {e}")
        raise SystemExit(1)

    try:
        return extract_json(text)
    except ValueError:
        print("Warning: Could not parse analyzer output.")
        print(text)
        raise SystemExit(1)


def print_gap_analysis(gap_analysis: dict) -> None:
    _section("GAP ANALYSIS RESULTS")

    overall = gap_analysis.get("overall_risk", "unknown").upper()
    headline = gap_analysis.get("headline", "")
    print(f"Overall risk: {overall}")
    print(f"Headline:     {headline}\n")

    gaps = gap_analysis.get("gaps", [])
    if gaps:
        print(f"Gaps found: {len(gaps)}\n")
        for g in gaps:
            level = g.get("risk_level", "").upper()
            status = g.get("status", "").upper()
            print(f"  [{level}] #{g.get('id')} {g.get('requirement')} ({status})")
            print(f"    Found:   {g.get('what_we_found', '')}")
            print(f"    Impact:  {g.get('why_it_matters', '')}")
            print(f"    Action:  {g.get('what_to_do', '')}")
            print(f"    Effort:  {g.get('estimated_effort', '')} | Cost: {g.get('estimated_cost', '')}")
            print()

    priority = gap_analysis.get("priority_3", [])
    if priority:
        print("Top 3 priority actions:")
        for i, action in enumerate(priority, 1):
            print(f"  {i}. {action}")
        print()

    good_news = gap_analysis.get("good_news", "")
    if good_news:
        print(f"What's working: {good_news}\n")

    board = gap_analysis.get("board_summary", "")
    if board:
        print(f"Board summary:\n  {board}\n")


# ---------------------------------------------------------------------------
# STAGE 4 — RED TEAM (interactive)
# ---------------------------------------------------------------------------

def run_redteam(
    client: anthropic.Anthropic,
    gap_analysis: dict,
    qualifier_result: dict,
    language: str,
) -> tuple[dict, str]:
    _section("RED TEAM — Simulated NIS2 Audit Inspection")
    print("Now let's simulate what happens when an auditor arrives at your door.")
    print("Answer as honestly as you would in a real inspection.\n")
    print("-" * 60 + "\n")

    system = build_redteam_system(gap_analysis, qualifier_result, language)
    messages = [{"role": "user", "content": "I'm ready for the inspection."}]

    text = _chat(client, system, messages, max_tokens=2048)
    messages.append({"role": "assistant", "content": text})

    obj, rest = parse_after_json(text)
    if obj and "verdict" in obj:
        return obj, rest

    print(f"Auditor: {text}\n")
    q_num = 1

    while True:
        user_input = _get_input("You: ")
        if not user_input:
            continue

        messages.append({"role": "user", "content": user_input})

        try:
            text = _chat(client, system, messages, max_tokens=4096)
        except anthropic.APIError as e:
            print(f"\nAPI error: {e}")
            raise SystemExit(1)

        messages.append({"role": "assistant", "content": text})

        obj, rest = parse_after_json(text)
        if obj and "verdict" in obj:
            pre_json = text[:text.find("{")].strip()
            if pre_json:
                print(f"\nAuditor: {pre_json}\n")
            return obj, rest

        q_num += 1
        print(f"\nAuditor [{q_num}]: {text}\n")


def print_redteam_result(verdict: dict, preparation: str) -> None:
    _section("AUDIT VERDICT")

    v = verdict.get("verdict", "UNKNOWN")
    print(f"Verdict: {v}\n")

    critical = verdict.get("critical_failures", [])
    if critical:
        print("Critical failures (would trigger immediate penalties):")
        for f in critical:
            print(f"  • {f}")
        print()

    conditional = verdict.get("conditional_passes", [])
    if conditional:
        print("Conditional passes (need documentation/improvement):")
        for c in conditional:
            print(f"  • {c}")
        print()

    summary = verdict.get("auditor_summary", "")
    if summary:
        print(f"Auditor summary:\n  {summary}\n")

    if preparation:
        print("-" * 60)
        print(preparation)
        print()


# ---------------------------------------------------------------------------
# STAGE 5 — DRAFTER (automatic)
# ---------------------------------------------------------------------------

def run_drafter(
    client: anthropic.Anthropic,
    gap_analysis: dict,
    qualifier_result: dict,
    language: str,
) -> dict:
    _section("REGULA — Drafting Policy Outlines...")
    print("Writing plain-language policy drafts for your top gaps.\n")

    system = build_drafter_system(gap_analysis, qualifier_result, language)
    messages = [{"role": "user", "content": "Please generate the policy outlines for the critical and high risk gaps."}]

    try:
        text = _chat(client, system, messages, max_tokens=4096)
    except anthropic.APIError as e:
        print(f"\nAPI error during drafting: {e}")
        raise SystemExit(1)

    try:
        return extract_json(text)
    except ValueError:
        print("Warning: Could not parse drafter output.")
        print(text)
        raise SystemExit(1)


def print_drafter_result(drafter_result: dict) -> None:
    _section("POLICY DRAFTS")

    policies = drafter_result.get("policies", [])
    if not policies:
        print("No policies generated.\n")
        return

    print(f"{len(policies)} policy draft(s) generated:\n")

    for i, p in enumerate(policies, 1):
        print(f"{'─' * 60}")
        print(f"Policy {i}: {p.get('title', '')}")
        print(f"Req #{p.get('requirement_id', '?')} | Owner: {p.get('who_owns_this', '')} | Review: {p.get('review_date', 'annually')}")
        print(f"\nWhy we have this:\n  {p.get('why_we_have_this', '')}\n")
        rules = p.get("rules", [])
        if rules:
            print("Rules:")
            for rule in rules:
                print(f"  • {rule}")
        disclaimer = p.get("disclaimer", "")
        if disclaimer:
            print(f"\n  ⚠  {disclaimer}")
        print()


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not found in .env file.")
        raise SystemExit(1)

    client = anthropic.Anthropic(api_key=api_key)

    try:
        requirements = load_nis2_requirements()
    except FileNotFoundError:
        print("Error: data/frameworks/nis2.json not found.")
        raise SystemExit(1)

    # ── Stage 1: Qualifier ──────────────────────────────────────────────────
    try:
        qualifier_result = run_qualifier(client)
    except SystemExit:
        raise
    except Exception as e:
        print(f"\nUnexpected error in qualifier: {e}")
        raise SystemExit(1)

    _section("QUALIFIER RESULT")
    print(json.dumps(qualifier_result, indent=2, ensure_ascii=False))

    if not qualifier_result.get("applies", False):
        print("\nNIS2 does NOT appear to apply to your company.")
        print(f"Reason: {qualifier_result.get('reasoning', '')}")
        print("\nDisclaimer: This is a preliminary assessment only — consult a legal advisor.")
        return

    print(f"\nNIS2 APPLIES — {qualifier_result.get('scope', 'unknown')} entity.")
    print(f"Reason: {qualifier_result.get('reasoning', '')}\n")

    # ── Stage 2: Interviewer ────────────────────────────────────────────────
    try:
        interview_result = run_interviewer(client, qualifier_result, requirements)
    except SystemExit:
        raise
    except Exception as e:
        print(f"\nUnexpected error in interviewer: {e}")
        raise SystemExit(1)

    _section("INTERVIEW FINDINGS")
    print(json.dumps(interview_result, indent=2, ensure_ascii=False))

    language = interview_result.get("language", "en")

    # ── Stage 3: Analyzer (automatic) ──────────────────────────────────────
    try:
        gap_analysis = run_analyzer(client, interview_result, requirements, language)
    except SystemExit:
        raise
    except Exception as e:
        print(f"\nUnexpected error in analyzer: {e}")
        raise SystemExit(1)

    _section("GAP ANALYSIS (raw JSON)")
    print(json.dumps(gap_analysis, indent=2, ensure_ascii=False))
    print_gap_analysis(gap_analysis)

    # ── Stage 4: Red Team (interactive) ────────────────────────────────────
    try:
        verdict, preparation = run_redteam(client, gap_analysis, qualifier_result, language)
    except SystemExit:
        raise
    except Exception as e:
        print(f"\nUnexpected error in red team: {e}")
        raise SystemExit(1)

    _section("RED TEAM VERDICT (raw JSON)")
    print(json.dumps(verdict, indent=2, ensure_ascii=False))
    print_redteam_result(verdict, preparation)

    # ── Stage 5: Drafter (automatic) ───────────────────────────────────────
    try:
        drafter_result = run_drafter(client, gap_analysis, qualifier_result, language)
    except SystemExit:
        raise
    except Exception as e:
        print(f"\nUnexpected error in drafter: {e}")
        raise SystemExit(1)

    _section("POLICY DRAFTS (raw JSON)")
    print(json.dumps(drafter_result, indent=2, ensure_ascii=False))
    print_drafter_result(drafter_result)

    print("=" * 60)
    print("  Your compliance report is ready.")
    print()
    print("  Disclaimer: Draft starting point for legal review —")
    print("  not a final compliance document.")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
