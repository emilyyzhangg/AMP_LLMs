"""
Enhanced LLM workflow handlers with interactive menu and file loading.
Includes paste mode, file loading, and trial-specific operations.
"""
import asyncio
import time
from pathlib import Path
from colorama import Fore, Style

try:
    from aioconsole import ainput, aprint
except ImportError:
    async def ainput(prompt):
        return input(prompt)
    async def aprint(*args, **kwargs):
        print(*args, **kwargs)

from amp_llm.config import get_logger
from amp_llm.llm.utils.session import OllamaSessionManager
from amp_llm.llm.utils.interactive import (
    handle_paste_command,
    handle_load_command,
    list_output_files,
    show_pwd,
)

logger = get_logger(__name__)


async def run_llm_entrypoint_api(ssh_manager):
    """
    Enhanced LLM workflow with interactive menu options.
    
    Features:
    - Paste mode for multi-line input
    - File loading from output/ directory
    - Trial-specific questions
    - Custom model building
    - Automatic SSH tunneling
    
    Args:
        ssh_manager: SSHManager instance
    """
    await aprint(Fore.CYAN + "\n=== 🤖 LLM Workflow (API Mode) ===")
    await aprint(Fore.YELLOW + "Enhanced with file loading and interactive features")
    
    # Get remote host and SSH connection
    remote_host = ssh_manager.host if hasattr(ssh_manager, 'host') else 'localhost'
    ssh_connection = ssh_manager.connection if hasattr(ssh_manager, 'connection') else None
    
    await aprint(Fore.CYAN + f"Connecting to Ollama at {remote_host}:11434...")
    
    try:
        async with OllamaSessionManager(remote_host, 11434, ssh_connection) as session:
            await aprint(Fore.GREEN + "✅ Connected to Ollama!")
            
            if session._using_tunnel:
                await aprint(Fore.CYAN + "   (via SSH tunnel)")
            
            # List available models
            models = await session.list_models()
            
            if not models:
                await _show_no_models_help(ssh_manager)
                return
            
            await aprint(Fore.GREEN + f"✅ Found {len(models)} model(s)")
            
            # Model selection with custom model option
            selected_model = await _select_or_create_model(
                session, 
                models, 
                ssh_connection
            )
            
            if not selected_model:
                return
            
            await aprint(Fore.GREEN + f"\n✅ Using model: {selected_model}")
            
            # Show enhanced menu
            await _show_interactive_menu()
            
            # Run interactive session with enhanced features
            await _run_enhanced_interactive_session(
                session, 
                selected_model,
                ssh_manager
            )
            
    except KeyboardInterrupt:
        await aprint(Fore.YELLOW + "\n\n⚠️ LLM session interrupted (Ctrl+C). Returning to main menu...")
        logger.info("LLM session interrupted by user")
    except ConnectionError as e:
        await aprint(Fore.RED + f"❌ Connection failed: {e}")
        logger.error(f"Connection error: {e}")
        await _show_connection_help(ssh_manager, remote_host)
    except Exception as e:
        await aprint(Fore.RED + f"❌ Unexpected error: {e}")
        logger.error(f"Unexpected error: {e}", exc_info=True)


