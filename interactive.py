# interactive.py
from output_handler import save_responses_to_excel
import shlex
import subprocess
import re
import requests

# ------------------------------
# Configuration
# ------------------------------
SERPAPI_API_KEY = "c4c32ac751923eafd8d867eeb14c433e245aebfdbc0261cb2a8357e08ca34ff0"  # for web search

# Regex to strip ANSI codes from Ollama
ANSI_ESCAPE = re.compile(r'(?:\x1B[@-_][0-?]*[ -/]*[@-~])')

def clean_ollama_output(text):
    return ANSI_ESCAPE.sub("", text).strip()

# ------------------------------
# Query PubMed
# ------------------------------
def fetch_pubmed_study(pmid):
    """
    Fetch study info from PubMed for a given PMID.
    Returns dict: title, authors, journal, abstract, publication_date
    """
    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {
        "db": "pubmed",
        "id": pmid,
        "retmode": "xml"
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        return {"error": str(e)}

    import xml.etree.ElementTree as ET
    root = ET.fromstring(resp.text)

    article = root.find(".//PubmedArticle")
    if article is None:
        return {"error": "No article found"}

    title = article.findtext(".//ArticleTitle", default="N/A")
    abstract = "".join([t.text or "" for t in article.findall(".//AbstractText")])
    journal = article.findtext(".//Journal/Title", default="N/A")
    pub_date = article.findtext(".//PubDate/Year", default="N/A")
    authors = []
    for author in article.findall(".//Author"):
        last = author.findtext("LastName")
        first = author.findtext("ForeName")
        if last and first:
            authors.append(f"{first} {last}")
    return {
        "pmid": pmid,
        "title": title,
        "authors": authors,
        "journal": journal,
        "abstract": abstract,
        "publication_date": pub_date
    }

# ------------------------------
# Query SerpAPI (Google search)
# ------------------------------
def search_web(query, num_results=5):
    from serpapi import GoogleSearch
    params = {
        "engine": "google",
        "q": query,
        "api_key": SERPAPI_API_KEY,
        "num": num_results
    }
    search = GoogleSearch(params)
    results = search.get_dict().get("organic_results", [])
    snippets = [res.get("snippet", "") for res in results if "snippet" in res]
    return "\n".join(snippets)

# ------------------------------
# Send query to local Ollama
# ------------------------------
def query_ollama(model, prompt):
    safe_model = shlex.quote(model)
    cmd = f'zsh -l -c "ollama run {safe_model}"'
    process = subprocess.Popen(
        cmd, shell=True, stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    stdout, stderr = process.communicate(prompt + "\n")
    output = stdout or stderr
    return clean_ollama_output(output)

# ------------------------------
# Interactive session
# ------------------------------
# ------------------------------
# Interactive session
# ------------------------------
def interactive_session(ssh_client=None, model_name=None, study_info=None):
    print(f"\nStarting interactive LLM session (type 'exit' to quit)...\n")
    conversation = []

    try:
        while True:
            prompt = input("Enter prompt (PubMed ID, NCT ID, 'web:' for search, or text): ").strip()
            if prompt.lower() == 'exit':
                break
            if not prompt:
                continue

            final_prompt = prompt

            # If user enters a PubMed ID (digits only)
            if prompt.isdigit():
                study_info = fetch_pubmed_study(prompt)
                if "error" in study_info:
                    print(f"Error fetching study info: {study_info['error']}")
                    continue
                print(f"\n[PubMed Study Info]:\n{study_info}\n")
                final_prompt = f"Summarize the following PubMed study:\n\n{study_info}"

            # If user enters an NCT ID
            elif prompt.upper().startswith("NCT") and prompt[3:].isdigit():
                nct_id = prompt.upper()
                print(f"\n[INFO] Searching web for ClinicalTrial {nct_id}")
                search_results = search_web(nct_id)
                if not search_results:
                    search_results = "No recent results found."
                print(f"\n[Search Results]:\n{search_results}\n")
                final_prompt = f"Summarize the following clinical trial information for {nct_id}:\n\n{search_results}"

            # If user wants web search
            elif prompt.lower().startswith("web:"):
                query = prompt[4:].strip()
                print(f"\n[INFO] Searching web for: {query}")
                search_results = search_web(query)
                if not search_results:
                    search_results = "No recent results found."
                final_prompt = f"You are a helpful assistant. A user asked: {query}\n\nSearch results:\n{search_results}"

            # Send to Ollama (via SSH if needed)
            if ssh_client and model_name:
                from llm_utils import run_ollama as remote_ollama
                response = remote_ollama(ssh_client, model_name, final_prompt)
            else:
                response = query_ollama(model_name, final_prompt)

            print(f"\nResponse:\n{response}\n")
            conversation.append((prompt, response))

    except KeyboardInterrupt:
        print("\nSession interrupted by user.")
    finally:
        if conversation:
            save_format = None
            while save_format not in ('csv', 'xlsx', 'exit'):
                save_format = input("Save conversation as (csv/xlsx) or 'exit' to skip saving: ").strip().lower()

            if save_format == 'csv':
                path = input("Enter CSV file path: ").strip()
                save_responses_to_excel(conversation, path, csv_mode=True)
                print(f"Conversation saved to {path}")
            elif save_format == 'xlsx':
                path = input("Enter Excel file path: ").strip()
                save_responses_to_excel(conversation, path, csv_mode=False)
                print(f"Conversation saved to {path}")
            else:
                print("Conversation not saved.")
