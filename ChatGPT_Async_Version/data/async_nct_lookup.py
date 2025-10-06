import asyncio, json
from data.data_fetchers import fetch_clinical_trial_and_pubmed_pmc, summarize_result, print_study_summary, save_results

async def run_nct_lookup_async():
    while True:
        nct_input = input('\\nEnter NCT number(s), comma-separated (or \"main menu\" to go back): ').strip()
        if nct_input.lower() in ('main menu','exit','quit'): return
        nct_ids = [n.strip().upper() for n in nct_input.split(',') if n.strip()]
        results = []
        for n in nct_ids:
            print(f\"\\n🔎 Processing {n} ...\")
            res = fetch_clinical_trial_and_pubmed_pmc(n)
            if 'error' in res:
                print('❌', res['error']); continue
            print_study_summary(res)
            results.append(summarize_result(res))
        if results:
            choice = input('\\nSave results? (y/n): ').strip().lower()
            if choice == 'y':
                fmt = input('Save as (1) TXT or (2) CSV [1]: ').strip() or '1'
                out = 'output'
                import os; os.makedirs(out, exist_ok=True)
                if fmt == '2':
                    import csv
                    path = f\"{out}/nct_results_{'_'.join(nct_ids)}.csv\"
                    with open(path,'w',newline='',encoding='utf-8') as f:
                        writer = csv.DictWriter(f, fieldnames=results[0].keys()); writer.writeheader(); writer.writerows(results)
                else:
                    path = f\"{out}/nct_results_{'_'.join(nct_ids)}.txt\"
                    with open(path,'w',encoding='utf-8') as f:
                        for r in results: f.write(json.dumps(r,indent=2)); f.write('\\n\\n')
                print(F'✅ Saved results to {path}')
        again = input('Lookup more NCTs? (y/n): ').strip().lower()
        if again != 'y': return
