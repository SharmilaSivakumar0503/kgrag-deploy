import os
import requests
import streamlit as st
API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")

st.set_page_config(
    page_title="Agriculture Scheme Assistant",
    page_icon="🌱"
)


st.title(
    "🌱 Agriculture Scheme Assistant"
)

st.write(
    "Ask questions about the agriculture schemes "
    "in the provided document."
)


question = st.text_input(
    "Ask your question"
)


if st.button("Ask"):

    if not question:

        st.warning(
            "Please enter a question."
        )

    else:

        try:

            response = requests.post(
                  f"{API_URL}/ask",
                     json={"question": question}
            )
            result = response.json()


            st.subheader("Answer")

            st.write(
                result["answer"]
            )


            if result["sources"]:

                st.subheader(
                    "Sources"
                )

                for source in result["sources"]:

                    st.write(
                        f"**{source['scheme']}** "
                        f"— PDF page(s): "
                        f"{source['pages']}"
                    )


        except Exception as error:

            st.error(
                f"Could not connect to API: {error}"
            )