async def _select_or_create_model(session, models: list, ssh_connection) -> str:
    """
    Select base LLM, then optionally create Research Assistant model.
    
    Workflow:
    1. Show available base models (exclude custom models)
    2. User selects base model
    3. Ask if building Research Assistant
    4. Build appropriate model if requested
    5. Use selected/created model
    
    Returns:
        Selected model name or None if cancelled
    """
    
    # STEP 1: Filter out custom models - show only base models
    base_models = [m for m in models if not m.startswith('ct-research-assistant') 
                   and not m.startswith('amp-assistant')]
    
    if not base_models:
        await aprint(Fore.RED + "❌ No base models available")
        return None
    
    await aprint(Fore.CYAN + f"\n📋 Available base models:")
    for i, model in enumerate(base_models, 1):
        marker = "→" if i == 1 else " "
        await aprint(Fore.WHITE + f"  {marker} {i}) {model}")
    
    # STEP 2: User selects base model
    choice = await ainput(Fore.GREEN + "Select base model [1]: ")
    choice = choice.strip() or "1"
    
    # Parse selection
    selected_base = None
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(base_models):
            selected_base = base_models[idx]
    elif choice in base_models:
        selected_base = choice
    
    if not selected_base:
        await aprint(Fore.YELLOW + "Invalid selection, using first model")
        selected_base = base_models[0]
    
    await aprint(Fore.GREEN + f"✅ Selected base: {selected_base}\n")
    
    # STEP 3: Ask about Research Assistant
    build_assistant = await ainput(
        Fore.CYAN + 
        "Build Research Assistant model from this base? (y/n) [n]: "
    )
    build_assistant = build_assistant.strip().lower()
    
    # STEP 4: Build model if requested
    if build_assistant in ('y', 'yes'):
        model_name = "ct-research-assistant:latest"
        await aprint(Fore.CYAN + f"\n🔬 Building Research Assistant model...")
        
        if await _build_custom_model(
            ssh_connection, 
            model_name, 
            base_models, 
            selected_base_model=selected_base
        ):
            await aprint(Fore.GREEN + f"\n✅ Created: {model_name}")
            await aprint(Fore.CYAN + f"   Base LLM: {selected_base}")
            await aprint(Fore.CYAN + f"   Purpose: Clinical Trial Research\n")
            return model_name
        else:
            await aprint(Fore.YELLOW + f"\n⚠️  Model creation failed")
            await aprint(Fore.YELLOW + f"Falling back to base model: {selected_base}\n")
            return selected_base
    else:
        # STEP 5: Use base model directly
        await aprint(Fore.GREEN + f"\n✅ Using base model: {selected_base}\n")
        return selected_base


async def _show_interactive_menu():
    """Display interactive menu options."""
    await aprint(Fore.CYAN + Style.BRIGHT + "\n" + "="*60)
    await aprint(Fore.CYAN + Style.BRIGHT + "  💬 INTERACTIVE LLM SESSION")
    await aprint(Fore.CYAN + Style.BRIGHT + "="*60 + Style.RESET_ALL)
    
    await aprint(Fore.YELLOW + "\n💡 Available Commands:")
    await aprint(Fore.WHITE + "  📋 File Operations:")
    await aprint(Fore.CYAN + "    • 'load <filename>' - Load file from output/ directory")
    await aprint(Fore.CYAN + "    • 'load <filename> <question>' - Load file and ask question")
    await aprint(Fore.CYAN + "    • 'paste' - Multi-line paste mode (end with <<<end)")
    await aprint(Fore.CYAN + "    • 'ls' or 'dir' - List files in output/ directory")
    
    await aprint(Fore.WHITE + "\n  🧬 Trial Operations:")
    await aprint(Fore.CYAN + "    • 'trial <NCT>' - Load specific trial data")
    await aprint(Fore.CYAN + "    • 'extract <NCT>' - Extract structured data from trial")
    await aprint(Fore.CYAN + "    • 'compare <NCT1> <NCT2>' - Compare two trials")
    
    await aprint(Fore.WHITE + "\n  ℹ️ Information:")
    await aprint(Fore.CYAN + "    • 'pwd' - Show current working directory")
    await aprint(Fore.CYAN + "    • 'help' - Show this menu again")
    await aprint(Fore.CYAN + "    • 'models' - List available models")
    
    await aprint(Fore.WHITE + "\n  🚪 Exit:")
    await aprint(Fore.CYAN + "    • 'exit', 'quit', 'main menu' - Return to main menu")
    await aprint(Fore.YELLOW + "    • Ctrl+C - Interrupt and return to main menu")
    
    await aprint(Fore.CYAN + "\n" + "="*60 + "\n")


