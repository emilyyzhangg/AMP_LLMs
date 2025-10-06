import json, csv, os
def save_responses_to_excel(conversation, path, csv_mode=False):
    # lightweight handler: write JSON or CSV depending on csv_mode
    if csv_mode:
        # conversation is list of dicts
        keys = set()
        for c in conversation:
            keys.update(c.keys())
        keys = list(keys)
        with open(path, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(conversation)
    else:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(conversation, f, indent=2, ensure_ascii=False)
