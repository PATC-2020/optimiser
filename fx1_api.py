from flask import Flask, render_template, request, jsonify
from flask import redirect
from flask_cors import CORS
from dirtyjson import load as dirty_load
import openai
import traceback
import sys
import re
import io
import json
import requests




def query_gpt(prompt):
    preferred_models = ["gpt-4o", "gpt-4-1106-preview", "gpt-4-0613", "gpt-4", "gpt-3.5-turbo-16k", "gpt-3.5-turbo"]
    response = None
    parsed = None

    for model_name in preferred_models:
        try:
            response = openai.ChatCompletion.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2048,
                temperature=0.4
            )
            raw_output = response["choices"][0]["message"]["content"]
            print("🧠 Raw GPT response:", raw_output)

            if raw_output.strip().startswith("```json"):
                raw_output = raw_output.strip()[7:-3].strip()
            elif raw_output.strip().startswith("```"):
                raw_output = raw_output.strip()[3:-3].strip()

            raw_output = re.sub(r",\s*([\]}])", r"\1", raw_output)
            raw_output = re.sub(r'"\s*\n\s*"', " ", raw_output)

            parsed = dirty_load(io.StringIO(raw_output))
            return parsed

        except openai.error.InvalidRequestError as e:
            print(f"⚠️ Model {model_name} failed: {str(e)}")
            continue
        except Exception as e:
            print(f"❌ Unexpected error with model '{model_name}': {str(e)}")
            import traceback
            traceback.print_exc()
            continue

    if not parsed:
        return jsonify({'error': 'No valid GPT model could be used.'}), 500

    statements = parsed.get("statements", [])
    problem_titles = parsed.get("problem_titles", [])

    return jsonify({
        "statements": statements,
        "titles": problem_titles,
    })



SYSTEM_INSTRUCTIONS = ("""
"You are an AI expert at developing problem-centric reasoning to help businesses shift from product-led to problem-led thinking, deriving underlying problems for perceived product features and benefits."
"You extracs product detail from web content and outputs clean, strict JSON only."
"Do not add commentary, do not repeat the input, and do not include anything outside the JSON object."
"Return only a strict JSON object matching this schema: { ... }"
""")

PROMPT_URL_EXTRACT = """
You are an AI expert that analyses website content to extract structured business insight. Do not explain your reasoning or process. Only return the output using the format provided. Use UK English throughout. Avoid all US spelling (e.g. use ‘realise’, not ‘realize’; ‘organisation’, not ‘organization’).

You will receive full extracted text content from a webpage.

Return only a single JSON object. Do not output any content or commentary before or after the JSON.

From this, return ONLY:
- A product name (max 10 words). Must not include company name or organisation name. Return only the product name as stated or inferred.
- A short product summary (max 35 words)
- A list of up to 4 features (each with a short title and one-sentence detail)
- A list of up to 4 benefits (each with a short title and one-sentence detail)
- Customer context: 1 sentence description, 1 industry, 1 challenge

MUST be in this JSON object, do not include any extra text, comments or explanation. Return only the JSON. Begin immediately with '{' and end with '}', strictly following this structure:

Only output content between the following triple backticks. Do not include anything else:
```json

{{
  "non-instructional data",
  "product_name": "string",
  "product_summary": "string",
  "features": [{{"title": "string", "detail": "string"}}],
  "benefits": [{{"title": "string", "detail": "string"}}],
  "customer_context": {{
    "description": "string",
    "industry": "string",
    "challenges": "string"
  }}
}}

Return all page content not used in product_name, summary, features, benefits, or customer_context in a field called 'non-instructional data'. Do not omit it, even if empty.

Then return the structured JSON block in your final output.

"""

