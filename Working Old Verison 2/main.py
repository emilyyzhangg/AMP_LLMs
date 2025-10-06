#!/usr/bin/env python3
import os
import sys
import json
import subprocess
from network.ssh_connection import connect_ssh  # your existing module
from network.networking import ping_host        # you need a ping helper
from llm.interactive import interactive_session
from llm.llm_utils import list_local_models, run_ollama_local, run_ollama_remote
from data.data_fetchers import fetch_clinical_trial_and_pubmed_pmc
from data.output_handler import save_any

def bootstrap_environment():
    """
    This function handles the environment setup, pip installs, etc., then relaunch inside environment.
    You said it already exists and works. We'll assume it is in env_setup.py or similar.
    """
    # Suppose you have an env_setup.py you call:
    import env_setup
    env_setup.ensure_env()  # this may install required packages etc.
    # After that, relaunch into the env if needed
    # (you presumably already have code for that)
    return

def prompt_ip():
    default = "127.0.0.1"
    while True:
        ip = input(f"Enter IP of remote host (default {default}): ").strip()
        if ip == "":
            ip = default
        print(f"Pinging {ip} …")
        try:
            ok = ping_host(ip)
        except Exception as e:
            print(f"Ping failed: {e}")
            ok = False
        if ok:
            print("✅ Host reachable.")
            return ip
        else:
            print("❌ Host not reachable. Try again.")

def prompt_username(default=None):
    if default is None:
        default = os.getlogin() or ""
    name = input(f"Username (default {default}): ").strip()
    if name == "":
        name = default
    return name

def ssh_login(ip, username):
    """
    Connect via SSH to username@ip, prompt for password, return ssh_client
    """
    client = connect_ssh(ip, username)  # presumably this prompts for password
    if not client:
        print("❌ SSH connection failed.")
        return None
    print("✅ SSH connected.")
    return client

def main_menu_loop(ssh_client):
    """
    After SSH login, show main menu and dispatch sub-modes.
    At any point, typing "main menu" returns here.
    """
    while True:
        print("\n=== MAIN MENU ===")
        print("1) Interactive Shell")
        print("2) LLM Workflow")
        print("3) NCT Lookup")
        print("4) Exit")
        choice = input("Select option: ").strip().lower()

        if choice in ("1", "interactive", "interactive shell"):
            interactive_shell_mode(ssh_client)
        elif choice in ("2", "llm", "llm workflow"):
            llm_workflow_mode(ssh_client)
        elif choice in ("3", "nct", "nct lookup"):
            nct_lookup_mode()
        elif choice in ("4", "exit", "quit"):
            print("Exiting to local shell.")
            break
        else:
            print("Unknown choice. Please choose 1–4.")

def interactive_shell_mode(ssh_client):
    """
    Launch a shell on the remote host via SSH, relay input/output.
    Typing “main menu” should exit this mode and return to main menu.
    """
    print("\n--- Interactive Remote Shell (type 'main menu' to return) ---")
    chan = ssh_client.invoke_shell()
    import threading

    def _read_from_remote():
        try:
            while True:
                data = chan.recv(4096).decode()
                if not data:
                    break
                print(data, end="")
        except Exception as e:
            print(f"\n[Remote shell read error: {e}]")

    reader = threading.Thread(target=_read_from_remote, daemon=True)
    reader.start()

    try:
        while True:
            cmd = input()
            if cmd.strip().lower() in ("main menu", "exit", "quit"):
                chan.close()
                break
            chan.send(cmd + "\n")
    except KeyboardInterrupt:
        chan.close()
    print("\nReturned to main menu.")

