import json
from openai import OpenAI
import os
import copy

# Field display names and descriptions
FIELD_INFO = {
    "problem_definition": {
        "name": "Problem Definition",
        "description": "What specific problem does your startup solve?"
    },
    "solution_description": {
        "name": "Solution Description",
        "description": "What is your solution?"
    },
    "icp": {
        "name": "Ideal Customer Profile",
        "description": "Who specifically experiences this problem?"
    }
}

def get_default_pitch_data():
    """Returns the default pitch data structure"""
    return {
        "problem_definition": {"value": "", "state": "unknown"},
        "solution_description": {"value": "", "state": "unknown"},
        "icp": {"value": "", "state": "unknown"}
    }

def get_completion_stats(pitch_data):
    """Calculate completion statistics"""
    total = len(pitch_data)
    complete = sum(1 for field in pitch_data.values() if field["state"] == "complete")
    partial = sum(1 for field in pitch_data.values() if field["state"] == "partial")
    unknown = sum(1 for field in pitch_data.values() if field["state"] == "unknown")

    return {
        "total": total,
        "complete": complete,
        "partial": partial,
        "unknown": unknown,
        "percentage": (complete / total * 100) if total > 0 else 0
    }

def ingest(client: OpenAI, conversation_history: list, pitch_data: dict) -> dict:
    """
    Conversational function to extract and refine pitch data.
    Returns updated pitch_data and AI response.
    """

    # Build system prompt with current state
    stats = get_completion_stats(pitch_data)

    # Create a summary of current state for the AI
    state_summary = "Current pitch data collection status:\n"
    for field_key, field_data in pitch_data.items():
        field_name = FIELD_INFO[field_key]["name"]
        state = field_data["state"]
        value = field_data["value"]

        state_summary += f"\n- {field_name}: {state.upper()}"
        if value:
            state_summary += f"\n  Current value: {value[:100]}..." if len(value) > 100 else f"\n  Current value: {value}"

    state_summary += f"\n\nProgress: {stats['complete']}/{stats['total']} complete ({stats['percentage']:.0f}%)"

    system_prompt = f"""You are a supportive startup pitch coach having a natural conversation with a founder. Your goal is to understand their:
1. What problem they're solving
2. What their solution is
3. Who their ideal customers are

{state_summary}

CONVERSATION STYLE:
- Be conversational and natural - avoid mentioning "fields" or structured data
- Let founders provide information in any order - they can give you everything at once or piece by piece
- If they provide all 3 pieces of info in one message, acknowledge it and mark everything complete
- Only ask follow-up questions if critical information is genuinely missing
- Keep responses concise and focused (1-2 sentences max)

EXTRACTION RULES:
- Extract ALL information the user provides in each message - look for problem, solution, AND customers
- If a founder says "I'm building X for Y to solve Z", that likely contains all 3 pieces
- Mark information as "complete" when you have a clear, specific answer - don't overthink it
- Be very liberal with marking things complete - if you have ANY reasonable info, mark it complete
- When you have all 3 pieces of information with ANY level of detail, you're done - mark READY

TECHNICAL FORMAT (hidden from user):
For each piece of information you extract, add a JSON block at the END:
---UPDATE---
{{"field_key": "problem_definition", "value": "the extracted value", "state": "complete"}}
---END---

Create one UPDATE block for EACH piece of info you extract. When all 3 are complete, add:
---READY_FOR_EVALUATION---

Information to collect:
- problem_definition: What problem are they solving? (Can be brief - even 1 sentence is fine)
- solution_description: What is their solution? (Can be brief - even 1 sentence is fine)
- icp: Who are their target customers? (Can be brief - even 1-2 words describing the persona is fine)
"""

    messages = [
        {"role": "system", "content": system_prompt},
        *conversation_history
    ]

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.7
    )

    ai_message = response.choices[0].message.content

    # Parse any updates from the AI response
    updated_pitch_data = copy.deepcopy(pitch_data)
    ready_for_eval = False

    if "---UPDATE---" in ai_message:
        # Extract update blocks
        parts = ai_message.split("---UPDATE---")
        for i in range(1, len(parts)):
            if "---END---" in parts[i]:
                json_str = parts[i].split("---END---")[0].strip()
                try:
                    update = json.loads(json_str)
                    field_key = update.get("field_key")
                    if field_key in updated_pitch_data:
                        updated_pitch_data[field_key]["value"] = update.get("value", "")
                        updated_pitch_data[field_key]["state"] = update.get("state", "partial")
                except json.JSONDecodeError:
                    pass  # Ignore malformed JSON

    if "---READY_FOR_EVALUATION---" in ai_message:
        ready_for_eval = True

    # Clean the message for display (remove JSON blocks)
    display_message = ai_message
    if "---UPDATE---" in display_message:
        display_message = display_message.split("---UPDATE---")[0].strip()
    if "---READY_FOR_EVALUATION---" in display_message:
        display_message = display_message.replace("---READY_FOR_EVALUATION---", "").strip()

    return {
        "pitch_data": updated_pitch_data,
        "response": display_message,
        "ready_for_evaluation": ready_for_eval
    }

