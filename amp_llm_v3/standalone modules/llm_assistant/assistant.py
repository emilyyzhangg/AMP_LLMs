import asyncio
import logging
from pathlib import Path
from typing import Optional, List, Dict
from colorama import Fore, Style, init
from amp_llm.cli.async_io import ainput, aprint
from amp_llm.config import get_logger, get_config
from amp_llm.llm.utils.session import OllamaSessionManager

# Import search engine and prompt generator
from nct_search_engine import NCTSearchEngine
from prompt_generator import PromptGenerator
from nct_models import SearchConfig

# Try to import Rich formatters
try:
    from amp_llm.cli.rich_formatters import RichFormatter, console
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    console = None

# Import RAG if available
try:
    from amp_llm.data.clinical_trials.rag import ClinicalTrialRAG
    HAS_RAG = True
except ImportError:
    HAS_RAG = False
    
# Import command handler if available
try:
    from amp_llm.llm.assistants.commands import CommandHandler
    HAS_COMMANDS = True
except ImportError:
    HAS_COMMANDS = False

logger = get_logger(__name__)
config = get_config()
init(autoreset=True)


async def safe_print(*args, **kwargs):
    """Safely print from async context."""
    if HAS_RICH and console:
        await asyncio.to_thread(console.print, *args, **kwargs)
    else:
        await asyncio.to_thread(print, *args, **kwargs)


