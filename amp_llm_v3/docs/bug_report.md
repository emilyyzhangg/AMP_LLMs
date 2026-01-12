# Last updated - 10/10/2025 - 06:00 PST

# Shutdown is not graceful
Tip: Press Ctrl+C anytime to return to this menu
Select an option: exit
Exiting. Goodbye!
2025-10-10 05:55:15 - src.amp_llm.core.lifecycle - INFO - Running 2 stopping hook(s)
2025-10-10 05:55:15 - src.amp_llm.core.ssh_manager - INFO - Closing SSH connection...
h:\Documents\LLM Code\AMP_LLMs\amp_llm_v3\src\amp_llm\core\ssh_manager.py:230: RuntimeWarning: coroutine 'SSHConnection.close' was never awaited
  self.connection.close()
RuntimeWarning: Enable tracemalloc to get the object allocation traceback
2025-10-10 05:55:20 - src.amp_llm.core.ssh_manager - WARNING - SSH close timeout, connection may not have closed cleanly
2025-10-10 05:55:20 - src.amp_llm.core.ssh_manager - INFO - SSH connection closed
✨ Thank you for using AMP_LLM!
2025-10-10 05:55:20 - src.amp_llm.core.app - INFO - Application shutdown complete
✅ Application exited cleanly.
2025-10-10 05:55:20 - asyncio - ERROR - Exception in callback <_asyncio.TaskStepMethWrapper object at 0x0000021D72DF1FF0>()
handle: ()>
Traceback (most recent call last):
  File "C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.13_3.13.2288.0_x64__qbz5n2kfra8p0\Lib\asyncio\events.py", line 89, in _run
    self._context.run(self._callback, *self._args)
    ~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.13_3.13.2288.0_x64__qbz5n2kfra8p0\Lib\asyncio\tasks.py", line 774, in cancel
    if child.cancel(msg=msg):
       ~~~~~~~~~~~~^^^^^^^^^
  File "C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.13_3.13.2288.0_x64__qbz5n2kfra8p0\Lib\asyncio\tasks.py", line 774, in cancel
    if child.cancel(msg=msg):
       ~~~~~~~~~~~~^^^^^^^^^
  File "C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.13_3.13.2288.0_x64__qbz5n2kfra8p0\Lib\asyncio\tasks.py", line 774, in cancel
    if child.cancel(msg=msg):
       ~~~~~~~~~~~~^^^^^^^^^
  [Previous line repeated 991 more times]
RecursionError: maximum recursion depth exceeded

# Output of NCT Lookup needs a lot of work
- clear indication of what is being search on which API with clear division between them, like Clinical Trials and PubMed.
- numbers at the end of the report dont match: 2 is not equal to 4
- only searching the other APIs using the NCT number at the moment, this needs to be expanded to title, if too many results then by title + author, if still a great number of responses then title + author + date or name of drug

============================================================
Fetching data for NCT04043065...
============================================================

🔍 ClinicalTrials.gov v2: fetching https://clinicaltrials.gov/api/v2/studies/NCT04043065       
✅ ClinicalTrials.gov v2: Study found (detail).

📖 Searching for related publications: 'A Leap to Understand Glucoregulatory Effects of Liver-enriched Antimicrobial Peptide 2 (LEAP-2)'
🔍 PubMed: searching for 'A Leap to Understand Glucoregulatory AND Filip K Knop[Author]'       
⚠️ PubMed: no matches found.
✅ PMC: found 2 matches.
✅ PMC: fetched metadata for 9650057
✅ PMC: fetched metadata for 8452786
✅ Successfully fetched NCT04043065

===== 📊 CLINICAL TRIAL SUMMARY =====
🧪 A Leap to Understand Glucoregulatory Effects of Liver-enriched Antimicrobial Peptide 2 (LEAP-2)
📅 Status: COMPLETED
🏥 Sponsor: University Hospital, Gentofte, Copenhagen
🔬 Conditions: Type 2 Diabetes

🔭 No PubMed matches found.

===== 🧾 PMC RESULTS =====
🔸 https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9650057/
🔸 https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8452786/

🔎 Running extended API search...

============================================================
🔎 Extended API Search
============================================================

🚀 Running 14 API search(es) concurrently...

🔍 Meilisearch: Searching index 'clinical_trials'...
🔍 Swirl: Running metasearch...
🔍 OpenFDA: Searching adverse events for 'Liver-enriched antimicrobial peptide 2'...
🔍 OpenFDA: Searching drug labels for 'Liver-enriched antimicrobial peptide 2'...
🔍 OpenFDA: Searching adverse events for 'Placebo'...
🔍 OpenFDA: Searching drug labels for 'Placebo'...
🔍 Health Canada: Searching clinical trials database...
🔍 DuckDuckGo: Searching web...
⚠️ DuckDuckGo: duckduckgo-search not installed
   Install with: pip install duckduckgo-search
2025-10-10 05:56:58 - amp_llm.data.external_apis.api_clients - WARNING - DuckDuckGo library not available
🔍 SERP API: Searching Google...
🔍 SERP API: Searching Google Scholar...
🔍 PMC Full Text: Searching for articles related to NCT04043065...
🔍 PMC Full Text: Searching for 'NCT04043065 OR (A Leap to Understand Glucoregulatory Effects of Liver-enriched Antimicrobial Peptide'...
🔍 EudraCT: Searching for trials related to NCT04043065...
🔍 EudraCT: Searching European trials database...
   Searching for: NCT04043065
🔍 WHO ICTRP: Searching for NCT04043065...
🔍 WHO ICTRP: Searching international trials registry...
   Query: NCT04043065
