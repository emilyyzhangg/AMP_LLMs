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

after logging in via SSH
8. Main Menu: give user choice between interactive shell or LLM Workflow or NCT Lookup or Exit. In any other menu or running mode from here on in, user can type main menu to return to this main menu at any time
9. interactive shell opens a shell on the host computer in the terminal where python was run on the remote computer. main menu return function remains always!

LLM Workflow
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
