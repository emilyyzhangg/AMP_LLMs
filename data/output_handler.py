# output_handler.py

import json
import pandas as pd


# ==============================================================
# 🧩 Helper flatteners for structured export
# ==============================================================

def flatten_pubmed_studies(pubmed_data):
    """Flatten PubMed studies from result structure."""
    if not pubmed_data:
        return []

    studies = pubmed_data.get("studies", [])
    rows = []
    for study in studies:
        rows.append({
            "pmid": study.get("pmid", ""),
            "title": study.get("title", ""),
            "abstract": study.get("abstract", ""),
            "authors": ", ".join(study.get("authors", [])),
            "journal": study.get("journal", ""),
            "publication_date": study.get("publication_date", ""),
            "url": study.get("url", ""),
            "source": study.get("source", "pubmed_api"),
            "error": study.get("error", "")
        })
    return rows


def flatten_pmc_studies(pmc_data):
    """Flatten PMC metadata studies."""
    if not pmc_data:
        return []

    studies = pmc_data.get("studies", [])
    rows = []
    for study in studies:
        rows.append({
            "pmcid": study.get("pmcid", ""),
            "pmid": study.get("pmid", ""),
            "title": study.get("title", ""),
            "authors": ", ".join(study.get("authors", [])),
            "publication_date": study.get("publication_date", ""),
            "journal": study.get("journal", ""),
            "url": study.get("url", ""),
            "source": study.get("source", "pmc_api"),
            "error": study.get("error", "")
        })
    return rows


def flatten_clinical_trial_data(clinical_data):
    """Flatten ClinicalTrials.gov data for Excel."""
    if not clinical_data:
        return []

    data = clinical_data.get("data", {})
    if not data:
        return []

    # Flatten key fields if available
    return [{
        "nct_id": data.get("id", ""),
        "title": data.get("brief_title", ""),
        "status": data.get("overall_status", ""),
        "conditions": ", ".join(data.get("conditions", [])),
        "interventions": ", ".join(data.get("interventions", [])),
        "locations": ", ".join(data.get("locations", [])),
        "study_type": data.get("study_type", ""),
        "phase": data.get("phase", ""),
        "start_date": data.get("start_date", ""),
        "completion_date": data.get("completion_date", ""),
        "last_update_posted": data.get("last_update_posted", ""),
        "source": clinical_data.get("source", "clinicaltrials_api")
    }]


# ==============================================================
# 💾 Core save functions
# ==============================================================

def save_results_to_csv(result, filename):
    """
    Save a combined fetch result to CSV.
    Flattens PubMed studies into one CSV table.
    """
    sources = result.get("sources", {})
    pubmed_rows = flatten_pubmed_studies(sources.get("pubmed"))
    clinical_rows = flatten_clinical_trial_data(sources.get("clinical_trials"))
    pmc_rows = flatten_pmc_studies(sources.get("pmc"))

    if pubmed_rows:
        df = pd.DataFrame(pubmed_rows)
    elif clinical_rows:
        df = pd.DataFrame(clinical_rows)
    elif pmc_rows:
        df = pd.DataFrame(pmc_rows)
    else:
        df = pd.DataFrame([{"message": "No data available"}])

    df.to_csv(filename, index=False, encoding="utf-8-sig")
    print(f"✅ CSV saved to '{filename}'")


def save_results_to_excel(result, filename):
    """
    Save combined results to Excel with multiple sheets:
      - ClinicalTrials.gov
      - PubMed
      - PMC
    """
    sources = result.get("sources", {})

    pubmed_rows = flatten_pubmed_studies(sources.get("pubmed"))
    pmc_rows = flatten_pmc_studies(sources.get("pmc"))
    clinical_rows = flatten_clinical_trial_data(sources.get("clinical_trials"))

    with pd.ExcelWriter(filename, engine="openpyxl") as writer:
        if clinical_rows:
            pd.DataFrame(clinical_rows).to_excel(writer, sheet_name="ClinicalTrials", index=False)
        if pubmed_rows:
            pd.DataFrame(pubmed_rows).to_excel(writer, sheet_name="PubMed", index=False)
        if pmc_rows:
            pd.DataFrame(pmc_rows).to_excel(writer, sheet_name="PMC", index=False)

        # Store raw JSON for debugging / context
        pd.DataFrame([{
            "nct_id": result.get("nct_id", ""),
            "raw_json": json.dumps(result, indent=2, ensure_ascii=False)
        }]).to_excel(writer, sheet_name="Raw_JSON", index=False)

    print(f"✅ Excel saved to '{filename}'")


# ==============================================================
# 💬 Conversation saving (for interactive sessions)
# ==============================================================

def save_responses_to_excel(conversation, filename, csv_mode=False):
    """
    Save interactive LLM conversation to CSV or Excel.
    Each entry: prompt, response, and source (e.g., pubmed_api, clinicaltrials_api).
    """
    if not conversation:
        print("⚠️ No conversation data to save.")
        return

    df = pd.DataFrame(conversation)
    if csv_mode:
        df.to_csv(filename, index=False, encoding="utf-8-sig")
        print(f"✅ Conversation saved to CSV: {filename}")
    else:
        with pd.ExcelWriter(filename, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Conversation", index=False)
        print(f"✅ Conversation saved to Excel: {filename}")


# ==============================================================
# 🧠 Convenience dispatcher
# ==============================================================

def save_any(result_or_conversation, filename, filetype="xlsx"):
    """
    Universal save function: automatically detects whether it's
    a combined result or a conversation and saves accordingly.
    """
    if isinstance(result_or_conversation, list):
        # Likely a conversation
        save_responses_to_excel(result_or_conversation, filename, csv_mode=(filetype == "csv"))
    elif isinstance(result_or_conversation, dict):
        if filetype == "csv":
            save_results_to_csv(result_or_conversation, filename)
        else:
            save_results_to_excel(result_or_conversation, filename)
    else:
        raise ValueError("Unsupported data type for saving.")
