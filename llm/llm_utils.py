# llm/llm_utils.py
import subprocess, shlex, json

def list_local_models():
    try:
        out = subprocess.check_output(["ollama", "list", "--json"], stderr=subprocess.DEVNULL)
        data = json.loads(out)
        if isinstance(data, list):
            return [m.get("name", str(m)) for m in data]
        if isinstance(data, dict):
            return list(data.keys())
    except Exception:
        try:
            out = subprocess.check_output(["ollama", "list"], stderr=subprocess.DEVNULL).decode(errors="ignore")
            lines = [l.strip() for l in out.splitlines() if l.strip() and not l.lower().startswith("name")]
            return lines
        except Exception:
            return []

def run_ollama_local(model, prompt, timeout=60):
    cmd = ["ollama", "run", model]
    try:
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = p.communicate(input=prompt.encode("utf-8"), timeout=timeout)
        if stdout:
            return stdout.decode(errors="ignore")
        if stderr:
            return stderr.decode(errors="ignore")
        return ""
    except Exception as e:
        return f"LLM local run error: {e}"

def run_ollama_remote(ssh_client, model, prompt, timeout=60):
    import shlex, time
    try:
        cmd = f"ollama run {shlex.quote(model)}"
        stdin, stdout, stderr = ssh_client.exec_command(cmd, timeout=timeout)
        stdin.write(prompt + "\n")
        stdin.channel.shutdown_write()
        out = stdout.read().decode(errors="ignore")
        err = stderr.read().decode(errors="ignore")
        if out:
            return out
        return err
    except Exception as e:
        return f"LLM remote run error: {e}"