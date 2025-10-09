import asyncio
from colorama import Fore

async def open_interactive_shell(ssh):
    """Open a simple interactive remote shell using an invoked shell and relay IO."""
    print(Fore.GREEN + "✅ Connected to remote host.")
    print(Fore.YELLOW + "Type 'main menu' to return to AMP_LLM, or 'exit' to close SSH.\n")
    chan, session = await ssh.open_session(term_type='xterm')
    # invoke shell
    await chan.request_pty(term_type='xterm')
    await chan.exec_shell()
    loop = asyncio.get_event_loop()

    async def reader():
        try:
            while True:
                data = await chan.read(1024)
                if not data:
                    break
                print(data, end="")
        except Exception:
            pass

    asyncio.create_task(reader())

    try:
        while True:
            cmd = input('> ')
            if cmd.lower() in ('main menu','exit','quit'):
                print(Fore.YELLOW + 'Returning to main menu...')
                break
            await chan.write(cmd + "\n")
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        try:
            chan.close()
        except Exception:
            pass
