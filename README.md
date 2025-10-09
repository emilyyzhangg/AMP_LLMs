# AMP_LLMs
LLM scripts for AMP Clinical Trial model

# Run the program
python main

# Commands available within program
main menu --> returns user to operation mode selection (terminal vs llm workflow)

# SSH into Mac directly
ssh emilyzhang@100.99.162.98

# Working Features
- interactive shell terminal
- LLM interactive access
- NCT lookup and data dump

# workflow
1. user runs python main
2. python check, pip install, env_setup, relaunch in env, all of this is great and stays the way it is.
3. user is prompted with entering IP, default remains
4. ping sent to IP, if response, proceed, otherwise go back to requesting IP from user
5. port is always 22, no need for this step
6. seek username input, default remains
7. ssh into user@IP, then prompt for password, these steps are great so far, very little needs fixing

# after logging in via SSH
8. Main Menu: give user choice between interactive shell or LLM Workflow or NCT Lookup or Exit. In any other menu or running mode from here on in, user can type main menu to return to this main menu at any time
9. interactive shell opens a shell on the host computer in the terminal where python was run on the remote computer. main menu return function remains always!

# LLM Workflow
10. LLM Workflow gives list of ollama llms installed on the host and user can pick an llm to start up
11. llm chosen starts up, user then has the choice to prompt the llm or to upload a csv file with prompts. prompt option runs the llm and allows the user to interact
12. the handling of the prompting file and responses will be programmed later, input is csv, output is csv for now

NCT lookup
13. prompts for NCT number or multiple, comma seperated NCT numbers. not case sensitive. "main menu" still returns to main
14. searches ClinicalTrials for NCT number info. 
15. extracts DOI, PMID, PMCID if available and attempts conversion to PMID
16. DOI, PMID, PMCID searches of PubMed followed by a search for title + author. found or not found messaging for all results and also JSON dumps
17. DOI, PMID, PMCID searches of PMC followed by a search for title + author. found or not found messaging for all results and also JSON dumps
18. repeat 14-17 for all NCT numbers entered
19. Option to save to txt file or csv. multiple NCT numbers will be seperated by commas in csv
20. ask user if they want additional NCT lookups otherwise return to main menu

# prompt for modelfile
 i want to use a modelfile or rag, or both if it makes sense, to get the llm to be a research assistant that digs through a json database with clinical trial information (sorted by NCT number) and pull out the following info: NCT Number Study Title Study Status Brief Summary Conditions Interventions/Drug Phases Enrollment Start Date Completion Date Classification <- evidence link(s) Delivery Mode Sequence dramp_name <- evidence link(s) Study ID (PMID OR DOI) Outcome Reason for Failure/withdrawal/termination Subsequent Trial ID <- evidence link(s) Peptide? Comments. a sample txt file is provided with the data structure for one single study, identified by NCT number. give me guidance and a full code that i can add to my project to make this possible

 # modelfile
- can be used with any llm
- field restrictions to be added, as per spreadsheet
- Database indexer - Indexes your JSON database by NCT numbers
- RAG retriever - Finds relevant trials and extracts structured data
- Custom Modelfile - Gives Ollama specialized instructions
- Enhanced LLM runner - Integrates RAG into your existing workflow

📋 Common Commands
CommandDescriptionExamplesearch <query>     Search database     search LEAP-2
extract <NCT>   Extract one trial   extract NCT04043065
query <question>    Ask with RAG    query What peptide trials completed?
load <file> Load JSON fileload   trial_data.json
export <NCT,NCT>    Export trials   export NCT123,NCT456
stats   Database stats    stats
exit Return to menu exit

search <query>          # Find trials in database
extract <NCT>           # Get structured extraction
query <question>        # Ask with auto-retrieval
load <file>             # Analyze JSON files
export <NCT,NCT,...>    # Export to JSON/CSV
stats                   # Database statistics

Data Validation
Study Status --> NOT_YET_RECRUITING, RECRUITING, ENROLLING_BY_INVITATION, ACTIVE_NOT_RECRUITING, COMPLETED, SUSPENDED, TERMINATED, WITHDRAWN, UNKNOWN
Phases --> EARLY_PHASE1, PHASE1, PHASE1|PHASE2, PHASE2, PHASE2|PHASE3, PHASE3, PHASE4
Classification --> AMP(infection), AMP(other), Other
Delivery Mode --> Injection/Infusion - Intramuscular, Injection/Infusion - Other/Unspecified, Injection/Infusion - Subcutaneous/Intradermal, IV, Intranasal, Oral - Tablet, Oral - Capsule, Oral - Food, Oral - Drink, Oral - Unspecified, Topical - Cream/Gel, Topical - Powder, Topical - Spray, Topical - Strip/Covering, Topical - Wash, Topical - Unspecified, Other/Unspecified, Oral - Unspecified, Inhalation
Outcome --> Positive, Withdrawn, Terminated, Failed - completed trial, Recruiting, Unknown, Active, not recruiting
Reason for Failure/withdrawl --> Business Reason, Ineffective for purpose, Toxic/Unsafe, Due to covid, Recruitment issues
Peptide? --> True, False


