# data/output_handler.py
import json
import pandas as pd

def flatten_pubmed_studies(pubmed_section):
    if not pubmed_section:
        return []
    studies = pubmed_section.get("studies", [])
    rows = []
    for s in studies:
        if "error" in s:
            rows.append({
                "pmid": s.get("pmid", ""),
                "title": f"ERROR: {s.get('error')}",
                "abstract": "",
                "authors": "",
                "journal": "",
                "publication_date": "",
                "url": "",
                "source": s.get("source", "")
            })
        else:
            rows.append({
                "pmid": s.get("pmid", ""),
                "title": s.get("title", ""),
                "abstract": s.get("abstract", ""),
                "authors": ", ".join(s.get("authors", [])),
                "journal": s.get("journal", ""),
                "publication_date": s.get("publication_date", ""),
                "url": s.get("url", ""),
                "source": s.get("source", "")
            })
    return rows

def flatten_pmc_summaries(pmc_section):
    if not pmc_section:
        return []
    rows = []
    for item in pmc_section.get("summaries", []):
        pmcid = item.get("pmcid", "")
        metadata = item.get("metadata", {}) or {}
        for uid, meta in metadata.items():
            rows.append({
                "pmcid": pmcid,
                "uid": uid,
                "title": meta.get("title", ""),
                "pubdate": meta.get("pubdate", ""),
                "source_db": meta.get("source_db", ""),
                "authors": ", ".join(meta.get("authors", [])) if isinstance(meta.get("authors", []), list) else meta.get("authors", ""),
                "doi_info": json.dumps(meta.get("doi", {})),
                "linked_pmid": meta.get("pmid", "")
            })
    return rows

def flatten_clinical_trial(clinical_section):
    if not clinical_section:
        return []
    data = clinical_section.get("data", {}) or {}
    brief = data.get("brief_title") or data.get("identificationModule", {}).get("briefTitle", "")
    title = brief or data.get("title") or ""
    return [{
        "nct_id": clinical_section.get("data", {}).get("nct_id") or clinical_section.get("data", {}).get("id", ""),
        "title": title,
        "source": clinical_section.get("source", "clinicaltrials_api"),
        "raw_present": bool(clinical_section.get("data"))
    }]

def save_results_to_csv(result, filename):
    sources = result.get("sources", {})
    pubmed_rows = flatten_pubmed_studies(sources.get("pubmed"))
    pmc_rows = flatten_pmc_summaries(sources.get("pmc"))
    rows = []
    if pubmed_rows:
        rows.extend(pubmed_rows)
    if pmc_rows:
        rows.extend(pmc_rows)
    if not rows:
        rows = [{"message": "No data available"}]
    df = pd.DataFrame(rows)
    df.to_csv(filename, index=False, encoding="utf-8-sig")
    print(f"✅ CSV saved to '{filename}'")

def save_results_to_excel(result, filename):
    sources = result.get("sources", {})
    pubmed_rows = flatten_pubmed_studies(sources.get("pubmed"))
    pmc_rows = flatten_pmc_summaries(sources.get("pmc"))
    clinical_rows = flatten_clinical_trial(sources.get("clinical_trials"))
    with pd.ExcelWriter(filename, engine="openpyxl") as writer:
        if clinical_rows:
            pd.DataFrame(clinical_rows).to_excel(writer, sheet_name="ClinicalTrials", index=False)
        if pubmed_rows:
            pd.DataFrame(pubmed_rows).to_excel(writer, sheet_name="PubMed", index=False)
        if pmc_rows:
            pd.DataFrame(pmc_rows).to_excel(writer, sheet_name="PMC", index=False)
        pd.DataFrame([{"nct_id": result.get("nct_id", ""), "raw_json": json.dumps(result, indent=2, ensure_ascii=False)}]).to_excel(writer, sheet_name="Raw_JSON", index=False)
    print(f"✅ Excel saved to '{filename}'")

def save_responses_to_excel(conversation, filename, csv_mode=False):
    if not conversation:
        print("⚠️ No conversation to save.")
        return
    df = pd.DataFrame(conversation)
    if csv_mode:
        df.to_csv(filename, index=False, encoding="utf-8-sig")
        print(f"✅ Conversation saved to CSV: {filename}")
    else:
        with pd.ExcelWriter(filename, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Conversation", index=False)
        print(f"✅ Conversation saved to Excel: {filename}")

def save_any(obj, filename, filetype="xlsx"):
    if isinstance(obj, list):
        save_responses_to_excel(obj, filename, csv_mode=(filetype == "csv"))
    elif isinstance(obj, dict):
        if filetype == "csv":
            save_results_to_csv(obj, filename)
        else:
            save_results_to_excel(obj, filename)
    else:
        raise ValueError("Unsupported data type for saving.")
