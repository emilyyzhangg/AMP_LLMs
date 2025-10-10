# Modelfile Setup Guide

## 📄 What is the Modelfile?

The Modelfile is a configuration file that creates a specialized version of any base Ollama model. It:
- **Stays on your local machine** (no need to upload manually)
- **Works with ANY base model** on your remote server
- **Automatically uploads and builds** when you run the research assistant
- **Creates a custom model** trained for clinical trial extraction

## 🎯 How It Works

```
Local Machine                    Remote Server
─────────────                    ─────────────
                                
Modelfile                        ollama list
(local file)                     ├─ llama3.2
    │                            ├─ mistral
    │                            ├─ codellama
    │                            └─ ...
    │                                 │
    ├─ Read content                   │
    ├─ Select base model ─────────────┤
    ├─ Replace FROM line              │
    ├─ Upload via SFTP                │
    └─ Send to remote ────────────────┤
                                      │
                                      ▼
                              ollama create
                              ct-research-assistant
                                      │
                                      ▼
                              New custom model
                              ready to use!
```

## 📁 File Placement

Place `Modelfile` in your project root:

```
Claude_Async_Version/
├── Modelfile          ← HERE (project root)
├── main.py
├── config.py
├── data/
│   ├── clinical_trial_rag.py
│   └── ...
├── llm/
│   ├── ct_research_runner.py
│   └── ...
└── ...
```

The system will search in these locations (in order):
1. `Claude_Async_Version/Modelfile`
2. `Claude_Async_Version/llm/Modelfile`
3. Current working directory
4. Parent directory

## 🚀 Usage Workflow

### First Time Setup

1. **Place Modelfile** in project root
2. **Run your program**:
   ```bash
   python main.py
   ```

3. **Select Research Assistant** (option 5)

4. **The system will**:
   - Check if custom model exists
   - If not, show available models on remote:
     ```
     📋 Available base models on remote server:
       1) llama3.2
       2) mistral
       3) codellama
       4) llama2
     
     Select base model by number or name [llama3.2]:
     ```

5. **Select your preferred base model**:
   - Press `1` for llama3.2
   - Press `2` for mistral  
   - Or type model name directly
   - Or press Enter for default

6. **Model builds automatically**:
   ```
   ✅ Found Modelfile at: /path/to/Modelfile
   📤 Uploading Modelfile to remote server...
   ✅ Uploaded to /tmp/ct_modelfile_xxxxx.modelfile
   🔨 Building model (this may take 1-2 minutes)...
       Please wait...
   
   ✅ Success! Model 'ct-research-assistant' created!
       Base: llama3.2
       Name: ct-research-assistant
   ```

7. **Start researching!**

### Subsequent Uses

Once created, the custom model persists on the remote server:

```bash
# Next time you run:
python main.py
# Select option 5

✅ Custom model 'ct-research-assistant' already exists
✅ Using model: ct-research-assistant
```

No rebuild needed!

## 🔧 Customizing the Modelfile

### Change Default Base Model

Edit line 6 in Modelfile:
```dockerfile
FROM mistral  # instead of llama3.2
```

> **Note**: This is just a placeholder. The actual base model is selected interactively.

### Adjust Temperature

For more creative responses:
```dockerfile
PARAMETER temperature 0.7  # More creative (0.3 is more factual)
```

For more factual responses:
```dockerfile
PARAMETER temperature 0.1  # Very factual
```

### Increase Context Window

For larger trials:
```dockerfile
PARAMETER num_ctx 16384  # Double the context (default is 8192)
```

### Add Custom Instructions

Edit the SYSTEM section to add domain-specific knowledge:
```dockerfile
SYSTEM """You are a Clinical Trial Research Assistant...

[Existing instructions]

## Additional Domain Knowledge:

- **AMP Database**: You have access to DRAMP (Database of Antimicrobial Peptides)
- **Special Focus**: Pay extra attention to antimicrobial peptide trials
- **Custom Classifications**: Use our internal taxonomy...

[Your custom instructions]
"""
```

### Change Model Name

In `ct_research_runner.py`, line 36:
```python
self.model_name = "ct-research-assistant"  # Change to your preferred name
```

## 🔄 Updating the Model

### Option 1: Delete and Rebuild

On remote server:
```bash
ollama rm ct-research-assistant
```

Next run will automatically rebuild with latest Modelfile.

### Option 2: Create Version 2

Change model name in code:
```python
self.model_name = "ct-research-assistant-v2"
```

Both versions will coexist.

### Option 3: Manual Update

```bash
# On remote server
ollama create ct-research-assistant -f /path/to/Modelfile
```

## 🎨 Model Variants

You can create multiple specialized models by:

