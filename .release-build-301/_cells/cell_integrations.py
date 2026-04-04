# @title Framework Integrations { display-mode: "form" }
from IPython.display import display, HTML

display(HTML(
    '<div style="background: #0f172a; border-radius: 16px; padding: 30px; margin: 20px 0; font-family: monospace;">'

    '<div style="margin-bottom: 25px;">'
    '<span style="color: #60a5fa; font-weight: bold; font-size: 16px;">LiteLLM (100+ providers)</span>'
    '<div style="background: #1e293b; padding: 12px 18px; border-radius: 8px; margin-top: 8px; color: #e2e8f0;">'
    'litellm.callbacks = [EPICallback()]</div></div>'

    '<div style="margin-bottom: 25px;">'
    '<span style="color: #a78bfa; font-weight: bold; font-size: 16px;">LangChain</span>'
    '<div style="background: #1e293b; padding: 12px 18px; border-radius: 8px; margin-top: 8px; color: #e2e8f0;">'
    'llm = ChatOpenAI(callbacks=[EPICallbackHandler()])</div></div>'

    '<div style="margin-bottom: 25px;">'
    '<span style="color: #34d399; font-weight: bold; font-size: 16px;">LangGraph</span>'
    '<div style="background: #1e293b; padding: 12px 18px; border-radius: 8px; margin-top: 8px; color: #e2e8f0;">'
    "checkpointer = EPICheckpointSaver('agent.epi')</div></div>"

    '<div style="margin-bottom: 25px;">'
    '<span style="color: #f472b6; font-weight: bold; font-size: 16px;">OpenAI (Direct)</span>'
    '<div style="background: #1e293b; padding: 12px 18px; border-radius: 8px; margin-top: 8px; color: #e2e8f0;">'
    'client = wrap_openai(OpenAI())</div></div>'

    '<div style="margin-bottom: 25px;">'
    '<span style="color: #fbbf24; font-weight: bold; font-size: 16px;">pytest</span>'
    '<div style="background: #1e293b; padding: 12px 18px; border-radius: 8px; margin-top: 8px; color: #e2e8f0;">'
    'pytest --epi</div></div>'

    '<div style="margin-bottom: 0;">'
    '<span style="color: #fb923c; font-weight: bold; font-size: 16px;">CI/CD (GitHub Actions)</span>'
    '<div style="background: #1e293b; padding: 12px 18px; border-radius: 8px; margin-top: 8px; color: #e2e8f0;">'
    '- uses: mohdibrahimaiml/epi-recorder/.github/actions/verify-epi@main</div></div>'

    '</div>'
    '<p style="text-align: center; color: #6b7280; font-size: 16px; margin-top: 15px;">'
    '<b>One line. Any framework. Signed evidence.</b></p>'
))