URL_EXTRACT_FUNCTION = {
    "name": "url_extract",
    "description": "Extract structured product info from HTML",
    "parameters": {
        "type": "object",
        "properties": {
            "product_name":    {"type": "string"},
            "product_summary": {"type": "string"},
            "features": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title":  {"type": "string"},
                        "detail": {"type": "string"}
                    },
                    "required": ["title","detail"]
                }
            },
            "benefits": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title":  {"type": "string"},
                        "detail": {"type": "string"}
                    },
                    "required": ["title","detail"]
                }
            },
            "customer_context": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "industry":    {"type": "string"},
                    "challenges":  {"type": "string"}
                },
                "required": ["description","industry","challenges"]
            }
        },
        "required": ["product_name","product_summary","features","benefits","customer_context"]
    }
}

PROMPT_PROBLEM_DERIVATION = """
You are an AI expert at developing problem-centric reasoning to help businesses shift from product-led to problem-led thinking. Your task is to analyse a predefined data on a product, its features, benefits, and customer context, and return structured outputs across multiple stages of logic. Follow these steps precisely and return all outputs in JSON format:

A) Derive Underlying Problems (for use in Stage 2)
For each Feature and Benefit provided in Stage 1, you must derive the underlying customer problem using the following structured logic:
a. Apply a 5 Whys reasoning process to uncover the deeper issue that the feature or benefit is addressing. Each “Why” should build naturally from the last, using realistic and human logic.
b. Use the Product Summary, Customer Context, Challenges, and Industry/Segment fields to enrich your understanding and make each “Why” contextually relevant.
c. Ensure the final derived problem reflects the true pain experienced by the customer, not a restatement of the product or its utility. It must feel like a problem that could be expressed by the customer if they had the language.
d. Do not reuse the original feature or benefit wording in the problem. Instead, focus on the impact, frustration, or limitation the customer faces if that feature or benefit didn’t exist.
e. Use a natural, realistic tone—do not use templates or repeatable phrasing like “Challenge with…” or “Risk of…”. Each problem must be unique, organic, and problem-centric.
f. For each Feature or Benefit, derive up to 3 distinct underlying problems where logically possible, based on 5 Whys analysis. If multiple meaningful problems are found, output them individually. If only one strong problem is found, output just that one. Each problem must be tied back to the originating Feature or Benefit title, allowing multiple problems per title if appropriate.
g. Ensure that a minimum of 10 total problems are generated across Features and Benefits. If fewer than 10 are generated, include weaker ones as needed. If 11 or more are generated, you may suppress any with a weak logic chain, unclear linkage, or low relevance—but only once the threshold of 10 is met.
h. When presenting each problem, include the original Title associated with the Feature or Benefit.

B) Output Structured Report Fields (for use in Stage 2)
Compile the following:
a. Product Info: Product Name, Summary, Customer Context (Industry, Segment, Challenges)
b. Full Problem Table: all problems with category (Feature/Benefit), Pain, Urgency, and Score
Deliver all outputs in a single JSON object with structured sections for:
•   "features"
•   "benefits"
•   "problem_elements"
•   "statements"
•   "problem_titles"
Each Feature and Benefit object must include:
- title
- category
- problem
- pain
- urgency
- score

Do not explain your process—only return the structured data. Use UK English throughout. Avoid all US spelling (e.g. use ‘realise’, not ‘realize’; ‘organisation’, not ‘organization’).

"""

PROMPT_PROBLEMS = """

You are an AI expert at developing problem-centric reasoning to help businesses shift from product-led to problem-led thinking. Your task is to analyse a predefined data on a product, its features, benefits, and customer context, and return structured outputs across multiple stages of logic. Follow these steps precisely and return all outputs in JSON format:
A) Rate and Score
1.  Rate Pain and Urgency (for use in Stage 2) - For each underlying problem, assign a Pain rating and an Urgency rating, using only the following values: High, Medium, or Low. Attribute High = 3, Medium = 2, and Low = 1, in order to calculate an amalgamated Score (Pain × Urgency). No other labels are allowed.
2.  Prioritise Problems (for use in Stage 2) - Sort the list of problems by descending amalgamated Score, but return ALL problems derived. Do not filter or limit to only the top 3.
3.  Always retain the exact original spelling and capitalisation of each feature or benefit title when generating the derived problem title. Never alter the capitalisation, wording, or punctuation of the title field values.

B) Output Structured Report Fields (for use in Stage 2)
Compile the following:
a. Full Problem Table: for each problem, return:
- Title (short label for the problem)
- Problem
- Category (Feature/Benefit)
- Pain
- Urgency
- Score
For each derived problem, retain and output the original title field from the corresponding feature or benefit it was derived from, using all lowercase field names (e.g., title, problem, category, pain, urgency, score) but preserve the original capitalisation of the field values.

Deliver all outputs in a single JSON object with structured sections for:
•   "prioritised_problems"

Do not explain your process—only return the structured data. Use UK English throughout. Avoid all US spelling (e.g. use ‘realise’, not ‘realize’; ‘organisation’, not ‘organization’).

"""

