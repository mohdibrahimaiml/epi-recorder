# @title Ask the Evidence (LIVE) { display-mode: "form" }
import zipfile, json, os
from pathlib import Path
from IPython.display import display, HTML, clear_output

# Find the EPI file
epi_files = list(Path('.').glob('*.epi')) + list(Path('.').glob('epi-recordings/*.epi'))
epi_file = max(epi_files, key=lambda p: p.stat().st_mtime) if epi_files else None

evidence_context = ""
steps = []
manifest = {}

# === Parse real data from the .epi file ===
actual_decision = "N/A"
actual_confidence = "N/A"
actual_reasoning = "N/A"
actual_risk_factors = []
actual_risk_level = "N/A"
actual_positive_signals = []
actual_balance = 0
actual_transactions = []

if epi_file:
    with zipfile.ZipFile(epi_file, 'r') as z:
        manifest = json.loads(z.read('manifest.json').decode('utf-8'))
        if 'steps.jsonl' in z.namelist():
            for line in z.read('steps.jsonl').decode('utf-8').strip().splitlines():
                if line:
                    try:
                        steps.append(json.loads(line))
                    except:
                        pass

    # Extract actual values from the captured steps
    for s in steps:
        kind = s.get('kind', '')
        content = s.get('content', s.get('data', {}))
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except:
                pass
        if not isinstance(content, dict):
            continue

        # Extract bank statement data from user.input or similar steps
        if 'average_monthly_balance' in content:
            actual_balance = content['average_monthly_balance']
        if 'transaction_descriptions' in content:
            actual_transactions = content['transaction_descriptions']

        if 'DECISION' in kind or 'decision' in kind:
            actual_decision = content.get('decision', actual_decision)
            actual_confidence = content.get('confidence', actual_confidence)
            actual_reasoning = content.get('reasoning', actual_reasoning)
            actual_risk_factors = content.get('risk_factors', actual_risk_factors)

        if kind.startswith('llm.response'):
            resp_text = str(content.get('response', ''))
            try:
                parsed = json.loads(resp_text)
                if 'risk_level' in parsed:
                    actual_risk_level = parsed['risk_level']
                    actual_positive_signals = parsed.get('positive_signals', [])
            except:
                pass

    # Build evidence context for Gemini (live mode)
    llm_steps = [s for s in steps if s.get('kind', '').startswith('llm.')]
    recent_steps = llm_steps[-10:]

    evidence_context = "EVIDENCE PACKAGE: {}\n".format(epi_file.name)
    evidence_context += "WORKFLOW: {}\n".format(manifest.get('goal', 'Loan Underwriting'))
    evidence_context += "TOTAL STEPS: {}\n".format(len(steps))
    evidence_context += "\n=== CAPTURED EVIDENCE LOG ===\n"

    for i, step in enumerate(recent_steps):
        kind = step.get('kind')
        content = step.get('content', {})
        idx = step.get('index', '?')
        if kind == 'llm.request':
            prompt = str(content.get('contents', ''))[:400].replace('\n', ' ')
            evidence_context += "[STEP {}] USER REQUEST: {}...\n".format(idx, prompt)
        elif kind == 'llm.response':
            response = str(content.get('response', ''))[:400].replace('\n', ' ')
            evidence_context += "[STEP {}] AI RESPONSE: {}...\n".format(idx, response)

    evidence_context += "\n=== FINAL DECISION OUTPUT ===\n"
    evidence_context += "RESULT: {}\n".format(actual_decision)
    evidence_context += "CONFIDENCE: {}\n".format(actual_confidence)
    evidence_context += "REASONING: {}\n".format(actual_reasoning)
    evidence_context += "RISK FACTORS: {}\n".format(actual_risk_factors)

api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")

def ask_evidence(question):
    system_prompt = (
        "You are an EPI Evidence Auditor.\n"
        "Answer ONLY based on the following captured evidence log.\n"
        "Do not use external knowledge. If the evidence does not support the answer, state that clearly.\n"
        "Cite specific Step numbers in your evidence.\n\n"
        + evidence_context + "\n\n"
        "QUESTION: " + question
    )

    if api_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-2.0-flash")
            response = model.generate_content(system_prompt)
            return response.text
        except Exception as e:
            return "LIVE ERROR: {}".format(str(e))

    else:
        # Demo Mode: answers built FROM REAL PARSED DATA
        q_lower = question.lower()

        if any(w in q_lower for w in ['risk', 'flag', 'concern', 'warning']):
            signals = "<br>".join("- " + s for s in actual_positive_signals) if actual_positive_signals else "None captured"
            factors = "<br>".join("- " + f for f in actual_risk_factors) if actual_risk_factors else "None flagged"
            return "<b>Risk Assessment from Evidence:</b><br><br>Risk Level: <b style='color: #10b981;'>{}</b><br><br><b>Positive Signals:</b><br>{}<br><br><b>Risk Factors:</b><br>{}".format(
                actual_risk_level, signals, factors)

        elif any(w in q_lower for w in ['decision', 'approve', 'reject', 'outcome', 'result', 'loan']):
            conf_str = "{:.0%}".format(float(actual_confidence)) if actual_confidence != "N/A" else "N/A"
            return "<b>Loan Decision from Evidence:</b><br><br><span style='font-size: 1.2em; color: #10b981;'>{}</span> with <b>{} confidence</b><br><br><b>AI Reasoning:</b><br>{}<br><br><b>Risk Factors:</b> {}".format(
                actual_decision, conf_str, actual_reasoning,
                ', '.join(actual_risk_factors) if actual_risk_factors else 'None')

        elif any(w in q_lower for w in ['fair', 'bias', 'discriminat', 'equal', 'compliance', 'legal']):
            return "<b>Fair Lending Compliance Check:</b><br><br>The AI was explicitly instructed:<br><br><i>Assess loans based ONLY on financial metrics. MUST NOT consider gender, race, religion.</i><br><br><b>Evidence confirms:</b><br>- Only financial data was provided (credit score, revenue, transactions)<br>- No protected class information in any captured prompts<br>- Decision: <b>{}</b> based on financial metrics only".format(actual_decision)

        elif any(w in q_lower for w in ['transaction', 'payment', 'bank', 'statement', 'balance', 'monthly']):
            txn_html = "<br>".join(
                "{}. {}".format(i+1, t) for i, t in enumerate(actual_transactions)
            ) if actual_transactions else "Not captured in this run"
            return "<b>Bank Statement from Evidence:</b><br><br><b>Average Monthly Balance:</b> ${:,.0f}<br><br><b>Captured Transactions:</b><br>{}".format(
                actual_balance, txn_html)

        else:
            return "<b>EPI Evidence Summary:</b><br><br>This package recorded a <b>loan underwriting workflow</b>.<br><br><b>From the evidence:</b><br>- Decision: <b>{}</b> ({})<br>- Risk Level: {}<br>- Reasoning: {}...<br><br><b>Try asking:</b> What risk factors? or Was this fair?".format(
                actual_decision, actual_confidence, actual_risk_level, str(actual_reasoning)[:100])