async def _run_enhanced_interactive_session(
    session: OllamaSessionManager, 
    model: str,
    ssh_manager
):
    """
    Run enhanced interactive session with all features.
    
    Args:
        session: Ollama session manager
        model: Model name to use
        ssh_manager: SSH manager for trial operations
    """
    while True:
        try:
            prompt = await ainput(Fore.GREEN + "LLM >>> " + Fore.WHITE)
            
            if prompt is None:
                prompt = ""
            prompt = prompt.strip()
            
            if not prompt:
                continue
            
            # Check for exit commands
            if prompt.lower() in ("exit", "quit", "main menu"):
                await aprint(Fore.YELLOW + "Returning to main menu...")
                break
            
            # Handle special commands
            if await _handle_special_command(prompt, session, model, ssh_manager):
                continue
            
            # Regular prompt to LLM
            await aprint(Fore.YELLOW + f"\n🤔 Generating response...")
            
            try:
                response = await session.send_prompt(
                    model=model,
                    prompt=prompt,
                    temperature=0.7,
                    max_retries=3
                )
                
                if response.startswith("Error:"):
                    await aprint(Fore.RED + f"\n{response}")
                else:
                    await aprint(Fore.GREEN + "\n🧠 Response:")
                    await aprint(Fore.WHITE + response + "\n")
                    
            except Exception as e:
                await aprint(Fore.RED + f"\n❌ Error: {e}")
                logger.error(f"Generation error: {e}", exc_info=True)
                
        except KeyboardInterrupt:
            await aprint(Fore.YELLOW + "\n\n⚠️ Interrupted. Type 'exit' to quit or press Enter to continue...")
            continue
        except EOFError:
            await aprint(Fore.YELLOW + "\nEOF detected. Returning to main menu...")
            break


async def _handle_special_command(
    prompt: str, 
    session: OllamaSessionManager, 
    model: str,
    ssh_manager
) -> bool:
    """
    Handle special commands.
    
    Returns:
        True if command was handled, False if should treat as regular prompt
    """
    prompt_lower = prompt.lower()
    
    # Help command
    if prompt_lower in ('help', '?', '!help'):
        await _show_interactive_menu()
        return True
    
    # Directory listing
    if prompt_lower in ('ls', 'dir', 'list'):
        await list_output_files(aprint)
        return True
    
    # Show working directory
    if prompt_lower in ('pwd', 'cwd'):
        await show_pwd(aprint)
        return True
    
    # Paste mode
    if prompt_lower == 'paste':
        pasted = await handle_paste_command(ainput, aprint)
        if pasted:
            await aprint(Fore.YELLOW + f"\n🤔 Sending pasted content to LLM...")
            response = await session.send_prompt(model=model, prompt=pasted)
            if not response.startswith("Error:"):
                await aprint(Fore.GREEN + "\n🧠 Response:")
                await aprint(Fore.WHITE + response + "\n")
            else:
                await aprint(Fore.RED + f"\n{response}")
        return True
    
    # Load file
    if prompt_lower.startswith('load '):
        final_prompt = await handle_load_command(prompt, ainput, aprint, logger)
        if final_prompt:
            await aprint(Fore.YELLOW + f"\n🤔 Processing file content...")
            response = await session.send_prompt(model=model, prompt=final_prompt)
            if not response.startswith("Error:"):
                await aprint(Fore.GREEN + "\n🧠 Response:")
                await aprint(Fore.WHITE + response + "\n")
            else:
                await aprint(Fore.RED + f"\n{response}")
        return True
    
    # Trial operations
    if prompt_lower.startswith('trial '):
        nct = prompt.split(maxsplit=1)[1].strip().upper()
        await _handle_trial_command(nct, session, model)
        return True
    
    if prompt_lower.startswith('extract '):
        nct = prompt.split(maxsplit=1)[1].strip().upper()
        await _handle_extract_command(nct, session, model)
        return True
    
    if prompt_lower.startswith('compare '):
        parts = prompt.split()[1:]
        if len(parts) >= 2:
            nct1, nct2 = parts[0].upper(), parts[1].upper()
            await _handle_compare_command(nct1, nct2, session, model)
        else:
            await aprint(Fore.RED + "Usage: compare <NCT1> <NCT2>")
        return True
    
    # List models
    if prompt_lower in ('models', 'list models'):
        models = await session.list_models()
        await aprint(Fore.CYAN + f"\n📋 Available models ({len(models)}):")
        for i, m in enumerate(models, 1):
            await aprint(Fore.WHITE + f"  {i}. {m}")
        await aprint("")
        return True
    
    return False