def evaluate(client: OpenAI, pitch_data: dict) -> dict:
    """
    Evaluates the pitch with an objective, investor perspective.
    Returns structured evaluation as a dictionary.
    """

    # Build pitch summary for evaluation
    pitch_summary = "PITCH SUMMARY:\n\n"
    for field_key, field_data in pitch_data.items():
        field_name = FIELD_INFO[field_key]["name"]
        value = field_data["value"]
        pitch_summary += f"{field_name}:\n{value}\n\n"

    # Step 1: Perform web search to gather competitive intelligence using OpenAI's web_search tool
    web_research_prompt = f"""Research the competitive landscape for this startup pitch using web search. Find REAL, current information about:

{pitch_summary}

Search for and identify:
1. **Direct competitors** - Companies solving the exact same problem with similar solutions (find 2-3 specific company names with their funding, market position, and key features)
2. **Indirect competitors** - Alternative approaches or solutions in this space (identify 2-3 specific companies or solution categories)
3. **Market dynamics** - Recent funding rounds, acquisitions, market trends, growth rates in this space

Provide SPECIFIC company names, funding amounts, founding dates, and verifiable data. Cite sources."""

    # For now, use GPT-4o's knowledge base for competitive research
    # Web search via OpenAI API is not available in standard API
    research_response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a startup research analyst with extensive knowledge of tech companies, funding data, and market trends. Provide specific company names and data based on your training data."},
            {"role": "user", "content": web_research_prompt}
        ],
        temperature=0.3
    )

    web_research_results = research_response.choices[0].message.content

    # Step 2: Structure the competitive analysis with web search data
    competitive_analysis_prompt = f"""Based on the web search findings below, create a structured competitive landscape analysis:

{pitch_summary}

RESEARCH FINDINGS:
{web_research_results}

Structure your analysis as follows:

**DIRECT COMPETITORS:**
List 2-3 companies solving the exact same problem with similar approaches. For each:
- Company name and brief description
- Why they matter (market share, funding, user base)
- Key differentiators from this pitch

**INDIRECT COMPETITORS:**
List 2-3 solutions that address the same need differently. For each:
- Solution type and key players
- Why users choose this alternative
- What makes it competitive

**SUBSTITUTE BEHAVIORS:**
What do people do today when they don't use any product? Why does this matter?

**MARKET DYNAMICS:**
- Recent funding/exits in this space
- Market trends (growing/declining/saturated)
- Switching costs and user lock-in factors

Use the research findings to provide SPECIFIC company names and data. If data is unavailable, note that explicitly."""

    competitive_response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a startup research analyst synthesizing research into a structured competitive analysis. Use specific company names and data from the research provided."},
            {"role": "user", "content": competitive_analysis_prompt}
        ],
        temperature=0.5
    )

    competitive_analysis = competitive_response.choices[0].message.content

    # Step 2: Structured evaluation
    system_prompt = f"""You are a savvy YC-style investor evaluating startup pitches. Be OBJECTIVE and HONEST.

Evaluate this pitch and respond with a JSON object with these exact fields:

{{
  "problem_clarity": {{
    "score": 1-10,
    "assessment": "Clear explanation of score and whether the problem is well-defined, specific, and compelling"
  }},
  "severity": {{
    "score": 1-10,
    "assessment": "How painful is this problem? Is it a must-have or nice-to-have? Do people actively seek solutions?"
  }},
  "competitive_analysis": {{
    "summary": "Use the competitive research provided below",
    "competitive_advantage": "Critical assessment of whether this solution is actually better/defensible"
  }},
  "gtm_challenges": {{
    "organic_viral_potential": {{
      "feasibility": "LOW/MEDIUM/HIGH - Can this realistically grow organically/virally?",
      "reasoning": "Specific analysis of network effects, word-of-mouth triggers, viral loops. Are competitors succeeding with organic growth? What's the benchmark?",
      "competitor_examples": "Which competitors (if any) are growing organically? What's their playbook?"
    }},
    "paid_acquisition": {{
      "competitiveness": "LOW/MEDIUM/HIGH - How competitive is paid marketing in this space?",
      "unit_economics": "Analysis of CAC, LTV, payback period. Is profitable paid acquisition realistic given competitive pressure?",
      "channels": "What channels work? CPCs/CPMs? How saturated?"
    }},
    "retention_monetization": {{
      "assessment": "Can you retain users and monetize well enough to overcome acquisition costs?"
    }},
    "overall_gtm_score": 1-10
  }},
  "overall_verdict": {{
    "decision": "FUNDABLE or NOT FUNDABLE YET",
    "reasoning": "2-3 sentence bottom line explanation"
  }}
}}

COMPETITIVE RESEARCH:
{competitive_analysis}

Be harsh and realistic. Don't sugarcoat. Focus on what actually matters for venture-scale returns."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Evaluate this pitch:\n\n{pitch_summary}"}
    ]

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.7,
        response_format={"type": "json_object"}
    )

    evaluation_json = json.loads(response.choices[0].message.content)

    return {
        "evaluation": evaluation_json,
        "competitive_analysis_full": competitive_analysis
    }