PROMPT_ELEMENTS = """

You are an AI expert at developing problem-centric reasoning to help businesses shift from product-led to problem-led thinking. Your task is to analyse a predefined data on a product, its features, benefits, and customer context, and return structured outputs across multiple stages of logic. Follow these steps precisely and return all outputs in JSON format:
A) Break Down Problem Elements (for use in Stage 2)
For each of the top 3 problems, generate values for the following elements:
o   Problem Name (2–3 word label)
o   Person or Group affected
o   Underlying Problem (trigger or scenario)
o   Impact (what occurs as a result)
o   Pain Caused (the emotional or operational toll)
o   Circumstance (when/where/how often)
o   Consequences Unaddressed
o   Risk Unaddressed
o   Benefit Created (hybrid of original or new benefit)
o   Opportunity Created (industry/customer advantage)
Ensure each field builds cumulatively for a logically sound narrative.

B) Output Structured Report Fields (for use in Stage 2)
Compile the following:
a. Problem Elements Table: 10 categories × 3 problems
Deliver all outputs in a single JSON object with structured sections for:
•   "problem_elements"
Do not explain your process—only return the structured data. Use UK English throughout. Avoid all US spelling (e.g. use ‘realise’, not ‘realize’; ‘organisation’, not ‘organization’).

"""

PROMPT_STATEMENTS = """

You are an AI expert at developing problem-centric reasoning to help businesses shift from product-led to problem-led thinking. Your task is to analyse a predefined data on a product, its features, benefits, and customer context, and return structured outputs across multiple stages of logic. Follow these steps precisely and return all outputs in JSON format:
A) Generate Problem Statements (for use in Stage 2)
For each of the top 3 prioritised problems, generate a single, clear problem statement using the following logic and structure:
a. Review all problem element fields generated in above for each of the 3 top problems. These include:
Problem Name, Person or Group, Underlying Problem, Impact, Pain Caused, Circumstance, Consequences Unaddressed, Risk Unaddressed, Benefit Created, Opportunity Created.
b. Select the most compelling 3–4 elements that together form a coherent, emotionally resonant summary of the problem. These should:
•   Be cumulatively linked
•   Reflect the depth and consequence of the issue
•   Capture the stakeholder’s lived experience
c. Avoid fixed templates. Each problem statement should be written as a natural, flowing paragraph in everyday language. It should read like something a smart business stakeholder could say to a team or customer.
d. Start the statement with the core tension or pain—not with “The issue is…” or “The problem is…”. Use emotive phrasing (e.g., “Significant errors…”, “Escalating demand…”).
e. If a specific stakeholder (Person or Group) is clearly affected, reference them directly in the sentence (e.g., “For customer service teams…”). If not, omit it to maintain clarity.
f. Avoid capitalising words mid-sentence (e.g., “with Existing workload”) unless part of a proper noun.
g. Only include an “If addressed” as a follow-on clause at the end of the problem statement if all three of the following conditions are met:
•   The Opportunity Created or Benefit Created or Risk field from point 4 above is clear, specific, and meaningful in the context of the problem.
•   The clause adds clarity, contrast, or consequence to the statement—i.e., it helps the user better understand why solving this matters.
•   The main body of the problem statement is not already benefit-oriented or forward-looking (to avoid repetition).
If these conditions are met, append a short phrase beginning with:
•   “...freeing up...”
•   “...allowing for...”
•   “...leading to...”
•   “...enabling...”
•   “...avoiding...”
Do not include the clause if the benefit or opportunity or risk is vague, or if the problem statement is already strong without it.
h. Ensure the output is focused on the problem—do not suggest fixes, describe solutions, or shift toward benefit statements. Keep the tone diagnostic, not prescriptive.

B) Output Structured Report Fields (for use in Stage 2)
Compile the following:
a. Final Problem Statements
b. GPT-generated Recommendations (brief paragraph + 2–3 actionable bullets)
Deliver all outputs in a single JSON object with structured sections for:
•   "problem_statements"
•   "report_summary"
Do not explain your process—only return the structured data. Use UK English throughout. Avoid all US spelling (e.g. use ‘realise’, not ‘realize’; ‘organisation’, not ‘organization’).

"""