async def _handle_trial_command(nct: str, session: OllamaSessionManager, model: str):
    """Load trial data and allow questions."""
    await aprint(Fore.YELLOW + f"\n🔍 Loading trial data for {nct}...")
    
    try:
        # Try to load from database
        from amp_llm.data.clinical_trials.rag import ClinicalTrialRAG
        from pathlib import Path
        
        db_path = Path("ct_database")
        if not db_path.exists():
            await aprint(Fore.RED + "❌ Trial database not found at ct_database/")
            return
        
        rag = ClinicalTrialRAG(db_path)
        if not rag.db.index_built:
            rag.db.build_index()
        
        trial = rag.db.get_trial(nct)
        
        if not trial:
            await aprint(Fore.RED + f"❌ Trial {nct} not found in database")
            return
        
        # Extract structured data
        extraction = rag.db.extract_structured_data(nct)
        
        if extraction:
            trial_text = extraction.to_formatted_string()
            await aprint(Fore.GREEN + f"✅ Loaded {nct}")
            await aprint(Fore.CYAN + f"\nPreview:")
            await aprint(Fore.WHITE + trial_text[:500] + "...\n")
            
            question = await ainput(Fore.CYAN + "Ask a question about this trial (or Enter to skip): ")
            
            if question.strip():
                prompt = f"Based on this clinical trial data:\n\n{trial_text}\n\nQuestion: {question}"
                
                await aprint(Fore.YELLOW + "\n🤔 Analyzing trial data...")
                response = await session.send_prompt(model=model, prompt=prompt)
                
                if not response.startswith("Error:"):
                    await aprint(Fore.GREEN + "\n🧠 Answer:")
                    await aprint(Fore.WHITE + response + "\n")
                else:
                    await aprint(Fore.RED + f"\n{response}")
        else:
            await aprint(Fore.RED + f"❌ Could not extract data for {nct}")
            
    except ImportError:
        await aprint(Fore.RED + "❌ RAG system not available")
    except Exception as e:
        await aprint(Fore.RED + f"❌ Error loading trial: {e}")
        logger.error(f"Trial load error: {e}", exc_info=True)


async def _handle_extract_command(nct: str, session: OllamaSessionManager, model: str):
    """Extract structured data from trial."""
    await aprint(Fore.YELLOW + f"\n📋 Extracting structured data for {nct}...")
    
    try:
        from amp_llm.data.clinical_trials.rag import ClinicalTrialRAG
        from pathlib import Path
        
        db_path = Path("ct_database")
        if not db_path.exists():
            await aprint(Fore.RED + "❌ Trial database not found")
            return
        
        rag = ClinicalTrialRAG(db_path)
        if not rag.db.index_built:
            rag.db.build_index()
        
        extraction = rag.db.extract_structured_data(nct)
        
        if extraction:
            context = extraction.to_formatted_string()
            
            prompt = f"""Extract and format this clinical trial data in a clear, structured way:

{context}

Provide a summary highlighting:
- Study status and phase
- Conditions and interventions
- Key dates
- Classification
- Outcome and any failure reasons"""
            
            await aprint(Fore.YELLOW + "\n🤔 Generating extraction...")
            response = await session.send_prompt(model=model, prompt=prompt)
            
            if not response.startswith("Error:"):
                await aprint(Fore.GREEN + "\n📊 Extracted Data:")
                await aprint(Fore.WHITE + response + "\n")
                
                # Offer to save
                save = await ainput(Fore.CYAN + "Save this extraction? (y/n): ")
                if save.lower() in ('y', 'yes'):
                    from pathlib import Path
                    output_dir = Path('output')
                    output_dir.mkdir(exist_ok=True)
                    
                    filename = f"{nct}_extraction.txt"
                    filepath = output_dir / filename
                    
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(response)
                    
                    await aprint(Fore.GREEN + f"✅ Saved to {filepath}")
            else:
                await aprint(Fore.RED + f"\n{response}")
        else:
            await aprint(Fore.RED + f"❌ Could not extract data for {nct}")
            
    except Exception as e:
        await aprint(Fore.RED + f"❌ Error: {e}")
        logger.error(f"Extract error: {e}", exc_info=True)