1. **Copy Modelfile** for each variant:
   ```
   Modelfile.factual      # temperature 0.1
   Modelfile.balanced     # temperature 0.3
   Modelfile.creative     # temperature 0.7
   ```

2. **Select different variant** in code:
   ```python
   # For more factual extraction
   self.model_name = "ct-research-factual"
   modelfile_path = Path("Modelfile.factual")
   
   # For creative analysis
   self.model_name = "ct-research-creative"
   modelfile_path = Path("Modelfile.creative")
   ```

## 🧪 Testing Your Modelfile

### Test Locally (if you have Ollama locally)

```bash
# Create local version
ollama create test-ct-assistant -f Modelfile

# Test it
ollama run test-ct-assistant "Extract trial info from this JSON: {...}"

# Remove when done
ollama rm test-ct-assistant
```

### Test Remotely

Via SSH:
```bash
ssh user@remote
ollama create test-model -f /path/to/Modelfile
ollama run test-model "Test query"
ollama rm test-model
```

## 📊 Model Comparison

Different base models have different strengths:

| Base Model | Size | Speed | Quality | Best For |
|------------|------|-------|---------|----------|
| **llama3.2** | ~2GB | Fast | Excellent | General use, balanced |
| **llama3.1:8b** | ~4.7GB | Medium | Excellent | Best quality |
| **mistral** | ~4.1GB | Fast | Very Good | Quick responses |
| **llama2** | ~3.8GB | Medium | Good | Stable, reliable |
| **codellama** | ~3.8GB | Medium | Good | If trials have code/sequences |
| **phi3** | ~2.3GB | Very Fast | Good | Limited resources |

**Recommendation**: Start with `llama3.2` for best balance of speed and quality.

## 🐛 Troubleshooting

### "Modelfile not found"

**Problem**: System can't find your Modelfile
**Solution**:
```bash
# Check current directory
pwd

# List files
ls -la

# Ensure Modelfile is present
ls -la Modelfile

# Check from Python
python -c "from pathlib import Path; print(Path('Modelfile').absolute())"
```

Place it in the project root where `main.py` is located.

### "Model creation failed"

**Problem**: `ollama create` command fails on remote

**Possible causes**:

1. **Base model doesn't exist**
   ```bash
   # On remote server, check:
   ollama list
   
   # Pull missing model:
   ollama pull llama3.2
   ```

2. **Insufficient disk space**
   ```bash
   df -h
   # Need ~5-10GB free
   ```

3. **Ollama not running**
   ```bash
   systemctl status ollama
   systemctl start ollama
   ```

4. **Permission issues**
   ```bash
   # Check write permissions in /tmp
   ls -la /tmp
   ```

### "SFTP upload failed"

**Problem**: Cannot upload Modelfile to remote

**Solutions**:
```python
# Check SSH connection
# In your code, verify:
if ssh.is_closed():
    print("SSH connection is closed!")
```

**Alternative**: Manually upload once:
```bash
# From local machine
scp Modelfile user@remote:/home/user/
```

Then modify code to use that path:
```python
temp_modelfile = "/home/user/Modelfile"  # Use permanent location
```

### "Model gives poor results"

**Problem**: Extractions are incomplete or inaccurate

**Solutions**:

1. **Lower temperature**:
   ```dockerfile
   PARAMETER temperature 0.1  # More factual
   ```

2. **Increase context**:
   ```dockerfile
   PARAMETER num_ctx 16384  # More context
   ```

3. **Enhance system prompt**:
   Add more examples and clearer instructions

4. **Try different base model**:
   Some models are better at structured extraction

### "Build takes too long"

**Problem**: `ollama create` hangs or takes forever

**Causes**:
- Large base model being downloaded
- Slow remote connection
- Server is busy

**Solutions**:
```bash
# Pre-pull base model on remote
ssh user@remote
ollama pull llama3.2  # Downloads once

# Then create your model
# (will be much faster)
```

## 🔐 Security Considerations

### Temporary Files

The system creates temporary files like:
```
/tmp/ct_modelfile_1234567890.modelfile
```

These are automatically deleted after model creation. If process is interrupted:
```bash
# Cleanup manually
rm /tmp/ct_modelfile_*
```

### Sensitive Data

The Modelfile contains your system prompt but NO sensitive data:
- ✅ No API keys
- ✅ No passwords
- ✅ No database contents
- ✅ Only instructions for the AI

It's safe to version control and share.

## 📈 Advanced Configuration

### Multiple Models for Different Tasks

Create specialized variants:

**Modelfile.extraction** (factual extraction):
```dockerfile
FROM llama3.2
PARAMETER temperature 0.1
SYSTEM """You are a strict data extractor..."""
```

**Modelfile.analysis** (creative analysis):
```dockerfile
FROM llama3.1:8b
PARAMETER temperature 0.6
SYSTEM """You are a research analyst..."""
```