class ClinicalTrialResearchAssistant:
    """
    Research Assistant with API search integration and prompt generation.
    
    Features:
    - Multi-database search (ClinicalTrials.gov, PubMed, PMC, PMC BioC)
    - Intelligent prompt generation from search results
    - RAG-powered context retrieval
    - Interactive command system
    - Structured data extraction
    """
    
    def __init__(self, database_path: Path):
        """Initialize research assistant."""
        if not HAS_RAG:
            raise ImportError("RAG system not available")
        
        self.rag = ClinicalTrialRAG(database_path)
        
        import json
        output_dir = Path("output")
        for f in output_dir.glob("*.json") if output_dir.exists() else []:
            try:
                self.rag.db.trials.append(json.loads(f.read_text()))
            except: pass
        
        self.rag.db.build_index()
        
        self.model_name = "ct-research-assistant:latest"
        self.session_manager = None
        self.command_handler = None
        
        # Initialize search engine and prompt generator
        self.search_engine = NCTSearchEngine()
        self.prompt_generator = PromptGenerator()
        self.search_initialized = False
    
    async def initialize_search(self):
        """Initialize the search engine."""
        if not self.search_initialized:
            await self.search_engine.initialize()
            self.search_initialized = True
            await aprint(Fore.GREEN + "✅ Search engine initialized")
    
    async def search_and_extract(self, nct_id: str, use_extended: bool = None) -> str:
        """
        Search APIs and extract structured data using LLM.
        
        Args:
            nct_id: NCT number
            use_extended: Whether to use extended APIs (if None, ask user)
            
        Returns:
            Extracted structured data
        """
        try:
            # Initialize search engine if needed
            await self.initialize_search()
            
            # Ask user about extended APIs if not specified
            if use_extended is None:
                use_extended = await self._ask_extended_api_preference()
            
            # Configure search
            if use_extended:
                enabled_dbs = await self._select_extended_apis()
                config = SearchConfig(
                    use_extended_apis=True,
                    enabled_databases=enabled_dbs
                )
                await aprint(Fore.CYAN + f"🌐 Using extended APIs: {', '.join(enabled_dbs)}")
            else:
                config = SearchConfig(
                    use_extended_apis=False,
                    enabled_databases=[]
                )
            
            await aprint(Fore.CYAN + f"\n🔍 Searching databases for {nct_id}...")
            
            # Execute search
            search_results = await self.search_engine.search(nct_id, config)
            
            # Check if trial was found
            if "error" in search_results:
                return f"Error: {search_results['error']}"
            
            # Display search summary
            await self._display_search_summary(search_results)
            
            # Generate prompt from search results
            await aprint(Fore.YELLOW + "\n📝 Generating extraction prompt...")
            prompt = self.prompt_generator.generate_extraction_prompt(
                search_results, 
                nct_id
            )
            
            # Optional: Save prompt for debugging
            prompt_dir = Path("prompts")
            prompt_dir.mkdir(exist_ok=True)
            prompt_file = prompt_dir / f"{nct_id}_extraction.txt"
            self.prompt_generator.save_prompt(prompt, prompt_file)
            await aprint(Fore.CYAN + f"💾 Prompt saved to: {prompt_file}")
            
            # Send to LLM
            await aprint(Fore.YELLOW + "\n🤖 Processing with LLM...")
            response = await self.session_manager.send_prompt(
                self.model_name, 
                prompt
            )
            
            if not response or len(response.strip()) < 50:
                return f"Error: LLM response too short or empty"
            
            return response
            
        except Exception as e:
            logger.error(f"Error in search_and_extract: {e}", exc_info=True)
            return f"Error: {e}"
    
    async def _ask_extended_api_preference(self) -> bool:
        """Ask user if they want to use extended APIs."""
        await aprint(Fore.CYAN + "\n🌐 Extended API Search Options:")
        await aprint(Fore.WHITE + "  • DuckDuckGo: Web search (no API key)")
        await aprint(Fore.WHITE + "  • Google Search: SERP API (requires key)")
        await aprint(Fore.WHITE + "  • Google Scholar: Academic search (requires key)")
        await aprint(Fore.WHITE + "  • OpenFDA: Drug database (no API key)")
        
        choice = await ainput(Fore.GREEN + "\nUse extended APIs? (y/n) [n]: ")
        return choice.strip().lower() in ('y', 'yes')
    
    async def _select_extended_apis(self) -> List[str]:
        """Let user select which extended APIs to use."""
        import os
        
        has_serpapi = bool(os.getenv('SERPAPI_KEY'))
        
        available_apis = {
            '1': ('duckduckgo', 'DuckDuckGo Web Search', True),
            '2': ('serpapi', 'Google Search (SERP)', has_serpapi),
            '3': ('scholar', 'Google Scholar', has_serpapi),
            '4': ('openfda', 'OpenFDA Drug Database', True)
        }
        
        await aprint(Fore.CYAN + "\n📋 Select Extended APIs to use:")
        for key, (api_name, display_name, available) in available_apis.items():
            status = "✓" if available else "✗ (requires API key)"
            await aprint(Fore.WHITE + f"  {key}) {display_name} {status}")
        
        await aprint(Fore.CYAN + "\nOptions:")
        await aprint(Fore.WHITE + "  • Enter numbers separated by commas (e.g., 1,4)")
        await aprint(Fore.WHITE + "  • Enter 'all' for all available")
        await aprint(Fore.WHITE + "  • Enter nothing for all available")
        
        choice = await ainput(Fore.GREEN + "\nSelect APIs [all]: ")
        choice = choice.strip().lower()
        
        # Default to all available
        if not choice or choice == 'all':
            return [api for _, (api, _, avail) in available_apis.items() if avail]
        
        # Parse selection
        selected = []
        for num in choice.split(','):
            num = num.strip()
            if num in available_apis:
                api_name, display_name, available = available_apis[num]
                if available:
                    selected.append(api_name)
                else:
                    await aprint(Fore.YELLOW + f"⚠️  Skipping {display_name} (API key not set)")
        
        if not selected:
            await aprint(Fore.YELLOW + "⚠️  No valid APIs selected, using DuckDuckGo only")
            return ['duckduckgo']
        
        return selected
    
    async def _display_search_summary(self, results: Dict):
        """Display summary of search results."""
        sources = results.get("sources", {})
        
        await aprint(Fore.GREEN + "\n📊 Search Results Summary:")
        await aprint(Fore.CYAN + "\n  Core Databases:")
        
        # ClinicalTrials.gov
        ct = sources.get("clinical_trials", {})
        if ct.get("success"):
            await aprint(Fore.WHITE + "    ✓ ClinicalTrials.gov: Found")
        else:
            await aprint(Fore.RED + "    ✗ ClinicalTrials.gov: Not found")
        
        # PubMed
        pm = sources.get("pubmed", {})
        if pm.get("success"):
            pm_data = pm.get("data", {})
            count = pm_data.get("total_found", 0)
            await aprint(Fore.WHITE + f"    ✓ PubMed: {count} articles")
        else:
            await aprint(Fore.RED + "    ✗ PubMed: Failed")
        
        # PMC
        pmc = sources.get("pmc", {})
        if pmc.get("success"):
            pmc_data = pmc.get("data", {})
            count = pmc_data.get("total_found", 0)
            await aprint(Fore.WHITE + f"    ✓ PMC: {count} articles")
        else:
            await aprint(Fore.RED + "    ✗ PMC: Failed")
        
        # PMC BioC
        bioc = sources.get("pmc_bioc", {})
        if bioc.get("success"):
            bioc_data = bioc.get("data", {})
            fetched = bioc_data.get("total_fetched", 0)
            total = bioc_data.get("total_found", 0)
            await aprint(Fore.WHITE + f"    ✓ PMC BioC: {fetched}/{total} articles")
        else:
            await aprint(Fore.RED + "    ✗ PMC BioC: Failed")
        
        # Extended APIs
        extended = sources.get("extended", {})
        if extended:
            await aprint(Fore.CYAN + "\n  Extended Searches:")
            
            # DuckDuckGo
            if "duckduckgo" in extended:
                ddg = extended["duckduckgo"]
                if ddg.get("success"):
                    ddg_data = ddg.get("data", {})
                    count = ddg_data.get("total_found", 0)
                    await aprint(Fore.WHITE + f"    ✓ DuckDuckGo: {count} results")
                else:
                    await aprint(Fore.RED + f"    ✗ DuckDuckGo: {ddg.get('error', 'Failed')}")
            
            # SERP API
            if "serpapi" in extended:
                serp = extended["serpapi"]
                if serp.get("success"):
                    serp_data = serp.get("data", {})
                    count = serp_data.get("total_found", 0)
                    await aprint(Fore.WHITE + f"    ✓ Google Search: {count} results")
                else:
                    await aprint(Fore.RED + f"    ✗ Google Search: {serp.get('error', 'Failed')}")
            
            # Google Scholar
            if "scholar" in extended:
                scholar = extended["scholar"]
                if scholar.get("success"):
                    scholar_data = scholar.get("data", {})
                    count = scholar_data.get("total_found", 0)
                    await aprint(Fore.WHITE + f"    ✓ Google Scholar: {count} results")
                else:
                    await aprint(Fore.RED + f"    ✗ Google Scholar: {scholar.get('error', 'Failed')}")
            
            # OpenFDA
            if "openfda" in extended:
                fda = extended["openfda"]
                if fda.get("success"):
                    fda_data = fda.get("data", {})
                    count = fda_data.get("total_found", 0)
                    await aprint(Fore.WHITE + f"    ✓ OpenFDA: {count} drugs")
                else:
                    await aprint(Fore.RED + f"    ✗ OpenFDA: {fda.get('error', 'Failed')}")
    
    async def extract_from_nct(self, nct_id: str) -> str:
        """
        Extract structured data from specific NCT trial.
        Now uses API search + prompt generation.
        
        Args:
            nct_id: NCT number
            
        Returns:
            Formatted extraction text
        """
        # Use new search-based extraction
        return await self.search_and_extract(nct_id)
    
    async def query_with_rag_and_search(
        self, 
        query: str, 
        nct_id: Optional[str] = None
    ) -> str:
        """
        Answer query using RAG + API search.
        
        Args:
            query: User question
            nct_id: Optional specific NCT to search
            
        Returns:
            LLM answer
        """
        try:
            if nct_id:
                # Search specific trial
                await self.initialize_search()
                
                config = SearchConfig(use_extended_apis=False)
                search_results = await self.search_engine.search(nct_id, config)
                
                # Generate query prompt
                prompt = self.prompt_generator.generate_rag_query_prompt(
                    query,
                    search_results
                )
            else:
                # Use RAG from local database
                context = self.rag.get_context_for_llm(query, max_trials=10)
                
                prompt = f"""You are a clinical trial research assistant. Use the trial data below to answer the question.

Question: {query}

{context}

Provide a clear, well-structured answer based on the trial data above."""
            
            response = await self.session_manager.send_prompt(
                self.model_name, 
                prompt
            )
            
            if not response:
                return "Error: No response from LLM"
            
            return response
            
        except Exception as e:
            logger.error(f"Error in query: {e}", exc_info=True)
            return f"Error: {e}"
    
    async def query_with_rag(self, query: str, max_trials: int = 10) -> str:
        """
        Answer query using RAG system (legacy method).
        """
        return await self.query_with_rag_and_search(query, nct_id=None)
    
    async def run(self, ssh_connection, remote_host: str):
        """Main entry point for research assistant."""
        # Display header
        if HAS_RICH:
            from rich.panel import Panel
            await safe_print(Panel(
                "[bold cyan]🔬 Clinical Trial Research Assistant[/bold cyan]\n"
                "Multi-database search + RAG-powered analysis",
                border_style="cyan"
            ))
        else:
            await aprint(Fore.CYAN + Style.BRIGHT + "\n=== 🔬 Clinical Trial Research Assistant ===")
            await aprint(Fore.WHITE + "Multi-database search + RAG-powered analysis\n")
        
        await aprint(Fore.GREEN + f"✅ Indexed {len(self.rag.db.trials)} clinical trials")
        
        # Setup Ollama connection
        await aprint(Fore.CYAN + f"\n🔗 Connecting to Ollama at {remote_host}:11434...")
        
        try:
            async with OllamaSessionManager(remote_host, 11434, ssh_connection) as session:
                self.session_manager = session
                
                await aprint(Fore.GREEN + "✅ Connected to Ollama!")
                if session._using_tunnel:
                    await aprint(Fore.CYAN + "   (via SSH tunnel)")
                
                # List models
                models = await session.list_models()
                
                if not models:
                    await self._show_no_models_help()
                    return
                
                await aprint(Fore.GREEN + f"✅ Found {len(models)} model(s)")
                
                # Ensure custom model exists
                model_ready = await self._ensure_model_exists(ssh_connection, models)
                
                if not model_ready:
                    # Fallback to base model
                    await aprint(Fore.YELLOW + "\n⚠️  Custom model not available")
                    await aprint(Fore.CYAN + "Select a base model:")
                    
                    for i, model in enumerate(models, 1):
                        await aprint(Fore.WHITE + f"  {i}. {model}")
                    
                    choice = await ainput(Fore.GREEN + "Select model [1]: ")
                    choice = choice.strip()
                    
                    if choice.isdigit() and 0 < int(choice) <= len(models):
                        self.model_name = models[int(choice) - 1]
                    elif choice in models:
                        self.model_name = choice
                    else:
                        self.model_name = models[0]
                    
                    await aprint(Fore.YELLOW + f"Using: {self.model_name}")
                
                await aprint(Fore.GREEN + f"\n✅ Using model: {self.model_name}")
                
                # Initialize command handler
                if HAS_COMMANDS:
                    self.command_handler = CommandHandler(self)
                    await self.command_handler.cmd_help()
                else:
                    await aprint(Fore.YELLOW + "⚠️  Command handler not available")
                    await self._show_basic_help()
                
                # Main interaction loop
                await self._interaction_loop()
                
        except ConnectionError as e:
            await aprint(Fore.RED + f"❌ Connection failed: {e}")
            logger.error(f"Connection error: {e}")
        except Exception as e:
            await aprint(Fore.RED + f"❌ Error: {e}")
            logger.error(f"Research assistant error: {e}", exc_info=True)
        finally:
            # Cleanup search engine
            if self.search_initialized:
                await self.search_engine.close()
                await aprint(Fore.CYAN + "🔒 Search engine closed")
    
    async def _show_basic_help(self):
        """Show basic help when command handler not available."""
        await aprint(Fore.CYAN + "\n📖 Basic Commands:")
        await aprint(Fore.WHITE + "  extract <NCT_ID>       - Extract data from trial")
        await aprint(Fore.WHITE + "  extract-ext <NCT_ID>   - Extract with extended APIs")
        await aprint(Fore.WHITE + "  search <NCT_ID>        - Search databases for trial")
        await aprint(Fore.WHITE + "  config-apis            - Configure default API settings")
        await aprint(Fore.WHITE + "  query <question>       - Ask about trials")
        await aprint(Fore.WHITE + "  exit/quit              - Return to main menu")
    
    async def _interaction_loop(self):
        """Main interaction loop with command handling."""
        while True:
            try:
                user_input = await ainput(Fore.GREEN + "\nResearch >>> " + Style.RESET_ALL)
                user_input = user_input.strip()
                
                if not user_input:
                    continue
                
                # Handle commands if available
                if HAS_COMMANDS and self.command_handler:
                    should_continue = await self.command_handler.handle_command(user_input)
                    if not should_continue:
                        break
                else:
                    # Basic command mode
                    if user_input.lower() in ('exit', 'quit', 'main menu'):
                        await aprint(Fore.YELLOW + "Returning to main menu...")
                        break
                    
                    # Parse basic commands
                    parts = user_input.split(maxsplit=1)
                    command = parts[0].lower()
                    args = parts[1] if len(parts) > 1 else ""
                    
                    if command == "extract" and args:
                        nct_id = args.strip()
                        await aprint(Fore.YELLOW + f"\n🔍 Extracting data for {nct_id}...")
                        response = await self.extract_from_nct(nct_id)
                        await aprint(Fore.CYAN + "\n📝 Extraction:")
                        await aprint(Fore.WHITE + response)
                    
                    elif command == "extract-ext" and args:
                        nct_id = args.strip()
                        await aprint(Fore.YELLOW + f"\n🔍 Extracting with extended APIs for {nct_id}...")
                        response = await self.search_and_extract(nct_id, use_extended=True)
                        await aprint(Fore.CYAN + "\n📝 Extraction:")
                        await aprint(Fore.WHITE + response)
                    
                    elif command == "search" and args:
                        nct_id = args.strip()
                        await aprint(Fore.YELLOW + f"\n🔍 Searching for {nct_id}...")
                        
                        # Ask about extended APIs
                        use_ext = await ainput(Fore.CYAN + "Use extended APIs? (y/n) [n]: ")
                        use_extended = use_ext.strip().lower() in ('y', 'yes')
                        
                        await self.initialize_search()
                        
                        if use_extended:
                            enabled_dbs = await self._select_extended_apis()
                            config = SearchConfig(
                                use_extended_apis=True,
                                enabled_databases=enabled_dbs
                            )
                        else:
                            config = SearchConfig(use_extended_apis=False)
                        
                        results = await self.search_engine.search(nct_id, config)
                        await self._display_search_summary(results)
                        
                        # Optionally display full results
                        show_full = await ainput(Fore.CYAN + "\nShow full results? (y/n) [n]: ")
                        if show_full.lower() in ('y', 'yes'):
                            import json
                            await aprint(Fore.WHITE + json.dumps(results, indent=2))
                    
                    elif command == "config-apis":
                        await self._configure_api_defaults()
                    
                    elif command == "query" and args:
                        await aprint(Fore.YELLOW + "\n🤔 Processing query...")
                        response = await self.query_with_rag(args)
                        await aprint(Fore.CYAN + "\n📝 Response:")
                        await aprint(Fore.WHITE + response)
                    
                    else:
                        # Simple query (no command prefix)
                        await aprint(Fore.YELLOW + "\n🤔 Processing query...")
                        response = await self.query_with_rag(user_input)
                        await aprint(Fore.CYAN + "\n📝 Response:")
                        await aprint(Fore.WHITE + response)
                    
            except KeyboardInterrupt:
                await aprint(Fore.YELLOW + "\n\nInterrupted. Type 'exit' to quit.")
                continue
            except Exception as e:
                await aprint(Fore.RED + f"\n❌ Error: {e}")
                logger.error(f"Interaction error: {e}", exc_info=True)
    
    async def _configure_api_defaults(self):
        """Configure default API settings."""
        import os
        
        await aprint(Fore.CYAN + "\n⚙️  API Configuration")
        await aprint(Fore.WHITE + "=" * 60)
        
        # Check current status
        has_serpapi = bool(os.getenv('SERPAPI_KEY'))
        has_ncbi = bool(os.getenv('NCBI_API_KEY'))
        
        await aprint(Fore.CYAN + "\n📊 Current API Status:")
        await aprint(Fore.WHITE + f"  SERPAPI_KEY: {'✓ Set' if has_serpapi else '✗ Not set'}")
        await aprint(Fore.WHITE + f"  NCBI_API_KEY: {'✓ Set' if has_ncbi else '✗ Not set'}")
        
        await aprint(Fore.CYAN + "\n📋 Available Extended APIs:")
        await aprint(Fore.WHITE + "  1) DuckDuckGo - Free web search")
        await aprint(Fore.WHITE + "  2) Google Search - Requires SERPAPI_KEY")
        await aprint(Fore.WHITE + "  3) Google Scholar - Requires SERPAPI_KEY")
        await aprint(Fore.WHITE + "  4) OpenFDA - Free drug database")
        
        if not has_serpapi:
            await aprint(Fore.YELLOW + "\n💡 Tip: Get a free SERPAPI key at https://serpapi.com")
            await aprint(Fore.YELLOW + "   Then set: export SERPAPI_KEY='your_key'")
        
        if not has_ncbi:
            await aprint(Fore.YELLOW + "\n💡 Tip: Get a free NCBI key at https://www.ncbi.nlm.nih.gov/account/")
            await aprint(Fore.YELLOW + "   Then set: export NCBI_API_KEY='your_key'")
            await aprint(Fore.YELLOW + "   Increases PubMed/PMC rate limits from 3/sec to 10/sec")
    
    async def _ensure_model_exists(
        self, 
        ssh_connection, 
        available_models: list
    ) -> bool:
        """
        Ensure Research Assistant model exists.
        
        Args:
            ssh_connection: SSH connection
            available_models: List of available models
            
        Returns:
            True if model ready
        """
        # Check if research assistant already exists
        model_variants = [
            self.model_name,
            f"{self.model_name}:latest"
        ]
        
        model_found = any(variant in available_models for variant in model_variants)
        
        if model_found:
            await aprint(Fore.GREEN + f"✅ Found existing model: {self.model_name}")
            
            # Ask if user wants to use it
            use_existing = await ainput(
                Fore.CYAN + 
                f"\nUse existing '{self.model_name}'? (y/n/rebuild) [y]: "
            )
            
            choice = use_existing.strip().lower()
            
            if choice in ('', 'y', 'yes'):
                await aprint(Fore.GREEN + f"\n✅ Using existing Research Assistant model")
                return True
            elif choice == 'rebuild':
                await aprint(Fore.YELLOW + f"\n🔄 Rebuilding model...")
                # Fall through to rebuild
            else:
                return False
        
        # Model doesn't exist or user wants to rebuild
        await aprint(Fore.CYAN + "\n🔬 Research Assistant Setup")
        await aprint(Fore.WHITE + "Building specialized clinical trial research model...\n")
        
        # Filter base models (exclude custom models)
        base_models = [m for m in available_models 
                    if not m.startswith('ct-research-assistant') 
                    and not m.startswith('amp-assistant')]
        
        if not base_models:
            await aprint(Fore.RED + "❌ No base models available")
            return False
        
        await aprint(Fore.CYAN + f"📋 Select base model for Research Assistant:")
        for i, model in enumerate(base_models, 1):
            marker = "→" if model == base_models[0] else " "
            await aprint(Fore.WHITE + f"  {marker} {i}) {model}")
        
        choice = await ainput(Fore.GREEN + "Select base model [1]: ")
        choice = choice.strip() or "1"
        
        # Parse choice
        base_model = None
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(base_models):
                base_model = base_models[idx]
        elif choice in base_models:
            base_model = choice
        
        if not base_model:
            base_model = base_models[0]
        
        await aprint(Fore.GREEN + f"✅ Selected: {base_model}\n")
        await aprint(Fore.CYAN + f"🔨 Building '{self.model_name}' from '{base_model}'...")
        
        # Build model
        from amp_llm.llm.models.builder import build_custom_model
        
        success = await build_custom_model(
            ssh_connection,
            self.model_name,
            base_models,
            selected_base_model=base_model
        )
        
        if success:
            await aprint(Fore.GREEN + "\n" + "="*60)
            await aprint(Fore.GREEN + f"✅ Research Assistant Ready!")
            await aprint(Fore.CYAN + f"   Model: {self.model_name}")
            await aprint(Fore.CYAN + f"   Base LLM: {base_model}")
            await aprint(Fore.CYAN + f"   Capabilities: API Search, RAG, Extraction, Analysis")
            await aprint(Fore.GREEN + "="*60 + "\n")
            return True
        else:
            await aprint(Fore.RED + f"❌ Failed to create '{self.model_name}'")
            return False
    
    async def _show_no_models_help(self):
        """Show help when no models found."""
        await aprint(Fore.RED + "❌ No models found on remote server")
        await aprint(Fore.YELLOW + "\nTo install models:")
        await aprint(Fore.WHITE + "  1. SSH to remote server")
        await aprint(Fore.WHITE + "  2. Run: ollama pull llama3.2")
        await aprint(Fore.WHITE + "  3. Run: ollama list (to verify)")