async def _handle_compare_command(
    nct1: str, 
    nct2: str, 
    session: OllamaSessionManager, 
    model: str
):
    """Compare two clinical trials."""
    await aprint(Fore.YELLOW + f"\n🔄 Comparing {nct1} vs {nct2}...")
    
    try:
        from amp_llm.data.clinical_trials.rag import ClinicalTrialRAG
        from pathlib import Path
        
        db_path = Path("ct_database")
        if not db_path.exists():
            await aprint(Fore.RED + "❌ Trial database not found")
            return
        
        rag = ClinicalTrialRAG(db_path)
        if not rag.db.index_built:
            rag.db.build_index()
        
        # Get both trials
        extraction1 = rag.db.extract_structured_data(nct1)
        extraction2 = rag.db.extract_structured_data(nct2)
        
        if not extraction1 or not extraction2:
            await aprint(Fore.RED + f"❌ Could not load both trials")
            return
        
        trial1_text = extraction1.to_formatted_string()
        trial2_text = extraction2.to_formatted_string()
        
        prompt = f"""Compare these two clinical trials and highlight key differences and similarities:

TRIAL 1 ({nct1}):
{trial1_text}

TRIAL 2 ({nct2}):
{trial2_text}

Provide a comparison focusing on:
- Similarities in approach, conditions, or interventions
- Key differences in methodology or outcomes
- Relative strengths and weaknesses
- Any notable findings"""
        
        await aprint(Fore.YELLOW + "\n🤔 Analyzing trials...")
        response = await session.send_prompt(model=model, prompt=prompt)
        
        if not response.startswith("Error:"):
            await aprint(Fore.GREEN + "\n📊 Comparison:")
            await aprint(Fore.WHITE + response + "\n")
        else:
            await aprint(Fore.RED + f"\n{response}")
            
    except Exception as e:
        await aprint(Fore.RED + f"❌ Error: {e}")
        logger.error(f"Compare error: {e}", exc_info=True)


async def _build_custom_model(ssh_connection, model_name: str, available_models: list) -> bool:
    """Build custom model from Modelfile."""
    await aprint(Fore.CYAN + "\n🏗️  Building Custom Model")
    await aprint(Fore.YELLOW + "Creating specialized clinical trial assistant...")
    
    # Find Modelfile
    modelfile_path = _find_modelfile()
    
    if not modelfile_path:
        await aprint(Fore.RED + "❌ Modelfile not found!")
        await aprint(Fore.YELLOW + "Expected: Modelfile in project root")
        return False
    
    await aprint(Fore.GREEN + f"✅ Found Modelfile: {modelfile_path}")
    
    try:
        modelfile_content = modelfile_path.read_text()
    except Exception as e:
        await aprint(Fore.RED + f"❌ Cannot read Modelfile: {e}")
        return False
    
    # Select base model
    await aprint(Fore.CYAN + f"\n📋 Select base model:")
    for i, model in enumerate(available_models, 1):
        await aprint(Fore.WHITE + f"  {i}. {model}")
    
    choice = await ainput(Fore.GREEN + "Select base model [1]: ")
    choice = choice.strip() or "1"
    
    # Parse choice
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(available_models):
            base_model = available_models[idx]
        else:
            base_model = available_models[0]
    else:
        base_model = available_models[0]
    
    await aprint(Fore.CYAN + f"\n🔨 Building '{model_name}' from '{base_model}'...")
    
    # Update Modelfile
    import re
    updated_modelfile = re.sub(
        r'^FROM\s+\S+',
        f'FROM {base_model}',
        modelfile_content,
        flags=re.MULTILINE
    )
    
    # Upload and build
    temp_path = f"/tmp/amp_modelfile_{int(time.time())}.modelfile"
    
    try:
        async with ssh_connection.start_sftp_client() as sftp:
            async with sftp.open(temp_path, 'w') as f:
                await f.write(updated_modelfile)
        
        await aprint(Fore.GREEN + "✅ Modelfile uploaded")
        await aprint(Fore.YELLOW + "🏗️  Building... (this may take 1-2 minutes)")
        
        result = await ssh_connection.run(
            f'bash -l -c "ollama create {model_name} -f {temp_path}"',
            check=False,
            term_type=None 
        )
        
        # Cleanup
        await ssh_connection.run(f'rm -f {temp_path}', check=False, term_type=None)
        
        if result.exit_status == 0:
            await aprint(Fore.GREEN + f"\n✅ Model '{model_name}' created successfully!")
            return True
        else:
            await aprint(Fore.RED + "\n❌ Model creation failed")
            return False
            
    except Exception as e:
        await aprint(Fore.RED + f"❌ Build error: {e}")
        logger.error(f"Build error: {e}", exc_info=True)
        return False


def _find_modelfile() -> Path:
    """Find Modelfile in expected locations."""
    search_paths = [
        Path("Modelfile"),
        Path("amp_llm/Modelfile"),
        Path("../Modelfile"),
    ]
    
    for path in search_paths:
        if path.exists():
            return path
    
    return None