**Modelfile.comparison** (comparative studies):
```dockerfile
FROM mistral
PARAMETER temperature 0.4
SYSTEM """You are a comparative research specialist..."""
```

Use different models in code:
```python
# For extraction
extraction_assistant = ClinicalTrialResearchAssistant(db_path)
extraction_assistant.model_name = "ct-extractor"

# For analysis
analysis_assistant = ClinicalTrialResearchAssistant(db_path)
analysis_assistant.model_name = "ct-analyzer"
```

### Performance Optimization

**For many small queries**:
```dockerfile
PARAMETER num_ctx 4096    # Smaller context
PARAMETER temperature 0.2  # Fast and factual
```

**For few large queries**:
```dockerfile
PARAMETER num_ctx 16384   # Large context
PARAMETER temperature 0.3  # Balanced
PARAMETER num_predict 4096  # Longer responses
```

### Custom Stop Sequences

Prevent model from rambling:
```dockerfile
PARAMETER stop "---END---"
PARAMETER stop "###"
```

Then in system prompt:
```
Always end your response with ---END---
```

## 🎓 Best Practices

### 1. Start Simple
Begin with default Modelfile, test thoroughly, then customize.

### 2. Version Control
```bash
git add Modelfile
git commit -m "Add clinical trial extraction model"
```

### 3. Document Changes
Keep a changelog in Modelfile comments:
```dockerfile
# v1.0 - Initial version (2024-01-15)
# v1.1 - Added peptide detection (2024-01-20)
# v1.2 - Enhanced evidence linking (2024-01-25)
```

### 4. Test Before Deploying
Always test Modelfile changes locally or on dev server first.

### 5. Keep Backups
```bash
cp Modelfile Modelfile.backup.$(date +%Y%m%d)
```

## 🔄 Workflow Examples

### Daily Research Workflow

```bash
# 1. Start application
python main.py

# 2. Select Research Assistant
# (First time: model builds automatically)
# (Subsequent: uses existing model)

# 3. Search and extract
search peptide trials
extract NCT04043065

# 4. Export results
export NCT04043065,NCT12345678

# 5. Continue research...
```

### Updating Workflow

```bash
# 1. Edit Modelfile locally
vim Modelfile
# Make your changes

# 2. Delete remote model
ssh user@remote
ollama rm ct-research-assistant
exit

# 3. Run application
python main.py
# Select option 5
# Model rebuilds with new Modelfile

# 4. Test new version
search test query
```

### Multi-User Workflow

```bash
# Each user can have their own variant:

# User 1: Extraction focus
Modelfile.user1 → ct-research-user1

# User 2: Analysis focus  
Modelfile.user2 → ct-research-user2

# Shared: General use
Modelfile → ct-research-assistant
```

## 📚 Additional Resources

### Ollama Modelfile Documentation
https://github.com/ollama/ollama/blob/main/docs/modelfile.md

### Available Parameters
- `temperature`: Creativity (0.0-1.0)
- `top_p`: Nucleus sampling (0.0-1.0)
- `top_k`: Token selection pool
- `num_ctx`: Context window size
- `num_predict`: Max response length
- `repeat_penalty`: Avoid repetition
- `stop`: Stop sequences

### System Prompt Tips
- Be specific and clear
- Provide examples
- Define exact output format
- Include edge cases
- Use markdown for structure

## 🎯 Quick Reference Card

```
┌─────────────────────────────────────────────┐
│ MODELFILE QUICK REFERENCE                   │
├─────────────────────────────────────────────┤
│ Location: Claude_Async_Version/Modelfile   │
│                                             │
│ Build: Automatic on first run              │
│ Update: Delete model → rebuild             │
│ Custom: Edit SYSTEM prompt section         │
│                                             │
│ Base Models (common):                       │
│   • llama3.2    - Best balance             │
│   • mistral     - Fast                     │
│   • llama3.1:8b - Highest quality          │
│                                             │
│ Key Parameters:                             │
│   • temperature 0.3  - Factual             │
│   • num_ctx 8192     - Context size        │
│   • top_p 0.9        - Sampling            │
│                                             │
│ Commands:                                   │
│   ollama list              - List models   │
│   ollama rm <model>        - Delete        │
│   ollama create <name> -f  - Build         │
└─────────────────────────────────────────────┘
```

## ✅ Checklist

Before running the Research Assistant:

- [ ] Modelfile is in project root (`Claude_Async_Version/Modelfile`)
- [ ] SSH connection to remote server works
- [ ] Ollama is running on remote (`ollama list` works)
- [ ] At least one base model exists on remote
- [ ] JSON database is prepared in `ct_database/`
- [ ] All Python files are in place
- [ ] Requirements are installed

You're ready to go! 🚀

