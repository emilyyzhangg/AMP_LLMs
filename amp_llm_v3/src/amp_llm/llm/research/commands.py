# amp_llm/src/amp_llm/llm/research/commands.py
"""
Enhanced Command handler for Research Assistant with interactive menus.
Processes user commands and routes to appropriate functions.
"""
import json
from pathlib import Path
from typing import Dict, Callable, List, Optional
from colorama import Fore, Style

try:
    from aioconsole import ainput, aprint
except ImportError:
    async def ainput(prompt):
        return input(prompt)
    async def aprint(*args, **kwargs):
        print(*args, **kwargs)

from amp_llm.config import get_logger

# Try to import validation config
try:
    from amp_llm.config.validation import get_validation_config
    HAS_VALIDATION = True
except ImportError:
    HAS_VALIDATION = False

logger = get_logger(__name__)


class CommandHandler:
    """Handles Research Assistant commands with interactive menus."""
    
    def __init__(self, assistant):
        """
        Initialize command handler.
        
        Args:
            assistant: ClinicalTrialResearchAssistant instance
        """
        self.assistant = assistant
        
        if HAS_VALIDATION:
            self.validation_config = get_validation_config()
        else:
            self.validation_config = None
        
        # Command registry
        self.commands: Dict[str, Callable] = {
            'help': self.cmd_help,
            '!help': self.cmd_help,
            '?': self.cmd_help,
            'menu': self.show_main_menu,
            'search': self.cmd_search,
            'extract': self.cmd_extract,
            'save': self.cmd_save,
            'query': self.cmd_query,
            'stats': self.cmd_stats,
            'validate': self.cmd_validate,
            'status': self.cmd_status,
        }
    
    async def show_main_menu(self, args: str = "") -> Optional[str]:
        """
        Display main menu and get user choice.
        
        Returns:
            Selected command or None
        """
        await aprint(Fore.CYAN + Style.BRIGHT + "\n" + "="*60)
        await aprint(Fore.CYAN + Style.BRIGHT + "  🧬 RESEARCH ASSISTANT - MAIN MENU")
        await aprint(Fore.CYAN + Style.BRIGHT + "="*60 + Style.RESET_ALL)
        
        menu_options = [
            ("1", "🔍 Search & Analyze Trials", "search"),
            ("2", "📋 Extract Trial Data (by NCT)", "extract"),
            ("3", "💾 Quick Save Trial (by NCT)", "save"),
            ("4", "💡 Ask Question (RAG Query)", "query"),
            ("5", "📊 Database Statistics", "stats"),
            ("6", "✅ Field Validation Info", "validate"),
            ("7", "🔌 Connection Status", "status"),
            ("8", "❓ Help & Commands", "help"),
            ("9", "🚪 Exit to Main Menu", "exit"),
        ]
        
        await aprint(Fore.WHITE + "")
        for num, desc, _ in menu_options:
            await aprint(Fore.CYAN + f"  [{num}] " + Fore.WHITE + desc)
        
        await aprint(Fore.CYAN + "\n" + "-"*60)
        await aprint(Fore.YELLOW + "💬 You can also type commands directly or ask questions!\n")
        
        choice = await ainput(Fore.GREEN + "Select option [1-9] or enter command: " + Fore.RESET)
        
        # Map number to command
        choice = choice.strip()
        for num, _, cmd in menu_options:
            if choice == num:
                return cmd
        
        # Return raw input if not a menu number
        return choice if choice else None
    
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
        if user_input.lower() in ('exit', 'quit', 'main menu', '9'):
            await aprint(Fore.YELLOW + "🚪 Returning to main menu...")
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
                await aprint(Fore.RED + f"❌ Command error: {e}")
                logger.error(f"Command '{command}' failed: {e}", exc_info=True)
        else:
            # Treat as query
            await self.cmd_query(user_input)
        
        return True
    
    async def cmd_help(self, args: str = ""):
        """Display help information."""
        await aprint(Fore.CYAN + Style.BRIGHT + "\n💡 Research Assistant Commands:" + Style.RESET_ALL)
        await aprint(Fore.CYAN + "\n📌 Basic Commands:")
        await aprint(Fore.WHITE + "   • " + Fore.CYAN + "menu" + Fore.WHITE + " - Show interactive menu")
        await aprint(Fore.WHITE + "   • " + Fore.CYAN + "help" + Fore.WHITE + " or " + Fore.CYAN + "!help" + Fore.WHITE + " or " + Fore.CYAN + "?" + Fore.WHITE + " - Show this help")
        
        await aprint(Fore.CYAN + "\n🔍 Search & Analysis:")
        await aprint(Fore.WHITE + "   • " + Fore.CYAN + "search <query>" + Fore.WHITE + " - Search database and analyze trials")
        await aprint(Fore.WHITE + "   • " + Fore.CYAN + "query <question> [--limit N]" + Fore.WHITE + " - Ask question (default limit: 10)")
        
        await aprint(Fore.CYAN + "\n📋 Data Extraction:")
        await aprint(Fore.WHITE + "   • " + Fore.CYAN + "extract <NCT>" + Fore.WHITE + " - Extract structured data from specific trial")
        await aprint(Fore.WHITE + "   • " + Fore.CYAN + "save <NCT>" + Fore.WHITE + " - Extract and save directly as JSON")
        
        await aprint(Fore.CYAN + "\n📊 Information:")
        await aprint(Fore.WHITE + "   • " + Fore.CYAN + "stats" + Fore.WHITE + " - Show database statistics")
        if HAS_VALIDATION:
            await aprint(Fore.WHITE + "   • " + Fore.CYAN + "validate" + Fore.WHITE + " - Show valid values for all fields")
        await aprint(Fore.WHITE + "   • " + Fore.CYAN + "status" + Fore.WHITE + " - Check connection status")
        
        await aprint(Fore.CYAN + "\n🚪 Exit:")
        await aprint(Fore.WHITE + "   • " + Fore.CYAN + "exit" + Fore.WHITE + " or " + Fore.CYAN + "quit" + Fore.WHITE + " or " + Fore.CYAN + "main menu" + Fore.WHITE + " - Return to main menu\n")
    
    async def cmd_search(self, args: str):
        """Search database for trials with interactive workflow."""
        if not args:
            await aprint(Fore.YELLOW + "\n🔍 Search Database")
            await aprint(Fore.CYAN + "-" * 40)
            query = await ainput(Fore.GREEN + "Enter search query: " + Fore.RESET)
            if not query.strip():
                await aprint(Fore.RED + "❌ Search cancelled")
                return
            args = query
        
        await aprint(Fore.YELLOW + f"\n🔍 Searching for: {args}")
        nct_ids = self.assistant.rag.db.search(args)
        
        if not nct_ids:
            await aprint(Fore.RED + "❌ No trials found matching query\n")
            return
        
        await aprint(Fore.GREEN + f"✅ Found {len(nct_ids)} trial(s):")
        for i, nct in enumerate(nct_ids, 1):
            await aprint(Fore.CYAN + f"  {i}. {nct}")
        
        # Interactive analysis menu
        await aprint(Fore.CYAN + "\n📊 What would you like to do?")
        await aprint(Fore.WHITE + "  [1] Analyze with AI")
        await aprint(Fore.WHITE + "  [2] Extract specific trial")
        await aprint(Fore.WHITE + "  [3] Show trial list only")
        await aprint(Fore.WHITE + "  [4] Cancel")
        
        choice = await ainput(Fore.GREEN + "\nSelect option [1-4]: " + Fore.RESET)
        
        if choice == "1":
            await aprint(Fore.YELLOW + "\n🤔 Analyzing trials...")
            response = await self.assistant.query_with_rag(args)
            
            if not response or response.startswith("Error:"):
                await aprint(Fore.RED + f"\n{response}\n")
            else:
                await aprint(Fore.GREEN + "\n📊 Analysis:\n")
                await aprint(Fore.WHITE + response + "\n")
                
                # Offer to save analysis
                save = await ainput(Fore.CYAN + "💾 Save this analysis? (y/n): ")
                if save.lower() in ('y', 'yes'):
                    await self._save_analysis(args, response)
        
        elif choice == "2":
            if len(nct_ids) == 1:
                await self.cmd_extract(nct_ids[0])
            else:
                trial_num = await ainput(Fore.GREEN + f"Enter trial number [1-{len(nct_ids)}]: ")
                try:
                    idx = int(trial_num) - 1
                    if 0 <= idx < len(nct_ids):
                        await self.cmd_extract(nct_ids[idx])
                    else:
                        await aprint(Fore.RED + "❌ Invalid trial number")
                except ValueError:
                    await aprint(Fore.RED + "❌ Invalid input")
        
        elif choice == "3":
            await aprint(Fore.GREEN + "✅ Trial list displayed above\n")
        
        else:
            await aprint(Fore.YELLOW + "❌ Search cancelled\n")
    
    async def cmd_extract(self, args: str):
        """Extract data from specific trial with save options."""
        if not args:
            await aprint(Fore.YELLOW + "\n📋 Extract Trial Data")
            await aprint(Fore.CYAN + "-" * 40)
            nct = await ainput(Fore.GREEN + "Enter NCT number: " + Fore.RESET)
            if not nct.strip():
                await aprint(Fore.RED + "❌ Extraction cancelled")
                return
            args = nct
        
        nct = args.upper().strip()
        await aprint(Fore.YELLOW + f"\n📋 Extracting data for {nct}...")
        
        response = await self.assistant.extract_from_nct(nct)
        
        if not response or response.startswith("Error:") or response.startswith("NCT number") or response.startswith("Could not"):
            await aprint(Fore.RED + f"\n❌ {response}\n")
        else:
            await aprint(Fore.GREEN + "\n✅ Structured Extraction:")
            await aprint(Fore.WHITE + response)
            
            # Save options menu
            await aprint(Fore.CYAN + "\n💾 Save Options:")
            await aprint(Fore.WHITE + "  [1] Save as JSON")
            await aprint(Fore.WHITE + "  [2] Save as Text")
            await aprint(Fore.WHITE + "  [3] Don't save")
            
            save_choice = await ainput(Fore.GREEN + "\nSelect option [1-3]: " + Fore.RESET)
            
            if save_choice == "1":
                await self._save_extraction(nct, response, 'json')
            elif save_choice == "2":
                await self._save_extraction(nct, response, 'txt')
            else:
                await aprint(Fore.YELLOW + "✅ Extraction complete (not saved)\n")
    
    async def cmd_save(self, args: str):
        """Extract and save trial directly."""
        if not args:
            await aprint(Fore.YELLOW + "\n💾 Quick Save Trial")
            await aprint(Fore.CYAN + "-" * 40)
            nct = await ainput(Fore.GREEN + "Enter NCT number: " + Fore.RESET)
            if not nct.strip():
                await aprint(Fore.RED + "❌ Save cancelled")
                return
            args = nct
        
        nct = args.upper().strip()
        await aprint(Fore.YELLOW + f"\n💾 Extracting and saving {nct}...")
        
        response = await self.assistant.extract_from_nct(nct)
        
        if not response or response.startswith("Error:"):
            await aprint(Fore.RED + f"\n❌ {response}\n")
            return
        
        await self._save_extraction(nct, response, 'json')
    
    async def cmd_query(self, args: str):
        """Query database with AI."""
        if not args:
            await aprint(Fore.YELLOW + "\n💡 Ask Question")
            await aprint(Fore.CYAN + "-" * 40)
            query_text = await ainput(Fore.GREEN + "Enter your question: " + Fore.RESET)
            if not query_text.strip():
                await aprint(Fore.RED + "❌ Query cancelled")
                return
            
            limit_input = await ainput(Fore.CYAN + "Max trials to analyze [10]: " + Fore.RESET)
            try:
                max_trials = int(limit_input) if limit_input.strip() else 10
            except ValueError:
                max_trials = 10
                await aprint(Fore.YELLOW + "⚠️  Invalid number, using default (10)")
        else:
            max_trials = 10
            query_text = args
            
            if '--limit' in args:
                parts = args.split('--limit')
                query_text = parts[0].strip()
                try:
                    limit_str = parts[1].strip().split()[0]
                    max_trials = int(limit_str)
                except (ValueError, IndexError):
                    await aprint(Fore.YELLOW + "⚠️  Invalid --limit value, using default (10)")
        
        await aprint(Fore.YELLOW + f"\n🤔 Processing query (max {max_trials} trials)...")
        response = await self.assistant.query_with_rag(query_text, max_trials=max_trials)
        
        if not response or response.startswith("Error:"):
            await aprint(Fore.RED + f"\n❌ {response}\n")
        else:
            await aprint(Fore.GREEN + "\n💡 Answer:\n")
            await aprint(Fore.WHITE + response + "\n")
            
            # Offer to save response
            save = await ainput(Fore.CYAN + "💾 Save this answer? (y/n): ")
            if save.lower() in ('y', 'yes'):
                await self._save_analysis(query_text, response)
    
    async def cmd_stats(self, args: str = ""):
        """Show database statistics."""
        await aprint(Fore.CYAN + Style.BRIGHT + "\n📊 Database Statistics")
        await aprint(Fore.CYAN + "="*50 + Style.RESET_ALL)
        
        total = len(self.assistant.rag.db.trials)
        await aprint(Fore.WHITE + f"  Total trials: " + Fore.GREEN + f"{total}")
        
        status_counts = {}
        peptide_count = 0
        phase_counts = {}
        
        for nct, trial in self.assistant.rag.db.trials.items():
            try:
                extraction = self.assistant.rag.db.extract_structured_data(nct)
                if extraction:
                    status = extraction.study_status
                    status_counts[status] = status_counts.get(status, 0) + 1
                    if hasattr(extraction, 'is_peptide') and extraction.is_peptide:
                        peptide_count += 1
                    if hasattr(extraction, 'phase'):
                        phase = extraction.phase
                        phase_counts[phase] = phase_counts.get(phase, 0) + 1
            except:
                pass
        
        await aprint(Fore.WHITE + f"  Peptide trials: " + Fore.GREEN + f"{peptide_count}")
        
        if status_counts:
            await aprint(Fore.CYAN + "\n  📋 By Status:")
            for status, count in sorted(status_counts.items(), key=lambda x: x[1], reverse=True):
                await aprint(Fore.WHITE + f"    • {status}: " + Fore.GREEN + f"{count}")
        
        if phase_counts:
            await aprint(Fore.CYAN + "\n  🔬 By Phase:")
            for phase, count in sorted(phase_counts.items(), key=lambda x: x[1], reverse=True):
                await aprint(Fore.WHITE + f"    • {phase}: " + Fore.GREEN + f"{count}")
        
        await aprint("")
    
    async def cmd_validate(self, args: str = ""):
        """Show valid values for all fields."""
        if not HAS_VALIDATION:
            await aprint(Fore.YELLOW + "⚠️  Validation config not available\n")
            return
        
        display = self.validation_config.format_valid_values_display()
        await aprint(Fore.CYAN + display + "\n")
    
    async def cmd_status(self, args: str = ""):
        """Check connection status."""
        await aprint(Fore.CYAN + "\n🔌 Checking connection status...")
        is_alive = await self.assistant.session_manager.is_alive()
        
        if is_alive:
            await aprint(Fore.GREEN + "✅ Connection is healthy\n")
        else:
            await aprint(Fore.RED + "❌ Connection is down")
            await aprint(Fore.YELLOW + "🔄 Attempting to reconnect...")
            await self.assistant.session_manager.start_session()
            is_alive = await self.assistant.session_manager.is_alive()
            
            if is_alive:
                await aprint(Fore.GREEN + "✅ Reconnected successfully\n")
            else:
                await aprint(Fore.RED + "❌ Reconnection failed\n")
    
    async def _save_extraction(self, nct: str, response: str, format: str):
        """Helper to save extraction to file."""
        try:
            # Try to import response parser
            try:
                from amp_llm.llm.response_parser import parse_extraction_to_dict
                has_parser = True
            except ImportError:
                has_parser = False
            
            default_filename = f"{nct}_extraction"
            filename = await ainput(Fore.CYAN + f"📝 Filename (without extension) [{default_filename}]: ")
            filename = filename.strip() or default_filename
            
            output_dir = Path('output')
            output_dir.mkdir(exist_ok=True)
            output_path = output_dir / f"{filename}.{format}"
            
            if format == 'json' and has_parser:
                extraction_dict = parse_extraction_to_dict(response)
                
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(extraction_dict, f, indent=2, ensure_ascii=False)
                
                await aprint(Fore.GREEN + f"✅ Saved as JSON: {output_path}\n")
            else:
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(response)
                
                file_type = "JSON" if format == 'json' else "text"
                await aprint(Fore.GREEN + f"✅ Saved as {file_type}: {output_path}\n")
            
            logger.info(f"Saved extraction to {output_path}")
            
        except Exception as e:
            await aprint(Fore.RED + f"❌ Error saving: {e}\n")
            logger.error(f"Error saving extraction: {e}", exc_info=True)
    
    async def _save_analysis(self, query: str, response: str):
        """Helper to save analysis/query response to file."""
        try:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_filename = f"analysis_{timestamp}"
            
            filename = await ainput(Fore.CYAN + f"📝 Filename (without extension) [{default_filename}]: ")
            filename = filename.strip() or default_filename
            
            output_dir = Path('output')
            output_dir.mkdir(exist_ok=True)
            output_path = output_dir / f"{filename}.txt"
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(f"Query: {query}\n")
                f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                f.write("="*60 + "\n\n")
                f.write(response)
            
            await aprint(Fore.GREEN + f"✅ Saved analysis: {output_path}\n")
            logger.info(f"Saved analysis to {output_path}")
            
        except Exception as e:
            await aprint(Fore.RED + f"❌ Error saving analysis: {e}\n")
            logger.error(f"Error saving analysis: {e}", exc_info=True)