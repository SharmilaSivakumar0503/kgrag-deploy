import os
import json

from pypdf import PdfReader
from dotenv import load_dotenv
from neo4j import GraphDatabase
from openai import OpenAI


load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


driver = GraphDatabase.driver(
    NEO4J_URI,
    auth=(NEO4J_USERNAME, NEO4J_PASSWORD)
)

client = OpenAI(api_key=OPENAI_API_KEY)


PDF_FILE = "Agriculture.pdf"


def read_pdf():

    reader = PdfReader(PDF_FILE)

    pages = []

    for page_number, page in enumerate(
        reader.pages,
        start=1
    ):

        text = page.extract_text()

        if text and text.strip():

            pages.append({
                "page": page_number,
                "text": text.strip()
            })

    return pages


def extract_knowledge(text, page_number):

    prompt = f"""
Extract structured information from this agriculture
government document.

Return ONLY valid JSON.

Structure:

{{
    "schemes": [
        {{
            "name": "",
            "benefits": [
                {{
                    "description": "",
                    "amount": "",
                    "crop": ""
                }}
            ],
            "eligibility": [],
            "districts": [],
            "crops": [],
            "officers": []
        }}
    ]
}}

Rules:

1. Extract only information explicitly present.
2. Do not invent information.
3. Preserve subsidy amounts and percentages.
4. Preserve district names.
5. Preserve officer names.
6. If information is unavailable, use [].
7. Multiple schemes may occur on one page.

PAGE:
{page_number}

TEXT:
{text}
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


def save_to_neo4j(
    tx,
    knowledge,
    page_number,
    page_text
):

    # --------------------------------
    # Store PDF page
    # --------------------------------

    tx.run(
        """
        MERGE (p:PDFPage {page: $page})

        SET p.text = $text
        """,
        page=page_number,
        text=page_text
    )


    for scheme in knowledge.get(
        "schemes",
        []
    ):

        scheme_name = scheme.get(
            "name",
            ""
        ).strip()

        if not scheme_name:
            continue


        # --------------------------------
        # Scheme
        # --------------------------------

        tx.run(
            """
            MERGE (s:Scheme {
                name: $name
            })

            MERGE (d:Department {
                name: "Agriculture Department"
            })

            MERGE (s)-[:UNDER_DEPARTMENT]->(d)

            MATCH (p:PDFPage {
                page: $page
            })

            MERGE (s)-[:MENTIONED_ON]->(p)
            """,
            name=scheme_name,
            page=page_number
        )


        # --------------------------------
        # Benefits
        # --------------------------------

        for benefit in scheme.get(
            "benefits",
            []
        ):

            description = benefit.get(
                "description",
                ""
            ).strip()

            amount = benefit.get(
                "amount",
                ""
            ).strip()

            if not description:
                continue

            tx.run(
                """
                MATCH (s:Scheme {
                    name: $scheme
                })

                MERGE (b:Benefit {
                    description: $description,
                    scheme: $scheme
                })

                SET b.amount = $amount

                MERGE (s)-[:PROVIDES]->(b)
                """,
                scheme=scheme_name,
                description=description,
                amount=amount
            )


        # --------------------------------
        # Eligibility
        # --------------------------------

        for value in scheme.get(
            "eligibility",
            []
        ):

            value = value.strip()

            if not value:
                continue

            tx.run(
                """
                MATCH (s:Scheme {
                    name: $scheme
                })

                MERGE (e:Eligibility {
                    description: $description
                })

                MERGE (s)-[:HAS_ELIGIBILITY]->(e)
                """,
                scheme=scheme_name,
                description=value
            )


        # --------------------------------
        # Crops
        # --------------------------------

        for crop in scheme.get(
            "crops",
            []
        ):

            crop = crop.strip()

            if not crop:
                continue

            tx.run(
                """
                MATCH (s:Scheme {
                    name: $scheme
                })

                MERGE (c:Crop {
                    name: $crop
                })

                MERGE (s)-[:APPLIES_TO]->(c)
                """,
                scheme=scheme_name,
                crop=crop
            )


        # --------------------------------
        # Districts
        # --------------------------------

        for district in scheme.get(
            "districts",
            []
        ):

            district = district.strip()

            if not district:
                continue

            tx.run(
                """
                MATCH (s:Scheme {
                    name: $scheme
                })

                MERGE (d:District {
                    name: $district
                })

                MERGE (s)-[:AVAILABLE_IN]->(d)
                """,
                scheme=scheme_name,
                district=district
            )


        # --------------------------------
        # Officers
        # --------------------------------

        for officer in scheme.get(
            "officers",
            []
        ):

            officer = officer.strip()

            if not officer:
                continue

            tx.run(
                """
                MATCH (s:Scheme {
                    name: $scheme
                })

                MERGE (o:Officer {
                    name: $officer
                })

                MERGE (s)-[:CONTACT]->(o)
                """,
                scheme=scheme_name,
                officer=officer
            )


def main():

    print("Reading PDF...")

    pages = read_pdf()

    print(
        f"Found {len(pages)} pages."
    )

    with driver.session() as session:

        for item in pages:

            page = item["page"]
            text = item["text"]

            print(
                f"Processing page {page}..."
            )

            try:

                knowledge = extract_knowledge(
                    text,
                    page
                )

                session.execute_write(
                    save_to_neo4j,
                    knowledge,
                    page,
                    text
                )

                print(
                    f"Page {page} completed."
                )

            except Exception as error:

                print(
                    f"Page {page} failed: {error}"
                )

    driver.close()

    print(
        "\nKnowledge Graph ingestion completed."
    )


if __name__ == "__main__":
    main()