PROMPT_PITCHES = """

You are an AI expert at developing problem-centric reasoning to help businesses shift from product-led to problem-led thinking. Your task is to analyse a product’s features, benefits, and customer context, and write clear, human-sounding elevator pitches that explain how the product addresses three validated customer problems.

Each pitch must draw solely from the original product input — do not invent new features or solutions. These pitches are intended to help the team explain the product’s value clearly to external stakeholders.

Follow these instructions precisely and return your output in JSON format:

A) Generate Elevator Pitch Statements (for use in Stage 2)
1. You are provided with problem element breakdowns for three top problems. Each one includes:
- Problem Name
- Person or Group Affected
- Underlying Problem
- Impact
- Pain Caused
- Circumstance
- Consequences Unaddressed
- Risk Unaddressed
- Benefit Created
- Opportunity Created
2. For each problem, write a natural-sounding elevator pitch that clearly shows how the original product addresses that problem. Use your understanding of the original product’s features, benefits, and context. You may refer to multiple features or benefits if needed — but do not invent or assume functionality that wasn’t provided.
3. The tone should be clear, persuasive and executive-level — similar to how a CEO or product lead would describe the product’s relevance to a specific problem. Avoid buzzwords or overused phrases. Use natural, fluent English that builds business credibility.
4. Mention the product name or feature/benefit titles only if doing so strengthens clarity or flow. Otherwise, keep the language principle-led and context-aware.
5. Each pitch should be 1–2 sentences. It must make sense as a standalone explanation, without needing a heading. Do not repeat the problem; focus on how the product responds to it.
6. After writing each pitch paragraph, derive a short 2–3 word heading that captures the core idea or theme of the pitch. This heading should:
- Summarise the pitch in plain, non-technical language
- Be suitable as a section label for the pitch
- Avoid repeating the problem name directly

B) Output Structured Report Fields (for use in Stage 2)
Compile the following:
a. Final Pitch Paragraphs (one per priority problem)

Deliver all outputs in a single JSON object with structured sections for:
•  "pitch_statements"
•  "pitch_titles"

Do not explain your process—only return the structured data. Use UK English throughout. Avoid all US spelling (e.g. use ‘realise’, not ‘realize’; ‘organisation’, not ‘organization’).

"""

PROMPT_RECOMMENDATIONS = """
You are an AI product strategy expert. Your task is to analyse the top three customer problems and their detailed breakdowns to generate clear, actionable recommendations across five fixed categories.

Use ONLY the existing data provided — do not invent new features, benefits or user types. If a category has no relevant concern, explicitly state that no action is currently needed.

Use UK English throughout. Avoid US spelling (e.g. ‘realise’, not ‘realize’).

For each category, return either:
- 1–2 short, specific recommendations, OR
- A message such as “No concerns found” or “No action needed”.

The five recommendation categories are:

1. **Validate** – Where and how should the top problems be tested or verified with customers?
2. **Refine** – Are any features or benefits misaligned with deeper customer problems?
3. **Prioritise** – Which problems or features deserve immediate attention based on urgency and pain?
4. **Align** – What messaging or internal comms could improve team understanding or customer-facing clarity?
5. **Extend** – Are there meaningful gaps in product coverage that warrant attention or future discovery?

Return your response in this JSON structure:

```json
{
  "report_summary": {
    "validate": "string",
    "refine": "string",
    "prioritise": "string",
    "align": "string",
    "extend": "string"
  }
}

Do not include commentary, intro text, or additional explanation. Only return the JSON block above.
"""