def llm_workflow_mode(ssh_client):
    """
    LLM workflow:
      - list models installed on remote host (via SSH)
      - user chooses one
      - prompt user: either enter prompt interactively or upload CSV file
      - interactive or batch mode accordingly
    """
    # List models
    print("\n--- LLM Workflow ---")
    models = list_local_models()  # or remote-list via SSH, if remote installation
    if not models:
        print("No models available.")
        return
    print("Available models:")
    for i, m in enumerate(models, start=1):
        print(f" {i}) {m}")
    sel = input("Select model by number (or name): ").strip()
    try:
        idx = int(sel) - 1
        model = models[idx]
    except:
        model = sel if sel in models else None
    if model is None:
        print("Invalid selection.")
        return
    print(f"Selected model: {model}")

    # Interaction mode or CSV-upload mode
    mode = input("Type 'prompt' to interact or 'upload' to run a CSV file: ").strip().lower()
    if mode == "upload":
        path = input("Enter path to CSV prompts file: ").strip()
        # read prompts
        import csv
        prompts = []
        with open(path, newline="", encoding="utf-8") as f:
            rdr = csv.reader(f)
            for row in rdr:
                if row:
                    prompts.append(row[0])
        responses = []
        for p in prompts:
            print(f"\nPrompt: {p}")
            if ssh_client:
                resp = run_ollama_remote(ssh_client, model, p)
            else:
                resp = run_ollama_local(model, p)
            print(f"Response: {resp}")
            responses.append((p, resp))
        # save to CSV
        save_path = input("Enter output CSV path: ").strip()
        with open(save_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["prompt", "response"])
            w.writerows(responses)
        print(f"Saved responses to {save_path}")
    else:
        # interactive prompting
        print("Enter prompts (type 'main menu' to return to main menu).")
        while True:
            p = input("Prompt: ").strip()
            if p.lower() in ("main menu", "exit", "quit"):
                break
            if ssh_client:
                resp = run_ollama_remote(ssh_client, model, p)
            else:
                resp = run_ollama_local(model, p)
            print("Response:")
            print(resp)

def nct_lookup_mode():
    """Handles steps 13–20: user enters NCT(s) and run conversions and PubMed/PMC lookups."""
    print("\n--- NCT Lookup Mode (type 'main menu' to return) ---")
    while True:
        inp = input("Enter NCT ID(s), comma-separated: ").strip()
        if inp.lower() in ("main menu", "exit", "quit"):
            return
        parts = [p.strip().upper() for p in inp.split(",") if p.strip()]
        if not parts:
            continue

        all_results = []
        for nct in parts:
            print(f"\n🔍 Looking up NCT: {nct}")
            res = fetch_clinical_trial_and_pubmed_pmc(nct)
            all_results.append({"nct_id": nct, "data": res})
            # print summary
            if "error" in res:
                print(f"❌ Error for {nct}: {res['error']}")
                continue
            # ClinicalTrials data
            ct = res.get("sources", {}).get("clinical_trials", {})
            print("ClinicalTrials.gov section:", ct.get("source"))
            # PubMed
            pm = res.get("sources", {}).get("pubmed", {})
            print("PubMed PMIDs:", pm.get("pmids", []))
            # PMC
            pmsc = res.get("sources", {}).get("pmc", {})
            print("PMC IDs:", pmsc.get("pmcids", []))

        # Save option
        choice = input("\nSave output? (json / csv / none): ").strip().lower()
        if choice in ("json", "csv"):
            path = input("Path to save (with extension): ").strip()
            if choice == "json":
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(all_results, f, indent=2, ensure_ascii=False)
                print(f"Saved JSON to {path}")
            else:
                # convert to flat CSV: one row per NCT or one per PMID? We'll do one per NCT, flattening key fields
                import csv
                with open(path, "w", newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    header = ["nct_id", "clinical_source", "pmids", "pmcids", "error"]
                    w.writerow(header)
                    for rec in all_results:
                        nct = rec.get("nct_id")
                        d = rec.get("data", {})
                        ct = d.get("sources", {}).get("clinical_trials", {})
                        pm = d.get("sources", {}).get("pubmed", {})
                        pmc = d.get("sources", {}).get("pmc", {})
                        err = d.get("error", "")
                        w.writerow([nct,
                                    ct.get("source", ""),
                                    "|".join(pm.get("pmids", [])),
                                    "|".join(pmc.get("pmcids", [])),
                                    err])
                print(f"Saved CSV to {path}")

        more = input("Lookup more NCTs? (y/n): ").strip().lower()
        if more != "y":
            return

def main():
    bootstrap_environment()
    ip = prompt_ip()
    username = prompt_username()
    ssh_client = ssh_login(ip, username)
    if not ssh_client:
        sys.exit(1)
    try:
        main_menu_loop(ssh_client)
    finally:
        ssh_client.close()
        print("SSH closed. Exiting.")

if __name__ == "__main__":
    main()
