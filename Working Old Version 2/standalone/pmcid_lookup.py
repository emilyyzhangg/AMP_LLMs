import requests
import xml.etree.ElementTree as ET

def fetch_pmc_metadata(pmcid: str):
    """
    Fetch article metadata from PubMed Central (PMC) using PMCID.
    Example: PMCID = 'PMC1234567'
    """
    pmcid = pmcid.strip().upper()
    if not pmcid.startswith("PMC"):
        pmcid = "PMC" + pmcid

    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {
        "db": "pmc",
        "id": pmcid,
        "retmode": "xml"
    }

    print(f"🔍 Fetching metadata for {pmcid} ...")
    response = requests.get(url, params=params)

    if response.status_code != 200:
        raise Exception(f"Error {response.status_code}: Unable to fetch data from PMC")

    # Parse XML
    root = ET.fromstring(response.text)

    article_data = {
        "PMCID": pmcid,
        "Title": None,
        "Journal": None,
        "PublicationDate": None,
        "Authors": [],
        "Abstract": None
    }

    try:
        # Title
        title_el = root.find(".//article-title")
        if title_el is not None:
            article_data["Title"] = title_el.text

        # Journal
        journal_el = root.find(".//journal-title")
        if journal_el is not None:
            article_data["Journal"] = journal_el.text

        # Publication Date
        date_el = root.find(".//pub-date")
        if date_el is not None:
            year = date_el.findtext("year", "")
            month = date_el.findtext("month", "")
            day = date_el.findtext("day", "")
            article_data["PublicationDate"] = f"{year}-{month}-{day}".strip("-")

        # Authors
        for author in root.findall(".//contrib[@contrib-type='author']"):
            last = author.findtext(".//surname", "")
            first = author.findtext(".//given-names", "")
            if last or first:
                article_data["Authors"].append(f"{first} {last}".strip())

        # Abstract
        abstract_el = root.find(".//abstract")
        if abstract_el is not None:
            abstract_text = " ".join([t.text.strip() for t in abstract_el.findall(".//p") if t.text])
            article_data["Abstract"] = abstract_text

    except Exception as e:
        print(f"⚠️ XML parsing issue: {e}")

    return article_data


if __name__ == "__main__":
    pmcid = input("Enter PMCID (e.g., PMC1234567): ").strip()
    info = fetch_pmc_metadata(pmcid)

    print("\n=== 🧾 Article Metadata ===")
    for key, value in info.items():
        if isinstance(value, list):
            value = ", ".join(value)
        print(f"{key}: {value}")
