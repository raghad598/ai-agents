"""
llm.py — sends messages to an AI language model via the OpenRouter API.

This file is the bridge between your Flask app and an AI model (GPT-3.5).
When a student types a message in the chat, it travels here, gets sent to
OpenRouter, and the AI's reply comes back.

KEY CONCEPTS:
  - API (Application Programming Interface): a way for two programs to talk
    to each other over the internet. OpenRouter exposes an API we can call.
  - HTTP POST request: sending data to a server (like submitting a form).
    We POST the conversation to OpenRouter and it POSTs back the AI reply.
  - System prompt: instructions given to the AI before the conversation starts.
    Think of it as the AI's job description.
"""

import os
import re
import requests
from flask import session
from jinja2 import Template
# The URL we send our messages to.
# OpenRouter acts as a single gateway to many different AI models.
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Which AI model to use. OpenRouter supports many models.
# Models with ':free' suffix are free to use — no API credits needed.
# See all available models at: https://openrouter.ai/models
# QUESTION: What would change if you switched to a different model?
#           Try 'google/gemma-2-9b-it:free' or 'mistralai/mistral-7b-instruct:free'.
DEFAULT_MODEL = "openai/gpt-4o-mini"

from jinja2 import Template

# One shared template for every expert's system prompt. Each expert just
# fills in different values for role/domain/instructions/context/examples.
MASTER_TEMPLATE = Template("""\
You are a {{ role }}, an expert in {{ domain }}.

{{ specific_instructions }}
{% if background_context %}
Context:
{{ background_context }}
{% endif %}
{% if few_shot_examples %}
Examples:
{{ few_shot_examples }}
{% endif %}
Request: {{ request }}
""", trim_blocks=True, lstrip_blocks=True)


def fill_template(role, domain, specific_instructions, request,
                   background_context="", few_shot_examples=""):
    """
    Render MASTER_TEMPLATE into one expert's full system prompt.

    background_context and few_shot_examples are optional: the {% if %}
    blocks drop the whole section when the argument is empty.
    """
    return MASTER_TEMPLATE.render(
        role=role,
        domain=domain,
        specific_instructions=specific_instructions,
        background_context=background_context,
        few_shot_examples=few_shot_examples,
        request=request,
    ).strip()

def send_message(user_message, system_prompt="You are a helpful assistant."):
    """
    Send a message to the AI and return its response as a string.

    Args:
        user_message  (str): The message the user typed in the chat.
        system_prompt (str): Instructions that define how the AI should behave.
                             This is sent before the user message, every time.

    Returns:
        str: The AI's reply text, or an error message if something went wrong.

    HOW IT WORKS:
        We build a 'messages' list with two entries:
          1. system — gives the AI its instructions (the resume context)
          2. user   — the student's actual question
        We send this list to OpenRouter, which forwards it to the AI model
        and returns the generated reply.

    # NOTE: This function has no memory — each call starts fresh.
    #       Every message includes the full system prompt but no chat history.
    # QUESTION: How would you modify this to remember previous messages?
    #           Hint: you would need to store past messages and include them
    #           in the 'messages' list between the system and user entries.
    """
    api_key = os.getenv('OPENROUTER_API_KEY')

    # If the .env file is missing or the key was not filled in, tell the user
    # immediately rather than making a doomed API call that will just hang.
    if not api_key or api_key == 'paste-your-key-here':
        return "⚠️ No API key found. Add your OpenRouter key to the .env file and restart the app."

    # The Authorization header tells OpenRouter who we are.
    # "Bearer" is just a standard prefix for API key authentication.
    # NEVER hardcode the api_key here — always load it from the .env file.
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8080"   # identifies our app to OpenRouter
    }

    # The messages list defines the conversation context for the AI.
    # 'system' sets the AI's role and knowledge before it sees our question.
    # 'user' is the message the student actually typed.
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_message}
    ]

    # Send the HTTP POST request to OpenRouter.
    # timeout=30 means: give up if we don't hear back within 30 seconds.
    response = requests.post(
        OPENROUTER_URL,
        headers=headers,
        json={"model": DEFAULT_MODEL, "messages": messages},
        timeout=30
    )

    result = response.json()

    # OpenRouter sometimes returns HTTP 200 but with an 'error' field instead
    # of 'choices' — this happens with a bad API key or an invalid request.
    # QUESTION: Print result here and see what OpenRouter actually sends back.
    if 'error' in result:
        error_message = result['error'].get('message', 'Unknown API error')
        return f"⚠️ OpenRouter error: {error_message}"

    if 'choices' not in result:
        return f"⚠️ Unexpected response from OpenRouter: {result}"

    return result['choices'][0]['message']['content']
