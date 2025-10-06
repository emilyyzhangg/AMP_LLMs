import asyncio
from data.data_fetchers import fetch_clinical_trial_and_pubmed_pmc, summarize_result, print_study_summary, save_results
from colorama import Fore

async def run_nct_lookup():
    while True:
        nct_input = input(Fore.CYAN + "\nEnter NCT number(s), comma-separated (or 'main menu' to go back): ").strip()
        if nct_input.lower() in ('main menu','exit','quit'):
            return
        ncts = [n.strip().upper() for n in nct_input.split(',') if n.strip()]
        results = []
        for n in ncts:
            print(Fore.YELLOW + f"\nFetching data for {n}...")
            res = fetch_clinical_trial_and_pubmed_pmc(n)
            if 'error' in res:
                print(Fore.RED + f"Error: {res.get('error')}")
                continue
            print_study_summary(res)
            results.append(res)
        if not results:
            continue
        save = input(Fore.CYAN + "\nSave results (txt/csv/none)? ").strip().lower()
        if save in ('txt','csv'):
            fname = input('Enter filename (without ext): ').strip()
            save_results(results, fname, fmt=save)
        again = input(Fore.CYAN + "Lookup more NCTs? (y/n): ").strip().lower()
        if again != 'y':
            return