async def _show_no_models_help(ssh_manager):
    """Show help when no models found."""
    await aprint(Fore.RED + "❌ No models found on remote server")
    await aprint(Fore.YELLOW + "\nTo install models:")
    await aprint(Fore.WHITE + "  1. SSH to remote server")
    await aprint(Fore.WHITE + "  2. Run: ollama pull llama3.2")
    await aprint(Fore.WHITE + "  3. Run: ollama list (to verify)")


async def _show_connection_help(ssh_manager, remote_host: str):
    """Show help when connection fails."""
    await aprint(Fore.RED + "❌ Cannot connect to Ollama")
    await aprint(Fore.CYAN + "\nTroubleshooting:")
    await aprint(Fore.WHITE + "  1. Check if Ollama is running:")
    username = ssh_manager.username if hasattr(ssh_manager, 'username') else 'user'
    await aprint(Fore.WHITE + f"     ssh {username}@{remote_host}")
    await aprint(Fore.WHITE + "     systemctl status ollama")
    await aprint(Fore.WHITE + "  2. Test Ollama API:")
    await aprint(Fore.WHITE + "     curl http://localhost:11434/api/tags")


async def run_llm_entrypoint_api(ssh_manager):
    """
    Enhanced LLM workflow with fixed model selection.
    """
    await aprint(Fore.CYAN + "\n=== 🤖 LLM Workflow (API Mode) ===")
    await aprint(Fore.YELLOW + "Enhanced with file loading and interactive features\n")
    
    # Get remote host and SSH connection
    remote_host = ssh_manager.host if hasattr(ssh_manager, 'host') else 'localhost'
    ssh_connection = ssh_manager.connection if hasattr(ssh_manager, 'connection') else None
    
    await aprint(Fore.CYAN + f"Connecting to Ollama at {remote_host}:11434...")
    
    try:
        async with OllamaSessionManager(remote_host, 11434, ssh_connection) as session:
            await aprint(Fore.GREEN + "✅ Connected to Ollama!")
            
            if session._using_tunnel:
                await aprint(Fore.CYAN + "   (via SSH tunnel)")
            
            # List available models
            models = await session.list_models()
            
            if not models:
                await _show_no_models_help(ssh_manager)
                return
            
            await aprint(Fore.GREEN + f"✅ Found {len(models)} model(s)\n")
            
            # FIXED: Use new model selection workflow
            selected_model = await _select_or_create_model(
                session, 
                models, 
                ssh_connection
            )
            
            if not selected_model:
                await aprint(Fore.RED + "❌ No model selected")
                return
            
            # Display current configuration
            await aprint(Fore.GREEN + Style.BRIGHT + "\n" + "="*60)
            await aprint(Fore.GREEN + Style.BRIGHT + "  🤖 CURRENT CONFIGURATION")
            await aprint(Fore.GREEN + Style.BRIGHT + "="*60)
            await aprint(Fore.WHITE + f"  Model: {selected_model}")
            
            # Check if it's the research assistant
            if "ct-research-assistant" in selected_model:
                await aprint(Fore.CYAN + "  Type: Clinical Trial Research Assistant")
                await aprint(Fore.CYAN + "  Features: RAG, Structured Extraction, Trial Analysis")
            else:
                await aprint(Fore.CYAN + "  Type: Base LLM (General Purpose)")
                await aprint(Fore.CYAN + "  Features: General Q&A, Code, Analysis")
            
            await aprint(Fore.GREEN + "="*60 + "\n")
            
            # Show interactive menu
            await _show_interactive_menu()
            
            # Run interactive session
            await _run_enhanced_interactive_session(
                session, 
                selected_model,
                ssh_manager
            )
            
    except KeyboardInterrupt:
        await aprint(Fore.YELLOW + "\n\n⚠️ LLM session interrupted (Ctrl+C). Returning to main menu...")
        logger.info("LLM session interrupted by user")
    except ConnectionError as e:
        await aprint(Fore.RED + f"❌ Connection failed: {e}")
        logger.error(f"Connection error: {e}")
        await _show_connection_help(ssh_manager, remote_host)
    except Exception as e:
        await aprint(Fore.RED + f"❌ Unexpected error: {e}")
        logger.error(f"Unexpected error: {e}", exc_info=True)