def format_metadata_block(product_name, product_summary, customer_desc, industry, challenges):
    return f"""Product Name: {product_name}
Product Summary: {product_summary}
Customer Description: {customer_desc}
Industry: {industry}
Challenges: {challenges}
"""

def extract_prompt_inputs(data):
    return {
        "product_name": data.get("product_name", ""),
        "product_summary": data.get("product_summary", ""),
        "features": data.get("features", []),
        "benefits": data.get("benefits", []),
        "customer_desc": data.get("customer_context", {}).get("description", ""),
        "industry": data.get("customer_context", {}).get("industry", ""),
        "challenges": data.get("customer_context", {}).get("challenges", "")
    }

def format_feature_text(features):
    return "\n".join(f"- Title: {f['title']} | Detail: {f['detail']}" for f in features)

def format_benefit_text(benefits):
    return "\n".join(f"- Title: {b['title']} | Detail: {b['detail']}" for b in benefits)


app = Flask(__name__)
CORS(app)


@app.route("/")
def index():
    return render_template("fx1_stage1.html")

@app.route("/fx1_stage1")
def fx1_stage1():
    return render_template("fx1_stage1.html")

@app.route("/fx1_stage2")
def fx1_stage2():
    return render_template("fx1_stage2.html")


def build_prompt_for_url_extract(text):
    instruction_block = PROMPT_URL_EXTRACT
    return f"{instruction_block}\n\n{text.strip()}"