def handle_ai_chat_request(db, role, message):
    """
    Route a chat message to the named expert.
    """
    if role is None:
        return send_message(message)

    config = db.getLLMRoles()[role]
    background_context = config['background_context'] or ""
    if role == "Content Expert":
        background_context += "\n" + db.getResumeText()

    system_prompt = fill_template(
        role=config['role'],
        domain=config['domain'],
        specific_instructions=config['specific_instructions'],
        background_context=background_context,
        few_shot_examples=config['few_shot_examples'] or "",
        request=message,
    )
    output = send_message(message, system_prompt).strip()
    print(f"[{role}] generated:\n{output}\n")

    if role == "Database Read Expert":
        return execute_read_query(db, output)
    if role == "Database Write Expert":
        return execute_write_action(db, output)
    if role == "Database Semantic Search Expert":
        return execute_semantic_search(db, output) 
    if role == "Job Analysis Expert":
        return execute_job_analysis(db, output)
    if role == "Orchestrator":
        return run_orchestrator_plan(db, message, output)
    return output   # Content Expert -- output is already the final answer

def execute_semantic_search(db, output):
    
    """
    Run the Database Semantic Search Expert's output.

    Homework 2: this is a separate expert (its own role, its own executor
    function here) rather than a second thing the Read Expert might say --
    the Orchestrator picks this role instead of "Database Read Expert" in
    its plan whenever a request names something by an abbreviation,
    paraphrase, or general category that might not match the database's
    exact wording.

    The expert is told (see llm_roles.csv) to respond with exactly one
    line in the form "<table>|<search text>".
    """
    try:
        table, query_text = output.strip().split('|', 1)
        results = db.semanticSearch(table.strip(), query_text.strip())
        for row in results:
            label = row.get('name') or row.get('title')
            print(f"  match: {label} (similarity {row['similarity']})")
        return str(results)
    except Exception as error:
        print(f"Semantic search failed: {error}")
        return "Sorry, that question couldn't be answered."

def execute_job_analysis(db, output):
    """
    Run the Job Analysis Expert's output.

    The expert returns a Python list literal of requirement strings.
    This parses it and returns the list -- the Match Expert consumes
    this directly, so it stays a real list rather than prose.
    """
    try:
        requirements = eval(output.strip())
        if not isinstance(requirements, list):
            raise ValueError("expected a list")
        print(f"  extracted {len(requirements)} requirements:")
        for requirement in requirements:
            print(f"    - {requirement}")
        return requirements
    except Exception as error:
        print(f"Job analysis failed: {error}")
        return []
def execute_match(db, requirements):
    """
    Run the match analysis. Unlike the other experts, this one does NOT
    call the LLM -- the requirements are already extracted, and matching
    them is embedding arithmetic. Keeping it out of the model makes the
    score reproducible: the same posting always gives the same number.
    """
    score, matched, gaps = db.matchRequirements(requirements)

    print(f"\n  MATCH SCORE: {score}%")
    print(f"  matched {len(matched)} of {len(requirements)} requirements")
    for item in matched:
        print(f"    OK   {item['requirement']}  <-  {item['evidence']} ({item['similarity']})")
    for gap in gaps:
        print(f"    GAP  {gap}")

    return {'score': score, 'matched': matched, 'gaps': gaps}
def execute_read_query(db, sql):
    """
    Run the Read Expert's generated SQL. Refuse anything that isn't SELECT.
    """
    if not sql.strip().upper().startswith("SELECT"):
        return "Sorry, I couldn't safely answer that question."
    try:
        return str(db.query(sql))
    except Exception as error:
        print(f"Read Expert query failed: {error}")
        return "Sorry, that question couldn't be answered."


def execute_write_action(db, generated_code):
    """
    Run the Write Expert's generated Python via exec().
    """
    local_vars = {}
    try:
        exec(generated_code, {"db": db, "NULL": None}, local_vars)
    except Exception as error:
        print(f"Write Expert code failed: {error}")
        return "Operation was unsuccessful."
    return local_vars.get("outcome", "Operation was unsuccessful.")


