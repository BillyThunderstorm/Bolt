# LLM_From_Scratch Docker Setup Guide

This Docker container provides an isolated development environment for experimenting with LLM implementations and new ideas before integrating them into Bolt.

## What's Included

- **Python 3.11** base image (slim variant for smaller footprint)
- **PyTorch CPU** — for model training/experimentation
- **NumPy, Pandas, Matplotlib** — data science tools
- **Jupyter Notebook** — interactive development at http://localhost:8888
- **TensorBoard** — visualization of training metrics at http://localhost:6006
- **Anthropic SDK** — access to Claude API inside the container
- **Your ANTHROPIC_API_KEY** — automatically loaded from your .env file

## First-Time Setup

### Prerequisites
1. **Docker Desktop installed** — download from https://www.docker.com/products/docker-desktop
2. **.env file in Bolt folder** — your ANTHROPIC_API_KEY must be there
3. **Terminal** — you'll run commands from the Bolt folder

### Start the Container

```bash
cd ~/Library/"Mobile Documents"/com~apple~CloudDocs/Bolt

# Start the container (first run takes 2-3 minutes to build + install packages)
docker-compose up -d

# Jump into the container shell
docker-compose exec llm-from-scratch bash
```

You're now inside the container at `/workspace` with Python 3.11, PyTorch, and all tools ready.

## Using the Container

### Interactive Python Development

```bash
# Inside the container bash shell:
python3                    # Start Python interactive shell
python3 script.py          # Run a script
python3 -m pip install X   # Install additional packages
```

### Jupyter Notebook (Interactive Development)

```bash
# Inside the container:
jupyter notebook --ip=0.0.0.0 --no-browser --allow-root

# On your Mac, open browser to: http://localhost:8888
# Copy the token from the output above when prompted
```

### Running LLM Experiments

Place your experiment scripts in `llm_experiments/` — they're automatically mounted at `/workspace` inside the container.

Example structure:
```
llm_experiments/
├── train_gpt.py          # Your training script
├── tokenizer.py          # Utilities
└── data/                 # Training data
```

Then from inside the container:
```bash
python3 train_gpt.py --epochs 10 --batch-size 32
```

## Common Commands

```bash
# View running container
docker-compose ps

# Stop the container
docker-compose down

# Restart it
docker-compose up -d

# View logs
docker-compose logs llm-from-scratch

# Remove all stopped containers and cleanup
docker system prune

# Re-enter the container (if already running)
docker-compose exec llm-from-scratch bash
```

## Accessing Your Data

Three sync points:

| Host Location | Container Location | Purpose |
|---------------|-------------------|---------|
| `llm_experiments/` | `/workspace` | Your code & scripts |
| `data/` | `/workspace/data` | Datasets, checkpoints |
| `.env` | Environment vars | API keys (loaded automatically) |

Any files you create inside the container at `/workspace/` are saved back to `llm_experiments/` on your Mac.

## Stopping & Cleanup

When you're done:

```bash
# Exit the container shell
exit

# Stop the running container
docker-compose down

# If you want to remove all images/volumes (complete cleanup)
docker-compose down -v
docker image rm python:3.11-slim
```

## Troubleshooting

### "docker-compose: command not found"
Make sure Docker Desktop is installed **and running**. Then try the full path:
```bash
/usr/local/bin/docker-compose up -d
# or on Apple Silicon Macs:
/opt/homebrew/bin/docker-compose up -d
```

### Container exits immediately
Check the logs:
```bash
docker-compose logs llm-from-scratch
```

### Can't access Jupyter at localhost:8888
Make sure port 8888 isn't already in use:
```bash
lsof -i :8888
```

### Need to install a Python package
From inside the container:
```bash
pip install package-name
```

## Integration with Bolt

Once you've experimented and want to bring code into Bolt:

1. **Develop** in the Docker container (`llm_experiments/`)
2. **Test** your scripts thoroughly
3. **Copy working modules** into `modules/` when ready
4. **Update requirements.txt** if you added new dependencies
5. **Wire into bot.py** following Bolt's module pattern

Example flow:
```
llm_experiments/new_feature.py  (development sandbox)
    ↓ (after testing)
modules/new_feature.py          (integrate into Bolt)
    ↓ (add to requirements)
requirements.txt                (ship it)
```

## Next Steps

1. Start the container: `docker-compose up -d`
2. Jump in: `docker-compose exec llm-from-scratch bash`
3. Try Python: `python3 -c "import torch; print(torch.__version__)"`
4. Run Jupyter: `jupyter notebook --ip=0.0.0.0 --no-browser --allow-root`
5. Create your first experiment in `llm_experiments/`

---

**Last updated:** 2026-05-07
**Status:** Ready to use — Docker container is configured and awaiting your first experiment.
