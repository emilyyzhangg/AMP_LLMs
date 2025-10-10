"""
Command handler for Research Assistant.
Processes user commands and routes to appropriate functions.
"""
import json
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from colorama import Fore
from config import get_logger
from config.validation import get_validation_config

try:
    from aioconsole import ainput, aprint
except ImportError:
    async def ainput(prompt):
        return input(prompt)
    async def aprint(*args, **kwargs):
        print(*args, **kwargs)

logger = get_logger(__name__)


class CommandHandler:
    """Handles Research Assistant commands."""
    
    def __init__(self, assistant):
        """
        Initialize command handler.
        
        Args:
            assistant: ClinicalTrialResearchAssistant instance
        """
        self.assistant = assistant
        self.validation_config = get_validation_config()
        
        # Command registry
        self.commands: Dict[str, Callable] = {
            'help': self.cmd_help,
            '!help': self.cmd_help,
            '?': self.cmd_help,
            'search': self.cmd_search,
            'extract': self.cmd_extract,
            'save': self.cmd_save,
            'query': self.cmd_query,
            'stats': self.cmd_stats,
            'validate': self.cmd_validate,
            'status': self.cmd_status,
        }
    
    async def handle_command(self, user_input: str) -> bool:
        """
        Handle user command.
        
        Args:
            user_input: Raw user input
            
        Returns:
            True if should continue, False if should exit
        """
        user_input = user_input.strip()
        
        if not user_input:
            return True
        
        # Check for exit commands
        if user_input.lower() in ('exit', 'quit', 'main menu'):
            await aprint(Fore.YELLOW + "Returning to main menu...")
            return False
        
        # Parse command and arguments
        parts = user_input.split(maxsplit=1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        
        # Look up command
        if command in self.commands:
            try:
                await self.commands[command](args)
            except Exception as e:
                await aprint(Fore.RED + f"Command error: {e}")
                logger.error(f"Command '{command}' failed: {e}", exc_info=True)
        else:
            # Treat as query
            await self.cmd_query(user_input)
        
        return True
    
    async def cmd_help(self, args: str = ""):
        """Display help information."""
        await aprint(Fore.CYAN + "\n💡 Research Assistant Commands:")
        await aprint(Fore.CYAN + "   • 'help' or '!help' or '?' - Show this help")
        await aprint(Fore.CYAN + "   • 'search <query>' - Search database and analyze trials")
        await aprint(Fore.CYAN + "   • 'extract <NCT>' - Extract structured data from specific trial")
        await aprint(Fore.CYAN + "   • 'save <NCT>' - Extract and save directly as JSON")
        await aprint(Fore.CYAN + "   • 'query <question> [--limit N]' - Ask question (default limit: 10)")
        await aprint(Fore.CYAN + "   • 'stats' - Show database statistics")
        await aprint(Fore.CYAN + "   • 'validate' - Show valid values for all fields")
        await aprint(Fore.CYAN + "   • 'status' - Check connection status")
        await aprint(Fore.CYAN + "   • 'exit' or 'quit' or 'main menu' - Return to main menu\n")
    
    async def cmd_search(self, args: str):
        """Search database for trials."""
        if not args:
            await aprint(Fore.RED + "Usage: search <query>")
            return
        
        await aprint(Fore.YELLOW + f"\n🔍 Searching for: {args}")
        nct_ids = self.assistant.rag.db.search(args)
        
        if not nct_ids:
            await aprint(Fore.RED + "No trials found matching query")
            return
        
        await aprint(Fore.GREEN + f"Found {len(nct_ids)} trial(s):")
        for nct in nct_ids:
            await aprint(Fore.CYAN + f"  • {nct}")
        
        analyze = await ainput(Fore.CYAN + "\nAnalyze these trials with AI? (y/n): ")
        
        if analyze.lower() in ('y', 'yes'):
            await aprint(Fore.YELLOW + "\n🤔 Analyzing trials...")
            response = await self.assistant.query_with_rag(args)
            
            if not response or response.startswith("Error:"):
                await aprint(Fore.RED + f"\n{response}\n")
            else:
                await aprint(Fore.GREEN + "\n📊 Analysis:\n")
                await aprint(Fore.WHITE + response + "\n")
    
    async def cmd_extract(self, args: str):
        """Extract data from specific trial."""
        if not args:
            await aprint(Fore.RED + "Usage: extract <NCT_NUMBER>")
            return
        
        nct = args.upper().strip()
        await aprint(Fore.YELLOW + f"\n📋 Extracting data for {nct}...")
        
        response = await self.assistant.extract_from_nct(nct)
        
        if not response or response.startswith("Error:") or response.startswith("NCT number") or response.startswith("Could not"):
            await aprint(Fore.RED + f"\n{response}\n")
        else:
            await aprint(Fore.GREEN + "\n📊 Structured Extraction:")
            await aprint(Fore.WHITE + response)
            
            save_choice = await ainput(Fore.CYAN + "\nSave this extraction? (json/txt/no) [no]: ")
            save_choice = save_choice.strip().lower()
            
            if save_choice in ('json', 'txt'):
                await self._save_extraction(nct, response, save_choice)
    
    async def cmd_save(self, args: str):
        """Extract and save trial directly."""
        if not args:
            await aprint(Fore.RED + "Usage: save <NCT_NUMBER>")
            return
        
        nct = args.upper().strip()
        await aprint(Fore.YELLOW + f"\n💾 Extracting and saving {nct}...")
        
        response = await self.assistant.extract_from_nct(nct)
        
        if not response or response.startswith("Error:"):
            await aprint(Fore.RED + f"\n{response}\n")
            return
        
        await self._save_extraction(nct, response, 'json')
    
    async def cmd_query(self, args: str):
        """Query database with AI."""
        if not args:
            await aprint(Fore.RED + "Usage: query <question> [--limit N]")
            return
        
        max_trials = 10
        query_text = args
        
        if '--limit' in args:
            parts = args.split('--limit')
            query_text = parts[0].strip()
            try:
                limit_str = parts[1].strip().split()[0]
                max_trials = int(limit_str)
            except (ValueError, IndexError):
                await aprint(Fore.YELLOW + "Invalid --limit value, using default (10)")
        
        await aprint(Fore.YELLOW + f"\n🤔 Processing query (max {max_trials} trials)...")
        response = await self.assistant.query_with_rag(query_text, max_trials=max_trials)
        
        if not response or response.startswith("Error:"):
            await aprint(Fore.RED + f"\n{response}\n")
        else:
            await aprint(Fore.GREEN + "\n💡 Answer:\n")
            await aprint(Fore.WHITE + response + "\n")
    
    async def cmd_stats(self, args: str = ""):
        """Show database statistics."""
        total = len(self.assistant.rag.db.trials)
        await aprint(Fore.CYAN + f"\n📊 Database Statistics:")
        await aprint(Fore.WHITE + f"  Total trials: {total}")
        
        status_counts = {}
        peptide_count = 0
        
        for nct, trial in self.assistant.rag.db.trials.items():
            try:
                extraction = self.assistant.rag.db.extract_structured_data(nct)
                if extraction:
                    status = extraction.study_status
                    status_counts[status] = status_counts.get(status, 0) + 1
                    if extraction.is_peptide:
                        peptide_count += 1
            except:
                pass
        
        await aprint(Fore.WHITE + f"  Peptide trials: {peptide_count}")
        await aprint(Fore.CYAN + "\n  By Status:")
        for status, count in sorted(status_counts.items()):
            await aprint(Fore.WHITE + f"    {status}: {count}")
        
        await aprint("")
    
    async def cmd_validate(self, args: str = ""):
        """Show valid values for all fields."""
        display = self.validation_config.format_valid_values_display()
        await aprint(Fore.CYAN + display + "\n")
    
    async def cmd_status(self, args: str = ""):
        """Check connection status."""
        is_alive = await self.assistant.session_manager.is_alive()
        if is_alive:
            await aprint(Fore.GREEN + "✅ Connection is healthy")
        else:
            await aprint(Fore.RED + "❌ Connection is down")
            await aprint(Fore.YELLOW + "Attempting to reconnect...")
            await self.assistant.session_manager.start_session()
            is_alive = await self.assistant.session_manager.is_alive()
            if is_alive:
                await aprint(Fore.GREEN + "✅ Reconnected successfully")
            else:
                await aprint(Fore.RED + "❌ Reconnection failed")
    
    async def _save_extraction(self, nct: str, response: str, format: str):
        """Helper to save extraction to file."""
        from llm.response_parser import parse_extraction_to_dict
        
        try:
            default_filename = f"{nct}_extraction"
            filename = await ainput(Fore.CYAN + f"Filename (without extension) [{default_filename}]: ")
            filename = filename.strip() or default_filename
            
            output_dir = Path('output')
            output_dir.mkdir(exist_ok=True)
            output_path = output_dir / f"{filename}.{format}"
            
            if format == 'json':
                extraction_dict = parse_extraction_to_dict(response)
                
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(extraction_dict, f, indent=2, ensure_ascii=False)
                
                await aprint(Fore.GREEN + f"✅ Saved as JSON: {output_path}")
            else:
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(response)
                
                await aprint(Fore.GREEN + f"✅ Saved as text: {output_path}")
            
            logger.info(f"Saved extraction to {output_path}")
            
        except Exception as e:
            await aprint(Fore.RED + f"❌ Error saving: {e}")
            logger.error(f"Error saving extraction: {e}", exc_info=True)