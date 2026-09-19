import os
import json

from dotenv import load_dotenv
from neo4j import GraphDatabase
from openai import OpenAI


load_dotenv()


driver = GraphDatabase.driver(
    os.getenv("NEO4J_URI"),
    auth=(
        os.getenv("NEO4J_USERNAME"),
        os.getenv("NEO4J_PASSWORD")
    )
)

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)


def extract_search_terms(question):

    prompt = f"""
Extract search terms from this agriculture question.

Return ONLY valid JSON:

{{
    "keywords": [],
    "crops": [],
    "districts": []
}}

Question:
{question}
"""

    response = client.responses.create(
        model="gpt-5-mini",
        input=prompt
    )

    result = response.output_text.strip()

    if result.startswith("```"):
        result = result.replace("```json", "")
        result = result.replace("```", "")
        result = result.strip()

    return json.loads(result)


def retrieve_from_neo4j(question):

    terms = extract_search_terms(
        question
    )

    keywords = terms.get(
        "keywords",
        []
    )

    crops = terms.get(
        "crops",
        []
    )

    districts = terms.get(
        "districts",
        []
    )


    query = """
    MATCH (s:Scheme)

    OPTIONAL MATCH
        (s)-[:PROVIDES]->(b:Benefit)

    OPTIONAL MATCH
        (s)-[:HAS_ELIGIBILITY]->(e:Eligibility)

    OPTIONAL MATCH
        (s)-[:APPLIES_TO]->(c:Crop)

    OPTIONAL MATCH
        (s)-[:AVAILABLE_IN]->(d:District)

    OPTIONAL MATCH
        (s)-[:CONTACT]->(o:Officer)

    OPTIONAL MATCH
        (s)-[:MENTIONED_ON]->(p:PDFPage)

    WITH s,
         collect(DISTINCT b.description) AS benefits,
         collect(DISTINCT b.amount) AS amounts,
         collect(DISTINCT e.description) AS eligibility,
         collect(DISTINCT c.name) AS crops,
         collect(DISTINCT d.name) AS districts,
         collect(DISTINCT o.name) AS officers,
         collect(DISTINCT p.page) AS pages

    WITH s,
         benefits,
         amounts,
         eligibility,
         crops,
         districts,
         officers,
         pages,

         size([
             x IN $keywords
             WHERE toLower(s.name) CONTAINS toLower(x)
                OR any(b IN benefits
                    WHERE toLower(b) CONTAINS toLower(x))
                OR any(e IN eligibility
                    WHERE toLower(e) CONTAINS toLower(x))
         ]) AS keyword_score,

         size([
             x IN $crops
             WHERE any(c IN crops
                 WHERE toLower(c) CONTAINS toLower(x))
         ]) AS crop_score,

         size([
             x IN $districts
             WHERE any(d IN districts
                 WHERE toLower(d) CONTAINS toLower(x))
         ]) AS district_score

    WITH s,
         benefits,
         amounts,
         eligibility,
         crops,
         districts,
         officers,
         pages,

         keyword_score +
         crop_score +
         district_score AS score

    WHERE score > 0

    RETURN
        s.name AS scheme,
        benefits,
        amounts,
        eligibility,
        crops,
        districts,
        officers,
        pages,
        score

    ORDER BY score DESC

    LIMIT 10
    """


    with driver.session() as session:

        result = session.run(
            query,
            keywords=keywords,
            crops=crops,
            districts=districts
        )

        return [
            record.data()
            for record in result
        ]


def generate_answer(
    question,
    graph_results
):

    context = ""

    for item in graph_results:

        context += f"""
SCHEME:
{item['scheme']}

BENEFITS:
{item['benefits']}

AMOUNTS:
{item['amounts']}

ELIGIBILITY:
{item['eligibility']}

CROPS:
{item['crops']}

DISTRICTS:
{item['districts']}

OFFICERS:
{item['officers']}

SOURCE PDF PAGES:
{item['pages']}

--------------------------------
"""


    prompt = f"""
You are an agriculture scheme assistant.

Answer the user's question using ONLY the
Knowledge Graph information below.

Do not invent information.

If the information is not available,
say that it is not available in the document.

Always mention the relevant PDF page number
when available.

Knowledge Graph:
{context}

Question:
{question}
"""

    response = client.responses.create(
        model="gpt-5-mini",
        input=prompt
    )

    return response.output_text


def ask(question):

    graph_results = retrieve_from_neo4j(
        question
    )

    if not graph_results:

        return {
            "answer": "No relevant information found in the document.",
            "sources": []
        }


    answer = generate_answer(
        question,
        graph_results
    )


    sources = []

    for item in graph_results:

        sources.append({
            "scheme": item["scheme"],
            "pages": item["pages"]
        })


    return {
        "answer": answer,
        "sources": sources
    }