🔍 Semantic Scholar: Searching papers for NCT04043065...
🔍 Semantic Scholar: Searching for 'NCT04043065 A Leap to Understand Glucoregulatory Effects of Liver-enriched Antimicrobial Peptide Typ'...
✅ SERP API: Found 0 result(s)
2025-10-10 05:56:58 - amp_llm.data.external_apis.api_clients - INFO - SERP API returned 0 results
✅ SERP API Scholar: Found 0 result(s)
2025-10-10 05:56:58 - amp_llm.data.external_apis.api_clients - INFO - SERP API Scholar returned 0 results
ℹ️ OpenFDA: No drug labels found for 'Liver-enriched antimicrobial peptide 2'
❌ Health Canada: Cannot connect to host health-products.canada.ca:443 ssl:True [SSLCertVerificationError: (1, '[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1032)')]
2025-10-10 05:56:58 - amp_llm.data.external_apis.api_clients - ERROR - Health Canada error: Cannot connect to host health-products.canada.ca:443 ssl:True [SSLCertVerificationError: (1, '[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1032)')]
ℹ️ OpenFDA: No drug labels found for 'Placebo'
ℹ️ OpenFDA: No adverse events found for 'Liver-enriched antimicrobial peptide 2'
✅ OpenFDA: Found 10 adverse event report(s)
2025-10-10 05:56:58 - amp_llm.data.external_apis.api_clients - INFO - OpenFDA returned 10 events for Placebo
✅ Semantic Scholar: Found 0 paper(s) (0 total)
2025-10-10 05:56:58 - amp_llm.data.external_apis.semantic_scholar - INFO - Semantic Scholar search returned 0 results
✅ WHO ICTRP: Found 0 trial(s)
2025-10-10 05:56:58 - amp_llm.data.external_apis.who_ictrp - INFO - WHO ICTRP search returned 0 results
ℹ️ No results for NCT04043065 in WHO ICTRP
✅ PMC Full Text: Found 4 article(s) (4 total)
2025-10-10 05:56:58 - amp_llm.data.external_apis.pmc_fulltext - INFO - PMC search returned 4 results
✅ Found 4 article(s) for NCT04043065
✅ EudraCT: Found 0 trial(s)
2025-10-10 05:56:59 - amp_llm.data.external_apis.eudract - INFO - EudraCT search returned 0 results
ℹ️ No direct matches for NCT04043065 in EudraCT
❌ Meilisearch: Cannot connect to host localhost:7700 ssl:default [The remote computer refused the network connection]
2025-10-10 05:57:00 - amp_llm.data.external_apis.api_clients - ERROR - Meilisearch error: Cannot connect to host localhost:7700 ssl:default [The remote computer refused the network connection]
❌ Swirl: Cannot connect to host localhost:9000 ssl:default [The remote computer refused the network connection]
2025-10-10 05:57:00 - amp_llm.data.external_apis.api_clients - ERROR - Swirl error: Cannot connect to host localhost:9000 ssl:default [The remote computer refused the network connection]    

============================================================
✅ Extended search complete
============================================================


✅ Extended API search complete for NCT04043065

📈 Extended API Results:
  📊 Meilisearch: 0 hit(s)
  🔄 Swirl: 0 result(s)
  💊 OpenFDA: 10 event(s), 0 label(s)
  🍁 Health Canada: 0 trial(s)
  🦆 DuckDuckGo: 0 result(s)
  📄 PMC Full Text: 4 article(s)
  🇪🇺 EudraCT: 0 trial(s)
  🌍 WHO ICTRP: 0 trial(s)
  🤖 Semantic Scholar: 0 paper(s)
2025-10-10 05:57:00 - amp_llm.data.nct_lookup - INFO - Successfully fetched complete data for NCT04043065

📊 Summary of 1 result(s):
  • NCT04043065: 0 PubMed, 2 PMC
    Extended: 10 OpenFDA, 4 PMC Full Text

# RAG training requires work
- need to give exact responses when prompted for analysis but when questions are asked, the llm should be reading the entire document presented
- workflow is not entirely clear around loading documents and extracting info

# no need to ask for existing model use, creation is quick and it should always be up to date anyway
✅ Connected to Ollama!
   (via SSH tunnel)
✅ Found 14 model(s)
✅ Found existing model: ct-research-assistant:latest

Use existing 'ct-research-assistant:latest'? (y/n/s=skip) [y]: n

🔄 Rebuilding 'ct-research-assistant:latest'...
Select a base model to create the custom model

# llama3 selection failed?? no idea why
Select base model [1]: 3

🔨 Building 'ct-research-assistant:latest' from 'llama3:8b'...

🏗️  Building Custom Model
✅ Found Modelfile: Modelfile
Using selected base model: llama3:8b

🔨 Building 'ct-research-assistant:latest' from 'llama3:8b'...
📤 Uploading Modelfile...
✅ Uploaded to /tmp/amp_modelfile_1760101492.modelfile
🏗️  Building model (this may take 1-2 minutes)...
   Please wait...

❌ Model creation failed!
Error: stty: stdin isn't a terminal
gathering model components
using existing layer sha256:6a0746a1ec1aef3e7ec53868f220ff6e389f6f8ef87a01d77c96807de94ca2aa   
using existing layer sha256:4fa551d4f938f68b8c1e6afa9d28befb70e3f33f75d0753248d530364aeea40f   
using existing layer sha256:8ab4849b038cf0abc5b1c9b8ee1443dca6b93a045c2272180d985126eb40bf6f   
using existing layer sha256:5b21492466fa588ac6c3065a9fde053ba2cac892b6757ded571288f9cdc6c810   
using existing layer sha256:6259088bdf3349b06dec5ceccda31928b07e75c8a23d21de9c0cb19894242056   
writing manifest
success
stty: stdin isn't a terminal

❌ Failed to create 'ct-research-assistant:latest'