@app.route("/fx1/url-extract", methods=["POST"])
def extract_from_url():
    try:
        data = request.get_json()
        url = data.get("url", "").strip()
        if not url or not url.startswith("http"):
            return jsonify({"error": "Invalid or missing URL"}), 400

        print("🌐 Fetching URL:", url)
        # ⛓️ Pull page content
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-GB,en;q=0.9",
            "Referer": "https://www.google.com/"
        }
        response = requests.get(url, headers=headers, timeout=8)

        print(f"📡 URL fetch returned status: {response.status_code}")
        print(f"📄 Response preview (first 300 chars): {response.text[:300]}")

        if response.status_code != 200:
            return jsonify({"error": "Failed to retrieve content"}), 500

        html = response.text  # raw HTML, fully intact

        # ──────────────────────────────────────────────────────────────────────────
        # Call ChatGPT via function-calling to ensure _only_ JSON is returned
        chat_resp = openai.ChatCompletion.create(
            model="gpt-4o",                        # or your top-preferred GPT model
            messages=[
                {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                {"role":   "user", "content": html}
            ],
            functions=[ URL_EXTRACT_FUNCTION ],
            function_call={ "name": "url_extract" },
            temperature=0.4
        )
        # Extract the JSON arguments from the function call
        args_json = chat_resp.choices[0].message.function_call.arguments
        result    = json.loads(args_json)
        return jsonify(result)
        # ──────────────────────────────────────────────────────────────────────────

        return jsonify(parsed)

    except Exception as e:
        import traceback
        print("❌ URL extract error:", e)
        traceback.print_exc()
        return jsonify({"error": "Unexpected server error"}), 500


def build_prompt_for_problem_derivation(data, task):
    product_name = data.get("product_name", "")
    product_summary = data.get("product_summary", "")
    customer_desc = data.get("customer_context", {}).get("description", "")
    industry = data.get("customer_context", {}).get("industry", "")
    challenges = data.get("customer_context", {}).get("challenges", "")
    features = data.get("features", [])
    benefits = data.get("benefits", [])

    meta = format_metadata_block(
        product_name,
        product_summary,
        customer_desc,
        industry,
        challenges
    )

    features_text = format_feature_text(features)
    benefits_text = format_benefit_text(benefits)

    instruction_block = PROMPT_PROBLEM_DERIVATION
    return f"{instruction_block}\n\n{meta}\n\n{features_text}\n\n{benefits_text}"

@app.route("/fx1/problem-derivation", methods=["POST"])
def derive_problems():
    data = request.get_json()
    print("📥 Incoming data (/fx1/problem-derivation):", data, file=sys.stderr)
    prompt = build_prompt_for_problem_derivation(data, task="derive underlying problems only")
    print("🧾 Prompt sent to GPT (/fx1/problem-derivation):", prompt, file=sys.stderr)

    response = query_gpt(prompt)

    if not data.get("features") and not data.get("benefits"):
        return jsonify({ "error": "At least one feature or benefit is required." }), 400

    try:
        parsed = response  # because query_gpt(prompt) already returns the parsed object
        return jsonify({
            "features": parsed.get("features", []),
            "benefits": parsed.get("benefits", [])
        })

    except Exception as e:
        print("❌ GPT error:", e, file=sys.stderr)
        traceback.print_exc()
        return jsonify({ "error": "Derivation failed", "details": str(e) }), 500


def build_prompt_for_problems(data):
    product_name = data.get("product_name", "")
    product_summary = data.get("product_summary", "")
    customer_desc = data.get("customer_context", {}).get("description", "")
    industry = data.get("customer_context", {}).get("industry", "")
    challenges = data.get("customer_context", {}).get("challenges", "")
    features = data.get("features", [])
    benefits = data.get("benefits", [])

    meta = format_metadata_block(
        product_name,
        product_summary,
        customer_desc,
        industry,
        challenges
    )
    features_text = format_feature_text(data.get("features", []))
    benefits_text = format_feature_text(data.get("benefits", []))

    return f"{PROMPT_PROBLEMS}\n\n{meta}\n\n{features_text}\n\n{benefits_text}"

@app.route("/fx1/problems", methods=["POST"])
def analyse_problems():
    data = request.get_json()
    print("📥 Incoming data (/fx1/problems):", data, file=sys.stderr)
    prompt = build_prompt_for_problems(data)
    print("🧾 Prompt sent to GPT (/fx1/problems):", prompt, file=sys.stderr)

    response = query_gpt(prompt)

    # Ensure response is a dict
    if hasattr(response, "to_dict"):
        response = response.to_dict()

    # Safely extract features and benefits
    features = response.get("features", [])
    benefits = response.get("benefits", [])

    # If features or benefits still missing, fallback to raw 'data'
    if not features:
        features = data.get("features", [])
    if not benefits:
        benefits = data.get("benefits", [])

    # Attach titles if missing
    for i, feature in enumerate(features):
        if "title" not in feature and i < len(data.get("features", [])):
            feature["title"] = data["features"][i].get("title", "")

    for i, benefit in enumerate(benefits):
        if "title" not in benefit and i < len(data.get("benefits", [])):
            benefit["title"] = data["benefits"][i].get("title", "")

    try:
        # Parse raw string into structured list of dicts
        parsed = json.loads(response) if isinstance(response, str) else response

        # Get full_problem_table safely
        problem_table = parsed.get("prioritised_problems", [])

        # Filter and extract directly what you need
        cleaned = [
            {
                "title": item.get("title", ""),
                "category": item.get("category", ""),
                "problem": item.get("problem", ""),
                "pain": item.get("pain", ""),
                "urgency": item.get("urgency", ""),
                "score": item.get("score", None)
            }
            for item in problem_table
            if isinstance(item, dict)
        ]

        # Split into features and benefits for front-end rendering
        features = [item for item in cleaned if item["category"].lower() == "feature"]
        benefits = [item for item in cleaned if item["category"].lower() == "benefit"]

        return jsonify({
            "features": features,
            "benefits": benefits
        })

    except Exception as e:
        print("❌ GPT error:", e, file=sys.stderr)
        traceback.print_exc()
        return jsonify({ "error": "Problem scoring failed", "details": str(e) }), 500


def build_prompt_for_elements(data):
    product_name = data.get("product_name", "")
    product_summary = data.get("product_summary", "")
    customer_desc = data.get("customer_context", {}).get("description", "")
    industry = data.get("customer_context", {}).get("industry", "")
    challenges = data.get("customer_context", {}).get("challenges", "")
    features = data.get("features", [])
    benefits = data.get("benefits", [])

    meta = format_metadata_block(
        product_name,
        product_summary,
        customer_desc,
        industry,
        challenges
    )

    features_text = format_feature_text(features)
    benefits_text = format_benefit_text(benefits)

    return f"{PROMPT_ELEMENTS}\n\n{meta}\n\n{features_text}\n\n{benefits_text}"

@app.route("/fx1/elements", methods=["POST"])
def analyse_elements():
    data = request.get_json()
    print("📥 Incoming data (/fx1/elements):", data, file=sys.stderr)
    prompt = build_prompt_for_elements(data)
    print("🧾 Prompt sent to GPT (/fx1/elements):", prompt, file=sys.stderr)

    response = query_gpt(prompt)
    if not data.get("features") and not data.get("benefits"):
        return jsonify({ "error": "At least one feature or benefit is required." }), 400

    try:
        parsed = response  # because query_gpt(prompt) already returns the parsed object
        return jsonify({
            "problem_elements": parsed.get("problem_elements", [])
        })
    except Exception as e:
        print("❌ GPT error:", e, file=sys.stderr)
        traceback.print_exc()
        return jsonify({ "error": "Element extraction failed", "details": str(e) }), 500


def build_prompt_for_statements(data):
    product_name = data.get("product_name", "")
    product_summary = data.get("product_summary", "")
    customer_desc = data.get("customer_context", {}).get("description", "")
    industry = data.get("customer_context", {}).get("industry", "")
    challenges = data.get("customer_context", {}).get("challenges", "")
    features = data.get("features", [])
    benefits = data.get("benefits", [])

    meta = format_metadata_block(
        product_name,
        product_summary,
        customer_desc,
        industry,
        challenges
    )

    features_text = format_feature_text(features)
    benefits_text = format_benefit_text(benefits)

    return f"{PROMPT_STATEMENTS}\n\n{meta}\n\n{features_text}\n\n{benefits_text}"

@app.route("/fx1/statements", methods=["POST"])
def analyse_statements():
    data = request.get_json()
    print("📩 Incoming data (/fx1/statements):", data, file=sys.stderr)
    prompt = build_prompt_for_statements(data)
    print("🧾 Prompt sent to GPT (/fx1/statements):", prompt, file=sys.stderr)

    if not data.get("features") and not data.get("benefits"):
        return jsonify({ "error": "At least one feature or benefit is required." }), 400

    try:
        response = query_gpt(prompt)
        parsed = response  # because query_gpt(prompt) already returns the parsed object

        from ast import literal_eval
        statements_raw = parsed.get("problem_statements", [])
        cleaned_statements = []

        for s in statements_raw:
            try:
                cleaned_statements.append(literal_eval(str(s)))
            except:
                cleaned_statements.append(str(s))

        result = {
            "statements": cleaned_statements,
            "titles": [f"Problem {i+1}" for i in range(len(cleaned_statements))]
        }

        return jsonify(result)

    except Exception as e:
        print("❌ GPT error:", e, file=sys.stderr)
        traceback.print_exc()
        return jsonify({ "error": "Statement generation failed", "details": str(e) }), 500

def build_prompt_for_pitches(data):
    product_name = data.get("product_name", "")
    product_summary = data.get("product_summary", "")
    customer_desc = data.get("customer_context", {}).get("description", "")
    industry = data.get("customer_context", {}).get("industry", "")
    challenges = data.get("customer_context", {}).get("challenges", "")
    problems = data.get("problem_elements", [])

    def format_problem_elements(problem):
        return f"""Problem Name: {problem.get("Problem Name", "")}
        Person or Group: {problem.get("Person or Group affected", "")}
        Underlying Problem: {problem.get("Underlying Problem", "")}
        Impact: {problem.get("Impact", "")}
        Pain Caused: {problem.get("Pain Caused", "")}
        Circumstance: {problem.get("Circumstance", "")}
        Consequences Unaddressed: {problem.get("Consequences Unaddressed", "")}
        Risk Unaddressed: {problem.get("Risk Unaddressed", "")}
        Benefit Created: {problem.get("Benefit Created", "")}
        Opportunity Created: {problem.get("Opportunity Created", "")}
        """

    problems_text = "\n\n".join([format_problem_elements(p) for p in problems])

    meta = format_metadata_block(
        product_name,
        product_summary,
        customer_desc,
        industry,
        challenges
    )

    instruction_block = PROMPT_PITCHES

    return f"{instruction_block}\n\n{meta}\n\n{problems_text}"

@app.route("/fx1/elevator", methods=["POST"])
def generate_elevator_pitches():
    data = request.get_json()
    print("📨 Incoming data (/fx1/elevator):", data, file=sys.stderr)

    prompt = build_prompt_for_pitches(data)

    try:
        response = query_gpt(prompt)
        parsed = response  # response is already a dict-like AttributedDict

        import json
        try:
            parsed = response
            pitch_statements = parsed.get("pitch_statements", [])
            pitch_titles = parsed.get("pitch_titles", []) 

            return jsonify(content={
                "pitch_statements": pitch_statements,
                "elevator_titles": [t or f"Pitch {i+1}" for i, t in enumerate(pitch_titles)],
                "elevator_pitches": [{"heading": pitch_titles[i], "text": p} for i, p in enumerate(pitch_statements)],
            })

        except Exception as e:
            print("❌ JSON parse failed in /fx1/elevator:", e)
            import traceback
            traceback.print_exc()
            return jsonify(content={
                "pitch_statements": [],
                "elevator_titles": []
            })

    except Exception as e:
        print("❌ Error in /fx1/elevator:", e, file=sys.stderr)
        return jsonify({"error": str(e)}), 500


def build_prompt_for_recommendations(data):
    product_name = data.get("product_name", "")
    product_summary = data.get("product_summary", "")
    customer_context = data.get("customer_context", {})
    features = data.get("features", [])
    benefits = data.get("benefits", [])
    problem_elements = data.get("problem_elements", [])

    customer_desc = customer_context.get("description", "")
    industry = customer_context.get("industry", "")
    challenges = customer_context.get("challenges", "")

    meta = format_metadata_block(product_name, product_summary, customer_desc, industry, challenges)
    features_text = format_feature_text(features)
    benefits_text = format_benefit_text(benefits)

    elements_text = json.dumps(problem_elements, indent=2) if isinstance(problem_elements, list) else str(problem_elements)

    return f"""{PROMPT_RECOMMENDATIONS}

{meta}

Features:
{features_text}

Benefits:
{benefits_text}

Problem Elements (Top 3):
{elements_text}
"""

@app.route("/fx1/recommendations", methods=["POST"])
def analyse_recommendations():
    data = request.get_json()
    print("📥 Incoming data (/fx1/recommendations):", data, file=sys.stderr)

    try:
        prompt = build_prompt_for_recommendations(data)
        print("🧾 Prompt sent to GPT (/fx1/recommendations):", prompt, file=sys.stderr)

        response = query_gpt(prompt)

        if isinstance(response, str):
            parsed = json.loads(response)
        else:
            parsed = response

        return jsonify(parsed)

    except Exception as e:
        print("❌ Recommendation generation error:", e, file=sys.stderr)
        traceback.print_exc()
        return jsonify({ "error": "Recommendation generation failed", "details": str(e) }), 500


@app.route("/")
def home_redirect():
    return render_template("fx1_stage1.html")


if __name__ == "__main__":
    print("✅ Flask is launching...")
    app.run(host="0.0.0.0", port=5010, debug=True)