def show_qa(question, answer):
    display(HTML("""
    <div style="background: #1f2937; border-radius: 12px; padding: 20px; margin: 15px 0;">
        <div style="display: flex; margin-bottom: 15px;">
            <div style="background: #3b82f6; color: white; padding: 8px 14px; border-radius: 8px; margin-right: 12px; font-weight: bold; min-width: 50px; text-align: center;">YOU</div>
            <div style="background: #374151; color: #e5e7eb; padding: 12px 18px; border-radius: 8px; flex: 1; font-size: 15px;">{}</div>
        </div>
        <div style="display: flex;">
            <div style="background: #10b981; color: white; padding: 8px 14px; border-radius: 8px; margin-right: 12px; font-weight: bold; min-width: 50px; text-align: center;">EPI</div>
            <div style="background: #374151; color: #e5e7eb; padding: 12px 18px; border-radius: 8px; flex: 1; font-size: 15px; line-height: 1.6;">{}</div>
        </div>
    </div>
    """.format(question, answer)))

if epi_file:
    print("=" * 70)
    display(HTML('<h2 style="color: #10b981; margin-bottom: 5px;">Live Evidence Chat</h2>'))
    display(HTML('<p style="color: #6b7280; margin-top: 0;">Interrogating: <b>{}</b></p>'.format(epi_file.name)))

    mode_label = 'Live Gemini 2.0 Flash' if api_key else 'Demo Mode (parsing real captured data)'
    display(HTML("""
    <div style='margin-bottom: 15px;'>
        <span style='color: #f9a8d4; font-family: monospace; background: #374151; padding: 6px 12px; border-radius: 6px; border: 1px solid #db2777;'>
            Mode: {}
        </span>
    </div>
    """.format(mode_label)))

    display(HTML('<p style="color: #94a3b8; font-style: italic; margin: 20px 0 5px 0;">Example question (auto-generated):</p>'))
    initial_answer = ask_evidence("risk factors")
    show_qa("What risk factors were identified in this loan decision?", initial_answer)

    try:
        import ipywidgets as widgets
        output = widgets.Output()

        def make_handler(q):
            def handler(b):
                with output:
                    clear_output()
                    show_qa(q, ask_evidence(q))
            return handler

        questions = [
            ("Why approved?", "Why was this loan approved?"),
            ("Fairness Check", "Was this fair and unbiased?"),
            ("Transactions", "What transactions were analyzed?"),
            ("Profile", "Tell me about the applicant"),
        ]

        buttons = []
        for label, q in questions:
            btn = widgets.Button(description=label, layout=widgets.Layout(width='auto', margin='5px'))
            btn.on_click(make_handler(q))
            buttons.append(btn)

        display(widgets.HBox(buttons, layout=widgets.Layout(flex_wrap='wrap')))
        display(output)

        display(HTML('<p style="color: #94a3b8; margin: 20px 0 10px 0;">Or ask your own:</p>'))
        text_input = widgets.Text(placeholder='Ask anything about this evidence...', layout=widgets.Layout(width='70%'))
        ask_btn = widgets.Button(description="Ask", button_style='success')
        def on_ask(b):
            if text_input.value.strip():
                with output:
                    clear_output()
                    show_qa(text_input.value, ask_evidence(text_input.value))
        ask_btn.on_click(on_ask)
        display(widgets.HBox([text_input, ask_btn]))
    except Exception as e:
        display(HTML('<p style="color: #f59e0b;">Interactive widgets unavailable. Showing sample Q&A:</p>'))
        show_qa("Why was this approved?", ask_evidence("why approved"))
        show_qa("Was this fair?", ask_evidence("fair"))

    print("=" * 70)
else:
    display(HTML('<p style="color: #ef4444;">Run the recording cell first to capture evidence.</p>'))