def run_orchestrator_plan(db, original_request, plan_text):
    """
    Parse the Orchestrator's plan, run each expert call in order, then
    synthesize one clean reply.
    """
    try:
        call_strings = eval(plan_text)
    except Exception:
        print(f"Orchestrator returned an unparseable plan: {plan_text}")
        return "Sorry, I couldn't plan a response to that."

    results = []
    for call_string in call_strings:
        print(f"[Orchestrator] executing: {call_string}")
        match = re.search(r'role="([^"]*)",\s*message="([^"]*)"', call_string)
        role, message = match.group(1), match.group(2)
        response = handle_ai_chat_request(db, role, message)
        results.append((role, message, response))

    steps_summary = "\n".join(f"{r}: {resp}" for r, m, resp in results)
    synthesis_prompt = (
        f'The user asked: "{original_request}"\n\n'
        f"Here is what each expert found or did:\n{steps_summary}\n\n"
        "Write ONE short, clear reply. A Database Write Expert step's result "
        "is already the exact message to show the user -- if one is present, "
        "reuse it verbatim rather than rephrasing it. Otherwise, summarize the "
        "other results in plain language. Never mention SQL, Python, code, "
        "or these internal steps."
    )
    return send_message(original_request, synthesis_prompt)

# ======================================================================
# HOMEWORK 2 - HUMAN VALIDATION WORKFLOW
#
# The Write Expert above genuinely deletes/modifies rows via exec(). These
# three functions gate that behind an explicit yes/no confirmation for any
# message that looks destructive, instead of letting it run unsupervised.
# ======================================================================

# A fast, predictable keyword scan -- not another AI call -- runs BEFORE
# anything gets anywhere near the Orchestrator or exec().
DANGEROUS_KEYWORDS = ['delete', 'remove', 'clear', 'drop', 'destroy']

def assess_message_risk(message):
    """
    Return True if `message` contains a keyword associated with a
    destructive/irreversible database action.
    """
    lowered = message.lower()
    return any(keyword in lowered for keyword in DANGEROUS_KEYWORDS)

def request_human_validation(message):
    """
    Pause a risky request and ask the user to confirm before anything
    runs. Stashes the original message in the Flask session under
    'pending_validation' -- the NEXT message the user sends is then
    checked (in socket_events.py) against that key, so it's interpreted
    as the yes/no answer to THIS question rather than a new, unrelated
    chat message.
    """
    session['pending_validation'] = message
    return (
        f'This looks like it could delete or modify data: "{message}". '
        f'Are you sure you want to proceed? (yes/no)'
    )

def handle_validation_response(db, response):
    """
    Called instead of the normal chat flow whenever session has a
    'pending_validation' entry waiting.

    "yes"    -> clear the pending state, run the ORIGINAL message through
                the normal Orchestrator flow
    "no"     -> clear the pending state, cancel
    anything else -> keep the pending state active and ask again
    """
    original_message = session['pending_validation']
    normalized = response.strip().lower()

    if normalized in ('yes', 'y'):
        session.pop('pending_validation')
        return handle_ai_chat_request(db, role="Orchestrator", message=original_message)

    if normalized in ('no', 'n'):
        session.pop('pending_validation')
        return "Okay, I won't do that. The request was cancelled."

    return f'Please answer "yes" or "no" -- do you want me to proceed with: "{original_message}"?'
def analyze_job_posting(db, posting_text):
    """
    The project's main pipeline: posting in, analysis out.

    Three stages, deliberately in this order:
      1. Job Analysis Expert  -- LLM call, extracts requirements
      2. Match Expert         -- NO LLM call, pure embedding arithmetic
      3. Cover Letter Expert  -- LLM call, writes from matched evidence only

    Stage 2 sits between two LLM calls on purpose: the letter is written
    from verified matches, not from the posting, so the model cannot
    invent experience the applicant does not have.
    """
    print("\n=== STAGE 1: extracting requirements ===")
    requirements = handle_ai_chat_request(db, role="Job Analysis Expert", message=posting_text)
    if not requirements:
        return "I couldn't read any requirements from that posting."

    print("\n=== STAGE 2: matching against resume database ===")
    result = execute_match(db, requirements)

    print("\n=== STAGE 3: writing cover letter ===")
    evidence = ", ".join(f"[{m['requirement']} <- {m['evidence']}]" for m in result['matched'])
    if not result['matched']:
        letter = "(No cover letter: none of the requirements matched your record.)"
    else:
        letter = handle_ai_chat_request(
            db,
            role="Cover Letter Expert",
            message=f"Matched evidence (the ONLY things you may cite): {evidence}",
        )

    gaps_text = "\n".join(f"  - {g}" for g in result['gaps']) or "  (none)"
    return (
        f"MATCH SCORE: {result['score']}%  "
        f"({len(result['matched'])} of {len(requirements)} requirements matched)\n\n"
        f"GAPS -- requirements with no evidence in your record:\n{gaps_text}\n\n"
        f"COVER LETTER:\n{letter}"
    )